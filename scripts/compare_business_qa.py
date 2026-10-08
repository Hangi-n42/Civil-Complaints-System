"""QAFactEval-inspired Korean question/answer comparison, without English learned scorers."""
import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path
import sys
import json

from compare_business_nli import read,write,sha
from compare_business_natlogic import object_schema as obj,array_schema as arr

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/knowledge/evaluations/business_nli_20261009'
OUT=ROOT/'data/knowledge/evaluations/business_qa_compare_20261009'
MODEL='qwen3.8:27b-q4_K_M'
QG=(
    '각 후보만 읽고 그 후보가 실제 주장하는 내용을 검증할 질문을 1~3개 생성한다. 원문과 정답은 제공되지 않는다. '
    '질문당 answer_quote는 후보에서 질문의 답에 해당하는 정확한 연속 인용이다. 후보를 수정하거나 없는 조건/주체/의무를 보태지 않는다. '
    '주체·행위·대상·조건·시점·순서·의무/허용 중 실제 주장의 핵심이 질문과 답에서 빠지지 않게 한다. '
    '조건부 주장은 적용 조건/범위 자체도 검증할 수 있게 묻고, 그 조건을 이미 맞는 사실로 질문에 숨겨 넣지 않는다. '
    '질문은 독립 문서에 물어볼 수 있어야 하며 잘못된 전제의 이유를 요구하거나 참거짓 정답을 유도하지 않는다. '
    '일부 포함 관계를 전체 목록 충분성 질문으로 바꾸지 않는다. 복합 주장은 여러 항목을 묶어 물어도 되지만 빠진 핵심이 있으면 coverage=incomplete로 남긴다. '
    '질문 개수만으로 coverage를 complete라 하지 않는다. 각 질문 id는 후보 id+":"+번호로 만든다. '
    '출력에는 후보별 id, questions, coverage(complete/incomplete), coverage_reason만 담는다.')
QA=(
    '주어진 문서만으로 각 질문에 답한다. 질문은 검증할 대상이며 질문 속 전제를 문서의 사실로 받아들이지 않는다. '
    '외부 지식이나 다른 문서의 내용을 보태지 않는다. 문서가 질문의 일반화/의무/대상/조건을 뒷받침하지 않으면 '
    '문서가 실제로 말하는 적용 범위와 한정을 답에 명시한다. 자료 부족과 명시 반증, 조건 밖 면제/금지를 구별한다. '
    '답을 결정할 수 없으면 answerable=false로 남기고 임의로 답하지 않는다. '
    'answer에는 실제 조건·주체·순서·양태와 필요한 괄호 내용을 보존한다. 일부 항목 질문에 전체 서류가 없다고 답변 불가로 하지 않는다. '
    'evidence는 block_id와 그 블록에 한번 등장하는 정확한 연속 quote 목록이다. '
    '답의 의미에 필요한 부모/제목 조건과 같은 문장 내 한정도 근거에 포함한다. '
    '모든 질문 id에 answerable, answer, evidence, 짧은 reason을 한번씩 출력한다.')
COMPARE=(
    '동일 질문의 candidate_answer와 source_answer를 대조한다. 두 QA는 서로 다른 문맥에서 생성됐다. '
    '질문, 후보에서 질문을 만들 때 선택한 answer_quote, 양쪽 답/근거와 실제 인용 블록/부모를 확인한다. '
    '질문이 후보의 뜻을 바꾸거나 잘못된 전제를 강요하면 valid_question=false다. '
    'candidate_answer가 후보의 해당 주장에 충실한지도 확인하고, 질문에 핵심 조건/주체/양태가 빠지면 성공 처리하지 않는다. '
    'source_answer와 근거가 candidate_answer의 내용을 단방향으로 지지하는지 판정한다. '
    '원문이 더 상세하고 후보가 참인 일부 포함만 말해도 supported이며 두 답의 완전 동등/문자열 일치를 요구하지 않는다. '
    '짧은 인용이 같아도 전체 인용 블록이나 부모의 조건·양태와 다르면 supported가 아니다. '
    '관측된 적용 범위 확대 등 원문 미지지는 not_supported, 명시적인 반대 내용은 contradicted다. '
    '제공 답/근거가 부족하거나 QA가 답변 불가이면 unresolved다. 그 자체를 not_supported 성공으로 바꾸지 않는다. '
    '원문 조건 밖의 면제/금지를 만들지 않는다. 정정문이나 새질문을 만들지 말고 질문별 id,valid_question,verdict,reason을 출력한다.')


def schemas():
    s={'type':'string'};boolean={'type':'boolean'}
    questions=obj(dict(candidates=arr(obj(dict(id=s,questions=arr(obj(dict(id=s,question=s,answer_quote=s))),
        coverage={'type':'string','enum':['complete','incomplete']},coverage_reason=s)))))
    answers=obj(dict(answers=arr(obj(dict(id=s,answerable=boolean,answer=s,
        evidence=arr(obj(dict(block_id=s,quote=s))),reason=s)))))
    verdicts=obj(dict(comparisons=arr(obj(dict(id=s,valid_question=boolean,
        verdict={'type':'string','enum':['supported','not_supported','contradicted','unresolved']},reason=s)))))
    return questions,answers,verdicts


def exact_rows(rows,ids):
    if len(set(ids))!=len(ids) or len(rows)!=len(ids) or {r['id'] for r in rows}!=set(ids): raise ValueError('missing_or_duplicate_ids')
    return {r['id']:r for r in rows}


def grounded_answer(answer,blocks,parents):
    lookup={b['id']:b for b in blocks};selected=set()
    for ref in answer['evidence']:
        if ref['block_id'] not in lookup or not ref['quote'] or lookup[ref['block_id']]['text'].count(ref['quote'])!=1:
            raise ValueError('nonunique_or_absent_evidence')
        selected.add(ref['block_id'])
    if answer['answerable'] and (not selected or not answer['answer'].strip()): raise ValueError('answer_without_evidence')
    # Preserve whole cited blocks and existing parents; do not hand-select a correct semantic span.
    while True:
        expanded=selected|{p for row in parents if row['block_id'] in selected for p in row['parent_block_ids']}
        if expanded==selected: break
        selected=expanded
    if not selected <= set(lookup): raise ValueError('missing_parent')
    return dict(answer,cited_blocks=[b for b in blocks if b['id'] in selected],
        source_parents=[r for r in parents if r['block_id'] in selected])


def aggregate(comparisons,ready):
    if not ready or not comparisons or any(not c['valid_question'] or c['verdict']=='unresolved' for c in comparisons):
        return None
    if any(c['verdict']=='contradicted' for c in comparisons): return 'R'
    if any(c['verdict']=='not_supported' for c in comparisons): return 'N'
    return 'S'


def freeze():
    assert not (OUT/'freeze.json').exists()
    inputs=read(BASE/'inputs.json');packet=read(BASE/'source_packet.json')
    write(OUT/'inputs.json',dict(candidates=[dict(id=x['id'],text=x['hypothesis']) for x in inputs],
        blocks=packet['blocks'],source_parents=packet['source_parents']))
    write(OUT/'criteria.json',dict(expected=dict(c13='S',c46='S',c47='N',c11='S'),
        gate='All four labels plus question coverage, faithful independent answers and source-grounded comparison.',
        exposure='All cases development-exposed; no holdout or product calls after failure.',
        failures='Missing questions, incomplete coverage, failed/unanswerable QA and invalid citations remain unresolved, never dropped.'))
    sys.path.insert(0,str(ROOT))
    from app.generation.model_client import ModelClient
    identity=ModelClient(dict(provider='ollama',endpoint='http://localhost:11434')).identities({'review':MODEL},{'review':49152})
    write(OUT/'freeze.json',dict(model=MODEL,identity=identity,context_tokens=49152,max_tokens=8192,think=False,temperature=0,timeout=1800,
        max_calls=7,max_questions_per_candidate=3,question_instruction=QG,answer_instruction=QA,comparison_instruction=COMPARE,schemas=schemas(),
        reference_revision='01177f11cc05f8b3e75511a0cfa54bac19324d09',reference_license='BSD-3-Clause; original algorithm idea, no upstream code copied.',
        variant='Korean Qwen QA task substitution; not original QAFactEval F1/LERC or English model reproduction.',
        batching='QG sees all claims but no source; each claim QA separate; source QA all questions together; comparison batched.',
        files={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'inputs.json',OUT/'criteria.json',BASE/'inputs.json',BASE/'source_packet.json',
            Path(__file__),ROOT/'scripts/compare_business_nli.py',ROOT/'scripts/compare_business_natlogic.py',
            ROOT/'app/generation/model_client.py',ROOT/'app/generation/service.py']}))


async def run():
    sys.path.insert(0,str(ROOT))
    from app.generation.model_client import ModelClient,ModelRequest
    f=read(OUT/'freeze.json');data=read(OUT/'inputs.json')
    assert all(sha(ROOT/p)==v for p,v in f['files'].items())
    assert not (OUT/'started.json').exists()
    client=ModelClient(dict(provider='ollama',endpoint='http://localhost:11434'))
    assert client.identities({'review':MODEL},{'review':49152})==f['identity']
    write(OUT/'started.json',dict(freeze_sha256=sha(OUT/'freeze.json')))
    calls=[];result=dict(cases=[dict(id=c['id'],status='pending',verdict=None) for c in data['candidates']],gate_passed=False)
    async def call(stage,instruction,context,schema):
        req=ModelRequest(stage,MODEL,[dict(role='system',content=instruction),dict(role='user',content=json.dumps(context,ensure_ascii=False))],
            schema=schema,max_tokens=f['max_tokens'],context_tokens=f['context_tokens'],think=f['think'],timeout=f['timeout'])
        rec=dict(request=asdict(req));calls.append(rec);write(OUT/'calls.json',calls)
        rec['response']=await client.generate(req);write(OUT/'calls.json',calls)
        print(stage,rec['response']['failure_kind'],rec['response']['elapsed_s'],flush=True)
        if rec['response']['failure_kind']: raise ValueError(rec['response']['failure_kind'])
        return rec['response']['parsed']
    try:
        qs,ans,vs=schemas()
        generated=await call('qa_generate_questions',QG,dict(candidates=data['candidates']),qs)
        write(OUT/'questions.json',generated)
        write(OUT/'questions_freeze.json',dict(questions_sha256=sha(OUT/'questions.json'),freeze_sha256=sha(OUT/'freeze.json')))
        groups=exact_rows(generated['candidates'],[c['id'] for c in data['candidates']]);questions=[];claim_answers={}
        for c,record in zip(data['candidates'],result['cases']):
            group=groups[c['id']];current=group['questions'];record['coverage']=group['coverage']
            try:
                if not 1<=len(current)<=3: raise ValueError('question_count')
                exact_rows(current,[q['id'] for q in current])
                for q in current:
                    if not q['id'].startswith(c['id']+':') or not q['question'].strip(): raise ValueError('question_id')
                    if not q['answer_quote'] or c['text'].count(q['answer_quote'])!=1: raise ValueError('question_answer_span')
                questions.extend(dict(q,candidate_id=c['id']) for q in current)
                record['question_ids']=[q['id'] for q in current]
                output=await call('qa_candidate_'+c['id'],QA,dict(blocks=[c],source_parents=[],
                    questions=[dict(id=q['id'],question=q['question']) for q in current]),ans)
                write(OUT/(c['id']+'_answers.json'),output)
                rows=exact_rows(output['answers'],record['question_ids'])
                claim_answers.update({k:grounded_answer(v,[c],[]) for k,v in rows.items()})
            except (ValueError,KeyError,TypeError) as exc: record.update(status='unresolved',error=str(exc))
        if not questions: raise ValueError('no_usable_questions')
        assert sha(OUT/'questions.json')==read(OUT/'questions_freeze.json')['questions_sha256']
        source=await call('qa_source',QA,dict(blocks=data['blocks'],source_parents=data['source_parents'],
            questions=[dict(id=q['id'],question=q['question']) for q in questions]),ans)
        write(OUT/'source_answers.json',source)
        source_rows=exact_rows(source['answers'],[q['id'] for q in questions]);pairs=[]
        for q in questions:
            record=next(r for r in result['cases'] if r['id']==q['candidate_id'])
            try:
                a=grounded_answer(source_rows[q['id']],data['blocks'],data['source_parents'])
                pairs.append(dict(q,candidate_answer=claim_answers[q['id']],source_answer=a))
            except (ValueError,KeyError,TypeError) as exc: record.update(status='unresolved',error=str(exc))
        if pairs:
            comparison=await call('qa_compare_answers',COMPARE,dict(pairs=pairs),vs)
            write(OUT/'comparisons.json',comparison);write(OUT/'comparison_inputs.json',pairs)
            rows=exact_rows(comparison['comparisons'],[p['id'] for p in pairs])
            for record in result['cases']:
                own=[p for p in pairs if p['candidate_id']==record['id']]
                checks=[rows[p['id']] for p in own]
                ready=record['status']=='pending' and record['coverage']=='complete' and len(own)==len(record.get('question_ids',[]))
                ready=ready and all(p['candidate_answer']['answerable'] and p['source_answer']['answerable'] for p in own)
                verdict=aggregate(checks,ready)
                record.update(verdict=verdict,status='calculated' if verdict else 'unresolved',comparisons=checks)
        expected=read(OUT/'criteria.json')['expected']
        result['label_gate_passed']=all(r['verdict']==expected[r['id']] for r in result['cases'])
        result['semantic_gate']='Requires question/QA/context review; no automatic success from declared coverage.'
    except (ValueError,KeyError,TypeError) as exc: result['execution_error']=str(exc)
    finally:
        for r in result['cases']:
            if r['status']=='pending': r['status']='not_completed'
        result['calls']=len(calls)
        result['cost']=dict(input_tokens=sum(c.get('response',{}).get('prompt_eval_count') or 0 for c in calls),
            output_tokens=sum(c.get('response',{}).get('eval_count') or 0 for c in calls),elapsed_s=sum(c.get('response',{}).get('elapsed_s') or 0 for c in calls))
        write(OUT/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run'])
    args=parser.parse_args();OUT.mkdir(exist_ok=True,parents=True);freeze() if args.mode=='freeze' else asyncio.run(run())

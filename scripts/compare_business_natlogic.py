"""Zero-NatVer-inspired hard-label diagnostic, not a paper reproduction or product judge."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/knowledge/evaluations/business_nli_20261009'
OUT = ROOT / 'data/knowledge/evaluations/business_natlogic_20261009'
MODEL = 'qwen3.8:27b-q4_K_M'
PRIORITY = ['equivalent', 'negation', 'forward', 'reverse', 'alternation']
# Evidence -> claim. Figure 1, Strong et al. 2024; independence is absorbing.
TRANSITIONS = {
    'S': dict(equivalent='S', forward='S', reverse='N', negation='R', alternation='R', independent='N'),
    'R': dict(equivalent='R', forward='N', reverse='R', negation='S', alternation='N', independent='N'),
    'N': dict.fromkeys([*PRIORITY, 'independent'], 'N'),
}
QUESTIONS = {
    'equivalent': ['원문 구간 E와 후보 구간 C가 실제 문맥의 조건·주체·양태를 유지한 채 서로 같은 뜻인가?',
                   '문맥에서 E가 주장하는 내용과 C가 주장하는 내용은 양방향으로 성립하며 의미 범위가 같은가?'],
    'forward': ['실제 원문 문맥의 E가 참일 때 C의 내용도 반드시 성립하는가?',
                '문맥의 E만으로 C를 도출할 수 있는가? 조건·의무·대상의 범위를 새로 보태거나 넓히면 안 된다.'],
    'reverse': ['실제 문맥에서 C가 참이면 E는 반드시 성립하지만, E만으로 C가 반드시 성립하지는 않는가?',
                'C가 E보다 엄격한 의미여서 C에서 E로의 추론만 성립하고 그 역방향 추론은 보장되지 않는가?'],
    'negation': ['동일한 조건·대상·시점에서 E와 C가 서로 정확한 부정으로 하나가 참이면 다른 하나가 거짓이며 둘 다 거짓일 수도 없는가?',
                 '같은 문맥의 가능한 상황을 E와 C가 겹침 없이 전부 양분하는 정확한 상보 관계인가?'],
    'alternation': ['동일 문맥에서 E와 C가 동시에 참일 수 없지만 둘 다 거짓일 수는 있는가?',
                    'E와 C는 실제 의미상 서로 배제되되 가능한 모든 상황을 둘만으로 다 덮지는 않는가?'],
}
ALIGN_INSTRUCTION = (
    '후보를 원문과 대조할 연속 구간으로 자동 분할하고 각 구간의 원문을 정렬한다. 최종 판정은 하지 않는다. '
    'tokens는 후보의 원래 문자열을 빈틈없이 나눈 주소이다. 각 part의 end는 1부터 시작한 마지막 token 번호다. '
    '첫 token부터 끝까지 원래 순서로 한 번씩 모두 포함해야 한다. 재작성·생략·순서 변경은 하지 않는다. '
    '조건/부정/양태/주체가 행위나 목록을 제한하면 그 적용을 잃지 않는 구간을 선택하고 필요하면 큰 구간을 유지한다. '
    'evidence는 실제 block_id와 그 블록에 한 번만 등장하는 정확한 연속 인용 목록이다. 부모 조건도 함께 대조한다. '
    '정렬할 원문이 없으면 evidence를 비운다. signal은 정렬의 support/refute/unclear이며 최종 판정이 아니다. '
    'scope_supported는 이 정렬이 복잡한 양태·부정·조건을 손실 없이 같은 적용 문맥에서 비교할 수 있을 때만 true다. '
    '미해석 적용 범위는 scope_supported=false와 reason으로 남긴다. 일부 구비 항목의 참과 전체 목록 충분성을 구분한다.')
MICRO_INSTRUCTION = (
    '각 pair에 대해 주어진 한 가지 의미 관계 질문에만 yes/no/unknown으로 답한다. 최종 후보 판정이나 다른 관계는 만들지 않는다. '
    'E는 evidence 인용의 원문 의미, C는 claim_span이다. full_source와 source_parents, full_claim은 적용 문맥이다. '
    '문자열 포함·단어 겹침은 의미 함의가 아니다. 조건·대상·주체·기간·의무/허용/서술·부정을 실제 문맥에서 보존한다. '
    'E에 조건이 있다고 조건 밖 면제/금지를 만들지 않는다. 원문 미지지는 명시 반증과 다르다. '
    '불명확한 관계는 unknown으로 기록한다. reason에는 E/C의 실제 관계를 간결히 설명한다. '
    '후보 자체의 부분 사실과 요구 전체 목록의 충분성을 혼동하지 않는다.')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(text):
    return [m.group() for m in re.finditer(r'\s*\S+', text)] + ([text[len(text.rstrip()):]] if text.rstrip() != text else [])


def aligned_pairs(candidate, parts, blocks):
    units = tokens(candidate['hypothesis'])
    assert ''.join(units) == candidate['hypothesis']
    source = {b['id']: b for b in blocks}
    previous, pairs = 0, []
    for i, part in enumerate(parts):
        end = part['end']
        if type(end) is not int or not previous < end <= len(units):
            raise ValueError('partition_boundary')
        refs = []
        for ref in part['evidence']:
            block = source.get(ref['block_id'])
            if not block or not ref['quote'] or block['text'].count(ref['quote']) != 1:
                raise ValueError('nonunique_or_absent_evidence')
            start = block['text'].index(ref['quote'])
            refs.append(dict(ref, start_char=start, end_char=start + len(ref['quote'])))
        pairs.append(dict(id=f"{candidate['id']}:{i+1}", candidate_id=candidate['id'],
            claim_span=''.join(units[previous:end]), claim_start=len(''.join(units[:previous])),
            claim_end=len(''.join(units[:end])), full_claim=candidate['hypothesis'],
            evidence=refs, signal=part['signal'], scope_supported=part['scope_supported'], reason=part['reason']))
        previous = end
    if previous != len(units):
        raise ValueError('incomplete_coverage')
    return pairs


def compose(operators):
    if not operators:
        raise ValueError('empty_proof')
    state, trace = 'S', []
    for op in operators:
        next_state = TRANSITIONS[state][op]
        trace.append(dict(before=state, operator=op, after=next_state))
        state = next_state
    return state, trace


def select_operator(judgments, signal):
    allowed = {'support': ['equivalent', 'forward'],
               'refute': ['negation', 'reverse', 'alternation'], 'unclear': PRIORITY}[signal]
    scores = {op: sum(v == 'yes' for v in judgments[op]) / 2 for op in allowed}
    if any(v == 'unknown' for op in allowed for v in judgments[op]):
        return None, scores, 'unresolved_microjudgment'
    eligible = [op for op in PRIORITY if op in allowed and scores[op] > .5]
    if eligible:
        return eligible[0], scores, None
    if any(scores.values()):
        return None, scores, 'microjudgment_disagreement'
    return 'independent', scores, None


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def array_schema(items):
    return dict(type='array', items=items)


def freeze():
    assert not (OUT/'freeze.json').exists()
    inputs, packet = read(BASE/'inputs.json'), read(BASE/'source_packet.json')
    write(OUT/'inputs.json', inputs)
    write(OUT/'source_packet.json', packet)
    write(OUT/'criteria.json', dict(expected={'c13':'S', 'c46':'S', 'c47':'N', 'c11':'S'},
        gate='All four labels AND source-grounded reasons/local relations must pass; N alone is not scope-error detection.',
        failure='Coverage/scope/unknown/disagreement/model failures stay in denominator; no silent conversion to document NEI.',
        exposure='All four development exposed. No holdout execution in this diagnostic.'))
    sys.path.insert(0, str(ROOT))
    from app.generation.model_client import ModelClient
    client = ModelClient(dict(provider='ollama', endpoint='http://localhost:11434'))
    identity = client.identities({'review':MODEL}, {'review':49152})
    write(OUT/'freeze.json', dict(method='Zero-NatVer-inspired 2-template hard-label full-context variant',
        reference_revision='e97735004c1568b827a497fac7f4fab03daac883', reference_license='AGPL-3.0; no official code copied',
        direction='evidence -> claim', transitions=TRANSITIONS, priority=PRIORITY, questions=QUESTIONS,
        alignment_instruction=ALIGN_INSTRUCTION, micro_instruction=MICRO_INSTRUCTION,
        model=MODEL, identity=identity, context_tokens=49152, max_tokens=8192, temperature=0, think=False, timeout=1800,
        maximum_calls=11, micro_batching='One separate request per operator/template; all valid pairs share a batch; not independent pair sampling.',
        differences=['Auto partition via boundary indices with post-validation, not token-follow constrained logits.',
            'Alignment uses exact quotes with Unicode validation, not upstream ASCII filtering.',
            'Two original Korean templates per operator, hard-label equal weights, not ten likelihood-weighted prompts.',
            'Full source/claim context retained for local judgments, not only local spans.',
            'No invented modal/polarity projection; non-composable scope is unresolved; conditional validity still relies on model judgments.'],
        files={p.name:sha(p) for p in [OUT/'inputs.json', OUT/'source_packet.json', OUT/'criteria.json']},
        originals={str(p.relative_to(ROOT)):sha(p) for p in [BASE/'inputs.json', BASE/'source_packet.json']},
        code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__), ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py']}))


async def run():
    sys.path.insert(0, str(ROOT))
    from app.generation.model_client import ModelClient, ModelRequest
    f=read(OUT/'freeze.json')
    assert all(sha(OUT/p)==v for p,v in f['files'].items())
    assert all(sha(ROOT/p)==v for p,v in {**f['originals'], **f['code']}.items())
    assert not (OUT/'started.json').exists(), 'Single frozen run only'
    client=ModelClient(dict(provider='ollama', endpoint='http://localhost:11434'))
    assert client.identities({'review':MODEL}, {'review':49152}) == f['identity']
    write(OUT/'started.json', dict(freeze_sha256=sha(OUT/'freeze.json')))
    inputs, packet=read(OUT/'inputs.json'), read(OUT/'source_packet.json')
    calls=[]
    async def call(stage, instruction, context, schema):
        req=ModelRequest(stage, MODEL, [dict(role='system', content=instruction),
            dict(role='user', content=json.dumps(context, ensure_ascii=False))], schema=schema,
            max_tokens=f['max_tokens'], context_tokens=f['context_tokens'], think=f['think'], timeout=f['timeout'])
        record=dict(request=asdict(req))
        calls.append(record);write(OUT/'calls.json', calls)
        record['response']=await client.generate(req)
        write(OUT/'calls.json', calls)
        print(stage, record['response']['failure_kind'], record['response']['elapsed_s'], flush=True)
        if record['response']['failure_kind']:
            raise ValueError(record['response']['failure_kind'])
        return record['response']['parsed']
    string=dict(type='string')
    evidence=object_schema(dict(block_id=string, quote=string))
    part=object_schema(dict(end=dict(type='integer'), evidence=array_schema(evidence),
        signal=dict(type='string', enum=['support','refute','unclear']), scope_supported=dict(type='boolean'), reason=string))
    alignment_schema=object_schema(dict(candidates=array_schema(object_schema(dict(id=string, parts=array_schema(part))))))
    result=dict(cases=[], calls=0, gate_passed=False)
    try:
        alignment=await call('natlogic_alignment', ALIGN_INSTRUCTION, dict(source=packet['blocks'],
            source_parents=packet['source_parents'], candidates=[dict(id=x['id'], claim=x['hypothesis'],
                tokens=[dict(id=i+1,text=t) for i,t in enumerate(tokens(x['hypothesis']))]) for x in inputs]), alignment_schema)
        write(OUT/'alignment.json', alignment)
        pairs=[]
        for candidate in inputs:
            rows=[r for r in alignment['candidates'] if r['id']==candidate['id']]
            record=dict(id=candidate['id'], status='pending', verdict=None)
            result['cases'].append(record)
            try:
                if len(rows)!=1: raise ValueError('missing_or_duplicate_candidate')
                record['pairs']=aligned_pairs(candidate, rows[0]['parts'], packet['blocks'])
                if any(not p['scope_supported'] for p in record['pairs']): raise ValueError('unsupported_composition_scope')
                if any(not p['evidence'] for p in record['pairs']): raise ValueError('unaligned_claim_scope')
                pairs.extend(record['pairs'])
            except (ValueError,KeyError,TypeError) as exc:
                record.update(status='alignment_failure', error=str(exc))
        micro={p['id']:{op:[] for op in PRIORITY} for p in pairs}
        reasons={p['id']:{op:[] for op in PRIORITY} for p in pairs}
        if pairs:
            schema=object_schema(dict(answers=array_schema(object_schema(dict(id=string,
                answer=dict(type='string',enum=['yes','no','unknown']), reason=string)))))
            for op in PRIORITY:
                for i, question in enumerate(QUESTIONS[op]):
                    output=await call(f'natlogic_{op}_{i+1}', MICRO_INSTRUCTION, dict(question=question,
                        full_source=packet['blocks'], source_parents=packet['source_parents'],
                        pairs=[{k:v for k,v in p.items() if k not in {'signal','reason','scope_supported'}} for p in pairs]), schema)
                    if len(output['answers'])!=len(pairs) or {a['id'] for a in output['answers']}!=set(micro):
                        raise ValueError('microjudgment_coverage')
                    for a in output['answers']:
                        micro[a['id']][op].append(a['answer']);reasons[a['id']][op].append(a['reason'])
                    write(OUT/'microjudgments.json', dict(answers=micro, reasons=reasons))
        for record in result['cases']:
            if record['status']!='pending': continue
            operators=[]
            for p in record['pairs']:
                op,scores,error=select_operator(micro[p['id']], p['signal'])
                p.update(operator=op, scores=scores, error=error, microjudgments=micro[p['id']], micro_reasons=reasons[p['id']])
                if error: record.update(status='unresolved', error=error)
                operators.append(op)
            if record['status']=='pending':
                verdict,trace=compose(operators);record.update(status='succeeded', verdict=verdict, trace=trace)
        expected=read(OUT/'criteria.json')['expected']
        result['label_gate_passed']=all(r['status']=='succeeded' and r['verdict']==expected[r['id']] for r in result['cases'])
        result['semantic_gate']='Requires source/reason review; label equality alone is insufficient.'
    except (ValueError,KeyError,TypeError) as exc:
        result['execution_error']=str(exc)
    finally:
        present={r['id'] for r in result['cases']}
        result['cases'].extend(dict(id=x['id'],status='not_completed',verdict=None) for x in inputs if x['id'] not in present)
        result['calls']=len(calls)
        result['cost']=dict(input_tokens=sum(c.get('response',{}).get('prompt_eval_count') or 0 for c in calls),
            output_tokens=sum(c.get('response',{}).get('eval_count') or 0 for c in calls),
            elapsed_s=sum(c.get('response',{}).get('elapsed_s') or 0 for c in calls))
        write(OUT/'result.json', result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['freeze','run'])
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    freeze() if args.mode=='freeze' else asyncio.run(run())

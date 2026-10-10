"""Frozen explicit no-duty candidate comparison; research only, no product writes."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import compare_business_candidate_contrast as previous

base, read, write, sha = previous.base, previous.read, previous.write, previous.sha
OUT = previous.OUT.parent / 'business_explicit_opposition_20261010'
INSTRUCTION = previous.INSTRUCTION.replace('candidates X/Y 각각의', 'candidates에 있는 모든 후보 각각의')
INSTRUCTION = INSTRUCTION.replace('두 후보의 실제', '후보들의 실제')
INSTRUCTION = INSTRUCTION.replace('반드시 한쪽만 옳다고', '반드시 한 후보만 옳다고')
INSTRUCTION = INSTRUCTION.replace('둘 다 지지, 둘 다 미지지', '여러 후보가 지지, 여러 후보가 미지지')
INSTRUCTION = INSTRUCTION.replace(
    'differences는 [{"X":{"field":"...","quote":"..."},"Y":{"field":"...","quote":"..."},"dimensions":["..."],"reason":"..."}]다.',
    'differences는 목록이다. 각 항목은 비교한 후보 ID 두 개 이상을 키로 갖고 각 값은 {"field":"...","quote":"..."}이며, dimensions와 reason도 갖는다. 입력에 없는 후보 ID는 쓰지 않는다. 후보가 하나면 differences는 빈 목록이고 그 후보 자체를 판단한다.')
INSTRUCTION = INSTRUCTION.replace('judgments는 {"X":판단,"Y":판단}이다.',
                                  'judgments는 입력의 모든 후보 ID를 키로 갖고 각 값은 판단이다.')


def prompt(cases):
    context = lambda c: {k: v for k, v in c.items() if k not in ['id', 'raw']}
    assert 1 <= len(cases) <= 3
    source = context(next(iter(cases.values())))
    assert all(context(c) == source for c in cases.values())
    payload = dict(context=source, candidates={k: c['raw'] for k, c in cases.items()})
    return ('<|im_start|>system\n' + INSTRUCTION + '<|im_end|>\n<|im_start|>user\n' +
            json.dumps(payload, ensure_ascii=False) + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{')


def parse(content, cases):
    answer = json.loads('{' + content, object_pairs_hook=previous.strict_object)
    if list(answer) != ['differences', 'judgments'] or set(answer['judgments']) != set(cases):
        raise ValueError('candidate_coverage')
    if not isinstance(answer['differences'], list) or (len(cases) == 1 and answer['differences']):
        raise ValueError('difference_cardinality')
    for d in answer['differences']:
        ids = set(d) - {'dimensions', 'reason'}
        if not {'dimensions', 'reason'} <= set(d) or not 2 <= len(ids) <= len(cases) or not ids <= set(cases):
            raise ValueError('difference_candidates')
        for key in ids:
            previous.refs.exact(d[key], cases[key], candidate=True)
        if not d['dimensions'] or not set(d['dimensions']) <= {'condition', 'subject', 'action', 'modality', 'wording', 'uncertain'}:
            raise ValueError('difference_dimensions')
        if not isinstance(d['reason'], str) or not d['reason'].strip():
            raise ValueError('difference_reason')
    for key, case in cases.items():
        # Keep the frozen per-candidate contract; only candidate cardinality changes.
        judgment = answer['judgments'][key]
        previous.refs.parse(dict(differences=[], judgments=dict(X=judgment, Y=judgment)), case, case)
    return answer


def construct(raw):
    changed = previous.derive(raw, 'no_obligation')
    old, new = raw['Event'], changed['Event']
    ending = next(e for e in previous.ENDINGS.values() if old.endswith(e))
    start = len(old) - len(ending)
    assert old[:start] == new[:start]
    assert {k: v for k, v in raw.items() if k != 'Event'} == {k: v for k, v in changed.items() if k != 'Event'}
    return dict(raw=changed, field='Event', before_span=[start, len(old)], after_span=[start, len(new)],
                before_quote=ending, after_quote=previous.ENDINGS['no_obligation'], semantic_validity='unverified')


def audit_construction():
    source = read(OUT / 'stored_claim_inventory.json')
    rows = []
    for claim in source['claims']:
        raw = deepcopy(claim['raw'])
        row = dict(id=claim['id'], before_raw=raw)
        try:
            row.update(status='constructed_unverified', construction=construct(raw))
        except ValueError as error:
            row.update(status='unsupported', reason=str(error))
        assert raw == claim['raw']
        rows.append(row)
    write(OUT / 'construction_audit.json', dict(at=time.time(),source_database=source['source_database'],
        source_sha256=source['sha256'], run_id=source['run_id'], total=len(rows),
        constructed=sum(r['status']=='constructed_unverified' for r in rows), rows=rows,
        limits='Suffix construction only; no gold/source supplied to constructor, no semantic or stored-error success, no model calls or DB writes'))
    print('Construction audit:',len(rows),'total;',sum(r['status']=='constructed_unverified' for r in rows),'constructed, meaning unverified')


def selfcheck():
    raw = dict(Event='같은 조건에서 신청해야 한다.', Entity=['신청인'], period='원래 기간')
    derived = construct(raw)
    assert derived['raw'] == dict(raw, Event='같은 조건에서 신청할 의무는 없다.')
    assert raw['Event'] == '같은 조건에서 신청해야 한다.'
    for event in ['번호를 변경한다.', '반드시 신청해야 한다.', '신청해야 한다. 신청해야 한다.']:
        try: construct(dict(Event=event))
        except ValueError: pass
        else: raise AssertionError('unsupported construction accepted')
    case = dict(id='a', raw=raw, blocks=[dict(id='b1',text='직접 신청해야 한다.')], source_parents=[])
    judgment = dict(label='1',error_fields=[],error_spans=[],evidence=[dict(block_id='b1',quote='직접 신청해야 한다.')],reason='일치')
    for size in [1,2,3]:
        cases = {k:case for k in ['X','Y','Z'][:size]}
        payload = json.loads(prompt(cases).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
        assert payload['context']['blocks'] == case['blocks'] and payload['candidates'] == {k:raw for k in cases}
        answer=dict(differences=[],judgments={k:deepcopy(judgment) for k in cases})
        content=json.dumps(answer,ensure_ascii=False)[1:]
        assert parse(content,cases)==answer
        answer['judgments']['missing']=judgment
        try:parse(json.dumps(answer)[1:],cases)
        except ValueError:pass
        else:raise AssertionError('unknown candidate accepted')
    print('Constructor preservation/rejection, one-to-three candidate coverage and exact evidence contracts passed')


def prepare():
    assert not (OUT/'prepared.json').exists()
    old={r['id']:r for r in read(previous.OUT/'inputs.json')}
    na=read(previous.OUT/'confirmation/inputs.json')
    pairs=[('na',na[0],na[1],'confirmation/run/NA_pair1_joint_response.json')]
    pairs += [(p,old[p]['X'],old[p]['Y'],f'run/{p}_joint_response.json') for p in ['p1','p2','p3','p5']]
    rows=[]; baselines=[]
    for ident,x,y,path in pairs:
        cases=dict(X=x,Y=y)
        if ident!='p5':
            generated=construct(x['raw'])
            cases['Z']=dict(deepcopy(x),raw=generated['raw'])
        else:generated=None
        response=previous.OUT/path
        answer=previous.parse(read(response)['content'],x,y)
        if ident=='na':
            original=next(r for r in read(previous.OUT/'confirmation/requests.json') if r['id']=='NA_pair1')
        else:original=next(r for r in read(previous.OUT/'requests.json') if r['id']==ident)
        assert original['prompt']==previous.prompt(x,y)
        baselines.append(dict(id=ident,answer=answer,prompt=original['prompt'],request=original['request'],
                              path=str(response),sha256=sha(response)))
        rows.append(dict(id=ident,phase='initial',cases=cases,construction=generated,prompt=prompt(cases)))
    for ident,case in [('NA02',na[1]),('p1X',old['p1']['X'])]:
        cases=dict(X=case)
        rows.append(dict(id=ident,phase='single',cases=cases,prompt=prompt(cases)))
    write(OUT/'inputs.json',rows);write(OUT/'baselines.json',baselines)
    files=[OUT/n for n in ['inputs.json','baselines.json','criteria.json','execution_authorization.json']]
    code=[Path(__file__),Path(previous.__file__),Path(base.__file__),Path(previous.refs.__file__),
          previous.ROOT/'scripts/compare_business_modality_spans.py',previous.ROOT/'scripts/business_dependency_parser.py']
    write(OUT/'prepared.json',dict(at=time.time(),initial_calls=5,conditional_single_calls=2,
        base_commit='def333024f1df79f09888cd3a1862d7b1885f523',
        files={str(p):sha(p) for p in files},code={str(p):sha(p) for p in code}))


def check():
    d=read(OUT/'prepared.json')
    assert all(sha(Path(p))==h for p,h in {**d['files'],**d['code']}.items())
    assert all(sha(Path(b['path']))==b['sha256'] for b in read(OUT/'baselines.json'))


def preflight():
    assert not (OUT/'freeze.json').exists()
    check();props=base.api('/props');old=read(previous.OUT/'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old.items() if k!='media_marker'}
    for b in read(OUT/'baselines.json'):
        ids=base.api('/tokenize',dict(content=b['prompt'],add_special=False,parse_special=True))['tokens']
        assert b['request']==dict(read(previous.prior.OUT/'settings.json'),prompt=ids)
    rows=[]
    for row in read(OUT/'inputs.json'):
        assert all(m not in row['prompt'] for m in [props['media_marker'],old['media_marker']])
        ids=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
        assert len(ids)+2048<8192
        rows.append(dict(row,input_tokens=len(ids),request=dict(read(previous.prior.OUT/'settings.json'),prompt=ids)))
    write(OUT/'requests.json',rows);write(OUT/'props.json',props)
    write(OUT/'freeze.json',dict(at=time.time(),files={n:sha(OUT/n) for n in ['prepared.json','requests.json','props.json','runtime_identity.json']}))
    print([(r['id'],r['phase'],r['input_tokens']) for r in rows])


def run(phase):
    check();assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props')==read(OUT/'props.json')
    if phase=='single':assert read(OUT/'initial_review.json')['passed'] is True
    dest=OUT/phase;dest.mkdir();result=dict(calls=0,records=[],semantic_review='pending');start=time.monotonic()
    for row in [r for r in read(OUT/'requests.json') if r['phase']==phase]:
        record=dict(id=row['id'],input_tokens=row['input_tokens'],contract_pass=False)
        result['records'].append(record);result['calls']+=1;write(dest/'result.json',result);before=time.monotonic()
        try:
            raw=base.call('/completion',row['request']);path=dest/f"{row['id']}_response.json";path.write_bytes(raw);response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('truncated') or response.get('stop_type')!='eos':raise ValueError('incomplete_generation')
            answer=json.loads('{'+response['content'],object_pairs_hook=previous.strict_object);record['answer']=answer
            mapping=base.MAPPINGS['primary'];record['semantic_labels']={k:mapping.get(v.get('label'),v.get('label') if v.get('label') in mapping.values() else None) for k,v in answer.get('judgments',{}).items()}
            try:parse(response['content'],row['cases']);record['contract_pass']=True
            except (ValueError,KeyError,TypeError,AssertionError) as error:record['contract_error']=repr(error)
        except (OSError,ValueError,KeyError,TypeError) as error:record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;result['wall_s']=time.monotonic()-start;write(dest/'result.json',result)
        print(row['id'],record.get('semantic_labels'),record['contract_pass'],flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode',choices=['selfcheck','audit_construction','prepare','preflight','initial','single'])
    mode=cli.parse_args().mode
    run(mode) if mode in ['initial','single'] else globals()[mode]()

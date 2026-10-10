"""Issue 649: unchanged source context with minimally different candidate claims."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import time

import compare_business_label_selection as base
import compare_business_joint_contrast as refs
import compare_business_entailment_boundary as prior
from compare_business_modality_spans import strict_object
from business_dependency_parser import read, write

ROOT = prior.ROOT
OUT = ROOT / 'data/knowledge/evaluations/business_candidate_contrast_20261010'
sha = prior.sha


ENDINGS = {'permission': '할 수 있다.', 'obligation': '해야 한다.',
           'no_obligation': '할 의무는 없다.', 'obligation_synonym': '할 의무가 있다.',
           'permission_synonym': '하는 것이 가능하다.'}


def derive(raw, target):
    text = raw.get('Event')
    if not isinstance(text, str) or target not in ENDINGS:
        raise ValueError('unsupported_candidate')
    matches = [ending for ending in ENDINGS.values() if text.endswith(ending) and text.count(ending) == 1]
    if len(matches) != 1 or any(cue in text for cue in ['반드시', '필수', '해야만']):
        raise ValueError('unmatched_or_conflicting_modality')
    ending = matches[0]
    result = deepcopy(raw)
    result['Event'] = text[:-len(ending)] + ENDINGS[target]
    if result == raw:
        raise ValueError('no_change')
    return result


INSTRUCTION = base.COMMON + '''
동일한 context 원문 전체와 부모/제목 문맥 아래 candidates X/Y 각각의 주장이 지지되는지 따로 판단한다. 한 후보의 주장을 다른 후보의 원문 근거로 가져오지 않는다.
두 후보의 실제 달라진 구절을 정확한 field/quote로 짚고 조건(condition)·주체(subject)·행위(action)·양태(modality)·표현만의 차이(wording) 중 무엇이 달라지는지 설명한다. 뜻이 같거나 해석이 미확정일 수도 있다.
반드시 한쪽만 옳다고 가정하지 않는다. 둘 다 지지, 둘 다 미지지, 명시 반증 또는 판단 불가도 가능하다. 의무의 명시 부정과 행위 금지는 다르며, 허용만으로 의무 없음이나 금지를 추론하지 않는다.
판정 코드 1=supported, 2=unsupported, 3=contradicted. 필요한 해석을 확정하지 못하면 label은 null이고 이유에 미확정을 남긴다. 필수 참조 전문이 제공되지 않았다면 이유에서 그 자료 부재를 구체적으로 구분한다.
출력은 differences와 judgments를 이 순서로 가진 JSON 하나다.
differences는 [{"X":{"field":"...","quote":"..."},"Y":{"field":"...","quote":"..."},"dimensions":["..."],"reason":"..."}]다. 차이를 특정하지 못하면 빈 목록과 각 판단 이유에 그 한계를 남긴다.
judgments는 {"X":판단,"Y":판단}이다. 각 판단은 label,error_fields,error_spans,evidence,reason을 갖는다. label은 코드 문자열 또는 null이다. error_fields는 해당 후보의 실제 문제 필드, error_spans는 [{"field":"...","quote":"해당 후보의 실제 문제 구절"}], evidence는 [{"block_id":"...","quote":"원문의 실제 구절"}], reason은 지지·미지지·명시 반증을 구분한 이유다.
supported이면 error_fields/error_spans는 빈 목록이다. 2/3이면 정확한 오류 필드·구절을 남긴다. 각 인용은 해당 원형 문자열에 정확히 한 번 있는 연속 부분문자열이며 개행을 바꾸지 않는다. 수정문·새 업무 규칙·현실의 면제 또는 금지를 만들어 쓰지 않는다.'''


def prompt(x, y):
    context = lambda case: {k:v for k,v in case.items() if k not in ['id','raw']}
    assert context(x) == context(y)
    payload = dict(context=context(x), candidates=dict(X=x['raw'],Y=y['raw']))
    return ('<|im_start|>system\n' + INSTRUCTION + '<|im_end|>\n<|im_start|>user\n' +
            json.dumps(payload,ensure_ascii=False) + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{')


def parse(content, x, y):
    answer = json.loads('{' + content, object_pairs_hook=strict_object)
    if list(answer) != ['differences','judgments'] or set(answer['judgments']) != {'X','Y'}:
        raise ValueError('joint_schema')
    if not isinstance(answer['differences'],list):
        raise ValueError('differences_schema')
    for difference in answer['differences']:
        if set(difference) != {'X','Y','dimensions','reason'}:
            raise ValueError('difference_schema')
        refs.exact(difference['X'],x,candidate=True); refs.exact(difference['Y'],y,candidate=True)
        if not difference['dimensions'] or not set(difference['dimensions']) <= {'condition','subject','action','modality','wording','uncertain'}:
            raise ValueError('difference_dimensions')
        if not isinstance(difference['reason'],str) or not difference['reason'].strip():
            raise ValueError('difference_reason')
    # Reuse the exact per-candidate evidence/label/span contract without source-difference references.
    refs.parse(dict(differences=[],judgments=answer['judgments']),x,y)
    return answer


def selfcheck():
    raw = {'Event':'대상이 조건 아래 신청해야 한다.', 'Entity':['대상']}
    changed = derive(raw,'permission')
    assert changed == {'Event':'대상이 조건 아래 신청할 수 있다.', 'Entity':['대상']}
    assert derive(changed,'obligation') == raw
    assert raw['Event'].endswith('해야 한다.')
    for text in ['대상이 신청한다.','대상이 반드시 신청해야 한다.','신청해야 한다. 신청해야 한다.']:
        try: derive({'Event':text},'permission')
        except ValueError: pass
        else: raise AssertionError('unsupported contrast silently repaired')
    x = dict(id='a',raw=raw,blocks=[dict(id='b1',text='원문')],source_parents=[])
    y = dict(x,id='b',raw=changed)
    payload = json.loads(prompt(x,y).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
    assert payload['candidates']['X'] == raw and payload['candidates']['Y'] == changed
    assert payload['context']['blocks'] == x['blocks'] and payload['context']['source_parents'] == []
    print('Candidate-only modality transformation, exact context preservation and invalid construction checks passed')


def prepare():
    assert not (OUT/'prepared.json').exists()
    inputs, baselines = read(OUT/'inputs.json'), read(OUT/'baselines.json')
    rows = []
    for baseline in baselines:
        assert baseline['prompt'] == base.prompt(baseline['case'],'A',base.MAPPINGS['primary'])
        if baseline['reused']:
            assert sha(Path(baseline['response_path'])) == baseline['response_sha256']
        else:
            rows.append(dict(id=baseline['id'],arm='individual',prompt=baseline['prompt']))
    for pair in inputs:
        rows.append(dict(id=pair['id'],arm='joint',prompt=prompt(pair['X'],pair['Y'])))
    assert len(rows)==9
    write(OUT/'prompts.json',rows)
    files=[OUT/n for n in ['inputs.json','baselines.json','criteria.json','construction.json','exposure_inventory.json','prompts.json']]
    code=[Path(__file__),Path(base.__file__),Path(refs.__file__),ROOT/'scripts/compare_business_modality_spans.py',ROOT/'scripts/business_dependency_parser.py']
    write(OUT/'prepared.json',dict(at=time.time(),base_commit='c79d1e05e6bcd8456a06b22f8e527dce90317251',
        max_calls=9,reused_individual=6,new_individual=4,new_joint=5,
        files={str(p):sha(p) for p in files},code={str(p):sha(p) for p in code}))


def check():
    d=read(OUT/'prepared.json')
    assert all(sha(Path(p))==h for p,h in {**d['files'],**d['code']}.items())
    assert all(sha(Path(r['response_path']))==r['response_sha256'] for r in read(OUT/'baselines.json') if r['reused'])


def preflight():
    assert not (OUT/'freeze.json').exists()
    check()
    props,old=base.api('/props'),read(prior.OUT/'baseline_props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old.items() if k!='media_marker'}
    for baseline in read(OUT/'baselines.json'):
        if baseline['reused']:
            ids=base.api('/tokenize',dict(content=baseline['prompt'],add_special=False,parse_special=True))['tokens']
            assert baseline['request']==dict(read(prior.OUT/'settings.json'),prompt=ids)
    requests=[]
    for row in read(OUT/'prompts.json'):
        assert all(marker not in row['prompt'] for marker in [props['media_marker'],old['media_marker']])
        ids=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
        assert len(ids)+2048<8192
        requests.append(dict(row,input_tokens=len(ids),request=dict(read(prior.OUT/'settings.json'),prompt=ids)))
    write(OUT/'requests.json',requests);write(OUT/'props.json',props)
    write(OUT/'freeze.json',dict(at=time.time(),max_calls=9,files={n:sha(OUT/n) for n in ['prepared.json','requests.json','props.json']}))
    print('Frozen candidate contrast:',len(requests),'calls; input tokens',sum(r['input_tokens'] for r in requests))


def run():
    check()
    assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props')==read(OUT/'props.json')
    pairs={r['id']:r for r in read(OUT/'inputs.json')}
    individuals={r['id']:r['case'] for r in read(OUT/'baselines.json')}
    dest=OUT/'run';dest.mkdir()
    result=dict(calls=0,records=[],semantic_review='pending');start=time.monotonic()
    for row in read(OUT/'requests.json'):
        record=dict(id=row['id'],arm=row['arm'],input_tokens=row['input_tokens'],contract_pass=False)
        result['records'].append(record);result['calls']+=1;write(dest/'result.json',result)
        before=time.monotonic()
        try:
            raw=base.call('/completion',row['request']);path=dest/f"{row['id']}_{row['arm']}_response.json";path.write_bytes(raw)
            response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('truncated') or response.get('stop_type')!='eos':raise ValueError('incomplete_generation')
            prefix=base.PREFIX if row['arm']=='individual' else '{'
            answer=json.loads(prefix+response['content'],object_pairs_hook=strict_object)
            record['answer']=answer
            judgments={'single':answer} if row['arm']=='individual' else answer.get('judgments',{})
            mapping=base.MAPPINGS['primary']
            record['semantic_labels']={k:mapping.get(v.get('label'),v.get('label') if v.get('label') in mapping.values() else None) for k,v in judgments.items()}
            try:
                if row['arm']=='individual':base.parse_a(response['content'],individuals[row['id']],mapping)
                else:parse(response['content'],pairs[row['id']]['X'],pairs[row['id']]['Y'])
                record['contract_pass']=True
            except (ValueError,KeyError,TypeError,AssertionError) as error:record['contract_error']=repr(error)
        except (OSError,ValueError,KeyError,TypeError) as error:record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;result['wall_s']=time.monotonic()-start
        write(dest/'result.json',result)
        print(row['id'],row['arm'],record.get('semantic_labels'),record['contract_pass'],flush=True)


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode',choices=['selfcheck','prepare','preflight','run'])
    globals()[cli.parse_args().mode]()

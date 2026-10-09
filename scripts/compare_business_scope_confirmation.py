"""Three separate-source cases: original judge, frozen link selector, linked judge."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_independent_scope as research

ROOT, read, write, sha = research.ROOT, research.read, research.write, research.sha
OUT = research.OUT / 'confirmation'


def fixed_prompts(cases):
    return [dict(id=case['id'], task=task, prompt=builder(case))
            for task, builder in [('baseline', research.previous.prompt), ('links', research.link_prompt)]
            for case in cases]


def prepare():
    assert not (OUT / 'prepared.json').exists()
    research.check_prepared()
    cases = read(OUT / 'inputs.json')
    assert len(cases) == len({c['id'] for c in cases}) == 3
    assert set(read(OUT / 'criteria.json')['expected']) == {c['id'] for c in cases}
    assert all(c['blocks'] == cases[0]['blocks'] for c in cases)
    write(OUT / 'prompts.json', fixed_prompts(cases))
    (OUT / 'settings.json').write_bytes((research.OUT / 'settings.json').read_bytes())
    files = [p for p in OUT.rglob('*') if p.is_file() and p.suffix in {'.json','.txt','.html','.md'}]
    code = [Path(__file__), *[ROOT / n for n in read(research.OUT / 'prepared.json')['code']]]
    write(OUT / 'prepared.json', dict(at=time.time(), files={str(p.relative_to(OUT)):sha(p) for p in files},
          code={str(p.relative_to(ROOT)):sha(p) for p in code}, max_calls=9,
          development_freeze_sha256=sha(research.OUT / 'freeze.json'),
          order='baseline3, links3, linked-judgment3; sequential; no tuning or A findings'))


def check_prepared():
    research.check_prepared()
    p = read(OUT / 'prepared.json')
    assert all(sha(OUT / n) == h for n,h in p['files'].items())
    assert all(sha(ROOT / n) == h for n,h in p['code'].items())
    assert p['development_freeze_sha256'] == sha(research.OUT / 'freeze.json')
    assert (OUT / 'settings.json').read_bytes() == (research.OUT / 'settings.json').read_bytes()


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check_prepared()
    assert read(OUT / 'execution_authorization.json')['compute_allocated']
    identity = read(research.previous.OUT / 'runtime_identity.json')
    for key in ['engine','gguf']:
        assert sha(Path(identity[key + '_path'])) == identity[key + '_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=10) as f:
        assert not json.load(f)['models']
    props = research.previous.prior.base.api('/props')
    old = read(research.OUT / 'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'} == {k:v for k,v in old.items() if k!='media_marker'}
    rows = [research.request_row(row) for row in read(OUT / 'prompts.json')]
    assert all(props['media_marker'] not in r['prompt'] and old['media_marker'] not in r['prompt'] for r in rows)
    write(OUT / 'requests.json',rows)
    write(OUT / 'props.json',props)
    write(OUT / 'freeze.json',dict(at=time.time(),max_calls=9,
          files={n:sha(OUT/n) for n in ['prepared.json','requests.json','props.json','execution_authorization.json']}))


def run():
    check_prepared()
    assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert research.previous.prior.base.api('/props') == read(OUT/'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    cases = {c['id']:c for c in read(OUT/'inputs.json')}
    result = dict(calls=0,records=[],cases=[],semantic_review='pending')
    start = time.monotonic()
    def save():
        result['wall_s'] = time.monotonic()-start
        write(dest/'result.json',result)
    def call(row):
        record = dict(id=row['id'],task=row['task'],input_tokens=row['input_tokens'],contract_pass=False,
                      request_sha256=research.text_hash(json.dumps(row['request'],ensure_ascii=False)))
        result['records'].append(record)
        result['calls'] += 1
        assert result['calls']<=9
        save()
        before = time.monotonic()
        try:
            raw = research.previous.prior.base.call('/completion',row['request'])
            path = dest/(row['id']+'_'+row['task']+'_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),
                          stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('stop_type')!='eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{'+response['content'],object_pairs_hook=research.previous.strict_object)
            record['answer'] = answer
            if row['task']=='links':
                record['parsed'] = research.resolve_links(answer,cases[row['id']])
            else:
                record['parsed'] = research.previous.parse_final(answer,cases[row['id']])
                record['label'] = research.previous.prior.MAPPING[answer['label']]
            record['contract_pass'] = True
        except (OSError,ValueError,KeyError,TypeError) as e:
            record['error'] = repr(e)
        record['elapsed_s'] = time.monotonic()-before
        save()
        print(row['id'],row['task'],record['contract_pass'],record.get('label'),record.get('error'),flush=True)
        return record
    for row in read(OUT/'requests.json'):
        call(row)
    dynamic = []
    for record in [r for r in result['records'] if r['task']=='links']:
        if not record['contract_pass']:
            result['cases'].append(dict(id=record['id'],label=None,status='B1_contract_failure'))
            continue
        try:
            row = research.request_row(dict(id=record['id'],task='judgment',
                  prompt=research.linked_judgment_prompt(cases[record['id']],record['parsed'])))
        except ValueError as e:
            result['cases'].append(dict(id=record['id'],label=None,status='B2_not_called',error=repr(e)))
            continue
        dynamic.append(dict(row,b1_raw_sha256=record['raw_sha256']))
        write(dest/'b2_requests.json',dynamic)
        judged = call(row)
        result['cases'].append(dict(id=record['id'],label=judged.get('label'),
                                   status='completed' if judged['contract_pass'] else 'B2_contract_failure'))
    save()


def selfcheck():
    cases = [dict(id=str(n),raw={'Event':'문장'},blocks=[dict(id='b',text='원문\n')]) for n in range(3)]
    rows = fixed_prompts(cases)
    assert [(r['task'],r['id']) for r in rows] == [(task,str(n)) for task in ['baseline','links'] for n in range(3)]
    for case,row in zip(cases,rows[:3]):
        assert row['prompt']==research.previous.prompt(case)
    links = dict(inspection_status='complete',examined_block_ids=['b'],links=[],unresolved=[],semantic_status='unverified')
    prompt = research.linked_judgment_prompt(cases[0],links)
    payload = json.loads(prompt.split('<|im_start|>user\n',1)[1].split('<|im_end|>',1)[0])
    assert payload.pop('automatic_scope_links')==links and payload==cases[0]
    print('Three fixed baseline/selector inputs and exact original case in linked judge checked.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','preflight','run','selfcheck'])
    globals()[parser.parse_args().mode]()

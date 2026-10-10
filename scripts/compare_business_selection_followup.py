"""Fresh frozen selector then literal-span judge on stored and separate-source cases."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_selected_source as selection

prior = selection.prior
ROOT, read, write, sha = selection.ROOT, selection.read, selection.write, selection.sha
BASE = selection.OUT.parent
PANELS = {'a_stored': (['c47', 'c46'], 4), 'confirmation_korail': (['KR01', 'KR02', 'KR03', 'KR04'], 12)}


def prepare(out):
    assert not (out/'prepared.json').exists()
    selection.check_prepared()
    ids, budget = PANELS[out.name]
    cases = read(out/'inputs.json')
    assert [c['id'] for c in cases] == ids
    assert set(read(out/'criteria.json')['expected']) == set(ids)
    tasks = ['links'] if out.name == 'a_stored' else ['baseline', 'links']
    rows = [dict(id=c['id'], task=t, prompt=(prior.link_prompt if t=='links' else prior.previous.prompt)(c))
            for t in tasks for c in cases]
    if out.name == 'a_stored':
        old = {c['id']: c for c in read(prior.OUT/'inputs.json')}
        baselines = {r['id']: r for r in read(prior.OUT/'baselines.json')}
        for c in cases:
            assert c == old[c['id']]
            b = baselines[c['id']]
            assert b['prompt'] == prior.previous.prompt(c) and sha(ROOT/b['raw_path']) == b['raw_sha256']
        write(out/'saved_baselines.json', [baselines[i] for i in ids])
    else:
        blind = read(out/'author_cases_blind.json')['cases']
        source = (out/'source.txt').read_text()
        assert all(c['raw'] == b['raw'] and c['blocks'] == [dict(id='korail-18336',text=source)]
                   for c,b in zip(cases,blind))
        assert sha(out/'source.txt') == read(out/'source_receipt.json')['source_text']['sha256']
        assert read(out/'agreement_review.json')['summary']['included'] == 4
    write(out/'prompts.json', rows)
    (out/'settings.json').write_bytes((prior.OUT/'settings.json').read_bytes())
    code = {**read(selection.OUT/'prepared.json')['code'], str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))}
    write(out/'prepared.json', dict(at=time.time(), max_calls=budget, code=code,
          files={p.name:sha(p) for p in out.iterdir() if p.is_file()},
          order='Fixed baseline if new source, fresh selector, exact frozen projection and A2. No retries or human repair.'))


def check(out):
    selection.check_prepared()
    p = read(out/'prepared.json')
    assert all(sha(out/n)==h for n,h in p['files'].items())
    assert all(sha(ROOT/n)==h for n,h in p['code'].items())
    if out.name == 'a_stored':
        assert all(sha(ROOT/r['raw_path'])==r['raw_sha256'] for r in read(out/'saved_baselines.json'))


def preflight(out):
    assert not (out/'freeze.json').exists()
    check(out)
    assert read(out/'execution_authorization.json')['compute_allocated']
    identity = read(prior.previous.OUT/'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key+'_path'])) == identity[key+'_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=10) as stream:
        assert not json.load(stream)['models']
    props = prior.previous.prior.base.api('/props')
    old = read(prior.OUT/'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'} == {k:v for k,v in old.items() if k!='media_marker'}
    write(out/'requests.json', [prior.request_row(r) for r in read(out/'prompts.json')])
    write(out/'props.json',props)
    write(out/'freeze.json',dict(at=time.time(), max_calls=PANELS[out.name][1],
          files={n:sha(out/n) for n in ['prepared.json','requests.json','props.json','execution_authorization.json']}))


def run(out):
    check(out)
    assert all(sha(out/n)==h for n,h in read(out/'freeze.json')['files'].items())
    assert prior.previous.prior.base.api('/props') == read(out/'props.json')
    dest = out/'run'
    dest.mkdir()
    cases = {c['id']:c for c in read(out/'inputs.json')}
    result = dict(calls=0,records=[],cases=[],semantic_review='pending')
    start = time.monotonic()
    def save():
        result['wall_s'] = time.monotonic()-start
        write(dest/'result.json',result)
    def call(row):
        record = dict(id=row['id'],task=row['task'],input_tokens=row['input_tokens'],contract_pass=False,
                      request_sha256=prior.text_hash(json.dumps(row['request'],ensure_ascii=False)))
        result['records'].append(record)
        result['calls'] += 1
        assert result['calls'] <= PANELS[out.name][1]
        save()
        before = time.monotonic()
        try:
            raw = prior.previous.prior.base.call('/completion',row['request'])
            path = dest/(row['id']+'_'+row['task']+'_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),
                          stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('stop_type')!='eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{'+response['content'],object_pairs_hook=prior.previous.strict_object)
            record['answer'] = answer
            if row['task']=='links':
                record['parsed'] = prior.resolve_links(answer,cases[row['id']])
            else:
                record['parsed'] = prior.previous.parse_final(answer,cases[row['id']])
                record['label'] = prior.previous.prior.MAPPING[answer['label']]
            record['contract_pass'] = True
        except (OSError,ValueError,KeyError,TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic()-before
        save()
        print(row['id'],row['task'],record['contract_pass'],record.get('label'),record.get('error'),flush=True)
        return record
    for row in read(out/'requests.json'):
        call(row)
    dynamic = []
    for record in [r for r in result['records'] if r['task']=='links']:
        ident = record['id']
        if not record['contract_pass']:
            result['cases'].append(dict(id=ident,label=None,status='B1_contract_failure',A2_called=False))
            continue
        spans = selection.project(cases[ident],record['parsed'])
        try:
            row = prior.request_row(dict(id=ident,task='selection_only',prompt=selection.prompt(cases[ident],spans)))
        except ValueError as error:
            result['cases'].append(dict(id=ident,label=None,status='A2_not_called',error=repr(error)))
            continue
        dynamic.append(dict(row,b1_raw_sha256=record['raw_sha256'],selected_source_spans=spans))
        write(dest/'a2_requests.json',dynamic)
        judged = call(row)
        result['cases'].append(dict(id=ident,label=judged.get('label'),A2_called=True,
                                   status='completed' if judged['contract_pass'] else 'A2_contract_failure'))
    save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('panel',choices=PANELS)
    parser.add_argument('mode',choices=['prepare','preflight','run','check'])
    args=parser.parse_args()
    globals()[args.mode](BASE/args.panel)

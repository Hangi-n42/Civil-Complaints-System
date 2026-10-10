"""First A-04 stage only: at most three source-limited constructions, no judgments."""
import argparse
import json
from pathlib import Path
import time

import compare_business_source_limit_contrast as trial
import run_business_condition_contrast as prior

ROOT, read, write, sha, base = prior.ROOT, prior.read, prior.write, prior.sha, prior.base
OUT = ROOT / 'data/knowledge/evaluations/business_source_limit_contrast_20261011'


def prepare():
    assert not (OUT / 'prepared.json').exists()
    rows = read(prior.OUT / 'stored_inputs.json')
    write(OUT / 'inputs.json', [dict(r, prompt=trial.prompt(r['case'])) for r in rows])
    (OUT / 'settings.json').write_bytes((prior.OUT / 'settings.json').read_bytes())
    original = next(r for r in rows if r['id'] == 'c46')['case']
    baseline = next(r for r in read(prior.OUT / 'followup/requests.json') if r['id'] == 'c46_single')
    assert prior.trial.prompt(dict(X=original)) == baseline['prompt']
    write(OUT / 'baseline_reuse.json', dict(c46_original_single=True, prompt_equal=True, judgment_instruction_sha256=sha(Path(prior.trial.__file__)),
        settings_sha256=sha(OUT / 'settings.json'), old_request_sha256=sha(prior.OUT / 'followup/requests.json'),
        old_response_sha256=sha(prior.OUT / 'followup/run/c46_single_response.json'),
        condition='Reuse only if judge/source/raw/props/settings/token request remain equal; no three-singleton quota. c13/c47 not yet run under this judge contract.'))
    files = [OUT / n for n in ['inputs.json','settings.json','criteria.json','baseline_reuse.json']]
    code = [Path(__file__),Path(trial.__file__),Path(prior.trial.__file__),ROOT / 'app/knowledge/business_run.py']
    write(OUT / 'prepared.json', dict(at=time.time(),calls=0,maximum_construction_calls=3,
        files={str(p):sha(p) for p in files},code={str(p):sha(p) for p in code}))


def check():
    prepared=read(OUT / 'prepared.json')
    assert all(sha(Path(p))==h for p,h in {**prepared['files'],**prepared['code']}.items())
    auth=read(OUT / 'authorization.json')
    assert auth['compute_allocated'] is True and auth['allowed_phases']==['generate'] and auth['maximum_calls']==3


def preflight():
    check()
    assert not (OUT / 'freeze.json').exists()
    props, old = base.api('/props'), read(prior.OUT / 'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old.items() if k!='media_marker'}
    rows=[]
    for row in read(OUT / 'inputs.json'):
        assert props['media_marker'] not in row['prompt']
        tokens=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
        assert len(tokens)+read(OUT / 'settings.json')['n_predict']<8192
        rows.append(dict(row,input_tokens=len(tokens),request=dict(read(OUT / 'settings.json'),prompt=tokens)))
    write(OUT / 'requests.json',rows)
    write(OUT / 'props.json',props)
    write(OUT / 'freeze.json',dict(at=time.time(),files={n:sha(OUT/n) for n in ['prepared.json','requests.json','props.json','authorization.json','runtime_identity.json']}))


def run():
    check()
    assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props')==read(OUT/'props.json')
    dest=OUT/'generate'
    dest.mkdir()
    result=dict(calls=0,records=[],semantic_review='pending',judgment_calls=0)
    start=time.monotonic()
    for row in read(OUT/'requests.json'):
        record=dict(id=row['id'],input_tokens=row['input_tokens'],contract_pass=False)
        result['records'].append(record)
        result['calls']+=1
        assert result['calls']<=3
        write(dest/'result.json',result)
        before=time.monotonic()
        try:
            raw=base.call('/completion',row['request'])
            path=dest/(row['id']+'_response.json')
            path.write_bytes(raw)
            response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('stop_type')!='eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer=json.loads('{'+response['content'],object_pairs_hook=prior.old.previous.strict_object)
            record['answer']=answer
            record['construction']=trial.construct(row['case'],answer,row['canonical_views'])
            record['contract_pass']=True
        except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:
            record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before
        result['wall_s']=time.monotonic()-start
        write(dest/'result.json',result)
        print(row['id'],record.get('construction',{}).get('status'),record['contract_pass'],record.get('error'),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode',choices=['prepare','preflight','run'])
    globals()[cli.parse_args().mode]()

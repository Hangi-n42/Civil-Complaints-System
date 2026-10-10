"""Separately approved c46 single/joint diagnostic after pre-judgment scope review."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import run_business_condition_contrast as initial

trial, read, write, sha, base = initial.trial, initial.read, initial.write, initial.sha, initial.base
OUT = initial.OUT / 'followup'


def prepare():
    initial.check()
    assert not (OUT / 'prepared.json').exists()
    auth = read(OUT / 'authorization.json')
    assert auth['maximum_calls'] == 2 and auth['candidate_ids'] == ['c46']
    assert auth['initial_regression_gate_remains_failed'] is True
    case = next(r for r in read(initial.OUT / 'stored_inputs.json') if r['id'] == 'c46')
    generated = next(r for r in read(initial.OUT / 'generate/result.json')['records'] if r['id'] == 'c46')
    construction = trial.construct(case['case']['raw'], generated['answer'])
    assert construction == generated['construction'] and construction['status'] == 'constructed_unverified'
    single = next(r for r in read(initial.OUT / 'requests.json') if r['phase'] == 'single' and r['id'] == 'c46')
    assert single['prompt'] == trial.prompt(dict(X=case['case']))
    cases = dict(X=case['case'], Y=dict(deepcopy(case['case']), raw=construction['raw']))
    rows = [dict(single, id='c46_single'), dict(id='c46_joint', phase='joint', cases=cases,
        canonical_views=case['canonical_views'], prompt=trial.prompt(cases))]
    write(OUT / 'inputs.json', rows)
    write(OUT / 'prepared.json', dict(at=time.time(), files={str(p): sha(p) for p in
        [OUT / 'inputs.json', OUT / 'authorization.json', OUT / 'criteria.json',
         initial.OUT / 'prepared.json', initial.OUT / 'freeze.json', initial.OUT / 'generate/result.json',
         initial.OUT / 'contracts/result.json', initial.OUT / 'settings.json']},
        runner_sha256=sha(Path(__file__)),calls=2))


def check():
    initial.check()
    assert read(initial.OUT / 'contract_review.json')['semantic_pass'] is False
    p = read(OUT / 'prepared.json')
    assert sha(Path(__file__)) == p['runner_sha256']
    assert all(sha(Path(n)) == h for n, h in p['files'].items())


def preflight():
    check()
    assert not (OUT / 'freeze.json').exists()
    props = base.api('/props')
    old = read(initial.OUT / 'props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in old.items() if k != 'media_marker'}
    rows = []
    for row in read(OUT / 'inputs.json'):
        assert all(m not in row['prompt'] for m in [props['media_marker'], old['media_marker']])
        tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(tokens) + read(initial.OUT / 'settings.json')['n_predict'] < 8192
        request = dict(read(initial.OUT / 'settings.json'), prompt=tokens)
        if row['id'] == 'c46_single':
            assert row['request'] == request and row['input_tokens'] == len(tokens)
        rows.append(dict(row, input_tokens=len(tokens), request=request))
    write(OUT / 'requests.json', rows)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), files={n: sha(OUT / n) for n in
        ['prepared.json', 'requests.json', 'props.json', 'runtime_identity.json']}))
    print([(r['id'], r['input_tokens']) for r in rows])


def run():
    check()
    assert all(sha(OUT / n) == h for n, h in read(OUT / 'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    result = dict(calls=0, records=[], initial_gate_passed=False, semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record)
        result['calls'] += 1
        assert result['calls'] <= 2
        write(dest / 'result.json', result)
        before = time.monotonic()
        try:
            raw = base.call('/completion', row['request'])
            path = dest / (row['id'] + '_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'), stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('stop_type') != 'eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'], object_pairs_hook=trial.previous.previous.strict_object)
            record['answer'] = answer
            record['semantic_labels'] = {k: base.MAPPINGS['primary'].get(v.get('label'), v.get('label') if v.get('label') in base.MAPPINGS['primary'].values() else None)
                for k, v in answer.get('judgments', {}).items() if isinstance(v, dict)}
            record['parsed'] = trial.parse(response['content'], row['cases'], row['canonical_views'])
            record['contract_pass'] = True
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], record.get('semantic_labels'), record['contract_pass'], record.get('error'), flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare', 'preflight', 'run'])
    globals()[cli.parse_args().mode]()

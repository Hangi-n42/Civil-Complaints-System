"""One-pass staged runner; model resources must be allocated before preflight."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import compare_business_condition_contrast as trial

old = trial.previous
read, write, sha, base = old.read, old.write, old.sha, old.base
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/knowledge/evaluations/business_condition_contrast_20261010'


def prepare():
    assert not (OUT / 'prepared.json').exists()
    old_rows = {r['id']: r for r in read(old.OUT / 'inputs.json') if r['phase'] == 'initial'}
    inputs = [dict(id=r['id'], phase='contracts', cases=r['cases'], canonical_views=None,
                   prompt=trial.prompt(r['cases'])) for r in [old_rows[k] for k in ['na', 'p2', 'p3', 'p5']]]
    for row in read(OUT / 'stored_inputs.json'):
        inputs.append(dict(id=row['id'], phase='generate', raw=row['case']['raw'],
                           prompt=trial.construction_prompt(row['case']['raw'])))
        cases = dict(X=row['case'])
        inputs.append(dict(id=row['id'], phase='single', cases=cases, canonical_views=row['canonical_views'],
                           prompt=trial.prompt(cases)))
    write(OUT / 'inputs.json', inputs)
    settings_path = old.previous.prior.OUT / 'settings.json'
    (OUT / 'settings.json').write_bytes(settings_path.read_bytes())
    code = [Path(__file__), Path(trial.__file__), Path(old.__file__), Path(old.previous.__file__),
            Path(base.__file__), Path(old.previous.refs.__file__), ROOT / 'app/knowledge/business_run.py',
            ROOT / 'scripts/compare_business_modality_spans.py']
    files = [OUT / n for n in ['inputs.json', 'stored_inputs.json', 'stored_input_receipt.json', 'criteria.json', 'settings.json']]
    write(OUT / 'prepared.json', dict(at=time.time(), initial_calls=10, conditional_joint_calls=3,
        files={str(p): sha(p) for p in files}, code={str(p): sha(p) for p in code},
        old_inputs_sha256=sha(old.OUT / 'inputs.json'), original_gate_preserved=False if read(old.OUT / 'initial_review.json')['passed'] else True))
    print('Prepared contracts4 + generate3 + single3; conditional joint<=3; no model calls')


def check():
    prepared = read(OUT / 'prepared.json')
    assert all(sha(Path(p)) == h for p, h in {**prepared['files'], **prepared['code']}.items())
    assert sha(old.OUT / 'inputs.json') == prepared['old_inputs_sha256']
    assert read(old.OUT / 'initial_review.json')['passed'] is False


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check()
    authorization = read(OUT / 'execution_authorization.json')
    assert authorization['compute_allocated'] is True and authorization['maximum_calls'] == 13
    props, old_props = base.api('/props'), read(old.OUT / 'props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in old_props.items() if k != 'media_marker'}
    rows = []
    for row in read(OUT / 'inputs.json'):
        assert props['media_marker'] not in row['prompt']
        tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(tokens) + read(OUT / 'settings.json')['n_predict'] < 8192
        rows.append(dict(row, input_tokens=len(tokens), request=dict(read(OUT / 'settings.json'), prompt=tokens)))
    write(OUT / 'requests.json', rows)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), files={n: sha(OUT / n) for n in
        ['prepared.json', 'requests.json', 'props.json', 'execution_authorization.json', 'runtime_identity.json']}))
    print([(r['id'], r['phase'], r['input_tokens']) for r in rows])


def joint():
    check()
    assert not (OUT / 'joint_requests.json').exists()
    review = read(OUT / 'construction_review.json')
    assert review['reviewed_before_judgments'] is True
    generated = {r['id']: r for r in read(OUT / 'generate/result.json')['records']}
    rows, skipped = [], []
    for stored in read(OUT / 'stored_inputs.json'):
        ident = stored['id']
        decision = review['cases'][ident]
        made = generated[ident].get('construction') or {}
        if not decision['allow_joint'] or made.get('status') != 'constructed_unverified':
            skipped.append(dict(id=ident, reason=decision['reason'], construction=made))
            continue
        assert generated[ident]['contract_pass'] and trial.construct(stored['case']['raw'], made['proposal']) == made
        cases = dict(X=stored['case'], Y=dict(deepcopy(stored['case']), raw=made['raw']))
        text = trial.prompt(cases)
        tokens = base.api('/tokenize', dict(content=text, add_special=False, parse_special=True))['tokens']
        assert len(tokens) + read(OUT / 'settings.json')['n_predict'] < 8192
        rows.append(dict(id=ident, phase='joint', cases=cases, canonical_views=stored['canonical_views'], prompt=text,
                         input_tokens=len(tokens), request=dict(read(OUT / 'settings.json'), prompt=tokens)))
    write(OUT / 'joint_requests.json', rows)
    write(OUT / 'joint_freeze.json', dict(at=time.time(), denominator=3, skipped=skipped,
        files={n: sha(OUT / n) for n in ['joint_requests.json', 'construction_review.json', 'generate/result.json']}))
    print('Joint requests:', len(rows), '; skipped in denominator:', len(skipped))


def run(phase):
    check()
    assert all(sha(OUT / n) == h for n, h in read(OUT / 'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT / 'props.json')
    authorization = read(OUT / 'execution_authorization.json')
    if phase in {'single', 'joint'}:
        assert phase in read(OUT / 'judgment_authorization.json')['allowed_phases']
    else:
        assert phase in authorization['allowed_phases']
    if phase != 'contracts':
        assert read(OUT / 'contract_review.json')['proceed_generation'] is True
    if phase in {'single', 'joint'}:
        assert read(OUT / 'construction_review.json')['reviewed_before_judgments'] is True
    if phase == 'joint':
        assert all(sha(OUT / n) == h for n, h in read(OUT / 'joint_freeze.json')['files'].items())
    rows = read(OUT / ('joint_requests.json' if phase == 'joint' else 'requests.json'))
    rows = [r for r in rows if r['phase'] == phase]
    assert len(rows) <= (4 if phase == 'contracts' else 3)
    dest = OUT / phase
    dest.mkdir()
    result = dict(calls=0, records=[], semantic_review='pending')
    start = time.monotonic()
    for row in rows:
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record)
        result['calls'] += 1
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
            answer = json.loads('{' + response['content'], object_pairs_hook=old.previous.strict_object)
            record['answer'] = answer
            if phase == 'generate':
                record['construction'] = trial.construct(row['raw'], answer)
            else:
                record['semantic_labels'] = {k: base.MAPPINGS['primary'].get(v.get('label'), v.get('label') if v.get('label') in base.MAPPINGS['primary'].values() else None)
                    for k, v in answer.get('judgments', {}).items() if isinstance(v, dict)}
                record['parsed'] = trial.parse(response['content'], row['cases'], row['canonical_views'])
            record['contract_pass'] = True
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], phase, record['contract_pass'], record.get('semantic_labels'), record.get('error'), flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare', 'preflight', 'joint', 'contracts', 'generate', 'single', 'run_joint'])
    mode = cli.parse_args().mode
    run('joint' if mode == 'run_joint' else mode) if mode in {'contracts', 'generate', 'single', 'run_joint'} else globals()[mode]()

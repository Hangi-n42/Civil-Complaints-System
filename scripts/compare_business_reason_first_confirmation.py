"""Three frozen separate-source cases, one old/new-order call each; no tuning."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_reason_first as research

ROOT, read, write, sha = research.ROOT, research.read, research.write, research.sha
OUT = research.OUT / 'confirmation'
OLD_ORDER = ['analysis', 'label', 'error_fields', 'error_spans', 'evidence', 'reason']


def parse_answer(answer, case, arm):
    if arm == 'reason_first':
        return research.parse_final(answer, case)
    assert arm == 'baseline'
    research.prior.parse_b(answer, case)
    if list(answer) != OLD_ORDER or list(answer['analysis']) != research.ANALYSIS_ORDER:
        raise ValueError('actual_generation_order')
    return answer


def prepare():
    assert not (OUT / 'prepared.json').exists()
    research.check_prepared()
    cases = read(OUT / 'inputs.json')
    assert len(cases) == len({c['id'] for c in cases}) == 3
    text = (OUT / 'source.txt').read_text()
    assert all(c['blocks'] == [dict(id='b1', text=text)] for c in cases)
    rows = []
    for arm, builder in [('baseline', research.prior.prompt), ('reason_first', research.prompt)]:
        for case in cases:
            rows.append(dict(id=case['id'], arm=arm, prompt=builder(case)))
    for old, new in zip(rows[:3], rows[3:]):
        restored = new['prompt']
        for before, after in research.REPLACEMENTS:
            assert restored.count(after) == 1
            restored = restored.replace(after, before, 1)
        assert restored == old['prompt']
    write(OUT / 'prompts.json', rows)
    (OUT / 'settings.json').write_bytes((research.OUT / 'settings.json').read_bytes())
    files = ['inputs.json', 'source.txt', 'source.html', 'source_preparation.json', 'settings.json',
             'prompts.json', 'criteria.json', 'authorization.json', 'author/candidates.json',
             'author/draft_criteria.json', 'author/receipt.json', 'reviewer/independent_review.json',
             'reviewer/comparison.json', 'reviewer/receipt.json', 'reviewer/comparison_receipt.json',
             'reviewer_phase1_lock.json', 'author_dispatch.json', 'reviewer_dispatch.json', 'material_checks.json']
    code = [Path(__file__), Path(research.__file__), Path(research.prior.__file__),
            Path(research.prior.base.__file__), ROOT / 'scripts/compare_business_nli.py',
            ROOT / 'scripts/compare_business_modality_spans.py']
    write(OUT / 'prepared.json', dict(at=time.time(), files={n: sha(OUT / n) for n in files},
          code={str(p.relative_to(ROOT)): sha(p) for p in code},
          development_freeze_sha256=sha(research.OUT / 'freeze.json'), max_calls=6,
          method_changed=False, call_order='baseline3 then reason_first3, sequential'))


def check_prepared():
    prepared = read(OUT / 'prepared.json')
    research.check_prepared()
    assert prepared['development_freeze_sha256'] == sha(research.OUT / 'freeze.json')
    assert all(sha(OUT / n) == h for n, h in prepared['files'].items())
    assert all(sha(ROOT / n) == h for n, h in prepared['code'].items())


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check_prepared()
    assert read(OUT / 'authorization.json')['compute_allocated']
    identity = read(research.OUT / 'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key + '_path'])) == identity[key + '_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models']
    props, previous = research.prior.base.api('/props'), read(research.OUT / 'props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in previous.items() if k != 'media_marker'}
    requests = []
    for row in read(OUT / 'prompts.json'):
        assert all(m not in row['prompt'] for m in [props['media_marker'], previous['media_marker']])
        ids = research.prior.base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        settings = read(OUT / 'settings.json')
        assert len(ids) + settings['n_predict'] < 8192
        requests.append(dict(id=row['id'], arm=row['arm'], input_tokens=len(ids), request=dict(settings, prompt=ids)))
    write(OUT / 'requests.json', requests)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), max_calls=6, new_calls=0,
          files={n: sha(OUT / n) for n in ['prepared.json', 'requests.json', 'props.json']}))


def run():
    check_prepared()
    assert all(sha(OUT / n) == h for n, h in read(OUT / 'freeze.json')['files'].items())
    assert research.prior.base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    cases = {c['id']: c for c in read(OUT / 'inputs.json')}
    result = dict(calls=0, cases=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], arm=row['arm'], input_tokens=row['input_tokens'], contract_pass=False)
        result['cases'].append(record)
        before = time.monotonic()
        result['calls'] += 1
        write(dest / 'result.json', result)
        try:
            raw = research.prior.base.call('/completion', row['request'])
            path = dest / (row['id'] + '_' + row['arm'] + '_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(timings=response.get('timings'), stop_type=response.get('stop_type'),
                          truncated=response.get('truncated'), response_sha256=sha(path))
            if response.get('truncated') or response.get('stop_type') != 'eos':
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'], object_pairs_hook=research.strict_object)
            if not isinstance(answer, dict):
                raise ValueError('output_schema')
            label = answer.get('label')
            record.update(answer=answer, actual_key_order=list(answer),
                          actual_analysis_order=list(answer['analysis']) if isinstance(answer.get('analysis'), dict) else None,
                          semantic_label=research.prior.MAPPING.get(label, label if label in research.prior.MAPPING.values() else None), status='completed')
            try:
                parse_answer(answer, cases[row['id']], row['arm'])
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError) as error:
                record['contract_error'] = str(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(status='failed', error=repr(error))
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['arm'], row['id'], record['status'], record.get('semantic_label'), record.get('contract_error'), flush=True)


def selfcheck():
    case = dict(raw={'Event': 'clause'}, blocks=[dict(id='b1', text='source')])
    answer = dict(analysis=dict(missing_premise=None, compatible_interpretation=None, source_state='present'),
                  label='1', error_fields=[], error_spans=[], evidence=[dict(block_id='b1', quote='source')], reason='contract only')
    parse_answer(answer, case, 'baseline')
    changed = {k: answer[k] for k in research.ORDER}
    parse_answer(changed, case, 'reason_first')
    for obj, arm in [(changed, 'baseline'), (answer, 'reason_first')]:
        try:
            parse_answer(obj, case, arm)
        except ValueError:
            continue
        raise AssertionError('other arm order accepted')
    assert answer == changed
    print('Same semantic fields retained; actual order checked separately for each arm.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'preflight', 'run', 'selfcheck'])
    globals()[parser.parse_args().mode]()

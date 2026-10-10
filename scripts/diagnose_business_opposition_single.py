"""Separately authorized two-call diagnosis; never changes the failed initial gate."""
import json
from pathlib import Path
import time

import compare_business_explicit_opposition as trial


def run():
    trial.check()
    auth = trial.read(trial.OUT / 'single_diagnostic_authorization.json')
    assert auth['maximum_calls'] == 2 and auth['initial_gate_remains_failed'] is True
    assert trial.sha(Path(__file__)) == auth['runner_sha256']
    assert all(trial.sha(trial.OUT / n) == h for n, h in auth['files'].items())
    assert all(trial.sha(trial.OUT / n) == h for n, h in trial.read(trial.OUT / 'freeze.json')['files'].items())
    assert trial.read(trial.OUT / 'initial_review.json')['passed'] is False
    assert trial.base.api('/props') == trial.read(trial.OUT / 'props.json')
    rows = [r for r in trial.read(trial.OUT / 'requests.json') if r['phase'] == 'single']
    assert [r['id'] for r in rows] == ['NA02', 'p1X']
    assert all(list(r['cases']) == ['X'] and r['prompt'] == trial.prompt(r['cases']) for r in rows)
    dest = trial.OUT / 'single_diagnostic'
    dest.mkdir()
    result = dict(calls=0, records=[], initial_gate_passed=False, semantic_review='pending')
    start = time.monotonic()
    for row in rows:
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record)
        result['calls'] += 1
        trial.write(dest / 'result.json', result)
        before = time.monotonic()
        try:
            raw = trial.base.call('/completion', row['request'])
            path = dest / f"{row['id']}_response.json"
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=trial.sha(path), timings=response.get('timings'),
                          stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('truncated') or response.get('stop_type') != 'eos':
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'], object_pairs_hook=trial.previous.strict_object)
            record['answer'] = answer
            mapping = trial.base.MAPPINGS['primary']
            record['semantic_labels'] = {k: mapping.get(v.get('label'), v.get('label') if v.get('label') in mapping.values() else None)
                                         for k, v in answer.get('judgments', {}).items()}
            try:
                trial.parse(response['content'], row['cases'])
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError, AssertionError) as error:
                record['contract_error'] = repr(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        trial.write(dest / 'result.json', result)
        print(row['id'], record.get('semantic_labels'), record['contract_pass'], flush=True)


if __name__ == '__main__':
    run()

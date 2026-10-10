"""Issue 649: only the predeclared partner/order and confirmation follow-ups."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import compare_business_candidate_contrast as trial

base, read, write, sha = trial.base, trial.read, trial.write, trial.sha


def prepare(phase):
    trial.check()
    dest = trial.OUT / phase
    dest.mkdir(exist_ok=True)
    assert not (dest / 'prepared.json').exists()
    rows = []
    if phase == 'stability':
        pairs = {r['id']: r for r in read(trial.OUT / 'inputs.json')}
        p1, p4 = pairs['p1'], pairs['p4']
        synonym = deepcopy(p1['X'])
        synonym['id'] = 'p1_permission_synonym'
        synonym['raw'] = trial.derive(synonym['raw'], 'permission_synonym')
        rows.append(dict(id='permission_synonym', arm='individual', X=synonym,
                         prompt=base.prompt(synonym, 'A', base.MAPPINGS['primary'])))
        for ident, x, y in [('duty_synonym_partner', p1['X'], synonym),
                            ('permission_synonyms', p1['Y'], synonym),
                            ('p4_reversed', p4['Y'], p4['X'])]:
            rows.append(dict(id=ident, arm='joint', X=x, Y=y, prompt=trial.prompt(x, y)))
        dependencies = [trial.OUT / 'criteria.json', trial.OUT / 'inputs.json']
    else:
        frozen = trial.OUT / 'confirmation'
        assert all(sha(frozen / p) == h for p, h in read(frozen / 'freeze.json')['files'].items())
        cases = read(frozen / 'inputs.json')
        prompts = read(frozen / 'prompts.json')
        for case in cases:
            prompt = base.prompt(case, 'A', base.MAPPINGS['primary'])
            assert prompt == prompts['A_individual'][case['id']]
            rows.append(dict(id=case['id'], arm='individual', X=case, prompt=prompt))
        for index, (x, y) in enumerate([(cases[0], cases[1]), (cases[2], cases[3])]):
            prompt = trial.prompt(x, y)
            assert prompt == prompts['A_joint'][index]
            rows.append(dict(id=f'NA_pair{index+1}', arm='joint', X=x, Y=y, prompt=prompt))
        dependencies = [frozen / 'freeze.json', frozen / 'criteria.json', frozen / 'prompts.json']
    props = base.api('/props')
    assert props == read(trial.OUT / 'props.json')
    for row in rows:
        tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(tokens) + 2048 < 8192
        row.update(input_tokens=len(tokens), request=dict(read(trial.prior.OUT / 'settings.json'), prompt=tokens))
    write(dest / 'requests.json', rows)
    files = dependencies + [dest / 'requests.json', Path(__file__), Path(trial.__file__)]
    write(dest / 'prepared.json', dict(at=time.time(), phase=phase, max_calls=len(rows),
        decision_owner='01a11fd9-f71b-7261-832b-0681548a03c4',
        files={str(p): sha(p) for p in files}))
    print(phase, len(rows), 'frozen calls;', sum(r['input_tokens'] for r in rows), 'input tokens')


def run(phase):
    trial.check()
    dest = trial.OUT / phase
    assert all(sha(Path(p)) == h for p, h in read(dest / 'prepared.json')['files'].items())
    assert base.api('/props') == read(trial.OUT / 'props.json')
    output = dest / 'run'
    output.mkdir()
    result = dict(calls=0, records=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(dest / 'requests.json'):
        record = dict(id=row['id'], arm=row['arm'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record)
        result['calls'] += 1
        write(output / 'result.json', result)
        before = time.monotonic()
        try:
            raw = base.call('/completion', row['request'])
            path = output / f"{row['id']}_{row['arm']}_response.json"
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'),
                          stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('truncated') or response.get('stop_type') != 'eos':
                raise ValueError('incomplete_generation')
            prefix = base.PREFIX if row['arm'] == 'individual' else '{'
            answer = json.loads(prefix + response['content'], object_pairs_hook=trial.strict_object)
            record['answer'] = answer
            judgments = {'single': answer} if row['arm'] == 'individual' else answer.get('judgments', {})
            mapping = base.MAPPINGS['primary']
            record['semantic_labels'] = {k: mapping.get(v.get('label'), v.get('label') if v.get('label') in mapping.values() else None)
                                         for k, v in judgments.items()}
            try:
                if row['arm'] == 'individual':
                    base.parse_a(response['content'], row['X'], mapping)
                else:
                    trial.parse(response['content'], row['X'], row['Y'])
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError, AssertionError) as error:
                record['contract_error'] = repr(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(output / 'result.json', result)
        print(row['id'], row['arm'], record.get('semantic_labels'), record['contract_pass'], flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=['stability', 'confirmation'])
    cli.add_argument('mode', choices=['prepare', 'run'])
    args = cli.parse_args()
    globals()[args.mode](args.phase)

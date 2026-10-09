"""Issue 637: three source-only diagnostic changes; no product writes or retries."""
import argparse
from copy import deepcopy
import difflib
import json
from pathlib import Path
import time
import urllib.request

import compare_business_label_selection as base
from compare_business_nli import read, write, sha

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/knowledge/evaluations/business_entailment_boundary_20261009'
OLD = Path('/Users/hyeongi/.codex/worktrees/business-repair-retrieval/Civil-Complaints-System/data/knowledge/evaluations')
LABELS = OLD / 'business_label_selection_20261009'
PERM = OLD / 'business_permutation_selection_20261009'
MAPPING = base.MAPPINGS['primary']
ORIGINAL = '로그인(ID/PW) 후 수령 가능'
REPLACEMENTS = [('d1', '로그인(ID/PW) 후 수령할 수 있음'),
                ('d2', '로그인(ID/PW) 후 수령해야 함'),
                ('d3', '로그인(ID/PW) 후 수령할 의무는 없음')]


def derive(case, replacement):
    assert len(case['blocks']) == 1
    text = case['blocks'][0]['text']
    assert text.count(ORIGINAL) == 1
    result = deepcopy(case)
    result['blocks'][0]['text'] = text.replace(ORIGINAL, replacement, 1)
    return result


def prepare():
    assert not (OUT / 'prepared.json').exists()
    original = next(c for c in read(PERM / 'confirmation_inputs.json') if c['id'] == 'NLC-C04')
    prompt_path = PERM / 'prompts/confirmation_NLC-C04_SUC_A.txt'
    assert prompt_path.read_text() == base.prompt(original, 'A', MAPPING)
    inputs = []
    diffs = []
    for id, replacement in REPLACEMENTS:
        case = derive(original, replacement)
        prompt = base.prompt(case, 'A', MAPPING)
        assert prompt == prompt_path.read_text().replace(ORIGINAL, replacement, 1)
        inputs.append(dict(id=id, case=case, prompt=prompt))
        diffs.extend(difflib.unified_diff(original['blocks'][0]['text'].splitlines(True),
                     case['blocks'][0]['text'].splitlines(True), fromfile='original', tofile=id))
    write(OUT / 'baseline_case.json', original)
    (OUT / 'baseline_prompt.txt').write_bytes(prompt_path.read_bytes())
    write(OUT / 'derived_inputs.json', inputs)
    (OUT / 'source_changes.diff').write_text(''.join(diffs))
    paths = {'baseline_request.json': PERM / 'confirmation/NLC-C04_SUC_A_request.json',
             'baseline_response.json': PERM / 'confirmation/NLC-C04_SUC_A_response.json',
             'baseline_props.json': PERM / 'confirmation/props.json',
             'runtime_identity.json': LABELS / 'runtime_identity.json',
             'baseline_freeze.json': LABELS / 'freeze.json'}
    for name, path in paths.items():
        (OUT / name).write_bytes(path.read_bytes())
    request = read(OUT / 'baseline_request.json')
    settings = {k: v for k, v in request.items() if k != 'prompt'}
    assert settings == dict(base.SETTINGS, n_predict=2048, n_probs=0)
    write(OUT / 'settings.json', settings)
    record = next(c for c in read(PERM / 'confirmation/result.json')['A_rows'] if c['id'] == 'NLC-C04')
    write(OUT / 'baseline_record.json', record)
    identity = read(OUT / 'runtime_identity.json')
    assert sha(Path(identity['engine_path'])) == identity['engine_sha256']
    assert sha(Path(identity['gguf_path'])) == identity['gguf_sha256']
    names = [*paths, 'baseline_case.json', 'baseline_prompt.txt', 'derived_inputs.json',
             'source_changes.diff', 'settings.json', 'baseline_record.json', 'criteria.json',
             'source_audit.json', 'authorization.json']
    write(OUT / 'prepared.json', dict(issue=637, at=time.time(), new_calls=0,
          files={n: sha(OUT / n) for n in names},
          code={str(p.relative_to(ROOT)): sha(p) for p in
                [Path(__file__), Path(base.__file__), ROOT / 'scripts/compare_business_nli.py']},
          origin_files={str(p): sha(p) for p in [*paths.values(), prompt_path,
                        PERM / 'confirmation_inputs.json', PERM / 'confirmation/result.json']},
          engine_argv=read(OUT / 'baseline_freeze.json')['engine_argv']))


def preflight():
    assert not (OUT / 'freeze.json').exists()
    prepared = read(OUT / 'prepared.json')
    assert all(sha(OUT / n) == h for n, h in prepared['files'].items())
    assert all(sha(ROOT / n) == h for n, h in prepared['code'].items())
    assert read(OUT / 'authorization.json')['compute_allocated']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models']
    props = base.api('/props')
    prior = read(OUT / 'baseline_props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {
        k: v for k, v in prior.items() if k != 'media_marker'}
    rows = read(OUT / 'derived_inputs.json')
    for marker in [props['media_marker'], prior['media_marker']]:
        assert all(marker not in r['prompt'] for r in rows)
    baseline_ids = base.api('/tokenize', dict(content=(OUT / 'baseline_prompt.txt').read_text(),
                                             add_special=False, parse_special=True))['tokens']
    assert baseline_ids == read(OUT / 'baseline_request.json')['prompt']
    requests = []
    for row in rows:
        ids = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(ids) + 2048 < 8192
        requests.append(dict(id=row['id'], input_tokens=len(ids),
                             request=dict(read(OUT / 'settings.json'), prompt=ids)))
    write(OUT / 'requests.json', requests)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(prepared_sha256=sha(OUT / 'prepared.json'), at=time.time(),
          requests_sha256=sha(OUT / 'requests.json'), props_sha256=sha(OUT / 'props.json'),
          baseline_token_ids_equal=True, new_semantic_calls=0, allowed_calls=3,
          props_exception='Only per-process media_marker; neither marker occurs in any text prompt.'))


def run():
    frozen = read(OUT / 'freeze.json')
    prepared = read(OUT / 'prepared.json')
    assert sha(OUT / 'prepared.json') == frozen['prepared_sha256']
    assert sha(OUT / 'requests.json') == frozen['requests_sha256']
    assert all(sha(OUT / n) == h for n, h in prepared['files'].items())
    assert all(sha(ROOT / n) == h for n, h in prepared['code'].items())
    assert base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'
    dest.mkdir()  # An existing attempt is never overwritten or resumed implicitly.
    cases = {r['id']: r['case'] for r in read(OUT / 'derived_inputs.json')}
    result = dict(calls=0, cases=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['cases'].append(record)
        before = time.monotonic()
        result['calls'] += 1
        write(dest / 'result.json', result)
        try:
            raw = base.call('/completion', row['request'])
            (dest / f"{row['id']}_response.json").write_bytes(raw)
            response = json.loads(raw)
            record.update(timings=response.get('timings'), stop_type=response.get('stop_type'),
                          truncated=response.get('truncated'), response_sha256=sha(dest / f"{row['id']}_response.json"))
            if response.get('truncated') or response.get('stop_type') != 'eos':
                raise ValueError('incomplete_generation')
            answer = json.loads(base.PREFIX + response['content'])
            if not isinstance(answer, dict):
                raise ValueError('output_schema')
            label = answer.get('label')
            record.update(answer=answer, semantic_label=MAPPING.get(label, label if label in MAPPING.values() else None),
                          status='completed')
            try:
                base.parse_a(response['content'], cases[row['id']], MAPPING)
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError) as error:
                record['contract_error'] = str(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(status='failed', error=repr(error))
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], record['status'], record.get('semantic_label'), flush=True)


def selfcheck():
    case = dict(id='same', raw={'Event': 'unchanged'}, blocks=[dict(id='b1', text='앞\n' + ORIGINAL + '\n뒤')])
    changed = derive(case, REPLACEMENTS[0][1])
    assert case['blocks'][0]['text'] == '앞\n' + ORIGINAL + '\n뒤'
    assert changed['raw'] == case['raw'] and changed['id'] == case['id']
    assert changed['blocks'][0]['text'] == '앞\n' + REPLACEMENTS[0][1] + '\n뒤'
    for text in ['missing', ORIGINAL + ORIGINAL]:
        invalid = deepcopy(case)
        invalid['blocks'][0]['text'] = text
        try:
            derive(invalid, REPLACEMENTS[0][1])
        except AssertionError:
            continue
        raise AssertionError('ambiguous or absent source span accepted')
    print('Single source-span edit, candidate/context preservation, absent/duplicate rejection passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'preflight', 'run', 'selfcheck'])
    globals()[parser.parse_args().mode]()

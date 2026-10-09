"""One frozen reason-before-verdict comparison against the saved issue 637 B8."""
import argparse
import difflib
import json
from pathlib import Path
import time
import urllib.request

import compare_business_premise_check as prior
from compare_business_modality_spans import strict_object
from compare_business_nli import read, write, sha

ROOT = prior.ROOT
OLD = prior.OUT
OUT = ROOT / 'data/knowledge/evaluations/business_reason_first_20261009'
ORDER = ['evidence', 'error_fields', 'error_spans', 'reason', 'analysis', 'label']
ANALYSIS_ORDER = ['missing_premise', 'compatible_interpretation', 'source_state']
REPLACEMENTS = [
    ('기존 판정 호출 하나 안에서 다음 분석을 먼저 작성한 다음 최종 판정한다.',
     '기존 판정 호출 하나 안에서 원문 근거·후보 차이·상세 이유를 먼저 작성한 다음 자료 상태와 최종 판정한다.'),
    ('출력은 JSON 객체 하나다. analysis를 label보다 먼저 출력한다.',
     '출력은 JSON 객체 하나다. evidence, error_fields, error_spans, reason, analysis, label 순서로 출력한다. analysis 안에서는 missing_premise, compatible_interpretation, source_state 순서로 출력한다.'),
    ('최상위 필드는 analysis, label, error_fields, error_spans, evidence, reason만 사용한다.',
     '최상위 필드는 evidence, error_fields, error_spans, reason, analysis, label만 사용한다.'),
]


def prompt(case):
    text = prior.prompt(case)
    for old, new in REPLACEMENTS:
        assert text.count(old) == 1
        text = text.replace(old, new, 1)
    return text


def parse_final(answer, case):
    prior.parse_b(answer, case)
    if list(answer) != ORDER or list(answer['analysis']) != ANALYSIS_ORDER:
        raise ValueError('actual_generation_order')
    return answer


def prepare():
    assert not (OUT / 'prepared.json').exists()
    old_freeze, old_prepared = read(OLD / 'freeze.json'), read(OLD / 'prepared.json')
    assert sha(OLD / 'prepared.json') == old_freeze['prepared_sha256']
    assert sha(OLD / 'requests.json') == old_freeze['requests_sha256']
    assert all(sha(OLD / n) == h for n, h in old_prepared['files'].items())
    assert all(sha(ROOT / n) == h for n, h in old_prepared['code'].items())
    for name in ['inputs.json', 'settings.json', 'criteria.json']:
        (OUT / name).write_bytes((OLD / name).read_bytes())
    cases, old_prompts, old_requests = read(OUT / 'inputs.json'), read(OLD / 'prompts.json'), read(OLD / 'requests.json')
    old_result = read(OLD / 'run/result.json')
    assert len(cases) == len(old_result['cases']) == 8
    baseline, prompts, changes = [], [], []
    for case, saved, request, record in zip(cases, old_prompts, old_requests, old_result['cases']):
        assert case['id'] == saved['id'] == request['id'] == record['id']
        assert saved['prompt'] == prior.prompt(case)
        raw_path = OLD / 'run' / (case['id'] + '_response.json')
        assert sha(raw_path) == record['response_sha256']
        assert {k: v for k, v in request['request'].items() if k != 'prompt'} == read(OUT / 'settings.json')
        baseline.append(dict(id=case['id'], prompt=saved['prompt'], request=request['request'],
                             original_record=record, raw_path=str(raw_path), raw_sha256=sha(raw_path)))
        changed = prompt(case)
        prompts.append(dict(id=case['id'], prompt=changed))
        changes.extend(difflib.unified_diff(saved['prompt'].splitlines(True), changed.splitlines(True),
                                          fromfile=case['id'] + '/saved_B8', tofile=case['id'] + '/reason_first'))
    write(OUT / 'baselines.json', baseline)
    write(OUT / 'prompts.json', prompts)
    (OUT / 'prompt_changes.diff').write_text(''.join(changes))
    names = ['inputs.json', 'settings.json', 'criteria.json', 'baselines.json', 'prompts.json',
             'prompt_changes.diff', 'authorization.json', 'comparison_protocol.json']
    code = [Path(__file__), Path(prior.__file__), Path(prior.base.__file__),
            ROOT / 'scripts/compare_business_nli.py', ROOT / 'scripts/compare_business_modality_spans.py']
    write(OUT / 'prepared.json', dict(at=time.time(), files={n: sha(OUT / n) for n in names},
          code={str(p.relative_to(ROOT)): sha(p) for p in code},
          previous_files={str(p.relative_to(ROOT)): sha(p) for p in [OLD / 'freeze.json', OLD / 'run/result.json',
                          prior.PARENT / 'runtime_identity.json', OLD / 'props.json']},
          maximum_calls=8, new_baseline_calls=0, changed='Three output-order instruction substitutions only.'))


def check_prepared():
    prepared = read(OUT / 'prepared.json')
    assert all(sha(OUT / n) == h for n, h in prepared['files'].items())
    for group in ['code', 'previous_files']:
        assert all(sha(ROOT / n) == h for n, h in prepared[group].items())
    assert all(sha(Path(r['raw_path'])) == r['raw_sha256'] for r in read(OUT / 'baselines.json'))


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check_prepared()
    assert read(OUT / 'authorization.json')['compute_allocated']
    identity = read(prior.PARENT / 'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key + '_path'])) == identity[key + '_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models']
    props, old_props = prior.base.api('/props'), read(OLD / 'props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in old_props.items() if k != 'media_marker'}
    requests = []
    for row, baseline in zip(read(OUT / 'prompts.json'), read(OUT / 'baselines.json')):
        assert row['id'] == baseline['id']
        old_ids = prior.base.api('/tokenize', dict(content=baseline['prompt'], add_special=False, parse_special=True))['tokens']
        assert old_ids == baseline['request']['prompt']
        assert all(marker not in text for marker in [props['media_marker'], old_props['media_marker']]
                   for text in [row['prompt'], baseline['prompt']])
        ids = prior.base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        settings = read(OUT / 'settings.json')
        assert len(ids) + settings['n_predict'] < 8192
        requests.append(dict(id=row['id'], input_tokens=len(ids), request=dict(settings, prompt=ids)))
    write(OUT / 'requests.json', requests)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), prepared_sha256=sha(OUT / 'prepared.json'),
          requests_sha256=sha(OUT / 'requests.json'), props_sha256=sha(OUT / 'props.json'),
          all_eight_baseline_tokens_equal=True, allowed_calls=8, new_calls=0))


def run():
    frozen = read(OUT / 'freeze.json')
    check_prepared()
    for name in ['prepared', 'requests', 'props']:
        assert sha(OUT / (name + '.json')) == frozen[name + '_sha256']
    assert prior.base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    cases = {c['id']: c for c in read(OUT / 'inputs.json')}
    result = dict(calls=0, cases=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['cases'].append(record)
        before = time.monotonic()
        result['calls'] += 1
        write(dest / 'result.json', result)
        try:
            raw = prior.base.call('/completion', row['request'])
            path = dest / (row['id'] + '_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(timings=response.get('timings'), stop_type=response.get('stop_type'),
                          truncated=response.get('truncated'), response_sha256=sha(path))
            if response.get('truncated') or response.get('stop_type') != 'eos':
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'], object_pairs_hook=strict_object)
            if not isinstance(answer, dict):
                raise ValueError('output_schema')
            label = answer.get('label')
            record.update(answer=answer, actual_key_order=list(answer),
                          actual_analysis_order=list(answer['analysis']) if isinstance(answer.get('analysis'), dict) else None,
                          semantic_label=prior.MAPPING.get(label, label if label in prior.MAPPING.values() else None), status='completed')
            try:
                parse_final(answer, cases[row['id']])
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError) as error:
                record['contract_error'] = str(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(status='failed', error=repr(error))
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], record['status'], record.get('semantic_label'), record.get('contract_error'), flush=True)


def selfcheck():
    case = dict(raw={'Event': 'candidate clause'}, blocks=[dict(id='b1', text='exact evidence')])
    answer = dict(evidence=[dict(block_id='b1', quote='exact evidence')], error_fields=['Event'],
                  error_spans=[dict(field='Event', quote='candidate')], reason='unsupported(2), not a label override',
                  analysis=dict(missing_premise=None, compatible_interpretation=None, source_state='present'), label='3')
    assert parse_final(answer, case)['label'] == '3'
    assert list(json.loads(json.dumps(answer), object_pairs_hook=strict_object)) == ORDER
    for bad in [dict(analysis=answer['analysis'], **{k: v for k, v in answer.items() if k != 'analysis'}),
                dict(answer, analysis=dict(source_state='present', missing_premise=None, compatible_interpretation=None)),
                dict(answer, evidence=[dict(block_id='b1', quote='absent')]),
                dict(answer, error_spans=[dict(field='Event', quote='absent')])]:
        try:
            parse_final(bad, case)
        except ValueError:
            continue
        raise AssertionError('invalid contract accepted')
    try:
        json.loads('{"label":"2","label":"3"}', object_pairs_hook=strict_object)
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate keys accepted')
    old, changed = prior.prompt(case), prompt(case)
    for before, after in REPLACEMENTS:
        changed = changed.replace(after, before, 1)
    assert changed == old
    print('Actual order, duplicate keys, exact quotes, unchanged payload and no reason-to-label repair passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'preflight', 'run', 'selfcheck'])
    globals()[parser.parse_args().mode]()

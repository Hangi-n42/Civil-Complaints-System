"""Issue 637: one replacement call per original case, without downstream judges."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_label_selection as base
from compare_business_modality_spans import strict_object
from compare_business_nli import read, write, sha

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'data/knowledge/evaluations/business_entailment_boundary_20261009'
OUT = PARENT / 'premise_comparison'
MAPPING = base.MAPPINGS['primary']
INSTRUCTION = '''기존 판정 호출 하나 안에서 다음 분석을 먼저 작성한 다음 최종 판정한다. 원문과 후보는 변경하지 않는다.
후보를 원문에서 도출하려면 원문에 없는 구체적인 추가 전제가 필요한가? 필요하다면 missing_premise에 원문의 어느 관계보다 무엇이 더 필요한지 쓴다. 후보가 참이라는 단순 복창은 분석이 아니다.
또는 원문의 모든 조건·주체·행위·예외·시점·순서를 유지해도 후보의 더 강한 주장이 성립하지 않는 구체적인 해석이 가능한가? 가능하면 compatible_interpretation에 그 해석과 어떤 원문 내용을 유지하는지 쓴다.
이 둘은 논리 검토용 가정이지 원문 사실이나 현실 사건이 아니다. 원문에 없는 면제·금지·현실 규칙으로 확정하지 않는다. 행위를 하지 않은 상황은 의무가 있지만 위반한 경우일 수 있으므로 그 자체로 의무 부재의 반례가 아니다.
반례나 추가 전제를 반드시 만들어야 하는 것은 아니다. 해당하지 않거나 유효한 해석을 찾지 못하면 null을 쓴다. 찾지 못했다는 사실만으로 supported가 되지 않는다. supported에는 후보의 모든 주장에 대한 실제 원문 지지 이유가 필요하다. 조건을 어기는 해석, 다른 대상/주체/시점의 해석은 무효다.
필요한 인용 조문 등 필수 참조 전문이 제공되지 않으면 analysis.source_state를 required_reference_missing으로 기록하고, reason에 어떤 자료가 빠졌는지 쓴다. 미지지와 명시 반대를 구분한다. 제공 자료에서 판단 가능한 경우 present, 자료 상태 자체를 판단하지 못하면 uncertain이다. 이 필드가 스스로 검증 완료를 뜻하지 않는다.
출력은 JSON 객체 하나다. analysis를 label보다 먼저 출력한다. analysis는 missing_premise와 compatible_interpretation(각각 문자열 또는 null), source_state(present/required_reference_missing/uncertain)만 포함한다.
label은 아래의 숫자 코드 문자열이다. error_fields는 후보 raw의 실제 문제 필드명 목록이다. error_spans는 각 문제의 실제 field와 그 필드에 정확히 한 번 나타나는 연속 문자열 quote 목록이다. supported이면 두 목록은 빈 배열이다.
evidence에는 실제 block_id와 원문 블록의 정확한 부분 문자열 quote를 최소 하나 넣는다. reason에는 원문 지지 또는 실제 차이·문제 위치와 분석의 근거를 쓴다. 원문·후보 인용을 바꾸지 않는다.
최상위 필드는 analysis, label, error_fields, error_spans, evidence, reason만 사용한다.'''


def prompt(case):
    system = base.COMMON + '\n' + INSTRUCTION + '\n판정 코드: ' + json.dumps(MAPPING, ensure_ascii=False)
    return ('<|im_start|>system\n' + system + '<|im_end|>\n<|im_start|>user\n' +
            json.dumps(case, ensure_ascii=False) + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{')


def parse_b(answer, case):
    if not isinstance(answer, dict) or set(answer) != {'analysis', 'label', 'error_fields', 'error_spans', 'evidence', 'reason'}:
        raise ValueError('output_schema')
    if list(answer).index('analysis') > list(answer).index('label'):
        raise ValueError('analysis_not_before_label')
    analysis = answer['analysis']
    if not isinstance(analysis, dict) or set(analysis) != {'missing_premise', 'compatible_interpretation', 'source_state'}:
        raise ValueError('analysis_schema')
    if analysis['source_state'] not in {'present', 'required_reference_missing', 'uncertain'}:
        raise ValueError('source_state')
    for key in ['missing_premise', 'compatible_interpretation']:
        value = analysis[key]
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError('analysis_text')
    old = {k: answer[k] for k in ['label', 'error_fields', 'evidence', 'reason']}
    text = json.dumps(old, ensure_ascii=False, separators=(',', ':'))
    assert text.startswith(base.PREFIX)
    base.parse_a(text[len(base.PREFIX):], case, MAPPING)
    spans = answer['error_spans']
    if not isinstance(spans, list) or (answer['label'] == '1') != (spans == []):
        raise ValueError('span_label_consistency')
    for span in spans:
        if not isinstance(span, dict) or set(span) != {'field', 'quote'}:
            raise ValueError('span_schema')
        field, quote = span['field'], span['quote']
        value = case['raw'].get(field) if isinstance(field, str) else None
        if field not in answer['error_fields'] or not isinstance(value, str) or not isinstance(quote, str) or not quote or value.count(quote) != 1:
            raise ValueError('nonunique_candidate_span')
    return answer


def prepare():
    assert not (OUT / 'prepared.json').exists()
    cases = read(OUT / 'inputs.json')
    baselines = read(OUT / 'baselines.json')
    assert [c['id'] for c in cases] == [r['id'] for r in baselines]
    settings = read(PARENT / 'settings.json')
    for case, row in zip(cases, baselines):
        assert row['prompt'] == base.prompt(case, 'A', MAPPING)
        assert {k: v for k, v in row['request'].items() if k != 'prompt'} == settings
        assert all(sha(Path(p)) == h for p, h in row['original_paths_sha256'].items())
    write(OUT / 'prompts.json', [dict(id=c['id'], prompt=prompt(c)) for c in cases])
    write(OUT / 'settings.json', settings)
    names = ['inputs.json', 'baselines.json', 'prompts.json', 'settings.json', 'criteria.json', 'authorization.json']
    paths = [Path(__file__), Path(base.__file__), ROOT / 'scripts/compare_business_nli.py',
             ROOT / 'scripts/compare_business_modality_spans.py']
    write(OUT / 'prepared.json', dict(at=time.time(), issue=637,
          files={n: sha(OUT / n) for n in names}, code={str(p.relative_to(ROOT)): sha(p) for p in paths},
          parent_files={n: sha(PARENT / n) for n in ['runtime_identity.json', 'baseline_props.json']},
          budget=8, new_A_calls=0, changed='Single-call task, output order/fields and assistant JSON prefill as one configuration.'))


def preflight():
    assert not (OUT / 'freeze.json').exists()
    p = read(OUT / 'prepared.json')
    assert all(sha(OUT / n) == h for n, h in p['files'].items())
    assert all(sha(ROOT / n) == h for n, h in p['code'].items())
    assert all(sha(PARENT / n) == h for n, h in p['parent_files'].items())
    assert read(OUT / 'authorization.json')['compute_allocated']
    identity = read(PARENT / 'runtime_identity.json')
    assert sha(Path(identity['engine_path'])) == identity['engine_sha256']
    assert sha(Path(identity['gguf_path'])) == identity['gguf_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models']
    props = base.api('/props')
    prior = read(PARENT / 'baseline_props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in prior.items() if k != 'media_marker'}
    requests = []
    for row, old in zip(read(OUT / 'prompts.json'), read(OUT / 'baselines.json')):
        assert row['id'] == old['id']
        old_ids = base.api('/tokenize', dict(content=old['prompt'], add_special=False, parse_special=True))['tokens']
        assert old_ids == old['request']['prompt']
        assert all(marker not in row['prompt'] for marker in [props['media_marker'], prior['media_marker']])
        ids = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(ids) + 2048 < 8192
        requests.append(dict(id=row['id'], input_tokens=len(ids), request=dict(read(OUT / 'settings.json'), prompt=ids)))
    write(OUT / 'requests.json', requests)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), prepared_sha256=sha(OUT / 'prepared.json'),
          requests_sha256=sha(OUT / 'requests.json'), props_sha256=sha(OUT / 'props.json'),
          all_eight_baseline_tokens_equal=True, allowed_calls=8, new_calls=0))


def run():
    f, p = read(OUT / 'freeze.json'), read(OUT / 'prepared.json')
    assert sha(OUT / 'prepared.json') == f['prepared_sha256']
    assert sha(OUT / 'requests.json') == f['requests_sha256']
    assert all(sha(OUT / n) == h for n, h in p['files'].items())
    assert all(sha(ROOT / n) == h for n, h in p['code'].items())
    assert base.api('/props') == read(OUT / 'props.json')
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
            raw = base.call('/completion', row['request'])
            path = dest / f"{row['id']}_response.json"
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
            record.update(answer=answer, semantic_label=MAPPING.get(label, label if label in MAPPING.values() else None), status='completed')
            try:
                parse_b(answer, cases[row['id']])
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
    case = dict(raw={'Event': 'candidate clause'}, blocks=[dict(id='b1', text='evidence text')])
    answer = dict(analysis=dict(missing_premise=None, compatible_interpretation=None, source_state='present'),
                  label='1', error_fields=[], error_spans=[], evidence=[dict(block_id='b1', quote='evidence')], reason='contract only')
    assert parse_b(answer, case)
    wrong_quote = dict(answer, evidence=[dict(block_id='b1', quote='absent')])
    bad_span = dict(answer, label='2', error_fields=['Event'], error_spans=[dict(field='Event', quote='absent')])
    bad_order = dict(label=answer['label'], **{k: v for k, v in answer.items() if k != 'label'})
    for invalid in [wrong_quote, bad_span, bad_order]:
        try:
            parse_b(invalid, case)
        except ValueError:
            continue
        raise AssertionError('invalid contract accepted')
    print('Analysis order, source/candidate quote contracts and normal empty spans passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'preflight', 'run', 'selfcheck'])
    globals()[parser.parse_args().mode]()

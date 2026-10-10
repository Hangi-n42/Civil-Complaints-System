"""Issue 647: frozen two-situation judgments using previously exposed minimal pairs."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_entailment_boundary as prior
import compare_business_label_selection as base
from business_dependency_parser import read, write

ROOT, sha = prior.ROOT, prior.sha
OUT = ROOT / 'data/knowledge/evaluations/business_joint_contrast_20261010'
PAIRS = [('p1', 'original', 'd2'), ('p2', 'd1', 'd3'), ('p3', 'original', 'd1')]
INSTRUCTION = base.COMMON + '''
두 situations X/Y는 서로 독립된 문서 상황이다. 동일한 후보 raw를 각각의 상황에서 판단한다. 한쪽 원문의 사실을 다른 쪽 근거로 쓰지 않는다.
실제 달라진 원문 구절을 각 상황의 block_id/정확한 연속 quote로 짚고 조건(condition)·주체(subject)·행위(action)·양태(modality)·표현만의 차이(wording) 중 무엇이 달라지는지 설명한다. 뜻이 같거나 해석이 미확정일 수도 있다.
각 상황의 원문 전체·조건·제목·주체·시점·행위를 읽고 동일 후보의 지지 범위를 따로 판단한다. 반드시 한쪽만 옳다고 가정하지 않는다. 둘 다 지지, 둘 다 미지지, 명시 반증 또는 판단 불가도 가능하다.
판정 코드 1=supported, 2=unsupported, 3=contradicted. 필요한 해석을 확정하지 못하면 label은 null이고 이유에 미확정을 남긴다. 근거를 못 찾았다는 사실만으로 지지나 명시 반증을 만들지 않는다. 의무의 명시 부정과 행위 금지는 다르다.
출력은 differences와 judgments를 이 순서로 가진 JSON 하나다.
differences는 [{"X":{"block_id":"...","quote":"..."},"Y":{"block_id":"...","quote":"..."},"dimensions":["..."],"reason":"..."}]다. 차이를 특정하지 못하면 빈 목록과 각 판단 이유에 그 한계를 남긴다.
judgments는 {"X":판단,"Y":판단}이다. 각 판단은 label,error_fields,error_spans,evidence,reason을 갖는다. label은 코드 문자열 또는 null이다. error_fields는 후보의 실제 문제 필드, error_spans는 [{"field":"...","quote":"후보의 실제 문제 구절"}], evidence는 그 상황만의 [{"block_id":"...","quote":"원문의 실제 구절"}], reason은 지지·미지지·명시 반증을 구분한 이유다.
supported이면 error_fields/error_spans는 빈 목록이다. 2/3이면 정확한 오류 필드·구절을 남긴다. 각 인용은 해당 원형 문자열에 정확히 한 번 있는 연속 부분문자열이며 개행을 바꾸지 않는다. 수정문·새 업무 규칙·현실의 면제 또는 금지를 만들어 쓰지 않는다.'''


def prompt(x, y):
    assert x['raw'] == y['raw']
    payload = dict(raw=x['raw'], situations={key: {k: v for k, v in case.items() if k != 'raw'}
                                           for key, case in [('X', x), ('Y', y)]})
    return ('<|im_start|>system\n' + INSTRUCTION + '<|im_end|>\n<|im_start|>user\n' +
            json.dumps(payload, ensure_ascii=False) + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{')


def exact(ref, case, candidate=False):
    key = 'field' if candidate else 'block_id'
    texts = case['raw'] if candidate else {b['id']: b['text'] for b in case['blocks']}
    if set(ref) != {key, 'quote'} or not isinstance(ref['quote'], str) or not ref['quote']:
        raise ValueError('reference_schema')
    text = texts.get(ref[key])
    if not isinstance(text, str) or text.count(ref['quote']) != 1:
        raise ValueError('nonunique_or_wrong_situation_reference')


def parse(answer, x, y):
    if list(answer) != ['differences', 'judgments'] or set(answer['judgments']) != {'X', 'Y'}:
        raise ValueError('joint_schema')
    if not isinstance(answer['differences'], list):
        raise ValueError('differences_schema')
    for difference in answer['differences']:
        if set(difference) != {'X', 'Y', 'dimensions', 'reason'}:
            raise ValueError('difference_schema')
        exact(difference['X'], x); exact(difference['Y'], y)
        if not difference['dimensions'] or not set(difference['dimensions']) <= {'condition', 'subject', 'action', 'modality', 'wording', 'uncertain'}:
            raise ValueError('difference_dimensions')
        if not isinstance(difference['reason'], str) or not difference['reason'].strip():
            raise ValueError('difference_reason')
    for key, case in [('X', x), ('Y', y)]:
        judgment = answer['judgments'][key]
        if set(judgment) != {'label', 'error_fields', 'error_spans', 'evidence', 'reason'}:
            raise ValueError('judgment_schema')
        if judgment['label'] is not None:
            legacy = {k: judgment[k] for k in ['label', 'error_fields', 'evidence', 'reason']}
            text = json.dumps(legacy, ensure_ascii=False, separators=(',', ':'))
            assert text.startswith(base.PREFIX)
            base.parse_a(text[len(base.PREFIX):], case, prior.MAPPING)
        elif not isinstance(judgment['reason'], str) or not judgment['reason'].strip():
            raise ValueError('unresolved_without_reason')
        for ref in judgment['evidence']: exact(ref, case)
        for ref in judgment['error_spans']: exact(ref, case, candidate=True)
        if set(judgment['error_fields']) != {r['field'] for r in judgment['error_spans']}:
            raise ValueError('error_field_span_mismatch')
        if judgment['label'] in {'2', '3'} and not judgment['error_spans']:
            raise ValueError('error_without_location')
    return answer


def prepare():
    assert not (OUT / 'prepared.json').exists()
    OUT.mkdir(exist_ok=True)
    cases = {'original': read(prior.OUT / 'baseline_case.json')}
    cases.update({r['id']: r['case'] for r in read(prior.OUT / 'derived_inputs.json')})
    for ident, replacement in prior.REPLACEMENTS:
        assert cases[ident] == prior.derive(cases['original'], replacement)
    rows = [dict(id=ident, X=x, Y=y, prompt=prompt(cases[x], cases[y])) for ident, x, y in PAIRS]
    write(OUT / 'inputs.json', cases); write(OUT / 'prompts.json', rows)
    write(OUT / 'criteria.json', dict(issue=647, expected={'original': '2', 'd1': '2', 'd2': '1', 'd3': '3'},
        pairs=PAIRS, maximum_initial_calls=3, all_cases_development_exposed=True,
        checks=['Original/d1 permission does not establish obligation; do not assert actual absence of duty.',
                'd2 obligation remains supported; d3 explicitly negates duty, not the action.',
                'Correct original judgment AND candidate error span required; difference detection alone is insufficient.',
                'Report repeated situations per occurrence and as four unique inputs; not six independent cases.',
                'Historical A fullword labels and strict format failures remain separate.',
                'Only meaningful improvement can authorize the minimum reverse-order check.',
                'Curated contrast success is not automatic contrast construction or product success.']))
    write(OUT / 'exposure.json', read(ROOT / 'data/knowledge/evaluations/business_document_boundary_20261010/exposure_inventory.json'))
    (OUT / 'settings.json').write_bytes((prior.OUT / 'settings.json').read_bytes())
    baseline = [prior.OUT / n for n in ['baseline_case.json', 'baseline_prompt.txt', 'baseline_request.json',
                 'baseline_response.json', 'baseline_props.json', 'runtime_identity.json', 'derived_inputs.json',
                 'requests.json', 'run/result.json', 'run/d1_response.json', 'run/d2_response.json', 'run/d3_response.json']]
    write(OUT / 'prepared.json', dict(at=time.time(), context=8192, initial_calls=3,
        code={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), Path(base.__file__), Path(prior.__file__)]},
        files={n: sha(OUT / n) for n in ['inputs.json', 'prompts.json', 'settings.json', 'criteria.json', 'exposure.json']},
        baselines={str(p.relative_to(ROOT)): sha(p) for p in baseline},
        changed='Joint task, difference explanation, multiple outputs and JSON prefill as one configuration.'))


def selfcheck():
    x = dict(id='same', raw={'Event': '주장'}, blocks=[dict(id='b1', text='첫째')])
    y = dict(x, blocks=[dict(id='b1', text='둘째')])
    exact(dict(block_id='b1', quote='첫째'), x)
    try: exact(dict(block_id='b1', quote='첫째'), y)
    except ValueError: pass
    else: raise AssertionError('cross-situation evidence accepted')
    payload = json.loads(prompt(x, y).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
    assert payload['raw'] == x['raw'] and payload['situations']['X']['blocks'] == x['blocks']
    assert payload['situations']['Y']['blocks'] == y['blocks']
    answer = dict(differences=[], judgments={key: dict(label='1', error_fields=[], error_spans=[],
                      evidence=[dict(block_id='b1', quote=text)], reason='일치')
                      for key, text in [('X', '첫째'), ('Y', '둘째')]})
    assert parse(answer, x, y) == answer
    print('Full input preservation, shared candidate, situation-specific citation checks passed')


def check():
    prepared = read(OUT / 'prepared.json')
    assert all(sha(ROOT / n) == h for n, h in prepared['code'].items())
    assert all(sha(OUT / n) == h for n, h in prepared['files'].items())
    assert all(sha(ROOT / n) == h for n, h in prepared['baselines'].items())


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check()
    identity = read(prior.OUT / 'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key + '_path'])) == identity[key + '_sha256']
    props, old = base.api('/props'), read(prior.OUT / 'baseline_props.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in old.items() if k != 'media_marker'}
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps') as response:
        assert not json.load(response)['models']
    originals = [('original', (prior.OUT / 'baseline_prompt.txt').read_text(encoding='utf-8'), read(prior.OUT / 'baseline_request.json'))]
    derived = {r['id']: r for r in read(prior.OUT / 'derived_inputs.json')}
    originals += [(r['id'], derived[r['id']]['prompt'], r['request']) for r in read(prior.OUT / 'requests.json')]
    settings = read(OUT / 'settings.json')
    for ident, text, request in originals:
        ids = base.api('/tokenize', dict(content=text, add_special=False, parse_special=True))['tokens']
        assert request == dict(settings, prompt=ids)
    rows = []
    for row in read(OUT / 'prompts.json'):
        ids = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(ids) + settings['n_predict'] < 8192
        rows.append(dict(row, input_tokens=len(ids), request=dict(settings, prompt=ids)))
    write(OUT / 'requests.json', rows); write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), max_calls=3, context=8192,
        authorized_by='01a11fd9-f71b-7261-832b-0681548a03c4', A_exact_requests_reused=4,
        files={n: sha(OUT / n) for n in ['prepared.json', 'requests.json', 'props.json']}))
    print([(r['id'], r['X'], r['Y'], r['input_tokens']) for r in rows], flush=True)


def run():
    check()
    assert all(sha(OUT / n) == h for n, h in read(OUT / 'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'; dest.mkdir()
    cases = read(OUT / 'inputs.json')
    result = dict(calls=0, records=[])
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], X=row['X'], Y=row['Y'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record); result['calls'] += 1
        assert result['calls'] <= 3
        write(dest / 'result.json', result)
        before = time.monotonic()
        try:
            raw = base.call('/completion', row['request'])
            path = dest / (row['id'] + '_response.json'); path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'),
                          stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('stop_type') != 'eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'])
            record['answer'] = answer
            record['semantic_labels'] = {key: prior.MAPPING.get(j.get('label'), j.get('label') if j.get('label') in prior.MAPPING.values() else None)
                                         for key, j in answer.get('judgments', {}).items()}
            try:
                parse(answer, cases[row['X']], cases[row['Y']])
                record['contract_pass'] = True
            except (ValueError, KeyError, TypeError, AssertionError) as error:
                record['contract_error'] = repr(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], record.get('semantic_labels'), record['contract_pass'], record.get('error'), flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare', 'selfcheck', 'preflight', 'run'])
    globals()[cli.parse_args().mode]()

"""Research preparation: one raw condition deletion and addressed A judgments."""
from copy import deepcopy
import json
import re

import compare_business_explicit_opposition as previous

FIELDS = {'Event', 'Head', 'Tail'}
DIMENSIONS = {'condition', 'subject', 'action', 'modality', 'wording', 'uncertain'}
CONSTRUCTION_INSTRUCTION = '''후보 raw의 제공 문장 필드만 읽는다. 원문이나 정답 판단은 제공되지 않는다.
그 후보의 적용 상황을 제한하는 기존 조건 구절 한 곳만 선택한다. 조건을 제거한 상대 후보를 만드는 연구용 선택이며 원본의 오류/지지 여부를 판단하거나 정정하지 않는다.
주체·행위·대상·수량·기간·목록 항목을 조건과 함께 지우지 않는다. 새 단어·조건·수정문을 작성하지 않는다. 여러 조건은 한 곳만 선택한다.
정확한 연속 quote가 그 field에 한 번 있어야 한다. 조건을 특정할 수 없거나 다른 의미를 함께 지워야 하면 unsupported다.
JSON 하나: {"status":"constructed 또는 unsupported","field":"실제 필드 또는 null","quote":"조건 구절 또는 빈 문자열","reason":"선택 또는 지원 불가 이유"}.
unsupported이면 field=null, quote=""이다. 원문 미지지·반증·올바른 수정이라고 주장하지 않는다.'''
INSTRUCTION = previous.INSTRUCTION.replace(
    'dimensions와 reason도 갖는다.',
    'dimensions는 ["condition","subject","action","modality","wording","uncertain"] 중 실제 차이에 해당하는 문자열의 배열이며 reason도 갖는다.')
INSTRUCTION = INSTRUCTION.replace(
    'evidence는 [{"block_id":"...","quote":"원문의 실제 구절"}]',
    'evidence는 blocks의 evidence_ref ID만 담은 배열 ["e1", "..."]')
INSTRUCTION += '\n원문 근거는 evidence_ref ID를 선택하고 문장을 재작성하지 않는다. 여러 근거는 별도 ID로 선택한다. 주소 일치는 의미 지지의 충분한 근거가 아니다.\n'


def construction_prompt(raw):
    fields = {k: v for k, v in raw.items() if k in FIELDS and isinstance(v, str)}
    return chat(CONSTRUCTION_INSTRUCTION, dict(raw=fields))


def chat(instruction, payload):
    return ('<|im_start|>system\n' + instruction + '<|im_end|>\n<|im_start|>user\n' +
            json.dumps(payload, ensure_ascii=False) + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{')


def construct(raw, proposal):
    if not isinstance(proposal, dict) or set(proposal) != {'status', 'field', 'quote', 'reason'}:
        raise ValueError('construction_schema')
    if not isinstance(proposal['reason'], str) or not proposal['reason'].strip():
        raise ValueError('construction_reason')
    if proposal['status'] == 'unsupported':
        if proposal['field'] is not None or proposal['quote'] != '':
            raise ValueError('unsupported_with_change')
        return dict(status='unsupported', proposal=deepcopy(proposal), semantic_validity='not_assessed')
    if proposal['status'] != 'constructed' or proposal['field'] not in FIELDS:
        raise ValueError('construction_field')
    field, quote = proposal['field'], proposal['quote']
    text = raw.get(field)
    if not isinstance(text, str) or not isinstance(quote, str) or not quote.strip():
        raise ValueError('construction_quote')
    positions = [m.start() for m in re.finditer('(?=' + re.escape(quote) + ')', text)]
    if len(positions) != 1:
        raise ValueError('construction_address')
    start = positions[0]
    after = text[:start] + text[start + len(quote):]
    if not after.strip():
        raise ValueError('construction_empty_field')
    changed = deepcopy(raw)
    changed[field] = after
    assert text[:start] == after[:start] and text[start + len(quote):] == after[start:]
    assert {k: v for k, v in raw.items() if k != field} == {k: v for k, v in changed.items() if k != field}
    return dict(status='constructed_unverified', raw=changed, field=field,
                before_span=[start, start + len(quote)], after_span=[start, start],
                before_quote=quote, after_quote='', proposal=deepcopy(proposal), semantic_validity='unverified')


def addressed_cases(cases):
    result = deepcopy(cases)
    for case in result.values():
        for n, block in enumerate(case['blocks']):
            block['evidence_ref'] = f'e{n + 1}'
    return result


def prompt(cases):
    prepared = addressed_cases(cases)
    old = previous.prompt(prepared)
    assert old.count(previous.INSTRUCTION) == 1
    return old.replace(previous.INSTRUCTION, INSTRUCTION, 1)


def parse(content, cases, canonical_views=None):
    from app.knowledge.business_run import exact_evidence
    answer = json.loads('{' + content, object_pairs_hook=previous.previous.strict_object)
    if not isinstance(answer, dict) or list(answer) != ['differences', 'judgments'] or not isinstance(answer['judgments'], dict) or set(answer['judgments']) != set(cases):
        raise ValueError('candidate_coverage')
    if not isinstance(answer['differences'], list):
        raise ValueError('differences_schema')
    for difference in answer['differences']:
        dims = difference.get('dimensions')
        if not isinstance(dims, list) or not dims or any(not isinstance(v, str) or v not in DIMENSIONS for v in dims):
            raise ValueError('difference_dimensions_array')
    source = next(iter(cases.values()))['blocks']
    references = {f'e{n + 1}': block for n, block in enumerate(source)}
    if canonical_views is not None and (set(canonical_views) != set(references)
            or any(canonical_views[v]['text'] != block['text'] for v, block in references.items())):
        raise ValueError('canonical_evidence_scope_mismatch')
    restored = deepcopy(answer)
    addresses = {}
    for key, row in restored['judgments'].items():
        if not isinstance(row, dict):
            raise ValueError('judgment_schema')
        selected = row.get('evidence')
        if not isinstance(selected, list) or any(not isinstance(v, str) or v not in references for v in selected):
            raise ValueError('unknown_evidence_reference')
        if len(selected) != len(set(selected)):
            raise ValueError('duplicate_evidence_reference')
        row['evidence'] = [dict(block_id=references[v]['id'], quote=references[v]['text']) for v in selected]
        if canonical_views is not None:
            addresses[key] = [exact_evidence([dict(block_id=canonical_views[v]['id'], quote=canonical_views[v]['text'])],
                                             [canonical_views[v]])[0] for v in selected]
    previous.parse(json.dumps(restored, ensure_ascii=False)[1:], cases)
    return dict(selected=answer, restored=restored, canonical_evidence=addresses,
                canonical_address_verified=canonical_views is not None)


def selfcheck():
    raw = dict(Head='대상이 미방문 시 구비서류', Relation='포함한다', Tail='서류', Entity=['대상'])
    before = deepcopy(raw)
    proposal = dict(status='constructed', field='Head', quote='미방문 시 ', reason='적용 상황 선택')
    made = construct(raw, proposal)
    assert made['raw'] == dict(raw, Head='대상이 구비서류') and raw == before
    assert made['before_span'] == [4, 10] and made['after_span'] == [4, 4]
    unsupported = dict(status='unsupported', field=None, quote='', reason='조건 구절 미확정')
    assert construct(raw, unsupported)['status'] == 'unsupported'
    for candidate, value in [(dict(raw, Head='aaa'), dict(proposal, quote='aa')),
                              (raw, dict(proposal, quote=raw['Head'])),
                              (raw, dict(proposal, field='Entity')), (raw, dict(proposal, quote='없는 구절')),
                              (raw, dict(unsupported, field='Head'))]:
        try: construct(candidate, value)
        except ValueError: pass
        else: raise AssertionError('Invalid construction accepted')
    text = '첫째\n둘째'
    case = dict(id='test', raw=raw, blocks=[dict(id='b1', text=text)], source_parents=[])
    canonical = dict(e1=dict(id='actual', text=text, source_version_id='version', parse_run_id='parse', span=[40, 45]))
    judgment = dict(label='1', error_fields=[], error_spans=[], evidence=['e1'], reason='지지')
    for size in [1, 2, 3]:
        cases = {key: case for key in ['X', 'Y', 'Z'][:size]}
        answer = dict(differences=[], judgments={key: deepcopy(judgment) for key in cases})
        parsed = parse(json.dumps(answer)[1:], cases, canonical)
        assert parsed['restored']['judgments']['X']['evidence'] == [dict(block_id='b1', quote=text)]
        assert parsed['canonical_evidence']['X'][0]['start_char'] == 40
        payload = json.loads(prompt(cases).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
        assert payload['context']['blocks'][0]['text'] == text and payload['candidates']['X'] == raw
    for value in [['outside'], ['e1', 'e1'], [dict(block_id='b1', quote='첫째 둘째')]]:
        bad = dict(differences=[], judgments=dict(X=dict(judgment, evidence=value)))
        try: parse(json.dumps(bad)[1:], dict(X=case))
        except ValueError: pass
        else: raise AssertionError('Invalid evidence accepted')
    bad = dict(differences=[dict(X=dict(field='Head',quote='미방문 시'),Y=dict(field='Head',quote='미방문 시'),
                                 dimensions='condition',reason='조건')], judgments=dict(X=judgment,Y=judgment))
    try: parse(json.dumps(bad)[1:], dict(X=case,Y=case))
    except ValueError: pass
    else: raise AssertionError('String dimensions accepted')
    payload = json.loads(construction_prompt(dict(raw, source='secret', gold='1')).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
    assert payload == dict(raw={k: raw[k] for k in ('Head', 'Tail')})
    print('Single deletion, unchanged raw, unsupported retention, addressed restoration, dimensions array and input isolation passed')


if __name__ == '__main__':
    selfcheck()

"""Research-only verbatim source qualifier insertion; meaning remains unverified."""
from copy import deepcopy
import json
import re

import compare_business_condition_contrast as previous

INSTRUCTION = '''전체 원문·부모 문맥과 후보 raw만 읽는다. 후보의 정답·오류 라벨을 판단하거나 올바른 정정문을 작성하는 과제가 아니다.
같은 행위/관계의 적용 범위를 제한하는 원문 구절 한 곳과 그 구절을 삽입할 후보 위치 한 곳을 선택하여 최소 범위 차이의 시험 상대를 구성한다. 원문에 있는 구절이라도 후보에 맞는 적용 관계라는 보장은 없다.
원본의 명시 주체·행위·대상·수량·기간·목록·기존 조건을 삭제하거나 바꾸지 않는다. 적용 범위 제한 외 다른 주장을 추가하지 않는다. 새로운 독립 주체/행위/조건 목록을 붙이지 않는다. 상대가 지지된다고 가정하지 않는다.
서버는 source.quote와 공백 한 개만 field의 유일한 anchor 앞에 삽입한다. source.quote는 한 블록의 정확한 연속 부분문자열이며 앞뒤 공백/줄바꿈과 미완성 괄호가 없어야 한다. anchor는 Event/Head/Tail의 유일한 실제 연속 문자열이고 시작 또는 공백/절 경계 뒤에서 시작한다.
그대로 넣어서 문법이 성립하는 조건 구절 또는 같은 대상의 범위 수식만 고른다. 조사·어미·접속어를 바꾸거나 후보 문장을 다시 쓰지 않는다. 직접 삽입만으로 문법/한 범위 차이가 불가능하거나 제한을 특정할 수 없으면 unsupported다. 기대 정답에 맞는 상대를 고르지 않는다.
출력 JSON 하나: {"status":"constructed 또는 unsupported","source":{"evidence_ref":"e1", "quote":"원문 구절"} 또는 null,"field":"Event/Head/Tail 또는 null","anchor":"실제 후보 구절 또는 빈 문자열","reason":"선택 또는 지원 불가 이유"}.
source.quote는 선택한 블록 안에서 정확히 한 번 있어야 한다. 서버가 실제 문자 위치를 복원한다. unsupported이면 source=null, field=null, anchor=""이다.'''


def prompt(case):
    source = previous.addressed_cases(dict(X=case))['X']
    return previous.chat(INSTRUCTION, dict(context={k: v for k, v in source.items() if k not in {'id', 'raw'}}, raw=source['raw']))


def balanced(text):
    stack, pairs = [], {')': '(', ']': '[', '}': '{'}
    for char in text:
        if char in '([{':
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def construct(case, proposal, canonical_views):
    from app.knowledge.business_run import exact_evidence
    if not isinstance(proposal, dict) or set(proposal) != {'status', 'source', 'field', 'anchor', 'reason'}:
        raise ValueError('construction_schema')
    if not isinstance(proposal['reason'], str) or not proposal['reason'].strip():
        raise ValueError('construction_reason')
    if proposal['status'] == 'unsupported':
        if proposal['source'] is not None or proposal['field'] is not None or proposal['anchor'] != '':
            raise ValueError('unsupported_with_change')
        return dict(status='unsupported', proposal=deepcopy(proposal), semantic_validity='not_assessed')
    ref, field, anchor = proposal['source'], proposal['field'], proposal['anchor']
    if proposal['status'] != 'constructed' or field not in previous.FIELDS or not isinstance(ref, dict) or set(ref) != {'evidence_ref', 'quote'}:
        raise ValueError('construction_selection')
    blocks = {f'e{n + 1}': b for n, b in enumerate(case['blocks'])}
    ident, quote = ref['evidence_ref'], ref['quote']
    if not isinstance(ident, str) or ident not in blocks or not isinstance(quote, str) or not quote.strip():
        raise ValueError('source_address')
    block = blocks[ident]
    occurrences = [m.start() for m in re.finditer('(?=' + re.escape(quote) + ')', block['text'])]
    if len(occurrences) != 1:
        raise ValueError('source_quote_ambiguous' if occurrences else 'source_quote_missing')
    start, end = occurrences[0], occurrences[0] + len(quote)
    if quote != quote.strip() or any(c in quote for c in '\n\r\t') or not balanced(quote):
        raise ValueError('source_insertion_syntax')
    text = case['raw'].get(field)
    if not isinstance(text, str) or not isinstance(anchor, str) or not anchor.strip():
        raise ValueError('candidate_anchor')
    positions = [m.start() for m in re.finditer('(?=' + re.escape(anchor) + ')', text)]
    if len(positions) != 1:
        raise ValueError('candidate_address')
    position = positions[0]
    if position and not (text[position - 1].isspace() or text[position - 1] in ',;:('):
        raise ValueError('candidate_insertion_boundary')
    canonical = canonical_views[ident]
    if canonical['text'] != block['text']:
        raise ValueError('canonical_source_mismatch')
    evidence = exact_evidence([dict(block_id=canonical['id'], quote=quote, start_char=start, end_char=end)], [canonical])[0]
    changed, inserted = deepcopy(case['raw']), quote + ' '
    changed[field] = text[:position] + inserted + text[position:]
    assert changed[field][:position] + changed[field][position + len(inserted):] == text
    assert {k: v for k, v in changed.items() if k != field} == {k: v for k, v in case['raw'].items() if k != field}
    return dict(status='constructed_unverified', raw=changed, field=field, before_span=[position, position],
                after_span=[position, position + len(inserted)], inserted_text=inserted,
                source_evidence=evidence, proposal=deepcopy(proposal), semantic_validity='unverified')


def selfcheck():
    case = dict(id='test',raw=dict(Event='신청인은 서류를 제출한다.',Entity=['신청인','서류']),
                blocks=[dict(id='b1',text='같은 조건일 때 같은 행동이다')],source_parents=[])
    views = dict(e1=dict(id='actual',text=case['blocks'][0]['text'],source_version_id='v',parse_run_id='p'))
    proposal = dict(status='constructed',source=dict(evidence_ref='e1',quote='같은 조건일 때'),field='Event',anchor=case['raw']['Event'],reason='주소 검사 전용')
    made = construct(case,proposal,views)
    assert made['raw'] == dict(case['raw'],Event='같은 조건일 때 신청인은 서류를 제출한다.')
    assert made['source_evidence']['start_char'] == 0 and made['source_evidence']['end_char'] == len(proposal['source']['quote'])
    assert case['raw']['Event'] == '신청인은 서류를 제출한다.'
    for ref in [dict(proposal['source'],quote='만든 구절'),dict(proposal['source'],quote=''),dict(proposal['source'],evidence_ref='outside')]:
        try: construct(case,dict(proposal,source=ref),views)
        except ValueError: pass
        else: raise AssertionError('Invalid source accepted')
    for changed in [dict(proposal,anchor='출한다.'),dict(proposal,field='Entity'),dict(proposal,anchor='없는 구절')]:
        try: construct(case,changed,views)
        except ValueError: pass
        else: raise AssertionError('Invalid candidate insertion accepted')
    repeated = deepcopy(case)
    repeated['blocks'][0]['text'] = '같은 조건일 때 / 같은 조건일 때'
    repeated_views = dict(e1=dict(views['e1'],text=repeated['blocks'][0]['text']))
    try: construct(repeated,proposal,repeated_views)
    except ValueError as error: assert str(error)=='source_quote_ambiguous'
    else: raise AssertionError('Repeated source quote accepted')
    assert construct(case,dict(status='unsupported',source=None,field=None,anchor='',reason='지원 불가'),views)['status']=='unsupported'
    payload=json.loads(prompt(case).split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
    assert payload['raw']==case['raw'] and 'id' not in payload['context']
    print('Source offsets, one insertion, unchanged original, boundaries and input isolation checked; meaning unverified')


if __name__ == '__main__':
    selfcheck()

"""Required reviewed content survives answer selection; this is not a semantic judge."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.knowledge import business_run, business_use as use
from app.tests.unit.test_knowledge_business_semantic_edit import reviewed


def test_required_scope_comes_from_snapshot_checks_not_application_explanations():
    text = '대리 방문 때 서류를 구비한다.'
    block = dict(id='b', source_version_id='v', parse_run_id='p', text=text)
    meanings = [dict(reviewed(key), evidence=[dict(block_id='b', quote=text)],
                     required_for_requirement=True, requirement_link={'reason': '필수라는 자유 설명'})
                for key in ['required', 'background']]
    snapshot = dict(blocks=[block], assessments={'r':dict(id='a', source=dict(meanings=meanings),
        representation=dict(source_checks=[dict(meaning_key=key, required_for_requirement=key=='required')
                                          for key in ['required', 'background']],
                            checks=[dict(meaning_key=m['key'], status='represented', claim_ids=['c'],
                                         claim_support={'c':'supported'}) for m in meanings]))})
    before = deepcopy(snapshot)
    assert use.required_answer_meaning_keys(snapshot, ['r']) == {'r':['required']}
    assert use.required_answer_meaning_keys(snapshot, []) == {}
    assert snapshot == before


@pytest.mark.parametrize('omission', ['empty_selection', 'missing_item', 'duplicate_item', 'qa_failure'])
def test_unselected_required_bundle_is_preserved_without_inventing_item_assignment(monkeypatch, omission):
    required = dict(reviewed('needed'), required_for_requirement=True,
                    statement='대리 방문 때 서류를 구비한다. 법인 서류는 생략할 수 없다.', exceptions=['법인'])
    required['field_judgments']['period'] = dict(status='unknown', statement_affected=False, reason='기간은 미확인')
    background = dict(reviewed('background'), statement='별도 업무의 안내.', required_for_requirement=False)
    blocked = dict(reviewed('blocked'), statement='미검토 추가 조건.', required_for_requirement=True,
                   complete_claim_bundle=False)
    other = dict(reviewed('other'), requirement_id='other', statement='다른 요구의 사실.', required_for_requirement=True)
    item = dict(item_id='i', selected=[], unconfirmed=['요청 조건과 담당 업무 사이의 연결을 확인해야 한다.'])
    response = None if omission=='qa_failure' else dict(
        items=[] if omission=='missing_item' else [item] * (2 if omission=='duplicate_item' else 1))
    run = dict(reviewed_meanings=[required, background, blocked, other],
               required_answer_meaning_keys={'r':['needed', 'blocked'], 'other':['other']},
               answer_items=[dict(id='i', requirement_id='r', request_quote='서류와 기관')])
    before = deepcopy(run['reviewed_meanings'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: response)
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='서류와 기관'), [])
    assert required['statement'] in answer['answer'] and '조건: 대리 방문' in answer['answer']
    assert '예외: 법인' in answer['answer'] and '기간:' not in answer['answer']
    assert all(m['statement'] not in answer['answer'] for m in [background, blocked, other])
    assert answer['citations'] == ['c']
    assert run['answer_meaning_selection']['unassigned_required'] == ['m1']
    assert 'r: required_meaning_not_assigned:needed' in run['answer_item_errors']
    assert run['reviewed_meanings'] == before


def test_selected_required_meaning_is_not_repeated_in_preservation_section(monkeypatch):
    m = dict(reviewed(), required_for_requirement=True)
    run = dict(reviewed_meanings=[m], required_answer_meaning_keys={'r':['m']},
               answer_items=[dict(id='i', requirement_id='r', request_quote='서류')])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(items=[dict(item_id='i',
        selected=[dict(meaning_ref='m1', use='direct_fact')], unconfirmed=[])]))
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='서류'), [])
    assert answer['answer'].count(m['statement']) == 1
    assert not run['answer_meaning_selection']['unassigned_required']
    assert not run['answer_item_errors']


@pytest.mark.parametrize('selected', [[], ['m1'], ['m2']])
def test_required_meaning_keeps_its_unselected_nonessential_premise(monkeypatch, selected):
    m = dict(reviewed('required'), statement='연결된 전제 아래 서류를 구비한다.', premise_keys=['premise'])
    p = dict(reviewed('premise'), statement='대리 방문의 경우에 적용된다.', claim_ids=['p'],
             required_claim_ids=['p'], claim_support={'p':'supported'}, premise_keys=['prerequisite'])
    prerequisite = dict(reviewed('prerequisite'), statement='등록된 대리 신청을 전제로 한다.', claim_ids=['q'],
                        required_claim_ids=['q'], claim_support={'q':'supported'})
    unrelated = dict(reviewed('background'), statement='독립한 별도 업무.')
    run = dict(reviewed_meanings=[m,p,prerequisite,unrelated], required_answer_meaning_keys={'r':['required']},
               answer_items=[dict(id='i', requirement_id='r', request_quote='서류')])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(items=[dict(item_id='i',
        selected=[dict(meaning_ref=ref, use='direct_fact') for ref in selected], unconfirmed=[])]))
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='서류'), [])
    assert answer['answer'].count(m['statement']) == answer['answer'].count(p['statement']) == 1
    assert answer['answer'].count(prerequisite['statement']) == 1
    assert unrelated['statement'] not in answer['answer']
    assert set(answer['citations']) == {'c','p','q'}
    assert set(run['answer_meaning_selection']['unassigned_required']) == {'m1','m2','m3'} - set(selected)
    assert run['answer_item_errors']


def test_absent_premise_does_not_make_required_meaning_renderable(monkeypatch):
    m = dict(reviewed('required'), premise_keys=['missing'])
    run = dict(reviewed_meanings=[m], required_answer_meaning_keys={'r':['required']},
               answer_items=[dict(id='i', requirement_id='r', request_quote='서류')])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No complete premise bundle'))
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='서류'), [])
    assert m['statement'] not in answer['answer'] and answer['citations'] == []
    assert run['answer_meaning_selection']['excluded'][0]['reason'] == 'missing_required_premise'

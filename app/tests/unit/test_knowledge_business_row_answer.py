"""Literal row delivery is separate from semantic review and completeness."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.knowledge import business_run, business_use as use
from app.knowledge.service import encode


@pytest.fixture
def snapshot():
    # Synthetic contract fixture, not a factual bus observation.
    fields = dict(NODE_ID=7, ARS_ID='00008', X좌표=127.1, Y좌표=37.2, 정류소명='대조 정차')
    block = dict(id='row', source_version_id='v2', parse_run_id='parse', text=encode(fields),
                 locator=dict(format='json', json_pointer='/2', fields=fields))
    ref = dict(block_id='row', source_version_id='v2', parse_run_id='parse', start_char=0,
               end_char=len(block['text']), quote=block['text'], precision='exact')
    claim = dict(id='c', role='structured_row', construction_method='direct_tabular_row', review_status='accepted',
                 source_version_ids=['v2'], raw=dict(Event=block['text'], fields=fields), evidence=[ref])
    meaning = dict(key='node', source_status='supported', availability='provided', evidence=[ref])
    assessment = dict(status='partial', source=dict(meanings=[meaning], completeness='partial', gaps=[]),
        representation=dict(source_completeness='unknown', checks=[dict(meaning_key='node', status='represented',
            claim_ids=['c'], claim_support={'c':'supported'})]))
    return dict(claims=[claim], blocks=[block], assessments={'r':assessment},
                source_versions={'v2':dict(filename='after.json', dates=[dict(role='file_snapshot', value='2025-06-24')])})


@pytest.mark.parametrize('question,wanted', [
    ('NODE_ID와 ARS_ID는?', ['NODE_ID', 'ARS_ID']),
    ('ARS_ID와 좌표는?', ['ARS_ID', 'X좌표', 'Y좌표']),
    ('좌표는?', ['X좌표', 'Y좌표']),
])
def test_missing_meaning_field_reaches_selection_and_only_selected_values_render(snapshot, monkeypatch, question, wanted):
    before = deepcopy(snapshot)
    fields = use.exact_row_answer_fields(snapshot, {'c'}, ['r'])
    assert {f['field_name'] for f in fields} == set(snapshot['claims'][0]['raw']['fields'])
    assert all(f['judgment_origin']['semantic_review'] is False for f in fields)
    limit = dict(requirement_id='r', period='최신 제공 스냅샷', status='partial', source_completeness='partial',
                 synthesis_source_completeness='unknown', gaps=['최신성은 확인되지 않았다.'])
    run = dict(reviewed_meanings=[], exact_row_answer_fields=fields, answer_assessment_limitations=[limit],
               answer_items=[dict(id='i', requirement_id='r', request_quote=question)])
    def choose(_service, _run, _stage, prompt, context, schema):
        supplied = context['reviewed_meanings']
        assert {m['field_name'] for m in supplied.values()} == set(snapshot['claims'][0]['raw']['fields'])
        assert context['assessment_limitations'] == [limit]
        for m in supplied.values():
            assert 'row_fields' not in m and 'evidence' not in m
            source = context['row_contexts'][m['row_context_id']]
            assert source['source_version_id'] == 'v2' and source['evidence'][0] == snapshot['claims'][0]['evidence'][0]
            assert source['row_fields'] == snapshot['claims'][0]['raw']['fields']
        assert len(context['row_contexts']) == 1
        return schema.model_validate(dict(items=[dict(item_id='i', unconfirmed=[], selected=[
            dict(meaning_ref=ref, use='direct_fact') for ref,m in supplied.items() if m['field_name'] in wanted])])).model_dump()
    monkeypatch.setattr(business_run, 'json_call', choose)
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question=question), [])
    for field in wanted:
        assert field + ': ' + encode(snapshot['claims'][0]['raw']['fields'][field]) in answer['answer']
    assert '대조 정차' not in answer['answer']
    assert 'after.json' in answer['answer'] and '2025-06-24' in answer['answer'] and 'v2' not in answer['answer']
    assert '전체 충족은 아직 확인되지' in answer['answer'] and 'unknown' not in answer['answer']
    assert any('전체 충족은 아직 확인되지' in value for value in answer['limitations'])
    assert any(limit['gaps'][0] in value for value in answer['limitations'])
    assert '확정 사실 아님' in answer['answer']
    assert answer['citations'] == ['c'] and not run['answer_item_errors']
    assert snapshot == before


@pytest.mark.parametrize('difference', ['unselected', 'unrequested_requirement', 'unapproved', 'non_tabular',
    'changed_value', 'other_version', 'unreviewed', 'source_error', 'superseded'])
def test_literal_fields_require_current_approved_source_row_and_review_link(snapshot, difference):
    selected, requirements = {'c'}, ['r']
    claim = snapshot['claims'][0]
    if difference == 'unselected': selected = set()
    if difference == 'unrequested_requirement': requirements = ['other']
    if difference == 'unapproved': claim['review_status'] = 'proposed'
    if difference == 'non_tabular': claim['role'] = 'event_entity'
    if difference == 'changed_value': claim['raw']['fields']['ARS_ID'] = 'different'
    if difference == 'other_version': snapshot['assessments']['r']['source']['meanings'][0]['evidence'] = [dict(claim['evidence'][0], source_version_id='old')]
    if difference == 'unreviewed': snapshot['assessments']['r']['representation']['checks'][0]['claim_support']['c'] = 'unknown'
    if difference == 'source_error': snapshot['assessments']['r']['source']['meanings'][0]['record_error'] = 'invalid quote'
    if difference == 'superseded': claim['superseded_by'] = ['new']
    assert use.exact_row_answer_fields(snapshot, selected, requirements) == []


def test_exact_cell_as_premise_keeps_missing_link(snapshot, monkeypatch):
    run = dict(reviewed_meanings=[], exact_row_answer_fields=use.exact_row_answer_fields(snapshot, {'c'}, ['r']),
               answer_items=[dict(id='i', requirement_id='r', request_quote='연결 결론')])
    monkeypatch.setattr(business_run, 'json_call', lambda *args, **kwargs: dict(items=[dict(item_id='i',
        selected=[dict(meaning_ref='f1', use='premise_only')], unconfirmed=['행값과 요청 결론의 연결 근거가 없다.'])]))
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='연결 결론'), [])
    assert '결론 연결 미확인' in answer['answer'] and '연결 근거가 없다' in answer['answer']
    assert not run['answer_item_errors']
    monkeypatch.setattr(business_run, 'json_call', lambda *args, **kwargs: dict(items=[dict(item_id='i',
        selected=[dict(meaning_ref='f1', use='premise_only')], unconfirmed=[])]))
    use.reviewed_item_answer(None, run, SimpleNamespace(question='연결 결론'), [])
    assert run['answer_item_errors'] == ['i: inference_link_not_specified']

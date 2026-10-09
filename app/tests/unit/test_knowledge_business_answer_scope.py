from types import SimpleNamespace

from app.knowledge import business_run, business_use as use
from app.tests.unit.test_knowledge_business_row_answer import snapshot


def test_explicit_row_field_omission_is_selection_gap_not_source_absence(monkeypatch, snapshot):
    run = dict(reviewed_meanings=[], exact_row_answer_fields=use.exact_row_answer_fields(snapshot, {'c'}, ['r']),
        answer_items=[dict(id='i', requirement_id='r', request_quote='NODE_ID와 ARS_ID 및 X 좌표')])
    def answer(_s, _r, _stage, prompt, context, schema):
        assert context['requested_row_fields']['i'] == ['NODE_ID', 'ARS_ID', 'X좌표']
        return dict(items=[dict(item_id='i', selected=[dict(meaning_ref='f1', use='direct_fact')], unconfirmed=[])])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = use.reviewed_item_answer(None, run, SimpleNamespace(question='NODE_ID와 ARS_ID 및 X 좌표'), [])
    assert 'i: requested_row_field_not_selected:ARS_ID' in run['answer_item_errors']
    assert '요청한 필드가 답변 근거 선택에서 빠졌습니다' in result['answer']
    assert '자료가 없습니다' not in result['answer']

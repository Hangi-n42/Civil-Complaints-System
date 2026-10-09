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


@pytest.mark.parametrize('statuses', [[], ['resolved'], ['not_required'], ['resolved', 'resolved'],
    ['resolved', 'unresolved'], ['unknown'], ['required_gap'], ['source_error'], ['claim_error'], ['unresolved']])
def test_current_answer_notes_follow_unique_resolution_without_erasing_history(snapshot, monkeypatch, statuses):
    source = snapshot['assessments']['r']['source']
    source.update(findings=[dict(id='finding', text='이전 조사 이의')],
                  finding_resolutions=[dict(finding_id='finding', status=s, reason='과거 판정 설명') for s in statuses])
    before = deepcopy(snapshot)
    notes = use.unresolved_finding_notes(source)
    active = statuses not in (['resolved'], ['not_required'])
    assert notes == (['이전 조사 이의'] if active else [])
    limit = dict(requirement_id='r', period='', status='partial', gaps=['local_source_inspection_scope_mismatch'],
                 review_notes=notes, finding_resolutions=deepcopy(source['finding_resolutions']))
    run = dict(reviewed_meanings=[], exact_row_answer_fields=use.exact_row_answer_fields(snapshot, {'c'}, ['r']),
        answer_assessment_limitations=[limit], answer_items=[dict(id='i', requirement_id='r', request_quote='NODE_ID')])
    def choose(service, active_run, stage, prompt, context, schema):
        assert context['assessment_limitations'][0]['review_notes'] == notes
        ref = next(k for k, m in context['reviewed_meanings'].items() if m.get('field_name') == 'NODE_ID')
        return dict(items=[dict(item_id='i', selected=[dict(meaning_ref=ref, use='direct_fact')], unconfirmed=[])])
    monkeypatch.setattr(business_run, 'json_call', choose)
    answer = use.reviewed_item_answer(None, run, SimpleNamespace(question='NODE_ID'), [])
    assert ('이전 조사 이의' in answer['answer']) == active
    assert 'local_source_inspection_scope_mismatch' in answer['answer'] and '전체 충족은 아직 확인되지' in answer['answer']
    assert snapshot == before


@pytest.mark.parametrize('mode,contract', [
    ('synthesis', None),
    ('synthesis', 'requirement-local-review-v8-owned-errors'),
    ('reviewed_items', 'requirement-local-review-v13-source-application'),
    ('synthesis', 'requirement-local-review-v9-answer-roots-experimental'),
    ('reviewed_items', 'requirement-local-review-v10-selection-experimental'),
    ('source_quotes', 'requirement-local-review-v8-owned-errors'),
    ('items', 'requirement-local-review-v8-owned-errors'),
])
def test_query_exposes_answer_boundary_separately_from_source_review_history(snapshot, tmp_path, monkeypatch, mode, contract):
    from app.knowledge.business_models import BusinessQuery
    from app.knowledge.service import KnowledgeService
    from app.knowledge import graph_retrieval
    service = KnowledgeService(tmp_path / 'boundary.db')
    requirement = dict(id='r', revision=1, status='ready', question='NODE_ID는?', criterion='NODE_ID')
    snapshot.update(id='s', kind='source_graph', run_id='origin', requirements=[requirement], concepts=[])
    snapshot['assessments']['r']['id'] = 'assessment'
    original = dict(id='origin', kind='business', status='succeeded', units=[],
        recipe=dict(options=dict(context_tokens=16384, review_tokens=4096)), model_identity={})
    if contract is not None:
        original['recipe']['review_contract'] = contract
    # The snapshot's assessment provenance need not be the source run recipe.
    snapshot['assessments']['r']['source']['review_contract'] = 'older-assessment-contract'
    before = deepcopy(snapshot)
    calls = []
    def respond(_service, run, stage, instruction, context, schema, **kwargs):
        calls.append(mode)
        if mode == 'reviewed_items':
            ref = next(k for k, value in context['reviewed_meanings'].items() if value.get('field_name') == 'NODE_ID')
            return dict(items=[dict(item_id='i', selected=[dict(meaning_ref=ref, use='direct_fact')], unconfirmed=[])])
        if mode == 'source_quotes':
            return dict(items=[dict(question_quote='NODE_ID', coverage='direct', evidence_refs=['t1'], missing_question_quote='')], choice=None)
        if mode == 'items':
            return dict(items=[dict(item_id='i', conclusions=[dict(statement='NODE_ID는 7이다.', kind='direct',
                conditions=[], exceptions=[], support=[dict(evidence_ref='t1', quote='NODE_ID')], reasoning='')], missing=[])], choice=None)
        return dict(answer='NODE_ID는 7이다.', citations=['c'], choice=None, limitations=[])
    monkeypatch.setattr(business_run, 'json_call', respond)
    items = [dict(id='i', requirement_id='r', requirement_revision=1, field='question', request_quote='NODE_ID')]
    request = BusinessQuery(snapshot_id='s', question='NODE_ID는?', requirement_ids=['r'], retrieval='bm25',
        answer_mode=mode, answer_items=items if mode in {'items', 'reviewed_items'} else [])
    try:
        with service.repository.connect() as db:
            for table, value in [('runs', original), ('snapshots', snapshot), ('requirements', requirement)]:
                db.execute(f'INSERT INTO {table} VALUES(?,?)', (value['id'], encode(value)))
        result = use.query(service, request)
        assert result['status'] == 'answered' and calls == [mode]
        boundary = result['execution_boundary']
        assert boundary['answer_mode'] == mode
        assert boundary['unadopted_answer_mode'] is (mode in {'source_quotes', 'items'})
        assert boundary['source_review_run_id'] == 'origin'
        assert boundary['source_run_review_contract'] == contract
        assert boundary['source_run_review_experimental'] is (contract is not None and 'experimental' in contract)
        assert boundary['review_provenance_scope'] == 'source_run_recipe_not_all_snapshot_assessments'
        assert '의미 정확성이나 요구 전체 충족을 보증하지 않는다' in boundary['status_semantics']
        saved = service.run(result['run_id'])
        assert saved['execution_boundary'] == boundary and boundary['answer_contract'] == saved['answer_contract']
        assert ('experimental' in boundary['answer_contract']) is (mode in {'source_quotes', 'items'})
        def failed_retrieval(*args):
            raise ValueError('synthetic retrieval failure')
        monkeypatch.setattr(graph_retrieval, 'retrieve', failed_retrieval)
        failed = use.query(service, request.model_copy(update=dict(retrieval='hipporag2')))
        assert failed['status'] == 'retrieval_failed' and calls == [mode]
        assert failed['execution_boundary'] == dict(boundary, answer_contract=None)
        assert service.run(failed['run_id'])['execution_boundary'] == failed['execution_boundary']
        from app.knowledge.discovery_profile import FrozenIndex
        monkeypatch.setattr(FrozenIndex, 'search', lambda *args, **kwargs: [])
        empty = use.query(service, request)
        assert empty['status'] == 'unverified' and empty['qa_model_called'] is False and calls == [mode]
        assert empty['execution_boundary'] == dict(boundary, answer_contract=None)
        assert 'execution_boundary' not in service.run('origin')
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'origin') == original
            assert service.repository.get(db, 'snapshots', 's') == before
    finally:
        service.shutdown()

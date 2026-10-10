"""Connection review receipts cannot approve stale or unsupported compound claims."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import create_model, Field

from app.knowledge import business_review as review, business_run, business_use
from app.knowledge.business_models import ConjunctionReview, RequirementSynthesisCheck
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_scope import block


def setup():
    run = local_run()
    run['recipe']['review_contract'] = review.CONTRACT
    run['requirements'][0].update(question='어느 기관이 신청을 접수하는가?', criterion='접수 기관 확인')
    run['answer_items'] = [dict(id='agency', requirement_id='r', requirement_revision=1,
        field='question', request_quote=run['requirements'][0]['question'])]
    source = dict(meanings=[meaning('m'), dict(meaning('background'), required_for_requirement=False)],
        review_contract=review.CONTRACT, examined_block_ids=['body'], completeness='complete', gaps=[],
        conjunctions=['기관은 신청을 접수한다.'], meaning_conjunctions=[], findings=[])
    review.conjunction_candidates(None, run, run['requirements'][0], source)
    return run, source


def connection(run, source, status='supported', background=False, **values):
    return dict(conjunction_id=source['conjunction_records'][0]['id'], original_source_status=status,
        source_status=status, statement=source['conjunction_records'][0]['text'], meaning_keys=['m'],
        claim_ids=[run['claims'][0]['id']], evidence=meaning('m')['evidence'],
        requirement_link=dict(requested_fact='' if background else '접수 기관',
            applicability='outside_scope' if background else 'applicable',
            contribution='background' if background else 'direct_answer',
            requirement_quote='' if background else run['requirements'][0]['question'], reason='공개 질문과 대조'),
        item_ids=[] if background else ['agency'],
        reason='제공 구간과 대조', **values)


def resolve(run, source, rows):
    result = judgments(['m'], ids=[run['claims'][0]['id']])
    result['checks'][0]['claim_support'] = {run['claims'][0]['id']: 'supported'}
    errors = review.resolve_conjunctions(run, run['requirements'][0], source, result, rows,
        run['blocks'], run['claims'], 'join-unit')
    return result, errors


@pytest.mark.parametrize('status', ['unsupported', 'unknown', 'refuted'])
def test_required_connection_failure_keeps_independent_source_and_approved_claim(status):
    run, source = setup(); original = deepcopy(source['meanings'])
    result, errors = resolve(run, source, [connection(run, source, status)])
    assert not errors and not result['satisfied'] and not result['conjunctions_satisfied']
    assert source['meanings'] == original and source['conjunctions'] == []
    assert result['meaning_challenges'] == [] and result['source_challenges'] == []
    assessment = dict(requirement_id='r', source=source, representation=result, errors=[], issues=[],
        input_fingerprint=business_run.assessment_fingerprint(run, run['requirements'][0], source))
    run['assessments'] = [assessment]
    assert business_use.eligibility(run) == ({run['claims'][0]['id']}, {})
    assert source['conjunction_records'][0]['action'] == ('withdrawn' if status == 'refuted' else 'unconfirmed')


def test_unneeded_connection_is_not_supported_or_a_new_mandatory_failure():
    run, source = setup()
    result, errors = resolve(run, source, [connection(run, source, 'unsupported', background=True)])
    assert not errors and result['satisfied'] and source['conjunctions'] == []
    assert source['conjunction_history'][0]['original_conjunctions'] == ['기관은 신청을 접수한다.']
    run, source = setup(); row = connection(run, source, 'unknown', background=True)
    row['requirement_link']['applicability'] = 'unresolved'
    assert resolve(run, source, [row])[0]['satisfied']


def test_missing_or_outside_review_cannot_be_covered_by_global_true():
    for rows_kind in ['missing', 'duplicate', 'unprovided_meaning']:
        run, source = setup(); row = connection(run, source)
        rows = [] if rows_kind == 'missing' else [row, deepcopy(row)] if rows_kind == 'duplicate' else [dict(row, meaning_keys=['background'])]
        result, errors = resolve(run, source, rows)
        assert errors and not result['satisfied'] and source['conjunctions'] == []
        assert source['conjunction_history'][-1]['output'] == rows


def test_correction_preserves_original_verdict_and_invalidates_only_changed_dependency():
    run, source = setup(); row = connection(run, source)
    row.update(original_source_status='unsupported', statement='신청을 접수하는 주체는 기관이다.')
    result, errors = resolve(run, source, [row])
    assert not errors and source['conjunction_records'][0]['action'] == 'corrected'
    assert source['conjunction_records'][0]['review']['original_source_status'] == 'unsupported'
    assert source['conjunctions'] == [row['statement']]
    assert source['conjunction_history'][-1]['previous']['text'] == '기관은 신청을 접수한다.'
    run['blocks'].append(dict(block('unrelated', '다른 문서의 무관 구간', path='section:2'), source_id='other'))
    run['claims'][1]['raw']['Tail'] = '무관 후보'
    source['meanings'][1]['statement'] = '무관 의미의 변경'
    review.refresh_conjunctions(run, run['requirements'][0], source)
    assert source['conjunction_records'][0]['review'] is not None
    source['meanings'][0]['statement'] = '관련 의미의 변경'
    review.refresh_conjunctions(run, run['requirements'][0], source)
    assert source['conjunction_records'][0]['review'] is None and source['conjunctions'] == []


def test_conjunction_evidence_and_full_fields_survive_final_request_schema(monkeypatch):
    run, source = setup(); row = connection(run, source)
    output_type = create_model('ConjunctionJoinTest', __base__=RequirementSynthesisCheck,
        conjunction_reviews=(list[ConjunctionReview], Field(min_length=1, max_length=1)))
    output = dict(checks=[], dependencies=[], source_challenges=[], meaning_challenges=[],
        preservation_checks=[], satisfied=True, conjunctions_satisfied=True, reason='전체',
        source_completeness='complete', unselected_source_required=False, finding_resolutions=[],
        conjunction_reviews=[dict(row, claim_ids=['c1'], evidence=['e1'])])
    def answer(_service, current, _stage, _messages, schema, **kwargs):
        assert 'conjunction_reviews' in schema['required']
        assert schema['properties']['conjunction_reviews']['minItems'] == schema['properties']['conjunction_reviews']['maxItems'] == 1
        assert 'original_source_status' in str(schema) and 'requirement_link' in str(schema)
        current['units'].append(dict(id='join', status='succeeded'))
        return dict(parsed=output)
    monkeypatch.setattr(business_run, 'call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    restored = business_run.json_call(None, run, 'requirement_representation', '',
        dict(blocks=run['blocks'], claims=run['claims']), output_type)['conjunction_reviews'][0]
    assert restored['claim_ids'] == row['claim_ids']
    assert restored['evidence'][0]['quote'] == run['blocks'][0]['text']
    assert restored['original_source_status'] == 'supported'


@pytest.mark.parametrize('claim_location', [True, False])
def test_qa_carries_connection_provenance_and_cannot_upgrade_source_only_support(monkeypatch, claim_location):
    run, source = setup(); row = connection(run, source)
    if not claim_location:
        row['claim_ids'] = []
    result, errors = resolve(run, source, [row]); assert not errors
    assert result['satisfied'] == claim_location
    assert source['completeness'] == 'complete'
    snapshot = dict(assessments={'r': dict(id='assessment', source=source, representation=result)}, blocks=run['blocks'])
    run['reviewed_meanings'] = business_use.reviewed_answer_meanings(snapshot, {run['claims'][0]['id']}, ['r'])
    run['reviewed_connections'] = business_use.reviewed_answer_connections(snapshot, run, ['r'])
    def answer(_service, _run, _stage, _instruction, payload, schema):
        record = payload['reviewed_connections']['k1']
        assert record['review_unit_id'] == 'join-unit' and record['review']['source_status'] == 'supported'
        assert 'k1' not in payload['reviewed_meanings']
        return dict(items=[dict(item_id='agency', selected=[dict(meaning_ref='m1', use='direct_fact')],
            unconfirmed=[], connection_refs=['k1'])])
    monkeypatch.setattr(business_run, 'json_call', answer)
    output = business_use.reviewed_item_answer(None, run, SimpleNamespace(question=run['requirements'][0]['question']), [])
    assert ('검토된 결합 해석:' in output['answer']) == claim_location
    assert ('현재 승인 후보의 표현 위치는 확인되지 않았습니다' in output['answer']) != claim_location
    assert output['citations'] == row['claim_ids'] or output['citations'] == [run['claims'][0]['id']]


def test_qa_item_binding_uses_checked_ids_and_retains_facts_on_wrong_connection_assignment(monkeypatch):
    run, source = setup()
    run['answer_items'].append(dict(run['answer_items'][0], id='other', request_quote='기관'))
    review.refresh_conjunctions(run, run['requirements'][0], source)
    result, errors = resolve(run, source, [connection(run, source)]); assert not errors
    snapshot = dict(assessments={'r': dict(id='a', source=source, representation=result)}, blocks=run['blocks'])
    run['reviewed_meanings'] = business_use.reviewed_answer_meanings(snapshot, {run['claims'][0]['id']}, ['r'])
    run['reviewed_connections'] = business_use.reviewed_answer_connections(snapshot, run, ['r'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a: dict(items=[
        dict(item_id=i['id'], selected=[dict(meaning_ref='m1', use='direct_fact')], unconfirmed=[],
             connection_refs=['k1']) for i in run['answer_items']]))
    output = business_use.reviewed_item_answer(None, run, SimpleNamespace(question=run['requirements'][0]['question']), [])
    assert output['answer'].count('검토된 결합 해석:') == 1
    assert output['answer'].count('검토된 원문 의미:') == 2
    assert run['answer_item_errors'] == ['other: connection_outside_public_item:k1']


def test_product_start_validates_and_persists_public_items(tmp_path, monkeypatch):
    from app.knowledge import parsers
    from app.knowledge.business_models import BusinessRunRequest
    from app.knowledge.schemas import SourceRegistration
    from app.knowledge.service import KnowledgeService, encode
    run, _ = setup()
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        vid = service.register('s.html', '<div id="content"><p>기관은 신청을 접수한다.</p></div>'.encode(),
            SourceRegistration(title='source', publisher='owner', namespace='test', selected_scope={'selector': '#content'}))['source_version_id']
        service.parse_input(dict(source_version_id=vid, parser=parsers.parser_info('html'), parser_options={'selector': '#content'}))
        with service.repository.connect() as db:
            db.execute('INSERT INTO requirements VALUES(?,?)', ('r', encode(run['requirements'][0])))
        monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a: {})
        monkeypatch.setattr(service.executor, 'submit', lambda *a: None)
        invalid = deepcopy(run['answer_items']); invalid[0]['request_quote'] = '원래 질문에 없는 요구'
        with pytest.raises(ValueError, match='정확한 구절'):
            business_run.start(service, BusinessRunRequest(source_version_ids=[vid], requirement_ids=['r'], answer_items=invalid))
        started = business_run.start(service, BusinessRunRequest(source_version_ids=[vid], requirement_ids=['r'], answer_items=run['answer_items']))
        assert service.run(started['run_id'])['answer_items'] == run['answer_items']
    finally:
        service.shutdown()


def test_supported_connection_requires_explicit_qa_selection(monkeypatch):
    run, source = setup()
    result, errors = resolve(run, source, [connection(run, source)]); assert not errors
    snapshot = dict(assessments={'r': dict(id='a', source=source, representation=result)}, blocks=run['blocks'])
    run['reviewed_meanings'] = business_use.reviewed_answer_meanings(snapshot, {run['claims'][0]['id']}, ['r'])
    run['reviewed_connections'] = business_use.reviewed_answer_connections(snapshot, run, ['r'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a: dict(items=[dict(item_id='agency',
        selected=[dict(meaning_ref='m1', use='direct_fact')], unconfirmed=[], connection_refs=[])]))
    output = business_use.reviewed_item_answer(None, run, SimpleNamespace(question=run['requirements'][0]['question']), [])
    assert '검토된 원문 의미:' in output['answer'] and '검토된 결합 해석:' not in output['answer']
    assert run['answer_item_errors'] == []
    assert source['conjunction_records'][0]['review']['source_status'] == 'supported'


def test_item_uncertainty_holds_selected_connections_without_erasing_facts_or_other_items(monkeypatch):
    run, source = setup()
    run['answer_items'].append(dict(run['answer_items'][0], id='other', request_quote='기관'))
    source['conjunction_records'].append(dict(deepcopy(source['conjunction_records'][0]), id='second_connection'))
    review.refresh_conjunctions(run, run['requirements'][0], source)
    first = connection(run, source); first['item_ids'] = ['agency', 'other']
    second = dict(deepcopy(first), conjunction_id='second_connection')
    result, errors = resolve(run, source, [first, second]); assert not errors
    snapshot = dict(assessments={'r': dict(id='a', source=source, representation=result)}, blocks=run['blocks'])
    run['reviewed_meanings'] = business_use.reviewed_answer_meanings(snapshot, {run['claims'][0]['id']}, ['r'])
    run['reviewed_connections'] = business_use.reviewed_answer_connections(snapshot, run, ['r'])
    original = deepcopy(run['reviewed_connections'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a: dict(items=[
        dict(item_id='agency', selected=[dict(meaning_ref='m1', use='direct_fact')],
            unconfirmed=['업무 연결을 확인하지 못함'], connection_refs=['k1', 'k2']),
        dict(item_id='other', selected=[dict(meaning_ref='m1', use='direct_fact')], unconfirmed=[], connection_refs=['k1'])]))
    output = business_use.reviewed_item_answer(None, run, SimpleNamespace(question=run['requirements'][0]['question']), [])
    first_section, second_section = output['answer'].split('\n\n')
    assert '검토된 결합 해석:' not in first_section
    assert '검토된 원문 의미:' in first_section and '확인 불가: 업무 연결을 확인하지 못함' in first_section
    assert '이 항목에는 미확인 내용이 남아 있어, 결합한 결론은 확정하지 않았습니다.' in first_section
    assert '검토된 결합 해석:' in second_section and '검토된 원문 의미:' in second_section
    assert run['answer_item_errors'] == ['agency: connection_selection_conflicts_with_unconfirmed:k1',
        'agency: connection_selection_conflicts_with_unconfirmed:k2']
    assert run['reviewed_connections'] == original

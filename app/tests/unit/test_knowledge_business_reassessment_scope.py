"""Partial fact checks retain observations without claiming whole-source coverage."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


def setup_source():
    run = local_run()
    run['recipe']['review_contract'] = review.CONTRACT
    req = dict(run['requirements'][0], question='처리 기관과 구비서류는?', criterion='조건과 참조 유지')
    m = dict(meaning('m'), conditions=['원문 조건'], references=['별도 서식'], required_for_requirement=True,
        requirement_link=dict(requested_fact='구비서류', applicability='applicable', contribution='direct_answer', reason='요청 항목'),
        field_judgments={'references': dict(status='unknown', statement_affected=False, reason='서식 상세 미제공')})
    source = dict(meanings=[m, dict(m, key='normal')], examined_block_ids=['body'], completeness='partial',
        gaps=['기존 조사 공백'], meaning_gaps=[], conjunctions=[], meaning_conjunctions=[], findings=[],
        review_contract=review.CONTRACT, source_batches=[])
    return run, req, source


def partial_call(monkeypatch, run, source, findings, *, examined=('body',), status='complete'):
    captured = {}
    def answer(_service, _run, stage, instruction, context, schema):
        assert stage == 'source_reassessment'
        assert schema.__name__ == 'ScopedRequirementSourceCheck'
        assert {'inspection_status', 'findings'} <= schema.model_fields.keys()
        assert not {'completeness', 'gaps'}.intersection(schema.model_fields)
        assert '전체 원문의 부재를 판정하지 않는다' in instruction
        captured.update(deepcopy(context))
        run['units'].append(dict(id='partial', status='succeeded'))
        return schema.model_validate(dict(meanings=[deepcopy(source['meanings'][0])],
            examined_block_ids=list(examined), inspection_status=status, findings=findings,
            conjunctions=[], meaning_conjunctions=[])).model_dump()
    monkeypatch.setattr(business_run, 'json_call', answer)
    return captured


@pytest.mark.parametrize('kind', ['local_not_found', 'reference_missing_here', 'interpretation_uncertain'])
def test_partial_contract_preserves_conditions_references_siblings_and_history(monkeypatch, kind):
    run, req, source = setup_source()
    source['findings'] = [dict(id='legacy', origin='source', kind='interpretation_uncertain', text='과거 자유 이의',
        meaning_keys=[], scope_meaning_keys=['m'], claim_ids=[], fields=[], provided_block_ids=['body'], unit_id='old')]
    source['reassessment_history'] = [dict(unit_id='old', previous=[deepcopy(source['meanings'][0])],
        output=dict(examined_block_ids=['body'], completeness='partial', gaps=['과거 자유 이의']))]
    before = deepcopy(source)
    captured = partial_call(monkeypatch, run, source, [dict(kind=kind, meaning_keys=['m'], text='실제 미확정 참조')])
    updated = review.reassess_source(None, run, req, dict(source=source), [dict(meaning_key='m', fields=['references'])])
    assert captured['requirement'] == req and captured['previous']['meanings'] == [before['meanings'][0]]
    assert updated['meanings'] == before['meanings'] and source == before
    assert updated['findings'][0] == before['findings'][0]
    assert updated['findings'][-1]['kind'] == kind and updated['findings'][-1]['meaning_keys'] == ['m']
    assert updated['gaps'] == before['gaps'] and updated['completeness'] == 'unknown'
    old, current = review.inspection_summaries(updated)
    assert 'provided_block_ids' not in old and old['inspection_status'] is None
    assert current['provided_block_ids'] == current['target_block_ids'] == current['examined_block_ids'] == ['body']
    assert current['meaning_keys'] == ['m'] and current['source_version_ids'] == ['v']
    assert current['inspection_scope'] == 'selected_meanings' and not current['inspection_error_active']
    assert not review.needs_source_read(updated, {})


@pytest.mark.parametrize('kind', ['local_not_found', 'reference_missing_here', 'interpretation_uncertain'])
def test_unattributed_observation_stays_unresolved_without_attacking_normal_facts(monkeypatch, kind):
    run, req, source = setup_source()
    source['gaps'] = []
    for m in source['meanings']:
        m.update(conditions=[], references=[], field_judgments={})
    partial_call(monkeypatch, run, source, [dict(kind=kind, meaning_keys=[], text='미선택 자료의 확인이 필요하다.')])
    updated = review.reassess_source(None, run, req, dict(source=source), [dict(meaning_key='m')])
    finding = updated['findings'][0]
    assert finding['meaning_keys'] == finding['scope_meaning_keys'] == []
    assert review.inspection_summaries(updated)[0]['meaning_keys'] == ['m']
    result = judgments(['m', 'normal'])
    result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(updated, result, [finding], run['blocks'], run['claims'], joined=True)
    assert updated['finding_resolutions'][0]['status'] == 'unresolved'
    assert updated['finding_resolutions'][0]['inspection_scope']['provided_block_ids'] == ['body']
    assert updated['completeness'] == 'partial'
    assert not result['meaning_challenges'] and not result['source_challenges']
    assert review.blocked(dict(source=updated, representation=result, errors=[], issues=[])) == (set(), [])


@pytest.mark.parametrize('examined,status', [([], 'complete'), (['body'], 'partial'), (['outside'], 'complete')])
def test_incomplete_inspection_keeps_actual_provided_ids_and_requests_additional_read(monkeypatch, examined, status):
    run, req, source = setup_source()
    partial_call(monkeypatch, run, source, [dict(kind='reference_missing_here', meaning_keys=['m'], text='외부 서식 미제공')],
                 examined=examined, status=status)
    updated = review.reassess_source(None, run, req, dict(source=source), [dict(meaning_key='m')])
    receipt = review.inspection_summaries(updated)[0]
    assert receipt['provided_block_ids'] == receipt['target_block_ids'] == ['body']
    assert receipt['examined_block_ids'] == examined and receipt['inspection_error_active']
    assert 'outside' not in updated['examined_block_ids']
    assert receipt['remaining_target_block_ids'] == ['body']
    assert review.needs_source_read(updated, {'unselected_source_required': False})
    assert updated['findings'][0]['text'] == '외부 서식 미제공'
    assert updated['meanings'][1] == source['meanings'][1]


def test_join_receives_partial_scope_receipt_and_typed_observation(monkeypatch):
    run, req, source = setup_source()
    partial_call(monkeypatch, run, source, [dict(kind='local_not_found', meaning_keys=[], text='미선택 자료 확인 필요')])
    updated = review.reassess_source(None, run, req, dict(source=source), [dict(meaning_key='m')])
    joined = {}
    def answer(_service, _run, _stage, _instruction, context, _schema):
        run['units'].append(dict(id='review'))
        if context['mode'] == 'requirement_join':
            joined.update(deepcopy(context))
            return None
        return judgments([m['key'] for m in context['source']['meanings']], ids=[run['claims'][0]['id']])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    review.represent(None, run, req, updated, [])
    assert joined['source_inspections'][0]['provided_block_ids'] == ['body']
    assert joined['source_inspections'][0]['inspection_scope'] == 'selected_meanings'
    assert joined['findings'][0]['kind'] == 'local_not_found'
    assert joined['findings'][0]['text'] == '미선택 자료 확인 필요'


@pytest.mark.parametrize('status,examined', [('partial', ['body']), ('complete', [])])
def test_legacy_additional_read_stops_with_explicit_limit_without_model_or_invented_coverage(monkeypatch, status, examined):
    run, req, source = setup_source()
    partial_call(monkeypatch, run, source, [], status=status, examined=examined)
    updated = review.reassess_source(None, run, req, dict(source=source), [dict(meaning_key='m')])
    before = deepcopy(updated)
    assert review.needs_source_read(updated, {}) and 'source_selection' not in updated
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No new whole-source call'))
    monkeypatch.setattr(review, 'source_selection', lambda *a: pytest.fail('No invented legacy selection'))
    assert review.source(None, run, req, previous=updated) is None
    assert updated['additional_read_errors'] == ['legacy_source_selection_missing']
    assert updated['completeness'] == 'unknown' and 'source_selection' not in updated
    assert all(updated[k] == before[k] for k in ('meanings', 'findings', 'reassessment_history', 'source_batches', 'gaps'))
    assert source['completeness'] == 'partial' and 'additional_read_errors' not in source

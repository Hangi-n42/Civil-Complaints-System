"""Responsibility boundaries and real stored judgments, independent of LLM quality."""
from copy import deepcopy

from app.knowledge import business_review as review, business_run, business_use
from app.knowledge.business_models import ExpressionReviewCheck, RequirementSynthesisCheck
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


def synthesis(**values):
    return dict(checks=[], dependencies=[], source_challenges=[], meaning_challenges=[],
        preservation_checks=[], satisfied=True, conjunctions_satisfied=True, reason='연결 확인',
        source_completeness='complete', unselected_source_required=False, finding_resolutions=[], **values)


def test_complete_expression_survives_partial_sibling_without_approving_bad_claim():
    full = judgments(['m'], ids=['normal'])
    partial = judgments(['m'], status='partial', ids=['part'])
    partial['checks'][0]['incorrect_claim_ids'] = ['bad']
    result = review.summarize_local([meaning('m')], [full, partial])
    assert result['checks'][0]['status'] == 'represented'
    assert result['checks'][0]['claim_ids'] == ['normal']
    assert result['checks'][0]['incorrect_claim_ids'] == ['bad']


def test_synthesis_preserves_unchanged_rows_and_rejects_unevidenced_downgrade():
    compact = judgments(['m'], ids=['normal'])
    result, joined, _, errors = review.retain_synthesis(compact, synthesis(), {'m'}, {'normal'}, [])
    assert joined and not errors and result['checks'] == compact['checks']
    row = dict(compact['checks'][0], status='partial', evidence=[], revision_basis='prior_misreading')
    changed = synthesis(); changed['checks'] = [row]
    result, joined, _, errors = review.retain_synthesis(compact, changed, {'m'}, {'normal'}, [])
    assert not joined and errors and result['checks'] == compact['checks']
    assert result['meaning_challenges'] and not result['satisfied']


def test_synthesis_accepts_evidenced_correction_without_rewriting_source():
    run = local_run()
    compact = judgments(['m'], status='partial', ids=['normal'])
    changed = synthesis(); changed['checks'] = [dict(compact['checks'][0], status='represented',
        revision_basis='combined_expression', evidence=meaning('m')['evidence'])]
    result, joined, _, errors = review.retain_synthesis(compact, changed, {'m'}, {'normal'}, run['blocks'])
    assert joined and not errors and result['checks'][0]['status'] == 'represented'
    assert result['source_checks'] == compact['source_checks']


def test_source_scope_excludes_outside_meaning_but_keeps_required_premise():
    meanings = [dict(meaning(k), required_for_requirement=k == 'main') for k in ['main', 'premise', 'outside']]
    meanings[0]['premise_keys'] = ['premise']
    source = dict(meanings=meanings, review_contract=review.CONTRACT)
    assert [m['key'] for m in review.review_meanings(source)] == ['main', 'premise']
    assert len(source['meanings']) == 3


def test_duplicate_synthesis_does_not_apply_first_change():
    run = local_run()
    compact = judgments(['m'], ids=['normal'])
    row = dict(compact['checks'][0], status='partial', evidence=meaning('m')['evidence'],
               revision_basis='prior_misreading')
    changed = synthesis(); changed['checks'] = [row, deepcopy(row)]
    result, joined, _, errors = review.retain_synthesis(compact, changed, {'m'}, {'normal'}, run['blocks'])
    assert not joined and errors and result['checks'] == compact['checks']


def test_expression_key_addresses_round_trip_in_join_context():
    original = dict(local_judgments=dict(checks=[dict(claim_support={'claim_long': 'incorrect'},
                                                     error_fields={'claim_long': ['Relation']})]))
    short = business_run.remap_expression_keys(original, {'claim_long': 'c1'})
    assert short['local_judgments']['checks'][0] == dict(claim_support={'c1': 'incorrect'}, error_fields={'c1': ['Relation']})
    assert business_run.remap_expression_keys(short, {'c1': 'claim_long'}) == original


def test_expression_error_evidence_uses_actual_server_source_view(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    context = dict(blocks=run['blocks'], claims=run['claims'], source=dict(meanings=[meaning('m')]))
    reference = 'e1'
    def response(*args, **kwargs):
        run['units'].append(dict(id='local'))
        return dict(parsed=dict(checks=[dict(meaning_key='m', status='incorrect', claim_ids=[],
            incorrect_claim_ids=['c1'], claim_support={'c1': 'incorrect'}, error_fields={'c1': ['raw.Relation']},
            error_evidence=[reference], reason='실제 구간 대조')], source_challenges=[], meaning_challenges=[], dependencies=[]))
    monkeypatch.setattr(business_run, 'call', response)
    monkeypatch.setattr(business_run, 'save', lambda *args: None)
    output = business_run.json_call(None, run, 'requirement_representation', '', context, ExpressionReviewCheck)
    row = output['checks'][0]
    assert row['error_fields'] == {run['claims'][0]['id']: ['raw.Relation']}
    assert row['error_evidence'][0]['quote'] == run['blocks'][0]['text']
    assert row['error_evidence'][0]['precision'] == 'exact'
    reference = 'not-provided'
    assert business_run.json_call(None, run, 'requirement_representation', '', context, ExpressionReviewCheck) is None
    assert run['units'][-1]['status'] == 'failed'


def test_existing_representation_path_uses_expression_only_and_delta_join(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    run['requirements'][0].update(question='전체 질문', criterion='전체 요구 기준', target='공개 대상', situation='공개 상황')
    source = dict(meanings=[dict(meaning('m'), required_for_requirement=True)], review_contract=review.CONTRACT,
        examined_block_ids=['body'], completeness='unknown', gaps=[], conjunctions=[], findings=[], source_batches=[])
    calls = []
    monkeypatch.setattr(business_run, 'cancelled', lambda *args: False)
    def answer(service, active, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(calls))))
        calls.append(deepcopy(context))
        assert 'source_checks' not in schema.model_fields
        if context['mode'] == 'requirement_join':
            assert schema is RequirementSynthesisCheck
            assert context['requirement']['criterion'] == '전체 요구 기준'
            assert context['review_meaning_keys'] == []
            return synthesis()
        assert schema is ExpressionReviewCheck
        assert 'question' not in context['requirement'] and 'criterion' not in context['requirement']
        assert context['requirement']['target'] == '공개 대상' and context['requirement']['situation'] == '공개 상황'
        return dict(checks=[dict(meaning_key='m', status='represented', claim_ids=[run['claims'][0]['id']],
            incorrect_claim_ids=[], reason='실제 표현', error_fields={}, error_evidence=[],
            claim_support={run['claims'][0]['id']: 'supported'})],
            source_challenges=[], meaning_challenges=[], dependencies=[dict(meaning_key='m', premise_keys=[])],
            preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert len(calls) == 2 and scope['join_succeeded']
    assert result['checks'][0]['status'] == 'represented'
    assert result['source_checks'][0] == review.source_judgment(source['meanings'][0])
    assert source['completeness'] == 'complete'


def test_unattributed_challenge_does_not_cancel_known_source_correction(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    source = dict(meanings=[dict(meaning('m'), required_for_requirement=True)], examined_block_ids=['body'],
        completeness='partial', gaps=[], conjunctions=[], findings=[dict(id='free', meaning_keys=[],
            text='미귀속 이의', kind='interpretation_uncertain')], source_batches=[], review_contract=review.CONTRACT)
    original = deepcopy(source)
    run['units'] = [dict(id='recheck')]
    def answer(service, active, stage, instruction, context, schema):
        assert context['challenges'] == [dict(meaning_key='m', fields=['period'], reason='오독')]
        return dict(meanings=deepcopy(source['meanings']), examined_block_ids=['body'], completeness='complete',
                    gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    corrected = review.reassess_source(None, run, {}, dict(source=source),
        ['미귀속 이의', dict(meaning_key='m', fields=['period'], reason='오독')])
    assert corrected['reassessed_meaning_keys'] == ['m']
    assert corrected['findings'] == original['findings'] and source == original


def test_unresolved_local_absence_stays_blocked_without_rewriting_source(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    run['blocks'].append(dict(deepcopy(run['blocks'][0]), id='other', text='별도 업무를 안내한다.'))
    finding = dict(id='local', origin='source', kind='local_not_found', text='이 구간에서 미발견',
        meaning_keys=['m'], scope_meaning_keys=['m'], claim_ids=[], fields=[], provided_block_ids=['body'], unit_id='old')
    source = dict(meanings=[dict(meaning('m'), required_for_requirement=True), dict(meaning('other'), required_for_requirement=False)],
        examined_block_ids=['body'], completeness='unknown', gaps=[], conjunctions=[],
        findings=[finding], source_batches=[], review_contract=review.CONTRACT)
    result = judgments(['m'])
    review.resolve_findings(source, result, [finding], run['blocks'], run['claims'], joined=False)
    assert result['meaning_challenges'][0]['source_reassessment_needed'] is False
    assessment = dict(source=source, representation=result, errors=[], issues=[])
    assert 'm' in review.blocked(assessment)[0]
    calls = []
    def answer(service, active, stage, instruction, context, schema):
        calls.append(context)
        assert {b['id'] for b in context['blocks']} == {'body'}
        assert [m['key'] for m in context['previous']['meanings']] == ['m']
        run['units'].append(dict(id='narrow'))
        return dict(meanings=[dict(meaning('m'), source_status='unknown', required_for_requirement=True)],
            examined_block_ids=['body'], completeness='unknown', gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    assert review.reassess_source(None, run, {}, assessment, result['meaning_challenges']) is None
    assert not calls
    corrected = review.reassess_source(None, run, {}, assessment,
        [*result['meaning_challenges'], dict(meaning_key='m', record_error='meaning_outside_local_target')])
    assert len(calls) == 1 and corrected['meanings'][0]['source_status'] == 'unknown'
    assert corrected['meanings'][1] == source['meanings'][1]
    assert corrected['reassessed_meaning_keys'] == ['m']


def test_partial_support_of_compound_claim_cannot_approve_it():
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    normal, compound = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('m')])
    representation = judgments(['m'], ids=[normal, compound])
    representation['checks'][0]['claim_support'] = {normal: 'supported', compound: 'unknown'}
    assessment = dict(requirement_id='r', source=source, representation=representation, errors=[], issues=[])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {normal} and 'unresolved_claim_support' in blocked[compound]


def test_partial_expression_keeps_its_separately_confirmed_error_action(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    partial, incorrect = [c['id'] for c in run['claims']]
    result = judgments(['m'], status='partial', ids=[partial])
    result['checks'][0].update(incorrect_claim_ids=[incorrect],
        claim_support={partial: 'not_assessed', incorrect: 'incorrect'},
        error_fields={incorrect: ['raw.Relation']}, error_evidence=meaning('m')['evidence'])
    source = dict(meanings=[dict(meaning('m'), required_for_requirement=True)], review_contract=review.CONTRACT,
        examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    monkeypatch.setattr(review, 'represent', lambda *a, **k: (deepcopy(result), {}))
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run.business_store, 'save_assessment', lambda *a: None)
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    assert [(a['action'], a['claim_ids']) for a in assessment['actions']] == [('hold', [partial]), ('correct', [incorrect])]
    assert business_use.eligibility(run)[0] == set()
    source['meanings'][0]['source_status'] = 'unknown'
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    assert all(a['action'] == 'hold' for a in assessment['actions'])


def test_unperformed_whole_check_is_not_a_veto_but_attributed_uncertainty_is():
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    normal, compound = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('a'), meaning('b')])
    representation = judgments(['a', 'b'])
    first, second = representation['checks']
    first.update(claim_ids=[normal, compound], claim_support={normal: 'supported', compound: 'not_assessed'})
    second.update(claim_ids=[compound], claim_support={compound: 'supported'})
    assessment = dict(requirement_id='r', source=source, representation=representation, errors=[], issues=[])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    assert business_use.eligibility(run)[0] == {normal, compound}
    first['claim_support'][compound] = 'unknown'
    first.update(error_fields={compound: ['Scope.conditions']}, error_evidence=meaning('a')['evidence'])
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {normal} and 'unresolved_claim_support' in blocked[compound]


def test_whole_candidate_uncertainty_requires_actual_attribution():
    check = dict(claim_ids=['c'], incorrect_claim_ids=[], claim_support={'c': 'not_assessed'}, error_fields={}, error_evidence=[])
    assert review.expression_attribution_valid(check, {'c'})
    check['claim_support']['c'] = 'unknown'
    assert not review.expression_attribution_valid(check, {'c'})
    check.update(error_fields={'c': ['Scope.conditions']}, error_evidence=meaning('m')['evidence'])
    assert review.expression_attribution_valid(check, {'c'})


def test_local_summary_preserves_unresolved_field_attribution():
    output = judgments(['m'], ids=['c'])
    output['checks'][0].update(claim_support={'c': 'unknown'}, error_fields={'c': ['Scope.conditions']},
                               error_evidence=meaning('m')['evidence'])
    row = review.summarize_local([meaning('m')], [output])['checks'][0]
    assert row['claim_support'] == {'c': 'unknown'}
    assert row['error_fields'] == {'c': ['Scope.conditions']}
    assert review.expression_attribution_valid(row, {'c'})


def test_candidate_uncertainty_preserves_other_complete_expression():
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    normal, uncertain = [c['id'] for c in run['claims']]
    full = judgments(['m'], ids=[normal])
    full['checks'][0]['claim_support'] = {normal: 'supported'}
    other = judgments(['m'], status='unknown', ids=[uncertain])
    other['checks'][0].update(claim_support={uncertain: 'unknown'}, error_fields={uncertain: ['Scope.conditions']},
                              error_evidence=meaning('m')['evidence'])
    source = dict(meanings=[meaning('m')])
    result = review.summarize_local(source['meanings'], [full, other])
    assert result['checks'][0]['status'] == 'represented'
    assert result['checks'][0]['claim_ids'] == [normal]
    assessment = dict(requirement_id='r', source=source, representation=result, errors=[], issues=[])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    assert business_use.eligibility(run)[0] == {normal}
    other['checks'][0]['error_fields'] = {}
    assert review.summarize_local(source['meanings'], [full, other])['checks'][0]['status'] == 'unknown'


def test_synthesis_cannot_drop_an_unmentioned_candidate_uncertainty(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    normal, uncertain = [c['id'] for c in run['claims']]
    compact = judgments(['m', 'n'])
    compact['checks'][0].update(status='partial', claim_ids=[normal], claim_support={normal: 'supported', uncertain: 'unknown'},
        error_fields={uncertain: ['Scope.conditions']}, error_evidence=meaning('m')['evidence'])
    compact['checks'][1].update(claim_ids=[uncertain], claim_support={uncertain: 'supported'})
    changed = synthesis(); changed['checks'] = [dict(meaning_key='m', status='represented', claim_ids=[normal],
        incorrect_claim_ids=[], claim_support={normal: 'supported'}, error_fields={}, error_evidence=[],
        evidence=meaning('m')['evidence'], revision_basis='combined_expression', reason='정상 표현 결합')]
    source = dict(meanings=[dict(meaning(k), required_for_requirement=True) for k in ['m', 'n']],
        review_contract=review.CONTRACT, examined_block_ids=['body'], completeness='unknown', gaps=[],
        conjunctions=[], findings=[], source_batches=[])
    monkeypatch.setattr(business_run, 'cancelled', lambda *args: False)
    def answer(service, active, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        if context['mode'] == 'requirement_join':
            return deepcopy(changed)
        keys = {m['key'] for m in context['source']['meanings']}
        return dict(checks=[deepcopy(c) for c in compact['checks'] if c['meaning_key'] in keys],
            dependencies=[dict(meaning_key=k, premise_keys=[]) for k in keys],
            source_challenges=[], meaning_challenges=[], preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert scope['join_succeeded'] and not scope['failures']
    assert result['checks'][0]['claim_support'][uncertain] == 'unknown'
    assert result['checks'][0]['error_fields'][uncertain] == ['Scope.conditions']
    assert review.expression_attribution_valid(result['checks'][0], {normal, uncertain})
    assessment = dict(requirement_id='r', source=source, representation=result, errors=[], issues=[])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    assert business_use.eligibility(run)[0] == {normal}
    changed['checks'][0]['claim_support'][uncertain] = 'not_assessed'
    repeated, _ = review.represent(None, run, run['requirements'][0], source, [])
    assert repeated['checks'][0]['claim_support'][uncertain] == 'unknown'


def test_expression_schema_places_locations_and_reason_before_final_verdict():
    from app.knowledge.business_models import ExpressionReviewCheck, RequirementSynthesisCheck
    for model, name in [(ExpressionReviewCheck, 'LocatedExpressionCheck'), (RequirementSynthesisCheck, 'ExpressionRevision')]:
        schema = model.model_json_schema()['$defs'][name]
        keys = list(schema['properties'])
        assert keys[-2:] == ['reason', 'status']
        assert keys.index('error_evidence') < keys.index('reason')
        assert schema['$comment'] == 'expression-evidence-before-verdict-v1'


def test_requirement_link_preserves_unresolved_scope_and_rejects_background_required():
    import pytest
    from app.knowledge.business_models import ScopedRequiredMeaningCheck, ScopedRequirementSourceCheck
    from pydantic import ValidationError
    m = dict(meaning('m'), required_for_requirement=True, requirement_link=dict(requested_fact='신청 기한',
        applicability='unresolved', contribution='direct_answer', reason='대상 시점 미확정'))
    assert ScopedRequiredMeaningCheck.model_validate(m).source_status == 'supported'
    assessment = dict(source=dict(meanings=[m]), representation=judgments(['m']), errors=[], issues=[])
    assert review.blocked(assessment)[0] == {'m'}
    assessment['source'].update(completeness='complete', gaps=[])
    assessment.update(preservation_complete=True)
    assessment['representation']['checks'][0]['claim_ids'] = ['normal']
    assert business_run.requirement_completion(assessment)['status'] == 'partial'
    for field, value in [('applicability', 'outside_scope'), ('contribution', 'background'), ('requested_fact', '')]:
        bad = deepcopy(m)
        bad['requirement_link'][field] = value
        with pytest.raises(ValidationError): ScopedRequiredMeaningCheck.model_validate(bad)
        bad['required_for_requirement'] = False
        assert not ScopedRequiredMeaningCheck.model_validate(bad).required_for_requirement
    schema = ScopedRequirementSourceCheck.model_json_schema()['$defs']['ScopedRequiredMeaningCheck']
    assert list(schema['properties']).index('requirement_link') < list(schema['properties']).index('required_for_requirement')


def test_unresolved_applicability_blocks_only_linked_claim_and_legacy_records_still_work():
    run = local_run()
    run['recipe']['review_contract'] = review.CONTRACT
    ids = [c['id'] for c in run['claims']]
    source = dict(review_contract=review.CONTRACT, completeness='complete', gaps=[], meanings=[
        dict(meaning(key), required_for_requirement=True, requirement_link=dict(requested_fact='접수 기관',
            applicability=state, contribution='direct_answer', reason='적용 시점 대조'))
        for key, state in [('uncertain', 'unresolved'), ('normal', 'applicable')]])
    representation = judgments(['uncertain', 'normal'])
    for row, cid in zip(representation['checks'], ids):
        row.update(claim_ids=[cid], claim_support={cid: 'supported'})
    assessment = dict(id='a', requirement_id='r', source=source, representation=representation,
                      errors=[], issues=[], preservation_complete=True)
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    original = deepcopy(source)
    eligible, blocks = business_use.eligibility(run)
    assert eligible == {ids[1]} and blocks[ids[0]][0] == 'meaning_dependency_blocked'
    assert source == original and all(m['source_status'] == 'supported' for m in source['meanings'])
    assert business_run.requirement_completion(assessment)['status'] == 'partial'
    run['recipe']['review_contract'] = source['review_contract'] = 'requirement-local-review-v6-separated'
    for row in source['meanings']: row.pop('requirement_link')
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    assert business_use.eligibility(run)[0] == set(ids)
    assert business_run.requirement_completion(assessment)['status'] == 'satisfied'

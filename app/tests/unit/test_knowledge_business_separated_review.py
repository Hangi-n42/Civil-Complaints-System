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


def test_answer_roots_expand_actual_premises_and_retain_unconnected_uncertainty():
    run = local_run(); run['recipe']['review_contract'] = review.ANSWER_SCOPE_EXPERIMENT
    req = dict(question='신청기한은 언제까지인가?', criterion='기산점과 단위를 구별한다.', situation='방문기관 선택')
    def item(key, contribution, required, quote='', premises=()):
        return dict(meaning(key), required_for_requirement=required, premise_keys=list(premises),
            requirement_link=dict(contribution=contribution, requirement_quote=quote))
    rows = [item('deadline', 'direct_answer', True, '신청기한', ['condition']),
            item('condition', 'necessary_premise', False), item('exception', 'necessary_premise', False),
            item('adjacent', 'background', False), item('unconnected', 'necessary_premise', True),
            item('context_only', 'direct_answer', True, '방문기관 선택')]
    source = dict(meanings=rows, review_contract=review.CONTRACT,
        answer_scope_contract=review.ANSWER_SCOPE_CONTRACT, answer_request=req,
        meaning_conjunctions=[dict(meaning_keys=['condition', 'exception'])])
    before = deepcopy(source)
    assert [m['key'] for m in review.review_meanings(source)] == ['deadline', 'condition', 'exception']
    assert {x['meaning_key'] for x in review.answer_scope_issues(source)} == {'unconnected', 'context_only'}
    assert source == before  # Background, original relevance, and unresolved links survive.
    assessment = dict(source=dict(source, completeness='complete', gaps=[], meaning_gaps=[]),
        representation=judgments(['deadline', 'condition', 'exception'], ids=['normal']),
        errors=[], preservation_complete=True)
    assessment['representation'].update(satisfied=True, conjunctions_satisfied=True)
    assert business_run.requirement_completion(assessment)['status'] == 'partial'
    instruction, context, schema = review.source_request(run, req, dict(blocks=run['blocks']), 0, 1)
    assert context['answer_request'] == {k: req[k] for k in ('question', 'criterion')}
    assert context['application_context'] == dict(situation='방문기관 선택')
    assert 'requirement' not in context and schema.__name__ == 'RootedRequirementSourceCheck'
    from json import loads
    private = dict(req, current_assessment={'status': 'old_model_judgment'}, history=['private'])
    instruction, context, schema = review.source_request(run, private, dict(blocks=run['blocks']), 0, 1)
    request = business_run.json_request(run, 'requirement_source', instruction, context, schema)
    supplied = loads(request['messages'][-1]['content'])
    assert supplied['application_context'] == dict(situation='방문기관 선택')
    run['recipe']['review_contract'] = review.CONTRACT
    _, default_context, default_schema = review.source_request(run, req, dict(blocks=run['blocks']), 0, 1)
    assert default_schema.__name__ == 'ScopedRequirementSourceCheck' and default_context['requirement'] == req

    legacy = dict(source); legacy.pop('answer_scope_contract')
    assert {m['key'] for m in review.review_meanings(legacy)} >= {'unconnected', 'context_only'}


def test_invalid_answer_link_reuses_partial_source_reassessment_without_rewriting_facts(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.ANSWER_SCOPE_EXPERIMENT
    req = dict(question='기간은?', criterion='기간을 보존한다', situation='기관 선택')
    normal = dict(meaning('normal'), required_for_requirement=True,
        requirement_link=dict(requested_fact='기간', applicability='applicable', contribution='direct_answer',
            reason='직접 요구', requirement_quote='기간'))
    adjacent = dict(meaning('adjacent'), required_for_requirement=True,
        requirement_link=dict(requested_fact='기관 선택', applicability='applicable', contribution='direct_answer',
            reason='방문 상황을 질문으로 오독', requirement_quote='기관 선택'))
    source = dict(meanings=[normal, adjacent], review_contract=review.CONTRACT,
        answer_scope_contract=review.ANSWER_SCOPE_CONTRACT, answer_request={k:req[k] for k in ('question','criterion')},
        examined_block_ids=['body'], completeness='unknown', gaps=[], meaning_gaps=[], meaning_conjunctions=[], findings=[])
    original = deepcopy(source); calls=[]
    def answer(service, active, stage, instruction, context, schema):
        calls.append(context);active['units'].append(dict(id='partial-link'))
        assert stage=='source_reassessment' and schema.__name__=='RequirementLinkReassessment'
        assert [m['key'] for m in context['previous']['meanings']]==['adjacent']
        assert context['challenges'][0]['invalid_requirement_quote']=='기관 선택'
        assert context['answer_request']==source['answer_request']
        patch=dict(key='adjacent', required_for_requirement=False, premise_keys=[], evidence=adjacent['evidence'],
            requirement_link=dict(requested_fact='', applicability='applicable', contribution='background',
                                  reason='직접 답변에 필요 없음', requirement_quote=''), reason='원문 사실은 유지')
        return dict(meanings=[patch], examined_block_ids=['body'], completeness='complete',gaps=[],
                    conjunctions=[],meaning_gaps=[],meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result=review.reassess_source(None, run, req, dict(source=source), review.answer_scope_challenges(source))
    assert len(calls)==1 and source==original and result['meanings'][0]==normal
    updated=result['meanings'][1]
    for field in ('statement','conditions','exceptions','period','references','source_status','availability'):
        assert updated[field]==adjacent[field]
    assert not review.answer_scope_challenges(result) and not updated['required_for_requirement']


def selection_fixture(run):
    run['id'] = 'run'
    run['recipe']['review_contract'] = review.MEANING_SELECTION_EXPERIMENT
    run['requirements'][0].update(question='어느 기관이 신청을 접수하는가?', criterion='접수 기관', situation='방문')
    run['assessments'] = [dict(id='prior', source=dict(meanings=[dict(meaning('stored'),
        required_for_requirement=True, requirement_link=dict(applicability='applicable'))]))]
    pool = review.selectable_meanings(run, run['blocks'])
    selected = dict(meaning_id=pool[0]['id'], source_status='unknown', availability='provided',
        evidence=meaning('m')['evidence'], requirement_link=dict(requested_fact='접수 기관',
        applicability='applicable', contribution='direct_answer', reason='질문 대조', requirement_quote='어느 기관이 신청을 접수하는가?'),
        premise_keys=[], reason='새 독립 판단', correction=None)
    return pool, dict(examined_block_ids=['body'], inspection_status='complete', selections=[selected],
        additions=[], findings=[], conjunctions=[], meaning_conjunctions=[])


def test_selection_discards_prior_verdict_and_retains_whole_saved_content():
    run = local_run(); pool, output = selection_fixture(run)
    assert set(pool[0]['content']) == {'statement', 'conditions', 'exceptions', 'period', 'references', 'evidence'}
    result = review.selected_source_output(output, pool)
    assert result['meanings'][0]['source_status'] == 'unknown'
    assert result['meanings'][0]['statement'] == meaning('stored')['statement']
    assert result['meanings'][0]['selection_origin']['assessment_id'] == 'prior'
    assert run['assessments'][0]['source']['meanings'][0]['source_status'] == 'supported'


def test_selection_scope_failure_keeps_healthy_sibling_and_surfaces_error(monkeypatch):
    run = local_run(); pool, output = selection_fixture(run)
    output['selections'][0]['source_status'] = 'supported'
    bad = deepcopy(pool[0]); bad['id'] = 's2'; pool.append(bad)
    bad = deepcopy(output['selections'][0]); bad['meaning_id'] = 's2'
    bad['requirement_link']['applicability'] = 'outside_scope'; output['selections'].append(bad)
    result = review.selected_source_output(output, pool)
    assert len(result['meanings']) == 2
    assert result['meanings'][0]['required_for_requirement']
    assert 'record_error' not in result['meanings'][0]
    assert result['meanings'][1]['record_error'].startswith('invalid_selection_scope:')
    assert result['meanings'][1]['source_status'] == 'supported'
    monkeypatch.setattr(review, 'source_selection', lambda *a: ([run['chunks'][0]], {}))
    monkeypatch.setattr(review, 'selectable_meanings', lambda *a: pool)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def response(*args):
        run['units'].append(dict(id='selection-unit'))
        return deepcopy(output)
    monkeypatch.setattr(business_run, 'json_call', response)
    source = review.source(None, run, run['requirements'][0])
    assert len(source['meanings']) == 2 and source['source_batches'][0]['errors']
    assert [m['key'] for m in review.review_meanings(source)] == ['batch1:s1']
    assert review.answer_scope_issues(source)[0]['meaning_key'] == 'batch1:s2'
    assert review.answer_scope_challenges(source)[0]['reassessment_scope'] == 'requirement_link_and_evidence'
    source.update(completeness='complete', gaps=[], meaning_gaps=[])
    assessment = dict(source=source, representation=judgments(['batch1:s1'], ids=['normal']), errors=[], issues=[], preservation_complete=True)
    assert business_run.requirement_completion(assessment)['status'] == 'partial'
    source['meanings'].pop()
    assert business_run.requirement_completion(assessment)['status'] == 'satisfied'


def test_selection_without_catalog_uses_claims_or_original_additions():
    run = local_run(); run['id'] = 'run'
    run['recipe']['review_contract'] = review.MEANING_SELECTION_EXPERIMENT
    assert review.selectable_meanings(run, run['blocks'])[0]['origin']['claim_id'] == run['claims'][0]['id']
    run['claims'] = []
    _, context, schema = review.source_request(run, run['requirements'][0], run['chunks'][0], 0, 1)
    assert context['existing_meanings'] == []
    new = dict(meaning('new'), required_for_requirement=True, requirement_link=dict(requested_fact='접수 기관',
        applicability='applicable', contribution='direct_answer', reason='원문에서 새 발견', requirement_quote='접수 기관'))
    output = schema.model_validate(dict(examined_block_ids=['body'], inspection_status='complete', selections=[],
        additions=[new], findings=[], conjunctions=[], meaning_conjunctions=[])).model_dump()
    assert review.selected_source_output(output, [])['meanings'] == [new]


def test_selected_source_evidence_restores_only_current_explicit_address(monkeypatch):
    run = local_run(); pool, output = selection_fixture(run)
    _, context, schema = review.source_request(run, run['requirements'][0], run['chunks'][0], 0, 1)
    output['selections'][0]['evidence'] = ['e1']
    def response(*args, **kwargs):
        run['units'].append(dict(id='u'))
        return dict(parsed=deepcopy(output))
    monkeypatch.setattr(business_run, 'call', response)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    result = business_run.json_call(None, run, 'requirement_source', '', context, schema)
    assert result['selections'][0]['evidence'][0]['quote'] == run['blocks'][0]['text']
    assert result['selections'][0]['source_status'] == 'unknown'
    output['selections'][0]['evidence'] = ['invented']
    assert business_run.json_call(None, run, 'requirement_source', '', context, schema) is None


def test_local_source_restores_separate_parent_and_body_references(monkeypatch):
    from app.knowledge.business_models import RequirementSourceCheck
    run = local_run()
    parent = dict(run['blocks'][0], id='parent', text='대리 신청', span=[0, 5], context_only=True)
    body = dict(run['blocks'][0], id='body', text='위임장 제출', span=[8, 14])
    context = dict(blocks=[parent, body])
    output = dict(examined_block_ids=['parent', 'body'], inspection_status='complete', findings=[], conjunctions=[],
        meanings=[dict(meaning('m', required_for_requirement=True), evidence=['e1', 'e2'], source_status='unknown')])
    def response(*args, **kwargs):
        run['units'].append(dict(id='u'))
        return dict(parsed=deepcopy(output))
    monkeypatch.setattr(business_run, 'call', response)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    result = business_run.json_call(None, run, 'requirement_source', '', context, RequirementSourceCheck)
    refs = result['meanings'][0]['evidence']
    assert [(r['block_id'], r['quote'], r['start_char'], r['end_char']) for r in refs] == [
        ('parent', '대리 신청', 0, 5), ('body', '위임장 제출', 8, 14)]
    assert result['meanings'][0]['source_status'] == 'unknown'
    assert run['units'][-1]['restored_evidence_output'] == result
    output['meanings'][0]['evidence'] = [dict(block_id='body', quote='대리 신청 위임장 제출')]
    assert business_run.json_call(None, run, 'requirement_source', '', context, RequirementSourceCheck) is None


def test_source_input_preserves_parser_parent_binding_without_changing_normal_r():
    import json
    from app.knowledge import autoschema
    from app.knowledge.business_models import RequirementSourceCheck
    from app.tests.unit.test_knowledge_business_scope import block
    run = local_run()
    run['blocks'] = [block('parent', '대리 신청', path='ul:1 > li:1::text(1)'),
        block('child', '위임장', path='ul:1 > li:1 > ul:1 > li:1'),
        block('sibling', '공통 신분증', path='ul:1 > li:2'),
        dict(block('other', '다른 버전', path='ul:1 > li:1 > ul:1 > li:1'), source_version_id='other')]
    context = dict(blocks=run['blocks'])
    source = business_run.json_request(run, 'requirement_source', '', context, RequirementSourceCheck)
    payload = json.loads(source['messages'][-1]['content'])
    assert payload['source_parents'] == [dict(block_id='b2', parent_block_ids=['b1'])]
    assert [p['id'] for p in autoschema.list_parents(run['blocks'][1], run['blocks'])] == ['parent']
    normal = business_run.json_request(run, 'requirement_representation', '', context, ExpressionReviewCheck)
    assert 'source_parents' not in json.loads(normal['messages'][-1]['content'])
    assert 'source_parents' not in normal['messages'][0]['content']


def test_source_quote_answer_server_keeps_conditional_text_and_unanswered_item(monkeypatch):
    from app.knowledge.business_models import BusinessQuery
    text = '대리인이 신청하는 경우 위임장을 제출한다.'
    evidence = [dict(id='b', text=text, claim_references=[dict(claim_ids=['c'])])]
    output = dict(items=[dict(question_quote='직접 신청에도 위임장이 필요한가?', coverage='unknown',
        evidence_refs=['t1'], missing_question_quote='직접 신청에도 위임장이 필요한가?')], choice=None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: deepcopy(output))
    run = {}; request = BusinessQuery(question='직접 신청에도 위임장이 필요한가?', snapshot_id='s', answer_mode='source_quotes')
    result = business_use.source_quote_answer(None, run, request, evidence, {}, {})
    assert result['citations'] == ['c'] and '원문: ' + text in result['answer']
    assert result['limitations'] == ['직접 확인 불가: 직접 신청에도 위임장이 필요한가?']
    output['items'][0]['question_quote'] = '질문에 없는 답변 항목'
    assert business_use.source_quote_answer(None, run, request, evidence, {}, {}) is None


def test_source_quote_answer_carries_public_criterion_without_prior_judgments(monkeypatch):
    from app.knowledge.business_models import BusinessQuery
    contexts = []
    def response(service, run, stage, instruction, context, schema, **kwargs):
        contexts.append(context)
        return dict(items=[dict(question_quote='구비서류 요건', coverage='unknown', evidence_refs=['t1'],
            missing_question_quote='구비서류 요건')], choice=None)
    monkeypatch.setattr(business_run, 'json_call', response)
    request = BusinessQuery(question='접수 기관은?', snapshot_id='s', answer_mode='source_quotes')
    result = business_use.source_quote_answer(None, {}, request,
        [dict(text='접수 기관: 본소', claim_references=[dict(claim_ids=['c'])])], {}, {},
        [dict(id='r', question='접수 기관은?', criterion='구비서류 요건', status='satisfied', history=['old verdict'])])
    assert result['limitations'] == ['직접 확인 불가: 구비서류 요건']
    assert 'status' not in contexts[0]['public_requirements'][0]
    assert 'history' not in contexts[0]['public_requirements'][0]


def test_public_item_binding_does_not_revise_requirements_or_accept_answer_text():
    from app.knowledge.business_models import BusinessQuery
    import pytest
    requirement = dict(id='r', revision=2, question='접수 기관은?', criterion='구비서류 요건', status='satisfied')
    original = deepcopy(requirement)
    request = BusinessQuery(question='접수 기관은?', snapshot_id='s', requirement_ids=['r'], answer_mode='items',
        answer_items=[dict(id='docs', requirement_id='r', requirement_revision=2, field='criterion', request_quote='구비서류 요건')])
    assert business_use.bind_answer_items(request, [requirement]) == [request.answer_items[0].model_dump()]
    assert requirement == original
    request.answer_items[0].requirement_revision = 1
    with pytest.raises(ValueError, match='revision'):
        business_use.bind_answer_items(request, [requirement])
    request.answer_items[0].requirement_revision = 2
    request.answer_items[0].request_quote = '위임장이 필요하다'
    with pytest.raises(ValueError, match='정확한 구절'):
        business_use.bind_answer_items(request, [requirement])


def test_item_answer_requires_all_public_items_and_preserves_specific_gap_and_source(monkeypatch):
    from app.knowledge.business_models import BusinessQuery
    public = [dict(id=k, requirement_id='r', requirement_revision=1, field='criterion', request_quote=q)
              for k, q in [('docs:required', '구비서류 요건'), ('office', '처리 기관')]]
    request = BusinessQuery(question='어디에 어떤 서류를 제출하는가?', snapshot_id='s', requirement_ids=['r'],
                            answer_mode='items', answer_items=public)
    text = '대리인이 신청하는 경우 위임장을 제출한다.'
    evidence = [dict(id='b', source_version_id='v', parse_run_id='p', span=[10, 10 + len(text)],
                     text=text, claim_references=[dict(claim_ids=['c'])])]
    output = dict(choice=None, items=[dict(item_id='docs:required', conclusions=[dict(statement=text, kind='conditional_duty',
        conditions=['대리인이 신청하는 경우'], exceptions=[], support=[dict(evidence_ref='t1', quote=text)], reasoning='')], missing=[]),
        dict(item_id='office', conclusions=[], missing=['제출 서류 원문에는 접수 기관이 명시되어 있지 않다.'])])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: deepcopy(output))
    run = dict(answer_items=public)
    result = business_use.item_answer(None, run, request, evidence, {}, {}, [])
    assert result['citations'] == ['c'] and '조건: 대리인이 신청하는 경우' in result['answer']
    assert result['limitations'] and len(result['items']) == 2
    assert result['items'][0]['conclusions'][0]['support'][0]['source']['span'] == [10, 10 + len(text)]
    output['items'].pop()
    partial = business_use.item_answer(None, run, request, evidence, {}, {}, [])
    assert partial['citations'] == ['c'] and text in partial['answer']
    assert partial['items'][1]['record_errors'] == ['missing_item']
    assert partial['limitations'] == []
    assert run['answer_item_errors'] == [dict(item_id='office', errors=['missing_item'])]
    output['items'].append(dict(item_id='office', conclusions=[], missing=['접수 기관 근거 없음']))
    output['items'][0]['conclusions'][0]['support'][0]['quote'] = '직접 신청도 위임장 필요'
    output['items'][1]['conclusions'] = deepcopy(output['items'][0]['conclusions'])
    output['items'][1]['conclusions'][0]['support'][0]['quote'] = text
    partial = business_use.item_answer(None, run, request, evidence, {}, {}, [])
    assert partial['citations'] == ['c'] and text in partial['answer']
    assert partial['items'][0]['conclusions'] == []
    assert partial['items'][1]['conclusions']
    assert run['answer_item_errors'] == [dict(item_id='docs:required', errors=['invalid_source_quote:0'])]
    assert run['answer_selection'] == output


def test_selection_catalog_cannot_supply_unread_support_or_old_premise_keys():
    run = local_run(); pool, output = selection_fixture(run)
    run['assessments'][0]['source']['meanings'][0]['evidence'].append(dict(block_id='unread', quote='별도 조건'))
    assert review.selectable_meanings(run, run['blocks']) == []
    run['assessments'][0]['source']['meanings'][0]['evidence'].pop()
    instruction, context, schema = review.source_request(run, run['requirements'][0], run['chunks'][0], 0, 1)
    wire = business_run.json_request(run, 'requirement_source', instruction, context, schema)
    import json
    row = json.loads(wire['messages'][1]['content'])['existing_meanings'][0]
    assert 'origin' not in row and 'evidence' not in row['content']
    assert row['source_evidence_refs'] == ['e1']
    assert context['existing_meanings'][0]['origin']['meaning_key'] == 'stored'


def test_selected_availability_is_source_provenance_and_self_premise_stays_unresolved():
    run = local_run(); pool, output = selection_fixture(run)
    output['selections'][0].pop('availability')
    result = review.selected_source_output(output, pool)['meanings'][0]
    assert result['availability'] == 'provided' and result['source_status'] == 'unknown'
    output['selections'][0]['premise_keys'] = [pool[0]['id']]
    result = review.selected_source_output(output, pool)['meanings'][0]
    assert result['record_error'] == 'invalid_selection_scope: self premise'
    assert result['source_status'] == 'unknown' and not result['required_for_requirement']


def test_reassessment_cannot_clear_self_premise_by_dropping_error_metadata():
    run = local_run(); pool, output = selection_fixture(run)
    m = review.selected_source_output(output, pool)['meanings'][0]
    m.update(source_status='supported', premise_keys=[m['key']], required_for_requirement=True)
    assert 'record_error' not in m
    source = dict(meanings=[m], review_contract=review.MEANING_SELECTION_EXPERIMENT,
        answer_scope_contract=review.ANSWER_SCOPE_CONTRACT, answer_request=run['requirements'][0],
        completeness='complete', gaps=[], meaning_gaps=[])
    assessment = dict(source=source, representation=judgments([m['key']], ids=['normal']),
                      errors=[], preservation_complete=True)
    assert review.answer_scope_issues(source)[0]['reason'] == 'invalid_selection_scope: self premise'
    assert business_run.requirement_completion(assessment)['status'] == 'partial'
    m['premise_keys'] = []
    assert business_run.requirement_completion(assessment)['status'] == 'satisfied'

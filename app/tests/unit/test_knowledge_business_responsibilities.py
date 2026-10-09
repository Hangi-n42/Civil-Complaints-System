"""Source truth, question applicability and candidate repair have different owners."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run


def test_direct_candidate_review_keeps_normal_unknown_and_owned_error_separate(monkeypatch):
    run = local_run(); claims = run['claims']; before = deepcopy(claims)
    states = ['supported', 'incorrect']
    def answer(service, current, stage, instruction, context, schema):
        assert stage == 'candidate_source_review'
        assert not {'requirement', 'source', 'previous'} & context.keys()
        current['units'].append(dict(id='direct'))
        return dict(checks=[dict(claim_id=c['id'], claim_support=state,
            evidence=c['evidence'], error_fields=[] if state == 'supported' else ['raw.Relation'],
            error_evidence=[] if state == 'supported' else c['evidence'], reason='원문 대조')
            for c, state in zip(claims, states)], preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    receipt = review.review_candidates(None, run, claims)
    assert not receipt['errors'] and receipt['checks'][0]['incorrect_claim_ids'] == []
    assert receipt['checks'][1]['incorrect_claim_ids'] == [claims[1]['id']]
    assert receipt['checks'][1]['error_attributions'][0]['status'] == 'accepted'
    states[1] = 'unknown'
    receipt = review.review_candidates(None, run, claims)
    assert not receipt['errors'] and receipt['checks'][1]['incorrect_claim_ids'] == []
    assert receipt['checks'][1]['claim_support'][claims[1]['id']] == 'unknown'
    assert run['claims'] == before and not run['assessments']


def test_fact_request_excludes_public_usage_and_candidate_hypotheses():
    run = local_run(); run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    request = dict(question='담당 기관?', criterion='처리 가능 범위', period='방문 전 확인', situation='번호판 변경')
    instruction, context, schema = review.source_request(run, request, run['chunks'][0], 0, 1)
    assert schema.__name__ == 'LocalSourceCheck'
    assert set(context) == {'blocks', 'source_scope'}
    assert '방문 전 확인' not in str(context)
    assert 'required_for_requirement' not in str(schema.model_json_schema())


def test_application_cannot_overwrite_fact_fields_and_outside_scope_is_not_false(monkeypatch):
    from app.knowledge.business_models import RequirementApplicationCheck
    from app.tests.unit.test_knowledge_business_local_review import meaning
    from pydantic import ValidationError
    import pytest
    run = local_run(); fact = meaning('m'); facts = dict(meanings=[fact]); original = deepcopy(facts)
    output = dict(links=[dict(key='m', required_for_requirement=False, requirement_link=dict(
        requested_fact='', applicability='outside_scope', contribution='background', reason='요구 밖', requirement_quote=''))],
        meaning_challenges=[])
    output['links'] = [dict(row, item_id=item) for item in ('question', 'criterion') for row in output['links']]
    def answer(*args):
        run['units'].append(dict(id='application'))
        return deepcopy(output)
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = review.apply_requirement(None, run, dict(question='기관?', criterion='담당', period='방문 전'), facts, run['blocks'])
    assert facts == original
    assert all(result['meanings'][0][k] == v for k, v in fact.items())
    assert result['meanings'][0]['source_status'] == 'supported'
    assert result['meanings'][0]['required_for_requirement'] is False
    poisoned = deepcopy(output); poisoned['links'][0]['period'] = '방문 전'
    with pytest.raises(ValidationError):
        RequirementApplicationCheck.model_validate(poisoned)


def test_scalar_candidate_support_survives_reference_restoration():
    value = dict(checks=[dict(claim_id='c1', claim_support='incorrect', error_fields=['raw.Relation'])])
    assert business_run.remap_expression_keys(value, {'c1': 'claim_real'}) == value
    value = dict(claim_support={'c1': 'supported'}, error_fields={'c1': ['raw.Relation']})
    assert business_run.remap_expression_keys(value, {'c1': 'claim_real'}) == dict(
        claim_support={'claim_real': 'supported'}, error_fields={'claim_real': ['raw.Relation']})


def test_application_failure_is_local_and_missing_link_keeps_fact(monkeypatch):
    from app.tests.unit.test_knowledge_business_local_review import meaning
    run = local_run(); facts = dict(meanings=[meaning(k) for k in ['normal', 'invalid', 'missing']])
    original = deepcopy(facts)
    normal = dict(key='normal', required_for_requirement=False, requirement_link=dict(requested_fact='',
        applicability='outside_scope', contribution='background', reason='요구 밖 정상 사실', requirement_quote=''))
    invalid = dict(key='invalid', required_for_requirement=True, requirement_link=dict(requested_fact='담당',
        applicability='outside_scope', contribution='direct_answer', reason='필수성 모순', requirement_quote='질문에 없는 구절'))
    def answer(*a):
        run['units'].append(dict(id='application'))
        return dict(links=[dict(row, item_id=item) for item in ('question', 'criterion')
                          for row in (normal, invalid)], meaning_challenges=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = review.apply_requirement(None, run, dict(question='기관?', criterion='담당'), facts, run['blocks'])
    by_key = {m['key']: m for m in result['meanings']}
    assert by_key['normal']['requirement_link'] == normal['requirement_link']
    assert not by_key['normal']['required_for_requirement']
    assert {e['meaning_key'] for e in result['application_history'][0]['errors']} == {'invalid', 'missing'}
    assert all(by_key[k]['requirement_link']['applicability'] == 'unresolved' for k in ['invalid', 'missing'])
    assert facts == original
    assert all(all(by_key[m['key']][k] == v for k, v in m.items()) for m in facts['meanings'])


def test_criterion_item_remains_required_when_institution_question_is_outside_scope(monkeypatch):
    from app.tests.unit.test_knowledge_business_local_review import meaning
    run = local_run()
    requirement = dict(id='r', revision=1, question='담당 기관?', criterion='구비서류 요건과 기관 범위')
    run['answer_items'] = [dict(id=key, requirement_id='r', requirement_revision=1, field=field, request_quote=quote)
        for key, field, quote in [('institution', 'question', '담당 기관?'), ('docs', 'criterion', '구비서류 요건')]]
    facts = dict(meanings=[meaning('m')]); before = deepcopy(facts)
    def answer(_s, _r, _stage, _prompt, context, schema):
        assert context['public_answer_items'] == run['answer_items']
        assert 'requirement_quote' not in str(schema.model_json_schema())
        run['units'].append(dict(id='items'))
        output = schema.model_validate(dict(links=[
            dict(item_id='institution', key='m', required_for_requirement=False, requirement_link=dict(
                requested_fact='담당 기관', applicability='outside_scope', contribution='background', requirement_quote='', reason='기관 정보 없음')),
            dict(item_id='docs', key='m', required_for_requirement=True, requirement_link=dict(
                requested_fact='구비서류 요건', applicability='applicable', contribution='direct_answer', requirement_quote='구비서류 요건', reason='서류 요청에 기여'))],
            meaning_challenges=[])).model_dump()
        # A recorded legacy response selected the right item but quoted another.
        output['links'][1]['requirement_link']['requirement_quote'] = '담당 기관?'
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = review.apply_requirement(None, run, requirement, facts, run['blocks'])
    assert facts == before and result['meanings'][0]['required_for_requirement']
    assert result['meanings'][0]['requirement_link']['requirement_quote'] == '구비서류 요건'
    assert len(result['meanings'][0]['requirement_applications']) == 2
    assert not result['application_history'][-1]['errors']
    assert result['application_history'][-1]['output']['links'][1]['requirement_link']['requirement_quote'] == '담당 기관?'
    assert result['application_history'][-1]['request_quote_bindings'][1]['bound_quote'] == '구비서류 요건'
    run['answer_items'][1]['requirement_revision'] = 0
    with pytest.raises(ValueError, match='revision'):
        review.apply_requirement(None, run, requirement, facts, run['blocks'])


def test_assessment_reuse_is_bound_to_current_public_item_scope():
    run = local_run(); requirement = run['requirements'][0]; source = dict(meanings=[])
    before = business_run.assessment_fingerprint(run, requirement, source)
    run['answer_items'] = [dict(id='docs', requirement_id=requirement['id'], requirement_revision=1,
                               field='criterion', request_quote='구비서류')]
    with_item = business_run.assessment_fingerprint(run, requirement, source)
    assert before != with_item
    run['answer_items'][0]['request_quote'] = '기관 범위'
    assert with_item != business_run.assessment_fingerprint(run, requirement, source)


def setup_direct_receipt(monkeypatch, states=('supported', 'incorrect'), transform=None):
    run = local_run(); run['recipe'].update(review_contract=review.SOURCE_APPLICATION_CONTRACT,
        models=dict(review='local-review', draft='local-draft'), generation=dict(provider='ollama'))
    run.update(model_identity={'review': 'digest'}, id='r', metrics={})
    def answer(service, current, stage, instruction, context, schema):
        assert stage == 'candidate_source_review'
        request = business_run.json_request(run, stage, instruction, context, schema)
        options = run['recipe']['options']
        output = dict(checks=[dict(claim_id=c['id'], claim_support=status,
            evidence=c['evidence'], error_fields=[] if status == 'supported' else ['raw.Relation'],
            error_evidence=[] if status == 'supported' else c['evidence'], reason='실제 필드 검수')
            for c, status in zip(run['claims'], states)], preservation_checks=[])
        if transform:
            transform(output)
        limits = dict(max_tokens=options['review_tokens'], context_tokens=options['context_tokens'], think=options['think'])
        run['units'].append(dict(id='direct', stage=stage, status='succeeded', error=None,
            **{k: request[k] for k in ['messages', 'schema', 'reference_map', 'evidence_reference_map']},
            request_configuration=dict(model='local-review', generation=deepcopy(run['recipe']['generation']),
                identity=deepcopy(run['model_identity']), temperature=0, timeout=options['timeout']),
            requested_limits=limits, executed_limits=deepcopy(limits), restored_evidence_output=deepcopy(output)))
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    receipt = review.review_candidates(None, run, run['claims'])
    if transform is None:
        assert not receipt['errors']
    return run, receipt


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'outside', 'bad_evidence', 'bad_field'])
def test_partial_candidate_response_preserves_valid_rows_and_rechecks_only_pending(monkeypatch, case):
    def transform(output):
        rows = output['checks']
        if case == 'missing':
            rows.pop()
        elif case == 'duplicate':
            rows.append(deepcopy(rows[-1]))
        elif case == 'outside':
            rows.append(dict(deepcopy(rows[-1]), claim_id='unrequested'))
        elif case == 'bad_evidence':
            rows[-1]['evidence'] = [dict(block_id='body', quote='원문에 없는 인용')]
        else:
            rows[-1].update(claim_support='incorrect', error_fields=['raw.absent'],
                            error_evidence=deepcopy(rows[-1]['evidence']))
    run, receipt = setup_direct_receipt(monkeypatch, states=('supported', 'supported'), transform=transform)
    normal, pending = [c['id'] for c in run['claims']]
    expected = {normal, pending} if case == 'outside' else {normal}
    assert set(review.current_candidate_reviews(run)) == expected
    assert {c['claim_ids'][0] for c in receipt['checks']} == expected
    assert all(not c['incorrect_claim_ids'] for c in receipt['checks'])
    assert all(isinstance(error, dict) for error in receipt['errors'])
    assert {e['claim_id'] for e in receipt['errors']} == ({'unrequested'} if case == 'outside' else {pending})
    scheduled = []
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(review, 'review_candidates', lambda service, current, claims, **kwargs:
        scheduled.extend(c['id'] for c in claims))
    review.review_candidate_pool(None, run, run['claims'])
    assert scheduled == ([] if case == 'outside' else [pending])


def test_direct_receipt_reuse_requires_exact_input_contract_model_and_correction_context(monkeypatch):
    run, receipt = setup_direct_receipt(monkeypatch)
    original = deepcopy(run)
    assert set(review.current_candidate_reviews(run)) == {c['id'] for c in run['claims']}
    changes = [lambda r: r['claims'][0]['raw'].update(Relation='변경'),
        lambda r: r['blocks'][0].update(text='다른 원문'),
        lambda r: r['recipe'].update(review_contract=review.CONTRACT),
        lambda r: r['recipe']['models'].update(review='another'),
        lambda r: r['model_identity'].update(review='new-digest'),
        lambda r: r['recipe']['options'].update(think=True),
        lambda r: r['recipe']['options'].update(review_tokens=8192),
        lambda r: r['repairs'].append(dict(id='repair', changes=[dict(before=deepcopy(r['claims'][0]), after=deepcopy(r['claims'][0]))]))]
    for change in changes:
        run = deepcopy(original); change(run)
        assert review.current_candidate_reviews(run) == {}


def test_contribution_has_no_accuracy_vote_and_only_concrete_contradiction_invalidates_receipt(monkeypatch):
    from app.knowledge.business_models import ContributionReviewCheck
    run, receipt = setup_direct_receipt(monkeypatch)
    bad = run['claims'][1]['id']
    context = dict(blocks=run['blocks'])
    request = business_run.json_request(run, 'requirement_representation', 'contribution', context, ContributionReviewCheck)
    assert 'Whole-candidate support' not in str(request['schema'])
    assert 'claim_support' not in str(request['schema'])
    output = dict(checks=[dict(meaning_key='m', status='represented', claim_ids=[bad], reason='기여')],
                  candidate_challenges=[], source_challenges=[])
    review.attach_candidate_support(run, output, run['claims'], run['blocks'])
    assert output['checks'][0]['claim_support'][bad] == 'incorrect'
    assert output['checks'][0]['incorrect_claim_ids'] == [bad]
    challenge = dict(meaning_key='m', claim_ids=[bad], fields=['raw.Relation'], evidence=run['claims'][1]['evidence'], reason='구체 차이')
    output['candidate_challenges'] = [challenge]
    review.attach_candidate_support(run, output, run['claims'], run['blocks'])
    assert run['candidate_challenges'] == [challenge]
    assert output['checks'][0]['claim_support'][bad] == 'not_assessed'
    assert set(review.current_candidate_reviews(run)) == {run['claims'][0]['id']}


def test_failed_e_does_not_block_owned_candidate_repair_or_invent_source_truth(monkeypatch):
    from app.tests.unit.test_knowledge_business_scope import scope_for
    from app.knowledge import business_store
    run, receipt = setup_direct_receipt(monkeypatch)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    before = deepcopy(run['claims']); normal, bad = before
    monkeypatch.setattr(review, 'source', lambda *a, **k: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    assessment = business_run.assess(None, run, run['requirements'][0])
    assert assessment['source'] is None and assessment['status'] == 'unknown'
    action = next(a for a in assessment['actions'] if a['action'] == 'correct')
    assert action['claim_ids'] == [bad['id']] and action['candidate_review_id'] == receipt['id']
    scope = scope_for(run['chunks'][0], run['blocks'][0]['text'])
    for entries in [scope['evidence'], scope['meanings'][0]['evidence'],
                    *[p['evidence'] for p in scope['meanings'][0]['participants']]]:
        for entry in entries:
            entry['block_id'] = 'body'
    def repair_answer(service, current, stage, instruction, context, schema):
        assert stage == 'requirement_repair'
        assert context['source']['meanings'] == []
        assert context['tasks'][0]['meanings'][0]['review_records'][0]['candidate_review_id'] == receipt['id']
        assert {b['id'] for b in context['blocks']} == {'body'}
        return dict(patches=[dict(meaning_key=action['meaning_key'], target_id=bad['id'],
            statement='기관은 신청을 접수한다.', head='기관', relation='접수', tail='신청',
            evidence=[dict(block_id='body', quote=run['blocks'][0]['text'])], conditions=[], exceptions=[],
            period='', references=[], scope=scope)], unresolved=[])
    monkeypatch.setattr(business_run, 'json_call', repair_answer)
    assert business_run.repair(None, run, run['requirements'][0], assessment)
    assert run['claims'][0] == normal
    assert run['repairs'][-1]['status'] == 'applied_awaiting_recheck'
    assert run['repairs'][-1]['changes'][0]['after']['source_extraction_raw'] == bad['raw']
    assert not review.current_candidate_reviews(run)  # Changed fields require fresh source review.
    assert assessment['status'] == 'unknown'  # Stored correction cannot manufacture requirement completion.


def test_unverified_direct_action_cannot_bypass_source_failure(monkeypatch):
    run, receipt = setup_direct_receipt(monkeypatch)
    cid = run['claims'][1]['id']
    assessment = dict(id='a', source=None, representation=None, errors=[], issues=[], actions=[dict(
        meaning_key='candidate:' + cid, action='correct', claim_ids=[cid], candidate_review_id='forged')])
    monkeypatch.setattr(business_run, 'json_call', lambda *a: (_ for _ in ()).throw(AssertionError('must not call repair')))
    assert not business_run.repair(None, run, run['requirements'][0], assessment)
    assert not run['repairs']


def test_application_only_reassessment_preserves_all_source_annotations(monkeypatch):
    from app.tests.unit.test_knowledge_business_local_review import meaning
    run = local_run(); run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    old = dict(meanings=[meaning('m', required_for_requirement=True), meaning('normal', required_for_requirement=False)],
        examined_block_ids=['body'], gaps=['unresolved original source gap'], meaning_gaps=[dict(meaning_keys=['m'], text='gap')],
        conjunctions=['source conjunction'], meaning_conjunctions=[], findings=[dict(id='f', meaning_keys=['m'])])
    original = deepcopy(old)
    def answer(service, current, stage, instruction, context, schema):
        assert stage == 'requirement_application'  # No fact re-judge for a link-only question.
        run['units'].append(dict(id='application'))
        return dict(links=[dict(item_id=item, key='m', required_for_requirement=False, requirement_link=dict(requested_fact='',
            applicability='outside_scope', contribution='background', reason='질문 밖', requirement_quote=''))
            for item in ('question', 'criterion')], meaning_challenges=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = review.reassess_source(None, run, dict(question='담당?', criterion='기관', source_ids=[]), dict(source=old),
        [dict(meaning_key='m', fields=['requirement_link'], reason='적용성만 재검토')])
    assert old == original and result['meanings'][1] == original['meanings'][1]
    assert all(result[k] == v for k, v in original.items() if k != 'meanings')
    assert all(result['meanings'][0][k] == v for k, v in original['meanings'][0].items() if k != 'required_for_requirement')


def test_new_contract_r_calls_only_contribution_and_reuses_direct_verdicts(monkeypatch):
    from app.knowledge.business_models import ContributionReviewCheck, ContributionSynthesisCheck
    from app.tests.unit.test_knowledge_business_local_review import meaning
    run, receipt = setup_direct_receipt(monkeypatch, states=('supported', 'supported'))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    calls = []
    source = dict(meanings=[meaning('m', required_for_requirement=True)], completeness='unknown', gaps=[],
        conjunctions=[], meaning_conjunctions=[], findings=[], source_batches=[], review_contract=review.SOURCE_APPLICATION_CONTRACT)
    def answer(service, current, stage, instruction, context, schema):
        assert stage == 'requirement_representation'
        assert 'Whole-candidate support' not in str(schema.model_json_schema())
        calls.append(context['mode']); run['units'].append(dict(id='r' + str(len(calls))))
        output = dict(checks=[], dependencies=[], source_challenges=[], meaning_challenges=[],
                      candidate_challenges=[], preservation_checks=[])
        if context['mode'] == 'meaning_batch':
            assert schema is ContributionReviewCheck
            assert len(context['whole_candidate_judgments']) == 2
            output.update(checks=[dict(meaning_key='m', status='represented', claim_ids=[run['claims'][0]['id']], reason='표현 위치')],
                          dependencies=[dict(meaning_key='m', premise_keys=[])])
        else:
            assert schema is ContributionSynthesisCheck
            output.update(satisfied=True, conjunctions_satisfied=True, reason='모의 결합', source_completeness='complete',
                          unselected_source_required=False, finding_resolutions=[])
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert calls == ['meaning_batch', 'requirement_join']
    assert result['checks'][0]['claim_support'][run['claims'][0]['id']] == 'supported'
    assert len(run['candidate_reviews']) == 1 and scope['join_succeeded']

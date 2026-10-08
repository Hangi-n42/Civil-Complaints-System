"""Local review failures must not become shared-scope errors or invented omissions."""
from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema, business_review as review, business_run, business_use
from app.knowledge.business_models import BusinessRunRequest
from app.tests.unit.test_knowledge_business_scope import block, scope_for


def meaning(key, **values):
    return dict(key=key, statement='기관은 신청을 접수한다.', source_status='supported', availability='provided',
        evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')], conditions=[], exceptions=[], period='',
        references=[], reason='원문', premise_keys=[], **values)


def judgments(keys, status='represented', ids=()):
    return dict(source_checks=[dict(meaning_key=k, required_for_requirement=True,
        field_checks=dict(statement='supported', conditions='not_applicable', exceptions='not_applicable',
            period='not_applicable', references='not_applicable'), reason='원문') for k in keys],
        checks=[dict(meaning_key=k, status=status, claim_ids=list(ids), incorrect_claim_ids=[], reason='대조') for k in keys],
        dependencies=[dict(meaning_key=k, premise_keys=[]) for k in keys], satisfied=True,
        conjunctions_satisfied=True, reason='전체', source_challenges=[], meaning_challenges=[], preservation_checks=[])


def local_run():
    b = dict(block('body', '기관은 신청을 접수한다.'), source_id='s')
    chunk = autoschema.chunks([b], 49152, 4096)[0]
    claims = [autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='접수', Tail='신청'), i)
              for i in range(2)]
    run = dict(recipe=dict(review_contract='requirement-local-review-v4', options=BusinessRunRequest(
        source_version_ids=['v'], requirement_ids=['r']).model_dump()), blocks=[b], chunks=[chunk], claims=claims,
        repairs=[], units=[], assessments=[], requirements=[dict(id='r', revision=1, source_ids=[])])
    return run


def test_join_preserves_mandatory_context_without_unrelated_packed_targets(monkeypatch):
    run = local_run()
    run['blocks'] = [dict(block('title', '등록 안내', path='h1:1'), source_id='s'),
        dict(block('parent', '신청인의 등록 업무', path='div:1::text(1)'), source_id='s'),
        dict(block('body', '기관은 신청을 접수한다.', path='div:1 > ul:1 > li:1'), source_id='s'),
        dict(block('note', '다만, 대리 신청은 신분증이 필요하다.', path='div:1 > ul:1 > li:2'), source_id='s'),
        dict(block('unrelated', '페이지 만족도를 평가해 주세요.', path='div:2 > p:1'), source_id='s')]
    original = deepcopy(run['blocks'])
    source = dict(meanings=[meaning('m')], completeness='unknown', gaps=[], conjunctions=[])
    contexts = []
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(_service, _run, stage, instruction, context, schema):
        contexts.append(deepcopy(context))
        run['units'].append(dict(id=str(len(contexts))))
        if context['mode'] == 'requirement_join':
            return None
        output = judgments(['m'], ids=[c['id'] for c in run['claims']])
        output['meaning_challenges'] = [dict(meaning_key='m', claim_ids=[], fields=['conditions'], reason='대리 신청 예외를 확인해야 한다.')]
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    review.represent(None, run, run['requirements'][0], source, [])
    local, joined = contexts
    assert 'unrelated' in {b['id'] for b in local['blocks']}
    assert {b['id'] for b in joined['blocks']} == {'title', 'parent', 'body', 'note'}
    assert len(joined['blocks']) == 4
    assert all(b['text'] == next(o['text'] for o in original if o['id'] == b['id']) for b in joined['blocks'])
    assert joined['findings'][0]['text'] == '대리 신청 예외를 확인해야 한다.'
    assert joined['local_judgments']['checks'][0]['reason'] == '대조'
    assert joined['local_judgments']['source_checks'][0]['reason'] == '원문'
    assert run['blocks'] == original


def test_common_scope_does_not_spread_bad_claim_and_free_json_is_not_typed():
    run = local_run()
    normal, mixed = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning(k) for k in ('common', 'bad', 'dependent')])
    source['meanings'][2]['premise_keys'] = ['bad']
    representation = judgments(['common', 'bad', 'dependent'])
    representation['dependencies'][2]['premise_keys'] = ['bad']
    representation['checks'][0]['claim_ids'] = [normal, mixed]
    representation['checks'][1].update(status='unknown', claim_ids=[mixed])
    assessment = dict(id='a', requirement_id='r', source=source, representation=representation, errors=[], issues=[])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    assert review.blocked(assessment) == ({'bad', 'dependent'}, [])
    assert business_use.eligibility(run)[0] == {normal}
    representation['source_challenges'] = [json.dumps(dict(meaning_key='bad', reason='free text'))]
    assert review.blocked(assessment)[1] == ['unscoped_source_challenge']


def test_reassessment_replaces_only_attributed_gaps_and_normalized_batch_state(monkeypatch):
    run = local_run()
    source = dict(meanings=[meaning('batch1:a'), meaning('batch2:b')], examined_block_ids=['body'],
        completeness='partial', gaps=[], conjunctions=[], meaning_conjunctions=[],
        meaning_gaps=[dict(meaning_keys=['batch1:a'], text='resolved'), dict(meaning_keys=['batch2:b'], text='remains')],
        source_batches=[dict(meaning_keys=['batch1:a'], output=dict(completeness='partial', meanings=[dict(key='a')]))])
    output = dict(meanings=[meaning('batch1:a')], examined_block_ids=['body'], completeness='complete',
                  gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[])
    run['units'] = [dict(id='u')]
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: deepcopy(output))
    corrected = review.reassess_source(None, run, {}, dict(source=source), [dict(meaning_key='batch1:a')])
    assert corrected['meaning_gaps'] == [source['meaning_gaps'][1]] and corrected['completeness'] == 'partial'
    source['meaning_gaps'].pop()
    corrected = review.reassess_source(None, run, {}, dict(source=source), [dict(meaning_key='batch1:a')])
    assert corrected['completeness'] == 'complete' and not corrected['meaning_gaps']
    assert source['meaning_gaps'] and corrected['reassessment_history']


def test_real_unmatched_pool_is_checked_before_missing_and_join_is_compact(monkeypatch):
    run = local_run()
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    normal, other = [c['id'] for c in run['claims']]
    from app.knowledge.discovery_profile import FrozenIndex
    monkeypatch.setattr(FrozenIndex, 'search', lambda *a: [dict(block_id=normal)])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    contexts = []
    def answer(_service, _run, stage, instruction, context, schema):
        contexts.append(context)
        run['units'].append(dict(id=str(len(contexts))))
        if context['mode'] == 'requirement_join':
            assert not context['claims'] and not context['blocks']
            assert 'source_batches' not in context['source']
            return judgments(['m'], ids=[other])
        ids = [c['id'] for c in context['claims']]
        return judgments(['m'], status='represented' if other in ids else 'missing', ids=[other] if other in ids else [])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert [c['id'] for c in contexts[1]['claims']] == [other]
    assert result['checks'][0]['status'] == 'represented' and not scope['pool_hash']
    assert scope['claim_ids'] == sorted([normal, other])


def test_one_local_failure_retains_independent_judgments_but_cannot_certify_join(monkeypatch):
    run = local_run()
    source = dict(meanings=[meaning(str(i)) for i in range(5)], examined_block_ids=['body'],
                  completeness='complete', gaps=[], conjunctions=[])
    run['blocks'].append(dict(block('separate', '기관은 신청을 접수한다.'), source_id='s'))
    source['meanings'][-1]['evidence'][0]['block_id'] = 'separate'
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        keys = [m['key'] for m in context['source']['meanings']]
        if keys == ['4'] or context['mode'] == 'requirement_join':
            return None
        return judgments(keys, ids=[run['claims'][0]['id']])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert [c['status'] for c in result['checks']] == ['represented'] * 4 + ['unknown']
    assert not result['satisfied'] and not scope['join_succeeded']


def test_independent_valid_patch_applies_with_new_scope_while_bad_patch_stays(monkeypatch):
    run = local_run()
    original = deepcopy(run['claims'])
    keys = ['good', 'bad']
    source = dict(meanings=[meaning(k) for k in keys], gaps=[], conjunctions=[])
    assessment = dict(id='a', source=source, representation=judgments(keys, 'incorrect'), errors=[], issues=[],
        actions=[dict(meaning_key=k, action='correct', claim_ids=[c['id']]) for k, c in zip(keys, original)])
    scope = scope_for(run['chunks'][0], run['blocks'][0]['text'])
    for e in [scope['evidence'], scope['meanings'][0]['evidence'], *[p['evidence'] for p in scope['meanings'][0]['participants']]]:
        for ref in e:
            ref['block_id'] = 'body'
    patches = [dict(meaning_key=k, target_id=c['id'], statement='기관은 신청을 접수한다.', head='기관', relation='접수', tail='신청',
        evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.' if k == 'good' else '없는 인용')],
        conditions=[], exceptions=[], period='', references=[], scope=scope) for k, c in zip(keys, original)]
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(patches=patches, unresolved=[]))
    assert business_run.repair(None, run, run['requirements'][0], assessment)
    assert run['claims'][1] == original[1]
    assert run['claims'][0]['interpretation']['target_status'] == 'addressed'
    assert not run['claims'][0]['interpretation']['errors']
    assert len(run['repairs'][0]['changes']) == 1 and run['repairs'][0]['errors']


def test_normal_and_incorrect_expressions_of_same_meaning_remain_distinct():
    result = review.summarize_local([meaning('m')], [judgments(['m'], ids=['normal']), judgments(['m'], 'incorrect', ['bad'])])
    check = result['checks'][0]
    assert check['status'] == 'represented' and check['claim_ids'] == ['normal']
    assert check['incorrect_claim_ids'] == ['bad'] and not result['satisfied']


def test_repair_protects_unknown_part_of_compound_claim_without_blocking_independent_target(monkeypatch):
    run = local_run()
    protected, independent = [c['id'] for c in run['claims']]
    representation = judgments(['unknown', 'fix'])
    representation['checks'][0].update(status='unknown', claim_ids=[protected])
    representation['checks'][1].update(status='incorrect', claim_ids=[protected, independent])
    assessment = dict(id='a', source=dict(meanings=[meaning(k) for k in ['unknown', 'fix']]),
        representation=representation, errors=[], issues=[], actions=[dict(
            meaning_key='fix', action='correct', claim_ids=[protected, independent])])
    def answer(_service, _run, stage, instruction, context, schema):
        assert context['tasks'][0]['target_id'] == independent
        assert context['tasks'][0]['meanings'][0]['claim_ids'] == [independent]
        assert [c['id'] for c in context['before']] == [independent]
        return dict(patches=[], unresolved=['contract probe'])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert not business_run.repair(None, run, run['requirements'][0], assessment)


@pytest.mark.parametrize('aggregate_action', ['maintain', 'correct'])
def test_repair_omits_only_past_source_history_and_corrects_shared_target_once(monkeypatch, aggregate_action):
    run = local_run()
    bad, normal = [c['id'] for c in run['claims']]
    keys = ['first', 'second']
    source = dict(meanings=[meaning(k) for k in keys], gaps=[], conjunctions=[],
        findings=[dict(id='current', text='현재 미해결 사항')],
        finding_resolutions=[dict(finding_id='current', status='unresolved')],
        resolution_history=[dict(previous_gaps=['과거 이력'])],
        reassessment_history=[dict(previous=['과거 의미'])])
    for row in source['meanings']:
        row['premise_keys'] = None
    original_source = deepcopy(source)
    representation = judgments(keys, ids=[normal])
    for row in representation['dependencies']:
        row['premise_keys'] = None
    for check in representation['checks']:
        check['incorrect_claim_ids'] = [bad]
        check['claim_support'] = {normal: 'supported', bad: 'incorrect'}
    assessment = dict(id='a', source=source, representation=representation, errors=[], issues=[],
        actions=[dict(meaning_key=k, action='correct', claim_ids=[bad], reason=k) for k in keys] +
                ([dict(meaning_key=k, action='maintain', claim_ids=[normal]) for k in keys]
                 if aggregate_action == 'maintain' else []),
        review_scope=dict(batches=[dict(unit_id='local', meaning_keys=keys, claim_ids=[bad, normal],
            provided_block_ids=['body'], output=representation, error=None)]))
    def answer(_service, _run, stage, instruction, context, schema):
        assert 'task당 패치는 최대 하나' in instruction
        assert len(context['tasks']) == 1 and context['tasks'][0]['target_id'] == bad
        assert schema.model_json_schema()['properties']['patches']['maxItems'] == 1
        assert {t['meaning_key'] for t in context['tasks'][0]['meanings']} == set(keys)
        assert all(t['review_records'][0]['unit_id'] == 'local' for t in context['tasks'][0]['meanings'])
        assert context['source'] == {k: v for k, v in original_source.items()
                                     if k not in {'resolution_history', 'reassessment_history'}}
        assert [c['id'] for c in context['before']] == [bad]
        assert [c['id'] for c in context['reuse_candidates']] == [normal]
        assert context['blocks'][0]['text'] == run['blocks'][0]['text']
        return dict(patches=[dict(meaning_key=keys[0], target_id=bad, reuse_claim_ids=[normal],
            evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')])], unresolved=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert business_run.repair(None, run, run['requirements'][0], assessment)
    assert source == original_source
    receipt = run['repairs'][0]
    assert len(receipt['changes']) == 1 and not receipt['errors']
    assert {t['meaning_key'] for t in receipt['targets']} == set(keys)
    assert receipt['status'] == 'applied_awaiting_recheck'
    assert not receipt['blocked_meaning_keys']
    assert run['assessments'] == []  # No semantic success is inferred by patch coverage.
    assert run['claims'][0]['superseded_by'] == [normal]


def test_numeric_identifier_ranking_is_opt_in():
    from app.knowledge.discovery_profile import FrozenIndex
    docs = [dict(id=str(n), text=f'1127 순번 {n} NODE ID ARS ID', file_id='v', source_group='v') for n in (13, 47)]
    ordinary = FrozenIndex(docs)
    numeric = FrozenIndex(docs, preserve_numbers=True)
    assert ordinary.tokens[0] == ordinary.tokens[1]
    assert numeric.search('1127 순번 47', {'13', '47'}, 1)[0]['block_id'] == '47'


def test_join_omitted_dependency_rows_keep_local_decisions_but_explicit_unknown_is_preserved(monkeypatch):
    run = local_run()
    source = dict(meanings=[meaning(k) for k in ['known', 'unknown']], examined_block_ids=['body'],
                  completeness='complete', gaps=[], conjunctions=[])
    for m in source['meanings']:
        m['premise_keys'] = None
    source['meaning_conjunctions'] = [dict(meaning_keys=['known', 'unknown'], text='두 의미의 결합 확인')]
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    for join_dependencies, expected in [([], []), ([dict(meaning_key='known', premise_keys=None)], None)]:
        def answer(_service, _run, stage, instruction, context, schema):
            run['units'].append(dict(id=str(len(run['units']))))
            result = judgments(['known', 'unknown'], ids=[run['claims'][0]['id']])
            result['dependencies'] = (deepcopy(join_dependencies) if context['mode'] == 'requirement_join' else
                [dict(meaning_key='known', premise_keys=[]), dict(meaning_key='unknown', premise_keys=None)])
            return result
        monkeypatch.setattr(business_run, 'json_call', answer)
        result, scope = review.represent(None, run, run['requirements'][0], source, [])
        dependencies = {d['meaning_key']: d['premise_keys'] for d in result['dependencies']}
        assert dependencies == dict(known=expected, unknown=None)
        assert scope['join_succeeded']


def test_join_receives_required_unknown_dependencies_without_unrelated_candidates(monkeypatch):
    run = local_run()
    normal, other = [c['id'] for c in run['claims']]
    keys = ['required_unknown', 'independent', 'optional_unknown']
    source = dict(meanings=[meaning(k) for k in keys], examined_block_ids=['body'],
                  completeness='complete', gaps=[], conjunctions=[])
    for m in source['meanings']:
        m['premise_keys'] = None
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        if context['mode'] == 'requirement_join':
            assert [c['id'] for c in context['claims']] == [normal]
            assert {b['id'] for b in context['blocks']} == {'body'}
        result = judgments(keys)
        result['source_checks'][2]['required_for_requirement'] = False
        for n, check in enumerate(result['checks']):
            check['claim_ids'] = [normal if n == 0 else other]
        result['dependencies'] = [dict(meaning_key=k, premise_keys=[] if k == 'independent' else None) for k in keys]
        if context['mode'] == 'requirement_join':
            assert context['review_meaning_keys'] == ['required_unknown']
        provided = context.get('review_meaning_keys', [m['key'] for m in context['source']['meanings']])
        for field in ('checks', 'source_checks', 'dependencies'):
            result[field] = [r for r in result[field] if r['meaning_key'] in provided]
        return result
    monkeypatch.setattr(business_run, 'json_call', answer)
    _, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert scope['join_succeeded']


def test_join_receives_the_actual_challenged_claim_not_only_the_normal_match(monkeypatch):
    run = local_run()
    normal, challenged = [c['id'] for c in run['claims']]
    run['claims'].append(autoschema.graph_record(run['chunks'][0], 'entity_relation',
        dict(Head='다른 기관', Relation='보관', Tail='다른 문서'), 2))
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete',
                  gaps=[], conjunctions=[])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        output = judgments(['m'], ids=[normal])
        if context['mode'] == 'requirement_join':
            assert {c['id'] for c in context['claims']} == {normal, challenged}
            assert context['blocks']
        else:
            output['meaning_challenges'] = [dict(meaning_key='m', claim_ids=[challenged], fields=['statement'],
                reason='표현 검토가 필요하다; 서버가 오류로 확정하지 않는다.')]
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    _, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert scope['join_succeeded']


def finding(fid='f', **values):
    return dict(id=fid, origin='source', kind='local_not_found', text='이 묶음에는 권한 규정이 없다.',
        meaning_keys=['m'], scope_meaning_keys=['m'], claim_ids=[], fields=[], provided_block_ids=['body'], **values)


def resolution(fid='f', status='resolved'):
    return dict(finding_id=fid, status=status, meaning_keys=['m'], claim_ids=[], fields=[],
        evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')], reason='실제 제공 원문 대조')


def current_source():
    return dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='unknown', gaps=['old gap'],
        conjunctions=[], meaning_gaps=[], meaning_conjunctions=[], findings=[finding()], source_batches=[],
        source_selection=dict(unselected_block_ids=[]), review_contract=review.CONTRACT)


def test_extra_join_row_keeps_independent_resolution_without_certifying_whole_join():
    run = local_run(); source = current_source()
    source['meanings'].append(meaning('outside'))
    cid = run['claims'][0]['id']
    compact = judgments(['m', 'outside'], ids=[cid])
    raw = judgments(['m', 'outside'], ids=[cid])
    raw['source_checks'][1]['field_checks']['statement'] = 'refuted'
    raw.update(source_completeness='complete', finding_resolutions=[resolution()])
    original = deepcopy(raw)
    result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m'}, {cid})
    review.resolve_findings(source, result, source['findings'], run['blocks'], [],
                            joined=joined, resolution_keys=valid['source_checks'], expression_keys=valid['checks'])
    assert not joined and not result['satisfied'] and source['completeness'] == 'partial'
    assert source['finding_resolutions'][0]['status'] == 'resolved'
    assert result['source_checks'][1] == compact['source_checks'][1]
    assert [c['meaning_key'] for c in result['meaning_challenges']] == ['outside']
    assert errors[0]['meaning_key'] == 'outside' and raw == original


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'claim_scope', 'dependency_scope', 'duplicate_dependency'])
def test_bad_join_row_and_its_dependents_stay_blocked_without_discarding_independent_row(fault):
    run = local_run(); source = current_source()
    source['meanings'] = [meaning(k) for k in ['m', 'bad', 'dependent']]
    source['findings'].append(dict(finding('bad-finding'), meaning_keys=['bad']))
    cid = run['claims'][0]['id']
    compact = judgments(['m', 'bad', 'dependent'], ids=[cid])
    compact['dependencies'][2]['premise_keys'] = ['bad']
    raw = deepcopy(compact)
    if fault == 'missing': raw['checks'].pop(1)
    if fault == 'duplicate': raw['source_checks'].append(deepcopy(raw['source_checks'][1]))
    if fault == 'claim_scope': raw['checks'][1]['claim_ids'] = ['unprovided']
    if fault == 'dependency_scope': raw['dependencies'][1]['premise_keys'] = ['invented']
    if fault == 'duplicate_dependency': raw['dependencies'].append(deepcopy(raw['dependencies'][1]))
    raw.update(source_completeness='complete', finding_resolutions=[resolution(),
        dict(resolution('bad-finding'), meaning_keys=['bad'])])
    result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m', 'bad', 'dependent'}, {cid})
    review.resolve_findings(source, result, source['findings'], run['blocks'], [],
                            joined=joined, resolution_keys=valid['source_checks'], expression_keys=valid['checks'])
    assert [r['status'] for r in source['finding_resolutions']] == (
        ['resolved', 'unresolved'] if fault == 'duplicate' else ['resolved', 'resolved'])
    assert result['checks'][1] == compact['checks'][1] and not joined
    assessment = dict(source=source, representation=result, errors=[], issues=[])
    assert review.blocked(assessment) == ({'bad', 'dependent'}, [])


def test_local_empty_is_a_complete_inspection_not_a_whole_requirement_gap(monkeypatch):
    run = local_run()
    bundle = run['chunks'][0]
    monkeypatch.setattr(review, 'source_selection', lambda *a: ([bundle], dict(unselected_block_ids=[])))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(*args):
        run['units'].append(dict(id='e'))
        return dict(examined_block_ids=['body'], inspection_status='complete', meanings=[], findings=[],
                    conjunctions=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    source = review.source(None, run, run['requirements'][0])
    assert source['completeness'] == 'unknown' and not source['gaps'] and not source['findings']
    assert not source['source_batches'][0]['errors']
    result = judgments([])
    result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(source, result, [], [], [], joined=True)
    # Even all delivered/inspected cannot invent a required meaning or satisfy it.
    assessment = dict(source=source, representation=result, errors=[], preservation_complete=True)
    assert business_run.requirement_completion(assessment)['status'] == 'partial'


def test_finding_resolution_requires_actual_source_and_keeps_raw_history():
    run = local_run()
    for valid in (False, True):
        source = current_source()
        result = judgments(['m'], ids=[run['claims'][0]['id']])
        result.update(source_completeness='complete', finding_resolutions=[resolution()])
        review.resolve_findings(source, result, source['findings'], run['blocks'] if valid else [], [], joined=True)
        assert source['completeness'] == ('complete' if valid else 'partial')
        assert bool(result['meaning_challenges']) is not valid
        assert source['findings'][0]['text'] and source['resolution_history'][0]['previous_gaps'] == ['old gap']
    source = current_source()
    result = judgments(['m'])
    result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(source, result, source['findings'], run['blocks'], [], joined=True)
    assert source['completeness'] == 'partial' and result['meaning_challenges']


def test_source_reassessment_typed_gap_survives_the_join_without_free_gap_duplicate(monkeypatch):
    run = local_run(); run['units'] = [dict(id='new-e')]
    source = current_source()
    output = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='partial', gaps=[],
        conjunctions=[], meaning_gaps=[dict(meaning_keys=['m'], text='필수 참조 상세가 제공되지 않았다.')], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: deepcopy(output))
    revised = review.reassess_source(None, run, {}, dict(source=source), [dict(meaning_key='m')])
    assert len(revised['findings']) == 1 and revised['findings'][0]['text'] == output['meaning_gaps'][0]['text']
    result = judgments(['m']); row = resolution(revised['findings'][0]['id'], 'required_gap')
    row['reason'] = output['meaning_gaps'][0]['text']
    result.update(source_completeness='complete', finding_resolutions=[row])
    review.resolve_findings(revised, result, revised['findings'], run['blocks'], [], joined=True)
    assert revised['meaning_gaps'] == output['meaning_gaps'] and revised['completeness'] == 'partial'
    assert source['gaps'] == ['old gap']


def test_claim_finding_cannot_be_dropped_or_reassigned_to_a_normal_sibling():
    run = local_run(); normal, bad = [c['id'] for c in run['claims']]
    source = current_source(); f = finding(); f.update(origin='representation', claim_ids=[bad])
    result = judgments(['m'], ids=[normal]); result['checks'][0]['incorrect_claim_ids'] = [bad]
    row = resolution(status='claim_error'); row['claim_ids'] = [normal]
    result.update(source_completeness='complete', finding_resolutions=[row])
    review.resolve_findings(source, result, [f], run['blocks'], run['claims'], joined=True)
    assert result['meaning_challenges'][0]['claim_ids'] == [bad]
    assert source['finding_resolutions'][0]['status'] == 'unresolved'
    row['claim_ids'] = [bad]; result['meaning_challenges'] = []
    review.resolve_findings(source, result, [f], run['blocks'], run['claims'], joined=True)
    assert not result['meaning_challenges'] and source['finding_resolutions'][0]['status'] == 'claim_error'


def test_ranked_prose_unread_cannot_be_excluded_by_join_false_but_exact_rows_can():
    result = dict(unselected_source_required=False)
    source = dict(source_selection=dict(unselected_block_ids=['other'], exact_row_excluded_block_ids=[]))
    assert review.needs_source_read(source, result)
    source['source_selection']['exact_row_excluded_block_ids'] = ['other']
    assert not review.needs_source_read(source, result)
    assert review.needs_source_read(source, dict(unselected_source_required=None))


def test_exact_row_selection_preserves_version_headings_and_does_not_hardcode_values():
    run = local_run()
    blocks = []
    for version in ['v1', 'v2']:
        blocks.append(dict(block(version + '-title', '조회 기준일: 2026.10.06', path='h1:1'),
                           source_version_id=version, source_id='s'))
        for number in (13, 47):
            fields = dict(ROUTE_ID=987, 순번=number)
            b = dict(block(f'{version}-{number}', json.dumps(fields)), source_version_id=version, source_id='s')
            b['locator']['fields'] = fields
            blocks.append(b)
    run['blocks'] = blocks
    bundles, selection = review.source_selection(run, dict(source_ids=[], question='ROUTE_ID 987 순번 47'))
    assert set(selection['exact_row_excluded_block_ids']) == {'v1-13', 'v2-13'}
    assert set(selection['row_lookup']['matched_block_ids']) == {'v1-47', 'v2-47'}
    assert all(any(b['id'].endswith('-title') for b in c['blocks']) for c in bundles)


def test_nonessential_local_missing_does_not_scan_the_unmatched_pool(monkeypatch):
    run = local_run(); normal, other = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    from app.knowledge.discovery_profile import FrozenIndex
    monkeypatch.setattr(FrozenIndex, 'search', lambda *a: [dict(block_id=normal)])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    seen = []
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        seen.extend(c['id'] for c in context['claims'])
        output = judgments(['m'], status='missing')
        output['source_checks'][0]['required_for_requirement'] = False
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert other not in seen and result['checks'][0]['status'] == 'missing'
    assert '국소 미발견' in result['checks'][0]['reason']


def test_exact_nonmatching_rows_are_recorded_without_hiding_unstructured_candidates(monkeypatch):
    run = local_run(); run['claims'][0].update(role='structured_row', raw=dict(fields=dict(순번=13)))
    normal, other = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[],
                  source_selection=dict(row_lookup=dict(bindings={'순번': ['47']}, matched_block_ids=['body'])))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    seen = []
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        seen.extend(c['id'] for c in context['claims'])
        return judgments(['m'], status='missing')
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert normal not in seen and other in seen
    assert scope['exact_row_exclusions']['m'] == [normal]
    assert result['checks'][0]['status'] == 'missing' and scope['pool_hash']


def test_partial_contributions_reach_join_as_actual_candidates_without_automatic_success(monkeypatch):
    from app.knowledge.discovery_profile import FrozenIndex
    run = local_run(); first, second = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    monkeypatch.setattr(FrozenIndex, 'search', lambda *a: [dict(block_id=first)])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    for joined in [False, True]:
        def answer(_service, _run, stage, instruction, context, schema):
            run['units'].append(dict(id=str(len(run['units']))))
            ids = [c['id'] for c in context['claims']]
            if context['mode'] == 'requirement_join':
                assert set(ids) == {first, second} and context['blocks']
                assert context['local_judgments']['checks'][0]['status'] == 'partial'
                return judgments(['m'], ids=ids) if joined else None
            assert len(ids) == 1
            return judgments(['m'], status='partial', ids=ids)
        monkeypatch.setattr(business_run, 'json_call', answer)
        result, scope = review.represent(None, run, run['requirements'][0], source, [])
        assert set(result['checks'][0]['claim_ids']) == {first, second}
        assert result['checks'][0]['status'] == ('represented' if joined else 'partial')
        assert result['satisfied'] is joined and bool(scope['pool_hash']) is not joined


def test_required_unread_prose_is_inspected_before_the_first_candidate_review(monkeypatch):
    run = local_run()
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    from app.knowledge import business_store
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    for exact_row_exclusion in [False, True]:
        stages = []
        def inspect(_service, _run, _requirement, *, previous=None):
            stages.append('additional E' if previous else 'initial E')
            return dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[],
                conjunctions=[], source_selection=dict(unselected_block_ids=[] if previous else ['unread'],
                    exact_row_excluded_block_ids=['unread'] if exact_row_exclusion else []))
        def represent(_service, _run, _requirement, source, context):
            stages.append('R')
            assert not source['source_selection']['unselected_block_ids'] or exact_row_exclusion
            return judgments(['m'], ids=[run['claims'][0]['id']]), dict(claim_ids=[run['claims'][0]['id']])
        monkeypatch.setattr(review, 'source', inspect)
        monkeypatch.setattr(review, 'represent', represent)
        business_run.assess(None, run, run['requirements'][0])
        assert stages == (['initial E', 'R'] if exact_row_exclusion else ['initial E', 'additional E', 'R'])


def test_keyed_source_batch_error_uses_existing_reassessment_without_erasing_history(monkeypatch):
    from app.knowledge import business_store
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    for corrected_status, call_failed in [('supported', False), ('unknown', False), ('supported', True)]:
        run = local_run()
        errors = [dict(meaning_key='scoped', reason='meaning_outside_local_target')]
        if call_failed:
            errors.append('local_source_call_failed')
        source = dict(meanings=[meaning('scoped'), meaning('normal')], examined_block_ids=['body'],
            completeness='unknown', gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[],
            findings=[], review_contract=review.CONTRACT, source_batches=[dict(errors=deepcopy(errors))])
        original = deepcopy(source)
        def represent(_service, _run, _requirement, value, context):
            result = judgments(['scoped', 'normal'])
            for check, claim in zip(result['checks'], run['claims']):
                check['claim_ids'] = [claim['id']]
            result['source_completeness'] = 'complete'
            review.resolve_findings(value, result, [], run['blocks'], run['claims'], joined=True)
            return result, dict(claim_ids=[c['id'] for c in run['claims']])
        monkeypatch.setattr(review, 'represent', represent)
        initial = business_run.assess(None, run, run['requirements'][0], source=source)
        assert [c['meaning_key'] for c in initial['source_record_challenges']] == ['scoped']
        assert review.blocked(initial) == ({'scoped'}, [])
        assert initial['status'] == 'partial' and source == original
        def reconsider(_service, _run, stage, instruction, context, schema):
            assert stage == 'source_reassessment'
            assert [m['key'] for m in context['previous']['meanings']] == ['scoped']
            assert context['challenges'] == initial['source_record_challenges']
            run['units'].append(dict(id='reassessed'))
            corrected = meaning('scoped')
            corrected['source_status'] = corrected_status
            return dict(meanings=[corrected], examined_block_ids=['body'], completeness='complete',
                gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[])
        monkeypatch.setattr(business_run, 'json_call', reconsider)
        corrected = review.reassess_source(None, run, run['requirements'][0], initial,
                                           initial['source_record_challenges'])
        final = business_run.assess(None, run, run['requirements'][0], source=corrected, phase='source_reassessment')
        assert corrected['reassessed_meaning_keys'] == ['scoped']
        assert corrected['source_batches'] == original['source_batches']
        assert not final['source_record_challenges'] and not final['errors']
        assert final['source']['gaps'] == (['local_source_call_failed'] if call_failed else [])
        assert final['status'] == ('satisfied' if corrected_status == 'supported' and not call_failed else 'partial')
        assert final['source']['meanings'][1] == initial['source']['meanings'][1]


def test_only_join_requires_explicit_source_completeness_without_promoting_unknown(monkeypatch):
    import pytest
    from pydantic import ValidationError
    run = local_run()
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    for completeness, unread_required in [('complete', False), ('complete', True), ('complete', None),
                                          ('partial', False), ('unknown', False)]:
        source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='unknown',
            gaps=[], conjunctions=[], findings=[], source_batches=[], review_contract=review.CONTRACT,
            source_selection=dict(unselected_block_ids=['other_row'], exact_row_excluded_block_ids=['other_row']))
        def answer(_service, _run, stage, instruction, context, schema):
            run['units'].append(dict(id=str(len(run['units']))))
            output = judgments(context.get('review_meaning_keys', ['m']), ids=[run['claims'][0]['id']])
            if context['mode'] == 'requirement_join':
                assert schema.model_fields['source_completeness'].is_required()
                assert schema.model_fields['unselected_source_required'].is_required()
                with pytest.raises(ValidationError):
                    schema.model_validate(output)
                output['source_completeness'] = completeness
                with pytest.raises(ValidationError):
                    schema.model_validate(output)
                output['unselected_source_required'] = unread_required
            else:
                assert not {'satisfied', 'conjunctions_satisfied', 'reason', 'source_completeness', 'unselected_source_required'} & schema.model_fields.keys()
                assert 'satisfied' not in instruction
            return schema.model_validate(output).model_dump()
        monkeypatch.setattr(business_run, 'json_call', answer)
        result, scope = review.represent(None, run, run['requirements'][0], source, [])
        assert result['satisfied'] and scope['join_succeeded']
        assert review.needs_source_read(source, result) is (unread_required is not False)
        assert source['completeness'] == ('complete' if completeness == 'complete' and unread_required is False else 'partial')


def test_local_error_reason_and_receipt_reach_repair_and_recheck(monkeypatch):
    from app.knowledge import business_store
    run = local_run()
    cid = run['claims'][0]['id']
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    local = judgments(['m'], 'incorrect', [cid])
    local['checks'][0]['reason'] = '국소 원문 대조에서 확인한 후보 표현 오류'
    local['review_unit_id'] = 'local-error-unit'
    merged = review.summarize_local(source['meanings'], [local])
    assert merged['checks'][0]['reason'] == local['checks'][0]['reason']
    assert merged['checks'][0]['review_unit_ids'] == ['local-error-unit']
    receipt = dict(unit_id='local-error-unit', meaning_keys=['m'], claim_ids=[cid],
        provided_block_ids=['body'], output=local, error=None)
    scope = scope_for(run['chunks'][0], run['blocks'][0]['text'])
    for refs in [scope['evidence'], scope['meanings'][0]['evidence'],
                 *[p['evidence'] for p in scope['meanings'][0]['participants']]]:
        for ref in refs: ref['block_id'] = 'body'
    contexts = []
    def represent(_service, _run, requirement, current_source, context):
        contexts.append(deepcopy(context))
        if not context:
            return deepcopy(merged), dict(batches=[receipt], claim_ids=[cid], failures=[])
        target = context[0]['targets'][0]
        assert target['reason'] == local['checks'][0]['reason']
        assert target['review_records'] == [dict(unit_id='local-error-unit',
            check=local['checks'][0], provided_block_ids=['body'])]
        result = judgments(['m'], ids=[cid])
        result['preservation_checks'] = [dict(target_id=cid, status='preserved',
            before_normal_meanings=['신청 접수'], after_locations=[cid], reason='보존 대조')]
        return result, dict(batches=[], claim_ids=[cid], failures=[])
    def answer(_service, _run, stage, instruction, context, schema):
        assert stage == 'requirement_repair'
        assert context['tasks'][0]['meanings'][0]['review_records'][0]['check']['reason'] == local['checks'][0]['reason']
        assert context['before'][0]['id'] == cid and context['blocks'][0]['id'] == 'body'
        return dict(patches=[dict(meaning_key='m', target_id=cid, statement='기관은 신청을 접수한다.',
            head='기관', relation='접수', tail='신청', evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')],
            conditions=[], exceptions=[], period='', references=[], scope=scope)], unresolved=[])
    monkeypatch.setattr(review, 'represent', represent)
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    assert business_run.repair(None, run, run['requirements'][0], assessment)
    business_run.assess(None, run, run['requirements'][0], source=source, phase='after_repair')
    assert len(contexts) == 2 and contexts[1]


def test_global_incompleteness_does_not_veto_independent_approval_but_scoped_faults_do():
    run = local_run()
    for i in range(2, 5):
        run['claims'].append(autoschema.graph_record(run['chunks'][0], 'entity_relation',
            dict(Head='기관', Relation='접수', Tail=f'신청{i}'), i))
    keys = ['independent', 'bad', 'dependent', 'unknown', 'free_only']
    ids = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning(k) for k in keys])
    representation = judgments(keys)
    for row, cid in zip(representation['checks'], ids): row['claim_ids'] = [cid]
    representation['checks'][3]['status'] = 'unknown'
    representation['dependencies'][2]['premise_keys'] = ['bad']
    representation['source_challenges'] = ['요구 전체 범위 미확정']
    assessment = dict(id='incomplete', requirement_id='r', source=source, representation=representation,
        errors=[], issues=[dict(meaning_key='bad', reason='특정 의미의 근거 오류')])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    assert not business_use.eligibility(run)[0]  # A free error is never permission on its own.
    assert review.blocked(assessment, include_global=False) == (
        {'bad', 'dependent', 'unknown'}, ['unscoped_source_challenge'])
    requirement = dict(id='valid', revision=1, source_ids=[])
    run['requirements'].append(requirement)
    valid_source = dict(meanings=[meaning(k) for k in keys[:4]])
    valid = dict(id='valid', requirement_id='valid', source=valid_source, representation=judgments(keys[:4]), errors=[], issues=[])
    for row, cid in zip(valid['representation']['checks'], ids): row['claim_ids'] = [cid]
    valid['input_fingerprint'] = business_run.assessment_fingerprint(run, requirement, valid_source)
    run['assessments'].append(valid)
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {ids[0]} and ids[4] not in eligible
    assert 'meaning_dependency_blocked' in blocked[ids[2]]
    assert 'unresolved_meaning_not_false' in blocked[ids[3]]


def test_only_completed_local_absence_with_actual_supported_anchors_can_be_not_required():
    run = local_run()
    for variant in ['valid', 'failed', 'unread', 'external', 'wrong_blocks', 'unsupported', 'missing_anchor']:
        source = current_source()
        f = source['findings'][0]
        f.update(unit_id='source-unit', meaning_keys=[], scope_meaning_keys=[])
        batch = dict(unit_id='source-unit', target_block_ids=['body'], provided_block_ids=['body'], errors=[],
                     output=dict(inspection_status='complete'))
        source['source_batches'] = [batch]
        result = judgments(['m'])
        row = resolution(status='not_required'); row['evidence'] = []
        result.update(source_completeness='complete', finding_resolutions=[row])
        blocks = run['blocks']
        if variant == 'failed': batch['errors'] = ['source call failed']
        if variant == 'unread': batch['output']['inspection_status'] = 'partial'
        if variant == 'external': f['kind'] = 'reference_missing_here'
        if variant == 'wrong_blocks': batch['provided_block_ids'] = ['elsewhere']
        if variant == 'unsupported': result['source_checks'][0]['field_checks']['statement'] = 'unknown'
        if variant == 'missing_anchor': blocks = []
        review.resolve_findings(source, result, [f], blocks, [], joined=True)
        assert source['finding_resolutions'][0]['status'] == ('not_required' if variant == 'valid' else 'unresolved')
        assert source['completeness'] == ('complete' if variant == 'valid' else 'partial')
        assert source['source_batches'][0] == batch and source['findings'][0] == f


def test_semantic_groups_preserve_connections_without_inferring_them_from_shared_addresses():
    source = dict(meanings=[meaning(k) for k in ['a', 'b', 'c', 'overlap', 'independent']])
    for i, m in enumerate(source['meanings']):
        m['evidence'] = [dict(block_id=str(i), quote=str(i), start_char=0, end_char=10)]
    source['meanings'][1]['premise_keys'] = ['a']
    source['meaning_conjunctions'] = [dict(meaning_keys=['b', 'c'], text='전제 연결')]
    source['meanings'][3]['evidence'] = [dict(block_id='2', quote='겹치는 실제 구간', start_char=5, end_char=15)]
    assert [[m['key'] for m in group] for group in review.meaning_groups(source)] == [
        ['a', 'b', 'c'], ['overlap'], ['independent']]
    source['meanings'][4]['evidence'] = deepcopy(source['meanings'][0]['evidence'])
    source['meanings'][4]['premise_keys'] = None
    assert [[m['key'] for m in group] for group in review.meaning_groups(source)] == [
        ['a', 'b', 'c'], ['overlap'], ['independent']]
    assert source['meanings'][4]['premise_keys'] is None


def test_local_batch_uses_actual_capacity_after_grouping_and_accounts_for_every_candidate(monkeypatch):
    run = local_run()
    for i in range(2, 12):
        run['claims'].append(autoschema.graph_record(run['chunks'][0], 'entity_relation',
            dict(Head='기관', Relation='접수', Tail=f'신청{i}'), i))
    source = dict(meanings=[meaning(str(i)) for i in range(6)], examined_block_ids=['body'],
                  completeness='complete', gaps=[], conjunctions=[],
                  meaning_conjunctions=[dict(meaning_keys=[str(i) for i in range(6)], text='실제 함께 판단할 연결')])
    from app.knowledge.discovery_profile import FrozenIndex
    monkeypatch.setattr(FrozenIndex, 'search', lambda *a: [dict(block_id=c['id']) for c in run['claims']])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    local_contexts = []
    # Size the actual produced message. The test budget stands in for a small context.
    def estimate(messages, schema, max_tokens):
        payload = json.loads(messages[-1]['content'])
        return 49153 if len(payload['claims']) > 7 else 40000
    monkeypatch.setattr(business_run, 'request_tokens', estimate)
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        keys = context.get('review_meaning_keys', [m['key'] for m in context['source']['meanings']])
        if context['mode'] == 'meaning_batch':
            local_contexts.append(context)
            return judgments(keys, 'missing')
        return judgments(keys, 'missing')
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert [len(c['claims']) for c in local_contexts] == [6, 6]
    assert all(len(c['source']['meanings']) == 6 for c in local_contexts)  # No fixed four-meaning split.
    assert {c['id'] for packet in local_contexts for c in packet['claims']} == {c['id'] for c in run['claims']}
    assert all(c['status'] == 'missing' for c in result['checks']) and not scope['failures']


def test_source_reuses_only_local_unverified_interpretations_without_overriding_evidence(monkeypatch):
    run = local_run()
    record = dict(contract=autoschema.SCOPE_CONTRACT, semantic_status='unverified',
        evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')],
        meanings=[dict(subject='기관', action='접수', address_errors=['unresolved qualifier'])], errors=['unresolved qualifier'])
    for claim in run['claims']: claim['interpretation'] = deepcopy(record)
    unrelated = deepcopy(run['claims'][0]); unrelated['id'] = 'unrelated'
    unrelated['interpretation']['evidence'][0]['block_id'] = 'outside'
    run['claims'].append(unrelated)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(review, 'source_selection', lambda *a: ([run['chunks'][0]], dict(unselected_block_ids=[])))
    def answer(_service, _run, stage, instruction, context, schema):
        refs = context['unverified_interpretations']
        assert len(refs) == 1 and refs[0]['claim_ids'] == [c['id'] for c in run['claims'][:2]]
        assert refs[0]['interpretation']['semantic_status'] == 'unverified'
        assert refs[0]['interpretation']['errors'] == ['unresolved qualifier']
        assert '원문을 독립적으로 읽어' in instruction and context['blocks'][0]['text'] == run['blocks'][0]['text']
        run['units'].append(dict(id='source'))
        return dict(examined_block_ids=['body'], inspection_status='complete', meanings=[], findings=[], conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    result = review.source(None, run, run['requirements'][0])
    assert result['meanings'] == [] and result['completeness'] == 'unknown'
    assert run['claims'][0]['interpretation'] == record


def test_repair_tasks_keep_missing_meanings_separate_and_bound_patch_count(monkeypatch):
    import pytest
    run = local_run()
    ids = [c['id'] for c in run['claims']]
    keys = ['incorrect', 'missing1', 'missing2']
    assessment = dict(id='a', source=dict(meanings=[meaning(k) for k in keys]),
        representation=judgments(keys), errors=[], issues=[], actions=[
            dict(meaning_key=keys[0], action='correct', claim_ids=ids),
            *[dict(meaning_key=k, action='recover', claim_ids=[]) for k in keys[1:]]])
    def answer(_service, _run, stage, instruction, context, schema):
        assert [t['target_id'] for t in context['tasks']] == ids + [None, None]
        assert [t['meanings'][0]['meaning_key'] for t in context['tasks'][-2:]] == keys[1:]
        assert schema.model_json_schema()['properties']['patches']['maxItems'] == 4
        patch = dict(meaning_key=keys[0], target_id=ids[0], statement='', head='', relation='', tail='',
            evidence=[], conditions=[], exceptions=[], period='', references=[])
        with pytest.raises(ValueError, match='at most 4'):
            schema.model_validate(dict(patches=[patch] * 5, unresolved=[]))
        return dict(patches=[], unresolved=['contract-only test'])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert not business_run.repair(None, run, run['requirements'][0], assessment)


def test_proposal_coverage_does_not_cover_another_candidate_or_missing_meaning(monkeypatch):
    run = local_run()
    ids = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning(k) for k in ['shared', 'missing']])
    assessment = dict(id='a', source=source, representation=judgments(['shared', 'missing']),
        errors=[], issues=[], actions=[dict(meaning_key='shared', action='correct', claim_ids=ids),
                                      dict(meaning_key='missing', action='recover', claim_ids=[])])
    scope = scope_for(run['chunks'][0], run['blocks'][0]['text'])
    for refs in [scope['evidence'], scope['meanings'][0]['evidence'],
                 *[p['evidence'] for p in scope['meanings'][0]['participants']]]:
        for ref in refs:
            ref['block_id'] = 'body'
    patch = dict(meaning_key='shared', target_id=ids[0], statement='기관은 신청을 접수한다.',
        head='기관', relation='접수', tail='신청', evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')],
        conditions=[], exceptions=[], period='', references=[], scope=scope)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(patches=[patch], unresolved=[]))
    before = deepcopy(run['claims'])
    assert not business_run.repair(None, run, run['requirements'][0], assessment)
    receipt = run['repairs'][0]
    assert len(receipt['proposed_changes']) == 1
    assert set(receipt['blocked_meaning_keys']) == {'shared', 'missing'}
    assert run['claims'] == before and not receipt['changes']


def test_event_link_selection_uses_complete_raw_endpoints_and_overlapping_source_addresses():
    ref = dict(source_version_id='v', parse_run_id='p', block_id='body', start_char=10, end_char=30)
    events = [dict(id='first', role='event_entity', raw=dict(Event='기관이 고지서를 교부한다.'), evidence=[ref]),
              dict(id='second', role='event_entity', raw=dict(Event='신청자가 납부한다.'), evidence=[ref])]
    link = dict(id='link', role='event_relation', raw=dict(Head=events[0]['raw']['Event'],
        Relation='before', Tail=events[1]['raw']['Event']), evidence=[dict(ref, start_char=0, end_char=40, precision='chunk')],
        interpretation=dict(errors=['unresolved_item_address']))
    select = lambda rows, ids={'first', 'second'}: review.connected_event_candidates(rows, ids, {'body'})
    assert select(events + [link]) == {'link'}
    assert not select(events + [link], {'first'})
    for field, value in [('source_version_id', 'other'), ('parse_run_id', 'other'), ('block_id', 'other'),
                         ('start_char', 30), ('parse_run_id', None)]:
        changed = dict(link, evidence=[dict(link['evidence'][0], **{field: value})])
        assert not select(events + [changed])
    named = dict(link, raw=dict(link['raw'], Head='기관'))
    assert not select(events + [named])
    # Selection is not a semantic judgment: an unsupported relation remains a candidate to review.
    unverified = dict(link, raw=dict(link['raw'], Relation='causes'))
    assert select(events + [unverified]) == {'link'}
    assert link['interpretation']['errors'] and link['evidence'][0]['precision'] == 'chunk'


def test_targeted_recheck_rejects_changed_pool_source_or_dependencies_before_model_call(monkeypatch):
    import pytest
    run = local_run()
    source = dict(meanings=[meaning('m')])
    assessment = dict(id='a', requirement_id='r', source=deepcopy(source), review_scope={})
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source, {})
    run.update(model_identity={}, assessments=[assessment])
    monkeypatch.setattr(review, 'represent', lambda *a, **k: pytest.fail('Invalid reuse reached the model boundary'))
    for change in ['raw', 'evidence', 'dependencies', 'unknown_key']:
        current = deepcopy(run); provided = deepcopy(source); keys = ['m']
        if change == 'raw': current['claims'][0]['raw']['Head'] = '다른 기관'
        elif change == 'evidence': provided['meanings'][0]['evidence'][0]['quote'] = '다른 원문'
        elif change == 'dependencies': provided['meanings'][0]['premise_keys'] = ['other']
        else: keys = ['not-in-source']
        with pytest.raises(ValueError, match='제한 재검수'):
            business_run.assess(None, current, current['requirements'][0], source=provided,
                                previous_run=run, recheck_meaning_keys=keys)


def test_join_receives_compact_changes_and_requires_explicit_preservation_for_each_target(monkeypatch):
    import pytest
    run = local_run()
    before, replacement = deepcopy(run['claims'])
    after = dict(before, superseded_by=[replacement['id']])
    context = [dict(id='repair', targets=[dict(meaning_key='m', reason='observed expression error')],
        preserve_meanings=[meaning('normal')], changes=[dict(before=before, after=after,
            replacements=[replacement], meaning_key='m')])]
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    seen = []
    def answer(_service, _run, stage, instruction, payload, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        output = judgments(['m'], ids=[replacement['id']])
        if payload['mode'] == 'requirement_join':
            assert payload['repair_context'] == context
            assert payload['local_preservation_checks'] == []
            assert schema.model_json_schema()['properties']['preservation_checks']['minItems'] == 1
            assert 'preservation_checks' in schema.model_json_schema()['required']
            output.update(source_completeness='complete', unselected_source_required=False)
            with pytest.raises(ValueError):
                schema.model_validate(output)
            output['preservation_checks'] = [dict(target_id=before['id'], status='unknown',
                before_normal_meanings=['접수'], after_locations=[], reason='보존 확인 불가')]
            normalized = schema.model_validate(output).model_dump()
            # Conditional join schemas must retain exact provided-view evidence selection.
            request = business_run.json_request(run, stage, instruction, payload, schema)
            assert request['evidence_reference_map']
            seen.append(normalized['preservation_checks'])
            return normalized
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    result, _ = review.represent(None, run, run['requirements'][0], source, context)
    assert result['preservation_checks'] == seen[0]
    assert result['preservation_checks'][0]['status'] == 'unknown'


@pytest.mark.parametrize("echo_requested_keys", [False, True])
def test_unresolved_finding_keys_are_not_expression_checks_and_keep_context(monkeypatch, echo_requested_keys):
    run = local_run()
    finding = dict(id='e1:missing', origin='source', kind='local_not_found',
        text='접수 기간의 명시를 확인하지 못함', meaning_keys=['unresolved:period'],
        scope_meaning_keys=[], claim_ids=[], fields=[], provided_block_ids=['body'], unit_id='source-unit')
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], review_contract=review.CONTRACT,
        completeness='partial', gaps=[], conjunctions=[], findings=[deepcopy(finding)], source_batches=[])
    source['meanings'][0]['premise_keys'] = None
    from app.knowledge.discovery_profile import FrozenIndex
    searches = []
    original_search = FrozenIndex.search
    def search(index, query, *args, **kwargs):
        searches.append(query)
        return original_search(index, query, *args, **kwargs)
    monkeypatch.setattr(FrozenIndex, 'search', search)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    joins = []
    def answer(_service, _run, stage, instruction, payload, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        keys = payload['review_meaning_keys'] if payload['mode'] == 'requirement_join' and echo_requested_keys else ['m']
        output = judgments(keys, ids=[run['claims'][0]['id']])
        for dependency in output['dependencies']:
            dependency['premise_keys'] = None
        if payload['mode'] == 'requirement_join':
            joins.append(payload)
            output.update(source_completeness='partial', unselected_source_required=False,
                finding_resolutions=[dict(finding_id=finding['id'], status='unresolved', meaning_keys=[],
                    claim_ids=[], fields=[], evidence=[], reason='자료 범위 확인 미완료')])
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert scope['join_succeeded']
    assert joins[0]['review_meaning_keys'] == ['m']
    assert joins[0]['findings'][0]['meaning_keys'] == finding['meaning_keys']
    assert finding['text'] in searches  # Unknown attribution must still select actual source context.
    assert source['findings'] == [finding]
    assert source['finding_resolutions'][0]['status'] == 'unresolved'
    assert source['completeness'] == 'partial'
    assert result['meaning_challenges']
    assert {c['meaning_key'] for c in result['checks']} == {'m'}


def test_filtering_expression_keys_keeps_unresolved_required_premise_and_conjunction(monkeypatch):
    from app.knowledge import business_store
    run = local_run()
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[],
        conjunctions=[], meaning_conjunctions=[dict(meaning_keys=['m', 'unresolved:approval'],
            text='접수 의미의 필수 승인 전제는 미확정이다.')])
    source['meanings'][0]['premise_keys'] = ['unresolved:approval']
    original = deepcopy(source)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    def answer(_service, _run, stage, instruction, payload, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        result = judgments(['m'], ids=[run['claims'][0]['id']])
        if payload['mode'] == 'requirement_join':
            assert payload['review_meaning_keys'] == ['m']
            assert payload['source']['meaning_conjunctions'] == original['meaning_conjunctions']
            assert payload['source']['meanings'][0]['premise_keys'] == ['unresolved:approval']
            # A join omitting dependency rows cannot erase the actual local unresolved premise.
            result.update(source_completeness='complete', unselected_source_required=False, dependencies=[])
        else:
            result['dependencies'][0]['premise_keys'] = ['unresolved:approval']
        return result
    monkeypatch.setattr(business_run, 'json_call', answer)
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    assert source == original
    assert assessment['source']['meaning_conjunctions'] == original['meaning_conjunctions']
    assert assessment['representation']['dependencies'] == [dict(meaning_key='m', premise_keys=['unresolved:approval'])]
    assert '의미 전제 범위 오류' in assessment['errors']
    assert assessment['status'] == 'partial'


def test_empty_represented_keeps_completed_missing_and_source_resolution_independent():
    run = local_run(); source = current_source()
    compact = judgments(['m'], status='missing')
    compact['dependencies'][0]['premise_keys'] = None
    raw = judgments(['m'])
    raw.update(dependencies=[], source_completeness='complete', finding_resolutions=[resolution()])
    result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m'}, set(), {'m'})
    review.resolve_findings(source, result, source['findings'], run['blocks'], [], joined=joined,
        resolution_keys=valid['source_checks'], expression_keys=valid['checks'], source_joined=True)
    assert not joined and not result['satisfied']
    assert result['checks'][0]['status'] == 'missing' and result['dependencies'][0]['premise_keys'] is None
    assert source['completeness'] == 'complete' and source['finding_resolutions'][0]['status'] == 'resolved'
    assert not result['meaning_challenges'] and valid['retained_missing'] == {'m'}
    assert review.blocked(dict(source=source, representation=result, errors=[], issues=[])) == (set(), [])


@pytest.mark.parametrize('status', ['missing', 'partial', 'unknown'])
def test_empty_represented_without_completed_missing_receipts_stays_unresolved(status):
    source = current_source(); compact = judgments(['m'], status=status)
    compact['dependencies'][0]['premise_keys'] = None
    raw = judgments(['m']); raw['dependencies'] = []
    result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m'}, set())
    assert result['checks'][0]['status'] == status and not joined
    assert not valid['retained_missing'] and result['dependencies'][0]['premise_keys'] is None
    assert review.blocked(dict(source=source, representation=result, errors=[], issues=[])) == ({'m'}, [])


def test_valid_expression_partial_unknown_and_missing_source_are_not_promoted():
    run = local_run(); cid = run['claims'][0]['id']
    compact = judgments(['m'], status='unknown')
    for status in ['represented', 'partial', 'unknown']:
        raw = judgments(['m'], status=status, ids=[cid])
        result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m'}, {cid})
        assert joined and not errors and result['checks'][0]['status'] == status
    source = current_source(); source['meanings'][0].update(source_status='unknown', availability='missing')
    compact = judgments(['m'], status='missing'); raw = judgments(['m'])
    result, joined, valid, errors = review.retain_join_rows(compact, raw, {'m'}, set(), {'m'})
    assert result['checks'][0]['status'] == 'missing'
    assert review.blocked(dict(source=source, representation=result, errors=[], issues=[])) == ({'m'}, [])


def test_valid_expression_join_keeps_local_errors_when_source_row_is_rejected(monkeypatch):
    run = local_run(); normal, bad = [c['id'] for c in run['claims']]
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'],
                  completeness='complete', gaps=[], conjunctions=['전체 대조'])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        result = judgments(['m'], ids=[normal])
        if context['mode'] == 'meaning_batch':
            result['checks'][0]['incorrect_claim_ids'] = [bad]
        else:
            result['source_checks'] = []
        return result
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, scope = review.represent(None, run, run['requirements'][0], source, [])
    assert not scope['join_succeeded'] and not scope['source_join_succeeded']
    assert result['checks'][0]['claim_ids'] == [normal]
    assert result['checks'][0]['incorrect_claim_ids'] == [bad]
    assert result['meaning_challenges'][0]['meaning_key'] == 'm'


def test_completed_local_absence_stays_unresolved_without_refuting_independent_fact():
    run = local_run()
    for kind, complete in [('local_not_found', True), ('reference_missing_here', True), ('local_not_found', False)]:
        source = current_source()
        f = source['findings'][0]
        f.update(kind=kind, unit_id='inspection', meaning_keys=[], scope_meaning_keys=[])
        source['source_batches'] = [dict(unit_id='inspection', provided_block_ids=['body'], errors=[],
            output=dict(inspection_status='complete' if complete else 'partial'))]
        before = deepcopy(source['meanings'])
        result = judgments(['m'])
        result.update(source_completeness='complete', finding_resolutions=[dict(resolution(status='not_required'),
            meaning_keys=[], evidence=[])])
        review.resolve_findings(source, result, [f], run['blocks'], [], joined=True)
        assessment = dict(source=source, representation=result, errors=[], issues=[])
        assert source['completeness'] == 'partial'
        assert source['finding_resolutions'][0]['status'] == 'unresolved'
        assert source['meanings'] == before and source['findings'] == [f]
        if kind == 'local_not_found' and complete:
            assert review.blocked(assessment) == (set(), [])
            assert source['finding_resolutions'][0]['inspection_scope'] == dict(
                unit_id='inspection', provided_block_ids=['body'])
        else:
            assert review.blocked(assessment)[1] == ['unscoped_source_challenge']

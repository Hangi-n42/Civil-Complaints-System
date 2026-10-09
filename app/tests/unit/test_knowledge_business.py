import json
from copy import deepcopy
from time import monotonic, sleep

import pytest

from app.knowledge import autoschema, business_store, business_run, business_use
from app.knowledge.business_models import RequirementInput, BusinessRunRequest, BusinessDecision
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService, KnowledgeConflict


def test_representation_context_preserves_other_stages_and_reuse_boundaries(monkeypatch):
    import httpx
    from app.generation.model_client import ModelClient
    request = BusinessRunRequest(source_version_ids=['v'], requirement_ids=['r'], model='draft',
        review_model='review', representation_context_tokens=65536)
    calls = []
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            calls.append((request.stage, request.context_tokens))
            return dict(parsed={}, failure_kind=None, elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    parent = dict(id='parent', units=[], model_identity={'draft': 'fixed', 'review': 'fixed'},
        recipe=dict(generation={'provider': 'ollama'}, models={'draft': 'draft', 'review': 'review'},
            options=BusinessRunRequest(source_version_ids=['v'], requirement_ids=['r']).model_dump()),
        metrics=dict(llm_calls=0, model_total_s=0))
    messages, schema, mapping = [dict(role='user', content='same')], {'type': 'object'}, {'source': 'b1'}
    stages = [('requirement_source', True, 4096), ('requirement_representation', True, 4096),
              ('concept_entity', False, 512)]
    for stage, review, budget in stages:
        business_run.call(None, parent, stage, messages, schema, review=review,
                          max_tokens=budget, reference_map=mapping)
    def child(previous, context):
        run = deepcopy(previous)
        run.update(id='child', units=[], parent_run_id=previous['id'], parent_recipe=deepcopy(previous['recipe']),
            parent_model_identity=deepcopy(previous['model_identity']), reusable_units=deepcopy(previous['units']),
            metrics=dict(llm_calls=0, model_total_s=0))
        run['recipe']['options']['representation_context_tokens'] = context
        return run
    enlarged = child(parent, 65536)
    for stage, review, budget in stages:
        business_run.call(None, enlarged, stage, messages, schema, review=review,
                          max_tokens=budget, reference_map=mapping)
    assert enlarged['metrics']['llm_calls'] == 0 and enlarged['metrics']['reused_responses'] == 3
    assert [u['requested_limits']['context_tokens'] for u in enlarged['units']] == [49152, 65536, 49152]
    assert all(u['executed_limits']['context_tokens'] == 49152 for u in enlarged['units'])
    for difference in ('shrink', 'messages', 'schema', 'mapping', 'model'):
        run = child(enlarged, 49152 if difference == 'shrink' else 65536)
        current_messages, current_schema, current_mapping = deepcopy((messages, schema, mapping))
        if difference == 'messages': current_messages[0]['content'] = 'changed'
        if difference == 'schema': current_schema = {'type': 'array'}
        if difference == 'mapping': current_mapping = {'source': 'b2'}
        if difference == 'model':
            run['recipe']['models']['review'] = 'other'
            run['model_identity']['review'] = 'other'
        business_run.call(None, run, 'requirement_representation', current_messages, current_schema,
                          review=True, reference_map=current_mapping)
        assert run['metrics']['llm_calls'] == 1 and not run['units'][0].get('reused_from'), difference
    large_messages = [dict(role='user', content='x' * 100000)]
    blocked = child(parent, None)
    assert business_run.call(None, blocked, 'requirement_representation', large_messages, review=True) is None
    assert blocked['units'][0]['error'] == 'input_capacity' and blocked['metrics']['llm_calls'] == 0
    repaired = child(blocked, 65536)
    assert business_run.call(None, repaired, 'requirement_representation', large_messages, review=True)
    assert repaired['metrics']['llm_calls'] == 1
    assert repaired['units'][0]['executed_limits']['context_tokens'] == 65536
    assert repaired['units'][0]['executed_limits']['max_tokens'] == 4096
    def native_limit(req):
        if req.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [dict(name=n, digest=n) for n in ('draft', 'review')]})
        assert req.url.path == '/api/show'
        return httpx.Response(200, json={'model_info': {'model.context_length': 49152}})
    monkeypatch.setattr(business_run, 'ModelClient', lambda _: ModelClient(
        {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434'}, transport=httpx.MockTransport(native_limit)))
    # A review override above the declared model capacity must fail before any
    # database access or generation; validating only the base would reach None.lock.
    with pytest.raises(ValueError, match='선언 컨텍스트'):
        business_run.start(None, request)


def test_reassessment_capacity_reuses_successes_with_original_limits(monkeypatch):
    from app.knowledge.business_models import GroundingCheck
    calls = []

    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            calls.append((request.stage, request.max_tokens))
            return dict(parsed=dict(examined_block_ids=[], meanings=[], completeness='partial', gaps=[], conjunctions=[]),
                        failure_kind=None, elapsed_s=.01)

    monkeypatch.setattr(business_run, 'ModelClient', Client)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    options = dict(context_tokens=49152, extraction_tokens=4096, concept_tokens=512,
                   review_tokens=4096, think=False, timeout=1800, neighbor_mode='structured')
    parent = dict(id='parent', units=[], model_identity={'review': 'fixed'},
                  recipe=dict(generation={'provider': 'ollama'}, models={'review': 'model'}, options=options),
                  metrics=dict(llm_calls=0, model_total_s=0))
    for stage in ('requirement_source', 'source_reassessment'):
        business_run.json_call(None, parent, stage, 'unchanged', {}, GroundingCheck)

    def child():
        run = deepcopy(parent)
        run.update(id='child', units=[], parent_run_id=parent['id'], parent_recipe=deepcopy(parent['recipe']),
                   parent_model_identity=deepcopy(parent['model_identity']), reusable_units=deepcopy(parent['units']),
                   metrics=dict(llm_calls=0, model_total_s=0))
        run['recipe']['options']['source_reassessment_tokens'] = 8192
        run['recipe']['options']['source_tokens'] = 8192
        return run

    success = child()
    business_run.json_call(None, success, 'source_reassessment', 'unchanged', {}, GroundingCheck)
    assert success['metrics']['llm_calls'] == 0
    assert success['units'][0]['requested_limits']['max_tokens'] == 8192
    assert success['units'][0]['executed_limits']['max_tokens'] == 4096

    failed = child()
    failed['reusable_units'][1]['response']['failure_kind'] = 'truncated'
    for stage in ('requirement_source', 'source_reassessment'):
        business_run.json_call(None, failed, stage, 'unchanged', {}, GroundingCheck)
    assert failed['metrics']['reused_responses'] == 1
    assert failed['metrics']['llm_calls'] == 1
    assert failed['units'][0]['executed_limits']['max_tokens'] == 4096
    assert failed['units'][1]['executed_limits']['max_tokens'] == 8192
    assert calls == [('requirement_source', 4096), ('source_reassessment', 4096), ('source_reassessment', 8192)]
    initial_failure = child()
    initial_failure['reusable_units'][0]['response']['failure_kind'] = 'truncated'
    for stage in ('requirement_source', 'source_reassessment'):
        business_run.json_call(None, initial_failure, stage, 'unchanged', {}, GroundingCheck)
    assert initial_failure['metrics']['reused_responses'] == 1 and initial_failure['metrics']['llm_calls'] == 1
    assert initial_failure['units'][0]['executed_limits']['max_tokens'] == 8192
    assert initial_failure['units'][1]['executed_limits']['max_tokens'] == 4096
    assert calls[-1] == ('requirement_source', 8192)



def test_representation_output_reservation_and_success_cache(monkeypatch):
    from app.knowledge.business_models import RequirementCheck
    calls = []
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            calls.append((request.stage, request.max_tokens))
            return dict(parsed=dict(source_checks=[], checks=[], satisfied=False,
                conjunctions_satisfied=False, reason='gap', source_challenges=[]),
                failure_kind=None, elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    base = BusinessRunRequest(source_version_ids=['v'], requirement_ids=['r']).model_dump()
    parent = dict(id='parent', units=[], model_identity={'review': 'fixed'},
        recipe=dict(generation={'provider': 'ollama'}, models={'review': 'review', 'draft': 'draft'}, options=base),
        metrics=dict(llm_calls=0, model_total_s=0))
    business_run.json_call(None, parent, 'requirement_representation', 'unchanged', {}, RequirementCheck)
    def child(previous, budget):
        run = deepcopy(previous)
        run.update(id='child', units=[], parent_run_id=previous['id'],
            parent_recipe=deepcopy(previous['recipe']), parent_model_identity=deepcopy(previous['model_identity']),
            reusable_units=deepcopy(previous['units']), metrics=dict(llm_calls=0, model_total_s=0))
        run['recipe']['options'] = BusinessRunRequest.model_validate(
            dict(previous['recipe']['options'], representation_tokens=budget)).model_dump()
        return run
    enlarged = child(parent, 16384)
    business_run.json_call(None, enlarged, 'requirement_representation', 'unchanged', {}, RequirementCheck)
    assert enlarged['metrics']['llm_calls'] == 0 and enlarged['metrics']['reused_responses'] == 1
    assert enlarged['units'][0]['requested_limits']['max_tokens'] == 16384
    assert enlarged['units'][0]['executed_limits']['max_tokens'] == 4096
    failed = child(parent, 16384)
    failed['reusable_units'][0]['response']['failure_kind'] = 'truncated'
    business_run.json_call(None, failed, 'requirement_representation', 'unchanged', {}, RequirementCheck)
    assert failed['units'][0]['executed_limits']['max_tokens'] == 16384
    smaller = child(enlarged, 8192)
    business_run.json_call(None, smaller, 'requirement_representation', 'unchanged', {}, RequirementCheck)
    assert smaller['metrics']['llm_calls'] == 1 and smaller['units'][0]['executed_limits']['max_tokens'] == 8192
    business_run.call(None, failed, 'requirement_source', [], review=True)
    business_run.call(None, failed, 'concept_entity', [], max_tokens=512)
    assert calls == [('requirement_representation', 4096), ('requirement_representation', 16384),
        ('requirement_representation', 8192), ('requirement_source', 4096), ('concept_entity', 512)]
    with pytest.raises(ValueError):
        BusinessRunRequest.model_validate(dict(base, representation_tokens=255))


def test_current_run_reuses_only_identical_successful_requests_and_keeps_usage(monkeypatch):
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            return dict(request_id=request.request_id, model=request.model, parsed={}, failure_kind=None,
                        elapsed_s=.01, prompt_eval_count=12, eval_count=3)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    run = dict(id='r', units=[], model_identity={'review': 'fixed'},
        recipe=dict(generation={'provider': 'ollama'}, models={'review': 'review'},
            options=BusinessRunRequest(source_version_ids=['v'], requirement_ids=['r']).model_dump()),
        metrics=dict(llm_calls=0, model_total_s=0))
    messages, schema, mapping = [dict(role='user', content='same')], {'type': 'object'}, {'source': 'b1'}
    business_run.call(None, run, 'requirement_representation', messages, schema, review=True, reference_map=mapping)
    original = deepcopy(run)
    business_run.call(None, run, 'requirement_representation', messages, schema, review=True, reference_map=mapping)
    assert run['metrics'] == dict(llm_calls=1, model_total_s=.01, reused_responses=1)
    assert run['units'][0] == original['units'][0]
    assert run['units'][1]['response'] == run['units'][0]['response']
    assert run['units'][1]['reused_from'] == dict(run_id='r', unit_id=run['units'][0]['id'], original_status='succeeded')
    for difference in ('stage', 'messages', 'schema', 'mapping', 'model', 'identity', 'generation',
                       'budget', 'context', 'think', 'timeout', 'schema_error', 'truncated', 'cancelled', 'executed_limits'):
        changed = deepcopy(original)
        current_messages, current_schema, current_mapping = deepcopy((messages, schema, mapping))
        stage, budget = 'requirement_representation', None
        if difference == 'stage': stage = 'source_reassessment'
        if difference == 'messages': current_messages[0]['content'] = 'changed'
        if difference == 'schema': current_schema = {'type': 'array'}
        if difference == 'mapping': current_mapping = {'source': 'b2'}
        if difference == 'model': changed['recipe']['models']['review'] = 'other'
        if difference == 'identity': changed['model_identity']['review'] = 'new digest'
        if difference == 'generation': changed['recipe']['generation']['endpoint'] = 'http://other'
        if difference == 'budget': budget = 8192
        if difference == 'context': changed['recipe']['options']['representation_context_tokens'] = 65536
        if difference == 'think': changed['recipe']['options']['think'] = True
        if difference == 'timeout': changed['recipe']['options']['timeout'] = 900
        if difference == 'schema_error': changed['units'][0].update(status='failed', error='schema_error: invalid output')
        if difference == 'truncated': changed['units'][0]['response']['failure_kind'] = 'truncated'
        if difference == 'cancelled': changed['units'][0]['status'] = 'cancelled'
        if difference == 'executed_limits': changed['units'][0]['executed_limits']['max_tokens'] = 2048
        business_run.call(None, changed, stage, current_messages, current_schema, review=True,
                          max_tokens=budget, reference_map=current_mapping)
        assert changed['metrics']['llm_calls'] == 2 and not changed['units'][-1].get('reused_from'), difference


def finish(service, run_id):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        value = service.run(run_id)
        if value['status'] not in {'queued', 'running', 'cancel_requested'}:
            return value
        sleep(.01)
    raise AssertionError('worker did not finish')


def test_structured_claim_compaction_preserves_values_and_original():
    fields = {'순번': 13, 'NODE_ID': '00013', 'X좌표': 127.0123}
    text = json.dumps(fields, ensure_ascii=False)
    claim = dict(id='row', role='structured_row', statement=text, raw=dict(Event=text, fields=fields))
    original = deepcopy(claim)
    compact = business_run.compact_claim(claim)
    assert compact['raw'] == {'fields': fields} and 'statement' not in compact
    assert claim == original
    claim['raw']['Event'] += ' 별도 조건'
    assert business_run.compact_claim(claim)['raw']['Event'].endswith('별도 조건')


def test_nonessential_real_responses_keep_scope_and_error_gates(monkeypatch):
    from pathlib import Path
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures' /
                          'business_nonessential_bus_responses.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *_: None)

    def replay(case):
        run = dict(blocks=deepcopy(case['blocks']), claims=deepcopy(case['claims']),
                   requirements=[deepcopy(case['requirement'])], repairs=[], assessments=[])
        stages = []
        def response(_service, _run, stage, *_args):
            stages.append(stage)
            historical = deepcopy(case['source' if stage == 'requirement_source' else 'representation'])
            # Reproduce the legacy server default, not an explicit model verdict.
            # These frozen old replies are not valid new provider responses.
            for check in historical.get('checks', []):
                check.setdefault('incorrect_claim_ids', [])
            return _args[-1].model_validate(historical).model_dump()
        monkeypatch.setattr(business_run, 'json_call', response)
        assessment = business_run.assess(None, run, run['requirements'][0])
        assert stages == ['requirement_source', 'requirement_representation']
        return run, assessment

    # Original model responses, before the server appended a challenge solely
    # because a correct extra meaning was marked nonessential.
    for case in fixture['cases']:
        run, assessment = replay(case)
        assert assessment['status'] == 'satisfied'
        assert not assessment['errors'] and not assessment['representation']['source_challenges']
        eligible, blocked = business_use.eligibility(run)
        assert eligible == set(case['expected_required_claim_ids']) and not blocked
        assert not eligible.intersection(case['optional_only_claim_ids'])
        assert run['claims'] == case['claims']

    # Controlled variants test server routing, not new model quality.
    for source_status, expression, expected in [
        ('supported', 'missing', 'hold'), ('supported', 'incorrect', 'correct'),
        ('refuted', 'incorrect', 'correct'), ('unknown', 'incorrect', 'hold'),
        ('supported', 'unknown', 'hold'),
    ]:
        case = deepcopy(fixture['cases'][1])
        meaning = next(m for m in case['source']['meanings'] if m['key'] == 'proposal_context')
        meaning['source_status'] = source_status
        check = next(c for c in case['representation']['checks'] if c['meaning_key'] == meaning['key'])
        check['status'] = expression
        if expression == 'missing':
            check['claim_ids'] = []
        run, assessment = replay(case)
        action = next(a for a in assessment['actions'] if a['meaning_key'] == meaning['key'])
        assert action['action'] == expected
        assert assessment['status'] == ('satisfied' if source_status == 'supported' and expression == 'missing' else 'partial')
        repair_contexts = []
        def repair_response(_service, _run, stage, _instruction, context, _schema):
            assert stage == 'requirement_repair'
            repair_contexts.append(context)
            return dict(patches=[], unresolved=['모의 호출 경계 확인; 실제 교정 아님'])
        monkeypatch.setattr(business_run, 'json_call', repair_response)
        business_run.repair(None, run, run['requirements'][0], assessment)
        assert bool(repair_contexts) == (expected == 'correct')
        if repair_contexts:
            assert 'approval_context' in {m['key'] for m in repair_contexts[0]['preserve_meanings']}
        eligible, _ = business_use.eligibility(run)
        assert not eligible.intersection(case['optional_only_claim_ids'])

    case = deepcopy(fixture['cases'][1])
    next(c for c in case['representation']['source_checks'] if c['meaning_key'] ==
         'proposal_context')['field_checks']['period'] = 'unknown'
    run, assessment = replay(case)
    assert assessment['status'] == 'partial' and assessment['representation']['source_challenges']
    assert not business_use.eligibility(run)[0]

    case = deepcopy(fixture['cases'][0])
    for check in case['representation']['source_checks']:
        check['required_for_requirement'] = False
    run, assessment = replay(case)
    assert assessment['status'] == 'partial' and not business_use.eligibility(run)[0]


def test_source_input_omits_only_filename_equal_to_title(monkeypatch):
    messages = []
    def capture(_service, _run, _stage, supplied, *_args, **_kwargs):
        messages.extend(supplied)
        return None
    monkeypatch.setattr(business_run, 'call', capture)
    run = dict(blocks=[], claims=[], recipe=dict(options={}), sources={
        'one': dict(title='record.html', filename='record.html', dates=[]),
        'two': dict(title='before.json', filename='after.json', dates=[]),
    })
    original = deepcopy(run)
    business_run.json_call(None, run, 'requirement_source', '원문 확인',
                           dict(blocks=[]), business_run.GroundingCheck)
    supplied = json.loads(messages[-1]['content'])['source_versions']
    assert supplied[0] == dict(id='v1', title='record.html', dates=[])
    assert supplied[1] == dict(id='v2', title='before.json', filename='after.json', dates=[])
    assert run == original


def test_source_versions_keep_distinct_filenames_under_shared_title(tmp_path, monkeypatch):
    from app.knowledge.business_models import GroundingCheck
    contexts = []
    class Client:
        def __init__(self, *_): pass
        def identities(self, models, required): return {k: {'name': v} for k, v in models.items()}
        async def generate(self, request, cancelled=None):
            contexts.append(json.loads(request.messages[-1]['content']))
            return dict(parsed=dict(examined_block_ids=[], meanings=[], completeness='partial', gaps=[], conjunctions=[]),
                        failure_kind=None, elapsed_s=.001)

    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        registered = [service.register(name, text.encode(), SourceRegistration(title='공통 출처 제목',
            publisher='기관', namespace='test', external_id='same-source',
            dates=[dict(role='file_snapshot', value=day)]))
            for name, text, day in [('before.txt', '변경 전 원문', '2025-05-13'), ('after.txt', '변경 후 원문', '2025-06-24')]]
        versions = [v['source_version_id'] for v in registered]
        finish(service, service.start(RunRequest(source_version_ids=versions))['run_id'])
        business_store.put_requirement(service, RequirementInput(id='r', question_ids=['q'], question='무엇이 달라졌는가?',
            target='동일 출처', situation='전후 비교', period='두 스냅샷', criterion='버전별 값을 구분한다'))
        monkeypatch.setattr(service.executor, 'submit', lambda *_: None)
        run = service.run(service.start_business(BusinessRunRequest(source_version_ids=versions, requirement_ids=['r']))['run_id'])
        assert run['recipe']['review_contract'] == 'requirement-local-review-v8-owned-errors'
        business_run.json_call(service, run, 'requirement_source', '원문 확인', dict(blocks=run['blocks']), GroundingCheck)
        supplied = contexts[0]['source_versions']
        assert [s['filename'] for s in supplied] == ['before.txt', 'after.txt']
        assert [s['dates'][0]['value'] for s in supplied] == ['2025-05-13', '2025-06-24']
        assert {s['title'] for s in supplied} == {'공통 출처 제목'}
        assert len({s['source_id'] for s in supplied}) == 1
        with service.repository.connect() as db:
            assert service.repository.get(db, 'sources', registered[0]['source_id'])['title'] == '공통 출처 제목'
            assert [service.repository.get(db, 'versions', v)['filename'] for v in versions] == ['before.txt', 'after.txt']
    finally:
        service.shutdown()


def test_server_quote_error_reaches_source_reassessment_without_model_challenge(tmp_path, monkeypatch):
    import jsonschema
    from app.knowledge import business_review

    read_source = business_review.source
    stored_source = tmp_path / 'legacy_source.json'

    def restore_invalid_source(*args, **kwargs):
        source = read_source(*args, **kwargs)
        assert len(source['meanings']) == 1 and source['source_batches'][0]['errors'] == []
        # Synthetic old stored record: current model responses select evidence IDs
        # and cannot freely write this malformed quotation.
        source['meanings'][0]['evidence'][0]['quote'] = '기관은 ... 접수한다.'
        stored_source.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
        return json.loads(stored_source.read_text(encoding='utf-8'))

    monkeypatch.setattr(business_review, 'source', restore_invalid_source)
    calls = []
    class Client:
        def __init__(self, *_): pass
        def identities(self, models, required):
            return {k: dict(name=v, digest='mock', context_length=required[k]) for k,v in models.items()}
        async def generate(self, request, cancelled=None):
            calls.append(request.stage)
            if request.stage in autoschema.ROLES:
                output = []
            elif request.stage == 'direct_definitions':
                output = {'definitions': []}
            else:
                context = json.loads(request.messages[-1]['content'])
                if request.stage in {'requirement_source', 'source_reassessment'}:
                    assert len(context['blocks']) == 1
                    assert context['blocks'][0]['text'] == '기관은 신청을 접수한다.'
                    block = context['blocks'][0]
                    if request.stage == 'source_reassessment':
                        challenge = context['challenges'][0]
                        assert challenge['meaning_key'] == 'batch1:accept'
                        assert challenge['record_error'] == '원문에 없는 근거 인용'
                        assert challenge['evidence'][0]['quote'] == '기관은 ... 접수한다.'
                        assert block['id'] in challenge['provided_block_ids']
                    output = dict(examined_block_ids=[block['id']], meanings=[dict(key='batch1:accept' if request.stage == 'source_reassessment' else 'accept',
                        statement='기관은 신청을 접수한다.', source_status='supported', availability='provided', required_for_requirement=True,
                        requirement_link=dict(requested_fact='신청 접수 기관', applicability='applicable', contribution='direct_answer', reason='질문 대상 기관'),
                        evidence=[block['evidence_ref']], conditions=[], exceptions=[],
                        period='', references=[], premise_keys=[], reason='원문')], completeness='complete', gaps=[], conjunctions=[])
                    if request.stage == 'requirement_source':
                        output.update(inspection_status='complete', findings=[])
                elif request.stage == 'requirement_representation':
                    assert [m['key'] for m in context['source']['meanings']] == ['batch1:accept']
                    key = context['source']['meanings'][0]['key']
                    if context['mode'] == 'requirement_join':
                        assert context['local_judgments']['checks'][0]['status'] == 'missing'
                        assert context['review_meaning_keys'] == []
                    output = dict(checks=([dict(meaning_key=key, status='missing', claim_ids=[], incorrect_claim_ids=[],
                        claim_support={}, error_fields={}, error_evidence=[], reason='후보 없음')]
                        if context['mode'] == 'meaning_batch' else []), dependencies=[], meaning_challenges=[],
                        satisfied=False, conjunctions_satisfied=True, reason='누락', source_challenges=[],
                        source_completeness='complete', unselected_source_required=False, finding_resolutions=[])
                elif request.stage == 'business_qa':
                    assert '기관은 신청을 접수한다.' in context['context'][0]['text']
                    output = dict(answer='기관', choice='A', citations=[context['context'][0]['id']], limitations=[])
                else:
                    raise AssertionError(request.stage)
            if request.schema:
                jsonschema.validate(output, request.schema)
            return dict(parsed=output, text=json.dumps(output, ensure_ascii=False), failure_kind=None, elapsed_s=.001)

    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        registered = service.register('source.txt', '기관은 신청을 접수한다.'.encode(),
            SourceRegistration(title='안내', publisher='기관', namespace='test'))
        vid = registered['source_version_id']
        unrelated = service.register('unrelated.txt', '관련 없는 교통량 통계'.encode(),
            SourceRegistration(title='별도 자료', publisher='기관', namespace='test'))['source_version_id']
        finish(service, service.start(RunRequest(source_version_ids=[vid, unrelated]))['run_id'])
        business_store.put_requirement(service, RequirementInput(id='r', question_ids=['q'], question='접수 기관은?',
            target='신청', situation='접수', period='원문 시점', criterion='접수 기관을 보존한다', source_ids=[registered['source_id']]))
        run = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid, unrelated],
            requirement_ids=['r'], conceptualize=False, repair=False))['run_id'])
        assert run['status'] == 'partial', run.get('error')
        assert len(run['blocks']) == 2 and len(run['assessments'][-1]['source_scope']['provided_block_ids']) == 1
        assert calls.count('source_reassessment') == 1
        assert run['assessments'][0]['errors'] == ['원문에 없는 근거 인용']
        assert run['assessments'][-1]['errors'] == []
        assert run['assessments'][0]['representation']['meaning_challenges'] == []
        assert run['assessments'][0]['source_record_challenges'][0]['meaning_key'] == 'batch1:accept'
        source = run['assessments'][-1]['source']
        assert source['meanings'][0]['statement'] == '기관은 신청을 접수한다.'
        assert source['meanings'][0]['evidence'][0]['quote'] == '기관은 신청을 접수한다.'
        assert source['reassessment_history'][0]['previous'][0]['record_error'] == '원문에 없는 근거 인용'
        assert json.loads(stored_source.read_text(encoding='utf-8'))['meanings'][0]['evidence'][0]['quote'] == '기관은 ... 접수한다.'
        assert run['assessments'][-1]['status'] == 'partial' and run['repairs'] == []
        assert business_use.change_view(service, run['changeset_id'])['eligible_ids'] == []
        decision = business_use.decide(service, run['changeset_id'], BusinessDecision(
            expected_revision=0, actor='test-operator', reason='승인 주장 없는 문서 기준선 검사', accept_ids=[]))
        from app.knowledge.business_models import BusinessQuery
        query = BusinessQuery(snapshot_id=decision['snapshot_id'], question='접수 기관은?', retrieval='bm25')
        previous_calls = len(calls)
        graph = business_use.query(service, query)
        assert graph['status'] == 'no_reviewed_claims' and not graph['model_called']
        assert len(calls) == previous_calls
        document = business_use.query(service, query, context_mode='document')
        assert document['status'] == 'answered' and document['answer']['answer'] == '기관'
        assert len(calls) == previous_calls + 1
    finally:
        service.shutdown()


def test_independent_extraction_multiedges_and_relation_source():
    assert BusinessRunRequest(source_version_ids=['v1'], requirement_ids=['r1']).neighbor_mode == 'plain'
    block = dict(id='b1', text='기관은 본인 신청을 접수한다. 다만 대리는 위임장이 필요하다.',
                 source_version_id='v1', locator={})
    chunk = autoschema.chunks([block], 8192, 1024)[0]
    assert all(autoschema.extraction_messages(chunk['text'], r)[1]['content'].endswith(chunk['text']) for r in autoschema.ROLES)
    claims = [autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation=r, Tail='신청'), i)
              for i, r in enumerate(['접수', '대리일 때 위임장 요구'])]
    graph = autoschema.graph(claims)
    assert len(graph['edges']) == 2
    target = next(t for t in autoschema.concept_targets(graph) if t['kind'] == 'relation')
    _, selection = autoschema.concept_messages(target, graph, {chunk['id']: chunk})
    assert selection['mandatory_chunk_ids'] == [chunk['id']]
    entity = next(t for t in graph['nodes'] if t['label'] == '기관')
    _, a = autoschema.concept_messages(entity, graph, {chunk['id']: chunk}, 'plain', neighbor_bytes=1)
    _, b = autoschema.concept_messages(entity, graph, {chunk['id']: chunk}, 'structured', neighbor_bytes=1)
    assert a['information_fingerprint'] == b['information_fingerprint']
    assert len(a['omissions']) == 2 and a['mandatory_chunk_ids']
    _, supplied = autoschema.concept_messages(entity, graph, {chunk['id']: chunk}, 'structured')
    assert set(supplied['selected_edge_ids']) == {edge['id'] for edge in graph['edges']}
    assert set(supplied['source_reference_map']) == {'b1'}
    with pytest.raises(ValueError):
        autoschema.normalize([{'Head': '', 'Relation': 'r', 'Tail': 't'}], 'entity_relation')


def test_requirement_revision_and_service_review_path(tmp_path, monkeypatch):
    import jsonschema

    class FakeClient:
        def __init__(self, *_): pass
        def identities(self, models, required):
            return {k: {'name': v, 'digest': 'mock', 'context_length': required[k]} for k, v in models.items()}
        async def generate(self, request, cancelled=None):
            context = json.loads(request.messages[-1]['content']) if request.stage.startswith(('requirement_', 'direct_', 'business_')) else {}
            if request.stage == 'entity_relation':
                evidence = [dict(block_id='b1', quote='기관은 본인 신청을 접수한다.')]
                scope = dict(evidence=evidence, meanings=[dict(statement_type='rule', relation_kind='authority',
                    subject='기관', action='접수한다', object='본인 신청', applies_to='본인 신청', modality='permission',
                    **{field: dict(state='absent', text=None)
                       for field in ('conditions', 'exceptions', 'time', 'local_negation', 'references')},
                    premises=dict(state='absent', meaning_indices=[]), evidence=evidence,
                    participants=[dict(field=field, entity_index=None, evidence=evidence) for field in ('Head', 'Tail')])])
                output = [dict(Head='기관', Relation='접수한다', Tail='본인 신청', Scope=scope)]
            elif request.stage in {'event_entity', 'event_relation'}: output = []
            elif request.stage == 'direct_definitions': output = {'definitions': []}
            elif request.stage.startswith('concept_'): output = None
            elif request.stage == 'requirement_source':
                block = context['blocks'][0]
                output = dict(examined_block_ids=[block['id']], meanings=[dict(key='accept', statement=block['text'],
                    source_status='supported', availability='provided', required_for_requirement=True,
                    requirement_link=dict(requested_fact='신청 접수 기관', applicability='applicable', contribution='direct_answer', reason='질문 대상 기관'),
                    evidence=[block['evidence_ref']],
                    conditions=[], exceptions=[], period='', references=[], premise_keys=[], reason='원문')], inspection_status='complete', findings=[], conjunctions=[])
            elif request.stage == 'requirement_representation':
                assert [m['key'] for m in context['source']['meanings']] == ['batch1:accept']
                if context['mode'] == 'meaning_batch':
                    key = context['source']['meanings'][0]['key']
                    ids = [context['claims'][0]['id']]
                else:
                    assert context['mode'] == 'requirement_join'
                    assert context['review_meaning_keys'] == (['batch1:accept'] if context['preservation_targets'] else [])
                    assert context['local_judgments']['checks'][0]['status'] == 'represented'
                    assert context['local_judgments']['checks'][0]['claim_ids']
                output = dict(checks=([dict(meaning_key=key, status='represented', claim_ids=ids, incorrect_claim_ids=[],
                                  claim_support={cid: 'supported' for cid in ids}, error_fields={}, error_evidence=[], reason='원문과 표현 일치')]
                                  if context['mode'] == 'meaning_batch' else []), dependencies=[], meaning_challenges=[],
                              satisfied=True, conjunctions_satisfied=True, reason='전체 의미', source_challenges=[],
                              source_completeness='complete', unselected_source_required=False, finding_resolutions=[])
                if context['mode'] == 'requirement_join' and context['preservation_targets']:
                    output['preservation_checks'] = [dict(target_id=t['target_id'], status='unknown',
                        before_normal_meanings=[], after_locations=[], reason='수정 전후 정상 의미 보존 판단 미확정')
                        for t in context['preservation_targets']]
            elif request.stage == 'business_qa':
                assert json.loads(context['context'][0]['text'])['raw'] == dict(Head='기관', Relation='접수한다', Tail='본인 신청')
                output = dict(answer='기관', choice=None, citations=[context['context'][0]['id']], limitations=[])
            else: raise AssertionError(request.stage)
            if request.schema:
                jsonschema.validate(output, request.schema)
            return dict(request_id=request.request_id, text='기관, 접수처' if output is None else json.dumps(output, ensure_ascii=False), parsed=output,
                        failure_kind=None, elapsed_s=.001, prompt_eval_count=10, eval_count=5, done=True, done_reason='stop')
    monkeypatch.setattr(business_run, 'ModelClient', FakeClient)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        vid = service.register('source.txt', '기관은 본인 신청을 접수한다.'.encode(),
             SourceRegistration(title='안내', publisher='기관', namespace='test'))['source_version_id']
        assert finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])['status'] == 'succeeded'
        requirement = RequirementInput(id='r1', question_ids=['q1'], question='접수 기관은?', target='본인',
                                      situation='접수', period='안내 시점', criterion='기관을 확인한다')
        business_store.put_requirement(service, requirement)
        with pytest.raises(KnowledgeConflict): business_store.put_requirement(service, requirement)
        run = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid], requirement_ids=['r1']))['run_id'])
        assert run['status'] == 'review_ready', run.get('error')
        assert {u['stage'] for u in run['units']} >= set(autoschema.ROLES)
        assert len(run['assessments']) == 1 and run['assessments'][0]['status'] == 'satisfied'
        assert [m['statement'] for m in run['assessments'][0]['source']['meanings']] == ['기관은 본인 신청을 접수한다.']
        assert run['claims'][0]['interpretation']['errors'] == []
        assert run['claims'][0]['interpretation']['target_status'] == 'addressed'
        assert run['claims'][0]['interpretation']['meanings']
        selected = [c['id'] for c in run['claims']]
        # A previous eligibility policy may have withheld this unchanged claim.
        with service.repository.connect() as db:
            published = service.repository.get(db, 'changesets', run['changeset_id'])
            published['eligible_ids'] = []
            service.repository.save(db, 'changesets', published)
        current = business_use.change_view(service, run['changeset_id'])
        assert current['eligible_ids'] == selected and current['published_eligible_ids'] == []
        result = business_use.decide(service, run['changeset_id'], BusinessDecision(
            expected_revision=0, actor='test-operator', reason='모의 계약 검사', accept_ids=selected))
        assert result['snapshot_id']
        assert result['decision']['eligibility_contract'] == business_use.ELIGIBILITY_CONTRACT
        with service.repository.connect() as db:
            assert service.repository.get(db, 'changesets', run['changeset_id'])['eligible_ids'] == []
        assert business_store.requirements(service)['items'][0]['current_assessment']['run_id'] == run['id']
        with service.repository.connect() as db:
            parent_before = service.repository.get(db, 'runs', run['id'])
        resumed = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid],
            requirement_ids=['r1'], resume_run_id=run['id']))['run_id'])
        assert resumed['status'] == 'review_ready', resumed.get('error')
        assert resumed['metrics']['llm_calls'] == 0 and resumed['metrics']['reused_responses'] == len(run['units'])
        assert all(u['reused_from']['run_id'] == run['id'] for u in resumed['units'])
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', run['id']) == parent_before
        focused = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid],
            requirement_ids=['r1'], resume_run_id=run['id'], conceptualize=False))['run_id'])
        assert focused['graph']['edges'] and not focused['concepts']
        assert focused['conceptualization_scope'] == 'deferred_to_selected_targets'
        assert focused['status'] == 'review_ready'
        reassessed = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid],
            requirement_ids=['r1'], reassess_run_id=run['id']))['run_id'])
        assert reassessed['status'] == 'review_ready', reassessed.get('error')
        assert reassessed['claims'] == run['claims'] and reassessed['concepts'] == run['concepts']
        assert reassessed['stored_pool']['construction_recipe'] == run['recipe']
        assert not reassessed['stored_pool']['assessment_inherited']
        assert reassessed['reusable_units'] == run['units']
        assert reassessed['metrics']['llm_calls'] == 0 and reassessed['metrics']['reused_responses'] == 3
        assert all(u['reused_from']['run_id'] == run['id'] for u in reassessed['units'])
        assert not reassessed['stored_pool']['approval_inherited']
        assert all(u['stage'] not in autoschema.ROLES for u in reassessed['units'])
        continued = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid],
            requirement_ids=['r1'], resume_run_id=reassessed['id']))['run_id'])
        assert continued['status'] == 'review_ready', continued.get('error')
        assert continued['stored_pool'] == reassessed['stored_pool']
        assert continued['reference_meanings'] == reassessed['reference_meanings']
        assert continued['claims'] == reassessed['claims'] and continued['concepts'] == reassessed['concepts']
        assert continued['metrics']['llm_calls'] == 0
        assert continued['metrics']['reused_responses'] == len(reassessed['units'])
        assert all(u['stage'] not in autoschema.ROLES and u['reused_from']['run_id'] == reassessed['id']
                   for u in continued['units'])
        from app.knowledge import snapshots
        from app.knowledge.business_models import BusinessQuery
        query = BusinessQuery(question='접수 기관은?', snapshot_id=result['snapshot_id'], retrieval='bm25')
        answer = business_use.query(service, query)
        assert answer['status'] == 'answered' and answer['answer']['answer'] == '기관'
        assert answer['answer']['citations'] == selected
        snapshots.set_availability(service, dict(actor='test', reason='원문 사용 중단',
            targets=[dict(type='source_version', id=vid)], state='blocked', expected_status_revision=0))
        blocked = business_use.query(service, query)
        assert blocked['status'] == 'needs_review' and blocked['answer'] is None
        with pytest.raises(KnowledgeConflict, match='제한된'):
            business_use.decide(service, run['changeset_id'], BusinessDecision(
                expected_revision=1, actor='test', reason='차단 확인', accept_ids=selected))
        # A successful current representation cannot certify preservation without
        # comparing the normal meaning in the actual before/after claim.
        original = json.loads(json.dumps(run['claims'][0]))
        source = run['assessments'][0]['source']
        old_fingerprint = business_run.assessment_fingerprint(run, run['requirements'][0], source)
        run['claims'][0]['statement'] += ' 수정'
        run['repairs'] = [dict(id='repair', targets=[], preserve_meanings=deepcopy(source['meanings']),
                              changes=[dict(before=original, after=run['claims'][0], meaning_key='accept')])]
        assert business_run.assessment_fingerprint(run, run['requirements'][0], source) != old_fingerprint
        after = business_run.assess(service, run, run['requirements'][0], source=source, phase='after_repair')
        assert after['status'] == 'partial' and not after['preservation_complete']
        assert after['representation']['preservation_checks'][0]['status'] == 'unknown'
        assert run['units'][-1]['status'] == 'succeeded' and not run['units'][-1]['error']
        unit = next(u for u in reversed(run['units']) if u['stage'] == 'requirement_representation'
                    and json.loads(u['messages'][-1]['content'])['mode'] == 'meaning_batch')
        packet = json.loads(unit['messages'][-1]['content'])
        from app.knowledge.discovery_analysis import remap
        mapping = unit['reference_map']
        assert remap(packet['repair_context'][0]['changes'][0]['before'], {v: k for k, v in mapping.items()}) == business_run.compact_claim(original)
        assert packet['blocks'][0]['text'] == '기관은 본인 신청을 접수한다.'
        with pytest.raises(KnowledgeConflict):
            business_use.decide(service, run['changeset_id'], BusinessDecision(expected_revision=0, actor='a', reason='r', accept_ids=selected))
    finally:
        service.shutdown()


def test_mixed_snapshots_keep_ontology_activation_separate(tmp_path):
    from app.knowledge import snapshots
    from app.tests.unit.test_knowledge_snapshots import reviewed, create, activate
    service, selection = reviewed(tmp_path)
    ontology_id = create(service, selection)
    activate(service, ontology_id)
    source_graph = dict(id='source-graph', kind='source_graph', claims=[], activation='explicit_query_only')
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', (source_graph['id'], json.dumps(source_graph)))
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', ('graph-event', json.dumps(
            dict(id='graph-event', kind='source_graph', event='reviewed_source_graph_snapshot'))))
    listing = snapshots.list_snapshots(service)
    assert [s['id'] for s in listing['items']] == [ontology_id]
    assert len(listing['events']) == 1 and listing['active_snapshot_id'] == ontology_id
    assert business_use.snapshots(service)['items'] == [source_graph]
    for operation in (lambda: snapshots.get_snapshot(service, source_graph['id']),
                      lambda: snapshots.export(service, source_graph['id']),
                      lambda: activate(service, source_graph['id'])):
        with pytest.raises(ValueError, match='출처 그래프'):
            operation()
    assert snapshots.get_snapshot(service)['snapshot_id'] == ontology_id
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', source_graph['id']) == source_graph


def test_one_empty_participant_keeps_valid_siblings_and_failed_statement():
    block = dict(id='b', source_version_id='v', text='본인 신청. 매매한 날부터 15일 이내.', locator={})
    chunk = autoschema.chunks([block], 8192, 1024)[0]
    output = [dict(Event='본인이 직접 신청한다.', Entity=['본인']),
              dict(Event='매매한 날부터 15일 이내에 등록한다.', Entity=[]),
              dict(Event='양수인 미방문 시 위임장을 구비한다.', Entity=['양수인', '위임장'])]
    frozen = json.loads(json.dumps(output))
    run, unit = dict(claims=[]), {}
    business_run.store_extraction(run, chunk, 'event_entity', dict(parsed=output), dict(unit, id='u'))
    assert len(run['claims']) == 3
    assert [c['role'] for c in run['claims']] == ['event_entity', 'event_entity', 'incomplete_extraction']
    assert run['extraction_rejections'][0]['raw'] == output[1]
    assert run['claims'][-1]['statement'] == output[1]['Event']
    assert len(autoschema.graph(run['claims'])['edges']) == 3
    assert output == frozen


def test_exact_evidence_uses_all_provided_views_and_canonical_offsets():
    views = [dict(id='b', source_version_id='v', span=[40, 45], text='다른 내용'),
             dict(id='b', source_version_id='v', span=[10, 15], text='앞 본문말')]
    found = business_run.exact_evidence([dict(block_id='b', quote='다른')], views)
    assert found[0]['start_char'] == 40 and found[0]['end_char'] == 42
    assert business_run.exact_evidence([dict(block_id='b', quote='본문')], views)[0]['start_char'] == 12
    with pytest.raises(ValueError, match='원문에 없는'):
        business_run.exact_evidence([dict(block_id='b', quote='미제공')], views)


def test_relation_repair_preserves_event_endpoints_and_records_explicit_conversion(monkeypatch):
    from copy import deepcopy
    block = dict(id='b', source_version_id='v', text='조건이면 예외를 적용할 수 있다.', locator={})
    chunk = autoschema.chunks([block], 8192, 1024)[0]
    original = autoschema.graph_record(chunk, 'event_relation', dict(Head='조건', Relation='동시에', Tail='예외 적용'), 0)
    normal = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='접수', Tail='신청'), 1)
    patch = dict(meaning_key='m', target_id=original['id'], statement='조건이면 예외를 적용할 수 있다.',
        head='조건', relation='해당하면 허용', tail='예외 적용', evidence=[dict(block_id='b', quote=block['text'])],
        conditions=['조건'], exceptions=[], period='', references=[])
    assessment = dict(id='a', errors=[], representation=dict(source_challenges=[]), source=dict(meanings=[]),
        actions=[dict(meaning_key='m', action='correct', claim_ids=[original['id']])])
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *_: dict(patches=[deepcopy(patch)], unresolved=[]))
    def attempt():
        run = dict(claims=deepcopy([original, normal]), blocks=[block], repairs=[])
        applied = business_run.repair(None, run, dict(id='r'), assessment)
        assert run['claims'][1] == normal
        return applied, run
    applied, run = attempt()
    assert applied and run['claims'][0]['role'] == 'event_relation'
    assert {n['kind'] for n in autoschema.graph([run['claims'][0]])['nodes']} == {'event'}
    patch['role'] = 'entity_relation'
    applied, run = attempt()
    assert not applied and run['claims'][0] == original
    patch['conversion_reason'] = '명시적인 형식 변환의 저장 계약 검사; 의미 성공 주장이 아님'
    applied, run = attempt()
    assert applied and run['claims'][0]['role_conversion']['before'] == 'event_relation'


def test_source_delivery_and_model_examination_do_not_replace_meaning_coverage(monkeypatch):
    from copy import deepcopy
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *_: None)
    requirement = dict(id='r', revision=1, source_ids=[])
    run = dict(blocks=[dict(id='b1', source_id='s', source_version_id='v', text='기관이 접수한다.'),
                       dict(id='b2', source_id='s', source_version_id='v', text='다른 업무 안내')],
               claims=[dict(id='c', statement='기관이 접수한다.')], repairs=[], assessments=[])
    source = dict(examined_block_ids=['b1'], completeness='complete', gaps=[], conjunctions=[], meanings=[dict(
        key='accept', statement='기관이 접수한다.', source_status='supported', availability='provided',
        evidence=[dict(block_id='b1', quote='기관이 접수한다.')])])
    response = dict(checks=[dict(meaning_key='accept', status='represented', claim_ids=['c'], reason='일치')],
        source_checks=[dict(meaning_key='accept', required_for_requirement=True,
            field_checks=dict(statement='supported', conditions='not_applicable', exceptions='not_applicable',
                              period='not_applicable', references='not_applicable'),
            reason='원문과 필드 일치')],
        satisfied=True, conjunctions_satisfied=True, source_challenges=[], preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', lambda *_: deepcopy(response))
    result = business_run.assess(None, run, requirement, source=deepcopy(source))
    assert not result['errors'] and result['status'] == 'satisfied'
    assert result['source_scope']['provided_not_declared_ids'] == ['b2']
    assert not result['source_scope']['model_reading_independently_verified']
    assert result['source']['examined_block_ids'] == ['b1']
    response['checks'][0]['status'] = 'missing'
    response['checks'][0]['claim_ids'] = []
    response['satisfied'] = False
    result = business_run.assess(None, run, requirement, source=deepcopy(source))
    assert result['status'] == 'partial' and result['actions'][0]['action'] == 'recover'
    source['examined_block_ids'].append('not-provided')
    result = business_run.assess(None, run, requirement, source=source)
    assert result['errors'] == ['제공하지 않은 블록의 조사 선언']
    source['examined_block_ids'].pop()
    source['meanings'][0]['period'] = '당일 완료'
    response['source_checks'][0]['field_checks']['period'] = 'unknown'
    response['source_checks'][0]['reason'] = '원문에 완료시점 없음'
    result = business_run.assess(None, run, requirement, source=deepcopy(source))
    assert result['status'] == 'partial'
    assert 'period' in result['representation']['source_challenges'][0]
    # A failed or still-challenged source reassessment cannot authorize repair
    # using the original, unsupported source meaning.
    monkeypatch.setattr(business_run, 'json_call', lambda *_: pytest.fail('unresolved source must not generate a repair'))
    assert not business_run.repair(None, run, requirement, result)


def test_business_api_requires_its_own_changeset_kind(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    from app.core.config import settings
    monkeypatch.setattr(settings, 'KNOWLEDGE_ENABLED', True)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    app = FastAPI(); app.include_router(knowledge.router)
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO changesets VALUES(?,?)', ('old', json.dumps(dict(id='old', kind='extraction'))))
        with TestClient(app) as client:
            req = dict(id='r', question_ids=['q'], question='필요 서류는?', target='본인',
                       situation='신청', period='원문 기준', criterion='서류와 예외를 보존')
            assert client.put('/knowledge/requirements/r', json=req).status_code == 200
            assert client.put('/knowledge/requirements/r', json=req).status_code == 409
            assert client.get('/knowledge/requirements').json()['data']['items'][0]['revision'] == 1
            assert client.get('/knowledge/business/runs').json()['data']['items'] == []
            assert client.get('/knowledge/business/changes/old').status_code == 422
            assert client.get('/knowledge/business/snapshots').json()['data']['items'] == []
            seen = []
            monkeypatch.setattr(service, 'start_business', lambda request: seen.append(request.model_dump())
                or dict(run_id='new', status='queued'))
            retry = dict(source_version_ids=['v'], requirement_ids=['r'], resume_run_id='old',
                source_tokens=24576, representation_tokens=16384, representation_context_tokens=98304)
            assert client.post('/knowledge/business/runs', json=retry).json()['data']['run_id'] == 'new'
            assert all(seen[0][k] == v for k, v in retry.items())
            assert seen[0]['context_tokens'] == 49152 and seen[0]['review_tokens'] == 4096
            assert client.post('/knowledge/business/runs', json=dict(retry, representation_tokens=255)).status_code == 422
            assert len(seen) == 1
    finally:
        service.shutdown()


def test_only_current_concepts_become_retrieval_hints():
    value = dict(claims=[dict(id='reviewed')], concepts=[
        dict(status='unreviewed', target=dict(claim_ids=['reviewed', 'unselected']), concepts=['신청 기관']),
        dict(status='needs_review', target=dict(claim_ids=['reviewed']), concepts=['수정 전 의미']),
        dict(status='failed', target=dict(claim_ids=['reviewed']), concepts=['실패 출력'])])
    assert business_use.concept_hints(value) == {'reviewed': ['신청 기관']}


def test_concept_search_hint_retrieves_claim_without_becoming_answer_evidence(tmp_path, monkeypatch):
    from app.knowledge.business_models import BusinessQuery
    service = KnowledgeService(tmp_path / 'knowledge.db')
    original = dict(id='origin', status='succeeded', units=[], recipe={}, model_identity={})
    snapshot = dict(id='s', kind='source_graph', run_id='origin', source_versions={'v': {'title': '안내'}},
        requirements=[], assessments={}, blocks=[], claims=[dict(id='c', statement='기관은 민원을 받는다.',
        source_version_ids=['v'], raw={}, evidence=[])], concepts=[dict(status='unreviewed',
        target=dict(claim_ids=['c']), concepts=['접수처'])])
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(snapshot)))
        def answer(service, run, stage, instruction, context, schema, **_kwargs):
            assert len(context['context']) == 1 and context['context'][0]['id'] == 'c'
            assert '접수처' not in context['context'][0]['text']
            return dict(answer='기관이 민원을 받습니다.', choice=None, citations=['c'], limitations=[])
        monkeypatch.setattr(business_run, 'json_call', answer)
        result = business_use.query(service, BusinessQuery(snapshot_id='s', question='접수처', retrieval='bm25', limit=1))
        assert result['retrieval'][0]['block_id'] == 'c' and result['status'] == 'answered'
        saved = service.run(result['run_id'])
        assert saved['retrieval_concept_hints'] == {'c': ['접수처']}
        assert saved['concept_hints_are_answer_evidence'] is False
    finally:
        service.shutdown()


def test_query_citations_are_bounded_aliased_and_empty_answers_fail(tmp_path, monkeypatch):
    from app.knowledge.business_models import BusinessQuery
    seen, scenario = [], ['valid']

    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            context = json.loads(request.messages[-1]['content'])['context']
            ids = [c['id'] for c in context]
            schema = request.schema['properties']['citations']
            assert ids == [f'q{i+1}' for i in range(len(context))]
            assert schema['maxItems'] == len(context) == 13
            assert schema['uniqueItems'] is True and set(schema['items']['enum']) == set(ids)
            seen.append(context)
            citations = ids[:2]
            answer, choice, limitations = '기관이 신청을 접수합니다.', 'A', []
            if scenario[0] == 'duplicate': citations = [ids[0], ids[0]]
            elif scenario[0] == 'unknown': citations = ['not-provided']
            elif scenario[0] == 'too_many': citations = ids + [ids[0]]
            elif scenario[0] in {'empty', 'whitespace'}:
                answer, citations = ('', []) if scenario[0] == 'empty' else ('   ', [])
            elif scenario[0] == 'abstain':
                answer, choice, citations, limitations = '제공 자료로 확인할 수 없습니다.', None, [], ['근거 부족']
            output = dict(answer=answer, choice=choice, citations=citations, limitations=limitations)
            return dict(parsed=output, text=json.dumps(output, ensure_ascii=False), failure_kind=None, elapsed_s=.001)

    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    original = dict(id='origin', status='succeeded', units=[], model_identity={}, recipe=dict(
        generation=dict(provider='ollama'), models=dict(review='mock'),
        options=dict(review_tokens=4096, context_tokens=16384, think=False, timeout=2)))
    snapshot = dict(id='s', kind='source_graph', run_id='origin', source_versions={'v': {'title': '안내'}},
        requirements=[], assessments={}, concepts=[],
        claims=[dict(id=f'original-claim-address-{i}', statement=f'기관{i}는 신청을 접수한다.',
            source_version_ids=['v'], raw={}, evidence=[]) for i in range(13)],
        blocks=[dict(id=f'original-block-address-{i}', text=f'기관{i}는 신청을 접수한다.',
            source_version_id='v') for i in range(13)])
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(snapshot)))
        request = BusinessQuery(snapshot_id='s', question='신청 접수 기관은?', retrieval='bm25', limit=13)
        for mode in ['document', 'graph']:
            result = business_use.query(service, request, context_mode=mode)
            assert result['status'] == 'answered'
            saved = service.run(result['run_id'])
            mapping = saved['units'][-1]['reference_map']
            reverse = {v:k for k,v in mapping.items()}
            assert result['answer']['citations'] == [reverse['q1'], reverse['q2']]
            assert set(mapping) == set(saved['provided_ids'])
            assert saved['answer_contract'] == business_use.ANSWER_CONTRACT
        for case in ['duplicate', 'unknown', 'too_many', 'empty', 'whitespace']:
            scenario[0] = case
            result = business_use.query(service, request)
            assert result['status'] == 'unverified' and result['answer'] is None
            assert service.run(result['run_id'])['units'][-1]['error'].startswith('schema_error:')
        scenario[0] = 'abstain'
        result = business_use.query(service, request)
        assert result['status'] == 'unverified' and result['answer']['choice'] is None
        assert result['answer']['limitations'] == ['근거 부족']
        from app.knowledge.discovery_profile import FrozenIndex
        monkeypatch.setattr(FrozenIndex, 'search', lambda *args, **kwargs: [])
        count = len(seen)
        result = business_use.query(service, request)
        assert result['status'] == 'unverified' and result['answer'] is None and result['qa_model_called'] is False
        assert len(seen) == count and service.run(result['run_id'])['units'] == []
        from app.knowledge import graph_retrieval
        def empty_graph(service, run, snapshot, request):
            run['metrics']['llm_calls'] = 1
            run['units'].append(dict(stage='graph_retrieval_filter', status='succeeded'))
            return []
        monkeypatch.setattr(graph_retrieval, 'retrieve', empty_graph)
        result = business_use.query(service, request.model_copy(update=dict(retrieval='hipporag2')))
        assert result['qa_model_called'] is False and 'model_called' not in result
        assert len(seen) == count and service.run(result['run_id'])['metrics']['llm_calls'] == 1
        with service.repository.connect() as db:
            assert service.repository.get(db, 'snapshots', 's') == snapshot
    finally:
        service.shutdown()


def test_conflicting_latest_meaning_blocks_whole_claim_without_erasing_normal_sibling(tmp_path):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        claims = [dict(id='mixed', statement='본인 접수 가능, 대리도 서류 없이 가능.'),
                  dict(id='normal', statement='기관이 접수한다.'), dict(id='unverified', statement='아직 확인되지 않은 주장')]
        run = dict(id='r', claims=claims, repairs=[], requirements=[dict(id='scope'), dict(id='exception'), dict(id='unrelated')], assessments=[])
        for rid, source_status, representation_status, ids in [('scope', 'supported', 'represented', ['mixed', 'normal']),
                ('exception', 'supported', 'incorrect', ['mixed']), ('unrelated', 'supported', 'represented', ['normal', 'unverified'])]:
            source = dict(meanings=[dict(key='m', source_status=source_status, availability='provided', evidence=['source'])])
            a = dict(id=rid, requirement_id=rid, source=source, errors=['원문 판단 인용 오류'] if rid == 'unrelated' else [], representation=dict(
                checks=[dict(meaning_key='m', status=representation_status, claim_ids=ids)],
                source_challenges=['다른 의미의 기간 오류'] if rid == 'unrelated' else []))
            a['input_fingerprint'] = business_run.assessment_fingerprint(run, next(q for q in run['requirements'] if q['id'] == rid), source)
            run['assessments'].append(a)
        result = business_use.publish(service, run)
        assert result['eligible_ids'] == ['normal']
        assert result['eligibility_blocks']['mixed'] == ['confirmed_error_or_refutation']
        assert result['candidates'] == claims
        # An unresolved meaning blocks use but is not turned into a false claim.
        run['assessments'][1]['representation']['checks'][0]['status'] = 'unknown'
        result = business_use.publish(service, run)
        assert result['eligible_ids'] == ['normal']
        assert result['eligibility_blocks']['mixed'] == ['unresolved_meaning_not_false']
        changed_candidate = deepcopy(result)
        changed_candidate['candidates'][1]['statement'] = '발행 이후 다른 내용으로 바뀐 후보'
        eligible, blocked = business_use.review_eligibility(changed_candidate, run)
        assert not eligible and blocked['normal'] == ['candidate_changed_since_publication']
        assessment = run['assessments'][1]
        assessment['representation']['checks'][0]['status'] = 'represented'
        assessment['source']['meanings'][0]['source_status'] = 'refuted'
        assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][1], assessment['source'])
        eligible, blocked = business_use.eligibility(run)
        assert eligible == {'normal'} and blocked['mixed'] == ['confirmed_error_or_refutation']
    finally:
        service.shutdown()


def test_preserved_repair_is_not_blocked_by_unrelated_requirement():
    run = dict(claims=[dict(id='fixed', statement='정상 의미를 보존한 수정'), dict(id='other', statement='다른 정상 주장')],
               repairs=[dict(changes=[dict(before=dict(id='fixed'), after=dict(id='fixed'))])],
               requirements=[dict(id='a'), dict(id='b')], assessments=[])
    for rid, cid in [('a', 'fixed'), ('b', 'other')]:
        source = dict(meanings=[dict(key='m', source_status='supported', availability='provided', evidence=['source'])])
        assessment = dict(id=rid, requirement_id=rid, source=source, errors=[], representation=dict(
            checks=[dict(meaning_key='m', status='represented', claim_ids=[cid])], source_challenges=[],
            preservation_checks=[dict(target_id='fixed', status='preserved', before_normal_meanings=['정상 의미'],
                                      after_locations=['fixed.statement'])] if rid == 'a' else []))
        assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, dict(id=rid), source)
        run['assessments'].append(assessment)
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {'fixed', 'other'} and not blocked
    run['assessments'][1]['representation']['preservation_checks'] = [dict(
        target_id='fixed', status='lost', before_normal_meanings=['누락 의미'], after_locations=[])]
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {'other'} and blocked['fixed'] == ['normal_meaning_preservation_conflict']


def test_neighbor_arms_execute_new_calls_on_identical_stored_information(tmp_path, monkeypatch):
    from app.knowledge import business_concepts
    from app.knowledge.business_models import ConceptRunRequest
    calls = []
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled):
            calls.append(request)
            return dict(text='기관, 접수처', parsed=None, failure_kind=None, elapsed_s=.001)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        block = dict(id='b', source_version_id='v', text='기관은 민원을 접수한다.', locator={})
        chunk = autoschema.chunks([block], 8192, 1024)[0]
        claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='접수', Tail='민원'), 0)
        graph = autoschema.graph([claim])
        parent = dict(id='parent', kind='business', status='partial', units=[], input_version_ids=['v'], chunks=[chunk],
                      graph=graph, claims=[claim], blocks=[block], model_identity={'draft':'fake'},
                      recipe=dict(generation={'provider':'fake'}, models={'draft':'fake'}, options=BusinessRunRequest(
                          source_version_ids=['v'], requirement_ids=['r']).model_dump()))
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('parent', json.dumps(parent)))
        results = [business_concepts.start(service, ConceptRunRequest(parent_run_id='parent',
            target_ids=[graph['nodes'][0]['id']], neighbor_mode=mode)) for mode in ['plain', 'structured']]
        assert len(calls) == 2 and all(r['metrics']['llm_calls'] == 1 and r['status'] == 'succeeded' for r in results)
        assert calls[0].messages != calls[1].messages
        assert results[0]['planned'][0]['selection']['information_fingerprint'] == results[1]['planned'][0]['selection']['information_fingerprint']
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'parent') == parent
    finally:
        service.shutdown()



def test_exact_evidence_connects_only_delivered_contiguous_consistent_source_ranges():
    from copy import deepcopy
    views = [dict(id='b', source_version_id='v', parse_run_id='p', span=[10, 14], text='가나다라'),
             dict(id='b', source_version_id='v', parse_run_id='p', span=[14, 17], text='마바사')]
    original = deepcopy(views)
    ref = [dict(block_id='b', quote='다라마')]
    assert business_run.exact_evidence(ref, views)[0]['start_char'] == 12
    overlapping = [views[0], dict(views[1], span=[12, 17], text='다라마바사')]
    assert business_run.exact_evidence(ref, overlapping)[0]['end_char'] == 15
    assert views == original
    for changed in [dict(views[1], span=[15, 18]), dict(views[1], source_version_id='other'),
                    dict(views[1], parse_run_id='other'), dict(views[1], id='other')]:
        with pytest.raises(ValueError, match='원문에 없는'):
            business_run.exact_evidence(ref, [views[0], changed])
    with pytest.raises(ValueError, match='겹친 제공 원문 본문 불일치'):
        business_run.exact_evidence(ref, [views[0], dict(views[1], span=[13, 17], text='X마바사')])
    with pytest.raises(ValueError, match='원문에 없는'):
        business_run.exact_evidence([dict(block_id='b', quote='다라...마')], views)
    with pytest.raises(ValueError, match='범위와 본문 길이 불일치'):
        business_run.exact_evidence(ref, [views[0], dict(views[1], span=[14, 20])])


def test_selected_source_evidence_retains_delivered_ranges_and_raw_response(monkeypatch):
    from app.knowledge.business_models import GroundingCheck, LocalSourceCheck, RequirementJoinCheck
    blocks = [dict(id='block', source_version_id='version', parse_run_id='parse',
                   text='같은 문장', span=[n, n + 5], context_only=bool(n)) for n in (0, 10)]
    run = dict(blocks=blocks, claims=[], sources={}, units=[],
               recipe=dict(options={'source_reassessment_tokens': 8192}))
    meaning = dict(key='m', statement='판단 보류', source_status='unknown', availability='ambiguous',
        evidence=['e2'], conditions=[], exceptions=[], period='', references=[], reason='판단 불가')
    raw = dict(examined_block_ids=['b2'], meanings=[meaning], completeness='partial', gaps=['불확실'], conjunctions=[])
    def generate(*args, **kwargs):
        run['units'].append(dict(response={'parsed': deepcopy(raw)}))
        return run['units'][-1]['response']
    monkeypatch.setattr(business_run, 'call', generate)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    context = dict(blocks=blocks, previous={})
    output = business_run.json_call(None, run, 'source_reassessment', '원문 재판정', context, GroundingCheck)
    evidence = output['meanings'][0]['evidence'][0]
    assert evidence == dict(block_id='block', quote='같은 문장', source_version_id='version',
                            parse_run_id='parse', start_char=10, end_char=15, precision='exact')
    assert business_run.exact_evidence([evidence], blocks) == [evidence]
    assert output['meanings'][0]['source_status'] == 'unknown' and output['completeness'] == 'partial'
    assert run['units'][-1]['response']['parsed'] == raw
    assert run['units'][-1]['evidence_reference_map']['e2']['context_only'] is True
    assert context['blocks'] == blocks
    request = business_run.json_request(run, 'requirement_representation', '결합', dict(blocks=blocks), RequirementJoinCheck)
    payload = json.loads(request['messages'][-1]['content'])
    assert [b['evidence_ref'] for b in payload['blocks']] == ['e1', 'e2']
    assert payload['blocks'][1]['context_only'] is True
    assert request['schema']['$defs']['SelectedFindingResolution']['properties']['evidence']['items']['enum'] == ['e1', 'e2']
    raw.update(inspection_status='complete', findings=[])
    for stage, output_type in [('requirement_source', LocalSourceCheck), ('source_reassessment', GroundingCheck)]:
        for selection in [['outside'], [dict(block_id='b2', quote='같은 문장')],
                          [dict(block_id='b2', quote='같은 ... 문장')]]:
            raw['meanings'][0]['evidence'] = selection
            assert business_run.json_call(None, run, stage, '원문 확인', context, output_type) is None
            assert run['units'][-1]['error'].startswith('schema_error')
            assert run['units'][-1]['response']['parsed'] == raw
            assert 'restored_evidence_output' not in run['units'][-1]
    with pytest.raises(ValueError):
        business_run.exact_evidence([dict(evidence, source_version_id='other')], blocks)
    with pytest.raises(ValueError):
        business_run.exact_evidence([dict(evidence, start_char=7, end_char=12)], blocks)


@pytest.mark.parametrize('status', ['supported', 'refuted', 'unknown'])
def test_reassessment_never_inherits_evidence_for_an_empty_selection(monkeypatch, status):
    from app.knowledge.business_models import RequirementGroundingCheck
    blocks = [dict(id='old', source_version_id='v1', parse_run_id='p', text='기한은 2일이다.', span=[0, 9]),
              dict(id='new', source_version_id='v2', parse_run_id='p', text='기한은 3일이다.', span=[0, 9])]
    old = dict(key='m', statement='기한은 2일이다.', source_status='supported', availability='provided',
        evidence=business_run.exact_evidence([dict(block_id='old', quote=blocks[0]['text'])], blocks),
        conditions=[], exceptions=[], period='', references=[], reason='이전 검수', required_for_requirement=True,
        requirement_link=dict(requested_fact='신청 기한', applicability='applicable', contribution='direct_answer', reason='질문 기한'))
    run = dict(blocks=blocks, claims=[], sources={}, units=[], recipe=dict(options={}))
    context = dict(blocks=blocks, previous=dict(meanings=[deepcopy(old)]))
    raw = dict(examined_block_ids=['b1', 'b2'], meanings=[dict(old, statement='기한은 3일이다.',
        source_status=status, evidence=[])], completeness='unknown', gaps=[], conjunctions=[])
    def generate(*args, **kwargs):
        run['units'].append(dict(response={'parsed': deepcopy(raw)}))
        return run['units'][-1]['response']
    monkeypatch.setattr(business_run, 'call', generate)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    request = business_run.json_request(run, 'source_reassessment', '재검수', context, RequirementGroundingCheck)
    previous = json.loads(request['messages'][1]['content'])['previous']['meanings'][0]
    assert previous['previous_evidence_refs'] == ['e1']
    assert context['previous']['meanings'] == [old]
    output = business_run.json_call(None, run, 'source_reassessment', '재검수', context, RequirementGroundingCheck)
    if status == 'unknown':
        assert output['meanings'][0]['evidence'] == [] and output['meanings'][0]['source_status'] == 'unknown'
    else:
        assert output is None and run['units'][-1]['error'].startswith('schema_error')
    raw['meanings'][0]['evidence'] = ['e2']  # Explicit selection replaces the old source; no quote inference.
    output = business_run.json_call(None, run, 'source_reassessment', '재검수', context, RequirementGroundingCheck)
    assert output['meanings'][0]['evidence'] == business_run.exact_evidence(
        [dict(block_id='new', quote=blocks[1]['text'])], blocks)
    assert output['meanings'][0]['source_status'] == status
    assert run['units'][-1]['response']['parsed'] == raw


def test_representation_requires_explicit_incorrect_ids_without_inference():
    from pydantic import ValidationError
    from app.knowledge.business_models import LocalRepresentationCheck
    row = dict(meaning_key='m', status='represented', claim_ids=['normal'], reason='오류 후보 mixed도 있음')
    output = dict(source_checks=[], checks=[row], source_challenges=[])
    with pytest.raises(ValidationError, match='incorrect_claim_ids'):
        LocalRepresentationCheck.model_validate(output)
    row['incorrect_claim_ids'] = []
    assert LocalRepresentationCheck.model_validate(output).checks[0].incorrect_claim_ids == []
    row['incorrect_claim_ids'] = ['mixed']
    check = LocalRepresentationCheck.model_validate(output).checks[0]
    assert check.claim_ids == ['normal'] and check.incorrect_claim_ids == ['mixed']


def test_requirement_query_keeps_approved_coverage_and_rejects_unknown_or_too_small_scope(tmp_path, monkeypatch):
    from copy import deepcopy
    from app.knowledge.business_models import BusinessQuery
    from app.knowledge.discovery_profile import FrozenIndex
    service = KnowledgeService(tmp_path/'knowledge.db')
    requirements = [dict(id=rid, revision=1, status='ready') for rid in ['r', 'other']]
    claims = [dict(id=cid, statement=cid, source_version_ids=['v'], raw={})
              for cid in ['mandatory', 'ranked', 'optional', 'other_requirement']]
    shared = dict(block_id='body', source_version_id='v', parse_run_id='parse', start_char=0, end_char=len('공식 제목과 원문 범위'),
                  quote='공식 제목과 원문 범위', precision='chunk')
    claims[0]['evidence'] = [shared, deepcopy(shared)]
    claims[1]['evidence'] = [deepcopy(shared), dict(shared, quote=shared['quote'][:2], end_char=2)]
    claims[2]['evidence'] = [dict(shared, block_id='optional', quote='다른 후보의 근거', end_char=len('다른 후보의 근거'))]
    representation = dict(source_checks=[dict(meaning_key='required', required_for_requirement=True),
        dict(meaning_key='optional', required_for_requirement=False)],
        checks=[dict(meaning_key='required', status='represented', claim_ids=['mandatory', 'not_approved']),
                dict(meaning_key='optional', status='represented', claim_ids=['optional'])])
    snapshot = dict(id='s', kind='source_graph', run_id='origin', source_versions={'v':{}}, requirements=requirements,
        assessments=dict(r=dict(requirement_id='r', status='satisfied', representation=representation),
            other=dict(requirement_id='other', status='satisfied', representation=dict(
                source_checks=[dict(meaning_key='x', required_for_requirement=True)],
                checks=[dict(meaning_key='x', status='represented', claim_ids=['other_requirement'])]))),
        claims=claims, concepts=[], blocks=[dict(id='body', locator=dict(line=4)),
                                         dict(id='optional', locator=dict(line=8))])
    supplied = []
    def answer(_service, run, stage, instruction, context, schema, **kwargs):
        ids = [c['id'] for c in context['context']]
        supplied.append(ids)
        evidence = context['source_evidence']
        shared_row = next(row for row in evidence if row['id'] == 'body')
        assert shared_row['text'] == shared['quote']
        assert shared_row['source_version_id'] == 'v' and shared_row['parse_run_id'] == 'parse'
        assert shared_row['span'] == [shared['start_char'], shared['end_char']]
        assert len(shared_row['claim_references']) == 2
        assert shared_row['claim_references'][1]['span'] == [0, 2]
        assert shared_row['claim_references'][0]['precision'] == 'chunk'
        assert shared_row['claim_references'][0]['span'] == [shared['start_char'], shared['end_char']]
        assert 'source_version_id' not in shared_row['claim_references'][0]  # Inherited from the enclosing view.
        if 'mandatory' in ids:
            assert len(evidence) == 1 and shared_row['claim_references'][0]['claim_ids'] == ['mandatory', 'ranked']
        else:
            assert len(evidence) == 2 and shared_row['claim_references'][0]['claim_ids'] == ['ranked']
        assert '같은 인용 안의 다른 의미까지 승인된 것으로 취급하지 않는다.' in instruction
        return dict(answer='제공된 근거', choice=None, citations=[ids[0]], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(FrozenIndex, 'search', lambda *args: [dict(block_id='ranked', file_id='v', score=1.0),
                                                          dict(block_id='optional', file_id='v', score=.5)])
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(dict(id='origin', status='succeeded', recipe={}, model_identity={}))))
            for req in requirements:
                db.execute('INSERT INTO requirements VALUES(?,?)', (req['id'], json.dumps(req)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(snapshot)))
        query = dict(snapshot_id='s', question='업무 요구 답변', retrieval='bm25', limit=2)
        unscoped = business_use.query(service, BusinessQuery(**query))
        assert supplied[-1] == ['ranked', 'optional'] and unscoped['status'] == 'answered'
        scoped = business_use.query(service, BusinessQuery(**query, requirement_ids=['r']))
        assert supplied[-1] == ['mandatory', 'ranked'] and scoped['status'] == 'answered'
        assert scoped['retrieval'][0]['selection_reason'] == 'required_reviewed_meaning'
        assert service.run(scoped['run_id'])['required_context_ids'] == ['mandatory']
        count = len(supplied)
        with pytest.raises(ValueError, match='snapshot'):
            business_use.query(service, BusinessQuery(**query, requirement_ids=['missing']))
        with pytest.raises(ValueError, match='검색 한도'):
            business_use.query(service, BusinessQuery(snapshot_id='s', question=query['question'], limit=1,
                                                       requirement_ids=['r', 'other']))
        assert len(supplied) == count
        with service.repository.connect() as db:
            req = dict(requirements[0], revision=2)
            service.repository.save(db, 'requirements', req)
        assert business_use.query(service, BusinessQuery(**query, requirement_ids=['r']))['status'] == 'needs_review'
        assert len(supplied) == count
    finally:
        service.shutdown()


def test_answer_meanings_keep_review_scope_and_uncertainty_without_promoting_source():
    from app.tests.unit.test_knowledge_business_local_review import meaning
    block = dict(id='body', source_version_id='v', parse_run_id='p', text='기관은 신청을 접수한다.', span=[0, 13])
    normal = meaning('normal')
    normal.update(conditions=['대리 신청'], exceptions=['다른 업무 제외'], period='접수 시')
    uncertain = dict(deepcopy(normal), key='uncertain', source_status='unknown', reason='적용 미확정')
    def assessment(rid, meanings, ids):
        return dict(id=rid, source=dict(meanings=meanings), representation=dict(checks=[
            dict(meaning_key=m['key'], status='represented' if m['source_status']=='supported' else 'unknown', claim_ids=ids)
            for m in meanings]))
    snapshot = dict(blocks=[block], assessments=dict(
        chosen=assessment('a', [normal, uncertain], ['selected', 'unselected']),
        other=assessment('other', [dict(deepcopy(normal), key='other')], ['selected'])))
    before = deepcopy(snapshot)
    rows = business_use.reviewed_answer_meanings(snapshot, {'selected'}, ['chosen'])
    assert len(rows) == 2 and all(r['claim_ids'] == ['selected'] and r['requirement_id']=='chosen' for r in rows)
    assert rows[0]['conditions'] == ['대리 신청'] and rows[0]['exceptions'] == ['다른 업무 제외']
    assert rows[1]['source_status'] == 'unknown' and rows[1]['expression_status'] == 'unknown'
    assert rows[0]['evidence'][0]['quote'] == block['text'] and snapshot == before
    assert business_use.reviewed_answer_meanings(dict(blocks=[block], assessments={}), {'selected'}, []) == []
    normal['evidence'][0]['quote'] = '원문에 없는 허용'
    invalid = business_use.reviewed_answer_meanings(snapshot, {'selected'}, ['chosen'])[0]
    assert invalid['record_error'] and invalid['evidence'] == []


@pytest.mark.parametrize('support', ['supported', 'unknown', 'not_assessed'])
def test_qa_source_compaction_keeps_mandatory_context_and_never_uses_partial_review(tmp_path, monkeypatch, support):
    from app.knowledge.business_models import BusinessQuery
    from app.knowledge.discovery_profile import FrozenIndex
    from app.tests.unit.test_knowledge_business_scope import block
    from app.tests.unit.test_knowledge_business_local_review import meaning
    blocks = [dict(block('title', '접수 안내', path='h1:1'), source_id='s'),
              dict(block('body', '기관은 신청을 접수한다.', path='div:1 > ul:1 > li:1'), source_id='s'),
              dict(block('note', '다만, 대리 신청은 위임장이 필요하다.', path='div:1 > ul:1 > li:2'), source_id='s'),
              dict(block('unrelated', '다른 부서 소식', path='div:2 > p:1'), source_id='s')]
    refs = [dict(business_run.exact_evidence([dict(block_id=b['id'], quote=b['text'])], blocks)[0], precision='chunk') for b in blocks]
    m = meaning('m')
    m['evidence'] = business_run.exact_evidence(m['evidence'], blocks)
    c = dict(id='c', role='entity_relation', raw=dict(Head='기관', Relation='접수', Tail='신청'),
             source_version_ids=[blocks[0]['source_version_id']], evidence=refs)
    req = dict(id='r', revision=1, status='ready', question='대리 신청 접수 조건은?',
               criterion='신청 서류와 접수 기관을 확인', target='대리인', history=['이전 판정'])
    a = dict(id='a', requirement_id='r', status='satisfied', source=dict(meanings=[m]), representation=dict(
        source_checks=[dict(meaning_key='m', required_for_requirement=True)],
        checks=[dict(meaning_key='m', status='represented' if support=='supported' else 'partial',
                     claim_ids=['c'], claim_support={'c': support})]))
    snap = dict(id='snap', kind='source_graph', run_id='origin', source_versions={blocks[0]['source_version_id']:{}},
        requirements=[req], assessments={'r':a}, claims=[c], concepts=[], blocks=blocks)
    options = BusinessRunRequest(source_version_ids=['v'], requirement_ids=['r']).model_dump()
    seen = []
    def answer(_service, run, stage, instruction, context, schema, **kwargs):
        seen.append(context)
        return dict(answer='기관은 신청을 접수한다.', choice=None, citations=['c'], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(FrozenIndex, 'search', lambda *args: [dict(block_id='c', file_id=blocks[0]['source_version_id'], score=1.0)])
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(dict(id='origin', status='succeeded', recipe=dict(options=options), model_identity={}))))
            db.execute('INSERT INTO requirements VALUES(?,?)', ('r', json.dumps(req)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('snap', json.dumps(snap)))
        business_use.query(service, BusinessQuery(snapshot_id='snap', question='대리 신청 접수 조건은?', requirement_ids=['r'], retrieval='bm25'))
        delivered = {b['id']:b['text'] for b in seen[0]['source_evidence']}
        assert delivered['body']==blocks[1]['text'] and delivered['note']==blocks[2]['text']
        assert ('unrelated' not in delivered) if support=='supported' else ('unrelated' in delivered)
        assert seen[0]['reviewed_meanings'][0]['claim_support'] == {'c':support}
        public = seen[0]['public_requirements'][0]
        assert public['criterion'] == req['criterion'] and public['question'] == req['question']
        assert 'status' not in public and 'history' not in public
        with service.repository.connect() as db: assert service.repository.get(db, 'snapshots', 'snap') == snap
    finally:
        service.shutdown()


@pytest.mark.parametrize('field', ['finding_resolutions', 'meaning_challenges', 'candidate_challenges'])
def test_evidence_selection_preserves_declared_nested_contract_in_sent_request(monkeypatch, field):
    from typing import Literal, get_args
    from pydantic import Field, create_model
    from app.knowledge.business_models import ContributionSynthesisCheck
    row_type = get_args(ContributionSynthesisCheck.model_fields[field].annotation)[0]
    row_type = create_model('RequiredAttribution', __base__=row_type,
        independent_meaning_keys=(list[Literal['m']], Field(..., max_length=1)))
    output_type = create_model('AttributedSynthesis', __base__=ContributionSynthesisCheck,
        **{field: (list[row_type], Field(...))})
    blocks = [dict(id='block', source_version_id='version', parse_run_id='parse', text='확인된 사실')]
    run = dict(blocks=blocks, claims=[], sources={}, units=[], recipe=dict(options={}))
    row = (dict(finding_id='f', status='unresolved', meaning_keys=['m'], claim_ids=[], fields=[], reason='관계 미확정')
        if field == 'finding_resolutions' else dict(meaning_key='m', claim_ids=[], fields=['statement'], reason='원문 대조'))
    row.update(evidence=['e1'], independent_meaning_keys=['m'])
    raw = dict(checks=[], dependencies=[], source_challenges=[], meaning_challenges=[], candidate_challenges=[],
        satisfied=False, conjunctions_satisfied=False, reason='전체 미완료', source_completeness='partial',
        unselected_source_required=False, finding_resolutions=[])
    raw[field] = [row]
    def generate(_service, _run, _stage, messages, schema, **kwargs):
        nested = schema['$defs']['SelectedRequiredAttribution']
        assert 'independent_meaning_keys' in nested['required']
        assert nested['properties']['independent_meaning_keys']['items']['const'] == 'm'
        assert nested['properties']['independent_meaning_keys']['maxItems'] == 1
        assert nested['properties']['evidence']['items']['const'] == 'e1'
        run['units'].append(dict(response={'parsed': deepcopy(raw)}, schema=schema))
        return run['units'][-1]['response']
    monkeypatch.setattr(business_run, 'call', generate)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    output = business_run.json_call(None, run, 'requirement_representation', '종합', dict(blocks=blocks), output_type)
    assert output[field][0]['independent_meaning_keys'] == ['m']
    assert output[field][0]['evidence'] == business_run.exact_evidence(
        [dict(block_id='block', quote=blocks[0]['text'])], blocks)
    assert run['units'][-1]['response']['parsed'] == raw
    for value in (None, ['outside'], 'm'):
        if value is None:
            row.pop('independent_meaning_keys')
        else:
            row['independent_meaning_keys'] = value
        assert business_run.json_call(None, run, 'requirement_representation', '종합', dict(blocks=blocks), output_type) is None
        assert run['units'][-1]['error'].startswith('schema_error')
        assert run['units'][-1]['response']['parsed'] == raw

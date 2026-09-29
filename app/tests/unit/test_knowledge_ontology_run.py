"""Bounded K3 execution checks; model responses are local, fixed JSON."""
import json
import asyncio
from threading import Event

from app.knowledge import ontology_run, ontology_schema
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_service import finished


def test_draft_model_and_design_timeout_are_frozen_in_recipe(monkeypatch):
    monkeypatch.setattr(ontology_run.settings, 'KNOWLEDGE_DESIGN_TIMEOUT', 360)
    monkeypatch.setattr(ontology_run.settings, 'STRUCTURING_MODEL', 'draft-model')
    run = {'recipe': ontology_run.recipe()}
    monkeypatch.setattr(ontology_run.settings, 'STRUCTURING_MODEL', 'changed-later')
    calls = []
    async def call(self, prompt, **kwargs):
        calls.append(kwargs)
        return {'text': '{}'}
    monkeypatch.setattr(ontology_run.GenerationService, 'call_ollama', call)
    for stage in ('analyze', 'design', 'revise'):
        asyncio.run(ontology_run.model_call('input', {}, stage, run))
    assert [c['model'] for c in calls] == ['draft-model'] * 3
    assert [c['timeout'] for c in calls] == [None, 360, None]
    assert all(c['think'] is False for c in calls)


def parsed_source(service, name='one'):
    registered = service.register(
        name + '.csv', '단지명\n행복단지\n'.encode(),
        SourceRegistration(title=name, publisher='LH', namespace='test', external_id=name))
    rid = service.start(RunRequest(source_version_ids=[registered['source_version_id']]))['run_id']
    assert finished(service, rid)['status'] == 'succeeded'
    return registered, rid


def request_for(*versions):
    return RunRequest(kind='ontology', source_version_ids=list(versions),
                      cqs=[{'id': 'CQ1', 'question': '단지란 무엇인가?'}])


def reply(prompt, stage, run, *, revision=False):
    context, _ = json.JSONDecoder().raw_decode(prompt.split('\nINPUT:\n', 1)[1])
    if stage == 'analyze':
        block = context['blocks'][0]
        value = {'observations': [{'term': '단지', 'meaning': '주택 단지',
                                   'evidence': [{'evidence_id': block['ref'], 'quote': block['text']}],
                                   'cq_ids': ['CQ1']}]}
    elif stage == 'review':
        value = {'needs_revision': revision, 'issues': ([{
            'candidate_id': 'Complex', 'reason': '정의 범위 불명확', 'suggestion': '주택 단지로 한정'}]
            if revision else [])}
    else:
        value = {'candidates': [{'id': 'Complex', 'kind': 'concept', 'name': '단지',
                                  'definition': '주택 단지' if stage == 'revise' else '단지',
                                  'inclusion': '자료에 등장하는 주택 단지', 'exclusion': '개별 세대',
                                  'evidence': [{'evidence_id': 'b0', 'quote': run['frozen_blocks'][0]['text']}],
                                  'cq_ids': ['CQ1']}]}
    return {'text': json.dumps(value, ensure_ascii=False), 'done': True,
            'done_reason': 'stop', 'prompt_eval_count': 100, 'eval_count': 50}


def test_analysis_plus_two_calls_publish_without_changing_parse(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    calls = []
    async def model(prompt, schema, stage, run):
        calls.append(stage)
        return reply(prompt, stage, run)
    monkeypatch.setattr(ontology_run, 'model_call', model)
    try:
        first, parse_one = parsed_source(service)
        second, parse_two = parsed_source(service, 'two')
        rid = service.start(request_for(first['source_version_id'], second['source_version_id']))['run_id']
        run = finished(service, rid)
        assert run['status'] == 'succeeded', run
        assert calls == ['analyze', 'analyze', 'design', 'review']
        assert run['metrics']['llm_calls'] == 4
        draft = ontology_schema.get_ontology(service, run['ontology_version_id'])
        assert draft['status'] == 'draft'
        assert draft['candidates'][0]['id'] == 'Complex'
        assert 'Complex' in draft['linkml_schema']['classes']
        assert draft['json_schema']
        assert ontology_schema.candidates(service, run['changeset_id'])['items']
        for registered, parse_id in [(first, parse_one), (second, parse_two)]:
            version = service.version(registered['source_id'], registered['source_version_id'])['version']
            assert version['processing_status'] == 'parsed'
            assert version['latest_parse_run_id'] == parse_id
    finally:
        service.shutdown()


def test_review_requests_only_one_revision(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    calls = []
    async def model(prompt, schema, stage, run):
        calls.append(stage)
        return reply(prompt, stage, run, revision=True)
    monkeypatch.setattr(ontology_run, 'model_call', model)
    try:
        registered, _ = parsed_source(service)
        run = finished(service, service.start(request_for(registered['source_version_id']))['run_id'])
        assert run['status'] == 'succeeded', run
        assert calls == ['analyze', 'design', 'review', 'revise']
        assert run['metrics']['llm_calls'] == 4
        assert run['review']['needs_revision'] is True
        assert ontology_schema.get_ontology(service, run['ontology_version_id'])['candidates'][0]['definition'] == '주택 단지'
    finally:
        service.shutdown()


def test_failed_prefix_and_frozen_blocks_survive_reparse_and_restart(tmp_path, monkeypatch):
    path = tmp_path / 'knowledge.db'
    service = KnowledgeService(path)
    calls, frozen_ids = [], []
    fail_design = True
    async def model(prompt, schema, stage, run):
        calls.append(stage)
        frozen_ids.append(run['frozen_blocks'][0]['id'])
        if stage == 'design' and fail_design:
            raise RuntimeError('temporary model failure')
        return reply(prompt, stage, run)
    monkeypatch.setattr(ontology_run, 'model_call', model)
    resumed = None
    try:
        registered, _ = parsed_source(service)
        sid, vid = registered['source_id'], registered['source_version_id']
        failed = finished(service, service.start(request_for(vid))['run_id'])
        assert failed['status'] == 'failed'
        assert failed['metrics']['llm_calls'] == 2
        original = failed['frozen_blocks'][0]['id']
        reparse = finished(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
        assert reparse['status'] == 'succeeded'
        assert service.blocks(sid, vid)['items'][0]['id'] != original
        # Persist a queued retry, then simulate process loss before its worker starts.
        monkeypatch.setattr(service.executor, 'submit', lambda *args: None)
        queued = service.start(RunRequest(kind='ontology', retry_of_run_id=failed['id']))['run_id']
        service.executor.shutdown()
        resumed = KnowledgeService(path)
        assert resumed.run(queued)['status'] == 'failed'
        assert resumed.version(sid, vid)['version']['latest_parse_run_id'] == reparse['id']
        fail_design = False
        retry = finished(resumed, resumed.start(RunRequest(kind='ontology', retry_of_run_id=queued))['run_id'])
        assert retry['status'] == 'succeeded', retry
        assert calls == ['analyze', 'design', 'design', 'review']
        assert set(frozen_ids) == {original}
        assert retry['reused_units'] == ['analyze-1']
        assert retry['metrics']['llm_calls'] == 2
    finally:
        if resumed:
            resumed.shutdown()
        service.shutdown()


def test_truncated_output_fails_and_cancelled_retry_reuses_completed_calls(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    entered, release = Event(), Event()
    calls = []
    truncate = True
    async def model(prompt, schema, stage, run):
        calls.append(stage)
        result = reply(prompt, stage, run)
        if stage == 'design' and truncate:
            result['done_reason'] = 'length'
        if stage == 'review':
            entered.set()
            assert release.wait(5)
        return result
    monkeypatch.setattr(ontology_run, 'model_call', model)
    try:
        registered, _ = parsed_source(service)
        failed = finished(service, service.start(request_for(registered['source_version_id']))['run_id'])
        assert failed['status'] == 'failed'
        assert '잘렸습니다' in failed['units'][1]['error']
        assert failed['units'][1]['raw_output']
        assert 'ontology_version_id' not in failed
        truncate = False
        rid = service.start(RunRequest(kind='ontology', retry_of_run_id=failed['id']))['run_id']
        assert entered.wait(5)
        service.cancel(rid)
        release.set()
        cancelled = finished(service, rid)
        assert cancelled['status'] == 'cancelled'
        assert 'ontology_version_id' not in cancelled
        completed_calls = list(calls)
        retry = finished(service, service.start(RunRequest(kind='ontology', retry_of_run_id=rid))['run_id'])
        assert retry['status'] == 'succeeded', retry
        assert calls == completed_calls == ['analyze', 'design', 'design', 'review']
        assert retry['metrics']['llm_calls'] == 0
        assert retry['ontology_version_id']
    finally:
        release.set()
        service.shutdown()

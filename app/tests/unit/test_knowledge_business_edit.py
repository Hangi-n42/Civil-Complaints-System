"""User Event edits share storage but never inherit semantic approval."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_edit, business_run, business_use, business_review
from app.knowledge.business_models import BusinessEventEdit
from app.knowledge.service import KnowledgeConflict, KnowledgeService, encode
from app.tests.unit.test_knowledge_business_event_repair import event_case
from app.tests.unit.test_knowledge_business_local_review import meaning, judgments


@pytest.fixture
def editing(tmp_path, monkeypatch):
    run, _, patch = event_case()
    run.update(kind='business', status='partial', units=[], analysis_units=[], model_identity={}, concepts=[],
               input_version_ids=['v'], sources={'v': {'title': '합성 자료'}})
    run['recipe']['options']['conceptualize'] = False
    run['recipe'].update(generation={'provider': 'ollama', 'endpoint': 'http://localhost:11434'}, models={})
    run['claims'][0].update(interpretation={'raw': {'old': True}, 'meanings': [], 'mentions': []},
                           conditions=['이전 조건'], exceptions=['이전 예외'], period='이전 기간', references=['이전 참조'])
    service = KnowledgeService(tmp_path / 'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
        for r in run['requirements']:
            r.setdefault('revision', 1); r.setdefault('status', 'partial'); r.setdefault('history', [])
            db.execute('INSERT INTO requirements VALUES(?,?)', (r['id'], encode(r)))
        service.repository.save(db, 'runs', run)
    change = business_use.publish(service, run)
    monkeypatch.setattr(service.executor, 'submit', lambda *args: None)
    request = BusinessEventEdit(expected_revision=0, expected_claim_version=autoschema.identifier('claim', run['claims'][0]),
        claim_id=run['claims'][0]['id'], actor='synthetic-operator', reason='원문 대조 합성 검사',
        event=patch['raw']['Event'], evidence=patch['evidence'])
    yield service, run, change, request
    service.shutdown()


def test_user_edit_preserves_history_and_siblings_without_scope_or_approval(editing):
    service, parent, change, request = editing
    before = deepcopy(parent)
    result = business_edit.start(service, change['id'], request)
    child = service.run(result['run_id'])
    old, new = parent['claims'][0], child['claims'][0]
    assert new['raw'] == dict(Event=request.event, Entity=old['raw']['Entity'])
    assert new['statement'] == request.event
    assert new['review_status'] == 'unreviewed' and new['semantic_status'] == 'unknown'
    assert new['qualifier_status'] == 'unparsed_user_text_requires_review'
    assert not new.get('interpretation') and new['interpretation_history'][-1] == old['interpretation']
    assert not new['conditions'] and not new['exceptions'] and not new['period'] and not new['references']
    assert child['claims'][1:] == parent['claims'][1:]
    receipt = child['repairs'][0]
    assert receipt['before'] == parent['claims'] and receipt['after'] == child['claims']
    assert receipt['origin'] == 'user' and receipt['actor'] == request.actor and receipt['reason'] == request.reason
    assert receipt['status'] == 'applied_awaiting_recheck'
    assert new['id'] not in business_use.eligibility(child)[0]
    assert parent == before
    assert service.run(parent['id'])['claims'] == parent['claims']
    assert business_use.snapshots(service)['items'] == []
    with pytest.raises(KnowledgeConflict):
        business_edit.start(service, change['id'], request)


@pytest.mark.parametrize('fault', ['revision', 'version', 'role', 'superseded', 'foreign_quote', 'no_change'])
def test_rejected_edit_does_not_mutate_run_or_revision(editing, fault):
    service, parent, change, request = editing
    if fault == 'revision': request.expected_revision = 2
    elif fault == 'version': request.expected_claim_version = 'stale'
    elif fault in {'role', 'superseded'}:
        if fault == 'role': parent['claims'][0]['role'] = 'entity_relation'
        else: parent['claims'][0]['superseded_by'] = ['other']
        change['candidates'] = deepcopy(parent['claims'])
        request.expected_claim_version = autoschema.identifier('claim', parent['claims'][0])
        with service.repository.connect() as db:
            service.repository.save(db, 'runs', parent); service.repository.save(db, 'changesets', change)
    elif fault == 'foreign_quote': request.evidence[0].quote = '없는 인용'
    else: request.event = parent['claims'][0]['raw']['Event']
    with pytest.raises((KnowledgeConflict, ValueError)):
        business_edit.start(service, change['id'], request)
    assert service.run(parent['id'])['claims'] == parent['claims']
    assert business_use.change_view(service, change['id'])['revision'] == 0


def test_api_contract_cannot_change_entity_role_or_supply_scope(editing):
    request = editing[3]
    for key, value in [('raw', {'Entity': ['다른 대상']}), ('role', 'entity_relation'), ('scope', {})]:
        with pytest.raises(ValidationError):
            BusinessEventEdit.model_validate(dict(request.model_dump(), **{key: value}))


def test_actual_assess_reads_user_receipt_and_old_judgment_is_stale(editing, monkeypatch):
    service, parent, change, request = editing
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete',
                  gaps=[], conjunctions=[])
    old = dict(id='old-assessment', requirement_id='r', source=source, representation=judgments(['m'], ids=[request.claim_id]),
               errors=[], issues=[], status='satisfied')
    old['input_fingerprint'] = business_run.assessment_fingerprint(parent, parent['requirements'][0], source)
    parent['assessments'] = [old]
    with service.repository.connect() as db: service.repository.save(db, 'runs', parent)
    child = service.run(business_edit.start(service, change['id'], request)['run_id'])
    assert 'stale_assessment' in business_use.eligibility(child)[1][request.claim_id]
    def represent(_service, run, requirement, source, context):
        assert context[0]['targets'][0]['origin'] == 'user'
        assert context[0]['targets'][0]['reason'] == request.reason
        assert context[0]['preserve_meanings'] == []
        assert context[0]['changes'][0]['before']['raw'] == parent['claims'][0]['raw']
        assert context[0]['changes'][0]['after']['raw']['Event'] == request.event
        return None, {'failures': []}
    monkeypatch.setattr(business_review, 'represent', represent)
    assessed = business_run.assess(service, child, child['requirements'][0], source=source, phase='after_user_edit')
    assert assessed['status'] == 'unknown'
    assert request.claim_id not in business_use.eligibility(child)[0]


def test_recheck_consumes_edited_claim_and_publishes_unapproved_change(editing, monkeypatch):
    service, parent, change, request = editing
    started = business_edit.start(service, change['id'], request)
    seen = []
    def assess(_service, run, requirement, *, source, phase):
        assert phase == 'after_user_edit' and run['claims'][0]['raw']['Event'] == request.event
        assert run['repairs'][0]['before'] == parent['claims']
        seen.append(requirement['id'])
        a = dict(id='synthetic-recheck', requirement_id=requirement['id'], source={'meanings': []},
                 representation=None, errors=[], status='unknown')
        run['assessments'].append(a)
        return a
    monkeypatch.setattr(business_run, 'assess', assess)
    monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *args: {})
    business_edit.recheck(service, started['run_id'])
    child = service.run(started['run_id'])
    assert seen == [r['id'] for r in parent['requirements']]
    assert child['status'] == 'partial' and child['repairs'][0]['status'] == 'recheck_incomplete'
    assert child['graph'] == autoschema.graph(child['claims'])
    assert business_use.change_view(service, child['changeset_id'])['eligible_ids'] == []
    assert business_use.snapshots(service)['items'] == []


def test_edit_api_matches_form_contract_and_rejects_stale_submission(editing, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    service, parent, change, request = editing
    app = FastAPI()
    app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    path = f'/api/v1/knowledge/business/changes/{change["id"]}/edits'
    with TestClient(app) as client:
        assert client.post(path, json=dict(request.model_dump(), raw={'Entity': []})).status_code == 422
        response = client.post(path, json=request.model_dump())
        assert response.status_code == 200
        child = client.get('/api/v1/knowledge/runs/' + response.json()['data']['run_id']).json()['data']
        assert child['claims'][0]['raw']['Event'] == request.event
        assert child['claims'][0]['raw']['Entity'] == parent['claims'][0]['raw']['Entity']
        assert client.post(path, json=request.model_dump()).status_code == 409

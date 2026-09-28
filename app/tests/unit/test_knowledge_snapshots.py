"""K5 selection, immutable review, and current restrictions without inference."""
import csv
import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge import snapshots, extraction_store as store, ontology_schema
from app.tests.unit.test_knowledge_extraction_store import setup


def reviewed(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    block = run['frozen_blocks'][0]
    block.update(source_version_id='v1', parse_run_id='run1', locator={'format': 'csv', 'physical_row': 2})
    with service.repository.connect() as db:
        db.execute('UPDATE runs SET payload=? WHERE id=?', (json.dumps(run), 'run1'))
        ontology = service.repository.get(db, 'ontology_versions', 'ontology1')
        ontology['status'] = 'reviewed'
        db.execute('UPDATE ontology_versions SET payload=? WHERE id=?', (json.dumps(ontology), 'ontology1'))
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('source1', 'test', 'source1', json.dumps(dict(id='source1', title='등록부'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('v1', 'source1', 'hash', json.dumps(dict(id='v1', source_id='source1', format='csv', sha256='hash'))))
        db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)', ('block1', 'v1', 'run1', 'parse1', 0, json.dumps(block)))
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion], evidence, [entity])
    store.decide(service, result['changeset_id'], dict(expected_changeset_revision=1, actor='test', decisions=[
        dict(candidate_id='link1', action='accept'), dict(candidate_id='count1', action='accept')]))
    selection = dict(changeset_id=result['changeset_id'], expected_changeset_revision=2, candidate_ids=['link1', 'count1'])
    return service, selection


def create(service, *selections):
    return snapshots.create(service, dict(selections=list(selections), actor='test', reason='선택 검토',
                                         expected_active_id=snapshots.list_snapshots(service)['active_snapshot_id']))['snapshot_id']


def activate(service, identifier):
    return snapshots.activate(service, identifier, dict(actor='test', reason='활성/복원',
                              expected_active_id=snapshots.list_snapshots(service)['active_snapshot_id']))


def state(service, kind, identifier, value):
    return snapshots.set_availability(service, dict(actor='test', reason='상태 확인', targets=[dict(type=kind, id=identifier)],
                   state=value, expected_status_revision=snapshots.list_snapshots(service)['status_revision']))


def test_explicit_selection_atomic_conflicts_and_frozen_payload(tmp_path):
    service, selection = reviewed(tmp_path)
    with pytest.raises(ValueError, match='연결 참조'):
        create(service, dict(selection, candidate_ids=['count1']))
    with pytest.raises(ontology_schema.VersionConflict):
        create(service, dict(selection, expected_changeset_revision=1))
    with pytest.raises(ValueError, match='중복'):
        create(service, selection, selection)
    assert snapshots.list_snapshots(service)['items'] == []
    first = create(service, selection)
    assert snapshots.list_snapshots(service)['active_snapshot_id'] is None
    activate(service, first)
    with service.repository.connect() as db:
        frozen = service.repository.get(db, 'snapshots', first)
    store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=2, decisions=[
        dict(candidate_id='count1', action='modify', patch={'value': 985, 'raw_value': '985',
             'evidence_ids': ['other'], 'field_evidence': {'value': ['other']}}, reason='다른 범위 수정')]))
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', first) == frozen
    assert snapshots.get_snapshot(service)['assertions'] == []
    assert snapshots.availability(service, 'assertion', 'count1')['state'] == 'needs_review'
    with pytest.raises(ValueError, match='사용 불가'):
        create(service, dict(selection, expected_changeset_revision=3))
    with pytest.raises(ontology_schema.VersionConflict):
        snapshots.activate(service, first, dict(actor='test', reason='오래된 화면', expected_active_id=None))
    assert snapshots.list_snapshots(service)['active_snapshot_id'] == first


@pytest.mark.parametrize('kind,identifier', [('evidence', 'code'), ('source_version', 'v1')])
def test_rollback_and_both_exports_obey_link_and_source_restrictions(tmp_path, kind, identifier):
    service, selection = reviewed(tmp_path)
    first = create(service, selection); activate(service, first)
    second = create(service, selection); activate(service, second)
    state(service, kind, identifier, 'blocked')
    result = activate(service, first)
    assert result['counts']['assertions'] == 0 and result['counts']['excluded'] == 1
    assert snapshots.export(service, format='json')['assertions'] == []
    assert list(csv.DictReader(io.StringIO(snapshots.export(service, format='csv')['content']))) == []
    state(service, 'assertion', 'count1', 'allowed')
    assert snapshots.get_snapshot(service)['assertions'] == []  # Cannot override blocked dependency.
    state(service, kind, identifier, 'allowed')
    rows = list(csv.DictReader(io.StringIO(snapshots.export(service, format='csv')['content'])))
    evidence = json.loads(rows[0]['evidence'])[0]
    assert evidence['source_id'] == 'source1' and evidence['locator']['physical_row'] == 2
    assert 'quote' not in evidence and 'text' not in evidence
    assert snapshots.get_snapshot(service, as_of='2010-01-01')['assertions'][0]['validity_status'] == 'unverified'


def test_link_change_batch_reaccept_does_not_clear_block_or_needs_review(tmp_path):
    service, selection = reviewed(tmp_path)
    first = create(service, selection); activate(service, first)
    changed = store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=2, decisions=[
        dict(candidate_id='link1', action='modify', patch={'mention': 'C001'}, reason='별칭 확인'),
        dict(candidate_id='count1', action='accept')]))
    assert all(i['review_status'] == 'accepted' for i in changed['items'])
    assert snapshots.availability(service, 'assertion', 'count1')['state'] == 'needs_review'
    state(service, 'assertion', 'count1', 'blocked')
    store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=3,
                 decisions=[dict(candidate_id='link1', action='unlink', reason='연결 취소')]))
    assert snapshots.availability(service, 'assertion', 'count1')['state'] == 'blocked'
    assert snapshots.get_snapshot(service, first)['assertions'] == []


def test_block_evidence_and_validity_input_boundary(tmp_path):
    service, selection = reviewed(tmp_path)
    result = store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=2, decisions=[
        dict(candidate_id='count1', action='modify', patch={'evidence_ids': ['block1'], 'field_evidence': {'value': ['block1']},
             'dates': [{'role': 'valid_from', 'value': '2026-01-01', 'precision': 'day', 'evidence_ids': ['block1']}]} )]))
    # Accepted human validity interpretation remains separate from machine string alignment.
    state(service, 'assertion', 'count1', 'allowed')
    first = create(service, dict(selection, expected_changeset_revision=3))
    assert snapshots.get_snapshot(service, first, as_of='2025-12-31')['assertions'] == []
    assert snapshots.get_snapshot(service, first, as_of='2026-01-01')['assertions']
    state(service, 'evidence', 'block1', 'blocked')
    assert snapshots.get_snapshot(service, first)['assertions'] == []
    invalid = store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=3, decisions=[
        dict(candidate_id='count1', action='modify', patch={'dates': [{'role': 'valid_from', 'precision': 'day', 'evidence_ids': ['block1']}]})]))
    candidate = next(c for c in invalid['items'] if c['id'] == 'count1')
    assert candidate['review_status'] == 'proposed' and 'invalid_validity_period' in candidate['validation_errors']
    with pytest.raises(ValueError):
        create(service, dict(selection, expected_changeset_revision=4))


def test_multi_changeset_and_http_envelope(tmp_path, monkeypatch):
    from app.api.routers import knowledge
    service, selection = reviewed(tmp_path)
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1'); run['id'] = 'run2'
        db.execute('INSERT INTO runs VALUES(?,?)', ('run2', json.dumps(run)))
        link = service.repository.get(db, 'entity_links', 'link1'); link.update(id='link2', local_candidate_key='link2')
        assertion = service.repository.get(db, 'assertions', 'count1'); assertion.update(id='count2', local_candidate_key='count2', subject_link_id='link2')
    published = store.publish_unit(service, run, {'id': 'u2'}, [link], [assertion], [], [])
    store.decide(service, published['changeset_id'], dict(expected_changeset_revision=1, actor='test', decisions=[
        dict(candidate_id='link2', action='accept'), dict(candidate_id='count2', action='accept')]))
    second = dict(changeset_id=published['changeset_id'], expected_changeset_revision=2, candidate_ids=['link2', 'count2'])
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    with TestClient(app) as client:
        base = '/api/v1/knowledge'
        response = client.post(base+'/snapshots', json=dict(selections=[selection, second], expected_active_id=None, actor='test', reason='다중 묶음'))
        assert response.status_code == 200 and response.json()['success']
        identifier = response.json()['data']['snapshot_id']
        assert client.get(base+'/snapshots/active').json()['data']['snapshot_id'] is None
        assert client.get(base+'/snapshots/'+identifier).json()['data']['counts']['assertions'] == 2
        url = base+'/snapshots/'+identifier+'/activate'
        body = dict(expected_active_id=None, actor='test', reason='활성')
        assert client.post(url, json=body).status_code == 200
        assert client.post(url, json=body).status_code == 409
        assert client.get(base+'/export?format=invalid').status_code == 422
        assert client.get(base+'/snapshots/active?as_of=invalid').status_code == 422


def test_invalid_candidates_keep_review_annotations_without_crashing(tmp_path):
    service, selection = reviewed(tmp_path)
    result = store.decide(service, selection['changeset_id'], dict(actor='test', expected_changeset_revision=2, decisions=[
        dict(candidate_id='count1', action='modify', patch={'dates': [None], 'field_evidence': None})]))
    invalid = next(c for c in result['items'] if c['id'] == 'count1')
    assert invalid['review_status'] == 'proposed'
    assert {'invalid_dates', 'field_evidence_required'} <= set(invalid['validation_errors'])
    assert invalid['usage_restrictions'][0]['state'] == 'needs_review'
    assert store.candidates(service, selection['changeset_id'])['items']

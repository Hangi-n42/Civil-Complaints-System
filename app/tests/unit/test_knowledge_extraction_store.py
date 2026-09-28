"""K4 review boundaries: provenance, direct dependencies, retries and K3 dispatch."""
import json
from threading import RLock
from types import SimpleNamespace

import pytest

from app.knowledge.repository import KnowledgeRepository
from app.knowledge import ontology_schema as ontology
from app.knowledge import extraction_store as store


def setup(tmp_path):
    service = SimpleNamespace(repository=KnowledgeRepository(tmp_path / 'knowledge.db'), lock=RLock())
    concept = dict(id='Complex', kind='concept', name='단지', definition='임대 단지', inclusion='단지', exclusion='세대',
                   domain_id=None, range='string', multivalued=False, required=False, enum_values=[], evidence=[], cq_ids=[])
    count = dict(concept, id='Households', kind='attribute', domain_id='Complex', range='integer')
    month = dict(concept, id='FirstMonth', kind='attribute', domain_id='Complex', range='string')
    text, _ = ontology.build_schema([concept, count, month])
    block = dict(id='block1', evidence_id='whole1', text='C001 단지 521세대, 985호, 최초입주 201106')
    run = dict(id='run1', kind='extract', ontology_version_id='ontology1', frozen_blocks=[block])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('run1', json.dumps(run)))
        db.execute('INSERT INTO ontology_versions VALUES(?,?)', ('ontology1', json.dumps(dict(id='ontology1', linkml_yaml=text))))
    evidence = []
    for key, quote in [('code', 'C001'), ('count', '521'), ('other', '985'), ('month', '201106')]:
        start = block['text'].index(quote)
        evidence.append(dict(id=key, block_id='block1', quote=quote, start_char=start, end_char=start+len(quote), alignment_status='matched'))
    entity = dict(id='entity1', namespace='lh-complex', official_id='C001', concept_id='Complex', name='단지', evidence_ids=['code'])
    link = dict(id='link1', local_candidate_key='link1', mention='단지', concept_id='Complex', target_entity_id='entity1',
                method='official_id', scope={'source': 'csv'}, evidence_ids=['code'])
    assertion = dict(id='count1', local_candidate_key='count1', subject_link_id='link1', subject_id='entity1',
                     predicate_id='Households', object_link_id=None, object_entity_id=None, value=521, raw_value='521', unit='세대',
                     scope={'description': 'CSV 집계'}, conditions=[], exceptions=[], dates=[], evidence_ids=['count'], field_evidence={'value': ['count']})
    return service, run, entity, link, assertion, evidence


def test_publish_idempotence_scope_and_invalid_candidates(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    other = dict(assertion, id='count2', local_candidate_key='count2', value=985, raw_value='985', unit='호',
                 scope={'description': '공고 집계'}, evidence_ids=['other'], field_evidence={'value': ['other']})
    month = dict(assertion, id='month1', local_candidate_key='month1', predicate_id='FirstMonth', value='2011-06', raw_value='201106',
                 evidence_ids=['month'], field_evidence={'value': ['month']}, dates=[{'role': 'first_occupancy', 'precision': 'month', 'value': '2011-06'}])
    bad = dict(assertion, id='bad', local_candidate_key='bad', predicate_id='NotInOntology')
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion, other, month, bad], evidence, [entity])
    repeated = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion, other, month, bad], evidence, [entity])
    assert result == repeated
    assert result['counts']['invalid'] == 1
    items = store.candidates(service, result['changeset_id'])['items']
    assert len(items) == 5 and items[1]['scope'] != items[2]['scope']
    assert items[3]['value'] == '2011-06' and items[3]['dates'][0]['precision'] == 'month'
    assert 'unknown_predicate' in items[4]['validation_errors']
    assert ontology.candidates(service)['items'] == []  # K3 default does not mix extraction candidates.
    assert len(ontology.candidates(service, kind='assertion')['items']) == 4
    with pytest.raises(ValueError, match='수락할 수 없는'):
        store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1,
                     decisions=[dict(candidate_id='bad', action='accept')]))


def test_atomic_accept_modify_unlink_and_conflict(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion], evidence, [entity])
    change_id = result['changeset_id']
    accepted = ontology.decide(service, change_id, dict(actor='test', expected_changeset_revision=1, decisions=[
        dict(candidate_id='count1', action='accept'), dict(candidate_id='link1', action='accept')]))
    assert all(i['review_status'] == 'accepted' for i in accepted['items'])
    assert accepted['items'][1]['link_dependencies'] == [{'link_id': 'link1', 'revision': 1}]
    with pytest.raises(ontology.VersionConflict):
        store.decide(service, change_id, dict(actor='test', expected_changeset_revision=1,
                     decisions=[dict(candidate_id='count1', action='defer')]))
    cancelled = store.decide(service, change_id, dict(actor='test', expected_changeset_revision=2,
                     decisions=[dict(candidate_id='link1', action='unlink', reason='잘못된 단지 연결')]))
    by_id = {i['id']: i for i in cancelled['items']}
    assert by_id['link1']['target_entity_id'] is None
    assert by_id['count1']['review_status'] == 'proposed'
    assert by_id['count1']['subject_id'] == 'entity1'  # Original accepted target is not silently overwritten.
    assert 'dependency_changed' in by_id['count1']['validation_errors']
    history = store.candidates(service, change_id)['changesets'][0]['decisions']
    assert any(h['action'] == 'dependency_changed' and h['before']['review_status'] == 'accepted' for h in history)
    assert cancelled['changeset_revision'] == 3
    modified = store.decide(service, change_id, dict(actor='test', expected_changeset_revision=3,
                   decisions=[dict(candidate_id='count1', action='modify', patch={'value': 'invalid integer'})]))
    assert next(i for i in modified['items'] if i['id'] == 'count1')['review_status'] == 'proposed'
    wrong_alias = store.decide(service, change_id, dict(actor='test', expected_changeset_revision=4,
                    decisions=[dict(candidate_id='link1', action='modify', patch={
                        'target_entity_id': 'entity1', 'mention': '없는 원문명', 'evidence_ids': ['code']})]))
    alias = next(i for i in wrong_alias['items'] if i['kind'] == 'entity_link')
    assert alias['review_status'] == 'proposed' and 'mention_not_in_evidence' in alias['validation_errors']
    corrected = store.decide(service, change_id, dict(actor='test', expected_changeset_revision=5,
                    decisions=[dict(candidate_id='link1', action='modify', patch={'mention': 'C 001', 'evidence_ids': ['code']})]))
    assert next(i for i in corrected['items'] if i['kind'] == 'entity_link')['review_status'] == 'accepted'
    history = store.candidates(service, change_id)['changesets'][0]['decisions']
    assert history[-1]['before']['mention'] == '없는 원문명'


def test_unmatched_or_invented_official_id_cannot_accept(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    entity['official_id'] = 'C999'
    evidence[1].update(start_char=None, end_char=None, alignment_status='ambiguous')
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion], evidence, [entity])
    items = {i['id']: i for i in result['items']}
    assert 'official_id_not_in_evidence' in items['link1']['validation_errors']
    assert 'evidence_alignment_unresolved' in items['count1']['validation_errors']
    with pytest.raises(ValueError):
        store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1,
                     decisions=[dict(candidate_id='link1', action='accept')]))


def test_literal_and_condition_evidence_are_required_before_acceptance(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    # The original K2 block remains usable even if no partial extraction was saved for it.
    block = dict(run['frozen_blocks'][0], source_version_id='source-version1')
    with service.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('source1', 'test', 'source1', json.dumps({'id': 'source1'})))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('source-version1', 'source1', 'hash', json.dumps({'id': 'source-version1', 'source_id': 'source1'})))
        db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)', ('block1', 'source-version1', 'run1', 'parse1', 0, json.dumps(block)))
    assertion.update(raw_value='452', value=452, conditions=['521세대 범위'], exceptions=['985호 제외'])
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion], evidence, [entity])
    invalid = next(i for i in result['items'] if i['kind'] == 'assertion')
    assert {'raw_value_not_in_value_evidence', 'conditions_evidence_required', 'exceptions_evidence_required'} <= set(invalid['validation_errors'])
    with pytest.raises(ValueError, match='raw_value_not_in_value_evidence'):
        store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1, decisions=[
            dict(candidate_id='link1', action='accept'), dict(candidate_id='count1', action='accept')]))
    reviewed = store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1, decisions=[
        dict(candidate_id='link1', action='accept'),
        dict(candidate_id='count1', action='modify', patch={'value': 521, 'raw_value': '521',
             'evidence_ids': ['block1'], 'field_evidence': {'value': ['block1'], 'conditions': ['block1'], 'exceptions': ['block1']}})]))
    valid = next(i for i in reviewed['items'] if i['kind'] == 'assertion')
    assert valid['review_status'] == 'accepted' and valid['validation_errors'] == []
    from app.knowledge.service import KnowledgeService
    resolved = KnowledgeService.evidence(service, 'block1')['evidence']
    assert resolved['quote'] == block['text'] and resolved['start_char'] == 0
    with service.repository.connect() as db:
        assert db.execute('SELECT id FROM evidence WHERE id=?', ('block1',)).fetchone() is None


def test_month_normalization_and_date_metadata_must_match_before_acceptance(tmp_path):
    service, run, entity, link, assertion, evidence = setup(tmp_path)
    with service.repository.connect() as db:
        version = service.repository.get(db, 'ontology_versions', 'ontology1')
        definitions = ontology._from_schema(version['linkml_yaml'])
        definitions[-1]['id'] = 'FirstOccupancyMonth'
        definitions.append(dict(definitions[-1], id='ConstructionDate', range='date'))
        version['linkml_yaml'], _ = ontology.build_schema(definitions)
        db.execute('UPDATE ontology_versions SET payload=? WHERE id=?', (json.dumps(version), version['id']))
    assertion.update(predicate_id='FirstOccupancyMonth', value='2023-12', raw_value='201106',
                     evidence_ids=['month'], field_evidence={'value': ['month']},
                     dates=[{'value': '2023-12', 'precision': 'month', 'role': 'first_occupancy'}])
    result = store.publish_unit(service, run, {'id': 'u1'}, [link], [assertion], evidence, [entity])
    invalid = next(i for i in result['items'] if i['kind'] == 'assertion')
    assert 'month_normalization_mismatch' in invalid['validation_errors']
    with pytest.raises(ValueError, match='month_normalization_mismatch'):
        store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1, decisions=[
            dict(candidate_id='link1', action='accept'), dict(candidate_id='count1', action='accept')]))
    with service.repository.connect() as db:
        schema = store._schema(service.repository, db, run)
        for value in ('2011-13', '2011-06-01'):
            candidate = dict(invalid, value=value, dates=[{'value': value, 'precision': 'month'}])
            assert 'month_value_invalid' in store._assertion_errors(service.repository, db, candidate, run, schema)
        for predicate, value, precision in [('FirstOccupancyMonth', '2011-06', 'day'), ('ConstructionDate', '2011-06-01', 'month')]:
            candidate = dict(invalid, predicate_id=predicate, value=value, dates=[{'value': value, 'precision': precision}])
            assert 'date_metadata_mismatch' in store._assertion_errors(service.repository, db, candidate, run, schema)
        candidate = dict(invalid, value='2011-06', dates=[{'value': '2011-07', 'precision': 'month'}])
        assert 'date_metadata_mismatch' in store._assertion_errors(service.repository, db, candidate, run, schema)
    valid = store.decide(service, result['changeset_id'], dict(actor='test', expected_changeset_revision=1, decisions=[
        dict(candidate_id='link1', action='accept'), dict(candidate_id='count1', action='modify', patch={
            'value': '2011-06', 'dates': [{'value': '2011-06', 'precision': 'month', 'role': 'first_occupancy'}]})]))
    assert next(i for i in valid['items'] if i['kind'] == 'assertion')['review_status'] == 'accepted'

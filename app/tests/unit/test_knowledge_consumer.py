"""A5 mapping and partial extraction boundaries; synthetic data, no LLM calls."""
from copy import deepcopy
import yaml

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge import ontology_canonical as canonical, ontology_consumer as consumer, ontology_schema
from app.knowledge import extraction, extraction_contract as contract, extraction_store, snapshots
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService, encode
from app.tests.unit.test_knowledge_service import finished


def seeded(tmp_path, renamed=False):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    registered = service.register('lh.csv', '단지코드,단지명,세대수\nC00001,행복단지,100\nC00002,희망단지,200\n'.encode(),
                                  SourceRegistration(title='합성 LH 등록부', publisher='test', namespace='synthetic'))
    vid = registered['source_version_id']
    run = finished(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
    blocks = service.blocks(registered['source_id'], vid)['items']
    mapping = {i: 'New_' + i if renamed else i for i in contract.PROFILE['definitions']}
    targets = {}
    for i, definition in contract.PROFILE['definitions'].items():
        t = dict(deepcopy(definition), id=mapping[i], symbol=mapping[i], name=i,
                 kind='class' if definition['kind'] == 'concept' else definition['kind'],
                 evidence_refs=[dict(evidence_id=blocks[0]['id'], quote=blocks[0]['text'])])
        for key in ('domain_id', 'range'):
            t[key] = mapping.get(t.get(key), t.get(key))
        targets[t['id']] = t
    payload, _, _ = canonical.build(None, targets)
    version = dict(payload, id='v2', status='reviewed', lineage_id='a5-test', created_at='2026-10-01')
    with service.repository.connect() as db:
        db.execute('INSERT INTO ontology_versions VALUES(?,?)', ('v2', encode(version)))
        db.execute('INSERT INTO ontology_heads VALUES(?,?)', ('a5-test', 'v2'))
    return service, vid, blocks, version, mapping


def test_new_ids_require_explicit_mapping_and_partial_extract_preserves_version(tmp_path):
    service, vid, blocks, version, mapping = seeded(tmp_path, renamed=True)
    try:
        request = RunRequest(kind='extract', ontology_version_id='v2', source_version_ids=[vid], registry_source_version_id=vid,
                             block_ids=[blocks[0]['id']], predicate_ids=[mapping['ATTRIBUTE_003']])
        with pytest.raises(ValueError, match='의미 대응'):
            service.start(request)
        decision = dict(actor='synthetic-review', reason='합성 정의와 LH 필드 대응 확인', target_ids=mapping,
                        expected_review_id=None, expected_ontology_head_id='v2')
        review = consumer.review(service, 'v2', decision)
        with pytest.raises(ontology_schema.VersionConflict):
            consumer.review(service, 'v2', decision)
        run = finished(service, service.start(request)['run_id'])
        assert run['status'] == 'succeeded', run['units']
        assert run['metrics']['llm_calls'] == 0
        assert run['consumer_contract']['review_id'] == review['contract']['review_id']
        rows = extraction_store.candidates(service, run['changeset_id'])
        facts = [c for c in rows['items'] if c['kind'] == 'assertion']
        assert len(facts) == 1 and facts[0]['value'] == 100 and not facts[0]['validation_errors']
        assert facts[0]['predicate_id'] == mapping['ATTRIBUTE_003']
        from app.knowledge import search, search_answer
        from app.knowledge.schemas import SearchRequest
        accepted = extraction_store.decide(service, run['changeset_id'], dict(expected_changeset_revision=rows['changeset_revision'],
            actor='test', decisions=[dict(candidate_id=c['id'], action='accept', reason='합성 원문 대조') for c in rows['items']]))
        snapshot_id = snapshots.create(service, dict(actor='test', reason='선택 사실', expected_active_id=None,
            selections=[dict(changeset_id=run['changeset_id'], expected_changeset_revision=accepted['changeset_revision'], candidate_ids=[c['id'] for c in rows['items']])]))['snapshot_id']
        with service.repository.connect() as db:
            snapshot = service.repository.get(db, 'snapshots', snapshot_id)
        packet, _ = search.packet(snapshot, [{facts[0]['id']}])
        assert packet['groups'][0]['facts'][0]['value'] == 100
        assert search.render_facts(snapshot, [facts[0]['id']])
        assert search_answer.build(snapshot, list(snapshot['assertions'].values()), SearchRequest(query='세대수', mode='local'), 'C')
        # A new mapping review cannot rewrite a frozen successful extraction.
        consumer.review(service, 'v2', dict(decision, expected_review_id=review['contract']['review_id'], target_ids={}))
        assert service.run(run['id'])['consumer_contract'] == run['consumer_contract']
        with service.repository.connect() as db:
            assert service.repository.get(db, 'ontology_versions', 'v2') == version
        assert snapshots.list_snapshots(service)['active_snapshot_id'] is None
    finally:
        service.shutdown()


def test_inherited_enum_required_and_retired_slots(tmp_path):
    service, _, blocks, version, _ = seeded(tmp_path)
    try:
        items = canonical.targets(version)
        items['Child'] = dict(items['CONCEPT_001'], id='Child', symbol='Child', name='하위 단지')
        items['edge'] = dict(id='edge', symbol='edge', kind='hierarchy', child_id='Child', parent_id='CONCEPT_001', relation='is_a')
        items['ATTRIBUTE_003'].update(required=True, enum_values=[])
        items['ATTRIBUTE_004']['enum_values'] = ['국민임대', '영구임대']
        items['ATTRIBUTE_005']['deprecated'] = True
        payload, _, effective = canonical.build(version, items)
        rows = {d['id']: d for d in consumer.definitions(payload)}
        assert 'ATTRIBUTE_005' not in rows and 'ATTRIBUTE_005' not in effective['Child']
        assert consumer.permits(rows['ATTRIBUTE_003'], 'Child')
        assert 'Child' in rows['ATTRIBUTE_003']['required_domain_ids']
        assert rows['ATTRIBUTE_004']['enum_values'] == ['국민임대', '영구임대']
        run = dict(ontology_candidates=list(rows.values()), frozen_blocks=blocks, predicate_ids=['ATTRIBUTE_004'])
        assert [d['id'] for d in contract.fact_definitions(run)] == ['ATTRIBUTE_004']
    finally:
        service.shutdown()


def test_semantics_are_not_automatically_mapped_by_name(tmp_path):
    service, _, _, version, _ = seeded(tmp_path)
    try:
        assert consumer.inspect(service, 'v2')['contract']['target_ids']['CONCEPT_001'] == 'CONCEPT_001'
        items = canonical.targets(version)
        items['CONCEPT_001']['definition'] = '다른 업무 대상'
        payload, _, _ = canonical.build(version, items)
        with service.repository.connect() as db:
            result = consumer.contract_for(db, dict(payload, id='semantic-change'))
        assert 'LH:complex' not in result['role_targets']
        assert 'ATTRIBUTE_003' not in result['target_ids']
    finally:
        service.shutdown()


def test_consumer_api_envelope_and_revision_conflict(tmp_path, monkeypatch):
    from app.api.routers.knowledge import router, get_knowledge_service
    from app.core.config import settings
    service, _, _, _, mapping = seeded(tmp_path)
    monkeypatch.setattr(settings, 'KNOWLEDGE_ENABLED', True)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_knowledge_service] = lambda: service
    try:
        with TestClient(app) as client:
            result = client.get('/knowledge/ontologies/v2/consumer')
            assert result.status_code == 200 and result.json()['success']
            body = dict(actor='test', reason='합성 대응', target_ids=mapping, expected_review_id=None, expected_ontology_head_id='wrong')
            assert client.post('/knowledge/ontologies/v2/consumer', json=body).status_code == 409
            body['expected_ontology_head_id'] = 'v2'
            assert client.post('/knowledge/ontologies/v2/consumer', json=body).status_code == 200
    finally:
        service.shutdown()


def test_v1_mapping_cannot_be_replaced_by_new_consumer_decision(tmp_path):
    service, _, _, version, mapping = seeded(tmp_path)
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO ontology_versions VALUES(?,?)', ('legacy', encode(dict(version, id='legacy', payload_version=1))))
        with pytest.raises(ValueError, match='v1은 기존 LH 매핑'):
            consumer.review(service, 'legacy', dict(actor='test', reason='기존 계약 보호', target_ids=mapping,
                expected_review_id=None, expected_ontology_head_id='v2'))
        with service.repository.connect() as db:
            assert consumer._latest(db, 'legacy') is None
    finally:
        service.shutdown()


def test_effective_slot_override_and_counter_evidence_dependency(tmp_path):
    service, _, blocks, version, _ = seeded(tmp_path)
    try:
        schema = yaml.safe_load(version['linkml_yaml'])
        schema['enums']['RestrictedType'] = {'permissible_values': {'국민임대': {}}}
        schema['classes']['CONCEPT_001']['slot_usage'] = {'ATTRIBUTE_003': {'range': 'string'}, 'ATTRIBUTE_004': {'range': 'RestrictedType'}}
        changed = dict(version, linkml_yaml=yaml.safe_dump(schema, allow_unicode=True))
        rows = {d['id']: d for d in consumer.definitions(changed)}
        assert rows['ATTRIBUTE_003']['range'] == 'string'
        assert rows['ATTRIBUTE_004']['enum_values'] == ['국민임대']
        items = canonical.targets(version)
        items['CONCEPT_001']['counter_evidence_refs'] = [dict(evidence_id=blocks[1]['id'], quote=blocks[1]['text'])]
        changed, _, _ = canonical.build(version, items)
        assert blocks[1]['id'] in consumer.evidence_ids(changed)
    finally:
        service.shutdown()


def test_notice_identifier_can_be_extracted_without_relation(tmp_path):
    service, vid, _, version, _ = seeded(tmp_path)
    try:
        with service.repository.connect() as db:
            mapping = consumer.contract_for(db, version)
        run = dict(ontology_payload_version=2, consumer_contract=mapping, ontology_candidates=consumer.definitions(version, mapping),
                   predicate_ids=['NoticeIdentifier'], sources={vid: {'title': '합성 공고'}},
                   frozen_blocks=[dict(id='html', source_version_id=vid, locator={'format': 'html', 'script_array': 'sbdList'}, text='panId: P001\nsbdLgoNo: C00001\nsbdLgoNm: 합성단지')])
        records = extraction.mapped_records(run, dict(block_ids=['html']))
        assert len(records) == 1 and records[0]['values'] == {'NoticeIdentifier': 'P001'}
    finally:
        service.shutdown()


@pytest.mark.parametrize('slot,notice_mapping', [('ATTRIBUTE_003', False), ('ATTRIBUTE_003', True),
                                               ('NoticeIdentifier', True), ('NoticeIncludesComplex', True)])
def test_sbd_partial_extraction_only_registers_selected_mapped_notice(tmp_path, slot, notice_mapping):
    service, vid, _, _, mapping = seeded(tmp_path, renamed=True)
    try:
        target_ids = {i: mapping[i] for i in ('CONCEPT_001', 'ATTRIBUTE_003')}
        if notice_mapping:
            target_ids.update({i: mapping[i] for i in ('Notice', 'NoticeIdentifier', 'NoticeIncludesComplex')})
        decision = dict(actor='test', reason='선택 필드의 의미 대응', target_ids=target_ids,
                        expected_review_id=None, expected_ontology_head_id='v2')
        if slot.startswith('Notice'):
            with pytest.raises(ValueError, match='주체'):
                consumer.review(service, 'v2', dict(decision, target_ids={i: v for i, v in target_ids.items() if i != 'Notice'}))
        consumer.review(service, 'v2', decision)
        html = "<div id='sub_container'><section>공고</section><section>단지</section></div><script>sbdList.push({panId:'P001',sbdLgoNo:'C00001',sbdLgoNm:'행복단지',hshCnt:'100'});</script>"
        registered = service.register('notice.html', html.encode(), SourceRegistration(title='합성 공고', publisher='test',
            namespace='synthetic', selected_scope={'complex_codes': ['C00001']}))
        parsed = finished(service, service.start(RunRequest(source_version_ids=[registered['source_version_id']]))['run_id'])
        assert parsed['status'] == 'succeeded'
        block = next(b for b in service.blocks(registered['source_id'], registered['source_version_id'])['items']
                     if b['locator'].get('script_array') == 'sbdList')
        run = finished(service, service.start(RunRequest(kind='extract', ontology_version_id='v2', registry_source_version_id=vid,
            source_version_ids=[registered['source_version_id']], block_ids=[block['id']], predicate_ids=[mapping[slot]]))['run_id'])
        assert run['status'] == 'succeeded', run['units']
        assert run['metrics']['llm_calls'] == 0
        assert any(e['namespace'] == 'LH:notice' for e in run['entities']) == slot.startswith('Notice')
        rows = extraction_store.candidates(service, run['changeset_id'])['items']
        assert all(not row['validation_errors'] for row in rows)
        assert [row['predicate_id'] for row in rows if row['kind'] == 'assertion'] == [mapping[slot]]
    finally:
        service.shutdown()


@pytest.mark.parametrize('relation,inherited,notice_mapping', [(False, False, True), (False, True, True),
                                                            (True, False, True), (True, True, True), (False, False, False)])
def test_custom_notice_slot_resolves_effective_subject_or_object(tmp_path, monkeypatch, relation, inherited, notice_mapping):
    service, vid, _, version, mapping = seeded(tmp_path, renamed=True)
    try:
        targets = canonical.targets(version)
        notice_domain = mapping['Notice']
        if inherited:
            notice_domain = 'ParentNotice'
            targets[notice_domain] = dict(targets[mapping['Notice']], id=notice_domain, symbol=notice_domain)
            targets['notice-edge'] = dict(id='notice-edge', symbol='notice_edge', kind='hierarchy',
                child_id=mapping['Notice'], parent_id=notice_domain, relation='is_a')
        slot = 'CustomNoticeSlot'
        targets[slot] = dict(targets[mapping['ATTRIBUTE_002']], id=slot, symbol=slot, name='공고 신규 슬롯',
            kind='relation' if relation else 'attribute', domain_id=mapping['CONCEPT_001'] if relation else notice_domain,
            range=notice_domain if relation else 'string')
        payload, _, _ = canonical.build(version, targets)
        version.update(payload)
        with service.repository.connect() as db:
            db.execute('UPDATE ontology_versions SET payload=? WHERE id=?', (encode(version), 'v2'))
        consumer.review(service, 'v2', dict(actor='test', reason='합성 공고 역할 대응',
            target_ids=mapping if notice_mapping else {i: mapping[i] for i in ('CONCEPT_001', 'ATTRIBUTE_003')},
            expected_review_id=None, expected_ontology_head_id='v2'))
        html = "<div id='sub_container'><section>공고 P001의 신청 방식은 방문접수이며 단지 C00001에 해당합니다.</section><section>단지</section></div><script>sbdList.push({panId:'P001',sbdLgoNo:'C00001',sbdLgoNm:'행복단지',hshCnt:'100'});</script>"
        registered = service.register('notice.html', html.encode(), SourceRegistration(title='합성 공고', publisher='test',
            namespace='synthetic', selected_scope={'complex_codes': ['C00001']}))
        finished(service, service.start(RunRequest(source_version_ids=[registered['source_version_id']]))['run_id'])
        blocks = service.blocks(registered['source_id'], registered['source_version_id'])['items']
        selected = [b['id'] for b in blocks if b['locator'].get('script_array') == 'sbdList' or '방문접수' in b['text']]
        monkeypatch.setattr(service.executor, 'submit', lambda *args: None)
        run = service.run(service.start(RunRequest(kind='extract', ontology_version_id='v2', registry_source_version_id=vid,
            source_version_ids=[registered['source_version_id']], block_ids=selected, predicate_ids=[slot]))['run_id'])
        unit = next(u for u in run['units'] if u['stage'] == 'llm')
        assert [d['id'] for d in contract.fact_definitions(run, unit)] == [slot]
        group = contract.text_units(run, unit)[0]
        ref = 'b' + str(next(i for i, b in enumerate(run['frozen_blocks']) if b['id'] == group['blocks'][0]['id']))
        notice = dict(mention='공고 P001', concept_id=mapping['Notice'], official_id='P001', evidence=[dict(block_id=ref, quote='공고 P001')])
        subject = dict(mention='행복단지', concept_id=mapping['CONCEPT_001'], official_id='C00001',
                       evidence=[dict(block_id=ref, quote='단지 C00001')]) if relation else notice
        fact = dict(predicate_id=slot, evidence=[dict(block_id=ref, quote='공고 P001' if relation else '방문접수')],
                    unit=None, scope='미확인', scope_evidence=[], conditions=[], conditions_evidence=[], exceptions=[], exceptions_evidence=[])
        fact.update({'object': notice} if relation else {'raw_value': '방문접수'})
        records, _, invalid = contract.adapt(run, unit, dict(units=[dict(unit_id=group['id'], subject=subject, facts=[fact], reason='')]))
        assert not invalid and len(records) == 1
        links, assertions, evidence = extraction.materialize(run, unit, records)
        published = extraction_store.publish_unit(service, run, unit, links, assertions, evidence, run['entities'])
        rows = extraction_store.candidates(service, published['changeset_id'])['items']
        assert any(e['namespace'] == 'LH:notice' for e in run['entities']) == notice_mapping
        assert run['metrics']['llm_calls'] == 0
        if notice_mapping:
            assert all(link['method'] == 'official_id' and link['target_entity_id'] for link in links)
            assert all(not row['validation_errors'] for row in rows)
        else:
            assert any('entity_unresolved' in row['validation_errors'] for row in rows)
            with pytest.raises(ValueError, match='entity_unresolved'):
                extraction_store.decide(service, published['changeset_id'], dict(actor='test', expected_changeset_revision=1,
                    decisions=[dict(candidate_id=row['id'], action='accept', reason='미대응 수락 불가') for row in rows]))
    finally:
        service.shutdown()


def test_decimal_normalization_and_store_agree():
    definition = dict(id='quantity', range='decimal')
    value, _ = contract.normalize('12.50', definition)
    assert extraction_store._scalar_valid(value, 'decimal')
    assert not extraction_store._scalar_valid(True, 'decimal')


def test_legacy_full_block_evidence_uses_existing_read_contract(tmp_path):
    from app.knowledge import ontology_changes
    service, _, blocks, _, _ = seeded(tmp_path)
    try:
        block = blocks[0]
        with service.repository.connect() as db:
            db.execute('DELETE FROM evidence WHERE id=?', (block['id'],))
            ref = ontology_changes._ref(dict(evidence_id=block['id']), {block['id']: block})
            assert ontology_changes._evidence_errors(service.repository, db, [ref], {block['id']: block}, {}) == []
            assert ontology_changes._evidence_errors(service.repository, db, [dict(ref, span=[0,1])], {block['id']: block}, {})
    finally:
        service.shutdown()

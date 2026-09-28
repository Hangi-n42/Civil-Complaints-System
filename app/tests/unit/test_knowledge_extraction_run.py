"""Focused K4 checks with real LinkML/alignment and no model inference."""
import json

from jsonschema import Draft202012Validator

from app.knowledge import extraction, ontology_schema
from app.knowledge.schemas import Candidate, RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService, encode
from app.tests.unit.test_knowledge_service import finished


def definitions():
    common = dict(evidence=[{'evidence_id': 'fixture', 'quote': '단지'}], cq_ids=['CQ1'],
                  inclusion='등록 원문 범위', exclusion='원문 밖 추측')
    return [Candidate(**common, **value).model_dump() for value in [
        dict(id='CONCEPT_001', kind='concept', name='단지', definition='주택 단지'),
        dict(id='ATTRIBUTE_001', kind='attribute', name='단지코드', definition='공식 코드', domain_id='CONCEPT_001'),
        dict(id='ATTRIBUTE_002', kind='attribute', name='단지명', definition='원문 명칭', domain_id='CONCEPT_001'),
        dict(id='FirstOccupancyMonth', kind='attribute', name='최초입주월', definition='최초입주 연월', domain_id='CONCEPT_001'),
    ]]


def record(block_id):
    return dict(concept_id='CONCEPT_001', mention='행복단지', official_id='C00001',
                subject_evidence=[dict(block_id=block_id, quote='C00001')],
                values={'FirstOccupancyMonth': '2011-06'}, raw_values={'FirstOccupancyMonth': '201106'},
                field_evidence={'FirstOccupancyMonth': [dict(block_id=block_id, quote='201106')]},
                scope='미확인', unit=None, conditions=[], exceptions=[])


def model_result(prompt):
    context, _ = json.JSONDecoder().raw_decode(prompt.split('\nINPUT:\n', 1)[1])
    return dict(text=json.dumps({'records': [record(context['blocks'][0]['block_id'])]}, ensure_ascii=False),
                done=True, done_reason='stop', eval_count=100)


def seeded_service(tmp_path):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    registered, parse_ids = [], {}
    for name, content in [
        ('registry.csv', '단지코드,단지명\nC00001,행복단지\n'),
        ('first.html', '<html><body><p>단지코드 C00001 행복단지 최초입주 201106</p></body></html>'),
        ('second.html', '<html><body><p>행복단지 C00001의 최초입주월은 201106</p></body></html>'),
    ]:
        item = service.register(name, content.encode(), SourceRegistration(
            title=name, publisher='LH', namespace='test', external_id=name))
        registered.append(item)
        rid = service.start(RunRequest(source_version_ids=[item['source_version_id']]))['run_id']
        assert finished(service, rid)['status'] == 'succeeded'
        parse_ids[item['source_version_id']] = rid
    text, _ = ontology_schema.build_schema(definitions())
    with service.repository.connect() as db:
        db.execute('INSERT INTO ontology_versions VALUES(?,?)', (
            'reviewed-test', encode(dict(id='reviewed-test', status='reviewed', linkml_yaml=text))))
    request = RunRequest(kind='extract', ontology_version_id='reviewed-test',
                         source_version_ids=[r['source_version_id'] for r in registered],
                         registry_source_version_id=registered[0]['source_version_id'],
                         cqs=[dict(id='CQ1', question='최초입주월은?')])
    return service, request, registered, parse_ids


def test_korean_alignment_rejects_ambiguous_and_nonmatching_quotes():
    block = dict(id='korean', text='금산휴먼시아의 최초입주는 201106입니다.')
    aligned = extraction.align(block, '201106')
    assert aligned['alignment_status'] == 'matched'
    assert block['text'][aligned['start_char']:aligned['end_char']] == aligned['quote']
    repeated = extraction.align(dict(id='repeated', text='201106 / 201106'), '201106')
    assert repeated['alignment_status'] == 'ambiguous'
    assert repeated['start_char'] is None and repeated['end_char'] is None
    missing = extraction.align(block, '201107')
    assert missing['alignment_status'] == 'unmatched'


def test_generated_schema_preserves_stable_concept_ids_and_rejects_unknown_slots():
    items = definitions()
    items += [dict(items[1], id='ATTRIBUTE_003', range='integer'),
              dict(items[1], id='ATTRIBUTE_005', range='date'),
              dict(items[1], id='ATTRIBUTE_007'), dict(items[0], id='Notice')]
    _, generated = ontology_schema.build_schema(items)
    ref = generated['$defs']['KnowledgeDocument']['properties']['items_CONCEPT_001']['items']['$ref']
    assert ref.rsplit('/', 1)[-1] != 'CONCEPT_001'
    run = dict(json_schema=generated, ontology_candidates=items, frozen_blocks=[
        dict(id=f'header-{i}', text=text, locator=dict(format='pdf', row=0, table=2))
        for i, text in enumerate(['단지명', '건설호수', '최초입주'])])
    schema = extraction.response_schema(run)  # No unit keeps the existing complete schema.
    validator = Draft202012Validator(schema)
    value = {'records': [record('block-1')]}
    assert not list(validator.iter_errors(value))
    value['records'][0]['values']['UnapprovedSlot'] = 'unapproved'
    assert list(validator.iter_errors(value))
    unit = dict(block_ids=[b['id'] for b in run['frozen_blocks']])
    limited = extraction.response_schema(run, unit)
    variants = limited['properties']['records']['items']['anyOf']
    assert len(variants) == 1 and variants[0]['properties']['concept_id']['const'] == 'CONCEPT_001'
    allowed = variants[0]['properties']['values']['properties']
    assert set(allowed) == {'ATTRIBUTE_002', 'ATTRIBUTE_003', 'FirstOccupancyMonth'}
    full = schema['properties']['records']['items']['anyOf'][0]['properties']['values']['properties']
    assert allowed == {k: full[k] for k in allowed}  # Reviewed slot types are reused verbatim.
    limited_validator = Draft202012Validator(limited)
    assert not list(limited_validator.iter_errors({'records': [record('data-cell')]}))
    for wrong_slot, wrong_value in [('ATTRIBUTE_005', '2011-06-01'), ('ATTRIBUTE_007', '2011-06')]:
        wrong = dict(record('data-cell'), values={wrong_slot: wrong_value})
        assert not list(validator.iter_errors({'records': [wrong]}))
        assert list(limited_validator.iter_errors({'records': [wrong]}))
    assert extraction.response_schema(run, dict(block_ids=unit['block_ids'][:2])) == schema


def test_n_text_calls_keep_mapping_and_parse_pointers(tmp_path, monkeypatch):
    service, request, registered, parse_ids = seeded_service(tmp_path)
    calls = []
    async def model(prompt, schema, run):
        calls.append(prompt)
        return model_result(prompt)
    monkeypatch.setattr(extraction, 'model_call', model)
    try:
        started = service.start(request)
        assert started['planned_llm_calls'] == 2
        run = finished(service, started['run_id'])
        assert run['status'] == 'succeeded', run
        assert len(calls) == run['metrics']['llm_calls'] == 2
        assert run['units'][0]['stage'] == 'mapped'
        assert run['units'][0]['call']['attempted'] is False
        with service.repository.connect() as db:
            assertions = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM assertions')]
        months = [a for a in assertions if a['predicate_id'] == 'FirstOccupancyMonth']
        assert len(months) == 2
        assert all(a['value'] == '2011-06' and a['raw_value'] == '201106' for a in months)
        assert all(a['dates'][0]['precision'] == 'month' for a in months)
        assert all(not a['validation_errors'] for a in months), months
        for item in registered:
            version = service.version(item['source_id'], item['source_version_id'])['version']
            assert version['latest_parse_run_id'] == parse_ids[item['source_version_id']]
    finally:
        service.shutdown()


def test_retry_only_failed_text_unit_uses_frozen_input_without_duplicates(tmp_path, monkeypatch):
    service, request, registered, _ = seeded_service(tmp_path)
    calls, truncate = [], True
    async def model(prompt, schema, run):
        calls.append(prompt)
        response = model_result(prompt)
        if truncate and '최초입주 201106' in prompt:
            response['done_reason'] = 'length'
        return response
    monkeypatch.setattr(extraction, 'model_call', model)
    try:
        original = finished(service, service.start(request)['run_id'])
        assert original['status'] == 'partial', original
        assert original['metrics']['llm_calls'] == 2
        assert [u['status'] for u in original['units']] == ['succeeded', 'failed', 'succeeded']
        with service.repository.connect() as db:
            previous = {r['id'] for r in db.execute('SELECT id FROM assertions')}
        changed = registered[1]
        reparsed = finished(service, service.start(RunRequest(source_version_ids=[changed['source_version_id']]))['run_id'])
        old_blocks = {b['id'] for b in original['frozen_blocks'] if b['source_version_id'] == changed['source_version_id']}
        assert old_blocks.isdisjoint(b['id'] for b in service.blocks(changed['source_id'], changed['source_version_id'])['items'])
        truncate = False
        retry_start = service.start(RunRequest(kind='extract', retry_of_run_id=original['id']))
        assert retry_start['planned_llm_calls'] == 1
        retry = finished(service, retry_start['run_id'])
        assert retry['status'] == 'succeeded', retry
        assert retry['metrics']['llm_calls'] == 1 and len(calls) == 3
        assert retry['frozen_blocks'] == original['frozen_blocks']
        assert retry['changeset_id'] == original['changeset_id']
        assert retry['reused_units'] == ['mapped', 'extract-2']
        with service.repository.connect() as db:
            current = {r['id'] for r in db.execute('SELECT id FROM assertions')}
        assert previous < current and len(current - previous) == 1
        assert service.version(changed['source_id'], changed['source_version_id'])['version']['latest_parse_run_id'] == reparsed['id']
    finally:
        service.shutdown()


def test_malformed_records_preserve_valid_candidates_and_model_time(tmp_path, monkeypatch):
    service, request, _, _ = seeded_service(tmp_path)
    clock = {'now': 0.0}
    original_materialize = extraction.materialize
    async def model(prompt, schema, run):
        clock['now'] += 2.0
        response = model_result(prompt)
        valid = json.loads(response['text'])['records'][0]
        response['text'] = json.dumps({'records': [valid, dict(valid, values=None),
                                                  dict(valid, values=[]), dict(valid, field_evidence=None)]})
        return response
    def materialize(*args):
        result = original_materialize(*args)
        clock['now'] += 3.0
        return result
    monkeypatch.setattr(extraction, 'model_call', model)
    monkeypatch.setattr(extraction, 'materialize', materialize)
    monkeypatch.setattr(extraction, 'monotonic', lambda: clock['now'])
    try:
        run = finished(service, service.start(request)['run_id'])
        assert run['status'] == 'succeeded', run
        assert run['invalid_record_count'] == 6
        assert run['metrics']['model_total_s'] == 4.0
        assert run['metrics']['elapsed_s'] == 13.0
        for unit in run['units'][1:]:
            assert unit['call']['elapsed_s'] == 2.0 and unit['elapsed_s'] == 5.0
            assert len(unit['records']) == 1 and unit['counts']['invalid_records'] == 3
            assert [item['index'] for item in unit['invalid_records']] == [1, 2, 3]
            assert all(item['validation_errors'] for item in unit['invalid_records'])
            assert unit['invalid_records'][0]['raw_record']['values'] is None
            assert unit['invalid_records'][1]['raw_record']['values'] == []
            assert unit['invalid_records'][2]['raw_record']['field_evidence'] is None
        with service.repository.connect() as db:
            values = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM assertions')]
        assert len([v for v in values if v['predicate_id'] == 'FirstOccupancyMonth']) == 2
    finally:
        service.shutdown()

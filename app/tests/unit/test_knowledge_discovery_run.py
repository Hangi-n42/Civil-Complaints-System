"""A1 boundaries: frozen provenance, scope, reuse, cancellation and API compatibility."""
from hashlib import sha256
import json
from threading import Event

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.routers import knowledge
from app.knowledge import discovery_inputs as inputs, discovery_run as discovery, parsers, snapshots
from app.knowledge.schemas import RunRequest
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_service import finished


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    specs = [('current', 'txt', '현재 국민임대\n현재의 조건\n', 'utf-8-sig'),
             ('table', 'md', '# 공고\r\n| 코드 | 명칭 |\r\n| 01 | 국민임대 |\r\n', 'utf-8-sig'),
             ('web', 'html', '<body><p id="a">국민임대 기준</p><p id="b">예외 조건</p></body>', 'utf-8-sig'),
             ('contrast', 'csv', '유형,설명\r\n분양전환,"첫줄\r\n다음줄"\r\n', 'cp949'),
             ('old', 'txt', '과거 국민임대', 'utf-8-sig'),
             ('future', 'txt', '후속 통합공공임대', 'utf-8-sig')]
    sources = []
    for name, suffix, text, encoding in specs:
        path = tmp_path / f'{name}.{suffix}'
        path.write_bytes(text.encode(encoding))
        sources.append(dict(source_id=name, title=name, publisher='시험 출처',
            source_url='https://example.org/' + name, rights={}, csv_encoding=encoding,
            input_files=[dict(path=path.name, sha256=sha256(path.read_bytes()).hexdigest(), role='test')]))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(bundle_id='fixture', selected_sources=sources,
        held_sources=[dict(source_id='held')], runs=[
            dict(id='current_discovery', source_ids=['current', 'table', 'web']),
            dict(id='contrast_extension', base_run='current_discovery', new_source_ids=['contrast']),
            dict(id='historical_change', initial_source_ids=['old'], updates=[['future']])])), encoding='utf-8')
    monkeypatch.setattr(inputs, 'ROOT', tmp_path)
    monkeypatch.setattr(inputs, 'MANIFEST', manifest)
    return tmp_path


def request(scope='current_discovery', step=0, file_ids=None):
    data = inputs.catalog(scope, step)
    fields = dict(kind='discovery', bundle_id=data['bundle_id'], manifest_hash=data['manifest_sha256'],
                  scope=scope, step=step)
    if file_ids is not None:
        fields['file_ids'] = file_ids
    return RunRequest(**fields)


@pytest.fixture
def service(corpus):
    instance = KnowledgeService(corpus / 'ledger/knowledge.db')
    yield instance
    instance.shutdown()


def prepare(service, **kwargs):
    run = finished(service, service.start(request(**kwargs))['run_id'])
    assert run['status'] == 'succeeded', run
    return run


def test_scope_history_contrast_and_evidence(service):
    current = prepare(service)
    old = prepare(service, scope='historical_change')
    later = prepare(service, scope='historical_change', step=1)
    contrast = prepare(service, scope='contrast_extension', file_ids=['contrast:0'])
    assert discovery.search(service, old['id'], '통합공공임대')['items'] == []
    assert discovery.search(service, current['id'], '분양전환')['items'] == []
    assert discovery.search(service, later['id'], '통합공공임대')['items'][0]['file_id'] == 'future:0'
    with pytest.raises(KeyError):
        discovery.read(service, old['id'], 'current:0')
    with pytest.raises(ValueError, match='scope/step'):
        discovery.search(service, old['id'], '임대', step=1)
    with pytest.raises(ValueError, match='밖 파일'):
        service.start(request(scope='historical_change', file_ids=['future:0']))
    with pytest.raises(ValueError, match='밖 파일'):
        service.start(request(file_ids=['held:0']))
    block = discovery.read(service, contrast['id'], 'contrast:0')['items'][0]
    assert '첫줄\r\n다음줄' in block['text']
    assert block['locator']['physical_row'] == 3
    assert block['locator']['column_names'] == ['유형', '설명']
    evidence = service.evidence(block['evidence_id'])
    assert evidence['block'] == {k: v for k, v in block.items() if k not in {'block_index', 'source_id'}}
    assert evidence['evidence']['quote'] == block['text']
    assert evidence['version']['id'] == block['source_version_id']
    md = discovery.read(service, current['id'], 'table:0')['items']
    assert md[2]['locator']['table_headers'] == ['| 코드 | 명칭 |']
    assert md[2]['locator']['section'] == '# 공고'
    original = service.raw_path(service.evidence(md[0]['evidence_id'])['version']).read_bytes().decode('utf-8-sig')
    for b in md:
        assert original[b['locator']['start_char']:b['locator']['end_char']] == b['text']


def test_recipe_reuse_and_latest_pointer_do_not_replace_frozen_blocks(service, monkeypatch):
    first = prepare(service, file_ids=['web:0'])
    original = discovery.read(service, first['id'], 'web:0')['items']
    file = first['frozen_input']['files'][0]
    newer = finished(service, service.start(RunRequest(source_version_ids=[file['source_version_id']],
                     parser_options={'selector': '#b'}))['run_id'])
    assert newer['status'] == 'succeeded'
    assert len(service.blocks(file['source_id'], file['source_version_id'])['items']) == 1
    # Same manifest recipe reuses its old completed result, not the latest parse.
    with monkeypatch.context() as patch:
        patch.setattr(parsers, 'parse_unit', lambda *a: pytest.fail('unexpected reparse'))
        second = prepare(service, file_ids=['web:0'])
        assert second['units'][0]['parse_run_id'] == first['units'][0]['parse_run_id']
        assert discovery.read(service, second['id'], 'web:0')['items'] == original
        assert discovery.search(service, first['id'], '국민임대')['items'][0]['evidence_id'] == original[0]['evidence_id']
    assert service.version(file['source_id'], file['source_version_id'])['version']['latest_parse_run_id'] == newer['id']
    info = parsers.parser_info
    monkeypatch.setattr(parsers, 'parser_info', lambda fmt: dict(info(fmt), adapter_version='test-next'))
    changed = prepare(service, file_ids=['web:0'])
    assert changed['units'][0]['parse_run_id'] != first['units'][0]['parse_run_id']
    assert changed['input_version_ids'] == first['input_version_ids']
    assert discovery.read(service, first['id'], 'web:0')['items'] == original


def test_file_array_order_is_not_a_persistent_evidence_identity(service, monkeypatch):
    manifest = json.loads(inputs.MANIFEST.read_text())
    manifest['selected_sources'][0]['input_files'].extend(manifest['selected_sources'][1]['input_files'])
    inputs.MANIFEST.write_text(json.dumps(manifest), encoding='utf-8')
    first = prepare(service, file_ids=['current:0', 'current:1'])
    saved = discovery.read(service, first['id'], 'current:0')['items']
    manifest['selected_sources'][0]['input_files'].reverse()
    inputs.MANIFEST.write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(parsers, 'parse_unit', lambda *a: pytest.fail('unexpected reparse'))
    reordered = prepare(service, file_ids=['current:0', 'current:1'])
    assert reordered['units'][1]['block_ids'] == first['units'][0]['block_ids']
    assert discovery.read(service, first['id'], 'current:0')['items'] == saved
    assert discovery.read(service, reordered['id'], 'current:1')['items'] == saved


def test_identical_bytes_reuse_parsing_without_merging_sources(service, monkeypatch):
    first = prepare(service, file_ids=['current:0'])
    original = discovery.read(service, first['id'], 'current:0')['items']
    manifest = json.loads(inputs.MANIFEST.read_text())
    duplicate = dict(manifest['selected_sources'][0], source_id='copy', title='다른 출처의 사본')
    manifest['selected_sources'].append(duplicate)
    manifest['runs'][0]['source_ids'].append('copy')
    inputs.MANIFEST.write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(parsers, 'parse_unit', lambda *a: pytest.fail('unexpected reparse'))
    copied = prepare(service, file_ids=['copy:0'])
    blocks = discovery.read(service, copied['id'], 'copy:0')['items']
    assert blocks[0]['source_id'] != original[0]['source_id']
    assert blocks[0]['source_version_id'] != original[0]['source_version_id']
    assert blocks[0]['evidence_id'] != original[0]['evidence_id']
    assert [(b['text'], b['locator']) for b in blocks] == [(b['text'], b['locator']) for b in original]
    assert service.run(copied['units'][0]['parse_run_id'])['reused_parse_run_id'] == first['units'][0]['parse_run_id']


def test_cancel_resume_pins_all_bytes_and_restart_does_not_touch_parse_state(service, corpus, monkeypatch):
    entered, release = Event(), Event()
    original_parse, calls = parsers.parse_unit, []
    def controlled(path, fmt, unit):
        calls.append(path.name)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return original_parse(path, fmt, unit)
    monkeypatch.setattr(parsers, 'parse_unit', controlled)
    rid = service.start(request(file_ids=['current:0', 'table:0']))['run_id']
    try:
        assert entered.wait(5)
        service.cancel(rid)
        (corpus / 'table.md').write_text('새 파일로 교체', encoding='utf-8')
        inputs.MANIFEST.unlink()
    finally:
        release.set()
    cancelled = finished(service, rid)
    assert cancelled['status'] == 'cancelled'
    assert [u['status'] for u in cancelled['units']] == ['succeeded', 'cancelled']
    saved = discovery.read(service, rid, 'current:0')['items']
    resumed = finished(service, service.start(RunRequest(kind='discovery', retry_of_run_id=rid))['run_id'])
    assert resumed['status'] == 'succeeded'
    assert len(calls) == 2
    assert resumed['frozen_input'] == cancelled['frozen_input']
    assert discovery.read(service, resumed['id'], 'current:0')['items'] == saved
    assert '공고' in discovery.read(service, resumed['id'], 'table:0')['items'][0]['text']
    assert service.start(RunRequest(kind='discovery', retry_of_run_id=resumed['id']))['run_id'] == resumed['id']
    with service.repository.connect() as db:
        versions = [dict(row) for row in db.execute('SELECT * FROM versions')]
    service.shutdown()
    restarted = KnowledgeService(service.repository.path)
    try:
        assert discovery.read(restarted, rid, 'current:0')['items'] == saved
        with restarted.repository.connect() as db:
            assert [dict(row) for row in db.execute('SELECT * FROM versions')] == versions
    finally:
        restarted.shutdown()


def test_interrupted_discovery_recovers_completed_parse_without_reparsing(service, monkeypatch):
    monkeypatch.setattr(service.executor, 'submit', lambda *a: None)
    rid = service.start(request(file_ids=['current:0']))['run_id']
    run = service.run(rid)
    parse_id = service.parse_input(run['frozen_input']['files'][0])
    version_before = service.version(run['frozen_input']['files'][0]['source_id'], run['input_version_ids'][0])
    # Process exits after a child parse commit, before saving discovery's mapping.
    service.shutdown()
    restarted = KnowledgeService(service.repository.path)
    try:
        assert restarted.run(rid)['status'] == 'failed'
        monkeypatch.setattr(parsers, 'parse_unit', lambda *a: pytest.fail('unexpected reparse'))
        resumed = finished(restarted, restarted.start(RunRequest(kind='discovery', retry_of_run_id=rid))['run_id'])
        assert resumed['status'] == 'succeeded'
        assert resumed['units'][0]['parse_run_id'] == parse_id
        assert restarted.version(version_before['source']['id'], version_before['version']['id']) == version_before
    finally:
        restarted.shutdown()


def test_partial_file_retry_reuses_successful_parse_units(service, monkeypatch):
    original_parse, calls = parsers.parse_unit, []
    monkeypatch.setattr(parsers, 'plan_units', lambda *a: [
        dict(id=key, locator=dict(format='html', selector='#' + key, element_index=0)) for key in ('a', 'b')])
    def fail_once(path, fmt, unit):
        calls.append(unit['id'])
        if calls == ['a', 'b']:
            raise ValueError('시험용 일시 실패')
        return original_parse(path, fmt, unit)
    monkeypatch.setattr(parsers, 'parse_unit', fail_once)
    failed = finished(service, service.start(request(file_ids=['web:0']))['run_id'])
    assert failed['status'] == 'failed'
    file = failed['frozen_input']['files'][0]
    preserved = service.blocks(file['source_id'], file['source_version_id'])['items'][0]
    assert service.version(file['source_id'], file['source_version_id'])['version']['latest_parse_run_id'] is None
    resumed = finished(service, service.start(RunRequest(kind='discovery', retry_of_run_id=failed['id']))['run_id'])
    assert resumed['status'] == 'succeeded'
    assert calls == ['a', 'b', 'b']
    assert discovery.read(service, resumed['id'], 'web:0')['items'][0]['evidence_id'] == preserved['evidence_id']


def test_retry_of_multi_source_parse_only_processes_selected_file(service, monkeypatch):
    initial = prepare(service, file_ids=['current:0', 'table:0'])
    first, other = initial['frozen_input']['files']
    info = parsers.parser_info
    monkeypatch.setattr(parsers, 'parser_info', lambda fmt: dict(info(fmt), adapter_version='next'))
    with monkeypatch.context() as patch:
        def fail(*a):
            raise ValueError('시험용 실패')
        patch.setattr(parsers, 'parse_unit', fail)
        manual = finished(service, service.start(RunRequest(source_version_ids=initial['input_version_ids']))['run_id'])
        assert manual['status'] == 'failed'
    other_before = service.version(other['source_id'], other['source_version_id'])
    selected = prepare(service, file_ids=['current:0'])
    parse = service.run(selected['units'][0]['parse_run_id'])
    assert parse['retry_of_run_id'] == manual['id']
    assert parse['input_version_ids'] == [first['source_version_id']]
    assert service.version(other['source_id'], other['source_version_id']) == other_before


def test_fixed_hash_rejected_and_availability_enforced(service, corpus):
    stale = request()
    inputs.MANIFEST.write_text(inputs.MANIFEST.read_text() + '\n')
    with pytest.raises(ValueError, match='manifest_hash'):
        service.start(stale)
    run = prepare(service, file_ids=['current:0'])
    block = discovery.read(service, run['id'], 'current:0')['items'][0]
    snapshots.set_availability(service, dict(actor='test', reason='사용 중단', expected_status_revision=0,
        targets=[dict(type='source_version', id=block['source_version_id'])], state='blocked'))
    with pytest.raises(ValueError, match='사용 중단'):
        discovery.read(service, run['id'], 'current:0')
    assert discovery.search(service, run['id'], '국민임대')['items'] == []
    (corpus / 'current.txt').write_text('변조', encoding='utf-8')
    with pytest.raises(ValueError, match='해시 불일치'):
        service.start(request(file_ids=['current:0']))


def test_discovery_api_envelopes_and_original_version_lookup(service, monkeypatch):
    app = FastAPI()
    app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    prefix = '/api/v1/knowledge'
    with TestClient(app) as client:
        data = client.get(prefix + '/discovery/sources').json()['data']
        response = client.post(prefix + '/runs', json=dict(kind='discovery', bundle_id=data['bundle_id'],
            manifest_hash=data['manifest_sha256'], file_ids=['current:0']))
        assert response.status_code == 200 and response.json()['success']
        rid = response.json()['data']['run_id']
        assert finished(service, rid)['status'] == 'succeeded'
        response = client.get(prefix + '/discovery/read', params=dict(run_id=rid, file_id='current:0'))
        assert response.status_code == 200
        block = response.json()['data']['items'][0]
        assert client.get(prefix + '/evidence/' + block['evidence_id']).json()['data']['block']['text'] == block['text']
        raw = f"{prefix}/sources/{block['source_id']}/versions/{block['source_version_id']}/raw"
        assert '현재 국민임대' in client.get(raw).content.decode('utf-8-sig')
        assert client.get(prefix + '/discovery/search', params=dict(run_id=rid, q='국민임대')).json()['data']['items']
        assert client.get(prefix + '/discovery/sources', params=dict(run_id=rid)).json()['data']['items'][0]['block_ids']
        assert client.get(prefix + '/discovery/read', params=dict(run_id=rid, file_id='old:0')).status_code == 404
        assert client.get(prefix + '/discovery/search', params=dict(run_id=rid, q='임대', step=1)).status_code == 422
        assert client.post(prefix + '/runs', json=dict(kind='discovery', retry_of_run_id=rid, scope='historical_change')).status_code == 422
        assert client.get(prefix + '/discovery/read', params=dict(file_id='current:0')).status_code == 200

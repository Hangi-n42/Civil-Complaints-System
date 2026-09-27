from threading import Event
from time import monotonic, sleep
import sys
import types
import pytest

from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeConflict, KnowledgeService


def finished(service, run_id):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        run = service.run(run_id)
        if run['status'] not in {'queued', 'running', 'cancel_requested'}:
            return run
        sleep(.01)
    raise AssertionError('worker did not finish')


def registration():
    return SourceRegistration(title='단지', publisher='LH', namespace='LH', external_id='one')


def test_registration_failure_retry_cancel_and_evidence(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    failures = {'two'}
    def parse(path, format, unit):
        if unit['id'] in failures:
            raise ValueError('broken table')
        if unit['id'] == 'wait':
            entered.set()
            assert release.wait(5)
        return [{'text': '한글 근거', 'locator': {'format': 'csv', 'physical_row': 2}}]
    parser = types.SimpleNamespace(plan_units=lambda *args: [{'id': 'one'}, {'id': 'two'}],
                                   parser_info=lambda _: {'name': 'test', 'version': '1'}, parse_unit=parse)
    monkeypatch.setitem(sys.modules, 'app.knowledge.parsers', parser)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        registered = service.register('test.csv', b'code,name\n1,test', registration())
        sid, vid = registered['source_id'], registered['source_version_id']
        assert service.register('copy.csv', b'code,name\n1,test', registration())['disposition'] == 'duplicate'
        with pytest.raises(ValueError):
            service.register('../test.csv', b'bad', registration())
        run_id = service.start(RunRequest(source_version_ids=[vid]))['run_id']
        assert finished(service, run_id)['status'] == 'partial'
        block = service.blocks(sid, vid)['items'][0]
        evidence = service.evidence(block['evidence_id'])['evidence']
        assert evidence['quote'] == '한글 근거'
        assert evidence['end_char'] == len(evidence['quote'])
        failures.clear()
        retry = service.start(RunRequest(retry_of_run_id=run_id))['run_id']
        assert finished(service, retry)['status'] == 'succeeded'
        assert len(service.blocks(sid, vid)['items']) == 2
        assert service.version(sid, vid)['version']['processing_status'] == 'parsed'
        parser.plan_units = lambda *args: [{'id': 'wait'}, {'id': 'never'}]
        cancel_run = service.start(RunRequest(source_version_ids=[vid]))['run_id']
        assert entered.wait(5)
        with pytest.raises(KnowledgeConflict):
            service.start(RunRequest(source_version_ids=[vid]))
        service.cancel(cancel_run)
        release.set()
        cancelled = finished(service, cancel_run)
        assert cancelled['status'] == 'cancelled'
        assert [u['status'] for u in cancelled['units']] == ['succeeded', 'cancelled']
        assert len(service.blocks(sid, vid)['items']) == 1
        assert service.evidence(block['evidence_id'])['evidence']['quote'] == '한글 근거'
    finally:
        release.set()
        service.shutdown()


def test_interrupted_run_is_recoverable(tmp_path, monkeypatch):
    parser = types.SimpleNamespace(plan_units=lambda *args: [{'id': 'one'}],
                                   parser_info=lambda _: {'name': 'test', 'version': '1'})
    monkeypatch.setitem(sys.modules, 'app.knowledge.parsers', parser)
    path = tmp_path / 'knowledge.db'
    service = KnowledgeService(path)
    vid = service.register('a.csv', b'a', registration())['source_version_id']
    # Simulate a process exit after persisting a queued run, without launching work.
    monkeypatch.setattr(service.executor, 'submit', lambda *args: None)
    rid = service.start(RunRequest(source_version_ids=[vid]))['run_id']
    service.executor.shutdown()
    resumed = KnowledgeService(path)
    try:
        assert resumed.run(rid)['status'] == 'failed'
        assert resumed.run(rid)['units'][0]['status'] == 'failed'
    finally:
        resumed.shutdown()

"""Single-worker parsing, preserving original bytes and completed units."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from time import monotonic
from uuid import uuid4
import json

from .repository import KnowledgeRepository
from .schemas import RunRequest, SourceRegistration


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class KnowledgeConflict(ValueError):
    pass


class KnowledgeService:
    def __init__(self, db_path):
        self.repository = KnowledgeRepository(Path(db_path))
        self.raw_dir = self.repository.path.parent / 'raw'
        self.raw_dir.mkdir(exist_ok=True)
        # ponytail: one worker per local server; use a shared job queue only for multi-process deployment.
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='knowledge-parse')
        self.closed = False
        with self.repository.connect() as db:
            for row in db.execute('SELECT payload FROM runs').fetchall():
                run = json.loads(row['payload'])
                if run['status'] in {'queued', 'running', 'cancel_requested'}:
                    for unit in run['units']:
                        if unit['status'] in {'queued', 'running'}:
                            unit.update(status='failed', error='서버 재시작으로 중단됨')
                    run.update(status='failed', finished_at=utcnow())
                    self.repository.save(db, 'runs', run)
                    self._update_versions(db, run)

    def register(self, filename, content: bytes, metadata: SourceRegistration):
        if not filename or '/' in filename or '\\' in filename or filename in {'.', '..'}:
            raise ValueError('경로를 포함하지 않는 파일명이 필요합니다.')
        format = Path(filename).suffix.lstrip('.').lower()
        if format not in {'pdf', 'html', 'csv', 'hwpx'} or not content:
            raise ValueError('비어 있지 않은 PDF/HTML/CSV/HWPX 파일만 등록할 수 있습니다.')
        digest = sha256(content).hexdigest()
        with self.lock, self.repository.connect() as db:
            source_id = metadata.source_id
            if not source_id and metadata.external_id:
                row = db.execute('SELECT id FROM sources WHERE namespace=? AND external_id=?',
                                 (metadata.namespace, metadata.external_id)).fetchone()
                source_id = row['id'] if row else None
            if source_id:
                self.repository.get(db, 'sources', source_id)
            else:
                source_id = uuid4().hex
                source = dict(id=source_id, title=metadata.title, publisher=metadata.publisher,
                              namespace=metadata.namespace, external_id=metadata.external_id or None,
                              source_url=metadata.source_url, rights=metadata.rights.model_dump(), created_at=utcnow())
                db.execute('INSERT INTO sources VALUES(?,?,?,?)',
                           (source_id, metadata.namespace, metadata.external_id or None, encode(source)))
            existing = db.execute('SELECT id FROM versions WHERE source_id=? AND sha256=?', (source_id, digest)).fetchone()
            if existing:
                return dict(source_id=source_id, source_version_id=existing['id'], disposition='duplicate')
            if metadata.supersedes_version_id:
                previous = self.repository.get(db, 'versions', metadata.supersedes_version_id)
                if previous['source_id'] != source_id:
                    raise ValueError('supersedes 버전은 같은 출처여야 합니다.')
            raw = self.raw_dir / f'{digest}.{format}'
            if not raw.exists():
                temporary = raw.with_suffix('.tmp')
                temporary.write_bytes(content)
                temporary.replace(raw)
            version = dict(id=uuid4().hex, source_id=source_id, sha256=digest,
                           relative_raw_path=raw.relative_to(self.repository.path.parent).as_posix(),
                           filename=filename, format=format, acquired_at=metadata.acquired_at,
                           verified_at=utcnow(), dates=metadata.dates, selected_scope=metadata.selected_scope,
                           supersedes_version_id=metadata.supersedes_version_id,
                           processing_status='registered', latest_parse_run_id=None)
            db.execute('INSERT INTO versions VALUES(?,?,?,?)', (version['id'], source_id, digest, encode(version)))
            return dict(source_id=source_id, source_version_id=version['id'], disposition='registered')

    def sources(self, source_id=None):
        with self.repository.connect() as db:
            rows = db.execute('SELECT payload FROM sources' + (' WHERE id=?' if source_id else ''),
                              (source_id,) if source_id else ()).fetchall()
            items = []
            for row in rows:
                source = json.loads(row['payload'])
                versions = [json.loads(v['payload']) for v in db.execute('SELECT payload FROM versions WHERE source_id=?', (source['id'],))]
                items.append(dict(source=source, versions=versions,
                                  processing_status=versions[-1]['processing_status'] if versions else 'registered'))
            return dict(items=items)

    def version(self, source_id, version_id):
        with self.repository.connect() as db:
            version = self.repository.get(db, 'versions', version_id)
            if version['source_id'] != source_id:
                raise KeyError(version_id)
            return dict(source=self.repository.get(db, 'sources', source_id), version=version,
                        raw_url=f'/api/v1/knowledge/sources/{source_id}/versions/{version_id}/raw')

    def raw_path(self, version):
        return self.repository.path.parent / version['relative_raw_path']

    def blocks(self, source_id, version_id):
        self.version(source_id, version_id)
        with self.repository.connect() as db:
            version = self.repository.get(db, 'versions', version_id)
            if not version['latest_parse_run_id']:
                return dict(items=[])
            run = self.repository.get(db, 'runs', version['latest_parse_run_id'])
            lineage = [run]
            while lineage[-1].get('retry_of_run_id'):
                lineage.append(self.repository.get(db, 'runs', lineage[-1]['retry_of_run_id']))
            effective = {}
            for prior in reversed(lineage):
                for unit in prior['units']:
                    if unit['source_version_id'] == version_id and unit['status'] == 'succeeded':
                        effective[unit['id']] = prior['id']
            items = []
            for uid, rid in effective.items():
                items.extend(json.loads(row['payload']) for row in db.execute(
                    'SELECT payload FROM blocks WHERE version_id=? AND run_id=? AND unit_id=? ORDER BY block_order',
                    (version_id, rid, uid)))
            return dict(items=items)

    def evidence(self, evidence_id):
        with self.repository.connect() as db:
            block = self.repository.get(db, 'blocks', evidence_id)
            version = self.repository.get(db, 'versions', block['source_version_id'])
            source = self.repository.get(db, 'sources', version['source_id'])
            return dict(evidence=dict(id=evidence_id, block_id=block['id'], quote=block['text'],
                                      start_char=0, end_char=len(block['text']), alignment_status='matched'),
                        block=block, source=source, version=version)

    def run(self, run_id):
        with self.repository.connect() as db:
            run = self.repository.get(db, 'runs', run_id)
        run['counts'] = {status: sum(u['status'] == status for u in run['units'])
                         for status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')}
        return run

    def start(self, request: RunRequest):
        from .parsers import plan_units, parser_info
        if request.kind != 'parse':
            raise ValueError('K2에서는 parse 작업만 지원합니다.')
        with self.lock, self.repository.connect() as db:
            if self.closed:
                raise KnowledgeConflict('서비스가 종료 중입니다.')
            active = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM runs')]
            if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in active):
                raise KnowledgeConflict('실행 중인 작업이 있습니다.')
            run = dict(id=uuid4().hex, kind='parse', status='queued', units=[], input_version_ids=[],
                       retry_of_run_id=request.retry_of_run_id, started_at=None, finished_at=None,
                       metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
            if request.retry_of_run_id:
                previous = self.repository.get(db, 'runs', request.retry_of_run_id)
                eligible = {u['id']: u for u in previous['units'] if u['status'] in {'failed', 'cancelled'}}
                selected = request.unit_ids if request.unit_ids is not None else list(eligible)
                if not selected or any(uid not in eligible for uid in selected):
                    raise ValueError('실패 또는 취소된 단위만 재시도할 수 있습니다.')
                for uid in dict.fromkeys(selected):
                    failed = eligible[uid]
                    version = self.repository.get(db, 'versions', failed['source_version_id'])
                    current_parser = parser_info(version['format'])
                    current_options = sha256(encode(version['selected_scope']).encode()).hexdigest()
                    if failed['parser'] != current_parser or failed['options_hash'] != current_options:
                        raise ValueError('파서 또는 범위 설정이 변경되었습니다. 새 parse 실행이 필요합니다.')
                    if failed['spec'] is None:
                        version = self.repository.get(db, 'versions', failed['source_version_id'])
                        try:
                            specs = plan_units(self.raw_path(version), version['format'], version['selected_scope'])
                            if not specs:
                                raise ValueError('선택 범위에 처리할 단위가 없습니다.')
                            for spec in specs:
                                run['units'].append({**failed, 'id': f'{version["id"]}:{spec["id"]}',
                                                     'spec': spec, 'status': 'queued', 'error': None})
                        except Exception as exc:
                            run['units'].append({**failed, 'status': 'failed', 'error': str(exc)})
                    else:
                        run['units'].append({**failed, 'status': 'queued', 'error': None})
                run['input_version_ids'] = list(dict.fromkeys(u['source_version_id'] for u in run['units']))
            else:
                if not request.source_version_ids or request.unit_ids:
                    raise ValueError('source_version_ids가 필요하며 unit_ids는 재시도에만 사용합니다.')
                run['input_version_ids'] = list(dict.fromkeys(request.source_version_ids))
                for vid in run['input_version_ids']:
                    version = self.repository.get(db, 'versions', vid)
                    info = parser_info(version['format'])
                    options_hash = sha256(encode(version['selected_scope']).encode()).hexdigest()
                    try:
                        units = plan_units(self.raw_path(version), version['format'], version['selected_scope'])
                        if not units:
                            raise ValueError('선택 범위에 처리할 단위가 없습니다.')
                        for unit in units:
                            run['units'].append(dict(id=f'{vid}:{unit["id"]}', source_version_id=vid,
                                                     spec=unit, status='queued', error=None, parser=info,
                                                     options_hash=options_hash))
                    except Exception as exc:
                        run['units'].append(dict(id=f'{vid}:plan', source_version_id=vid,
                                                 spec=None, status='failed', error=str(exc), parser=info,
                                                 options_hash=options_hash))
            db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
        self.executor.submit(self._execute, run['id'])
        return dict(run_id=run['id'], status='queued')

    def cancel(self, run_id):
        with self.lock, self.repository.connect() as db:
            run = self.repository.get(db, 'runs', run_id)
            if run['status'] in {'queued', 'running'}:
                run['status'] = 'cancel_requested'
                self.repository.save(db, 'runs', run)
            return dict(run_id=run_id, status=run['status'])

    def _update_versions(self, db, run):
        for vid in run['input_version_ids']:
            version = self.repository.get(db, 'versions', vid)
            lineage = [run]
            while lineage[-1].get('retry_of_run_id'):
                lineage.append(self.repository.get(db, 'runs', lineage[-1]['retry_of_run_id']))
            effective = {}
            for prior in reversed(lineage):
                for unit in prior['units']:
                    if unit['source_version_id'] == vid:
                        effective[unit['id']] = unit
                # A planning retry replaces the failed planning placeholder with actual units.
                if any(u['source_version_id'] == vid and u['spec'] is not None for u in prior['units']):
                    effective.pop(f'{vid}:plan', None)
            units = list(effective.values())
            version['processing_status'] = 'parsed' if units and all(u['status'] == 'succeeded' for u in units) else 'failed'
            version['latest_parse_run_id'] = run['id']
            self.repository.save(db, 'versions', version)

    def _execute(self, run_id):
        from .parsers import parse_unit
        started = monotonic()
        with self.lock, self.repository.connect() as db:
            run = self.repository.get(db, 'runs', run_id)
            if run['status'] != 'cancel_requested':
                run['status'] = 'running'
            run['started_at'] = utcnow()
            self.repository.save(db, 'runs', run)
        for index in range(len(run['units'])):
            with self.lock, self.repository.connect() as db:
                run = self.repository.get(db, 'runs', run_id)
                if run['status'] == 'cancel_requested':
                    break
                unit = run['units'][index]
                if unit['status'] != 'queued':
                    continue
                version = self.repository.get(db, 'versions', unit['source_version_id'])
                unit['status'] = 'running'
                self.repository.save(db, 'runs', run)
            try:
                if unit['spec'] is None:
                    raise ValueError('범위 계획 실패는 새 parse 실행으로 재확인하십시오.')
                parsed = parse_unit(self.raw_path(version), version['format'], unit['spec'])
                with self.lock, self.repository.connect() as db:
                    run = self.repository.get(db, 'runs', run_id)
                    for order, block in enumerate(parsed):
                        bid = uuid4().hex
                        payload = dict(id=bid, evidence_id=bid, source_version_id=version['id'],
                                       parse_run_id=run_id, unit_id=unit['id'], order=order,
                                       text=block['text'], locator=block['locator'])
                        db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)',
                                   (bid, version['id'], run_id, unit['id'], order, encode(payload)))
                    run['units'][index].update(status='succeeded', error=None, block_count=len(parsed))
                    self.repository.save(db, 'runs', run)
            except Exception as exc:
                with self.lock, self.repository.connect() as db:
                    run = self.repository.get(db, 'runs', run_id)
                    run['units'][index].update(status='failed', error=str(exc))
                    self.repository.save(db, 'runs', run)
        with self.lock, self.repository.connect() as db:
            run = self.repository.get(db, 'runs', run_id)
            cancelled = run['status'] == 'cancel_requested'
            for unit in run['units']:
                if unit['status'] == 'queued':
                    unit['status'] = 'cancelled'
            statuses = {u['status'] for u in run['units']}
            run['status'] = ('cancelled' if cancelled else 'succeeded' if statuses == {'succeeded'}
                             else 'partial' if 'succeeded' in statuses else 'failed')
            run['finished_at'] = utcnow()
            run['metrics']['elapsed_s'] = round(monotonic() - started, 3)
            self.repository.save(db, 'runs', run)
            self._update_versions(db, run)

    def shutdown(self):
        with self.lock, self.repository.connect() as db:
            self.closed = True
            for row in db.execute('SELECT payload FROM runs').fetchall():
                run = json.loads(row['payload'])
                if run['status'] in {'queued', 'running'}:
                    run['status'] = 'cancel_requested'
                    self.repository.save(db, 'runs', run)
        self.executor.shutdown(wait=True)

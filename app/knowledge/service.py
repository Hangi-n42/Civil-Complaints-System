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
                    for unit in [*run['units'], *run.get('analysis_units', [])]:
                        if unit['status'] in {'queued', 'running'}:
                            if unit['status'] == 'running' and unit.get('attempts'):
                                attempt = unit['attempts'][-1]
                                if attempt['outcome'] == 'started':
                                    attempt['outcome'] = 'interrupted_before_result_commit'
                                    run['metrics']['interrupted_time_reserve_s'] = run['metrics'].get('interrupted_time_reserve_s', 0) + attempt['timeout_s']
                            unit.update(status='failed', error='서버 재시작으로 중단됨')
                    run.update(status='failed', finished_at=utcnow())
                    self.repository.save(db, 'runs', run)
                    self._update_versions(db, run)

    def register(self, filename, content: bytes, metadata: SourceRegistration):
        if not filename or '/' in filename or '\\' in filename or filename in {'.', '..'}:
            raise ValueError('경로를 포함하지 않는 파일명이 필요합니다.')
        format = Path(filename).suffix.lstrip('.').lower()
        if format not in {'pdf', 'html', 'csv', 'hwpx', 'txt', 'md', 'json', 'xlsx'} or not content:
            raise ValueError('비어 있지 않은 PDF/HTML/CSV/HWPX/TXT/MD/JSON/XLSX 파일만 등록할 수 있습니다.')
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
            run_id = version['latest_parse_run_id'] or version.get('latest_parse_attempt_run_id')
            return dict(items=self.parse_blocks(db, run_id, version_id) if run_id else [])

    def parse_blocks(self, db, run_id, version_id):
        """Read a specific parse lineage, independent of the version's current pointer."""
        run = self.repository.get(db, 'runs', run_id)
        if run['kind'] != 'parse' or version_id not in run['input_version_ids']:
            raise ValueError('해당 버전의 parse 실행이 아닙니다.')
        items = []
        for unit, rid in self.parse_units(db, run, version_id):
            if unit['status'] == 'succeeded':
                items.extend(json.loads(row['payload']) for row in db.execute(
                    'SELECT payload FROM blocks WHERE version_id=? AND run_id=? AND unit_id=? ORDER BY block_order',
                    (version_id, rid, unit['id'])))
        return items

    def parse_units(self, db, run, version_id):
        lineage = [run]
        while lineage[-1].get('retry_of_run_id'):
            lineage.append(self.repository.get(db, 'runs', lineage[-1]['retry_of_run_id']))
        effective = {}
        for prior in reversed(lineage):
            for unit in prior['units']:
                if unit['source_version_id'] == version_id:
                    effective[unit['id']] = (unit, prior['id'])
            if any(u['source_version_id'] == version_id and u['spec'] is not None for u in prior['units']):
                effective.pop(f'{version_id}:plan', None)
        return list(effective.values())

    def evidence(self, evidence_id):
        with self.repository.connect() as db:
            saved = db.execute('SELECT payload FROM evidence WHERE id=?', (evidence_id,)).fetchone()
            evidence = json.loads(saved['payload']) if saved else None
            block = self.repository.get(db, 'blocks', evidence['block_id'] if evidence else evidence_id)
            version = self.repository.get(db, 'versions', block['source_version_id'])
            source = self.repository.get(db, 'sources', version['source_id'])
            from .snapshots import current_restrictions
            restrictions = current_restrictions(self.repository, db, {'evidence_ids': [evidence_id]})
            return dict(evidence=evidence or dict(id=evidence_id, block_id=block['id'], quote=block['text'],
                                      start_char=0, end_char=len(block['text']), alignment_status='matched'),
                        block=block, source=source, version=version, usage_restrictions=restrictions)

    def run(self, run_id):
        with self.repository.connect() as db:
            run = self.repository.get(db, 'runs', run_id)
        run['counts'] = {status: sum(u['status'] == status for u in run['units'])
                         for status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')}
        if run.get('discovery_mode') == 'analyze':
            run['analysis_counts'] = {s: sum(u['status']==s for u in run['analysis_units'])
                                      for s in ('queued','running','succeeded','failed')}
        if run['kind'] == 'extract':
            run['processed_block_ids'] = list(dict.fromkeys(b for u in run['units']
                if u['status'] == 'succeeded' for b in u['block_ids']))
            if run.get('changeset_id'):
                from .extraction_store import candidates
                items = candidates(self, run['changeset_id'])['items']
                invalid = sum(bool(v.get('validation_errors')) for v in items)
                run['candidate_counts'] = dict(valid=len(items)-invalid, invalid=invalid,
                    manual=sum(v.get('origin')=='manual' for v in items), automatic=sum(v.get('origin')!='manual' for v in items),
                    unresolved=sum(v['review_status'] in {'proposed', 'deferred'} for v in items))
        return run

    def start(self, request: RunRequest):
        if request.kind == 'discovery':
            from .discovery_run import start
            return start(self, request)
        if request.kind == 'ontology':
            from .ontology_run import start
            return start(self, request)
        if request.kind == 'extract':
            from .extraction import start
            return start(self, request)
        if request.kind != 'parse':
            raise ValueError('현재 parse, ontology, extract, discovery 작업만 지원합니다.')
        with self.lock, self.repository.connect() as db:
            if self.closed:
                raise KnowledgeConflict('서비스가 종료 중입니다.')
            active = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM runs')]
            if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in active):
                raise KnowledgeConflict('실행 중인 작업이 있습니다.')
            run = self._create_parse(db, request)
        self.executor.submit(self._execute, run['id'])
        return dict(run_id=run['id'], status='queued')

    def start_business(self, request):
        from .business_run import start
        return start(self, request)

    def _create_parse(self, db, request):
        from .parsers import plan_units, parser_info
        run = dict(id=uuid4().hex, kind='parse', status='queued', units=[], input_version_ids=[],
                   retry_of_run_id=request.retry_of_run_id, started_at=None, finished_at=None,
                   metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        if request.retry_of_run_id:
            if request.parser_options is not None:
                raise ValueError('재시도에서 파서 옵션을 변경할 수 없습니다.')
            previous = self.repository.get(db, 'runs', request.retry_of_run_id)
            if previous['kind'] != 'parse':
                raise ValueError('parse 작업만 parse로 재시도할 수 있습니다.')
            eligible = {u['id']: u for u in previous['units'] if u['status'] in {'failed', 'cancelled'}}
            selected = request.unit_ids if request.unit_ids is not None else list(eligible)
            if not selected or any(uid not in eligible for uid in selected):
                raise ValueError('실패 또는 취소된 단위만 재시도할 수 있습니다.')
            for uid in dict.fromkeys(selected):
                failed = eligible[uid]
                version = self.repository.get(db, 'versions', failed['source_version_id'])
                current_parser = parser_info(version['format'])
                options = failed.get('options', version['selected_scope'])
                current_options = sha256(encode(options).encode()).hexdigest()
                if failed['parser'] != current_parser or failed['options_hash'] != current_options:
                    raise ValueError('파서 또는 범위 설정이 변경되었습니다. 새 parse 실행이 필요합니다.')
                if failed['spec'] is None:
                    version = self.repository.get(db, 'versions', failed['source_version_id'])
                    try:
                        specs = plan_units(self.raw_path(version), version['format'], options)
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
                options = version['selected_scope'] if request.parser_options is None else request.parser_options
                options_hash = sha256(encode(options).encode()).hexdigest()
                try:
                    units = plan_units(self.raw_path(version), version['format'], options)
                    if not units:
                        raise ValueError('선택 범위에 처리할 단위가 없습니다.')
                    for unit in units:
                        run['units'].append(dict(id=f'{vid}:{unit["id"]}', source_version_id=vid,
                                                 spec=unit, status='queued', error=None, parser=info,
                                                 options_hash=options_hash, options=options))
                except Exception as exc:
                    run['units'].append(dict(id=f'{vid}:plan', source_version_id=vid,
                                             spec=None, status='failed', error=str(exc), parser=info,
                                             options_hash=options_hash, options=options))
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
        return run

    def find_parse(self, db, version_id, parser, options, *, complete=True):
        """Find a matching recipe by version, never by its latest pointer."""
        for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC'):
            run = json.loads(row['payload'])
            statuses = {'succeeded', 'partial'} if complete else {'failed', 'partial', 'cancelled'}
            if run['kind'] != 'parse' or run['status'] not in statuses:
                continue
            if version_id not in run['input_version_ids']:
                continue
            units = [u for u, _ in self.parse_units(db, run, version_id)]
            version = self.repository.get(db, 'versions', version_id)
            if not units or not all(u['parser'] == parser and
                    u.get('options', version['selected_scope']) == options for u in units):
                continue
            if complete and all(u['status'] == 'succeeded' for u in units):
                return run['id']
            if not complete and any(u['source_version_id'] == version_id and
                                    u['status'] in {'failed', 'cancelled'} for u in run['units']):
                return run['id']
        return None

    def parse_input(self, item):
        """Called on the serial worker; only this parse path writes parse state/pointers."""
        from .parsers import parser_info
        with self.lock, self.repository.connect() as db:
            run_id = self.find_parse(db, item['source_version_id'], item['parser'], item['parser_options'])
            if run_id:
                return run_id
            version = self.repository.get(db, 'versions', item['source_version_id'])
            if parser_info(version['format']) != item['parser']:
                raise ValueError('고정된 파서 버전이 변경되었습니다. 새 discovery 실행이 필요합니다.')
            # Identical bytes from another source reuse parsing, but retain separate provenance IDs.
            retry_id = self.find_parse(db, version['id'], item['parser'], item['parser_options'], complete=False)
            run = None
            if retry_id:
                previous = self.repository.get(db, 'runs', retry_id)
                failed = [u['id'] for u in previous['units'] if u['source_version_id'] == version['id'] and
                          u['status'] in {'failed', 'cancelled'}]
                run = self._create_parse(db, RunRequest(retry_of_run_id=retry_id, unit_ids=failed))
            for row in db.execute('SELECT payload FROM versions WHERE sha256=? AND id!=?',
                                  (version['sha256'], version['id'])).fetchall():
                if run is not None:
                    break
                other = json.loads(row['payload'])
                if other['format'] != version['format']:
                    continue
                previous_id = self.find_parse(db, other['id'], item['parser'], item['parser_options'])
                if not previous_id:
                    continue
                previous = self.repository.get(db, 'runs', previous_id)
                blocks = self.parse_blocks(db, previous_id, other['id'])
                units = [dict(u, id=f'{version["id"]}:{u["spec"]["id"]}', source_version_id=version['id'],
                              status='queued', error=None,
                              reuse_from_block_ids=[b['id'] for b in blocks if b['unit_id'] == u['id']])
                         for u, _ in self.parse_units(db, previous, other['id'])]
                run = dict(id=uuid4().hex, kind='parse', status='queued', units=units,
                           input_version_ids=[version['id']], retry_of_run_id=None,
                           started_at=None, finished_at=None, reused_parse_run_id=previous_id,
                           metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
                db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
                break
            if run is None:
                run = self._create_parse(db, RunRequest(source_version_ids=[version['id']],
                                                        parser_options=item['parser_options']))
        self._execute(run['id'])
        return run['id']

    def cancel(self, run_id):
        with self.lock, self.repository.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run = self.repository.get(db, 'runs', run_id)
            if run['status'] in {'queued', 'running'}:
                run['status'] = 'cancel_requested'
                self.repository.save(db, 'runs', run)
            return dict(run_id=run_id, status=run['status'])

    def _update_versions(self, db, run):
        if run['kind'] != 'parse':
            return
        for vid in run['input_version_ids']:
            version = self.repository.get(db, 'versions', vid)
            units = [u for u, _ in self.parse_units(db, run, vid)]
            complete = (run['status'] in {'succeeded', 'partial'} and units and
                        all(u['status'] == 'succeeded' for u in units))
            version['processing_status'] = 'parsed' if complete else 'failed'
            version['latest_parse_attempt_run_id'] = run['id']
            if complete:
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
                if sha256(self.raw_path(version).read_bytes()).hexdigest() != version['sha256']:
                    raise ValueError('등록 원문 해시 불일치')
                if 'reuse_from_block_ids' in unit:
                    with self.repository.connect() as db:
                        parsed = [self.repository.get(db, 'blocks', bid) for bid in unit['reuse_from_block_ids']]
                else:
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
                        evidence = dict(id=bid, block_id=bid, quote=block['text'], start_char=0,
                                        end_char=len(block['text']), alignment_status='matched')
                        db.execute('INSERT INTO evidence VALUES(?,?)', (bid, encode(evidence)))
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

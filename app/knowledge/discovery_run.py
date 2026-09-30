"""A1 input preparation on the existing serial executor; no ontology or model calls."""
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from . import discovery_inputs as inputs
from .schemas import SourceRegistration
from .service import KnowledgeConflict, encode, utcnow


def _freeze(service, request):
    from .parsers import parser_info
    data = inputs.catalog(request.scope or 'current_discovery', request.step or 0)
    if request.bundle_id != data['bundle_id'] or request.manifest_hash != data['manifest_sha256']:
        raise ValueError('현재 확정 목록의 bundle_id와 manifest_hash가 필요합니다.')
    selected = set(request.file_ids) if request.file_ids is not None else {f['file_id'] for f in data['items']}
    if not selected <= {f['file_id'] for f in data['items']}:
        raise ValueError('선택 scope/step 밖 파일은 등록할 수 없습니다.')
    files = [f for f in data['items'] if f['file_id'] in selected]
    if not files:
        raise ValueError('선택된 입력 파일이 없습니다.')
    contents = []
    for item in files:
        content = inputs._path(item).read_bytes()
        if sha256(content).hexdigest() != item['sha256']:
            raise ValueError('확정 입력 해시 불일치: ' + item['file_id'])
        contents.append(content)
        item['parser'] = parser_info(Path(item['path']).suffix.lstrip('.').lower())
        item['parser_options'] = inputs.parser_options(item)
    for item, content in zip(files, contents):
        registered = service.register(Path(item['path']).name, content, SourceRegistration(
            title=item['title'], publisher=item['publisher'] or '미확인',
            namespace='discovery:' + data['bundle_id'], external_id=item['source_id'],
            source_url=item['source_url'], selected_scope=item['parser_options'],
            rights={'status': 'local_only', 'note': encode(item['rights'])}))
        item['manifest_source_id'] = item['source_id']
        item.update(source_id=registered['source_id'], source_version_id=registered['source_version_id'])
    return dict(bundle_id=data['bundle_id'], manifest_hash=data['manifest_sha256'],
                scope=data['scope'], step=data['step'], files=files)


def start(service, request):
    allowed = {'kind', 'retry_of_run_id'} if request.retry_of_run_id else {
        'kind', 'bundle_id', 'manifest_hash', 'scope', 'step', 'file_ids'}
    if request.model_fields_set - allowed:
        raise ValueError('A1 discovery는 입력 선택 또는 변경 없는 재개만 지원합니다.')
    with service.lock, service.repository.connect() as db:
        if service.closed:
            raise KnowledgeConflict('서비스가 종료 중입니다.')
        if any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
               for r in db.execute('SELECT payload FROM runs').fetchall()):
            raise KnowledgeConflict('실행 중인 작업이 있습니다.')
        if request.retry_of_run_id:
            run = service.repository.get(db, 'runs', request.retry_of_run_id)
            if run['kind'] != 'discovery':
                raise ValueError('discovery 실행만 재개할 수 있습니다.')
            if run['status'] == 'succeeded':
                return dict(run_id=run['id'], status=run['status'])
            if run['status'] not in {'failed', 'partial', 'cancelled'}:
                raise ValueError('종료된 discovery 실행만 재개할 수 있습니다.')
            run['reused_units'] = [u['id'] for u in run['units'] if u['status'] == 'succeeded']
            for unit in run['units']:
                if unit['status'] != 'succeeded':
                    unit.update(status='queued', error=None)
        else:
            frozen = _freeze(service, request)
            run = dict(kind='discovery', frozen_input=frozen,
                       input_version_ids=list(dict.fromkeys(f['source_version_id'] for f in frozen['files'])),
                       units=[dict(id=uuid4().hex, file_id=f['file_id'], status='queued', error=None,
                                   source_version_id=f['source_version_id']) for f in frozen['files']])
        run.update(id=uuid4().hex, status='queued', retry_of_run_id=request.retry_of_run_id,
                   started_at=None, finished_at=None, stage='input_grounding',
                   metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    service.executor.submit(execute, service, run['id'])
    return dict(run_id=run['id'], status='queued')


def execute(service, run_id):
    started = monotonic()
    with service.lock, service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
        if run['status'] != 'cancel_requested':
            run['status'] = 'running'
        run['started_at'] = utcnow()
        service.repository.save(db, 'runs', run)
    for index, item in enumerate(run['frozen_input']['files']):
        with service.lock, service.repository.connect() as db:
            run = service.repository.get(db, 'runs', run_id)
            if run['status'] == 'cancel_requested':
                break
            if run['units'][index]['status'] == 'succeeded':
                continue
            run['units'][index]['status'] = 'running'
            service.repository.save(db, 'runs', run)
        try:
            parse_id = service.parse_input(item)
            with service.lock, service.repository.connect() as db:
                parsed = service.repository.get(db, 'runs', parse_id)
                units = [u for u, _ in service.parse_units(db, parsed, item['source_version_id'])]
                if not units or any(u['status'] != 'succeeded' for u in units):
                    errors = [u['error'] for u in parsed['units'] if u.get('error')]
                    raise ValueError('입력 parse 미완료: ' + '; '.join(errors))
                blocks = service.parse_blocks(db, parse_id, item['source_version_id'])
                if not blocks:
                    raise ValueError('완료된 원문 블록이 없습니다.')
                run = service.repository.get(db, 'runs', run_id)
                run['units'][index].update(status='succeeded', error=None, parse_run_id=parse_id,
                    block_ids=[b['id'] for b in blocks])
                service.repository.save(db, 'runs', run)
        except Exception as exc:
            with service.lock, service.repository.connect() as db:
                run = service.repository.get(db, 'runs', run_id)
                run['units'][index].update(status='failed', error=str(exc))
                service.repository.save(db, 'runs', run)
    with service.lock, service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
        cancelled = run['status'] == 'cancel_requested'
        for unit in run['units']:
            if unit['status'] == 'queued':
                unit['status'] = 'cancelled'
        statuses = {u['status'] for u in run['units']}
        run['status'] = ('cancelled' if cancelled else 'succeeded' if statuses == {'succeeded'}
                         else 'partial' if 'succeeded' in statuses else 'failed')
        run['finished_at'] = utcnow()
        run['metrics']['elapsed_s'] = round(monotonic() - started, 3)
        service.repository.save(db, 'runs', run)


def _run(service, db, run_id, scope, step):
    run = service.repository.get(db, 'runs', run_id)
    if run['kind'] != 'discovery':
        raise ValueError('discovery 실행 ID가 필요합니다.')
    frozen = run['frozen_input']
    if ((scope is not None and scope != frozen['scope']) or
            (step is not None and step != frozen['step'])):
        raise ValueError('실행에 고정된 scope/step과 다릅니다.')
    return run


def _metadata(run):
    frozen = run['frozen_input']
    return dict(run_id=run['id'], bundle_id=frozen['bundle_id'], manifest_sha256=frozen['manifest_hash'],
                scope=frozen['scope'], step=frozen['step'])


def catalog(service, run_id, scope=None, step=None):
    with service.repository.connect() as db:
        run = _run(service, db, run_id, scope, step)
        return dict(**_metadata(run), items=[dict(f, **{k: u[k] for k in
                    ('status', 'error', 'parse_run_id', 'block_ids') if k in u})
                    for f, u in zip(run['frozen_input']['files'], run['units'])])


def _blocks(service, db, item, unit):
    if unit['status'] != 'succeeded':
        return []
    blocks = service.parse_blocks(db, unit['parse_run_id'], item['source_version_id'])
    if [b['id'] for b in blocks] != unit['block_ids']:
        raise ValueError('고정된 원문 블록 대응이 일치하지 않습니다.')
    return blocks


def _available(item, block, statuses):
    return all(statuses.get((kind, identifier), {}).get('state', 'allowed') == 'allowed'
               for kind, identifier in [('source_version', item['source_version_id']),
                                         ('evidence', block['evidence_id'])])


def read(service, run_id, file_id, scope=None, step=None, offset=0, limit=20):
    from .snapshots import _statuses
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError('offset은 0 이상, limit은 1~100이어야 합니다.')
    with service.repository.connect() as db:
        run = _run(service, db, run_id, scope, step)
        pair = next(((f, u) for f, u in zip(run['frozen_input']['files'], run['units'])
                     if f['file_id'] == file_id), None)
        if pair is None:
            raise KeyError(file_id)
        item, unit = pair
        if unit['status'] != 'succeeded':
            raise ValueError('해당 파일의 입력 준비가 완료되지 않았습니다.')
        blocks = _blocks(service, db, item, unit)
        statuses = _statuses(db)
        selected = blocks[offset:offset + limit]
        if any(not _available(item, b, statuses) for b in selected):
            raise ValueError('사용 중단 또는 재검토가 필요한 원문입니다.')
        return dict(**_metadata(run), source=item,
                    items=[dict(block_index=offset+i, source_id=item['source_id'], **b)
                           for i, b in enumerate(selected)],
                    next_offset=offset+len(selected) if offset+len(selected) < len(blocks) else None)


def search(service, run_id, query, scope=None, step=None, limit=20):
    from .snapshots import _statuses
    terms = set(re.findall(r'\w+', query.casefold()))
    if not terms or not 1 <= limit <= 50:
        raise ValueError('검색어와 1~50의 limit이 필요합니다.')
    with service.repository.connect() as db:
        run = _run(service, db, run_id, scope, step)
        matches, statuses = [], _statuses(db)
        for item, unit in zip(run['frozen_input']['files'], run['units']):
            for index, block in enumerate(_blocks(service, db, item, unit)):
                if not _available(item, block, statuses):
                    continue
                score = sum(term in block['text'].casefold() for term in terms)
                if score:
                    matches.append(dict(file_id=item['file_id'], title=item['title'], source_id=item['source_id'],
                                        block_index=index, score=score, **block))
                    # ponytail: bounded lexical scan of stored blocks; ranking/indexing is A2.
                    matches.sort(key=lambda m: -m['score'])
                    del matches[limit:]
        return dict(**_metadata(run), query=query, items=matches,
                    incomplete_file_ids=[u['file_id'] for u in run['units'] if u['status'] != 'succeeded'])

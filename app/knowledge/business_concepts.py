"""Reconceptualize selected entities from a fixed stored extraction pool."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import autoschema, business_run
from .service import KnowledgeConflict, encode, utcnow


def plan(service, request):
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', request.parent_run_id)
    if parent.get('kind') != 'business' or parent['status'] in {'queued', 'running', 'cancel_requested'}:
        raise ValueError('종료된 업무 지식 실행의 추출 풀을 선택하세요.')
    targets = {t['id']: t for t in autoschema.concept_targets(parent['graph']) if t['kind'] == 'entity'}
    if not set(request.target_ids) <= targets.keys():
        raise ValueError('현재 그래프의 개체 대상만 선택하세요.')
    return parent, prepare(parent, [targets[i] for i in dict.fromkeys(request.target_ids)], request.neighbor_mode)


def prepare(parent, targets, mode):
    chunks = {c['id']: c for c in parent['chunks']}
    for claim in parent['claims']:
        if claim['chunk_id'] not in chunks:
            ids = {e['block_id'] for e in claim['evidence']}
            blocks = [b for b in parent['blocks'] if b['id'] in ids]
            if not blocks:
                raise ValueError('교정된 대상의 원문 위치를 확인할 수 없습니다.')
            chunks[claim['chunk_id']] = dict(id=claim['chunk_id'], blocks=blocks, text=autoschema.source_text(blocks),
                                           source_version_id=blocks[0]['source_version_id'])
    planned = []
    for target in targets:
        messages, selection = autoschema.concept_messages(target, parent['graph'], chunks, mode)
        planned.append(dict(target=target, messages=messages, selection=selection))
    return planned


def refresh_changed(service, run, changed_ids):
    options = run['recipe']['options']
    targets = [t for t in autoschema.concept_targets(run['graph']) if changed_ids.intersection(t['claim_ids'])
               and not any(c['status'] in {'unreviewed', 'accepted'} and c['target'] == t for c in run['concepts'])]
    for item in prepare(run, targets, options['neighbor_mode']):
        if business_run.cancelled(service, run):
            return
        response = business_run.call(service, run, 'concept_' + item['target']['kind'], item['messages'],
                                     max_tokens=options['concept_tokens'])
        run['concepts'].append(dict(id=uuid4().hex, target=item['target'], selection=item['selection'],
            concepts=autoschema.concepts(response['text']) if response else [],
            status='unreviewed' if response else 'failed', relation='has_concept', approved_is_a=False,
            request_id=run['units'][-1]['id'], refreshed_after_claim_change=True))
        business_run.save(service, run)


def start(service, request):
    parent, planned = plan(service, request)
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('기존 실행 종료 후 개념화를 시작하세요.')
        recipe = deepcopy(parent['recipe']); recipe['options']['neighbor_mode'] = request.neighbor_mode
        run = dict(id=uuid4().hex, kind='business_concept', status='running', parent_run_id=parent['id'],
            input_version_ids=parent['input_version_ids'], recipe=recipe, model_identity=parent['model_identity'],
            graph_fingerprint=autoschema.identifier('graph', parent['graph']), planned=planned, concepts=[], units=[],
            started_at=utcnow(), finished_at=None, metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    begin = monotonic()
    try:
        for item in planned:
            if business_run.cancelled(service, run): break
            response = business_run.call(service, run, 'concept_entity', item['messages'],
                                          max_tokens=recipe['options']['concept_tokens'])
            run['concepts'].append(dict(target=item['target'], selection=item['selection'],
                concepts=autoschema.concepts(response['text']) if response else [],
                status='unreviewed' if response else 'failed', relation='has_concept', approved_is_a=False,
                request_id=run['units'][-1]['id']))
        run['status'] = 'succeeded' if len(run['concepts']) == len(planned) and all(c['status'] != 'failed' for c in run['concepts']) else 'partial'
    except Exception as exc:
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if business_run.cancelled(service, run): run['status'] = 'cancelled'
        run.update(finished_at=utcnow()); run['metrics']['elapsed_s'] = monotonic() - begin
        with service.lock, service.repository.connect() as db:
            service.repository.save(db, 'runs', run)
    return run

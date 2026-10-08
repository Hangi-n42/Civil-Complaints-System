"""Explicit Event text edits, followed by the existing preservation and use path."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import autoschema, business_run, business_use
from .service import KnowledgeConflict, encode, utcnow


def start(service, changeset_id, request):
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('기존 실행 종료 후 편집하세요.')
        change = service.repository.get(db, 'changesets', changeset_id)
        if change.get('kind') != 'source_graph' or change['revision'] != request.expected_revision:
            raise KnowledgeConflict('변경안 버전이 다릅니다. 다시 불러오세요.')
        parent = service.repository.get(db, 'runs', change['run_id'])
        old = next((c for c in parent['claims'] if c['id'] == request.claim_id), None)
        published = next((c for c in change['candidates'] if c['id'] == request.claim_id), None)
        if old is None or old != published or autoschema.identifier('claim', old) != request.expected_claim_version:
            raise KnowledgeConflict('후보 내용이 바뀌었습니다. 다시 불러오세요.')
        if old['role'] != 'event_entity' or old.get('superseded_by') or old.get('extraction_error'):
            raise ValueError('현재는 유효한 Event 문장만 편집합니다. 관계형·Entity 목록·대체된 후보는 지원하지 않습니다.')
        if request.event == old['raw']['Event']:
            raise ValueError('수정한 문장을 입력하세요.')
        if business_use.restricted_sources(db, parent['input_version_ids']):
            raise KnowledgeConflict('사용이 제한된 원문이 있습니다.')
        for requirement in parent['requirements']:
            current = service.repository.get(db, 'requirements', requirement['id'])
            if current['revision'] != requirement['revision'] or current['status'] == 'needs_review':
                raise KnowledgeConflict('요구·원문 변경 이후 재검수가 필요합니다.')
        receipt_id = uuid4().hex
        # User text is not a model-authored Scope. Old annotations remain in before/history.
        patch = dict(target_id=old['id'], meaning_key='user:' + receipt_id, role='event_entity',
            raw=dict(Event=request.event, Entity=deepcopy(old['raw']['Entity'])),
            evidence=[e.model_dump() for e in request.evidence], conditions=[], exceptions=[], period='', references=[])
        after = business_run.materialize_patch(parent, patch, old, receipt_id, parent['blocks'], origin='user')
        run = deepcopy(parent)
        run.update(id=uuid4().hex, parent_run_id=parent['id'], status='queued', started_at=None, finished_at=None,
            units=[], analysis_units=[], reusable_units=deepcopy(parent['units']), parent_recipe=deepcopy(parent['recipe']),
            parent_model_identity=deepcopy(parent['model_identity']), metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            prior_repairs=deepcopy([*parent.get('prior_repairs', []), *parent['repairs']]), repairs=[])
        for key in ('changeset_id', 'error', 'continuation'):
            run.pop(key, None)
        run['claims'] = [after if c['id'] == old['id'] else c for c in run['claims']]
        receipt = dict(id=receipt_id, origin='user', actor=request.actor, reason=request.reason, created_at=utcnow(),
            source_changeset_id=changeset_id, expected_revision=request.expected_revision,
            expected_claim_version=request.expected_claim_version, requirement_id=None, assessment_id=None,
            targets=[dict(meaning_key=patch['meaning_key'], action='user_edit', origin='user',
                claim_ids=[old['id']], fields=['raw.Event'], reason=request.reason, evidence=deepcopy(patch['evidence']))],
            preserve_meanings=[],
            before=deepcopy(parent['claims']), after=deepcopy(run['claims']), patches=dict(patches=[patch], unresolved=[]),
            changes=[dict(before=deepcopy(old), after=deepcopy(after), meaning_key=patch['meaning_key'])],
            errors=[], status='applied_awaiting_recheck')
        run['repairs'].append(receipt)
        run['graph'] = autoschema.graph(run['claims'])
        # Consuming a revision prevents a second edit from silently overwriting this one.
        change['revision'] += 1
        change.setdefault('edit_run_ids', []).append(run['id'])
        service.repository.save(db, 'changesets', change)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    service.executor.submit(recheck, service, run['id'])
    return dict(run_id=run['id'], status='queued', changeset_revision=change['revision'])


def recheck(service, run_id):
    started = monotonic()
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
    run.update(status='running', started_at=utcnow())
    business_run.save(service, run)
    try:
        options = run['recipe']['options']
        run['model_identity'] = business_run.ModelClient(run['recipe']['generation']).identities(
            run['recipe']['models'], dict(draft=options['context_tokens'],
                review=max(options['context_tokens'], options.get('representation_context_tokens') or options['context_tokens'])))
        receipt = run['repairs'][-1]
        reviewed = []
        for requirement in run['requirements']:
            if business_run.cancelled(service, run):
                return
            previous = next((a for a in reversed(run['assessments']) if a['requirement_id'] == requirement['id']), None)
            if previous and previous.get('input_fingerprint') == business_run.assessment_fingerprint(
                    run, requirement, previous['source'], previous.get('review_scope')):
                continue
            assessment = business_run.assess(service, run, requirement,
                source=previous['source'] if previous else None, phase='after_user_edit')
            reviewed.append(assessment)
        receipt['recheck_assessment_ids'] = [a['id'] for a in reviewed]
        receipt['status'] = 'rechecked' if reviewed and all(a['status'] == 'satisfied' for a in reviewed) else 'recheck_incomplete'
        business_run.refresh_repaired_graph(service, run)
        if business_run.cancelled(service, run):
            return
        run['changeset_id'] = business_use.publish(service, run)['id']
        latest = {a['requirement_id']: a for a in run['assessments']}
        run['status'] = 'review_ready' if len(latest) == len(run['requirements']) and all(
            a['status'] == 'satisfied' for a in latest.values()) else 'partial'
    except Exception as exc:
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if business_run.cancelled(service, run):
            run['status'] = 'cancelled'
        run['finished_at'] = utcnow()
        run['metrics']['elapsed_s'] = monotonic() - started
        with service.lock, service.repository.connect() as db:
            service.repository.save(db, 'runs', run)

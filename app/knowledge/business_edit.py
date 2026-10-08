"""Explicit Event text edits, followed by the existing preservation and use path."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import autoschema, business_run, business_use, business_review
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
        if request.event == old['raw']['Event'] and not request.source_edits:
            raise ValueError('수정한 문장을 입력하세요.')
        if request.error_owner == 'source' and request.event != old['raw']['Event']:
            raise ValueError('원문 해석만 정정할 때 후보 문장은 유지해야 합니다.')
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
        after = (business_run.materialize_patch(parent, patch, old, receipt_id, parent['blocks'], origin='user')
                 if request.event != old['raw']['Event'] else deepcopy(old))
        run = deepcopy(parent)
        run.update(id=uuid4().hex, parent_run_id=parent['id'], status='queued', started_at=None, finished_at=None,
            units=[], analysis_units=[], reusable_units=deepcopy(parent['units']), parent_recipe=deepcopy(parent['recipe']),
            parent_model_identity=deepcopy(parent['model_identity']), metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            prior_repairs=deepcopy([*parent.get('prior_repairs', []), *parent['repairs']]), repairs=[])
        for key in ('changeset_id', 'error', 'continuation'):
            run.pop(key, None)
        run['claims'] = [after if c['id'] == old['id'] else c for c in run['claims']]
        run['source_corrections'] = deepcopy(parent.get('source_corrections', []))
        latest = {a['requirement_id']: a for a in parent['assessments']}
        for edit in request.source_edits:
            assessment = latest.get(edit.requirement_id)
            previous = next((m for m in (assessment or {}).get('source', {}).get('meanings', [])
                             if m['key'] == edit.meaning_key), None)
            if previous is None or autoschema.identifier('meaning', previous) != edit.expected_meaning_version:
                raise KnowledgeConflict('원문 해석 버전이 바뀌었습니다. 다시 불러오세요.')
            requirement = next(r for r in run['requirements'] if r['id'] == edit.requirement_id)
            blocks = business_review.source_blocks(run, requirement)
            refs = business_run.exact_evidence([e.model_dump() for e in edit.evidence], blocks)
            if not set(r['block_id'] for r in refs).intersection(r['block_id'] for r in previous['evidence']):
                raise ValueError('기존 원문 해석의 자기 근거가 필요합니다.')
            keys = {m['key'] for m in assessment['source']['meanings']}
            if not set(edit.premise_keys or []) <= keys - {edit.meaning_key}:
                raise ValueError('실제 다른 의미만 연결 전제로 선택하세요.')
            correction = dict(id=uuid4().hex, edit_id=receipt_id, origin='user' if edit.mode == 'replace' else 'user_challenge',
                actor=request.actor, reason=edit.reason, error_owner=request.error_owner,
                requirement_id=edit.requirement_id, requirement_revision=requirement['revision'],
                source_versions=deepcopy(run['input_version_ids']), before=deepcopy(previous), evidence=refs,
                expected_version=edit.expected_meaning_version, fields=list(edit.fields), mode=edit.mode, status='pending')
            if edit.mode == 'replace':
                corrected = dict(deepcopy(previous), **{k: getattr(edit, k) for k in
                    ('statement', 'conditions', 'exceptions', 'period', 'references', 'premise_keys')},
                    evidence=refs, reason=edit.reason, source_status='supported', availability='provided')
                corrected['field_judgments'] = {k: dict(status='supported' if corrected[k] else 'not_applicable',
                    reason=edit.reason, statement_affected=True) for k in ('statement', 'conditions', 'exceptions', 'period', 'references')}
                corrected['field_judgments'].update({k: v.model_dump() for k, v in edit.field_judgments.items()})
                corrected.pop('record_error', None)
                corrected['correction'] = {k: correction[k] for k in ('id', 'origin', 'actor', 'reason', 'expected_version')}
                correction.update(after=corrected, after_version=autoschema.identifier('meaning', corrected),
                                  status='explicit_correction_awaiting_dependent_review')
            run['source_corrections'].append(correction)
        receipt = dict(id=receipt_id, origin='user', actor=request.actor, reason=request.reason, created_at=utcnow(),
            source_changeset_id=changeset_id, expected_revision=request.expected_revision,
            expected_claim_version=request.expected_claim_version, requirement_id=None, assessment_id=None,
            targets=[dict(meaning_key=patch['meaning_key'], action='user_edit', origin='user',
                claim_ids=[old['id']], fields=['raw.Event'], reason=request.reason, evidence=deepcopy(patch['evidence']))],
            preserve_meanings=[],
            before=deepcopy(parent['claims']), after=deepcopy(run['claims']), patches=dict(patches=[patch], unresolved=[]),
            changes=[dict(before=deepcopy(old), after=deepcopy(after), meaning_key=patch['meaning_key'])],
            error_owner=request.error_owner, source_correction_ids=[c['id'] for c in run['source_corrections'] if c['edit_id'] == receipt_id],
            errors=[], status='applied_awaiting_recheck')
        if after == old:
            receipt.update(changes=[], targets=[], patches=dict(patches=[], unresolved=[]))
        run['repairs'].append(receipt)
        # New conditions can matter to a requirement with no old claim edge.
        changed_versions = set(old['source_version_ids']) | {e['source_version_id'] for c in run['source_corrections']
            if c['edit_id'] == receipt_id for e in c['evidence']}
        changed_sources = {b['source_id'] for b in run['blocks'] if b['source_version_id'] in changed_versions}
        known = {r['id'] for r in run['requirements']}
        run['impact_candidates'] = []
        for row in db.execute('SELECT payload FROM requirements'):
            related = json.loads(row['payload'])
            if related['id'] not in known and (not related['source_ids'] or changed_sources.intersection(related['source_ids'])):
                run['impact_candidates'].append(related)
        run['edit_impact'] = dict(changed_claim_ids=[old['id']] if after != old else [],
            source_correction_ids=receipt['source_correction_ids'], related_requirement_ids=[r['id'] for r in run['requirements']],
            candidate_requirement_ids=[r['id'] for r in run['impact_candidates']],
            basis='shared source scope is an impact candidate, not confirmed semantic impact')
        run['preservation_reuses'] = preservation_reuses(parent, run)
        run['graph'] = autoschema.graph(run['claims'])
        # Consuming a revision prevents a second edit from silently overwriting this one.
        change['revision'] += 1
        change.setdefault('edit_run_ids', []).append(run['id'])
        change['invalidated_claim_ids'] = sorted(set(change.get('invalidated_claim_ids', [])) | {old['id']})
        service.repository.save(db, 'changesets', change)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
        for row in db.execute('SELECT id,payload FROM snapshots').fetchall():
            snapshot = json.loads(row['payload'])
            linked = {c['id'] for c in snapshot.get('claims', [])}
            affected_requirements = [rid for rid, a in snapshot.get('assessments', {}).items()
                if old['id'] in a.get('claim_ids', []) or any(c['requirement_id'] == rid
                for c in run['source_corrections'] if c['edit_id'] == receipt_id)]
            if snapshot.get('kind') == 'source_graph' and snapshot.get('run_id') == parent['id'] and (old['id'] in linked or affected_requirements):
                event = dict(id=uuid4().hex, event='business_correction', snapshot_id=snapshot['id'], run_id=run['id'], edit_id=receipt_id,
                    reason='candidate_or_source_interpretation_corrected', claim_ids=[old['id']],
                    requirement_ids=affected_requirements)
                db.execute('INSERT INTO snapshot_events VALUES(?,?)', (event['id'], encode(event)))
    service.executor.submit(recheck, service, run['id'])
    return dict(run_id=run['id'], status='queued', changeset_revision=change['revision'])


def preservation_reuses(parent, run):
    """Reuse a local before/after check, never the requirement's unknown conjunctions."""
    reused = []
    current = {c['id']: c for c in run['claims']}
    latest = {a['requirement_id']: a for a in parent['assessments']}
    changed_versions = {e['source_version_id'] for c in run.get('source_corrections', [])
                        if c['edit_id'] == run['repairs'][-1]['id'] for e in c['evidence']}
    for rid, assessment in latest.items():
        if assessment.get('input_fingerprint') != business_run.assessment_fingerprint(parent,
            next(r for r in parent['requirements'] if r['id'] == rid), assessment['source'], assessment.get('review_scope')):
            continue
        for check in (assessment.get('representation') or {}).get('preservation_checks', []):
            ids = {check['target_id'], *check['after_locations']}
            if check['status'] != 'preserved' or not check['before_normal_meanings'] or not check['after_locations']:
                continue
            old = [c for c in parent['claims'] if c['id'] in ids]
            if len(old) != len(ids) or any(c != current.get(c['id']) for c in old):
                continue
            versions = {v for c in old for v in c['source_version_ids']}
            if changed_versions.intersection(versions):
                continue
            # This only reuses literal preservation of unchanged local content.
            # Cross-source applicability and unknown premises remain in the join.
            reused.append(dict(requirement_id=rid, assessment_id=assessment['id'], check=deepcopy(check),
                claim_versions={c['id']: autoschema.identifier('claim', c) for c in old},
                requirement_revision=assessment['revision'],
                meaning_versions={m['key']: autoschema.identifier('meaning', m)
                    for m in business_review.review_meanings(assessment['source'])
                    if any(e['source_version_id'] in versions for e in m['evidence'])},
                source_versions=sorted(versions), scope='local_preservation_only_not_requirement_independence'))
    return reused


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
        if run.get('impact_candidates'):
            from .business_changes import review_impacts, apply_impacts
            diff = dict(changes=[dict(id=receipt['id'], kind='interpretation_or_candidate',
                changes=receipt['changes'], source_corrections=[c for c in run['source_corrections'] if c['edit_id'] == receipt['id']])], unchanged=[])
            impacts, valid = review_impacts(service, run, run['impact_candidates'], diff, run['sources'], [])
            apply_impacts(service, run, run['impact_candidates'], impacts['items'])
            run['edit_impact'].update(items=impacts['items'], record_valid=valid)
            needs_review = {i['requirement_id'] for i in impacts['items'] if i['status'] != 'unaffected'}
            run['edit_impact']['pending_requirement_ids'] = sorted(needs_review)
            # Existing change workflow marks related requirements stale. It does
            # not turn a small edit into extraction/review of every stored task.
        reviewed = []
        for requirement in run['requirements']:
            if business_run.cancelled(service, run):
                return
            previous = next((a for a in reversed(run['assessments']) if a['requirement_id'] == requirement['id']), None)
            pending_correction = any(c['requirement_id'] == requirement['id'] and c['edit_id'] == receipt['id']
                                     for c in run.get('source_corrections', []))
            if not pending_correction and previous and previous.get('input_fingerprint') == business_run.assessment_fingerprint(
                    run, requirement, previous['source'], previous.get('review_scope')):
                continue
            source = deepcopy(previous['source']) if previous else None
            corrections = [c for c in run.get('source_corrections', []) if c['requirement_id'] == requirement['id']]
            if source:
                for correction in corrections:
                    if correction['mode'] == 'reassess' and correction['status'] == 'pending':
                        challenge = dict(meaning_key=correction['before']['key'], fields=correction.get('fields',
                            ['statement', 'conditions', 'exceptions', 'period', 'references', 'premise_keys']),
                            reason=correction['reason'], evidence=correction['evidence'], error_owner=correction['error_owner'])
                        updated = business_review.reassess_source(service, run, requirement,
                            dict(previous, source=source), [challenge])
                        correction.update(status='model_reassessed' if updated else 'model_reassessment_failed',
                            model_unit_id=run['units'][-1]['id'] if run['units'] else None)
                        if updated:
                            source = updated
                            correction['after'] = deepcopy(next(m for m in source['meanings'] if m['key'] == correction['before']['key']))
                            correction['after_version'] = autoschema.identifier('meaning', correction['after'])
                source = business_run.apply_source_corrections(run, requirement, source)
                changed_keys = {c['before']['key'] for c in corrections if c['edit_id'] == receipt['id']}
                if changed_keys:
                    facts = dict(source, meanings=[m for m in source['meanings'] if m['key'] in changed_keys],
                                 application_history=[], application_challenges=[])
                    blocks = business_review.related_blocks(run, facts['meanings'])
                    applied = business_review.apply_requirement(service, run, requirement, facts,
                        blocks)
                    application = applied.get('application_history', [])[-1:]
                    if application and application[0]['output'] is not None and any(isinstance(error, dict) and error.get('reason') ==
                            'requirement_application_missing_or_duplicate' for error in application[0]['errors']):
                        # One bounded protocol completion, never infer omitted
                        # cells or regenerate successful applicability judgments.
                        applied = business_review.apply_requirement(service, run, requirement, applied, blocks,
                            resume=dict(run_id=run['id'], unit=deepcopy(run['units'][-1]), receipt=application[0]))
                    replacements = {m['key']: m for m in applied['meanings']}
                    source['meanings'] = [replacements.get(m['key'], m) for m in source['meanings']]
                    source.setdefault('application_history', []).extend(applied.get('application_history', []))
                    source['application_challenges'] = [c for c in source.get('application_challenges', [])
                        if c['meaning_key'] not in changed_keys] + applied.get('application_challenges', [])
            assessment = business_run.assess(service, run, requirement, source=source, phase='after_user_edit')
            assessment = business_run.reassess_challenges(service, run, requirement, assessment)
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

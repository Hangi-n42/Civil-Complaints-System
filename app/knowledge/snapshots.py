"""Immutable reviewed selections and a separate, current availability ledger."""
from copy import deepcopy
from datetime import date
import csv
import io
import json
from uuid import uuid4

from . import extraction_store as store, ontology_schema, ontology_consumer as consumer
from .schemas import ActivateSnapshotRequest, AvailabilityRequest, SnapshotRequest
from .service import encode, utcnow


def _state(db):
    return dict(db.execute('SELECT active_snapshot_id,status_revision FROM knowledge_state WHERE id=1').fetchone())


def _statuses(db):
    # ponytail: scan the small local history; index latest rows if the pilot grows.
    return {(row['target_type'], row['target_id']): json.loads(row['payload'])
            for row in db.execute('SELECT * FROM availability_history ORDER BY status_revision')}


def _write_status(db, targets, state, actor, reason):
    revision = _state(db)['status_revision'] + 1
    now = utcnow()
    for kind, identifier in sorted(set(targets)):
        value = dict(id=uuid4().hex, type=kind, target_id=identifier, state=state,
                     status_revision=revision, actor=actor, reason=reason, recorded_at=now)
        db.execute('INSERT INTO availability_history VALUES(?,?,?,?,?)',
                   (value['id'], revision, kind, identifier, encode(value)))
    db.execute('UPDATE knowledge_state SET status_revision=? WHERE id=1', (revision,))
    return revision


def mark_changed(db, assertion_ids, actor, reason):
    """Called inside the existing review transaction; never relax a block."""
    statuses = _statuses(db)
    targets = [('assertion', identifier) for identifier in set(assertion_ids)
               if statuses.get(('assertion', identifier), {}).get('state', 'allowed') == 'allowed']
    if targets:
        _write_status(db, targets, 'needs_review', actor, reason)


def availability(service, kind, identifier):
    with service.lock, service.repository.connect() as db:
        _target_exists(service.repository, db, kind, identifier)
        history = [json.loads(row['payload']) for row in db.execute(
            'SELECT payload FROM availability_history WHERE target_type=? AND target_id=? ORDER BY status_revision DESC',
            (kind, identifier))]
        return dict(type=kind, target_id=identifier, state=history[0]['state'] if history else 'allowed',
                    history=history, **_state(db))


def _target_exists(repo, db, kind, identifier):
    table = {'assertion': 'assertions', 'evidence': 'evidence', 'source_version': 'versions'}.get(kind)
    if not table:
        raise ValueError('지원하지 않는 사용 상태 대상입니다.')
    if store._optional(repo, db, table, identifier) is None:
        raise KeyError(identifier)


def set_availability(service, request):
    request = AvailabilityRequest.model_validate(request)
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if _state(db)['status_revision'] != request.expected_status_revision:
            raise ontology_schema.VersionConflict('사용 상태가 변경되었습니다. 다시 조회해 주세요.')
        targets = [(t.type, t.id) for t in request.targets]
        if len(set(targets)) != len(targets):
            raise ValueError('같은 상태 대상을 중복 지정할 수 없습니다.')
        for kind, identifier in targets:
            _target_exists(service.repository, db, kind, identifier)
        revision = _write_status(db, targets, request.state, request.actor, request.reason)
        return dict(status_revision=revision, status_checked_at=utcnow())


def _evidence_ids(candidate):
    fields, dates = candidate.get('field_evidence'), candidate.get('dates')
    groups = [candidate.get('evidence_ids'), candidate.get('dependency_evidence_ids')]
    if isinstance(fields, dict):
        groups.extend(fields.values())
    if isinstance(dates, list):
        groups.extend(d.get('evidence_ids') for d in dates if isinstance(d, dict))
    return {i for group in groups if isinstance(group, list) for i in group if isinstance(i, str)}


def current_restrictions(repo, db, candidate, statuses=None):
    """Availability annotations for the existing review screen (not persisted)."""
    statuses = _statuses(db) if statuses is None else statuses
    ids = _evidence_ids(candidate)
    ontology = store._optional(repo, db, 'ontology_versions', candidate.get('ontology_version_id'))
    if ontology and ontology.get('payload_version') == 2:
        ids.update(consumer.evidence_ids(ontology))
    links = [candidate] if candidate.get('kind') == 'entity_link' else []
    for key in ('subject_link_id', 'object_link_id'):
        link = store._optional(repo, db, 'entity_links', candidate.get(key))
        if link:
            links.append(link)
    for link in links:
        ids.update(_evidence_ids(link))
        entity = store._optional(repo, db, 'entities', link.get('target_entity_id')) or {}
        ids.update(entity.get('evidence_ids', []))
    targets = {('assertion', candidate['id'])} if candidate.get('kind') == 'assertion' else set()
    for identifier in ids:
        targets.add(('evidence', identifier))
        ev = store._optional(repo, db, 'evidence', identifier) or {}
        block = store._optional(repo, db, 'blocks', ev.get('block_id')) or {}
        if block.get('source_version_id'):
            targets.add(('source_version', block['source_version_id']))
    return [dict(type=kind, id=identifier, state=statuses[kind, identifier]['state'])
            for kind, identifier in sorted(targets) if statuses.get((kind, identifier), {}).get('state', 'allowed') != 'allowed']


def _targets(snapshot, candidate):
    ids = _evidence_ids(candidate)
    ids.update(snapshot.get('ontology_dependency_evidence_ids', []))
    links = [candidate] if candidate['kind'] == 'entity_link' else []
    for key in ('subject_link_id', 'object_link_id'):
        if candidate.get(key):
            links.append(snapshot['links'][candidate[key]])
    for link in links:
        ids.update(_evidence_ids(link))
        ids.update(snapshot['entities'][link['target_entity_id']].get('evidence_ids', []))
    targets = {('assertion', candidate['id'])} if candidate['kind'] == 'assertion' else set()
    for identifier in ids:
        ev = snapshot['evidence'][identifier]
        targets.add(('evidence', identifier))
        targets.add(('source_version', ev['source_version_id']))
    return targets


def _blocked(snapshot, candidate, statuses):
    return [dict(type=kind, id=identifier, state=statuses[kind, identifier]['state'])
            for kind, identifier in sorted(_targets(snapshot, candidate))
            if statuses.get((kind, identifier), {}).get('state', 'allowed') != 'allowed']


def _capture_evidence(repo, db, identifier):
    ev = store._optional(repo, db, 'evidence', identifier)
    if ev is None:
        raise ValueError('없는 근거: ' + identifier)
    block = repo.get(db, 'blocks', ev['block_id'])
    start, end = ev.get('start_char'), ev.get('end_char')
    if (ev.get('alignment_status') != 'matched' or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(block['text']) or block['text'][start:end] != ev['quote']):
        raise ValueError('원문과 일치하지 않는 근거: ' + identifier)
    return dict(ev, source_version_id=block['source_version_id'], parse_run_id=block.get('parse_run_id'),
                locator=block.get('locator', {}))


def _integrity(snapshot):
    """Check frozen references, never rebuild an old snapshot from live candidates."""
    contract = snapshot.get('consumer_contract', {})
    definitions = {c['id']: c for c in consumer.definitions(snapshot['ontology'], contract)}
    for candidate in [*snapshot['links'].values(), *snapshot['assertions'].values()]:
        if candidate['review_status'] != 'accepted' or candidate.get('validation_errors'):
            raise ValueError('수락되지 않은 스냅샷 항목입니다.')
        if candidate['kind'] == 'entity_link':
            entity = snapshot['entities'].get(candidate['target_entity_id'])
            if not entity or consumer.entity_type(entity, contract) != candidate['concept_id'] or candidate['concept_id'] not in definitions:
                raise ValueError('개체 참조가 일치하지 않습니다.')
        else:
            definition = definitions.get(candidate['predicate_id'], {})
            for role in ('subject', 'object'):
                link_id = candidate.get(role + '_link_id')
                if role == 'object' and definition.get('kind') != 'relation':
                    continue
                link = snapshot['links'].get(link_id)
                resolved = candidate.get('subject_id' if role == 'subject' else 'object_entity_id')
                if not link or not consumer.permits(definition, link['concept_id'], role) or link['target_entity_id'] != resolved:
                    raise ValueError('선택한 주장의 연결 참조가 일치하지 않습니다: ' + str(link_id))
                if {'link_id': link_id, 'revision': link['revision']} not in candidate.get('link_dependencies', []):
                    raise ValueError('검토 당시 연결 버전이 아닙니다: ' + str(link_id))
        if not _evidence_ids(candidate) or not _evidence_ids(candidate) <= snapshot['evidence'].keys():
            raise ValueError('스냅샷 근거 참조가 없습니다.')
    for ev in snapshot['evidence'].values():
        if ev['source_version_id'] not in snapshot['versions']:
            raise ValueError('스냅샷 원문 버전이 없습니다.')
    if snapshot['ontology'].get('payload_version') == 2:
        dependencies = set(snapshot.get('ontology_dependency_evidence_ids', []))
        if dependencies != consumer.evidence_ids(snapshot['ontology']) or not dependencies <= snapshot['evidence'].keys():
            raise ValueError('스냅샷 온톨로지의 파생 근거가 없습니다.')
        for entity in snapshot['entities'].values():
            kind = consumer.entity_type(entity, contract)
            required = {d['id'] for d in definitions.values() if d['kind'] in {'attribute','relation'} and
                        kind in d.get('required_domain_ids', [kind] if d.get('required') and consumer.permits(d, kind) else [])}
            present = {a['predicate_id'] for a in snapshot['assertions'].values() if a.get('subject_id')==entity['id']}
            if required - present:
                raise ValueError('선택 개체의 필수 속성·관계가 없습니다: '+entity['id']+': '+', '.join(sorted(required-present)))


def create(service, request):
    request = SnapshotRequest.model_validate(request)
    repo = service.repository
    with service.lock, repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state = _state(db)
        if state['active_snapshot_id'] != request.expected_active_id:
            raise ontology_schema.VersionConflict('활성 버전이 변경되었습니다.')
        snapshot = dict(id=uuid4().hex, parent_id=state['active_snapshot_id'], created_at=utcnow(),
                        actor=request.actor, reason=request.reason, selections=[], links={}, assertions={},
                        entities={}, evidence={}, versions={}, sources={}, run_scopes=[])
        seen_changes, seen_candidates = set(), set()
        ontology = None
        for selection in request.selections:
            if selection.changeset_id in seen_changes or len(selection.candidate_ids) != len(set(selection.candidate_ids)):
                raise ValueError('묶음 또는 후보를 중복 선택했습니다.')
            seen_changes.add(selection.changeset_id)
            change = repo.get(db, 'changesets', selection.changeset_id)
            if change['revision'] != selection.expected_changeset_revision:
                raise ontology_schema.VersionConflict('선택 후보가 변경되었습니다. 다시 조회해 주세요.')
            if change.get('kind') != 'extraction' or not set(selection.candidate_ids) <= set(change['candidate_ids']):
                raise ValueError('추출 묶음에 속한 후보만 선택하세요.')
            run = repo.get(db, 'runs', change['run_id'])
            version = repo.get(db, 'ontology_versions', run['ontology_version_id'])
            if version.get('status') != 'reviewed' or (ontology and ontology['id'] != version['id']):
                raise ValueError('동일한 검토된 온톨로지의 후보만 함께 선택하세요.')
            ontology = version
            contract = run.get('consumer_contract', {})
            if 'consumer_contract' in snapshot and snapshot['consumer_contract'] != contract:
                raise ValueError('동일한 소비 계약의 후보만 함께 선택하세요.')
            snapshot['consumer_contract'] = deepcopy(contract)
            snapshot['run_scopes'].append(dict(run_id=run['id'], changeset_id=change['id'],
                predicate_ids=deepcopy(run.get('predicate_ids')),
                block_ids=sorted({b for u in run.get('units', []) for b in u.get('block_ids', [])}
                                 if run.get('units') else {b['id'] for b in run['frozen_blocks']})))
            schema = store._schema(repo, db, run)
            items = {c['id']: c for c in store._items(repo, db, change)}
            for identifier in selection.candidate_ids:
                candidate = items[identifier]
                if identifier in seen_candidates or candidate['review_status'] != 'accepted' or candidate.get('validation_errors'):
                    raise ValueError('중복 또는 미수락 후보입니다: ' + identifier)
                seen_candidates.add(identifier)
                if candidate['ontology_version_id'] != ontology['id']:
                    raise ValueError('후보 온톨로지 버전이 다릅니다.')
                if candidate['kind'] == 'entity_link':
                    errors = store._link_errors(repo, db, candidate, run, schema)
                    snapshot['links'][identifier] = candidate
                else:
                    checked = deepcopy(candidate)
                    errors = store._assertion_errors(repo, db, checked, run, schema, require_accepted=True)
                    if any(checked.get(key) != candidate.get(key) for key in ('subject_id', 'object_entity_id', 'link_dependencies')):
                        errors.append('accepted_link_revision_changed')
                    errors.extend(candidate.get('extraction_errors', []))
                    snapshot['assertions'][identifier] = candidate
                if errors:
                    raise ValueError(identifier + ': ' + ', '.join(errors))
            snapshot['selections'].append(selection.model_dump())
        snapshot['ontology'] = ontology
        snapshot['ontology_version_id'] = ontology['id']
        evidence_ids = set()
        for link in snapshot['links'].values():
            entity = repo.get(db, 'entities', link['target_entity_id'])
            snapshot['entities'][entity['id']] = entity
            evidence_ids.update(entity.get('evidence_ids', []))
        for candidate in [*snapshot['links'].values(), *snapshot['assertions'].values()]:
            evidence_ids.update(_evidence_ids(candidate))
        # Preserve schema provenance too, without treating its design text as factual evidence.
        if ontology.get('payload_version') == 2:
            snapshot['ontology_dependency_evidence_ids'] = sorted(consumer.evidence_ids(ontology))
            evidence_ids.update(snapshot['ontology_dependency_evidence_ids'])
        else:
            for definition in consumer.definitions(ontology):
                evidence_ids.update(e['evidence_id'] for e in definition.get('evidence', []))
        for identifier in sorted(evidence_ids):
            ev = _capture_evidence(repo, db, identifier)
            snapshot['evidence'][identifier] = ev
            version = repo.get(db, 'versions', ev['source_version_id'])
            snapshot['versions'][version['id']] = version
            source = repo.get(db, 'sources', version['source_id'])
            snapshot['sources'][source['id']] = source
        _integrity(snapshot)
        statuses = _statuses(db)
        unavailable = [c['id'] for c in [*snapshot['links'].values(), *snapshot['assertions'].values()]
                       if _blocked(snapshot, c, statuses)]
        if unavailable:
            raise ValueError('사용 불가 항목을 선택에서 제외하세요: ' + ', '.join(unavailable))
        snapshot['counts'] = dict(entities=len(snapshot['entities']), links=len(snapshot['links']),
                                  assertions=len(snapshot['assertions']))
        db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], encode(snapshot)))
        return dict(snapshot_id=snapshot['id'], parent_id=snapshot['parent_id'], counts=snapshot['counts'])


def list_snapshots(service):
    with service.lock, service.repository.connect() as db:
        items = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM snapshots ORDER BY rowid DESC')]
        events = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM snapshot_events ORDER BY rowid DESC')]
        return dict(**_state(db), items=[{k: s[k] for k in ('id', 'parent_id', 'created_at', 'actor', 'reason', 'counts')}
                                        for s in items], events=events)


def _validity(assertion, as_of):
    try:
        bounds = store.validity_bounds(assertion)
    except (ValueError, TypeError, KeyError):
        return 'unverified', True
    if not as_of or not bounds:
        return 'unverified', True
    return 'verified_for_selected_scope', (not bounds.get('valid_from') or bounds['valid_from'] <= as_of) and (
        not bounds.get('valid_to') or as_of <= bounds['valid_to'])


def _view(snapshot, statuses, state, entity_id=None, as_of=None):
    assertions, excluded = [], []
    for candidate in snapshot['assertions'].values():
        if entity_id and entity_id not in (candidate['subject_id'], candidate.get('object_entity_id')):
            continue
        blocked = _blocked(snapshot, candidate, statuses)
        validity, in_period = _validity(candidate, as_of)
        if blocked or not in_period:
            excluded.append(dict(id=candidate['id'], reasons=blocked or [{'state': 'outside_validity_period'}]))
        else:
            assertions.append(dict(candidate, validity_status=validity))
    link_ids = {a[k] for a in assertions for k in ('subject_link_id', 'object_link_id') if a.get(k)}
    # Explicitly selected standalone links are useful even without a surviving assertion.
    links = [link for link in snapshot['links'].values() if not _blocked(snapshot, link, statuses)
             and (not entity_id or link['target_entity_id'] == entity_id or link['id'] in link_ids)]
    entity_ids = {link['target_entity_id'] for link in links}
    evidence_ids = set().union(*(_evidence_ids(c) for c in [*assertions, *links]))
    for identifier in entity_ids:
        evidence_ids.update(snapshot['entities'][identifier].get('evidence_ids', []))
    evidence = [{k: v for k, v in snapshot['evidence'][i].items() if k != 'quote'} for i in sorted(evidence_ids)]
    version_ids = {ev['source_version_id'] for ev in evidence}
    source_ids = {snapshot['versions'][i]['source_id'] for i in version_ids}
    return dict(snapshot_id=snapshot['id'], parent_id=snapshot['parent_id'], **state, status_checked_at=utcnow(),
                ontology_version_id=snapshot['ontology_version_id'], selections=snapshot['selections'],
                consumer_contract=snapshot.get('consumer_contract', {}),
                ontology_dependency_evidence_ids=snapshot.get('ontology_dependency_evidence_ids', []),
                vocabulary_registry=snapshot['ontology'].get('vocabulary_registry', {}),
                run_scopes=snapshot.get('run_scopes', []),
                definitions=[{k: c.get(k) for k in ('id', 'kind', 'name', 'definition', 'range', 'aliases')}
                             for c in consumer.definitions(snapshot['ontology'], snapshot.get('consumer_contract'))],
                entities=[snapshot['entities'][i] for i in sorted(entity_ids)], links=links, assertions=assertions,
                evidence=evidence, sources=[snapshot['sources'][i] for i in sorted(source_ids)],
                versions=[{k: v for k, v in snapshot['versions'][i].items() if k != 'relative_raw_path'} for i in sorted(version_ids)],
                counts=dict(entities=len(entity_ids), links=len(links), assertions=len(assertions), excluded=len(excluded)),
                coverage=dict(selected_assertion_count=len(snapshot['assertions']), returned_assertion_count=len(assertions),
                              entity_id=entity_id, as_of=as_of, excluded=excluded, partial=bool(excluded)),
                validity_status='unverified' if any(a['validity_status'] == 'unverified' for a in assertions) or not assertions else 'verified_for_selected_scope')


def get_snapshot(service, snapshot_id=None, entity_id=None, as_of=None):
    if as_of:
        as_of = date.fromisoformat(str(as_of)).isoformat()
    with service.lock, service.repository.connect() as db:
        state = _state(db)
        identifier = snapshot_id or state['active_snapshot_id']
        if not identifier:
            return dict(snapshot_id=None, **state, entities=[], links=[], assertions=[], evidence=[], sources=[], versions=[],
                        counts=dict(entities=0, links=0, assertions=0, excluded=0), coverage=dict(excluded=[], partial=False),
                        status_checked_at=utcnow(), validity_status='unverified')
        snapshot = service.repository.get(db, 'snapshots', identifier)
        view = _view(snapshot, _statuses(db), state, entity_id, as_of)
        latest = _state(db)
        if latest['status_revision'] != state['status_revision']:
            view = _view(snapshot, _statuses(db), latest, entity_id, as_of)
        return view


def activate(service, snapshot_id, request):
    request = ActivateSnapshotRequest.model_validate(request)
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state = _state(db)
        if state['active_snapshot_id'] != request.expected_active_id:
            raise ontology_schema.VersionConflict('활성 버전이 변경되었습니다. 다시 비교해 주세요.')
        snapshot = service.repository.get(db, 'snapshots', snapshot_id)
        _integrity(snapshot)
        event = dict(id=uuid4().hex, before_id=state['active_snapshot_id'], after_id=snapshot_id,
                     actor=request.actor, reason=request.reason, created_at=utcnow())
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', (event['id'], encode(event)))
        db.execute('UPDATE knowledge_state SET active_snapshot_id=? WHERE id=1', (snapshot_id,))
        view = _view(snapshot, _statuses(db), _state(db))
        return {k: view[k] for k in ('active_snapshot_id', 'status_revision', 'status_checked_at', 'counts')}


def export(service, snapshot_id=None, format='json', entity_id=None, as_of=None):
    with service.lock:
        if format not in {'json', 'csv'}:
            raise ValueError('json 또는 csv 형식만 지원합니다.')
        view = get_snapshot(service, snapshot_id, entity_id, as_of)
        if format == 'json':
            return dict(format='json', **view)
        output = io.StringIO(newline='')
        fields = ['snapshot_id', 'status_revision', 'id', 'revision', 'subject_id', 'predicate_id', 'object_entity_id',
                  'value', 'unit', 'scope', 'conditions', 'exceptions', 'dates', 'evidence_ids', 'evidence', 'validity_status']
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for assertion in view['assertions']:
            row = dict(assertion, snapshot_id=view['snapshot_id'], status_revision=view['status_revision'])
            row['evidence'] = [dict(ev, source_id=next(v['source_id'] for v in view['versions'] if v['id'] == ev['source_version_id']))
                               for ev in view['evidence'] if ev['id'] in assertion['evidence_ids']]
            values = {k: encode(row[k]) if isinstance(row.get(k), (dict, list)) else row.get(k) for k in fields}
            # Literal document text must not become a spreadsheet formula.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v
                             for k, v in values.items()})
        return dict(format='csv', content=output.getvalue(), snapshot_id=view['snapshot_id'],
                    status_revision=view['status_revision'], status_checked_at=view['status_checked_at'], coverage=view['coverage'])

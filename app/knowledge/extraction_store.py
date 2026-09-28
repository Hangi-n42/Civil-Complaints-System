"""K4 candidate ledger and direct human decisions; no active graph or propagation engine."""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import re
from uuid import uuid4

from .ontology_schema import VersionConflict, _from_schema, _now
from .schemas import DecisionRequest

LINK_FIELDS = {'target_entity_id', 'scope', 'mention', 'evidence_ids'}
ASSERTION_FIELDS = {'value', 'raw_value', 'unit', 'scope', 'conditions', 'exceptions', 'dates',
                    'evidence_ids', 'field_evidence', 'subject_link_id', 'object_link_id'}


def _encode(value):
    return json.dumps(value, ensure_ascii=False)


def evidence_id(block_id, quote, start_char, end_char, alignment_status):
    key = [block_id, start_char, end_char] if alignment_status == 'matched' else [block_id, quote, alignment_status]
    return sha256(_encode(key).encode()).hexdigest()[:32]


def _all(db, table):
    return [json.loads(row['payload']) for row in db.execute(f'SELECT payload FROM {table}')]


def _optional(repo, db, table, identifier):
    if not identifier:
        return None
    try:
        return repo.get(db, table, identifier)
    except KeyError:
        if table == 'evidence':
            block = _optional(repo, db, 'blocks', identifier)
            if block:
                return dict(id=identifier, block_id=block['id'], quote=block['text'], start_char=0,
                            end_char=len(block['text']), alignment_status='matched')
        return None


def _schema(repo, db, run):
    return {c['id']: c for c in _from_schema(repo.get(db, 'ontology_versions', run['ontology_version_id'])['linkml_yaml'])}


def _evidence_errors(repo, db, ids, run):
    blocks = {b['id']: b for b in run['frozen_blocks']}
    errors = []
    if not ids:
        return ['evidence_required']
    for identifier in ids:
        ev = _optional(repo, db, 'evidence', identifier)
        if not ev or ev.get('block_id') not in blocks:
            errors.append('evidence_not_in_frozen_input')
            continue
        start, end = ev.get('start_char'), ev.get('end_char')
        if ev.get('alignment_status') != 'matched' or type(start) is not int or type(end) is not int:
            errors.append('evidence_alignment_unresolved')
        elif not (0 <= start < end <= len(blocks[ev['block_id']]['text'])) or blocks[ev['block_id']]['text'][start:end] != ev['quote']:
            errors.append('evidence_quote_mismatch')
    return list(dict.fromkeys(errors))


def _link_errors(repo, db, link, run, schema):
    errors = _evidence_errors(repo, db, link.get('evidence_ids', []), run)
    concept = schema.get(link.get('concept_id'), {})
    if concept.get('kind') != 'concept':
        errors.append('unknown_concept')
    entity = _optional(repo, db, 'entities', link.get('target_entity_id'))
    if not entity:
        errors.append('entity_unresolved')
    elif entity.get('concept_id') != link.get('concept_id'):
        errors.append('entity_type_mismatch')
    if entity and link.get('method') == 'official_id':
        quoted = ' '.join(((_optional(repo, db, 'evidence', identifier) or {}).get('quote', ''))
                          for identifier in link.get('evidence_ids', []))
        code = str(entity.get('official_id') or '')
        if not code or not re.search(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?![A-Za-z0-9])', quoted):
            errors.append('official_id_not_in_evidence')
    elif link.get('method') != 'official_id':
        mention = link.get('mention')
        mention = re.sub(r'\s+', '', mention) if isinstance(mention, str) else ''
        quotes = [(_optional(repo, db, 'evidence', identifier) or {}).get('quote', '')
                  for identifier in link.get('evidence_ids', [])]
        if not mention or not any(mention in re.sub(r'\s+', '', quote) for quote in quotes):
            errors.append('mention_not_in_evidence')
    if not isinstance(link.get('scope'), dict):
        errors.append('invalid_scope')
    return list(dict.fromkeys(errors))


def _scalar_valid(value, range_name):
    if range_name == 'integer':
        return type(value) is int
    if range_name in {'float', 'double'}:
        return type(value) in {int, float}
    if range_name == 'boolean':
        return type(value) is bool
    if not isinstance(value, str):
        return False
    try:
        if range_name == 'date':
            return date.fromisoformat(value).isoformat() == value
        if range_name == 'datetime':
            datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _assertion_errors(repo, db, assertion, run, schema, require_accepted=False):
    errors = _evidence_errors(repo, db, assertion.get('evidence_ids', []), run)
    predicate = schema.get(assertion.get('predicate_id'), {})
    if predicate.get('kind') not in {'attribute', 'relation'}:
        errors.append('unknown_predicate')
    dependencies = []
    for role in ('subject', 'object'):
        identifier = assertion.get(role + '_link_id')
        if role == 'object' and predicate.get('kind') != 'relation':
            if identifier:
                errors.append('attribute_has_object')
            continue
        link = _optional(repo, db, 'entity_links', identifier)
        if not link:
            errors.append(role + '_link_missing')
            continue
        if link.get('run_id') != run['id']:
            errors.append(role + '_link_not_in_run')
        entity = _optional(repo, db, 'entities', link.get('target_entity_id'))
        expected = predicate.get('domain_id' if role == 'subject' else 'range')
        if not entity or entity.get('concept_id') != expected:
            errors.append(role + '_type_or_target_unresolved')
        if require_accepted and link.get('review_status') != 'accepted':
            errors.append(role + '_link_not_accepted')
        if _link_errors(repo, db, link, run, schema):
            errors.append(role + '_link_invalid')
        dependencies.append(dict(link_id=link['id'], revision=link['revision']))
        # Subject/object IDs change only when explicitly accepting the assertion.
        if require_accepted:
            assertion['subject_id' if role == 'subject' else 'object_entity_id'] = link.get('target_entity_id')
    if predicate.get('kind') == 'relation':
        if assertion.get('value') is not None:
            errors.append('relation_has_literal_value')
    else:
        value = assertion.get('value')
        values = value if predicate.get('multivalued') and isinstance(value, list) else [value]
        if predicate.get('multivalued') != isinstance(value, list) or not all(_scalar_valid(v, predicate.get('range', 'string')) for v in values):
            errors.append('literal_type_mismatch')
        if predicate.get('enum_values') and any(v not in predicate['enum_values'] for v in values):
            errors.append('literal_not_in_enum')
    field_evidence = assertion.get('field_evidence', {})
    expected_field = 'object' if predicate.get('kind') == 'relation' else 'value'
    if not isinstance(field_evidence, dict) or not field_evidence.get(expected_field):
        errors.append('field_evidence_required')
    elif any(not isinstance(ids, list) or not set(ids) <= set(assertion.get('evidence_ids', [])) for ids in field_evidence.values()):
        errors.append('field_evidence_not_in_evidence_ids')
    if isinstance(field_evidence, dict):
        for key in ('conditions', 'exceptions'):
            if assertion.get(key) and not field_evidence.get(key):
                errors.append(key + '_evidence_required')
        raw = assertion.get('raw_value')
        value_ids = field_evidence.get('value', [])
        if predicate.get('kind') == 'attribute' and type(raw) in {str, int, float} and isinstance(value_ids, list):
            quotes = [(_optional(repo, db, 'evidence', identifier) or {}).get('quote', '')
                      for identifier in value_ids if isinstance(identifier, str)]
            # Literal presence only: this does not prove the slot, unit or scope is correct.
            if not str(raw).strip() or not any(str(raw) in quote for quote in quotes):
                errors.append('raw_value_not_in_value_evidence')
    if not isinstance(assertion.get('scope'), dict):
        errors.append('invalid_scope')
    for key in ('conditions', 'exceptions'):
        if not isinstance(assertion.get(key), list) or any(not isinstance(v, str) for v in assertion[key]):
            errors.append('invalid_' + key)
    if not isinstance(assertion.get('dates'), list) or any(not isinstance(d, dict) for d in assertion['dates']):
        errors.append('invalid_dates')
    else:
        month_slot = assertion.get('predicate_id') in {'ATTRIBUTE_007', 'FirstOccupancyMonth'}
        value = assertion.get('value')
        if month_slot:
            match = re.fullmatch(r'(\d{4})-(\d{2})', value) if isinstance(value, str) else None
            try:
                if not match:
                    raise ValueError('invalid month')
                date(int(match[1]), int(match[2]), 1)
            except ValueError:
                errors.append('month_value_invalid')
            raw_month = re.fullmatch(r'(\d{4})[.-]?(\d{2})', str(assertion.get('raw_value', '')).strip())
            if raw_month and value != f'{raw_month[1]}-{raw_month[2]}':
                errors.append('month_normalization_mismatch')
        if month_slot or predicate.get('range') == 'date':
            precision = 'month' if month_slot else 'day'
            if not assertion['dates'] or any(d.get('value') != value or d.get('precision') != precision for d in assertion['dates']):
                errors.append('date_metadata_mismatch')
    if require_accepted:
        assertion['link_dependencies'] = dependencies
    return list(dict.fromkeys(errors))


def publish_unit(service, run, unit, links, assertions, evidence, entities):
    repo = service.repository
    with service.lock, repo.connect() as db:
        schema = _schema(repo, db, run)
        row = db.execute("SELECT payload FROM changesets WHERE json_extract(payload,'$.kind')='extraction' AND json_extract(payload,'$.run_id')=?", (run['id'],)).fetchone()
        change = json.loads(row['payload']) if row else dict(id=uuid4().hex, kind='extraction', run_id=run['id'],
            ontology_version_id=run['ontology_version_id'], revision=0, created_at=_now(), candidate_ids=[], published_unit_ids=[])
        if unit['id'] in change['published_unit_ids']:
            return _publish_result(repo, db, change)
        for entity in entities:
            prior = _optional(repo, db, 'entities', entity['id'])
            if prior:
                if (prior['namespace'], prior.get('official_id'), prior['concept_id']) != (entity['namespace'], entity.get('official_id'), entity['concept_id']):
                    raise ValueError('기존 개체 ID와 다른 식별 정보를 저장할 수 없습니다.')
                continue
            if schema.get(entity['concept_id'], {}).get('kind') != 'concept':
                raise ValueError('등록 개체의 concept_id가 검토된 스키마에 없습니다.')
            db.execute('INSERT INTO entities VALUES(?,?,?,?)', (entity['id'], entity['namespace'], entity.get('official_id'), _encode(entity)))
        for ev in evidence:
            db.execute('INSERT OR IGNORE INTO evidence VALUES(?,?)', (ev['id'], _encode(ev)))
        for table, items, kind in (('entity_links', links, 'entity_link'), ('assertions', assertions, 'assertion')):
            for original in items:
                value = deepcopy(original)
                value.update(kind=kind, run_id=run['id'], unit_id=unit['id'], changeset_id=change['id'],
                             ontology_version_id=run['ontology_version_id'], revision=0, review_status='proposed')
                value.setdefault('scope', {})
                if kind == 'entity_link':
                    value.setdefault('candidate_entity_ids', [])
                    value['original_target_entity_id'] = value.get('target_entity_id')
                    value['validation_errors'] = _link_errors(repo, db, value, run, schema)
                else:
                    for key in ('conditions', 'exceptions', 'dates', 'link_dependencies'):
                        value.setdefault(key, [])
                    value.setdefault('field_evidence', {})
                    value['validation_errors'] = list(dict.fromkeys(_assertion_errors(repo, db, value, run, schema)
                                                       + value.get('extraction_errors', [])))
                db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?)', (value['id'], run['id'], unit['id'], value['local_candidate_key'], _encode(value)))
                change['candidate_ids'].append(value['id'])
        change['published_unit_ids'].append(unit['id'])
        change['revision'] += 1
        if row:
            repo.save(db, 'changesets', change)
        else:
            db.execute('INSERT INTO changesets VALUES(?,?)', (change['id'], _encode(change)))
        return _publish_result(repo, db, change)


def _items(repo, db, change):
    values = []
    for identifier in change['candidate_ids']:
        value = _optional(repo, db, 'entity_links', identifier) or repo.get(db, 'assertions', identifier)
        values.append(value)
    return values


def _publish_result(repo, db, change):
    items = _items(repo, db, change)
    invalid = sum(bool(v.get('validation_errors')) for v in items)
    return dict(changeset_id=change['id'], changeset_revision=change['revision'], items=items,
                counts=dict(valid=len(items)-invalid, invalid=invalid,
                            unresolved=sum(v['review_status'] in {'proposed', 'deferred'} for v in items)))


def candidates(service, changeset_id=None, kind=None, review_status=None):
    with service.repository.connect() as db:
        changes = ([service.repository.get(db, 'changesets', changeset_id)] if changeset_id else
                   [c for c in reversed(_all(db, 'changesets')) if c.get('kind') == 'extraction'])
        changes = [c for c in changes if c.get('kind') == 'extraction']
        items = []
        for change in changes:
            change['candidates'] = _items(service.repository, db, change)
            change['unresolved_count'] = sum(c['review_status'] in {'proposed', 'deferred'} for c in change['candidates'])
            change['decisions'] = [d for d in _all(db, 'decisions') if d.get('changeset_id') == change['id']]
            items.extend(c for c in change['candidates'] if (not kind or c['kind'] == kind)
                         and (not review_status or c['review_status'] == review_status))
    first = changes[0] if changes else {}
    return dict(items=items, changesets=changes, changeset_id=first.get('id'), changeset_revision=first.get('revision'),
                unresolved_count=first.get('unresolved_count', 0))


def list_entities(service, concept_id=None, namespace=None, official_id=None, q=None):
    with service.repository.connect() as db:
        items = _all(db, 'entities')
    return {'items': [e for e in items if (not concept_id or e['concept_id'] == concept_id)
                     and (not namespace or e['namespace'] == namespace) and (not official_id or e.get('official_id') == official_id)
                     and (not q or q.casefold() in (e.get('name', '') + ' ' + str(e.get('official_id', ''))).casefold())][:100]}


def get_entity(service, entity_id):
    with service.repository.connect() as db:
        entity = service.repository.get(db, 'entities', entity_id)
        links = [v for v in _all(db, 'entity_links') if v.get('target_entity_id') == entity_id]
        link_ids = {v['id'] for v in links}
        assertions = [v for v in _all(db, 'assertions') if entity_id in (v.get('subject_id'), v.get('object_entity_id'))
                      or v.get('subject_link_id') in link_ids or v.get('object_link_id') in link_ids]
    return dict(entity=entity, aliases=[v for v in links if v['review_status'] == 'accepted'], links=links, assertions=assertions)


def get_evidence(service, identifier):
    with service.repository.connect() as db:
        ev = service.repository.get(db, 'evidence', identifier)
        block = service.repository.get(db, 'blocks', ev['block_id'])
        version = service.repository.get(db, 'versions', block['source_version_id'])
        source = service.repository.get(db, 'sources', version['source_id'])
    return dict(evidence=ev, block=block, version=version, source=source)


def decide(service, changeset_id, request):
    request = DecisionRequest.model_validate(request)
    repo = service.repository
    with service.lock, repo.connect() as db:
        change = repo.get(db, 'changesets', changeset_id)
        if change['revision'] != request.expected_changeset_revision:
            raise VersionConflict('후보가 변경되었습니다. 최신 내용을 다시 조회해 주세요.')
        if len({d.candidate_id for d in request.decisions}) != len(request.decisions):
            raise ValueError('같은 후보를 한 요청에서 두 번 결정할 수 없습니다.')
        run = repo.get(db, 'runs', change['run_id'])
        schema = _schema(repo, db, run)
        current = {v['id']: v for v in _items(repo, db, change)}
        if any(d.candidate_id not in current for d in request.decisions):
            raise ValueError('이 변경 묶음에 없는 후보입니다.')
        # Links are explicit decisions, never silently accepted for a dependent assertion.
        ordered = sorted(request.decisions, key=lambda d: current[d.candidate_id]['kind'] != 'entity_link')
        changed_sets = {change['id']: change}
        for decision in ordered:
            value = current[decision.candidate_id]
            before = deepcopy(value)
            is_link = value['kind'] == 'entity_link'
            table = 'entity_links' if is_link else 'assertions'
            fields = LINK_FIELDS if is_link else ASSERTION_FIELDS
            if decision.patch:
                if decision.action != 'modify' or not set(decision.patch) <= fields:
                    raise ValueError('수정 가능한 필드만 modify로 전달해야 합니다.')
                if is_link and 'target_entity_id' in decision.patch:
                    target = decision.patch['target_entity_id']
                    if target is None and value.get('target_entity_id'):
                        raise ValueError('연결 취소는 사유와 함께 unlink로 요청해야 합니다.')
                    entity = _optional(repo, db, 'entities', target)
                    if target and (not entity or entity['concept_id'] != value['concept_id']):
                        raise ValueError('동일한 개념 타입의 등록 개체를 선택해야 합니다.')
                if 'scope' in decision.patch:
                    old_source = value.get('scope', {}).get('source_version_id')
                    new_scope = decision.patch['scope']
                    if not isinstance(new_scope, dict) or new_scope.get('source_version_id') != old_source:
                        raise ValueError('원문 source_version_id는 수정할 수 없습니다.')
                value.update(decision.patch)
                if is_link and 'target_entity_id' in decision.patch:
                    value['method'] = 'manual' if value.get('target_entity_id') else 'unresolved'
            if decision.action == 'unlink':
                if not is_link or not decision.reason.strip():
                    raise ValueError('연결 취소는 개체 연결에만 가능하며 사유가 필요합니다.')
                value.update(target_entity_id=None, method='unresolved')
            accepting = decision.action in {'accept', 'modify'}
            errors = (_link_errors(repo, db, value, run, schema) if is_link else
                      _assertion_errors(repo, db, value, run, schema, require_accepted=accepting))
            if not is_link and decision.action != 'modify':
                errors = list(dict.fromkeys(errors + value.get('extraction_errors', [])))
            elif not is_link and decision.action == 'modify' and not errors:
                value['extraction_errors'] = []
            if errors and not is_link:
                for key in ('subject_id', 'object_entity_id', 'link_dependencies'):
                    if key in before:
                        value[key] = before[key]
                    else:
                        value.pop(key, None)
            if decision.action == 'accept' and errors:
                raise ValueError('수락할 수 없는 후보: ' + ', '.join(errors))
            value['validation_errors'] = errors
            value['review_status'] = ('accepted' if not errors else 'proposed') if accepting else {
                'defer': 'deferred', 'reject': 'rejected', 'unlink': 'proposed'}[decision.action]
            value['revision'] += 1
            repo.save(db, table, value)
            _decision(db, change['id'], request.actor, decision.action, decision.reason, before, value, change['revision'] + 1)
            if is_link:
                for assertion in _all(db, 'assertions'):
                    if assertion['review_status'] != 'accepted' or not any(
                        d['link_id'] == value['id'] and d['revision'] == before['revision']
                        for d in assertion.get('link_dependencies', [])):
                        continue
                    original = deepcopy(assertion)
                    assertion.update(review_status='proposed', revision=assertion['revision'] + 1)
                    assertion['validation_errors'] = list(dict.fromkeys(assertion.get('validation_errors', []) + ['dependency_changed']))
                    # Preserve accepted subject/object IDs until this assertion is reviewed again.
                    repo.save(db, 'assertions', assertion)
                    affected_id = assertion['changeset_id']
                    if affected_id not in changed_sets:
                        changed_sets[affected_id] = repo.get(db, 'changesets', affected_id)
                    if assertion['id'] in current:
                        current[assertion['id']] = assertion
                    _decision(db, affected_id, request.actor, 'dependency_changed', '직접 의존 연결 변경', original, assertion,
                              changed_sets[affected_id]['revision'] + 1)
        for changed in changed_sets.values():
            changed['revision'] += 1
            repo.save(db, 'changesets', changed)
        result = _publish_result(repo, db, change)
        result['invalid_count'] = result['counts']['invalid']
        result['unresolved_count'] = result['counts']['unresolved']
        return result


def _decision(db, changeset_id, actor, action, reason, before, after, revision):
    record = dict(id=uuid4().hex, changeset_id=changeset_id, revision=revision, actor=actor, action=action,
                  candidate_id=after['id'], reason=reason, created_at=_now(), before=before, after=deepcopy(after))
    db.execute('INSERT INTO decisions VALUES(?,?)', (record['id'], _encode(record)))

"""Version-bound LH consumer mapping; canonical definitions remain in LinkML/registry."""
from copy import deepcopy
import json
from uuid import uuid4

from pydantic import Field

from . import ontology_canonical as canonical, ontology_schema
from .extraction_contract import PROFILE
from .schemas import RecordedAction

ROLES = {'LH:complex': 'CONCEPT_001', 'LH:notice': 'Notice'}
SCALARS = {'string', 'integer', 'float', 'double', 'decimal', 'boolean', 'date', 'datetime'}


class MappingReview(RecordedAction):
    expected_review_id: str | None
    expected_ontology_head_id: str | None
    target_ids: dict[str, str] = Field(default_factory=dict)


def definitions(version, contract=None):
    if version.get('payload_version') != 2:
        return ontology_schema._from_schema(version['linkml_yaml'])
    from linkml_runtime.utils.schemaview import SchemaView
    view = SchemaView(version['linkml_yaml'])
    items = canonical.targets(version)
    live = {i: t for i, t in items.items() if not t.get('deprecated')}
    classes = {i: t for i, t in live.items() if t['kind'] == 'class'}
    reverse = {v: k for k, v in (contract or {}).get('target_ids', {}).items()}
    result = []
    for identifier, target in live.items():
        if target['kind'] not in {'class', 'attribute', 'relation'}:
            continue
        value = deepcopy(target)
        value.update(kind='concept' if target['kind'] == 'class' else target['kind'],
                     range=target.get('range', 'string'),
                     evidence=[dict(evidence_id=e['evidence_id'], quote=e['quote']) for e in target.get('evidence_refs', [])])
        if target['kind'] == 'class':
            value['aliases'] = list(view.get_class(target['symbol']).aliases or [])
        if target['kind'] != 'class':
            domains = {i: view.induced_slot(target['symbol'], c['symbol']) for i, c in classes.items()
                       if target['symbol'] in view.class_slots(c['symbol'])}
            value['allowed_domain_ids'] = sorted(domains)
            value['required_domain_ids'] = sorted(i for i, slot in domains.items() if slot.required)
            # Class-local overrides must not silently become one global fact contract.
            variants = {(str(s.range), bool(s.multivalued), tuple(str(k) for k in (s.any_of or []))) for s in domains.values()}
            if len(variants) > 1 or any(s.any_of or s.all_of or s.exactly_one_of or s.pattern for s in domains.values()):
                value['unsupported_reason'] = '클래스별 값 제약/복합 슬롯 제약은 명시 대응 필요'
            elif domains:
                slot = next(iter(domains.values()))
                value['multivalued'] = bool(slot.multivalued)
                enum = view.all_enums().get(str(slot.range))
                value['range'] = 'string' if enum else next((i for i, t in classes.items() if t['symbol'] == slot.range), str(slot.range))
                value['enum_values'] = list(enum.permissible_values) if enum else []
            value['allowed_range_ids'] = sorted(i for i, c in classes.items()
                if value.get('range') in classes and classes[value['range']]['symbol'] in view.class_ancestors(c['symbol']))
            if target['kind'] == 'attribute' and (value.get('multivalued') or value['range'] not in SCALARS):
                value['unsupported_reason'] = '단일값 기본 자료형만 추출 지원'
        if identifier in reverse:
            value['profile_id'] = reverse[identifier]
        result.append(value)
    return result


def permits(predicate, concept_id, role='subject'):
    key, fallback = ('allowed_domain_ids', 'domain_id') if role == 'subject' else ('allowed_range_ids', 'range')
    return concept_id in predicate.get(key, [predicate.get(fallback)])


def entity_type(entity, contract):
    return (contract or {}).get('role_targets', {}).get(entity.get('namespace'), entity.get('concept_id'))


def evidence_ids(version):
    items = canonical.targets(version)
    return {identifier for t in items.values() if not t.get('deprecated')
            for identifier in [*[e['evidence_id'] for e in [*t.get('evidence_refs', []), *t.get('counter_evidence_refs', [])]],
                               *t.get('dependency_block_ids', [])]}


def _same_meaning(actual, expected):
    keys = ['kind', 'definition', 'inclusion', 'exclusion']
    if expected['kind'] != 'concept':
        keys += ['domain_id', 'range', 'multivalued']
    qualifiers = actual.get('qualifiers', {})
    return (not actual.get('unsupported_reason') and all(actual.get(k) == expected.get(k) for k in keys)
            and not actual.get('enum_values')
            and not any(qualifiers.get(k) for k in ('scope', 'time'))
            and qualifiers.get('negation', 'unknown') != 'negated')


def _latest(db, identifier):
    row = db.execute("SELECT payload FROM decisions WHERE json_extract(payload,'$.kind')='lh_consumer_mapping' "
                     "AND json_extract(payload,'$.ontology_version_id')=? ORDER BY rowid DESC LIMIT 1", (identifier,)).fetchone()
    return json.loads(row['payload']) if row else None


def contract_for(db, version):
    values = {d['id']: d for d in definitions(version)}
    mapping = {i: i for i, expected in PROFILE['definitions'].items() if i in values and _same_meaning(values[i], expected)}
    review = _latest(db, version['id'])
    if review:
        mapping = review['target_ids']
    # A slot mapping needs the reviewed class endpoints too.
    mapping = {i: target for i, target in mapping.items() if all(k in mapping for k in
        [PROFILE['definitions'][i].get('domain_id'),
         PROFILE['definitions'][i].get('range') if PROFILE['definitions'][i]['kind'] == 'relation' else None] if k)}
    return dict(ontology_version_id=version['id'], ontology_hash=version.get('version_hash') or canonical.digest(version['linkml_yaml']),
                review_id=review['id'] if review else None, profile_version=PROFILE['version'],
                target_ids=mapping, role_targets={role: mapping[original] for role, original in ROLES.items() if original in mapping})


def inspect(service, identifier):
    with service.repository.connect() as db:
        version = service.repository.get(db, 'ontology_versions', identifier)
        contract = contract_for(db, version)
        rows = definitions(version, contract)
        head = db.execute('SELECT reviewed_version_id FROM ontology_heads WHERE lineage_id=?', (version.get('lineage_id'),)).fetchone()
        return dict(contract=contract, ontology_head_id=head[0] if head else None,
                    mapping_editable=version.get('payload_version') == 2, review=_latest(db, identifier),
                    definitions=rows, mapping_roles=PROFILE['definitions'],
                    unresolved_profile_ids=[i for i in PROFILE['definitions'] if i not in contract['target_ids']],
                    unsupported=[dict(id=d['id'], reason=d['unsupported_reason']) for d in rows if d.get('unsupported_reason')],
                    vocabulary_registry=version.get('vocabulary_registry', {}),
                    activation='separate_snapshot_decision')


def review(service, identifier, request):
    request = MappingReview.model_validate(request)
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        version = service.repository.get(db, 'ontology_versions', identifier)
        if version['status'] != 'reviewed':
            raise ValueError('검토된 온톨로지의 LH 의미 대응만 확정할 수 있습니다.')
        if version.get('payload_version') != 2:
            raise ValueError('v1은 기존 LH 매핑을 유지합니다. 새 의미 대응은 reviewed v2에서 검토하세요.')
        prior = _latest(db, identifier)
        head = db.execute('SELECT reviewed_version_id FROM ontology_heads WHERE lineage_id=?', (version.get('lineage_id'),)).fetchone()
        if (prior['id'] if prior else None) != request.expected_review_id or (head[0] if head else None) != request.expected_ontology_head_id:
            raise ontology_schema.VersionConflict('의미 대응 또는 온톨로지 head가 변경되었습니다.')
        if head and head[0] != identifier:
            raise ontology_schema.VersionConflict('현재 head 버전에서 새 의미 대응을 검토하세요.')
        rows = {d['id']: d for d in definitions(version)}
        mapping = request.target_ids
        if len(set(mapping.values())) != len(mapping):
            raise ValueError('서로 다른 LH 필드를 하나의 정의로 합칠 수 없습니다.')
        for original, target in mapping.items():
            expected, actual = PROFILE['definitions'].get(original), rows.get(target)
            if not expected or not actual or actual['kind'] != expected['kind'] or actual.get('unsupported_reason'):
                raise ValueError('지원하는 LH 역할과 유효 정본 ID만 대응하세요: ' + original)
            if expected['kind'] != 'concept':
                if not permits(actual, mapping.get(expected['domain_id'])) or actual.get('multivalued', False) != expected['multivalued']:
                    raise ValueError('LH 주체/다중값 계약과 다른 대응입니다: ' + original)
                if expected['kind'] == 'relation':
                    if not permits(actual, mapping.get(expected['range']), 'object'):
                        raise ValueError('LH 관계 대상 계약과 다른 대응입니다.')
                elif actual['range'] != expected['range']:
                    raise ValueError('LH 값 변환 자료형과 다른 대응입니다.')
        from .snapshots import current_restrictions
        if current_restrictions(service.repository, db, dict(id=identifier, ontology_version_id=identifier)):
            raise ValueError('사용 제한된 온톨로지 근거의 대응은 수락할 수 없습니다.')
        record = dict(id=uuid4().hex, kind='lh_consumer_mapping', ontology_version_id=identifier,
                      target_ids=mapping, actor=request.actor, reason=request.reason,
                      created_at=ontology_schema._now(), previous_review_id=prior['id'] if prior else None)
        db.execute('INSERT INTO decisions VALUES(?,?)', (record['id'], json.dumps(record, ensure_ascii=False)))
    return inspect(service, identifier)

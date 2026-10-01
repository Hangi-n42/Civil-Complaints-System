"""LinkML canonical versions and local human review, without graph activation."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import yaml

from .schemas import Candidate, DecisionRequest

ROOT = 'KnowledgeDocument'
SCALARS = {'string', 'integer', 'float', 'double', 'boolean', 'date', 'datetime', 'uri'}
EDITABLE = set(Candidate.model_fields) - {'id', 'kind'}


class VersionConflict(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encode(value):
    return json.dumps(value, ensure_ascii=False)


def _merge(base, proposed):
    return list({c['id']: c for c in [*base, *proposed]}.values())


def _references(items):
    concepts = {c['id'] for c in items if c['kind'] == 'concept'}
    for c in items:
        if c['kind'] != 'concept' and c['domain_id'] not in concepts:
            raise ValueError(f"{c['id']}: domain_id에 해당하는 개념을 함께 수락해야 합니다.")
        if c['kind'] == 'relation' and c['range'] not in concepts:
            raise ValueError(f"{c['id']}: 관계 대상 개념을 함께 수락해야 합니다.")
        if c['kind'] == 'attribute' and c['range'] not in SCALARS:
            raise ValueError(f"{c['id']}: 지원하지 않는 속성 자료형입니다.")
        if c['kind'] != 'attribute' and c['enum_values']:
            raise ValueError('enum_values는 속성에만 사용할 수 있습니다.')


def validate_candidates(candidates, blocks, cqs, base_candidates=None):
    values = [Candidate.model_validate(c).model_dump() for c in candidates]
    ids = [c['id'] for c in values]
    if not values or len(ids) != len(set(ids)):
        raise ValueError('비어 있지 않은 고유 후보 ID가 필요합니다.')
    if any(i == ROOT or i.startswith(('items_', 'enum_')) for i in ids):
        raise ValueError('KnowledgeDocument, items_, enum_는 예약된 이름입니다.')
    block_index = {b['evidence_id']: b['text'] for b in blocks}
    cq_ids = {c['id'] for c in cqs}
    base = {c['id']: c for c in base_candidates or []}
    for c in values:
        if c['id'] in base and c['kind'] != base[c['id']]['kind']:
            raise ValueError('기존 ID의 후보 종류를 변경할 수 없습니다.')
        if not set(c['cq_ids']) <= cq_ids:
            raise ValueError(f"{c['id']}: 존재하지 않는 CQ입니다.")
        for evidence in c['evidence']:
            if not evidence['quote'].strip() or evidence['quote'] not in block_index.get(evidence['evidence_id'], ''):
                raise ValueError(f"{c['id']}: 근거 ID 또는 인용문이 고정 원문과 일치하지 않습니다.")
    _references(_merge(list(base.values()), values))
    return values


def build_schema(items):
    """Root/range/prefix checks adapted from OntoGPT; no dynamic code imports."""
    from linkml.generators.jsonschemagen import JsonSchemaGenerator
    from linkml_runtime.utils.schemaview import SchemaView

    _references(items)
    schema = dict(id='https://example.org/company-knowledge', name='company_knowledge',
                  prefixes={'linkml': 'https://w3id.org/linkml/', 'ck': 'https://example.org/company-knowledge/'},
                  default_prefix='ck', imports=['linkml:types'], default_range='string',
                  classes={ROOT: {'tree_root': True, 'slots': []}}, slots={}, enums={})
    for c in items:
        definition = dict(title=c['name'], description=c['definition'],
                          annotations={'candidate': {'tag': 'candidate', 'value': _encode(c)}})
        if c['kind'] == 'concept':
            schema['classes'][c['id']] = dict(definition, slots=[])
            slot = 'items_' + c['id']
            schema['slots'][slot] = dict(range=c['id'], multivalued=True, inlined_as_list=True)
            schema['classes'][ROOT]['slots'].append(slot)
        else:
            range_name = c['range']
            if c['enum_values']:
                range_name = 'enum_' + c['id']
                schema['enums'][range_name] = {'permissible_values': {v: {} for v in c['enum_values']}}
            schema['slots'][c['id']] = dict(definition, domain=c['domain_id'], range=range_name,
                                          required=c['required'], multivalued=c['multivalued'])
            if c['kind'] == 'relation':
                schema['slots'][c['id']]['inlined'] = True
    for c in items:
        if c['kind'] != 'concept':
            schema['classes'][c['domain_id']]['slots'].append(c['id'])
    text = yaml.safe_dump(schema, allow_unicode=True, sort_keys=False)
    view = SchemaView(text)
    if ROOT not in view.all_classes() or not view.schema.prefixes:
        raise ValueError('LinkML root 또는 prefix가 없습니다.')
    derived = json.loads(JsonSchemaGenerator(view.schema).serialize())
    return text, derived


def _from_schema(text):
    schema = yaml.safe_load(text)
    return [json.loads(v['annotations']['candidate']['value'])
            for group in ('classes', 'slots') for v in schema.get(group, {}).values()
            if 'candidate' in v.get('annotations', {})]


def _insert(db, table, value):
    # Table names are internal literals, never request parameters.
    db.execute(f'INSERT INTO {table} VALUES(?,?)', (value['id'], _encode(value)))


def _version(db, items, changeset_id, status, parent_id=None, run_id=None):
    text, derived = build_schema(items)
    version = dict(id=uuid4().hex, created_at=_now(), changeset_id=changeset_id,
                   parent_version_id=parent_id, status=status, linkml_yaml=text, run_id=run_id,
                   schema_hash=sha256(text.encode('utf-8')).hexdigest(),
                   generated_json_schema_hash=sha256(json.dumps(derived, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
                   unsupported_constraints=[])
    _insert(db, 'ontology_versions', version)
    return version['id']


def _base(service, run):
    base_id = run.get('base_ontology_version_id')
    if not base_id:
        return []
    version = get_ontology(service, base_id)
    if version.get('payload_version') == 2:
        raise ValueError('v2 기준 변경은 A3 변경 후보 경로를 사용해야 합니다.')
    if version['status'] != 'reviewed':
        raise ValueError('검토된 온톨로지 버전만 기준으로 사용할 수 있습니다.')
    return version['candidates']


def publish(service, run, candidates):
    base = _base(service, run)
    values = validate_candidates(candidates, run['frozen_blocks'], run['cqs'], base)
    change = dict(id=uuid4().hex, kind='ontology', revision=0, created_at=_now(), run_id=run['id'],
                  base_ontology_version_id=run.get('base_ontology_version_id'),
                  original_candidates=deepcopy(values),
                  review_status={c['id']: 'proposed' for c in values},
                  review=run.get('review', {}), reviewed_ontology_version_id=None)
    with service.lock, service.repository.connect() as db:
        existing = db.execute("SELECT payload FROM changesets WHERE json_extract(payload, '$.run_id')=?", (run['id'],)).fetchone()
        if existing:
            value = json.loads(existing['payload'])
            return dict(changeset_id=value['id'], ontology_version_id=value['ontology_version_id'])
        change['ontology_version_id'] = _version(db, _merge(base, values), change['id'], 'draft', run.get('base_ontology_version_id'), run['id'])
        _insert(db, 'changesets', change)
    return dict(changeset_id=change['id'], ontology_version_id=change['ontology_version_id'])


def get_ontology(service, ontology_id):
    with service.repository.connect() as db:
        version = service.repository.get(db, 'ontology_versions', ontology_id)
    if version.get('payload_version') == 2:
        from .ontology_canonical import read
        return read(version)
    values = _from_schema(version['linkml_yaml'])
    _, derived = build_schema(values)
    return dict(version, payload_version=1, vocabulary_registry={}, review_status=version['status'], candidates=values,
                linkml_schema=yaml.safe_load(version['linkml_yaml']), json_schema=derived)


def list_ontologies(service):
    with service.repository.connect() as db:
        values = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM ontology_versions ORDER BY rowid DESC')]
    return {'items': [{k: v for k, v in value.items() if k != 'linkml_yaml'} for value in values]}


def candidates(service, changeset_id=None, kind=None, review_status=None):
    from . import extraction_store
    if kind in {'entity_link', 'assertion'}:
        return extraction_store.candidates(service, changeset_id, kind, review_status)
    with service.repository.connect() as db:
        changes = ([service.repository.get(db, 'changesets', changeset_id)] if changeset_id else
                   [json.loads(r['payload']) for r in db.execute('SELECT payload FROM changesets ORDER BY rowid DESC')])
        if changeset_id and changes[0].get('kind') == 'extraction':
            return extraction_store.candidates(service, changeset_id, kind, review_status)
        changes = [c for c in changes if c.get('kind', 'ontology') == 'ontology']
        for change in changes:
            change['decisions'] = [json.loads(r['payload']) for r in db.execute(
                "SELECT payload FROM decisions WHERE json_extract(payload, '$.changeset_id')=? ORDER BY rowid", (change['id'],))]
    items = []
    for change in changes:
        if change.get('payload_version') == 2:
            from .ontology_changes import view
            change.update(view(service, change))
            items.extend(c for c in change['candidates'] if (not kind or c['kind'] == kind)
                         and (not review_status or c['review_status'] == review_status))
            continue
        current = get_ontology(service, change['ontology_version_id'])['candidates']
        change['candidates'] = [dict(c, review_status=change['review_status'][c['id']], changeset_id=change['id'])
                                for c in current if c['id'] in change['review_status']]
        change['unresolved_count'] = sum(c['review_status'] in {'proposed', 'deferred'} for c in change['candidates'])
        items.extend(c for c in change['candidates'] if (not kind or c['kind'] == kind)
                     and (not review_status or c['review_status'] == review_status))
    first = changes[0] if changes else {}
    return dict(items=items, changesets=changes, changeset_id=first.get('id'),
                changeset_revision=first.get('revision'), unresolved_count=first.get('unresolved_count', 0))


def decide(service, changeset_id, request):
    request = DecisionRequest.model_validate(request)
    with service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', changeset_id)
        kind = change.get('kind', 'ontology')
    if change.get('payload_version') == 2:
        from .ontology_changes import decide as decide_v2
        return decide_v2(service, changeset_id, request)
    if any(d.consumer_action for d in request.decisions):
        raise ValueError('consumer_action은 v2 변경 후보에만 지원합니다.')
    if any(d.action == 'edit' for d in request.decisions):
        raise ValueError('edit는 v2 변경 후보에만 지원합니다.')
    if kind == 'extraction':
        from .extraction_store import decide as decide_extraction
        return decide_extraction(service, changeset_id, request)
    if any(d.action == 'unlink' for d in request.decisions):
        raise ValueError('온톨로지 후보에는 연결 취소를 사용할 수 없습니다.')
    with service.lock, service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', changeset_id)
        if request.expected_changeset_revision != change['revision']:
            raise VersionConflict('후보가 변경되었습니다. 최신 내용을 다시 조회해 주세요.')
        run = service.repository.get(db, 'runs', change['run_id'])
        base = _base(service, run)
        current = _from_schema(service.repository.get(db, 'ontology_versions', change['ontology_version_id'])['linkml_yaml'])
        proposals = {c['id']: c for c in current if c['id'] in change['review_status']}
        if len({d.candidate_id for d in request.decisions}) != len(request.decisions):
            raise ValueError('한 요청에 같은 후보를 두 번 결정할 수 없습니다.')
        for decision in request.decisions:
            if decision.candidate_id not in proposals:
                raise ValueError('이 묶음에 없는 후보입니다.')
            if decision.patch:
                if decision.action != 'modify' or not set(decision.patch) <= EDITABLE:
                    raise ValueError('수정 가능한 후보 필드만 modify로 전달해야 합니다.')
                proposals[decision.candidate_id].update(decision.patch)
            change['review_status'][decision.candidate_id] = {
                'accept': 'accepted', 'modify': 'accepted', 'defer': 'deferred', 'reject': 'rejected'}[decision.action]
        values = validate_candidates(list(proposals.values()), run['frozen_blocks'], run['cqs'], base)
        accepted = [c for c in values if change['review_status'][c['id']] == 'accepted']
        reviewed = _merge(base, accepted)
        _references(reviewed)
        old_id = change['ontology_version_id']
        change['ontology_version_id'] = _version(db, _merge(base, values), change['id'], 'draft', old_id, run['id'])
        change['reviewed_ontology_version_id'] = _version(db, reviewed, change['id'], 'reviewed', old_id, run['id']) if reviewed else None
        change['revision'] += 1
        for decision in request.decisions:
            _insert(db, 'decisions', dict(id=uuid4().hex, changeset_id=change['id'], revision=change['revision'],
                                        actor=request.actor, created_at=_now(), ontology_version_id=change['ontology_version_id'],
                                        **decision.model_dump()))
        service.repository.save(db, 'changesets', change)
    return dict(changeset_id=change['id'], changeset_revision=change['revision'],
                ontology_version_id=change['ontology_version_id'], reviewed_ontology_version_id=change['reviewed_ontology_version_id'],
                items=candidates(service, change['id'])['items'])


def default_cqs():
    path = Path(__file__).resolve().parents[2] / 'configs/knowledge/pilot_v1/tasks.development.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return {'items': [{'id': task['task_id'], 'question': task['query']} for task in data['tasks']]}

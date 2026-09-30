"""LinkML owns classes/slots; the same version's registry owns vocabulary."""
from copy import deepcopy
from hashlib import sha256
import json

import yaml

from .ontology_schema import ROOT, _encode


METAMODEL = dict(version='discovery-empty-v1', company_definitions=[],
    target_kinds=['class', 'attribute', 'relation', 'vocabulary_concept', 'hierarchy', 'alias'])
OPTIONAL_PATTERNS = [dict(id='vocabulary-broader-v1', definition='통제 어휘의 더 넓은 용어 연결',
    relations=['broader', 'related'], applicable='동일 범위의 통제 어휘',
    not_applicable='클래스 상속 또는 개별 사실의 참/거짓 판정',
    source='https://www.w3.org/TR/2009/REC-skos-reference-20090818/',
    license='W3C document license; 의미 참고, 코드 이식 없음', version='2009-08-18')]


def digest(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return sha256(text.encode('utf-8')).hexdigest()


def annotation(value):
    return {'value': _encode(value)}


def annotated(obj, name, default=None):
    raw = obj.get('annotations', {}).get(name)
    return json.loads(raw['value']) if raw else deepcopy(default)


def targets(version):
    """Read v1 identities without migration; read v2 definitions from their canonical owner."""
    if not version:
        return {}
    schema = yaml.safe_load(version['linkml_yaml'])
    result = {}
    for group in ('classes', 'slots'):
        for symbol, d in schema.get(group, {}).items():
            item = annotated(d, 'ontology_target')
            if item is None:
                legacy = annotated(d, 'candidate')
                if legacy is None:
                    continue
                item = dict(legacy, kind='class' if legacy['kind']=='concept' else legacy['kind'])
                item['evidence_refs'] = item.pop('evidence', [])
            item.update(symbol=symbol, name=d.get('title', symbol), definition=d.get('description', ''),
                        deprecated=bool(d.get('deprecated')))
            if group == 'slots':
                item.update(domain_id=d.get('domain'), range=d.get('range', 'string'),
                            required=bool(d.get('required')), multivalued=bool(d.get('multivalued')))
                enum = schema.get('enums', {}).get(item['range'])
                if enum:
                    item.update(range='string', enum_values=list(enum.get('permissible_values', {})))
            result[item['id']] = item
    # References use stable IDs; symbols are only LinkML names.
    ids = {t['symbol']: t['id'] for t in result.values()}
    for t in result.values():
        for key in ('domain_id', 'range'):
            if key in t:
                t[key] = ids.get(t[key], t[key])
    result.update({t['id']: t for t in annotated(schema, 'ontology_links', [])})
    result.update(deepcopy(version.get('vocabulary_registry', {}).get('targets', {})))
    return result


def references(target):
    keys = {'attribute': ['domain_id'], 'relation': ['domain_id', 'range'],
            'hierarchy': ['child_id', 'parent_id'], 'alias': ['alias_of']}.get(target.get('kind'), [])
    return {target[k] for k in keys if isinstance(target.get(k), str) and target[k]}


def project(base, changes):
    items = deepcopy(targets(base))
    for c in changes:
        identifier = c['target_id']
        if c['operation'] in {'merge', 'deprecate'}:
            items[identifier] = dict(items[identifier], deprecated=True,
                replaced_by=c['after'].get('canonical_id') if c['operation']=='merge' else None)
            continue
        item = dict(items.get(identifier, {}), **c['after'])
        item.update(id=identifier, kind=c['target_kind'], symbol=c['symbol'], deprecated=False)
        for field in ('evidence_refs', 'counter_evidence_refs', 'qualifiers', 'cq_ids', 'scope_item_ids',
                      'rationale', 'support_type', 'hierarchy_review'):
            item[field] = deepcopy(c[field])
        items[identifier] = item
    return items


def derive(text):
    """Never reconstruct stored v2 YAML through the v1 candidate builder."""
    from linkml_runtime.utils.schemaview import SchemaView
    from linkml.generators.jsonschemagen import JsonSchemaGenerator
    view = SchemaView(text)
    derived = json.loads(JsonSchemaGenerator(view.schema).serialize())
    slots = {name: view.class_slots(name) for name in view.all_classes() if name != ROOT}
    return derived, slots


def build(base, items):
    if base:
        schema = yaml.safe_load(base['linkml_yaml'])
    else:
        schema = dict(id='https://example.org/company-knowledge', name='company_knowledge',
            prefixes={'linkml': 'https://w3id.org/linkml/', 'ck': 'https://example.org/company-knowledge/'},
            default_prefix='ck', imports=['linkml:types'], default_range='string',
            classes={ROOT: {'tree_root': True, 'slots': []}}, slots={}, enums={})
    schema.setdefault('annotations', {})['metamodel_version'] = annotation(METAMODEL['version'])
    classes, slots = schema['classes'], schema.setdefault('slots', {})
    old_links = annotated(schema, 'ontology_links', [])
    # Remove only structural projections owned by our previous link records.
    for edge in old_links:
        owner = items.get(edge.get('child_id') or edge.get('alias_of'), {})
        d = classes.get(owner.get('symbol'), {})
        if edge['kind']=='hierarchy' and edge.get('relation')=='is_a':
            d.pop('is_a', None)
        elif edge['kind']=='alias' and edge.get('name') in d.get('aliases', []):
            d['aliases'].remove(edge['name'])
    symbols = {i: t['symbol'] for i,t in items.items()}
    registry, links = {}, []
    for identifier, t in items.items():
        kind, symbol = t['kind'], t['symbol']
        vocabulary = kind=='vocabulary_concept' or (kind=='hierarchy' and t.get('relation') in {'broader','related'}) or (
            kind=='alias' and items.get(t.get('alias_of'), {}).get('kind')=='vocabulary_concept')
        if vocabulary:
            registry[identifier] = deepcopy(t)
            continue
        if kind in {'hierarchy', 'alias'}:
            links.append(deepcopy(t))
            continue
        group = classes if kind=='class' else slots
        d = deepcopy(group.get(symbol, {}))
        d.update(title=t['name'], description=t['definition'])
        d['annotations'] = {k:v for k,v in d.get('annotations', {}).items() if k not in {'candidate','ontology_target'}}
        # Descriptions and slot constraints have a single owner: standard LinkML fields.
        metadata = {k:v for k,v in t.items() if k not in {'name','definition','domain_id','range','required','multivalued','enum_values','deprecated','symbol'}}
        d['annotations']['ontology_target'] = annotation(metadata)
        if t.get('deprecated'):
            d['deprecated'] = 'reviewed deprecation; see ontology_target.replaced_by'
        else:
            d.pop('deprecated', None)
        if kind=='class':
            d.setdefault('slots', [])
            item_slot = 'items_' + symbol
            slots[item_slot] = dict(range=symbol, multivalued=True, inlined_as_list=True)
            if item_slot not in classes[ROOT]['slots']:
                classes[ROOT]['slots'].append(item_slot)
        else:
            for cls in classes.values():
                if symbol in cls.get('slots', []):
                    cls['slots'].remove(symbol)
            d.update(domain=symbols[t['domain_id']], range=symbols.get(t['range'], t['range']),
                     required=t.get('required', False), multivalued=t.get('multivalued', False))
            if t.get('enum_values'):
                d['range'] = 'enum_' + symbol
                schema.setdefault('enums', {})[d['range']] = {'permissible_values': {v:{} for v in t['enum_values']}}
            if kind=='relation':
                d['inlined'] = True
        group[symbol] = d
    for t in items.values():
        if t['kind'] in {'attribute','relation'}:
            classes[symbols[t['domain_id']]].setdefault('slots', []).append(t['symbol'])
    for edge in links:
        if edge.get('deprecated'):
            continue
        if edge['kind']=='hierarchy' and edge['relation']=='is_a':
            classes[symbols[edge['child_id']]]['is_a'] = symbols[edge['parent_id']]
        elif edge['kind']=='alias':
            d = classes[symbols[edge['alias_of']]]
            d['aliases'] = list(dict.fromkeys([*d.get('aliases', []), edge['name']]))
    schema['annotations']['ontology_links'] = annotation(links)
    text = yaml.safe_dump(schema, allow_unicode=True, sort_keys=False)
    vocabulary_registry = dict(version=1, targets=registry,
        replaced_ids={i:t['replaced_by'] for i,t in items.items() if t.get('replaced_by')})
    derived, effective = derive(text)
    sh, rh = digest(text), digest(vocabulary_registry)
    return dict(payload_version=2, linkml_yaml=text, vocabulary_registry=vocabulary_registry,
                schema_hash=sh, registry_hash=rh, version_hash=digest([sh,rh]),
                generated_json_schema_hash=digest(derived),
                unsupported_constraints=['원문 의미·범위·시점·부정·조건은 JSON Schema로 판정하지 않음']), derived, effective


def read(version):
    derived, effective = derive(version['linkml_yaml'])
    items = targets(version)
    # Compatibility view for A2 inspection, not a second editable store or K4 activation.
    candidates = [dict(t, kind='concept' if t['kind']=='class' else t['kind'],
        classification={'class':'type','attribute':'property_value','vocabulary_concept':'vocabulary'}.get(t['kind'], 'unresolved'),
        evidence=[dict(evidence_id=e['evidence_id'], quote=e['quote']) for e in t.get('evidence_refs', [])])
        for t in items.values() if not t.get('deprecated')]
    return dict(version, review_status=version['status'], candidates=candidates, targets=list(items.values()),
                linkml_schema=yaml.safe_load(version['linkml_yaml']), json_schema=derived,
                effective_class_slots=effective, consumer_support='A3 review only; K4/K5 v2 integration requires A5')

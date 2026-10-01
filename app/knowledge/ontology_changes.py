"""A3 candidates before compilation, deterministic review and atomic lineage heads."""
from copy import deepcopy
import json
from uuid import uuid4

from pydantic import ValidationError

from . import ontology_canonical as canonical
from .ontology_changes_models import AddOntologyChanges, Definition, EvidenceRef, HierarchyReview, OntologyChangeV2, Qualifiers
from .ontology_schema import SCALARS, VersionConflict, _insert, _now
from .schemas import DecisionRequest


EDITABLE = {'after', 'target_kind', 'support_type', 'evidence_refs', 'counter_evidence_refs',
            'qualifiers', 'cq_ids', 'scope_item_ids', 'rationale', 'unresolved_issues', 'hierarchy_review'}
DEFINITION_FIELDS = {'name', 'definition', 'inclusion', 'exclusion'}
AFTER_FIELDS = dict(class_=DEFINITION_FIELDS, vocabulary_concept=DEFINITION_FIELDS,
    attribute=DEFINITION_FIELDS | {'domain_id','range','required','multivalued','enum_values'},
    relation=DEFINITION_FIELDS | {'domain_id','range','required','multivalued','direction'},
    hierarchy={'child_id','parent_id','relation'}, alias={'name','alias_of'})
AFTER_FIELDS['class'] = AFTER_FIELDS.pop('class_')


def _base(repo, db, change):
    identifier = change.get('base_ontology_version_id')
    return repo.get(db, 'ontology_versions', identifier) if identifier else None


def _head(db, lineage):
    row = db.execute('SELECT reviewed_version_id FROM ontology_heads WHERE lineage_id=?', (lineage,)).fetchone()
    return row['reviewed_version_id'] if row else None


def _blocks(repo, db, run):
    return {identifier: repo.get(db, 'blocks', identifier) for u in run['units']
            if u['status']=='succeeded' for identifier in u.get('block_ids', [])}


def _ref(raw, blocks):
    """Fill missing locators/spans, never replace an explicitly supplied mismatching reference."""
    b = blocks.get(raw.get('block_id') or raw.get('evidence_id'), {})
    quote = raw.get('quote', b.get('text', ''))
    start = b.get('text', '').find(quote) if quote else -1
    return dict(evidence_id=raw.get('evidence_id', ''), block_id=raw.get('block_id', b.get('id', '')),
        source_version_id=raw.get('source_version_id', b.get('source_version_id', '')),
        parse_run_id=raw.get('parse_run_id', b.get('parse_run_id', b.get('run_id', ''))),
        span=raw.get('span', [start, start+len(quote)]), quote=quote,
        locator=raw.get('locator', b.get('locator', {})))


def _make(raw, base, origin=None):
    requested_id = raw.get('target_id')
    target = base.get(requested_id) if isinstance(requested_id, str) else None
    identifier = target['id'] if target else 'ot_' + uuid4().hex
    values = dict(change_id='oc_'+uuid4().hex, target_id=identifier,
        symbol=target['symbol'] if target else 'T'+identifier.removeprefix('ot_'), target_kind=raw.get('target_kind', 'class'),
        operation=raw.get('operation', 'add'), before=deepcopy(target), after=deepcopy(raw.get('after', {})),
        dependency_ids=[], affected_reference_ids=[], support_type='unresolved', evidence_refs=[], counter_evidence_refs=[],
        qualifiers={}, cq_ids=[], scope_item_ids=[], rationale='', unresolved_issues=[], hierarchy_review={},
        validation={}, review_status='unreviewed', origin=deepcopy(origin or {}))
    for key in EDITABLE - {'target_kind','after'}:
        if key in raw:
            values[key] = deepcopy(raw[key])
    if 'target_id' in raw and not target:
        values['origin']['unknown_target_id'] = repr(requested_id)
    unknown = set(raw) - (EDITABLE | {'operation', 'target_id'})
    if unknown:
        values['origin']['unsupported_fields'] = sorted(unknown)
    return values


def _convert(run, base, blocks):
    result = run['result']
    rows, references, mapping = [], [], {}
    alignments = result.get('alignments', [])
    observations = result.get('observations', [])
    relations = result.get('relations', [])
    for source in observations + relations:
        concept = 'classification' in source
        if (concept and source['classification'] not in {'type','vocabulary'}) or (not concept and source['statement_type']=='instance'):
            references.append(deepcopy(source))
            mapping[source['id']] = dict(reference_id=source['id'], local_ref=source.get('local_ref'))
            continue
        kind = ('class' if source['classification']=='type' else 'vocabulary_concept') if concept else 'relation'
        support = source.get('support_type', 'explicit' if source.get('statement_type') in {'definition','rule'} else source.get('statement_type'))
        support = 'design_proposal' if support=='instance_proposal' else support
        raw = dict(target_kind=kind, support_type=support or 'unresolved',
            after=dict(name=source.get('label', source.get('predicate', '')), definition=source.get('definition', ''),
                       inclusion=source.get('conditions', ''), exclusion=source.get('exceptions', '')),
            evidence_refs=[_ref(e, blocks) for e in source.get('evidence_refs', [])],
            cq_ids=source.get('cq_ids', []), scope_item_ids=source.get('scope_item_ids', []),
            rationale=source.get('abstraction_level', '') if concept else 'A2 관계 분석 제안; 사람 의미 검수 필요',
            qualifiers=dict(scope=source.get('conditions', ''), time=source.get('time', ''),
                negation=source.get('negation', 'unknown'),
                statement_type=('design_proposal' if support=='design_proposal' else 'definition') if concept else source['statement_type']),
            unresolved_issues=source.get('review_signals', []))
        if not concept:
            raw['after'].update(domain_id=source['subject'], range=source['object'], direction=source['direction'])
            raw['after']['definition'] = ' '.join(source[k] for k in ('subject','predicate','object'))
        matches = [a for a in alignments if a['observation_ref']==source['id']] if concept else []
        origin = dict(candidate_id=source['id'], local_ref=source.get('local_ref'),
                      validation=source.get('validation', []), direction=source.get('direction'), alignments=deepcopy(matches))
        if matches:
            match = matches[0]
            target = base.get(match['target_id'])
            meaning = match.get('meaning', 'uncertain') if len(matches)==1 else 'uncertain'
            if meaning in {'same', 'changed'} and target and target['kind']==kind and not target.get('deprecated'):
                raw.update(operation='update', target_id=target['id'])
                before = {k:deepcopy(v) for k,v in target.items() if k in AFTER_FIELDS[kind]}
                if meaning=='same':
                    raw['after'] = before
                    raw['qualifiers'] = deepcopy(target.get('qualifiers', {}))
                    origin['change_intent'] = 'evidence_only'
                else:
                    raw['after'] = dict(before, definition=source['definition'], inclusion=source.get('conditions', ''), exclusion=source.get('exceptions', ''))
                    origin['change_intent'] = 'meaning_change'
                # Keep old evidence and the separate new observation; accepting remains a human decision.
                prior_refs = [_ref(e, blocks) for e in target.get('evidence_refs', [])]
                raw['evidence_refs'] = prior_refs + [e for e in raw['evidence_refs'] if e not in prior_refs]
                raw['cq_ids'] = list(dict.fromkeys(raw['cq_ids'] + [i for i in target.get('cq_ids', []) if i in {q['id'] for q in run['cqs']}]))
                raw['rationale'] += '; 기존 정의 대응: ' + match['reason']
            elif meaning!='distinct':
                raw['support_type']='unresolved'
                raw['unresolved_issues']=[*raw['unresolved_issues'], '기존 정의와 동일/변경/별개인지 확인 필요']
                origin['change_intent']='alignment_pending'
        row = _make(raw, base, origin)
        if origin.get('change_intent')=='alignment_pending': row['review_status']='deferred'
        previous = next((c for c in rows if c['target_id']==row['target_id'] and
            c['origin'].get('change_intent')==origin.get('change_intent')=='evidence_only'), None)
        if previous:
            previous['evidence_refs'] += [e for e in row['evidence_refs'] if e not in previous['evidence_refs']]
            previous['origin'].setdefault('additional_observations', []).append(deepcopy(source))
            previous['origin']['alignments'].extend(deepcopy(matches))
            previous['cq_ids'] = list(dict.fromkeys(previous['cq_ids']+row['cq_ids']))
            previous['scope_item_ids'] = list(dict.fromkeys(previous['scope_item_ids']+row['scope_item_ids']))
            row = previous
        else:
            rows.append(row)
        mapping[source['id']] = dict(change_id=row['change_id'], target_id=row['target_id'], local_ref=source.get('local_ref'))
    def target(identifier):
        return mapping.get(identifier, {}).get('target_id', identifier)
    for row in rows:
        if row['target_kind']=='relation':
            row['after']['domain_id'] = target(row['after']['domain_id'])
            row['after']['range'] = target(row['after']['range'])
    hierarchies = {h['id']:h for t in result.get('taxonomy', []) for h in t.get('hierarchies', [])}
    for revision in result.get('revisions', []):
        for h in revision.get('effective_hierarchies', []):
            hierarchies[h['id']] = h
    for h in hierarchies.values():
        matches = [check for c in result.get('critiques', []) for check in c.get('hierarchy_checks', [])
            if all(check.get(k)==h.get(k) for k in ('child_ref','parent_ref','relation'))]
        review = dict(builder={k:deepcopy(h[k]) for k in ('a_to_b','b_to_a')}, critic=deepcopy(matches),
                      review_status='unreviewed', possible_equivalence=False)
        evs, counters = set(), set()
        for check in [h, *matches]:
            for direction in ('a_to_b', 'b_to_a'):
                evs.update(check[direction]['evidence_ids']); counters.update(check[direction]['counter_evidence_ids'])
        endpoints = [c for c in rows if c['target_id'] in {target(h['child_ref']),target(h['parent_ref'])}]
        endpoint_values = endpoints + [base[i] for i in (h['child_ref'], h['parent_ref']) if i in base]
        row = _make(dict(target_kind='hierarchy', after=dict(child_id=target(h['child_ref']), parent_id=target(h['parent_ref']), relation=h['relation']),
            evidence_refs=[_ref({'evidence_id':i}, blocks) for i in sorted(evs)],
            counter_evidence_refs=[_ref({'evidence_id':i}, blocks) for i in sorted(counters)],
            support_type='design_proposal', cq_ids=sorted({q for c in endpoint_values for q in c.get('cq_ids', [])}),
            scope_item_ids=sorted({q for c in endpoint_values for q in c.get('scope_item_ids', [])}),
            qualifiers=dict(statement_type='design_proposal'), rationale='A2 Builder의 제안 계층; 명시적 포함 여부는 사람 검수 필요', hierarchy_review=review),
            base, dict(candidate_id=h['id'], validation=h.get('validation', [])))
        rows.append(row); mapping[h['id']] = dict(change_id=row['change_id'], target_id=row['target_id'])
    by_id = {c['id']:c for c in observations}
    for taxonomy in result.get('taxonomy', []):
        for n, alias in enumerate(taxonomy.get('alias_proposals', [])):
            source = by_id.get(alias['observation_ref'], {})
            row = _make(dict(target_kind='alias', after=dict(name=source.get('label', ''), alias_of=target(alias['target_id'])),
                evidence_refs=[_ref(e, blocks) for e in source.get('evidence_refs', [])],
                support_type='design_proposal', qualifiers=dict(statement_type='design_proposal'),
                cq_ids=source.get('cq_ids', []), scope_item_ids=source.get('scope_item_ids', []), rationale=alias['reason']),
                base, dict(unit_id=taxonomy['unit_id'], alias_proposal=alias))
            rows.append(row)
            mapping[f"{taxonomy['unit_id']}:alias:{n}"] = dict(change_id=row['change_id'], target_id=row['target_id'])
    for row in rows:
        identifier = row['origin'].get('candidate_id')
        identifiers = {identifier, *[c['id'] for c in row['origin'].get('additional_observations', [])]}
        deferrals = result.get('revision_deferrals', []) + [d for r in result.get('revisions', []) for d in r.get('deferred', [])]
        for deferred in deferrals:
            if deferred['candidate_ref'] in identifiers:
                row['review_status']='deferred'; row['unresolved_issues'].append(deepcopy(deferred))
        row['origin']['revision_history'] = [deepcopy(h) for h in result.get('revision_history', []) if h['candidate_id'] in identifiers]
        row['origin']['critiques'] = [deepcopy(i) for c in result.get('critiques', []) for i in c.get('issues', []) if i.get('candidate_ref') in {'',*identifiers}]
        row['origin']['relation_checks'] = [deepcopy(i) for c in result.get('critiques', []) for i in c.get('relation_checks', []) if i.get('candidate_ref')==identifier]
        counter_refs = [_ref({'evidence_id':e}, blocks) for issue in row['origin']['critiques']
                        if issue.get('candidate_ref') in identifiers for e in issue.get('counter_evidence_ids', [])]
        counter_refs += [_ref({'evidence_id':i['evidence_id'],'quote':i['quote']}, blocks)
                        for i in row['origin']['relation_checks'] if i['judgment']=='refuted' and i.get('quote')]
        for ref in counter_refs:
            if ref not in row['counter_evidence_refs']:
                row['counter_evidence_refs'].append(ref)
        review_units = {c['unit_id'] for c in result.get('critiques', []) if any(
            i in linked for field, linked in [('issues',row['origin']['critiques']),
                ('relation_checks',row['origin']['relation_checks']),('hierarchy_checks',row['hierarchy_review'].get('critic',[]))]
            for i in c.get(field, []))}
        units = [u for u in run.get('analysis_units', [])
            if u['id'] in review_units or u['id']==row['origin'].get('unit_id')
            or any(c.get('id') in identifiers for field in ('observations','relations','hierarchies','effective_hierarchies') for c in u.get('output', {}).get(field, []))
            or any(h.get('candidate_id') in identifiers for h in u.get('output', {}).get('history', []))]
        row['origin']['analysis_unit_ids'] = [u['id'] for u in units]
        row['origin']['dependency_block_ids'] = sorted({i for u in units for i in u.get('dependency_ids', [])})
    return rows, references, mapping


def publish(service, run_id):
    """Idempotent conversion of a terminal A2 run. No parse/model call or source mutation."""
    repo = service.repository
    with service.lock, repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute("SELECT payload FROM changesets WHERE json_extract(payload,'$.run_id')=? AND json_extract(payload,'$.payload_version')=2", (run_id,)).fetchone()
        if existing:
            return {'changeset_id':json.loads(existing['payload'])['id']}
        run = repo.get(db, 'runs', run_id)
        if run.get('discovery_mode')!='analyze' or run['status'] not in {'partial','failed','cancelled','review_ready'} or not run.get('result'):
            raise ValueError('저장 결과가 있는 종료된 A2 분석 실행이 필요합니다.')
        change = dict(id=uuid4().hex, kind='ontology', payload_version=2, revision=0, created_at=_now(), run_id=run_id,
            lineage_id=run['lineage_id'], base_ontology_version_id=run.get('base_ontology_version_id'),
            ontology_version_id=None, reviewed_ontology_version_id=None, input_status=run['status'],
            analysis_result=deepcopy(run['result']), original_candidates=[], candidates=[], review_status={},
            metamodel=deepcopy(canonical.METAMODEL), optional_patterns=deepcopy(canonical.OPTIONAL_PATTERNS))
        base = _base(repo, db, change)
        if base and base['status']!='reviewed':
            raise ValueError('검토된 기준 버전만 사용합니다.')
        rows, references, mapping = _convert(run, canonical.targets(base), _blocks(repo, db, run))
        change.update(candidates=rows, original_candidates=deepcopy(rows), reference_material=references, id_mapping=mapping)
        db.execute('INSERT OR IGNORE INTO ontology_heads VALUES(?,?)', (change['lineage_id'], change['base_ontology_version_id']))
        _validate(repo, db, change, run, base)
        # Candidate errors are persisted before any LinkML compilation is attempted.
        _insert(db, 'changesets', change)
        run['changeset_id'] = change['id']; repo.save(db, 'runs', run)
    return {'changeset_id':change['id']}


def _contains(value, identifier):
    if isinstance(value, dict):
        return any(_contains(v, identifier) for v in value.values())
    if isinstance(value, list):
        return any(_contains(v, identifier) for v in value)
    return value == identifier


def _impact(repo, db, identifier, base_targets):
    from .extraction_contract import PROFILE
    result = [dict(id='ontology:'+i, kind=t['kind'], target_id=i, frozen=False)
              for i,t in base_targets.items() if identifier in canonical.references(t) and not t.get('deprecated')]
    if identifier in PROFILE['definitions'] or _contains(PROFILE['definitions'], identifier):
        result.append(dict(id='mapping:'+PROFILE['version']+':'+identifier, kind='extraction_mapping', frozen=False))
    entities, link_ids = {}, set()
    runs = {r['id']: json.loads(r['payload']) for r in db.execute("SELECT id,payload FROM runs WHERE json_extract(payload,'$.kind')='extract'")}

    def entity_matches(entity_id, value):
        # The official identity's global type cannot override a frozen v2 role.
        entity = entities.get(entity_id, {})
        run = runs.get(value.get('run_id'), {})
        contract = run.get('consumer_contract', {})
        if entity.get('namespace', '').startswith('LH:') and (contract or run.get('ontology_payload_version') == 2):
            return identifier == contract.get('role_targets', {}).get(entity['namespace'])
        return identifier == entity.get('concept_id')

    # ponytail: direct ID scan of the small ledger; index reference fields if the pilot grows.
    for table in ('entities','entity_links','assertions','snapshots','runs'):
        for row in db.execute(f'SELECT id,payload FROM {table}'):
            value = json.loads(row['payload'])
            if table=='runs' and value.get('kind')!='extract':
                continue
            if table=='snapshots':
                linked = identifier in canonical.targets(value.get('ontology'))
            elif table=='runs':
                linked = any(identifier in {d['id'], d.get('domain_id'), d.get('range')} for d in value.get('ontology_candidates', []))
            elif table=='entity_links':
                linked = (identifier==value['concept_id'] if value.get('concept_id')
                          else entity_matches(value.get('target_entity_id'), value))
                if linked: link_ids.add(row['id'])
            elif table=='assertions':
                linked = (identifier==value.get('predicate_id')
                    or any(value.get(k) in link_ids for k in ('subject_link_id','object_link_id'))
                    or any(not value.get(link) and entity_matches(value.get(entity), value)
                           for link, entity in (('subject_link_id','subject_id'),('object_link_id','object_entity_id'))))
            else:
                entities[row['id']] = value
                linked = identifier == value.get('concept_id')
            if linked:
                result.append(dict(id=table+':'+row['id'], kind=table, frozen=table in {'snapshots','runs'}))
    for row in db.execute("SELECT id,payload FROM decisions WHERE json_extract(payload,'$.kind')='lh_consumer_mapping'"):
        value=json.loads(row['payload'])
        if identifier in value.get('target_ids',{}).values():
            result.append(dict(id='mapping_review:'+row['id'],kind='extraction_mapping',frozen=True))
    return result


def _consumer_fingerprint(candidate):
    return canonical.digest({k:candidate[k] for k in ('target_id','target_kind','operation','after','qualifiers')})


def _consumer_impact(candidate, references):
    before=candidate['before'] or {}
    previous=Definition.model_validate({k:v for k,v in before.items() if k in Definition.model_fields}).model_dump()
    updated=dict(previous,**candidate['after'])
    qualifiers=Qualifiers.model_validate(before.get('qualifiers',{})).model_dump()
    unchanged=all(previous[k]==updated[k] for k in previous if k!='name') and qualifiers==candidate['qualifiers']
    operation,kind=candidate['operation'],candidate['target_kind']
    if operation in {'merge','deprecate'}:
        action='review_dependencies'
    elif operation=='add' and kind in {'attribute','relation'}:
        action='partial_extract'
    elif (kind=='alias' and operation=='add' and not candidate['qualifiers'].get('scope')
          and not candidate['qualifiers'].get('time') and candidate['qualifiers'].get('negation')!='negated') or (operation=='update' and unchanged):
        action='display_refresh'
    else:
        action='semantic_review'
    external=[r['id'] for r in references if not r['id'].startswith('ontology:')]
    resolution=candidate.get('consumer_resolution',{})
    resolved=(set(resolution.get('reference_ids',[])) if resolution.get('action')=='review_required'
        and resolution.get('fingerprint')==_consumer_fingerprint(candidate) else set())
    unresolved=sorted(set(external)-resolved) if action in {'semantic_review','review_dependencies'} else []
    return dict(action=action,affected_assertion_ids=[r['id'].removeprefix('assertions:') for r in references if r['kind']=='assertions'],
        preserved_run_ids=[r['id'].removeprefix('runs:') for r in references if r['kind']=='runs'],
        preserved_snapshot_ids=[r['id'].removeprefix('snapshots:') for r in references if r['kind']=='snapshots'],
        new_required=action=='partial_extract' and bool(candidate['after'].get('required')),
        existing_records='preserved',new_facts='new_ontology_version_and_k4_review',
        requires_resolution=bool(unresolved),unresolved_reference_ids=unresolved)


def _evidence_errors(repo, db, references, blocks, statuses):
    from .extraction_store import _optional
    errors = []
    for raw in references:
        try:
            e = EvidenceRef.model_validate(raw).model_dump()
            evidence = _optional(repo, db, 'evidence', e['evidence_id'])
            b = blocks[e['block_id']]
            start, end = e['span']
            if (evidence['block_id']!=b['id'] or e['source_version_id']!=b['source_version_id']
                or e['parse_run_id']!=b.get('parse_run_id',b.get('run_id')) or e['locator']!=b['locator']
                or not 0 <= start < end <= len(b['text']) or b['text'][start:end]!=e['quote']
                or not evidence['start_char'] <= start < end <= evidence['end_char']):
                raise ValueError('ID/version/parse/span/quote/locator 불일치')
            if any(statuses.get((kind,i),{}).get('state','allowed')!='allowed' for kind,i in
                   [('evidence',e['evidence_id']),('source_version',e['source_version_id'])]):
                raise ValueError('사용 중단 또는 재검토 근거')
        except (KeyError, ValueError, TypeError) as exc:
            errors.append('evidence: '+str(exc))
    return errors


def _review_candidates(change):
    selected={c['change_id']:c for c in change['candidates'] if c['review_status'] not in {'rejected','deferred'} and not c['validation']['structural_errors']}
    while any(not set(c['dependency_ids']) <= selected.keys() for c in selected.values()):
        selected={i:c for i,c in selected.items() if set(c['dependency_ids']) <= selected.keys()}
    return selected


def _validate(repo, db, change, run, base):
    from .snapshots import _statuses
    blocks, statuses, initial = _blocks(repo, db, run), _statuses(db), canonical.targets(base)
    proposals = change['candidates']
    good = []
    for c in proposals:
        errors = []
        c.pop('consumer_impact',None)
        c['validation'] = dict(structural_errors=errors, semantic_review=['의미 적합성은 사람 검수 대상'], can_accept=False)
        try:
            normalized = OntologyChangeV2.model_validate({k:v for k,v in c.items() if k in OntologyChangeV2.model_fields}).model_dump(mode='json')
            for field in EDITABLE - {'after','hierarchy_review'}:
                c[field] = normalized[field]
            definition = Definition.model_validate(c['after']).model_dump(exclude_unset=True)
            c['after'] = definition
            if c['target_kind']=='hierarchy' and c['operation'] in {'add','update'}:
                HierarchyReview.model_validate(c['hierarchy_review'])
        except ValidationError as exc:
            errors.append('contract: '+str(exc)); continue
        target = initial.get(c['target_id'])
        allowed_fields = ({'canonical_id'} if c['operation']=='merge' else set() if c['operation']=='deprecate' else AFTER_FIELDS[c['target_kind']])
        if set(c['after']) - allowed_fields:
            errors.append('변경 종류에 맞지 않는 정의 필드: '+str(sorted(set(c['after']) - allowed_fields)))
        if c['origin'].get('unknown_target_id'):
            errors.append('존재하지 않는 기존 target_id')
        if c['origin'].get('unsupported_fields'):
            errors.append('지원하지 않는 입력 필드: '+str(c['origin']['unsupported_fields']))
        if c['operation']=='add' and target or c['operation']!='add' and not target:
            errors.append('add/기존 대상 작업 구분 오류')
        if target and (target['kind']!=c['target_kind'] or target.get('deprecated')):
            errors.append('기존 ID 종류 변경 또는 폐기 대상 재사용')
        if c['target_kind'] in {'attribute','relation'} and c['operation'] in {'add','update'}:
            c['after'].setdefault('range', (target or {}).get('range', 'string'))
        if c['target_kind'] in {'class','attribute','relation','vocabulary_concept'} and c['operation'] in {'add','update'}:
            if not c['after'].get('name','').strip() or not c['after'].get('definition','').strip():
                errors.append('명칭과 정의 필요')
        if not c['cq_ids'] and not c['scope_item_ids']:
            errors.append('CQ 또는 범위 연결 필요')
        if not set(c['cq_ids']) <= {x['id'] for x in run['cqs']} or not set(c['scope_item_ids']) <= {x['id'] for x in run.get('scope_items',[])}:
            errors.append('고정 CQ/범위 밖 참조')
        if not c['evidence_refs']:
            errors.append('원문 또는 설계 출처 근거 필요')
        errors.extend(_evidence_errors(repo, db, c['evidence_refs']+c['counter_evidence_refs'], blocks, statuses))
        for i in c['origin'].get('dependency_block_ids', []):
            b=blocks.get(i)
            if not b or any(statuses.get((k,v),{}).get('state','allowed')!='allowed' for k,v in
                           [('evidence',b['evidence_id']),('source_version',b['source_version_id'])]):
                errors.append('A2 파생 입력의 사용 중단/범위 밖 의존'); break
        if not c['rationale'].strip() or c['support_type']=='unresolved':
            errors.append('제안 방식과 이유 미해결')
        if c['support_type']=='design_proposal' and c['qualifiers'].get('statement_type')!='design_proposal':
            errors.append('설계 제안을 원문 의무/사실로 표시할 수 없음')
        if c['qualifiers'].get('statement_type')=='instance':
            errors.append('개별 사실은 K4 검수 대상')
        if c['target_kind']=='alias' and c['operation'] in {'add','update'} and (
                c['qualifiers'].get('scope') or c['qualifiers'].get('time') or c['qualifiers'].get('negation')=='negated'):
            errors.append('조건부/부정 별칭은 무조건 동의어로 투영할 수 없음; 의미 검토 후 보류')
        if c['target_kind']=='relation' and c['operation'] in {'add','update'} and c['after'].get('direction')!='subject_to_object':
            errors.append('A2 관계 방향 미해결')
        if c['target_kind'] in {'relation','hierarchy'} and c['qualifiers'].get('negation')=='negated':
            errors.append('부정된 관계를 양의 스키마 관계로 수락할 수 없음')
        if c['target_kind']=='relation' and c['after'].get('name') in {'is_a','instance_of','broader','related','part_of'}:
            errors.append('계층 종류를 업무 관계 슬롯으로 저장할 수 없음')
        good.append(c)
    # Rejected/deferred/invalid proposals retain history, but do not alter review structure.
    active = [c for c in good if c['review_status'] not in {'rejected','deferred'} and not c['validation']['structural_errors']]
    projected = dict(initial)
    for c in active:
        if c['operation'] in {'add','update'}:
            projected[c['target_id']] = dict(initial.get(c['target_id'], {}), **c['after'])
            projected[c['target_id']].update(id=c['target_id'], kind=c['target_kind'], symbol=c['symbol'])
        elif c['target_id'] in initial:
            projected[c['target_id']] = dict(initial[c['target_id']], deprecated=True,
                replaced_by=c['after'].get('canonical_id') if c['operation']=='merge' else None)
    by_target = {c['target_id']:c for c in active}
    for c in good:
        errors=c['validation']['structural_errors']
        item=projected.get(c['target_id'], {})
        refs=canonical.references(item) if c['operation'] not in {'merge','deprecate'} else set()
        c['dependency_ids']=sorted({by_target[i]['change_id'] for i in refs if i in by_target and i!=c['target_id']})
        for identifier in refs:
            if identifier not in projected or projected[identifier].get('deprecated'):
                errors.append('없는/폐기 참조: '+identifier)
        kind=c['target_kind']; after=item if c['operation'] in {'merge','deprecate'} else c['after']
        if kind in {'attribute','relation'} and projected.get(after.get('domain_id'),{}).get('kind')!='class':
            errors.append('domain은 class ID 필요')
        if kind=='attribute' and after.get('range','string') not in SCALARS:
            errors.append('속성 range는 지원 scalar 필요')
        if kind=='relation' and projected.get(after.get('range'),{}).get('kind')!='class':
            errors.append('관계 range는 class ID 필요')
        if kind=='alias' and (not after.get('name') or projected.get(after.get('alias_of'),{}).get('kind') not in {'class','vocabulary_concept'}):
            errors.append('별칭 명칭과 class/vocabulary 대상 필요')
        if kind=='hierarchy' and c['operation'] in {'add','update'}:
            a,b,relation=after.get('child_id'),after.get('parent_id'),after.get('relation')
            ka,kb=projected.get(a,{}).get('kind'),projected.get(b,{}).get('kind')
            if not a or not b or a==b:
                errors.append('계층 대상 누락 또는 자기 참조')
            expected = {'is_a':('class','class'),'broader':('vocabulary_concept','vocabulary_concept'),
                        'related':('vocabulary_concept','vocabulary_concept'),'part_of':('class','class')}
            if relation=='instance_of':
                errors.append('instance_of는 개체 표본으로 보존; 사실 수락은 K4 필요')
            elif expected.get(relation)!=(ka,kb):
                errors.append('계층 종류/대상 종류 불일치')
            review=c['hierarchy_review']
            judgments=[]
            for role, checks in [('builder',[review.get('builder',{})]),('critic',review.get('critic',[]))]:
                for check in checks:
                    pair=[]
                    for direction in ('a_to_b','b_to_a'):
                        value=check.get(direction,{})
                        judgment=value.get('judgment')
                        if judgment not in {'supported','refuted','unknown'} or not value.get('reason'):
                            errors.append(role+': 양방향 판단/이유 필요')
                        pair.append(judgment)
                        allowed={e['evidence_id'] for e in c['evidence_refs']+c['counter_evidence_refs']}
                        if not set(value.get('evidence_ids',[])+value.get('counter_evidence_ids',[])) <= allowed:
                            errors.append(role+': 판단 근거 연결 오류')
                        if judgment in {'supported','refuted'} and not value.get('evidence_ids') and not value.get('counter_evidence_ids'):
                            errors.append(role+': 판단 근거 필요')
                    judgments.append(pair)
            review['possible_equivalence'] = ['supported','supported'] in judgments
            review['review_status'] = 'unreviewed'
            if review['possible_equivalence']:
                c['validation']['semantic_review'].append('양방향 지지: 동치 검토 가능성, 자동 병합 없음')
            if any('unknown' in p for p in judgments):
                c['validation']['semantic_review'].append('unknown은 반증/비소속이 아님')
        if c['operation']=='merge':
            destination_id = c['after'].get('canonical_id')
            dst=projected.get(destination_id,{})
            if not dst or dst['id']==c['target_id'] or dst['kind']!=kind:
                errors.append('병합 정본 ID/종류 오류')
            else:
                try: canonical.replacement_id(projected, destination_id)
                except ValueError as exc: errors.append(str(exc))
            if destination_id in by_target:
                c['dependency_ids']=sorted(set(c['dependency_ids']+[by_target[destination_id]['change_id']]))
        if c['operation']=='deprecate' and any(t.get('replaced_by')==c['target_id'] for t in initial.values()):
            errors.append('이전 ID의 병합 정본은 대체 ID 없이 폐기할 수 없음')
        impact=_impact(repo,db,c['target_id'],initial) if c['operation']!='add' else []
        if c['operation']=='add' and kind in {'attribute','relation'} and c['after'].get('domain_id') in initial:
            impact=[r for r in _impact(repo,db,c['after']['domain_id'],initial) if not r['id'].startswith('ontology:')]
        c['affected_references']=impact; c['affected_reference_ids']=[i['id'] for i in impact]
        c['consumer_impact']=_consumer_impact(c,impact)
        if c['operation'] in {'merge','deprecate'}:
            if c['consumer_impact']['requires_resolution']:
                errors.append('기존 매핑/사실/snapshot 직접 참조 미해결: 명시 소비자 재검토 처리 또는 보류 필요')
            for incoming in impact:
                if incoming['id'].startswith('ontology:'):
                    referencing = projected[incoming['target_id']]
                    if not referencing.get('deprecated') and c['target_id'] in canonical.references(referencing):
                        errors.append('직접 정의 참조 미해결: '+incoming['id'])
                    elif incoming['target_id'] in by_target:
                        c['dependency_ids']=sorted(set(c['dependency_ids']+[by_target[incoming['target_id']]['change_id']]))
        elif c['consumer_impact']['requires_resolution']:
            errors.append('정의/조건 변경의 기존 소비자 직접 참조 미해결')
        c['diff']={k:dict(before=(c['before'] or {}).get(k),after=v) for k,v in after.items() if (c['before'] or {}).get(k)!=v}
    # Dropping an invalid update restores its base edge, which may expose another cycle.
    while True:
        hierarchy_targets = dict(initial)
        for c in _review_candidates(change).values():
            if c['target_kind']=='hierarchy':
                hierarchy_targets[c['target_id']] = projected[c['target_id']]
        parents={}
        for edge in hierarchy_targets.values():
            if edge['kind']=='hierarchy' and edge.get('relation')=='is_a' and not edge.get('deprecated'):
                parents.setdefault(edge.get('child_id'),set()).add(edge.get('parent_id'))
        invalidated=False
        for c in good:
            errors=c['validation']['structural_errors']
            if not errors and c['operation'] in {'add','update'} and c['target_kind']=='hierarchy' and c['after'].get('relation')=='is_a':
                a,b=c['after'].get('child_id'),c['after'].get('parent_id')
                seen=set(); todo=[b]
                while todo:
                    i=todo.pop()
                    if i in seen: continue
                    seen.add(i);todo.extend(parents.get(i,set()))
                if a in seen: errors.append('is_a 순환')
                if len(parents.get(a,set()))>1: errors.append('is_a 단일 부모 계약; 추가 부모는 보류')
                invalidated = invalidated or bool(errors)
        if not invalidated: break
    ids={c['change_id']:c for c in proposals}
    accepted={c['change_id'] for c in proposals if c['review_status']=='accepted'}
    for c in proposals:
        errors=c['validation']['structural_errors']
        c['validation']['unresolved_dependency_ids']=[i for i in c['dependency_ids'] if i not in accepted]
        c['validation']['can_accept_with_dependencies']=not errors and all(not ids[i]['validation']['structural_errors'] for i in c['dependency_ids'])
        c['validation']['can_accept']=c['validation']['can_accept_with_dependencies'] and not c['validation']['unresolved_dependency_ids'] and c['review_status'] not in {'rejected','deferred'}
    change['review_status']={c['change_id']:c['review_status'] for c in proposals}
    change['unresolved_count']=sum(c['review_status'] in {'unreviewed','deferred'} for c in proposals)


def view(service, change):
    with service.repository.connect() as db:
        run=service.repository.get(db,'runs',change['run_id'])
        base=_base(service.repository,db,change)
        _validate(service.repository,db,change,run,base)
        change['ontology_head_id']=_head(db,change['lineage_id'])
        change['decisions']=[json.loads(r['payload']) for r in db.execute(
            "SELECT payload FROM decisions WHERE json_extract(payload,'$.changeset_id')=? ORDER BY rowid", (change['id'],))]
    change['candidates']=[dict(c, id=c['change_id'], kind=c['target_kind'], changeset_id=change['id'],
                               can_accept=c['validation']['can_accept']) for c in change['candidates']]
    return change


def add(service, changeset_id, request):
    request=AddOntologyChanges.model_validate(request)
    repo=service.repository
    with service.lock,repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        change=repo.get(db,'changesets',changeset_id)
        if change.get('payload_version')!=2: raise ValueError('v2 변경 묶음 필요')
        if request.expected_changeset_revision!=change['revision']: raise VersionConflict('후보 revision 충돌')
        base=_base(repo,db,change); initial=canonical.targets(base)
        for raw in request.candidates:
            c=_make(raw,initial,dict(actor=request.actor,reason=request.reason,raw_proposal=raw))
            if any(x['target_id']==c['target_id'] for x in change['candidates']):
                raise ValueError('같은 대상의 변경은 기존 후보를 수정해야 합니다.')
            change['candidates'].append(c);change['original_candidates'].append(deepcopy(c))
        change['revision']+=1
        _validate(repo,db,change,repo.get(db,'runs',change['run_id']),base)
        repo.save(db,'changesets',change)
    return {'changeset_id':changeset_id,'changeset_revision':change['revision']}


def _accepted_projection(repo,db,change,run,base):
    chosen=[deepcopy(c) for c in change['candidates'] if c['review_status']=='accepted']
    closed=dict(change,candidates=chosen)
    _validate(repo,db,closed,run,base)
    errors=[(c['change_id'],c['validation']['structural_errors']) for c in chosen if c['validation']['structural_errors']]
    if errors: raise ValueError('수락 집합 오류: '+str(errors))
    items=canonical.project(base,chosen)
    for item in items.values():
        if item.get('deprecated'): continue
        for identifier in canonical.references(item):
            if identifier not in items or items[identifier].get('deprecated'):
                raise ValueError('직접 의존 변경을 함께 수락하거나 보류해야 합니다: '+identifier)
    return chosen,items


def preview(service, changeset_id):
    with service.repository.connect() as db:
        change=service.repository.get(db,'changesets',changeset_id)
        if change.get('payload_version')!=2: raise ValueError('v2 변경 묶음 필요')
        base=_base(service.repository,db,change)
        run=service.repository.get(db,'runs',change['run_id'])
        _validate(service.repository,db,change,run,base)
        selected=_review_candidates(change)
        try:
            compiled,derived,slots=canonical.build(base,canonical.project(base,list(selected.values())))
            return dict(changeset_id=changeset_id,changeset_revision=change['revision'],status='unreviewed_preview',
                included_change_ids=list(selected), excluded_change_ids=[c['change_id'] for c in change['candidates'] if c['change_id'] not in selected],
                **compiled,json_schema=derived,effective_class_slots=slots)
        except (ValueError,KeyError,TypeError) as exc:
            return dict(changeset_id=changeset_id,status='invalid_preview',error=str(exc),included_change_ids=list(selected))


def decide(service, changeset_id, request):
    request=DecisionRequest.model_validate(request)
    if 'expected_ontology_head_id' not in request.model_fields_set:
        raise ValueError('v2는 expected_ontology_head_id(null 포함)가 필요합니다.')
    if any(d.action=='unlink' or not d.reason.strip() for d in request.decisions):
        raise ValueError('v2 결정은 사유가 필요하며 unlink는 지원하지 않습니다.')
    if len({d.candidate_id for d in request.decisions})!=len(request.decisions):
        raise ValueError('중복 후보 결정')
    if any(d.consumer_action for d in request.decisions) and not request.actor.strip():
        raise ValueError('소비자 재검토 처리자는 공백일 수 없습니다.')
    repo=service.repository
    with service.lock,repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        change=repo.get(db,'changesets',changeset_id)
        if request.expected_changeset_revision!=change['revision']: raise VersionConflict('후보 revision 충돌')
        head=_head(db,change['lineage_id'])
        if request.expected_ontology_head_id!=head: raise VersionConflict('온톨로지 head 충돌; 최신 기준 비교 필요')
        base=_base(repo,db,change);run=repo.get(db,'runs',change['run_id'])
        before=deepcopy(change)
        proposals={c['change_id']:c for c in change['candidates']}
        for d in request.decisions:
            if d.candidate_id not in proposals: raise ValueError('이 묶음에 없는 후보')
            c=proposals[d.candidate_id]
            if d.patch:
                if d.action not in {'modify','edit'} or not set(d.patch)<=EDITABLE:
                    raise ValueError('수정 필드/작업 오류; 서버 ID는 수정 불가')
                c.update(deepcopy(d.patch));c['origin']['human_edited']=True
            c['review_status']={'accept':'accepted','modify':'accepted','edit':'unreviewed','defer':'deferred','reject':'rejected'}[d.action]
        _validate(repo,db,change,run,base)
        for d in request.decisions:
            if not d.consumer_action: continue
            c=proposals[d.candidate_id]
            impact=c.get('consumer_impact',{})
            references=[r['id'] for r in c.get('affected_references',[]) if not r['id'].startswith('ontology:')]
            if d.action not in {'accept','modify'} or impact.get('action') not in {'semantic_review','review_dependencies'} or not references:
                raise ValueError('소비자 재검토는 직접 참조가 있는 의미/폐기/병합 변경의 수락에만 지정할 수 있습니다.')
            c['consumer_resolution']=dict(action=d.consumer_action,fingerprint=_consumer_fingerprint(c),
                actor=request.actor,reason=d.reason,reference_ids=references,assertion_ids=impact['affected_assertion_ids'],
                preserved_run_ids=impact['preserved_run_ids'],preserved_snapshot_ids=impact['preserved_snapshot_ids'],
                existing_records='preserved',new_facts='new_ontology_version_and_k4_review')
        if any(d.consumer_action for d in request.decisions):
            _validate(repo,db,change,run,base)
        accepted=lambda value:[{k:v for k,v in c.items() if k not in {'validation','diff','affected_references','affected_reference_ids','consumer_impact'}}
            for c in value['candidates'] if c['review_status']=='accepted']
        if accepted(before)!=accepted(change):
            if head not in {change['base_ontology_version_id'],change['reviewed_ontology_version_id']}:
                raise VersionConflict('다른 변경 묶음이 head를 갱신했습니다. 새 기준에서 재작성해야 합니다.')
            chosen,items=_accepted_projection(repo,db,change,run,base)
            compiled,_,_=canonical.build(base,items)
            version=dict(compiled,id=uuid4().hex,created_at=_now(),status='reviewed',run_id=run['id'],
                changeset_id=changeset_id,parent_version_id=head,lineage_id=change['lineage_id'],
                scope=run['frozen_input']['scope'],step=run['frozen_input']['step'],accepted_change_ids=[c['change_id'] for c in chosen])
            _insert(db,'ontology_versions',version)
            head=version['id']
            db.execute('UPDATE ontology_heads SET reviewed_version_id=? WHERE lineage_id=?',(head,change['lineage_id']))
            change['reviewed_ontology_version_id']=head;change['ontology_version_id']=head
        from .snapshots import _statuses, mark_changed
        for d in request.decisions:
            if not d.consumer_action: continue
            resolution=proposals[d.candidate_id]['consumer_resolution']
            statuses=_statuses(db)
            resolution['marked_assertion_ids']=[i for i in resolution['assertion_ids']
                if statuses.get(('assertion',i),{}).get('state','allowed')=='allowed']
            mark_changed(db,resolution['assertion_ids'],request.actor,d.reason)
            resolution['ontology_version_id']=head
        change['revision']+=1
        for d in request.decisions:
            previous=next(c for c in before['candidates'] if c['change_id']==d.candidate_id)
            _insert(db,'decisions',dict(id=uuid4().hex,changeset_id=changeset_id,revision=change['revision'],
                actor=request.actor,created_at=_now(),ontology_version_id=head,**d.model_dump(),
                before=previous,after=deepcopy(proposals[d.candidate_id])))
        repo.save(db,'changesets',change)
    return dict(changeset_id=changeset_id,changeset_revision=change['revision'],ontology_head_id=head,
                reviewed_ontology_version_id=change['reviewed_ontology_version_id'],items=view(service,change)['candidates'])

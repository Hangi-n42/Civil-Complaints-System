"""Bounded A2 roles on A1 evidence and the existing serial executor. No ontology writes."""
import asyncio
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

import httpx

from app.core.config import settings
from app.generation.service import GenerationService, local_ollama_url
from . import discovery_run as grounding, discovery_models as models, discovery_profile as profile, discovery_segments as segments, discovery_review as reviews, discovery_design as design
from .service import KnowledgeConflict, encode, utcnow
from . import discovery_candidates as identities

PROMPT_VERSION = 'discovery-a2-v40'


def recipe(budgets):
    return dict(profile_version='a2-survey-v5', candidate_version=identities.VERSION, prompt_version=PROMPT_VERSION, prompt_hash=profile.digest([models.COMMON, models.PROMPTS]),
        models=dict(draft=settings.STRUCTURING_MODEL, review=settings.KNOWLEDGE_REVIEW_MODEL),
        endpoint=local_ollama_url(settings.OLLAMA_BASE_URL), budgets=budgets,
        num_ctx=32768, num_predict=4096, think=False, input_chars=24000,
        call_timeout=settings.KNOWLEDGE_DESIGN_TIMEOUT,
        schema_hash=profile.digest({k: v.model_json_schema() for k, v in models.OUTPUTS.items()}))


def model_identity(current):
    """Read installed model identity/context only; never pull a model or follow a redirect."""
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=15) as client:
        response = client.get(current['endpoint'] + '/api/tags'); response.raise_for_status()
        installed = {m['name']: m for m in response.json()['models']}
        result = {}
        for role, name in current['models'].items():
            if name not in installed:
                raise ValueError('설치된 로컬 모델이 없습니다: ' + name)
            response = client.post(current['endpoint'] + '/api/show', json={'model': name})
            response.raise_for_status()
            lengths = [int(v) for k, v in response.json().get('model_info', {}).items() if k.endswith('.context_length')]
            if not lengths or min(lengths) < current['num_ctx']:
                raise ValueError('모델의 선언 컨텍스트가 실행 설정보다 작거나 확인 불가합니다.')
            result[role] = dict(name=name, digest=installed[name]['digest'], context_length=min(lengths))
        return result


def load_blocks(service, run):
    blocks = []
    with service.repository.connect() as db:
        for file, unit in zip(run['frozen_input']['files'], run['units']):
            blocks.extend(dict(b, file_id=file['file_id'], title=file['title'], role=file.get('role'),
                source_group=file['manifest_source_id'], source_id=file['source_id'], block_index=n)
                for n,b in enumerate(grounding._blocks(service, db, file, unit)))
    return blocks


def allowed_ids(service, blocks):
    from .snapshots import _statuses
    with service.repository.connect() as db:
        statuses = _statuses(db)
    return {b['id'] for b in blocks if grounding._available(b, b, statuses)}


def _base(service, request, frozen):
    if not request.base_ontology_version_id:
        return None, []
    from .ontology_schema import get_ontology
    base = get_ontology(service, request.base_ontology_version_id)
    if base['review_status'] != 'reviewed':
        raise ValueError('승인 기준은 검토된 온톨로지 버전이어야 합니다.')
    if frozen['scope'] == 'historical_change' and frozen['step'] == 0:
        raise ValueError('역사 최초 단계는 빈 회사 기준이어야 합니다.')
    versions = {f['source_version_id'] for f in frozen['files']}
    with service.repository.connect() as db:
        origin = service.repository.get(db, 'runs', base['run_id'])
        prior = origin.get('frozen_input')
        if frozen['scope'] == 'historical_change':
            if not prior or prior['scope'] != 'historical_change' or prior['step'] > frozen['step'] or origin.get('lineage_id') != (request.lineage_id or frozen['bundle_id'] + ':historical'):
                raise ValueError('역사 기준 버전의 계보·scope/step이 일치하지 않습니다.')
        elif prior and prior['scope'] == 'historical_change':
            raise ValueError('역사 기준을 현재 업무에 섞을 수 없습니다.')
        for candidate in base['candidates']:
            if not candidate['evidence']:
                raise ValueError('기준 정의에 근거가 없습니다.')
            for ev in candidate['evidence']:
                evidence = service.repository.get(db, 'evidence', ev['evidence_id'])
                block = service.repository.get(db, 'blocks', evidence['block_id'])
                if block['source_version_id'] not in versions:
                    raise ValueError('기준 온톨로지의 근거가 선택 입력 범위 밖입니다.')
    frozen_base = {k: base[k] for k in ('id', 'linkml_yaml', 'status', 'run_id')}
    if base.get('payload_version') == 2:
        frozen_base.update(vocabulary_registry=base['vocabulary_registry'], version_hash=base['version_hash'])
    return frozen_base, base['candidates']


def start(service, request):
    allowed = {'kind', 'retry_of_run_id', 'discovery_mode'} if request.retry_of_run_id else {
        'kind', 'discovery_mode', 'input_run_id', 'cqs', 'scope_items', 'baseline_version',
        'lineage_id', 'base_ontology_version_id', 'discovery_budgets', 'analysis_block_ids', 'analysis_selection_reason'}
    if request.model_fields_set - allowed:
        raise ValueError('A2는 A1 input_run_id와 분석 설정 또는 변경 없는 재개만 받습니다.')
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('실행 중이거나 종료 중인 작업이 있습니다.')
        if request.retry_of_run_id:
            run = service.repository.get(db, 'runs', request.retry_of_run_id)
            if run.get('discovery_mode') != 'analyze':
                raise ValueError('A2 분석 실행만 재개할 수 있습니다.')
            if run['recipe'] != recipe(run['recipe']['budgets']):
                raise ValueError('모델·프롬프트·예산이 변경되었습니다. 새 실행이 필요합니다.')
            if run['status'] not in {'failed', 'partial', 'cancelled', 'review_ready'}:
                raise ValueError('종료된 분석 실행만 재개할 수 있습니다.')
            run['reused_units'] = [u['id'] for u in run['analysis_units'] if u['status'] == 'succeeded']
            for unit in run['analysis_units']:
                if unit['status'] != 'succeeded' and not (unit['attempts'] and (unit['stage']=='revision' or ':recovery_' in unit['id'])):
                    unit.update(status='queued', error=None)
            run.pop('error', None)
        else:
            if not request.input_run_id:
                raise ValueError('A1 input_run_id가 필요합니다.')
            source = service.repository.get(db, 'runs', request.input_run_id)
            if source['kind'] != 'discovery' or source.get('discovery_mode') == 'analyze' or source['status'] not in {'succeeded', 'partial', 'failed'}:
                raise ValueError('종료된 A1 입력 준비 실행 ID가 필요합니다.')
            cqs, scope_items = [v.model_dump() for v in request.cqs], [v.model_dump() for v in request.scope_items]
            if not cqs and not scope_items:
                raise ValueError('CQ 또는 명시적인 업무 범위 항목이 필요합니다.')
            for values in (cqs, scope_items):
                if len({c['id'] for c in values}) != len(values) or any(not c['question'].strip() for c in values):
                    raise ValueError('CQ/범위 ID는 고유하고 내용은 비어 있지 않아야 합니다.')
            frozen = source['frozen_input']
            base, candidates = _base(service, request, frozen)
            pinned = {i for u in source['units'] for i in u.get('block_ids', [])}
            if any(e['evidence_id'] not in pinned for c in candidates for e in c['evidence']):
                raise ValueError('기준 근거는 A1에 고정된 parse/block을 사용해야 합니다.')
            if request.analysis_block_ids is not None and (not set(request.analysis_block_ids) <= pinned or not request.analysis_selection_reason.strip()):
                raise ValueError('분석 선택은 A1 고정 블록과 명시적인 선택 이유가 필요합니다.')
            run = dict(kind='discovery', discovery_mode='analyze', input_run_id=source['id'],
                frozen_input=frozen, units=source['units'], input_version_ids=source['input_version_ids'],
                cqs=cqs, scope_items=scope_items, baseline_version=request.baseline_version,
                analysis_block_ids=request.analysis_block_ids, analysis_selection_reason=request.analysis_selection_reason,
                lineage_id=request.lineage_id or frozen['bundle_id'] + ':' + ('historical' if frozen['scope']=='historical_change' else 'current'),
                base_ontology_version_id=request.base_ontology_version_id, base_ontology=base, base_candidates=candidates,
                recipe=recipe(models.Budgets.model_validate(request.discovery_budgets).model_dump()),
                analysis_units=[], tool_events=[], search_cache={}, extra_requests=[],
                metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0, searches=0))
        run.update(id=uuid4().hex, retry_of_run_id=request.retry_of_run_id, status='queued',
                   stage='analysis', started_at=None, finished_at=None, stop_reason=None)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    service.executor.submit(execute, service, run['id'])
    return dict(run_id=run['id'], status='queued')


def save(service, run):
    with service.lock, service.repository.connect() as db:
        live = service.repository.get(db, 'runs', run['id'])
        if live['status'] == 'cancel_requested':
            run['status'] = 'cancel_requested'
        service.repository.save(db, 'runs', run)


def cancelled(service, run):
    if service.run(run['id'])['status'] == 'cancel_requested':
        run['status'] = 'cancel_requested'
        return True
    return False


def lookup(service, run, label, term_type, blocks):
    allowed = allowed_ids(service, blocks)
    identities.register(run)
    def usable(candidate):
        ids = {e['evidence_id'] for e in candidate.get('evidence', [])} | set(candidate.get('evidence_ids', []))
        return bool(ids) and ids <= allowed
    candidates = [dict(c, review_status='reviewed') for c in run['base_candidates'] if usable(c)]
    rows = {}
    for u in run['analysis_units']:
        if u['status']!='succeeded' or not set(u['dependency_ids']) <= allowed: continue
        for c in u.get('output', {}).get('observations', []):
            if not identities.dependencies(run,c['id']) <= allowed: continue
            candidate = identities.view(run,c)
            rows.setdefault(candidate['id'], dict(candidate, origin_dependency_ids=sorted(set(u['dependency_ids']) | identities.dependencies(run,c['id']))))
        for h in u.get('output', {}).get('history', []):
            if 'classification' in h['after']:
                candidate = identities.view(run,h['after'],revised=True)
                rows[candidate['id']] = dict(candidate, origin_dependency_ids=u['dependency_ids'])
    blocked_revisions = {identities.identifier(run,h['candidate_id']) for u in run['analysis_units'] if u['status']=='succeeded' and not set(u.get('dependency_ids', [])) <= allowed for h in u.get('output', {}).get('history', [])}
    candidates += [c for c in rows.values() if c['id'] not in blocked_revisions and usable(c) and not c['validation'] and not c['outside_scope_reason']]
    return [c for c in candidates if label.casefold() in (c.get('label') or c.get('name', '')).casefold()
            and (term_type=='any' or c.get('classification', {'concept':'type', 'attribute':'property_value'}.get(c.get('kind'))) == term_type)]


def search(service, run, index, blocks, query, purpose):
    key = profile.digest(query)
    allowed = allowed_ids(service, blocks)
    if key in run['search_cache']:
        hits = [h for h in run['search_cache'][key] if h['block_id'] in allowed]
        reused = True
    else:
        if run['metrics']['searches'] >= run['recipe']['budgets']['searches']:
            raise ValueError('검색 예산 종료')
        run['metrics']['searches'] += 1
        save(service, run)
        hits = index.search(query, allowed)
        run['search_cache'][key] = hits
        reused = False
    run['tool_events'].append(dict(action='search', query=query, purpose=purpose,
        block_ids=[h['block_id'] for h in hits], reused=reused, at=utcnow()))
    save(service, run)
    return [h['block_id'] for h in hits]


def dispatch(service, run, index, blocks, action, analysis_request=False):
    action = models.Action.model_validate(action)
    if action.action == 'read':
        group = next((g for g in run['frontier'] if g['id']==action.unit_id), None)
        if group is None:
            raise ValueError('실행 범위 밖 unit_id')
        ids = group['block_ids']
        if not set(ids) <= allowed_ids(service, blocks):
            raise ValueError('사용 중단된 원문')
        result = dict(block_ids=ids)
    elif action.action in {'search', 'request_evidence'}:
        if action.action == 'request_evidence' and action.issue_id not in issue_ids(run):
            raise ValueError('추가 근거 요청의 쟁점 ID 불일치')
        result = dict(block_ids=search(service, run, index, blocks, action.query, action.action),
                      issue_id=action.issue_id)
        if not result['block_ids']:
            result['gap'] = '자료 필요: 선택 입력에 검색 근거 없음; 외부 다운로드하지 않음'
    elif action.action == 'lookup_term':
        result = dict(terms=lookup(service, run, action.label, action.term_type, blocks), block_ids=[])
    else:
        result = dict(reason=action.reason, block_ids=[])
    run['tool_events'].append(dict(**action.model_dump(), result=result, at=utcnow()))
    if result.get('block_ids'):
        run['extra_requests'].append(dict(block_ids=result['block_ids'], reason=action.reason,
            purpose='analysis' if analysis_request else 'comparison'))
    save(service, run)
    return result


def packet(ids, by_id, context_map):
    complete = list(dict.fromkeys(i for bid in ids for i in context_map[bid]['block_ids']))
    return [dict(ref=i, text=by_id[i]['text'], locator=by_id[i]['locator'], title=by_id[i]['title'],
                 source_role=by_id[i]['role'], table_context={k:v for k,v in context_map[i].items() if k!='block_ids'}) for i in complete]


def compact(value, originals=None):
    if originals is None:
        originals = {}
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, list): pending.extend(item)
            elif isinstance(item, dict):
                if isinstance(item.get('ref'), str) and isinstance(item.get('text'), str):
                    originals[item['ref']] = item['text']
                pending.extend(item.values())
    if isinstance(value, list):
        return [compact(v, originals) for v in value]
    if isinstance(value, dict):
        omitted = {'evidence_refs', 'counter_evidence_refs', 'input_hash', 'origin_dependency_ids', 'local_ref',
                   'source_refs', 'counter_source_refs', 'candidate_view_version', 'endpoint_mode'}
        if value.get('endpoint_mode')=='source_text' and not value.get('source_relation'):
            omitted.add('unresolved_endpoints')  # Source statements intentionally have no type binding.
            if value.get('endpoint_labels')=={k:value.get(k) for k in ('subject','object')}:
                omitted.add('endpoint_labels')
        omitted.update(k for k in ('validation','evidence_validation','unresolved_endpoints') if value.get(k)==[])
        omitted.update(k for k in ('source_errors','candidate_alignments','target_gap_errors') if value.get(k)==[])
        if value.get('recovery_meanings'): omitted.add('recovery_meaning')
        if value.get('analysis_target') is False: omitted.add('analysis_target')
        # Model input only: omit a quote only if that evidence's original is also provided.
        if (value.get('evidence_id') in originals and isinstance(value.get('quote'), str)
                and value['quote'] in originals[value['evidence_id']]):
            omitted.add('quote')
        return {k: compact(v, originals) for k,v in value.items() if k not in omitted}
    return value


def remap(value, mapping):
    if isinstance(value, list):
        return [remap(v, mapping) for v in value]
    if isinstance(value, dict):
        literal = {'endpoint_labels'} | ({'subject','object'} if value.get('endpoint_mode')=='source_text' and not value.get('source_relation') else set())
        return {k: deepcopy(v) if k in literal else remap(v, mapping) for k,v in value.items()}
    return mapping.get(value, value) if isinstance(value, str) else value


def normalize(output, stage, run, deps, by_id, supplied, context=None, require_issue_cause=False):
    if any(not text.strip() for field in ('findings','gaps') for text in output.get(field, [])):
        raise ValueError('조사 결과/미해결 사유는 빈 문자열일 수 없음')
    if not any(output.get(field) for field in models.RESULT_FIELDS[stage]):
        raise ValueError('빈 분석에는 구체적인 결과 또는 미해결 사유 필요')
    cq_ids = {c['id'] for c in run['cqs']}; scope_ids = {c['id'] for c in run['scope_items']}
    def refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'evidence_ids', 'counter_evidence_ids'} and isinstance(child,list) and all(isinstance(i,str) for i in child) and not set(child) <= set(deps):
                    raise ValueError('실제 모델 입력 밖 근거 ID')
                if key=='evidence_id' and isinstance(child,str) and child and child not in deps:
                    raise ValueError('실제 모델 입력 밖 근거 ID')
                refs(child)
        elif isinstance(value, list):
            for child in value: refs(child)
    if stage=='critic':
        return reviews.normalize(output, run, deps, by_id, supplied, context or {}, normalize, refs, require_issue_cause)
    refs(output)
    if stage == 'revision':
        history = []
        seen = set()
        for field, role in [('observations','concept'), ('relations','relation'), ('hierarchies','builder')]:
            for row in output[field]:
                identifier = row.pop('candidate_ref'); reason = row.pop('reason')
                if identifier in seen or identifier not in supplied:
                    raise ValueError('수정 대상 중복 또는 범위 밖 후보')
                original = supplied[identifier]
                expected = 'classification' if field=='observations' else 'negation' if field=='relations' else 'child_ref'
                if expected not in original:
                    raise ValueError('수정 대상 종류 불일치')
                evidence_only = identifier in (context or {}).get('evidence_only_ids', [])
                if evidence_only:
                    before = {k:v for k,v in original.items() if k!='source_relation'}
                    if meaning_signature(row) != meaning_signature(before):
                        raise ValueError('근거 선택 보완은 기존 의미를 변경할 수 없음')
                replacement = normalize({field:[row]}, role, run, deps, by_id, supplied)[field][0]
                if evidence_only:
                    repaired = deepcopy(original)
                    for key in ('evidence_ids','source_refs','source_quotes','evidence_refs','validation'):
                        if key in replacement: repaired[key]=replacement[key]
                    replacement.clear()
                    replacement.update(repaired)
                source_change = identifier in (context or {}).get('source_change_ids', []) and not evidence_only
                for key in ('source_relation','source_relation_ids','design_reason'):
                    if source_change: continue
                    if key in original: replacement[key]=deepcopy(original[key])
                if original.get('source_relation_ids'):
                    replacement['support_type']='design_proposal'
                if source_change:
                    raw = dict(deepcopy(replacement),id=identifier,revision_status='unreviewed_revision')
                    if all(raw[k]==original['source_relation'][k] for k in ('subject','object')):
                        replacement.update(subject=original['subject'],object=original['object'],source_relation=raw,
                            unresolved_endpoints=[],statement_type='design_proposal',support_type='design_proposal',
                            design_reason=original.get('design_reason',''))
                elif original.get('source_relation'):
                    replacement.update(statement_type='design_proposal',support_type='design_proposal')
                replacement['id'] = identifier
                replacement['revision_status'] = 'unreviewed_revision'
                history.append(dict(candidate_id=identifier, before=original, after=deepcopy(replacement), reason=reason))
                seen.add(identifier)
        for item in output['deferred']:
            if item['candidate_ref'] in seen or item['candidate_ref'] not in supplied:
                raise ValueError('보류 대상 중복 또는 범위 밖 후보')
            seen.add(item['candidate_ref'])
        effective = dict(supplied)
        effective.update({h['candidate_id']:h['after'] for h in history})
        hierarchies = [deepcopy(c) for c in effective.values() if 'child_ref' in c]
        identifiers = [h['id'] for h in hierarchies]
        if hierarchies:
            checked = normalize({'hierarchies':hierarchies}, 'builder', run, deps, by_id, effective)['hierarchies']
            for identifier, row in zip(identifiers, checked):
                row['id'] = identifier
                effective[identifier] = row
            for h in history:
                h['after'] = effective[h['candidate_id']]
            output['hierarchies'] = [effective[h['id']] for h in output['hierarchies']]
            output['effective_hierarchies'] = checked
        output['history'] = history
        return output
    for name in ('observations', 'relations'):
        rows = output.get(name, [])
        if len({c['local_ref'] for c in rows}) != len(rows):
            raise ValueError('응답 내부 local_ref 중복')
        for candidate in rows:
            problems = []
            if not candidate['evidence_ids']: problems.append('원문 또는 설계 출처 근거 필요')
            if not set(candidate['cq_ids']) <= cq_ids or not set(candidate['scope_item_ids']) <= scope_ids:
                problems.append('허용 CQ/범위 밖 연결')
            if not candidate['cq_ids'] and not candidate['scope_item_ids'] and not candidate['outside_scope_reason']:
                problems.append('CQ 또는 범위 연결 누락')
            candidate.update(id='dc_' + uuid4().hex, review_status='unreviewed', validation=problems,
                evidence_refs=[dict(evidence_id=i, block_id=by_id[i]['id'], source_version_id=by_id[i]['source_version_id'],
                    parse_run_id=by_id[i]['parse_run_id'], locator=by_id[i]['locator'], quote=by_id[i]['text']) for i in candidate['evidence_ids']])
    rows = output.get('observations', [])
    local = {c['local_ref']: c['id'] for c in rows}
    for alignment in output.get('alignments', []):
        if alignment['observation_ref'] not in local or alignment['target_id'] not in supplied:
            raise ValueError('관측/기준 개념 대응 참조 불일치')
        alignment['observation_ref'] = local[alignment['observation_ref']]
        alignment['review_status'] = 'unreviewed'
        target = supplied[alignment['target_id']]
        alignment['target_scope'] = 'reviewed' if target.get('review_status')=='reviewed' else 'run_candidate'
        if alignment['target_scope']=='run_candidate':
            alignment['target_fingerprint'] = identities.exact_key(target)
            alignment['target_snapshot'] = deepcopy(target)
    for relation in output.get('relations', []):
        if relation.get('endpoint_mode')=='source_text':
            relation['endpoint_labels'] = {k:relation[k] for k in ('subject','object')}
            relation['unresolved_endpoints'] = ['subject','object']
            continue
        relation.setdefault('endpoint_labels', {})
        relation['unresolved_endpoints'] = []
        for field in ('subject', 'object'):
            value = relation[field]
            if field not in relation['endpoint_labels'] and value not in supplied:
                relation['endpoint_labels'][field] = value  # Legacy name output, not an inferred phrase for an ID.
            # Never reinterpret an explicit entity/vocabulary ID as a class.
            matches = [supplied[value]] if value in supplied else [c for c in supplied.values() if (c.get('label') or c.get('name'))==value]
            if len(matches)==1 and matches[0].get('classification')=='type' and not (
                    matches[0].get('validation') or matches[0].get('outside_scope_reason')):
                relation[field] = matches[0]['id']
            else:
                relation['unresolved_endpoints'].append(field)
    if stage=='builder' and ('observations' in output or 'relation_bindings' in output):
        supplied = design.bind(output,supplied,by_id,context or {})
    for alias in output.get('alias_proposals', []):
        alias.update(review_status='unreviewed', validation=[] if alias['observation_ref'] in supplied and alias['target_id'] in supplied else ['존재하지 않는 별칭 참조'])
    for hierarchy in [*output.get('hierarchies', []), *output.get('hierarchy_checks', [])]:
        a, b = hierarchy['child_ref'], hierarchy['parent_ref']
        errors = []
        if a not in supplied or b not in supplied:
            errors.append('존재하지 않는 후보 참조')
        if a == b:
            errors.append('자기 참조')
        kinds = {'is_a': ('type','type'), 'instance_of': ('entity','type'), 'broader': ('vocabulary','vocabulary')}
        if hierarchy['relation'] in kinds and a in supplied and b in supplied:
            if tuple(supplied[i].get('classification') for i in (a,b)) != kinds[hierarchy['relation']]:
                errors.append('구조 관계의 대상 종류 불일치')
        for direction in ('a_to_b','b_to_a'):
            d = hierarchy[direction]
            if d['judgment'] != 'unknown' and not d['evidence_ids'] and not d['counter_evidence_ids']:
                errors.append('방향 판정 근거 누락')
        hierarchy.update(id='dh_' + uuid4().hex, review_status='unreviewed', validation=errors)
    # No canonical merge: even double support remains a human equivalence review.
    edges = [(h['child_ref'], h['parent_ref']) for h in output.get('hierarchies', []) if h['relation']=='is_a']
    for hierarchy in output.get('hierarchies', []):
        if hierarchy['relation'] != 'is_a': continue
        seen, pending = set(), [hierarchy['parent_ref']]
        while pending:
            current = pending.pop()
            if current == hierarchy['child_ref']:
                hierarchy['validation'].append('is_a 순환'); break
            if current not in seen:
                seen.add(current); pending.extend(b for a,b in edges if a==current)
    for action in output.get('actions', []):
        if action['action']=='request_evidence' and action['issue_id'] not in issue_ids(run):
            raise ValueError('추가 근거 요청의 쟁점 참조 불일치')
    return output


def issue_ids(run):
    return {i['id'] for u in run.get('analysis_units', []) if u['status']=='succeeded'
            for i in u.get('output', {}).get('issues', [])}


async def model_call(prompt, schema, stage, run, timeout):
    return await GenerationService().call_ollama(prompt, temperature=0, response_schema=schema,
        model=run['recipe']['models']['review' if stage=='critic' else 'draft'],
        num_predict=run['recipe']['num_predict'], num_ctx=run['recipe']['num_ctx'], think=False,
        timeout=timeout, return_metadata=True, local_only=True)


def make_prompt(run, stage, context, deps, supplied, key='', source_scope=None):
    mapping = {i: 'e'+str(n) for n,i in enumerate(sorted(set(deps)))}
    mapping.update({i: 'c'+str(n) for n,i in enumerate(sorted(supplied))})
    context = segments.bind(context, source_scope or run.get('id'), stage+':'+key)
    if stage=='revision':
        context['targets']=[dict(c['source_relation'],id=c['id']) if c['id'] in context.get('source_change_ids', []) else c
                            for c in context['targets']]
    if stage=='critic':
        bindings={}
        for field in ('unapproved_relations','reviewed_base','comparison_terms'):
            for n,c in enumerate(context.get(field, [])):
                if not c.get('source_relation'): continue
                bindings[c['id']]=dict(relation_ref=c['id'],subject_ref=c['subject'],object_ref=c['object'],reason=c.get('design_reason',''))
                context[field][n]=dict(c['source_relation'],id=c['id'])
        context['relation_bindings']=list(bindings.values())
    if 'review_scope' in context:
        context['review_scope']['provided_source_refs']=[v['source_ref'] for v in segments.originals(context)]
    payload = dict(cqs=run['cqs'], scope_items=run['scope_items'], **context)
    payload = compact(remap(payload, mapping))
    prompt = models.COMMON + models.PROMPTS[stage] + '\nINPUT:\n' + json.dumps(segments.compact_text(payload), ensure_ascii=False, separators=(',', ':'))
    return mapping, prompt


def call(service, run, stage, key, context, deps, by_id, supplied=None):
    supplied = supplied or {}
    uid = stage + ':' + key
    unit = next((u for u in run['analysis_units'] if u['id']==uid), None)
    if unit is None:
        unit = dict(id=uid, stage=stage, group_id=key, status='queued', attempts=[], error=None)
        run['analysis_units'].append(unit)
    source_scope = unit.setdefault('source_ref_run_id', run['id'])
    context = segments.bind(context, source_scope, uid)
    mapping, prompt = make_prompt(run, stage, context, deps, supplied, key, source_scope)
    input_hash = profile.digest([prompt, run['recipe']])
    # A resumed successful unit is immutable, even when its newly built input is wrong.
    if unit['status'] == 'succeeded':
        if not set(deps) <= allowed_ids(service, list(by_id.values())):
            raise ValueError('사용 중단/재검토 근거가 성공 단위에 포함됨')
        if unit['input_hash'] != input_hash:
            raise ValueError('성공 단위의 입력 해시 변경: 새 실행 필요')
        return unit['output']
    if ':recovery_' in uid and unit['attempts']:
        return None  # One attempt per cause/target; resume cannot reset a failed recovery.
    unit['dependency_ids'] = sorted(set(deps))
    unit['provided_block_ids'] = sorted(raw_refs(context))
    citation_ids = unit['provided_block_ids']
    unit['source_ref_map'] = {b['source_ref']:dict(block_id=b['ref'],span=b.get('span',[0,len(b['text'])]))
                              for b in segments.originals(context)}
    try:
        if not set(deps) <= allowed_ids(service, list(by_id.values())):
            raise ValueError('사용 중단/재검토 근거가 원문 또는 파생 입력에 포함됨')
        if cancelled(service, run):
            return None
        if len(prompt) > run['recipe']['input_chars']:
            raise ValueError(f'전체 입력 {len(prompt)}자 예산 초과; 원문을 자르지 않고 미처리')
        # UTF-8 byte count is a conservative token upper bound, never a char=token claim.
        if len(prompt.encode()) + run['recipe']['num_predict'] > run['recipe']['num_ctx']:
            raise ValueError('전체 입력의 보수적 토큰 상한이 선언 컨텍스트 초과')
        if run['recipe'] != recipe(run['recipe']['budgets']):
            raise ValueError('실제 호출 시 모델/로컬 처리 설정 변경')
        if model_identity(run['recipe']) != run['model_identity']:
            raise ValueError('실제 호출 시 설치 모델 digest 변경')
        budget = run['recipe']['budgets']
        remaining = budget['model_seconds'] - run['metrics']['model_total_s'] - run['metrics'].get('interrupted_time_reserve_s', 0)
        if run['metrics']['llm_calls'] >= budget['model_calls'] or remaining <= 0:
            raise ValueError('모델 호출/시간 예산 종료')
        timeout = min(remaining, run['recipe']['call_timeout'])
        schema = models.OUTPUTS[stage].model_json_schema()
        if stage=='relation':
            targets = [v['source_ref'] for v in context.get('blocks', []) if v.get('analysis_target') and not v.get('context_only')]
            schema['$defs']['TargetGap']['properties']['source_ref']['enum'] = targets or ['']
            schema['properties']['target_gaps']['maxItems'] = len(targets)
        if stage=='builder':
            schema['$defs']['RelationBinding'] = schema['properties']['relation_bindings']['items']
            schema['properties']['relation_bindings']['items'] = {'$ref':'#/$defs/RelationBinding'}
        if stage=='critic':
            # SkipValidation inlines record schemas; keep the existing enum/coverage constraints.
            definitions = deepcopy(schema.get('$defs', {}))
            for field, name in [('issues','Issue'), ('hierarchy_checks','Hierarchy'),
                                ('relation_checks','RelationCheck'), ('observation_checks','ObservationCheck'), ('missing_meanings','MissingMeaning')]:
                item = schema['properties'][field]['items']
                schema['$defs'][name] = deepcopy(definitions[item['$ref'].split('/')[-1]] if '$ref' in item else item)
                schema['properties'][field]['items'] = {'$ref':'#/$defs/'+name}
            schema['properties']['issues']['maxItems']=8
            primary_targets = {(v['ref'],tuple(v.get('span',[0,len(v['text'])]))) for v in context.get('blocks', [])
                               if v.get('analysis_target') and not v.get('context_only')}
            missing_limit = max(2,min(5,len(primary_targets)))
            schema['properties']['missing_meanings']['maxItems']=missing_limit
            schema['$defs']['Issue']['required'].append('cause')
            for section,name in [('relation_checks','RelationCheck'),('observation_checks','ObservationCheck')]:
                fields=models.SEMANTIC_FIELDS[section]
                schema['$defs'][name]['properties']['semantic_checks']=dict(type='object',
                    properties={k:dict(type='string',enum=['supported','refuted','unknown']) for k in fields},required=list(fields),additionalProperties=False)
            comparable=[mapping[i] for i,c in supplied.items() if 'classification' in c or 'negation' in c]
            comparisons=schema['$defs']['MissingMeaning']['properties']['compared_candidate_ids']
            comparisons['items']['enum']=comparable or ['']
            comparisons['maxItems']=len(comparable)
        action_schema = schema.get('$defs', {}).get('Action')
        if action_schema:
            variants = []
            for action, fields in {'read':['unit_id'], 'search':['query'], 'lookup_term':['label','term_type'], 'request_evidence':['query','issue_id'], 'finish':[]}.items():
                request_issues = sorted(issue_ids(run)) + ([f'i{n}' for n in range(1,9)] if stage=='critic' else [])
                if action == 'request_evidence' and not request_issues:
                    continue
                props = {k:deepcopy(action_schema['properties'][k]) for k in ['action','reason',*fields]}
                props['action'] = {'type':'string','const':action}
                for prop in props.values(): prop.pop('default', None)
                for field in fields:
                    if field != 'term_type': props[field]['minLength'] = 1
                if action == 'read':
                    props['unit_id']['enum'] = [g['id'] for g in run['frontier']]
                if action == 'request_evidence':
                    props['issue_id']['enum'] = request_issues
                variants.append(dict(type='object', properties=props, required=list(props), additionalProperties=False))
            schema['$defs']['Action'] = {'anyOf':variants}
        alignment = schema.get('$defs', {}).get('ConceptAlignment') or schema.get('$defs', {}).get('Alignment')
        if alignment:
            alignment['properties']['target_id']['enum'] = [mapping[i] for i in supplied] or ['']
            if stage == 'concept':
                if not supplied:
                    schema['properties']['alignments']['maxItems'] = 0
                alignment['properties']['observation_ref']['enum'] = [f'o{n}' for n in range(1,6)]
                schema['$defs']['Observation']['properties']['local_ref']['enum'] = [f'o{n}' for n in range(1,6)]
            else:
                alignment['properties']['observation_ref']['enum'] = [mapping[i] for i in supplied] or ['']
                if not supplied:
                    schema['properties']['alias_proposals']['maxItems'] = 0
        issue_schema = schema.get('$defs', {}).get('Issue')
        if issue_schema:
            issue_schema['properties']['candidate_ref']['enum'] = ['', *[mapping[i] for i in supplied]]
            issue_schema['properties']['target_ref']['enum'] = ['', *[mapping[i] for i in supplied]]
        for name, field in [('ObservationRevision','classification'), ('RelationRevision','negation'), ('HierarchyRevision','child_ref'), ('Deferred',None), ('RelationCheck','negation'), ('ObservationCheck','classification')]:
            definition = schema.get('$defs', {}).get(name)
            if definition:
                ids = [mapping[i] for i,c in supplied.items() if field is None or field in c]
                if stage=='revision':
                    ids = [mapping[i] for i in context['target_ids'] if field is None or field in supplied[i]]
                definition['properties']['candidate_ref']['enum'] = ids or ['']
                if name in {'RelationCheck','ObservationCheck'}:
                    ids = [mapping[i] for i in context.get('review_target_ids',supplied) if field in supplied[i]]
                    definition['properties']['candidate_ref']['enum'] = ids or ['']
                    definition['required'] = [p for p in definition['properties'] if p!='source_refs']
                    schema['required'] = list(schema['properties'])
                    definition['properties']['evidence_id']['enum'] = ['', *[mapping[i] for i in citation_ids]]
                    schema['properties']['relation_checks' if name=='RelationCheck' else 'observation_checks'].update(minItems=len(ids), maxItems=len(ids))
        if stage=='revision':
            for field, marker in [('observations','classification'), ('relations','negation'), ('hierarchies','child_ref')]:
                schema['properties'][field]['maxItems'] = min(5, sum(marker in supplied[i] for i in context['target_ids']))
        if stage=='builder':
            relation_ids = [mapping[i] for i in context.get('design_relation_ids', [])]
            if len(relation_ids)>2: raise ValueError('Builder 주관계는 최대 2개; 묶음 분리 필요')
            type_ids = [mapping[i] for i,c in supplied.items() if c.get('classification')=='type']
            schema['properties']['observations']['maxItems']=0
            schema['$defs']['DesignedType']['properties'].pop('local_ref')
            schema['$defs']['DesignedType']['properties']['source_relation_ids']['items']['enum'] = relation_ids or ['']
            binding = schema['$defs']['RelationBinding']['properties']
            binding['relation_ref']['enum'] = relation_ids or ['']
            for field in ('subject_ref','object_ref'):
                binding[field] = {'anyOf':([dict(type='string',enum=type_ids)] if type_ids else [])+[{'$ref':'#/$defs/DesignedType'}]}
            binding_definition=schema['$defs']['RelationBinding']
            variants=[]
            for decision in ('bind','defer','source_error'):
                fields=['relation_ref','decision','reason']+(['subject_ref','object_ref'] if decision=='bind' else [])
                props={k:deepcopy(binding[k]) for k in fields}
                props['decision']={'type':'string','const':decision}
                variants.append(dict(type='object',properties=props,required=fields,additionalProperties=False))
            binding_definition.clear(); binding_definition['anyOf']=variants
            schema['properties']['relation_bindings'].update(minItems=len(relation_ids),maxItems=len(relation_ids))
            schema['required']=list(schema['properties'])
            if not relation_ids:
                schema['properties']['observations']['maxItems']=0
                schema['properties']['relation_bindings']['maxItems']=0
        hierarchy_schema = schema.get('$defs', {}).get('Hierarchy') or schema.get('$defs', {}).get('HierarchyRevision')
        if hierarchy_schema:
            # ponytail: new inline types can join hierarchies/aliases once supplied in a later group.
            identifiers = [mapping[i] for i,c in supplied.items() if c.get('classification') in {'type','entity','vocabulary','unresolved'}]
            if not identifiers:
                schema['properties']['hierarchy_checks' if stage=='critic' else 'hierarchies']['maxItems'] = 0
            for name in ('child_ref','parent_ref'):
                hierarchy_schema['properties'][name]['enum'] = identifiers or ['']
            if stage == 'critic':
                proposed = context.get('taxonomy', {}).get('hierarchies', [])
                schema['properties']['hierarchy_checks'].update(minItems=len(proposed), maxItems=len(proposed))
                variants = []
                for hierarchy in proposed:
                    variant = deepcopy(hierarchy_schema)
                    for field in ('child_ref','parent_ref','relation'):
                        variant['properties'][field] = {'type':'string','const':mapping.get(hierarchy[field], hierarchy[field])}
                    variants.append(variant)
                if variants:
                    hierarchy_schema.clear()
                    hierarchy_schema['anyOf'] = variants
        for definition in schema.get('$defs', {}).values():
            props = definition.get('properties', {})
            if stage=='relation' and 'endpoint_labels' in props:
                props.pop('endpoint_labels')
                props.pop('local_ref')
            if 'endpoint_labels' in props:
                props['endpoint_labels']=dict(type='object',properties={k:dict(type='string',minLength=1,maxLength=100) for k in ('subject','object')},
                    required=['subject','object'],additionalProperties=False)
            for field in ('source_refs','counter_source_refs'):
                if field in props:
                    if unit['source_ref_map']: props[field]['items']['enum']=list(unit['source_ref_map'])
                    else: props[field]['maxItems']=0
            if 'cq_ids' in props:
                for field, values in [('cq_ids', run['cqs']), ('scope_item_ids', run['scope_items'])]:
                    if values:
                        props[field]['items']['enum'] = [c['id'] for c in values]
                    else:
                        # Ollama rejects enum=[] even on an optional array. Preserve the empty selection.
                        props[field]['maxItems'] = 0
                definition['required'] = [p for p in props if p!='source_refs']
            for name in ('evidence_ids', 'counter_evidence_ids'):
                if name in definition.get('properties', {}):
                    definition['properties'][name]['items']['enum'] = [mapping[i] for i in citation_ids]
        for definition in schema.get('$defs', {}).values():
            if 'cq_ids' in definition.get('properties', {}):
                variants = []
                for field in ('cq_ids', 'scope_item_ids', 'outside_scope_reason'):
                    if definition['properties'][field].get('maxItems') == 0:
                        continue
                    variant = deepcopy(definition)
                    variant['properties'][field]['minLength' if field=='outside_scope_reason' else 'minItems'] = 1
                    variants.append(variant)
                definition.clear()
                definition['anyOf'] = variants
        root = {k:v for k,v in schema.items() if k!='$defs'}
        variants = []
        for field in models.RESULT_FIELDS[stage]:
            if root['properties'][field].get('maxItems') == 0:
                continue
            variant = deepcopy(root)
            variant['required'] = list(dict.fromkeys([*variant.get('required', []),field]))
            variant['properties'][field]['minItems'] = max(1, variant['properties'][field].get('minItems', 0))
            variants.append(variant)
        schema = {'$defs':schema.get('$defs', {}), 'anyOf':variants}
        quote_schema = schema.get('$defs', {}).get('SourceQuote')
        if quote_schema:
            quote_schema['properties']['evidence_id']['enum'] = [mapping[i] for i in citation_ids] or ['']
        # New generation uses one citation path; parsers still accept stored exact-quote records.
        def source_only(node):
            if isinstance(node,list):
                for child in node: source_only(child)
            elif isinstance(node,dict):
                for child in list(node.values()): source_only(child)
                props=node.get('properties', {})
                if props.get('source_refs', {}).get('type')=='array':
                    for name in ('evidence_ids','counter_evidence_ids','source_quotes','evidence_id','quote'):
                        props.pop(name,None)
                    node['required']=[k for k in node.get('required', []) if k in props]
                    node['required']=list(dict.fromkeys(node['required']+['source_refs']))
                    if 'cq_ids' in props: props['source_refs']['minItems']=1
                    if 'judgment' in props:
                        unknown=deepcopy(node);grounded=deepcopy(node)
                        unknown['properties']['judgment']={'type':'string','const':'unknown'}
                        grounded['properties']['judgment']={'type':'string','enum':['supported','refuted']}
                        grounded['properties']['source_refs']['minItems']=1
                        node.clear();node['anyOf']=[unknown,grounded]
        source_only(schema)
        unit.update(status='running', prompt=prompt, input_hash=input_hash, input_chars=len(prompt), error=None)
        unit['attempts'].append(dict(started_at=utcnow(), timeout_s=timeout, outcome='started'))
        run['metrics']['llm_calls'] += 1
        save(service, run)
        started = monotonic(); metadata = None
        try:
            metadata = asyncio.run(model_call(prompt, schema, stage, run, timeout))
            unit['raw_output'] = metadata['text']
            if metadata.get('done_reason') == 'length' or metadata.get('done') is False:
                raise ValueError('모델 출력 절단')
            if not metadata.get('prompt_eval_count') or metadata['prompt_eval_count'] + run['recipe']['num_predict'] > run['recipe']['num_ctx']:
                raise ValueError('실제 입력 토큰/컨텍스트 확인 실패')
            decoded = json.loads(metadata['text'])
            if stage=='builder': design.inline_types(decoded)
            if stage=='relation':
                for n, row in enumerate(decoded.get('relations', []), 1):
                    row['local_ref'] = f'r{n}'
            output = models.OUTPUTS[stage].model_validate(decoded).model_dump(warnings=False)
            if stage=='builder': design.scope_local_refs(output)
            for row in output.get('relations', []):
                identifier = {v:k for k,v in mapping.items()}.get(row.get('candidate_ref'))
                original = supplied.get(identifier, {})
                source_change = identifier in context.get('source_change_ids', [])
                if stage=='relation' or (stage=='revision' and (source_change or original.get('endpoint_mode')=='source_text' and not original.get('source_relation'))):
                    if stage=='revision':
                        raw=original.get('source_relation',original)
                        types={i for i,c in supplied.items() if c.get('classification')=='type'}
                        if original.get('source_relation'): types.update(original[k] for k in ('subject','object'))
                        type_refs=types | {mapping[i] for i in types if i in mapping}
                        if row['statement_type']=='design_proposal' or any(row[k]!=raw[k] and row[k] in type_refs for k in ('subject','object')):
                            raise ValueError('원명제 수정은 유형 ID/별칭 또는 design_proposal로 대체할 수 없음')
                    row['endpoint_mode']='source_text'
            output = remap(output, {v:k for k,v in mapping.items()})
            if not set(deps) <= allowed_ids(service, list(by_id.values())):
                raise ValueError('호출 중 입력 근거 사용 상태 변경')
            if stage!='critic': segments.restore(output, by_id, segments.originals(context))
            output = normalize(output, stage, run, citation_ids, by_id, supplied, context, require_issue_cause=stage=='critic')
            if stage=='critic':
                count = len(decoded.get('missing_meanings', []))
                output['capacity'] = dict(roles={'missing_meanings':dict(limit=missing_limit,output_count=count)},
                    primary_analysis_targets=len(primary_targets),semantic_completeness='미검증; 상한 미도달도 전체 검수 완료가 아님')
                output['capacity_pending'] = ['누락 의미 응답 상한 도달; 추가 미검수 의미 가능성'] if count>=missing_limit else []
            if stage in {'concept', 'relation'}:
                rows = output['observations' if stage=='concept' else 'relations']
                group = next(g for g in run['frontier'] if g['id']==key)
                for candidate in rows:
                    if meaning_signature(candidate, supplied) in group.get('previous_signatures', []):
                        candidate['validation'].append('누락 복구에서 기존 의미 산출 반복; 새 복구 결과 아님')
                    refs, errors = segments.references(candidate, by_id, segments.originals(context))
                    candidate['evidence_refs'] = refs
                    candidate['evidence_validation'] = errors
                    candidate['validation'].extend(errors)
                primary = raw_refs(context.get('blocks', []))
                if rows and not any(primary & set(c['evidence_ids']) for c in rows) and not output['gaps']:
                    raise ValueError('주 분석 원문 근거 또는 해당 자료의 분석 공백 필요')
                if stage=='relation':
                    output['target_coverage'] = segments.target_coverage(output, context.get('blocks', []))
            if stage=='revision':
                revised = output['observations'] + output['relations']
                for candidate in revised:
                    refs, errors = segments.references(candidate, by_id, segments.originals(context))
                    candidate['evidence_refs'] = refs
                    candidate['evidence_validation'] = errors
                    candidate['validation'].extend(errors)
                    if candidate.get('source_relation', {}).get('revision_status')=='unreviewed_revision':
                        candidate['source_relation'].update(evidence_refs=deepcopy(refs),evidence_validation=list(errors),validation=list(candidate['validation']))
                for history in output['history']:
                    replacement = next((c for c in revised if c['id']==history['candidate_id']), None)
                    if replacement is not None: history['after'] = deepcopy(replacement)
                covered = {h['candidate_id'] for h in output['history']} | {d['candidate_ref'] for d in output['deferred']}
                if covered != set(context['target_ids']):
                    raise ValueError('수정 대상의 수정 또는 명시적 보류 누락')
            unit.update(output=output, status='succeeded')
            identities.register(run)
        finally:
            seconds = monotonic()-started
            unit['attempts'][-1].update(elapsed_s=round(seconds,3), outcome=unit['status'],
                metadata={k:v for k,v in (metadata or {}).items() if k!='text'})
            run['metrics']['model_total_s'] = round(run['metrics']['model_total_s']+seconds,3)
    except Exception as exc:
        unit.update(status='failed', error=str(exc))
        if unit['attempts'] and unit['attempts'][-1]['outcome'] in {'started','running'}:
            unit['attempts'][-1]['outcome'] = 'failed'
    save(service, run)
    return unit.get('output') if unit['status']=='succeeded' else None


def apply_actions(service, run, index, blocks, stage, key, output):
    unit = next(u for u in run['analysis_units'] if u['id']==stage+':'+key)
    if unit.get('actions_done') or cancelled(service, run):
        return
    unit['tool_errors'] = []
    for action in output.get('actions', []):
        try:
            result = dispatch(service, run, index, blocks, action, analysis_request=stage=='scout')
            if stage == 'scout' and action['action'] == 'read':
                for group in run['frontier']:
                    if group['id'] == action['unit_id']:
                        group['requested_by_scout'] = True
                        group['reason'] += '; Scout: ' + action['reason']
            unit.setdefault('tool_results', []).append(result)
        except ValueError as exc:
            unit['tool_errors'].append(str(exc))
    unit['actions_done'] = True
    save(service, run)


def base_context(run):
    return [dict(c, review_status='reviewed', classification=c.get('classification') or
                 {'concept':'type', 'attribute':'property_value', 'vocabulary_concept':'vocabulary'}.get(c['kind'], 'unresolved'))
            for c in run.get('base_candidates', [])]


def meaning_signature(candidate, supplied=None):
    supplied = supplied or {}
    candidate = candidate.get('source_relation') or candidate
    fields = ('label','classification','definition','conditions','exceptions','time') if 'classification' in candidate else (
        'subject','predicate','object','direction','negation','conditions','time','statement_type')
    values = {k:candidate.get(k, '') for k in fields}
    for key in ('subject','object'):
        if key not in values: continue
        target = supplied.get(values[key], {})
        values[key] = candidate.get('endpoint_labels', {}).get(key) or target.get('label') or target.get('name') or values[key]
    return profile.digest({k:' '.join(str(v).split()) for k,v in values.items()})


def queue_recovery(run, review, group, by_id=None):
    by_id = by_id or {}
    requests = run.setdefault('recovery_requests', [])
    scope = [run.get('frozen_input', {}).get(k) for k in ('bundle_id','scope','step')]
    scope += [run.get('analysis_block_ids'), run.get('cqs', []), run.get('scope_items', [])]
    def add(cause, role, target, need, validation=()):
        key = profile.digest([cause, target, role, scope])
        request = next((r for r in requests if r['id']==key), None)
        if request is None:
            request = dict(deepcopy(need), id=key, cause=cause, role=role, target=target,
                validation=list(validation), critic_group_id=group['id'], meanings=[], status='pending',
                semantic_status='unverified')
            requests.append(request)
        elif request['validation'] and not validation and not request.get('group_id'):
            # A rejected comparison request must not consume the actual owner's one attempt.
            request.update(validation=[],status='pending',critic_group_id=group['id'])
        meaning = {k:deepcopy(v) for k,v in need.items() if k not in {'validation','id'}}
        def identity(m):
            return [' '.join(m.get('meaning','').split()), sorted(m.get('cq_ids', [])), sorted(m.get('scope_item_ids', [])),
                    sorted((e['block_id'],e['span']) for e in m.get('evidence_refs', []))]
        if not any(identity(m)==identity(meaning) for m in request['meanings']): request['meanings'].append(meaning)
        return request
    owners = [g for g in run.get('frontier', []) if g['id'] in group.get('analysis_group_ids', [group['id']])]
    owned = [v for g in owners for i in g['block_ids'] for v in
             (g.get('segments') or ([dict(block_id=i,span=[0,len(by_id[i]['text'])])] if i in by_id else [])) if v['block_id']==i]
    for need in review.get('missing_meanings', []):
        validation = list(need['validation'])
        selected = run.get('analysis_block_ids')
        if selected is not None and any(e['block_id'] not in selected for e in need['evidence_refs']):
            validation.append('선택 분석 블록 밖 비교 원문은 누락 재분석 대상으로 사용할 수 없음')
        targets = []
        for ref in need['evidence_refs']:
            views = [v for v in owned if v['block_id']==ref['block_id'] and v['span'][0]<=ref['span'][0] and ref['span'][1]<=v['span'][1]]
            if owners and not views: validation.append('담당 분석 구간 밖 비교 원문은 누락 재분석 대상으로 사용할 수 없음')
            view = views[0] if views and need.get('trigger')!='target_response' else ref
            target = [view['block_id'], view['span']]
            if target not in targets: targets.append(target)
        request = add('extraction_missing', need['role'], sorted(targets), need, validation)
        if not validation and not request.get('group_id'):
            request['owner_group_ids'] = [g['id'] for g in owners]
    candidates = {c['id']:c for c in group.get('candidates', [])}
    candidates.update({c['id']:c for c in group.get('design_candidates', [])})
    primary = set(group.get('primary_candidate_ids', [])) | set(group.get('design_candidate_ids', []))
    issues = list(review.get('issues', []))
    issues += [dict(candidate_ref=e['relation_ref'],cause='content_error',reason=e['reason']) for e in group.get('source_errors', [])]
    issues += [dict(candidate_ref=c['candidate_ref'],cause='endpoint',reason='; '.join(c['binding_validation']))
               for c in review.get('relation_checks', []) if c.get('binding_validation')]
    for unit in run.get('analysis_units', []):
        if unit['status']!='succeeded': continue
        for alignment in unit.get('output', {}).get('alignments', []):
            identifier = alignment['observation_ref']
            if identifier not in primary: continue
            target = candidates.get(alignment['target_id'], {})
            name = candidates[identifier].get('label')
            if alignment.get('meaning')=='uncertain' or (alignment.get('meaning') in {'same','changed'} and name!=(target.get('name') or target.get('label'))):
                issues.append(dict(candidate_ref=identifier,cause='alignment',target_ref=alignment['target_id'],reason=alignment['reason']))
    for identifier in sorted(primary & candidates.keys()):
        c = candidates[identifier]
        for cause, reason in [('endpoint', '미연결 끝점: '+', '.join(c.get('unresolved_endpoints', []))),
                              ('evidence_error', '; '.join(c.get('evidence_validation', [])))]:
            if cause=='endpoint' and (group.get('comparison_only') or not c.get('unresolved_endpoints')) or cause=='evidence_error' and not c.get('evidence_validation'): continue
            issues.append(dict(candidate_ref=identifier,cause=cause,reason=reason))
    for issue in issues:
        cause = issue.get('cause', 'content_error')
        identifier = issue.get('candidate_ref', '')
        c = candidates.get(identifier, {})
        target = dict(candidate_id=identifier) if identifier else dict(group_id=group['id'])
        if cause=='endpoint': target['endpoints']=c.get('unresolved_endpoints') or ['subject','object']
        if cause=='alignment': target['definition_id']=issue.get('target_ref', '')
        role = 'revision' if cause in {'evidence_error','content_error'} else 'builder' if cause=='endpoint' else 'review'
        request = add(cause, role, target, dict(meaning=issue['reason'],candidate_ref=identifier,
            target_ref=issue.get('target_ref', ''),defer_reason=issue.get('defer_reason', ''),
            assessment_scope=deepcopy(review.get('review_scope', {}))))
        if cause in {'endpoint','alignment','source_absent','budget_exhausted'} or identifier not in primary:
            request.update(status='budget_exhausted' if cause=='budget_exhausted' else 'source_absent' if cause=='source_absent' else 'manual_review',
                reason=('원문 관계 보존; 기존 Builder 연결 결과를 명시 검수' if cause=='endpoint' else
                        '관련 기존 정의와 명시 대응 검수' if cause=='alignment' else issue.get('defer_reason') or issue['reason']))


def recovery_groups(run, round_number, by_id):
    groups = []
    for request in run.get('recovery_requests', []):
        if request.get('cause','extraction_missing')!='extraction_missing' or request['status']!='pending' or request['validation']: continue
        owners = [g for g in run.get('frontier', []) if g['id'] in request.get('owner_group_ids', [])]
        views = []
        targets = request.get('target', [(e['block_id'],e['span']) for e in request['evidence_refs']])
        for block_id, span in targets:
            ref = dict(block_id=block_id,span=span)
            b = by_id[ref['block_id']]
            owned = [v for g in owners for v in g.get('segments', []) if v['block_id']==block_id]
            matching = [v for v in owned or segments.split(b) if v['span'][0] <= ref['span'][0] and ref['span'][1] <= v['span'][1]]
            view = deepcopy(matching[0]) if matching else dict(block_id=b['id'],span=span,shared_spans=[],recipe=segments.VERSION)
            if request.get('trigger')=='target_response':
                a,z = view['span']
                view['shared_spans'] += [s for s in ([a,span[0]],[span[1],z]) if s[0]<s[1]]
                view.update(span=span,analysis_target=True)
            if view not in views: views.append(view)
        if not views: continue
        ids = list(dict.fromkeys(v['block_id'] for v in views))
        known = identities.rows(run, [c for u in run['analysis_units'] if u['status']=='succeeded' for field in ('observations','relations')
                 for c in u['output'].get(field, [])])
        known += base_context(run)
        prior = [c for c in known if any(e['block_id']==bid and e.get('span') and
                 e['span'][0]<span[1] and span[0]<e['span'][1] for e in c.get('evidence_refs', []) for bid,span in targets)]
        endpoints = {c[k] for c in prior for k in ('subject','object') if c.get(k)}
        endpoint_types = [c for c in known if c['id'] in endpoints and 'classification' in c]
        compared = {identities.identifier(run,i) for m in request['meanings'] for i in m.get('compared_candidate_ids', [])}
        critic_group = next((g for g in run.get('candidate_groups', []) if g['id']==request['critic_group_id']), {})
        comparison_candidates = {c['id']:c for c in known}
        comparison_candidates.update({c['id']:c for c in critic_group.get('candidates', [])+critic_group.get('design_candidates', [])})
        comparisons = [c for i,c in comparison_candidates.items() if i in compared] if request['role']=='concept' else []
        prior += [c for c in endpoint_types if c not in prior]
        # Use the Critic's modeled view; its source_relation and the original units retain the raw statement.
        prior = [c for c in prior if c['id'] not in {v['id'] for v in comparisons}] + comparisons
        provided_ids = {c['id'] for c in prior}
        omissions = [dict(candidate_id=c['id'],reason='요청 구간과 불일치' if any(e.get('span') for e in c.get('evidence_refs', [])) else 'legacy span 미확인; 비교 보류')
                     for c in known if set(c.get('evidence_ids', [])) & set(ids) and c['id'] not in provided_ids]
        identifier = 'recovery_' + request['id'][:20]
        supplied = {c['id']:c for c in identities.rows(run, [c for u in run['analysis_units'] if u['status']=='succeeded' for c in u['output'].get('observations', [])])}
        groups.append(dict(id=identifier, file_id=by_id[ids[0]]['file_id'], source_group=by_id[ids[0]]['source_group'],
            block_ids=ids, segments=views, features=[], priority=2, required=True, input_chars=sum(v['span'][1]-v['span'][0] for v in views),
            round=round_number, reason='Critic이 특정한 원문 의미 누락: '+request['meaning'], status='unvisited',
            recovery_request_id=request['id'], recovery_meaning=request['meaning'], recovery_meanings=deepcopy(request['meanings']),
            context_block_ids=list(dict.fromkeys(i for g in owners for i in g.get('context_block_ids', []))),
            required_endpoint_ids=[c['id'] for c in endpoint_types] if request['role']=='relation' else [],
            required_comparison_ids=[c['id'] for c in comparisons], omitted_recovery_candidates=omissions,
            previous_observations=[c for c in prior if 'classification' in c],
            previous_relations=[c for c in prior if 'negation' in c],
            previous_signatures=[meaning_signature(c,supplied) for c in known if set(c.get('evidence_ids', [])) & set(ids)], roles=[request['role']]))
        request.update(status='scheduled', group_id=identifier, submitted_meanings=deepcopy(request['meanings']))
    return groups


def analysis_context(run, stage, context, supplied, group, reserve=0):
    context = deepcopy(context)
    omitted = group.setdefault('omitted_comparison_ids', [])
    fields = ('reviewed_base','unapproved_observations','previous_observations','previous_relations','comparison_terms')
    seen = set()
    for field in fields:
        rows = []
        for c in context.get(field, []):
            if c['id'] not in seen: rows.append(c); seen.add(c['id'])
        if field in context: context[field] = rows
    seen = set()
    for field in ('blocks','tool_originals'):
        rows = []
        for b in context.get(field, []):
            key = (b['ref'],tuple(b.get('span', [0,len(b['text'])])),b['text'],b.get('context_only',False),b.get('analysis_target',False))
            if key not in seen: rows.append(b); seen.add(key)
        if field in context: context[field] = rows
    required = set(group.get('required_endpoint_ids', [])) | set(group.get('required_comparison_ids', []))
    mandatory_raw = set(group.get('required_endpoint_block_ids', [])) | {i for c in supplied.values() if c['id'] in required
        for i in c.get('evidence_ids', []) + [e['evidence_id'] for e in c.get('evidence', [])]}
    def retained():
        values = [c for field in fields for c in context.get(field, [])]
        selected = {c['id']:supplied[c['id']] for c in values if c['id'] in supplied}
        if 'previous_candidate_ids' in context:
            context['previous_candidate_ids'] = [i for i in context['previous_candidate_ids'] if i in selected]
        deps = raw_refs(context) | {i for c in selected.values() for i in c.get('origin_dependency_ids', [])}
        return sorted(deps), selected
    before = None
    while True:
        deps, selected = retained()
        _, prompt = make_prompt(run, stage, context, deps, selected)
        if before is None: before = len(prompt)
        group.setdefault('input_allocation', {})[stage] = dict(before_chars=before,input_chars=len(prompt),reserve_chars=reserve,
            char_margin=run['recipe']['input_chars']-len(prompt)-reserve,
            context_margin=run['recipe']['num_ctx']-len(prompt.encode())-reserve*3-run['recipe']['num_predict'])
        if len(prompt)+reserve <= run['recipe']['input_chars'] and len(prompt.encode())+reserve*3+run['recipe']['num_predict'] <= run['recipe']['num_ctx']:
            return context, deps, selected
        # Comparison material can be reviewed in the later candidate groups; primary text cannot be cut.
        removable = [(f,c) for f in ('comparison_terms','reviewed_base','previous_relations','previous_observations',
                     *(['unapproved_observations'] if group.get('roles')==['relation'] else []),'tool_originals')
                     for c in reversed(context.get(f, [])) if c.get('id') not in required and c.get('ref') not in mandatory_raw]
        if not removable:
            group['input_allocation'][stage]['pending_reason'] = '필수 원문·공유조건·직접 끝점 정의와 예약 여유가 배정 한도 초과; 원문 무절단'
            return context, deps, selected
        field, removed = removable[0]
        context[field].remove(removed)
        identifier = removed.get('id', removed.get('ref'))
        if identifier not in omitted: omitted.append(identifier)
        if field=='tool_originals':
            provided = raw_refs(context)
            for kind in ('reviewed_base','comparison_terms'):
                removed_terms = [c for c in context.get(kind, []) if not (set(c.get('evidence_ids', [])) | {e['evidence_id'] for e in c.get('evidence', [])}) <= provided]
                omitted.extend(c['id'] for c in removed_terms if c['id'] not in omitted)
                context[kind] = [c for c in context.get(kind, []) if c not in removed_terms]
        else:
            needed = mandatory_raw | {e['evidence_id'] for c in context.get('reviewed_base', []) for e in c.get('evidence', [])}
            needed |= {i for f in fields for c in context.get(f, []) for i in c.get('evidence_ids', [])}
            context['tool_originals'] = [b for b in context.get('tool_originals', []) if b['ref'] in needed]


def ordered_groups(run, groups, phase):
    """Keep saved order; rotate known anchors (or source groups before CQ extraction)."""
    order = run.setdefault('execution_order', {}).setdefault(phase, [])
    remaining = [g for g in groups if g['id'] not in order]
    priorities = sorted({g.get('priority', 0) for g in remaining})
    for priority in priorities:
        buckets = {}
        for g in remaining:
            if g.get('priority', 0)!=priority: continue
            anchor = g.get('anchor') or next(iter(g.get('cq_ids', [])), None) or g.get('source_group', '')
            buckets.setdefault(anchor, []).append(g)
        for values in buckets.values(): values.sort(key=lambda g: not g.get('requested_by_scout', False))
        order.extend(values[n]['id'] for n in range(max(map(len,buckets.values()))) for values in buckets.values() if n<len(values))
    by_id = {g['id']:g for g in groups}
    return [by_id[i] for i in order if i in by_id]


def review_reservation(run, round_number, by_id, context_map, available):
    from .discovery_synthesis import assemble
    # Preview on a copy: no successful unit, group assignment or representative ID changes.
    groups = run.get('candidate_groups', []) + assemble(deepcopy(run), round_number, by_id, context_map, available)
    succeeded = {u['id'] for u in run['analysis_units'] if u['status']=='succeeded'}
    pending = [dict(unit_id=stage+':'+g['id'],stage=stage,round=g.get('round',0)) for g in groups for stage in ('builder','critic') if stage+':'+g['id'] not in succeeded]
    estimates = run.setdefault('role_time_estimates', {})
    for stage in ('concept','relation','builder','critic','revision'):
        observed = [a['elapsed_s'] for u in run['analysis_units'] if u['stage']==stage for a in u.get('attempts', []) if a.get('elapsed_s') is not None]
        role = 'review' if stage=='critic' else 'draft'
        estimate = estimates.setdefault(stage, dict(initial_s=run['recipe']['call_timeout'],estimate_s=run['recipe']['call_timeout'],
            basis='미관측 역할: recipe 호출 제한시간',model_identity=deepcopy(run.get('model_identity', {}).get(role))))
        if observed:
            # First observation replaces the timeout prior; later estimates only rise.
            estimate['estimate_s'] = max(estimate['estimate_s'] if estimate.get('observed_count') else 0, max(observed)*1.25)
            estimate.update(basis='같은 실행·모델의 역할별 최대 실제 시간 × 1.25; 완료 보장 아님',observed_count=len(observed))
    reservation = dict(group_ids=[g['id'] for g in groups],pending_units=pending,model_calls=len(pending),
        estimated_model_s=round(sum(estimates[p['stage']]['estimate_s'] for p in pending),3))
    run['reserved_builder_critic_calls'] = len(pending)
    run['review_reservation'] = reservation
    return reservation


def process_group(service, run, group, index, blocks, by_id, context_map):
    key = group['id']; base = base_context(run)
    links = {c['id'] for c in run['cqs'] + run['scope_items']}
    base = [c for c in base if links & set(c.get('cq_ids', [])) or c.get('name', '') in ' '.join(by_id[i]['text'] for i in group['block_ids'])]
    group.pop('error', None)
    group['analysis_grounded'] = grounded_analysis(run, group, allowed_ids(service, blocks))
    group['status'] = 'analysis_succeeded' if group['analysis_grounded'] else 'unvisited'
    raw = segments.packet(group, by_id, context_map, packet)
    deps = [b['ref'] for b in raw] + [e['evidence_id'] for c in base for e in c['evidence']]
    base_raw = packet(list(dict.fromkeys(e['evidence_id'] for c in base for e in c['evidence'])), by_id, context_map)
    deps += [b['ref'] for b in base_raw]
    common = dict(blocks=raw, focus_spans=group.get('segments', []), reviewed_base=base, tool_originals=[b for b in base_raw if b['ref'] not in {r['ref'] for r in raw}], selection_reason=group['reason'])
    # Freeze the small comparison set before this group's first call; later results cannot alter resume input.
    if 'prior_comparisons' not in group:
        group['prior_comparisons'] = []
        text = ' '.join(v['text'] for v in raw if not v.get('context_only'))
        for candidate in lookup(service, run, '', 'any', blocks):
            if candidate.get('review_status')=='reviewed': continue
            same_span = any(e['block_id']==v['ref'] and e.get('span') and e['span'][0]<v.get('span',[0,len(v['text'])])[1]
                and v.get('span',[0])[0]<e['span'][1] for e in candidate.get('evidence_refs', []) for v in raw)
            if same_span or candidate.get('label') and candidate['label'] in text:
                group['prior_comparisons'].append(deepcopy(candidate))
            if len(group['prior_comparisons'])==5: break
    common['comparison_terms'] = deepcopy(group['prior_comparisons'])
    if group['prior_comparisons']:
        from .discovery_synthesis import context_for
        prior_context, prior_deps, _ = context_for(group['prior_comparisons'],by_id,context_map)
        common['tool_originals'].extend(prior_context['blocks'])
        deps += prior_deps
    scout_unit = next(u for u in run['analysis_units'] if u['id']=='scout:structure')
    common, deps, supplied_tools = with_tool_context(service, run, common, deps, [scout_unit], by_id, context_map)
    supplied = {c['id']:c for c in base}
    supplied.update({c['id']:c for c in group['prior_comparisons']})
    supplied.update(supplied_tools)
    previous = group.get('previous_observations', [])
    if group.get('recovery_request_id'):
        from .discovery_synthesis import context_for
        prior = previous + group.get('previous_relations', [])
        common.update(recovery_meaning=group['recovery_meaning'], recovery_meanings=group['recovery_meanings'],
            previous_observations=previous, previous_relations=group.get('previous_relations', []),
            previous_candidate_ids=[c['id'] for c in prior])
        common['reviewed_base'].extend(c for c in previous if c.get('review_status')=='reviewed' and c not in common['reviewed_base'])
        required_ids = set(group.get('required_endpoint_ids', [])) | set(group.get('required_comparison_ids', []))
        required = [c for c in prior if c['id'] in required_ids]
        endpoint_context, _, _ = context_for(required, by_id, context_map)
        group['required_endpoint_block_ids'] = sorted(raw_refs(endpoint_context['blocks']))
        common['tool_originals'].extend(endpoint_context['blocks'])
        supplied.update({c['id']:c for c in prior})
    roles = group.get('roles', ['concept','relation'])
    needed = [stage for stage in roles if not any(u['id']==stage+':'+key and u['status']=='succeeded' for u in run['analysis_units'])]
    if needed:
        reservation = review_reservation(run, group['round'], by_id, context_map, allowed_ids(service,blocks))
        future = needed + ['builder','critic'] # Minimum one new group; actual count is recomputed after analysis.
        budget = run['recipe']['budgets']; metrics = run['metrics']
        remaining_calls = budget['model_calls']-metrics['llm_calls']
        remaining_s = budget['model_seconds']-metrics['model_total_s']-metrics.get('interrupted_time_reserve_s', 0)
        estimated_s = reservation['estimated_model_s']+sum(run['role_time_estimates'][stage]['estimate_s'] for stage in future)
        proceed = remaining_calls >= reservation['model_calls']+len(future) and remaining_s >= estimated_s
        group['budget_allocation'] = dict(used_calls=metrics['llm_calls'],used_model_s=metrics['model_total_s'],
            remaining_calls=remaining_calls,remaining_model_s=remaining_s,pending_review_calls=reservation['model_calls'],
            next_minimum_calls=len(future),reserved_estimated_s=round(estimated_s,3),decision='analyze' if proceed else 'review_existing')
        if not proceed:
            group['error'] = '분석 및 실제 Builder/Critic 묶음 예약 호출/시간 예산 부족; 기존 후보 검수로 전환'
            return False
    group['status'] = 'raw_provided'
    relation_context, relation_supplied = deepcopy(common), dict(supplied)
    if 'concept' in roles:
        common, deps, supplied = analysis_context(run, 'concept', common, supplied, group, reserve=2000)
        concepts = call(service, run, 'concept', key, common, deps, by_id, supplied)
        if concepts is not None:
            apply_actions(service, run, index, blocks, 'concept', key, concepts)
            concept_unit = next(u for u in run['analysis_units'] if u['id']=='concept:'+key)
            relation_context, _, related = with_tool_context(service, run, relation_context, [], [concept_unit], by_id, context_map)
            relation_supplied.update(related)
        elif 'relation' not in roles:
            return
    if 'relation' in roles:
        completed = next((u for u in run['analysis_units'] if u['id']=='relation:'+key and u['status']=='succeeded'), None)
        if completed:
            if not set(completed['dependency_ids']) <= allowed_ids(service, blocks):
                raise ValueError('사용 중단/재검토 근거가 성공 관계 단위에 포함됨')
            relations = completed['output']
        else:
            # Source statements need originals, not Concept predictions. Keep legacy recovery endpoint definitions.
            required = set(group.get('required_endpoint_ids', []))
            for field in ('reviewed_base','comparison_terms','previous_observations','unapproved_observations'):
                retained = [c for c in relation_context.get(field, []) if c['id'] in required]
                if retained: relation_context[field] = retained
                else: relation_context.pop(field, None)
            relation_context, deps, relation_supplied = analysis_context(run, 'relation', relation_context, relation_supplied, group)
            relations = call(service, run, 'relation', key, relation_context, deps, by_id, relation_supplied)
        if relations is None: return
        apply_actions(service, run, index, blocks, 'relation', key, relations)
    capacity_status(run, group, by_id)
    group['analysis_grounded'] = grounded_analysis(run, group, allowed_ids(service, blocks))
    group['status'] = 'analysis_succeeded'
    save(service, run)


def capacity_status(run, group, by_id):
    markers = profile.numbered_items([by_id[i] for i in group['block_ids']])
    if group.get('segments'):
        markers = [m for m in markers if any(v['block_id']==m['block_id'] and v['span'][0]<=m['start']<v['span'][1] for v in group['segments'])]
    roles = {}
    pending = []
    for stage, field in (('concept', 'observations'), ('relation', 'relations')):
        limit = models.OUTPUTS[stage].model_json_schema()['properties'][field]['maxItems']
        unit = next((u for u in run['analysis_units'] if u['id'] == stage + ':' + group['id']), None)
        count = len(unit['output'][field]) if unit and unit['status'] == 'succeeded' else None
        roles[stage] = dict(limit=limit, output_count=count)
        if count == limit:
            pending.append(stage + ': 출력 상한 도달; 추가 누락 여부 미확인')
    if len(markers) > roles['concept']['limit']:
        pending.append('인식한 번호 목록이 관측 상한을 초과; 목록 수는 필요한 후보 수의 확정값이 아님')
    group['capacity'] = dict(roles=roles, numbered_items=markers,
                             semantic_completeness='미검증; 목록 신호가 없어도 완전성 보장 아님')
    group['capacity_pending'] = pending
    unit = next((u for u in run['analysis_units'] if u['id']=='relation:'+group['id'] and u['status']=='succeeded'), None)
    group['analysis_target_coverage'] = deepcopy((unit or {}).get('output', {}).get('target_coverage', []))
    if not group.get('recovery_request_id'):
        for target in group['analysis_target_coverage']:
            if target['candidate_ids'] or target['gaps']: continue
            ref = dict(evidence_id=target['block_id'],block_id=target['block_id'],span=target['span'])
            queue_recovery(run, {'missing_meanings':[dict(role='relation',meaning='제공 항의 관계 응답 미제출; 원문과 기존 산출을 대조하여 미표현 의미만 분석',
                evidence_refs=[ref],validation=[],trigger='target_response')]}, group, by_id)
    if pending and not group.get('recovery_request_id'):
        views = group.get('segments') or [dict(block_id=i,span=[0,len(by_id[i]['text'])]) for i in group['block_ids']]
        for stage in group.get('roles', ['concept','relation']):
            if roles[stage]['output_count'] != roles[stage]['limit']: continue
            refs = [dict(evidence_id=v['block_id'], block_id=v['block_id'], span=v['span']) for v in views]
            queue_recovery(run, {'missing_meanings':[dict(role=stage, meaning='출력 상한 이후 아직 제안하지 않은 의미만 확인; 기존 의미 반복 금지', evidence_refs=refs, validation=[], trigger='output_capacity')]}, group, by_id)


def grounded_analysis(run, group, available):
    if group.get('capacity_pending'): return False
    if any(not t['candidate_ids'] or t['gaps'] for t in group.get('analysis_target_coverage', [])): return False
    for stage, field in (('concept','observations'), ('relation','relations')):
        if stage not in group.get('roles', ['concept','relation']): continue
        unit = next((u for u in run['analysis_units'] if u['id']==stage+':'+group['id']), None)
        if not unit or unit['status']!='succeeded' or not set(unit['dependency_ids']) <= available:
            return False
        if not any(set(c['evidence_ids']) & set(group['block_ids']) for c in unit['output'][field]
                   if not c['validation'] and not c['outside_scope_reason']):
            return False
    return True


def linked_blocks(run, group, stage, available):
    field = 'observations' if stage=='concept' else 'relations'
    unit = next((u for u in run['analysis_units'] if u['id']==stage+':'+group['id']), None)
    if not unit or unit['status']!='succeeded' or not set(unit['dependency_ids']) <= available: return set()
    return {i for c in unit['output'][field] if not c['validation'] and not c['outside_scope_reason']
            for i in c['evidence_ids']} & set(group['block_ids'])


def finish(run, blocks, available):
    identities.register(run)
    by_id = {b['id']: b for b in blocks}
    for group in run.get('frontier', []):
        if set(group['block_ids']) <= by_id.keys():
            capacity_status(run, group, by_id)
        group['analysis_grounded'] = grounded_analysis(run, group, available)
    outputs = [u for u in run['analysis_units'] if u['status']=='succeeded' and set(u.get('dependency_ids', [])) <= available]
    original_observations = [c for u in outputs if u['stage'] in {'concept','builder'} for c in u['output'].get('observations', [])]
    original_relations = [c for u in outputs if u['stage']=='relation' for c in u['output'].get('relations', [])]
    rows = {c['id']:c for c in identities.rows(run, original_observations+original_relations, available)}
    rows.update({c['id']:c for c in identities.rows(run, [c for u in outputs if u['stage']=='builder' for c in u['output'].get('modeled_relations', [])], available)})
    history = [h for u in outputs for h in u['output'].get('history', [])]
    for h in history:
        candidate = identities.view(run,h['after'],revised=True)
        if candidate['id'] in rows: rows[candidate['id']] = candidate
    blocked_revisions = {identities.identifier(run,h['candidate_id']) for u in run['analysis_units'] if u['status']=='succeeded' and not set(u.get('dependency_ids', [])) <= available for h in u.get('output', {}).get('history', [])}
    rows = {i:c for i,c in rows.items() if i not in blocked_revisions}
    observations = [c for c in rows.values() if 'classification' in c]
    relations = [c for c in rows.values() if 'negation' in c]
    candidates = observations + relations
    current = {c['id']:c for g in run.get('candidate_groups', []) for c in g['candidates']}
    current.update(rows)
    for u in outputs:
        if u['stage'] not in {'builder','revision'}: continue
        for field in ('hierarchies','effective_hierarchies'):
            current.update({h['id']:identities.view(run,h) for h in u['output'].get(field, [])})
    latest_reviews = reviews.latest_by_candidate([u['output'] for u in outputs if u['stage']=='critic'],current)
    review_units = {u['group_id']:u['output'] for u in outputs if u['stage']=='critic'}
    for group in run.get('candidate_groups', []):
        followup = next((u for u in outputs if u['id']==group.get('revision_review_unit_id')), None)
        if followup: review_units[group['id']]=followup['output']
    reviewed_candidates = set().union(*(reviews.valid_ids(r,current,latest_reviews) or set() for r in review_units.values()))
    reviewed_candidates.update(i for g in run.get('candidate_groups', []) if g['id'] in review_units
        and reviews.valid_ids(review_units[g['id']],current) is None for i in g['primary_candidate_ids']+g.get('design_candidate_ids', []))
    reviewed = {g['id'] for g in run.get('candidate_groups', []) if g['status']=='review_issues_generated'
                and g['id'] in review_units and not review_units[g['id']].get('record_errors')
                and not review_units[g['id']].get('capacity_pending')
                and (reviews.valid_ids(review_units[g['id']]) is None or
                     set(review_units[g['id']].get('review_coverage', {}).get('expected_candidate_ids',
                         g['primary_candidate_ids']+g.get('design_candidate_ids', []))) <= reviews.valid_ids(review_units[g['id']]))
                and set(review_units[g['id']].get('review_coverage', {}).get('expected_candidate_ids', [])) <= reviewed_candidates}
    processed = {g['id'] for g in run.get('frontier', []) if not g.get('capacity_pending') and all(any(u['id']==stage+':'+g['id'] for u in outputs) for stage in g.get('roles', ['concept','relation']))}
    required_pending = [g['id'] for g in run.get('frontier', []) if g['required'] and g['id'] not in processed]
    required_pending += [g['id'] for g in run.get('candidate_groups', []) if g['id'] not in reviewed]
    reviewed_candidates -= {h['candidate_id'] for h in history
        if not any(h['candidate_id'] in (reviews.valid_ids(r,current,latest_reviews) or set()) for r in review_units.values())}
    unreviewed_candidates = sorted({identities.identifier(run,c['id']) for c in original_observations+original_relations
        if not c['validation'] and not c['outside_scope_reason'] and identities.identifier(run,c['id']) not in reviewed_candidates})
    no_result = [dict(group_id=g['id'], empty_roles=[stage for stage in g.get('roles', ['concept','relation'])
                  if not linked_blocks(run,g,stage,available)]) for g in run.get('frontier', []) if g['id'] in processed]
    no_result = [g for g in no_result if g['empty_roles']]
    failures = [dict(unit_id=u['id'], error=u.get('error')) for u in run['analysis_units'] if u['status']!='succeeded']
    gaps = [v for u in outputs for v in u['output'].get('gaps', [])]
    gaps.extend(r['gap'] for u in outputs for r in u.get('tool_results', []) if r.get('gap'))
    coverage = []
    for kind, items, field in [('cq',run['cqs'],'cq_ids'),('scope',run['scope_items'],'scope_item_ids')]:
        for item in items:
            linked = [c['id'] for c in candidates if item['id'] in c[field] and not c['validation'] and not c['outside_scope_reason']]
            coverage.append(dict(kind=kind, id=item['id'], candidate_ids=linked,
                status='evidence_linked' if linked else 'gap', reason='연결 후보 존재; 의미 해결 미검증' if linked else '자료 필요 또는 후보 누락; 사람 검수 필요'))
    provided = {i for u in run['analysis_units'] if u.get('attempts') for i in u.get('provided_block_ids', [])}
    concept_linked = set().union(*(linked_blocks(run,g,'concept',available) for g in run.get('frontier', [])))
    relation_linked = set().union(*(linked_blocks(run,g,'relation',available) for g in run.get('frontier', [])))
    both_linked = concept_linked & relation_linked
    capacity_pending_ids = {i for g in run.get('frontier', []) if g.get('capacity_pending') for i in g['block_ids']}
    incomplete_blocks = {i for g in run.get('frontier', []) if not g['analysis_grounded'] for i in g['block_ids']}
    analyzed = both_linked - capacity_pending_ids - incomplete_blocks
    selected = {i for g in run.get('frontier', []) for i in g['block_ids']}
    unfulfilled = sorted({i for r in run['extra_requests'] for i in r['block_ids']} - provided)
    titles = [f['title'] for f in run['frozen_input']['files']]
    reference_gaps = [dict(file_id=p['file_id'], reference=ref, status='자료 필요: 선택 목록 표제에서 참조 대상 미확인')
                      for p in run.get('profiles', []) for ref in p['reference_expressions'] if not any(ref in title for title in titles)]
    for unit in run['analysis_units']:
        if unit['status']!='succeeded' and '예산' in (unit.get('error') or ''):
            queue_recovery(run, {'issues':[dict(cause='budget_exhausted',reason=unit['error'],defer_reason=unit['error'])]}, dict(id=unit['id']))
    for request in run.get('recovery_requests', []):
        request['semantic_status']='unverified'
        group = next((g for g in run.get('frontier', []) if g['id']==request.get('group_id')), None)
        units = [u for u in outputs if group and u['group_id']==group['id']]
        unit = next((u for u in run['analysis_units'] if u['id']==request.get('unit_id')), None)
        created = [c['id'] for u in units for field in ('observations','relations') for c in u['output'].get(field, []) if not c['validation'] and not c['outside_scope_reason']]
        if unit and unit['status']=='succeeded':
            created += [h['candidate_id'] for h in unit['output'].get('history', []) if h['candidate_id']==request.get('candidate_ref') and not h['after']['validation']
                        and (meaning_signature(h['before'])!=meaning_signature(h['after']) or h['before'].get('evidence_refs')!=h['after'].get('evidence_refs'))]
        request['proposal_ids'] = created
        if request['validation']:
            request.update(status='invalid',reason='; '.join(request['validation']))
        elif group or unit:
            error = (unit or {}).get('error') or (group or {}).get('error') or ''
            if created:
                request.update(status='proposals_created',reason='제안 생성; 요청 의미 충족과 사람 검수 완료는 미확인')
            elif '예산' in error:
                request.update(status='budget_exhausted',stop_cause='budget_exhausted',reason=error)
            else:
                deferred = [d['reason'] for d in (unit or {}).get('output', {}).get('deferred', []) if d['candidate_ref']==request.get('candidate_ref')]
                request.update(status='unresolved',reason=error or '; '.join(deferred) or '새 유효 제안 없음 또는 기존 의미 반복; 동일 대상 자동 재시도 없음')
        elif request['status']=='pending':
            if run['status']=='cancel_requested': request['reason']='취소로 미실행; 같은 입력으로 재개 가능'
            elif request['role'] in {'concept','relation'}:
                request.update(status='budget_exhausted',stop_cause='budget_exhausted',reason='추가 round 예산 종료; 자동 증액 없음')
            else:
                request.update(status='manual_review',reason='자동 수정 미선택 또는 유효 검토 부족; 대상 후보 명시 검수 필요')
        request['unattempted_meanings'] = [m for m in request.get('meanings', []) if m not in request.get('submitted_meanings', request.get('meanings', []))]
        request['proposal_review_status'] = 'unverified'  # A Critic output is not human acceptance.
    unresolved_recovery = list(run.get('recovery_requests', []))
    recovery_groups_ids = {r['group_id'] for r in unresolved_recovery if r.get('group_id')}
    recovery_groups_ids.update(g['id'] for g in run.get('candidate_groups', []) if recovery_groups_ids & set(g['analysis_group_ids']))
    recovery_units = [u for u in run['analysis_units'] if u.get('group_id') in recovery_groups_ids or u['id'] in {r.get('unit_id') for r in unresolved_recovery}]
    attempts = [a for u in recovery_units for a in u['attempts']]
    run['metrics'].update(recovery_calls=len(attempts), recovery_model_s=round(sum(a.get('elapsed_s',0) for a in attempts),3),
        recovery_attempted_tasks=sum(any(u['attempts'] and (u['id']==r.get('unit_id') or u.get('group_id')==r.get('group_id')) for u in recovery_units) for r in unresolved_recovery),
        recovery_remaining_by_cause={cause:sum(r.get('cause','extraction_missing')==cause for r in unresolved_recovery)
            for cause in sorted({r.get('cause','extraction_missing') for r in unresolved_recovery})})
    compared = {c['id'] for g in run.get('candidate_groups', []) if g['id'] in reviewed for c in g['candidates']}
    deferred_comparisons = sorted({i for g in run.get('frontier', []) for i in g.get('omitted_comparison_ids', []) if i not in compared})
    bindings = [dict(unit_id=u['id'],**u['output']['binding_coverage']) for u in outputs if 'binding_coverage' in u['output']]
    binding_pending = [i for b in bindings for i in b['pending_relation_ids']+b['deferred_relation_ids']]
    run['result'] = dict(reference_gaps=reference_gaps, unfulfilled_read_requests=unfulfilled, payload_version='a2-analysis-v2', review_status='unreviewed',
        design_binding_coverage=bindings, design_pending_relation_ids=sorted(set(binding_pending)),
        analysis_target_coverage=[dict(group_id=g['id'],**t) for g in run.get('frontier', []) for t in g.get('analysis_target_coverage', [])],
        review_outcomes=[dict(unit_id=u['id'],**u['output']['review_outcomes']) for u in outputs if 'review_outcomes' in u['output']],
        original_observations=original_observations, original_relations=original_relations, revision_history=history,
        revisions=[dict(unit_id=u['id'], **identities.output(run,u['output'])) for u in outputs if u['stage']=='revision'],
        revision_deferrals=[d for g in run.get('candidate_groups', []) for d in g.get('revision_deferrals', [])],
        observations=[c for c in observations if not c['outside_scope_reason']],
        relations=[c for c in relations if not c['outside_scope_reason']],
        outside_scope=[c for c in candidates if c['outside_scope_reason']],
        alignments=[identities.alignment(run,a) for u in outputs for a in u['output'].get('alignments', [])],
        taxonomy=[dict(unit_id=u['id'], **identities.output(run,u['output'])) for u in outputs if u['stage']=='builder'],
        critiques=[dict(unit_id=u['id'], **u['output']) for u in outputs if u['stage']=='critic'],
        review_pending_candidate_ids=sorted({i for i,c in current.items() if c.get('review_status')!='reviewed'} - reviewed_candidates -
            set().union(*(reviews.valid_ids(r,current,latest_reviews) or set() for r in review_units.values()))),
        review_record_errors=[dict(unit_id=u['id'],**error) for u in outputs if u['stage']=='critic' for error in u['output'].get('record_errors', [])],
        recovery_requests=run.get('recovery_requests', []), unresolved_recovery_requests=unresolved_recovery,
        deferred_comparison_ids=deferred_comparisons,
        capacity_pending=[dict(group_id=g['id'], reasons=g['capacity_pending'], **g['capacity'])
                          for g in run.get('frontier', []) if g.get('capacity_pending')]
                         + [dict(group_id=i,stage='critic',reasons=r['capacity_pending'],**r['capacity'])
                            for i,r in review_units.items() if r.get('capacity_pending')],
        incomplete_review_searches=[dict(group_id=g['id'], **search) for g in run.get('candidate_groups', [])
                                   for search in g.get('critic_searches', []) if search['status']!='succeeded'],
        coverage=coverage, gaps=gaps, failures=failures, mandatory_pending=required_pending,
        unavailable_block_ids=sorted({b['id'] for b in blocks}-available),
        structure_surveyed=len(blocks), raw_provided=len(provided), analysis_succeeded=len(analyzed),
        analysis_groups=len(run.get('frontier', [])), processed_analysis_groups=len(processed),
        segment_coverage=[dict(group_id=g['id'], segments=g.get('segments', []), status=g['status'], evidence_linked=g['analysis_grounded']) for g in run.get('frontier', [])],
        candidate_groups=len(run.get('candidate_groups', [])), no_result_groups=no_result, unreviewed_candidate_ids=unreviewed_candidates,
        selected_analysis_block_ids=sorted(selected), not_selected_block_ids=sorted({b['id'] for b in blocks}-selected),
        concept_evidence_block_ids=sorted(concept_linked), relation_evidence_block_ids=sorted(relation_linked),
        evidence_linked_block_ids=sorted(concept_linked | relation_linked), both_roles_evidence_block_ids=sorted(both_linked),
        processed_without_linked_evidence_ids=sorted({i for g in run.get('frontier', []) if g['id'] in processed for i in g['block_ids']}-(concept_linked|relation_linked)),
        review_groups=len(reviewed), unvisited_block_ids=sorted({b['id'] for b in blocks}-provided),
        unanalysed_block_ids=sorted({b['id'] for b in blocks}-analyzed),
        incomplete_file_ids=[u['file_id'] for u in run['units'] if u['status']!='succeeded'],
        unprocessed_features=[dict(file_id=g['file_id'], features=g['features']) for g in run.get('frontier', [])
                              if not g.get('analysis_grounded') and g['features']])
    if identities.enabled(run): run['result']['candidate_identity'] = deepcopy(run['candidate_identity'])
    has_errors = any(u.get('tool_errors') or u['output'].get('binding_errors') for u in outputs) or any(g.get('error') for g in run.get('frontier', []) + run.get('candidate_groups', []))
    incomplete = bool(binding_pending or deferred_comparisons or unresolved_recovery or run['result']['capacity_pending'] or run['result']['incomplete_review_searches'] or required_pending or unreviewed_candidates or no_result or run['result']['revision_deferrals'] or failures or has_errors or unfulfilled or run['result']['incomplete_file_ids'] or
                      run['result']['unavailable_block_ids'] or run.get('error') or
                      any(p.get('csv', {}).get('unresolved_block_ids') for p in run.get('profiles', [])))
    run['status'] = 'cancelled' if run['status']=='cancel_requested' else 'partial' if incomplete else 'review_ready'
    run['stop_reason'] = ('취소 요청: 현재 호출 저장 후 중단' if run['status']=='cancelled' else
                          '필수 미처리/실패/사용 중단/예산 잔여 확인 필요' if incomplete else
                          '필수 분석과 쟁점 저장 완료; 초안 검수 준비이며 의미 정확성/운영 승인 아님')


def execute(service, run_id):
    started = monotonic(); run = service.run(run_id); blocks = []
    run['started_at'] = utcnow()
    if run['status'] != 'cancel_requested': run['status'] = 'running'
    save(service, run)
    try:
        identity = model_identity(run['recipe'])
        if run.get('model_identity') and identity != run['model_identity']:
            raise ValueError('재개 모델 digest가 고정값과 다름')
        run['model_identity'] = identity
        blocks = load_blocks(service, run); by_id = {b['id']: b for b in blocks}
        if not blocks: raise ValueError('분석 가능한 완료 원문 블록 없음')
        if 'profiles' not in run:
            profiles, frontier, context_map = profile.survey(run['frozen_input']['files'], blocks)
            full_frontier = deepcopy(frontier)
            if run.get('analysis_block_ids') is not None:
                selected = set(run['analysis_block_ids'])
                frontier = []
                for group in full_frontier:
                    ids = [i for i in group['block_ids'] if i in selected]
                    if ids:
                        frontier.append(dict(group, block_ids=ids, reason=group['reason']+'; '+run['analysis_selection_reason']))
                assigned = {i for g in frontier for i in g['block_ids']}
                for identifier in sorted(selected-assigned):
                    b = by_id[identifier]
                    frontier.append(dict(id='selected_'+identifier, file_id=b['file_id'], source_group=b['source_group'],
                        block_ids=[identifier], features=[], priority=2, required=True, input_chars=len(b['text']),
                        round=0, reason=run['analysis_selection_reason'], status='unvisited'))
            frontier = segments.expand(frontier, by_id)
            run.update(profiles=profiles, frontier=frontier, full_frontier=full_frontier, candidate_groups=[],

                scout_frontier=[{k:g[k] for k in ('id','file_id','priority','input_chars','reason')} for g in frontier],
                expected_analysis_calls=1+2*len(frontier), reserved_builder_critic_calls=0,
                initial_full_analysis_groups=len(full_frontier), synthesis_call_formula='1 + 2m + 2g + revisions; g는 후보 조립 후 확정')
        else:
            profiles = run['profiles']
            context_map = {}
            for file in run['frozen_input']['files']:
                context_map.update(profile.contexts([b for b in blocks if b['file_id']==file['file_id']]))
        save(service, run)
        index = frozen_index(service, run, blocks)
        # Profile evidence is a dependency too: revoked rows cannot leak through summaries.
        scout_profiles = [{k:v for k,v in p.items() if k not in {'exception_block_ids'}} for p in profiles]
        for p in scout_profiles:
            if 'csv' in p:
                p['csv'] = {k:v for k,v in p['csv'].items() if k not in {'selected', 'unresolved_block_ids'}}
        scout = call(service, run, 'scout', 'structure', dict(profiles=scout_profiles,
            frontier=run['scout_frontier']),
            list(by_id), by_id)
        if scout is None: return
        apply_actions(service, run, index, blocks, 'scout', 'structure', scout)
        from .discovery_synthesis import synthesize
        for round_number in range(run['recipe']['budgets']['additional_rounds']+1):
            pending = ordered_groups(run, [g for g in run['frontier'] if g['round']==round_number], 'analysis:'+str(round_number))
            review_blocked = False
            for group in pending:
                while True:
                    if cancelled(service, run): return
                    proceed = process_group(service, run, group, index, blocks, by_id, context_map)
                    reservation = review_reservation(run, round_number, by_id, context_map, allowed_ids(service,blocks))
                    save(service, run)
                    if proceed is not False or not any(p['round']<=round_number for p in reservation['pending_units']): break
                    successful = {u['id'] for u in run['analysis_units'] if u['status']=='succeeded'}
                    run.setdefault('budget_transitions', []).append(dict(group_id=group['id'],**group['budget_allocation']))
                    synthesize(service, run, round_number, index, blocks, by_id, context_map, allow_revisions=False)
                    reservation = review_reservation(run, round_number, by_id, context_map, allowed_ids(service,blocks))
                    review_blocked = (any(p['round']<=round_number for p in reservation['pending_units']) or
                        not ({u['id'] for u in run['analysis_units'] if u['status']=='succeeded'}-successful))
                    if review_blocked: break
                    # Review observations can release the conservative initial time reservation.
                if proceed is False:
                    queue_recovery(run, {'issues':[dict(cause='budget_exhausted',reason=group['error'],defer_reason=group['error'])]}, group)
                save(service, run)
                if proceed is False: break
            successful = {u['id'] for u in run['analysis_units'] if u['status']=='succeeded'}
            primary_pending = any(stage+':'+g['id'] not in successful for g in pending for stage in g.get('roles',['concept','relation']))
            if not review_blocked:
                synthesize(service, run, round_number, index, blocks, by_id, context_map, allow_revisions=not primary_pending)
            reservation = review_reservation(run, round_number, by_id, context_map, allowed_ids(service,blocks))
            # Later saved rounds must remain reachable on resume; only earlier work blocks them.
            if primary_pending or any(p['round']<=round_number for p in reservation['pending_units']): break
            if round_number == run['recipe']['budgets']['additional_rounds']: break
            run['frontier'].extend(recovery_groups(run, round_number+1, by_id))
            assigned = {i for g in run['frontier'] for i in g['block_ids']}
            for request in run['extra_requests']:
                if request.get('purpose')!='analysis': continue
                ids = [i for i in request['block_ids'] if i not in assigned and (run.get('analysis_block_ids') is None or i in run['analysis_block_ids'])]
                if ids:
                    group = dict(id='x_'+profile.digest(ids)[:20], file_id=by_id[ids[0]]['file_id'],
                        source_group=by_id[ids[0]]['source_group'], block_ids=ids, features=[], priority=2,
                        required=False, input_chars=sum(len(by_id[i]['text']) for i in ids),
                        round=round_number+1, reason=request['reason'], status='unvisited')
                    run['frontier'].append(group); assigned.update(ids)
            save(service, run)
    except Exception as exc:
        run['error'] = str(exc)
    finally:
        finish(run, blocks, allowed_ids(service, blocks))
        run['finished_at'] = utcnow()
        run['metrics']['elapsed_s'] = round(run['metrics']['elapsed_s']+monotonic()-started,3)
        with service.lock, service.repository.connect() as db:
            if service.repository.get(db, 'runs', run_id)['status']=='cancel_requested':
                run['status'] = 'cancelled'; run['stop_reason'] = '취소 요청: 현재 호출 저장 후 중단'
            service.repository.save(db, 'runs', run)


def frozen_index(service, run, blocks):
    key = run['input_run_id']
    with service.lock:
        cache = getattr(service, '_discovery_indexes', {})
        if key not in cache:
            if len(cache) >= 4:
                cache.pop(next(iter(cache)))
            cache[key] = profile.FrozenIndex(blocks)
            service._discovery_indexes = cache
        return cache[key]


def search_run(service, run, query, limit):
    blocks = load_blocks(service, run)
    index = frozen_index(service, run, blocks)
    by_id = {b['id']: b for b in blocks}
    hits = index.search(query, allowed_ids(service, blocks), limit)
    return dict(**grounding._metadata(run), query=query,
        items=[dict(by_id[h['block_id']], score=h['score']) for h in hits],
        incomplete_file_ids=[u['file_id'] for u in run['units'] if u['status']!='succeeded'])


def terms(service, run_id, label, term_type='any'):
    run = service.run(run_id)
    if run.get('discovery_mode') != 'analyze':
        raise ValueError('A2 분석 실행이 필요합니다.')
    models.Action(action='lookup_term', label=label, term_type=term_type, reason='용어 조회')
    return dict(**grounding._metadata(run), items=lookup(service, run, label, term_type, load_blocks(service, run)))


def raw_refs(value):
    refs = set()
    if isinstance(value, dict):
        if 'ref' in value and 'text' in value:
            refs.add(value['ref'])
        for child in value.values(): refs.update(raw_refs(child))
    elif isinstance(value, list):
        for child in value: refs.update(raw_refs(child))
    return refs


def with_tool_context(service, run, context, deps, units, by_id, context_map):
    """A tool's returned original/term must reach a bounded subsequent role to count as read."""
    context = deepcopy(context)
    allowed = allowed_ids(service, list(by_id.values()))
    terms, ids = [], []
    for unit in units:
        for result in unit.get('tool_results', []):
            for term in result.get('terms', []):
                dependencies = set(term.get('origin_dependency_ids', [])) | set(term.get('evidence_ids', [])) | {e['evidence_id'] for e in term.get('evidence', [])}
                if not dependencies <= allowed:
                    raise ValueError('조회한 용어의 파생 근거 사용 중단')
                terms.append(term); ids.extend(dependencies)
            ids.extend(result.get('block_ids', []))
    if not set(ids) <= allowed:
        raise ValueError('도구 조회 결과의 사용 상태 변경')
    extra = packet(list(dict.fromkeys(ids)), by_id, context_map)
    existing = raw_refs(context)
    context.setdefault('tool_originals', []).extend(b for b in extra if b['ref'] not in existing)
    context.setdefault('comparison_terms', []).extend(terms)
    return context, list(dict.fromkeys(deps + [b['ref'] for b in extra])), {t['id']: t for t in terms}

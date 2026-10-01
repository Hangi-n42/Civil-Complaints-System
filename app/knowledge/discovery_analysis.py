"""Bounded A2 roles on A1 evidence and the existing serial executor. No ontology writes."""
import asyncio
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

import httpx

from app.core.config import settings
from app.generation.service import GenerationService, local_ollama_url
from . import discovery_run as grounding, discovery_models as models, discovery_profile as profile
from .service import KnowledgeConflict, encode, utcnow

PROMPT_VERSION = 'discovery-a2-v8'


def recipe(budgets):
    return dict(profile_version='a2-survey-v3', prompt_version=PROMPT_VERSION, prompt_hash=profile.digest([models.COMMON, models.PROMPTS]),
        models=dict(draft=settings.STRUCTURING_MODEL, review=settings.KNOWLEDGE_REVIEW_MODEL),
        endpoint=local_ollama_url(settings.OLLAMA_BASE_URL), budgets=budgets,
        num_ctx=32768, num_predict=4096, think=False, input_chars=12000,
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
                if unit['status'] != 'succeeded' and not (unit['stage']=='revision' and unit['attempts']):
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
    def usable(candidate):
        ids = {e['evidence_id'] for e in candidate.get('evidence', [])} | set(candidate.get('evidence_ids', []))
        return bool(ids) and ids <= allowed
    candidates = [dict(c, review_status='reviewed') for c in run['base_candidates'] if usable(c)]
    rows = {}
    for u in run['analysis_units']:
        if u['status']!='succeeded' or not set(u['dependency_ids']) <= allowed: continue
        for c in u.get('output', {}).get('observations', []):
            rows[c['id']] = dict(c, origin_dependency_ids=u['dependency_ids'])
        for h in u.get('output', {}).get('history', []):
            if 'classification' in h['after']:
                rows[h['candidate_id']] = dict(h['after'], origin_dependency_ids=u['dependency_ids'])
    blocked_revisions = {h['candidate_id'] for u in run['analysis_units'] if u['status']=='succeeded' and not set(u.get('dependency_ids', [])) <= allowed for h in u.get('output', {}).get('history', [])}
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


def dispatch(service, run, index, blocks, action):
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
        run['extra_requests'].append(dict(block_ids=result['block_ids'], reason=action.reason))
    save(service, run)
    return result


def packet(ids, by_id, context_map):
    complete = list(dict.fromkeys(i for bid in ids for i in context_map[bid]['block_ids']))
    return [dict(ref=i, text=by_id[i]['text'], locator=by_id[i]['locator'], title=by_id[i]['title'],
                 source_role=by_id[i]['role'], table_context={k:v for k,v in context_map[i].items() if k!='block_ids'}) for i in complete]


def compact(value):
    if isinstance(value, list):
        return [compact(v) for v in value]
    if isinstance(value, dict):
        return {k: compact(v) for k,v in value.items() if k not in {'evidence_refs', 'input_hash', 'origin_dependency_ids', 'local_ref'}}
    return value


def remap(value, mapping):
    if isinstance(value, list):
        return [remap(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: remap(v, mapping) for k,v in value.items()}
    return mapping.get(value, value) if isinstance(value, str) else value


def normalize(output, stage, run, deps, by_id, supplied):
    if any(not text.strip() for field in ('findings','gaps') for text in output.get(field, [])):
        raise ValueError('조사 결과/미해결 사유는 빈 문자열일 수 없음')
    if not any(output.get(field) for field in models.RESULT_FIELDS[stage]):
        raise ValueError('빈 분석에는 구체적인 결과 또는 미해결 사유 필요')
    cq_ids = {c['id'] for c in run['cqs']}; scope_ids = {c['id'] for c in run['scope_items']}
    def refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'evidence_ids', 'counter_evidence_ids'} and not set(child) <= set(deps):
                    raise ValueError('실제 모델 입력 밖 근거 ID')
                refs(child)
        elif isinstance(value, list):
            for child in value: refs(child)
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
                replacement = normalize({field:[row]}, role, run, deps, by_id, supplied)[field][0]
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
    issues = output.get('issues', [])
    if len({i['local_ref'] for i in issues}) != len(issues):
        raise ValueError('응답 내부 쟁점 local_ref 중복')
    issue_refs = {}
    for issue in issues:
        if not issue['evidence_ids'] and not issue['counter_evidence_ids'] and not issue['defer_reason'].strip():
            raise ValueError('근거 없는 쟁점에는 명시적 보류 사유 필요')
        if issue['candidate_ref'] and issue['candidate_ref'] not in supplied:
            raise ValueError('검토 대상 후보 참조 불일치')
        issue['id'] = 'di_' + uuid4().hex
        issue_refs[issue['local_ref']] = issue['id']
    for action in output.get('actions', []):
        if action['action'] == 'request_evidence':
            identifier = issue_refs.get(action['issue_id'], action['issue_id'])
            if identifier not in set(issue_refs.values()) | issue_ids(run):
                raise ValueError('추가 근거 요청의 쟁점 참조 불일치')
            action['issue_id'] = identifier
    for check in output.get('relation_checks', []):
        if check['candidate_ref'] not in supplied or 'negation' not in supplied[check['candidate_ref']]:
            raise ValueError('관계 검토 대상 불일치')
        if check['judgment'] != 'unknown' and not check['quote']:
            raise ValueError('관계 판단에는 원문 인용 필요')
        if check['quote'] and (check['evidence_id'] not in deps or check['quote'] not in by_id[check['evidence_id']]['text']):
            raise ValueError('관계 판단 인용이 제공 원문과 불일치')
    return output


def issue_ids(run):
    return {i['id'] for u in run.get('analysis_units', []) if u['status']=='succeeded'
            for i in u.get('output', {}).get('issues', [])}


async def model_call(prompt, schema, stage, run, timeout):
    return await GenerationService().call_ollama(prompt, temperature=0, response_schema=schema,
        model=run['recipe']['models']['review' if stage=='critic' else 'draft'],
        num_predict=run['recipe']['num_predict'], num_ctx=run['recipe']['num_ctx'], think=False,
        timeout=timeout, return_metadata=True, local_only=True)


def make_prompt(run, stage, context, deps, supplied):
    mapping = {i: 'e'+str(n) for n,i in enumerate(sorted(set(deps)))}
    mapping.update({i: 'c'+str(n) for n,i in enumerate(sorted(supplied))})
    payload = dict(cqs=run['cqs'], scope_items=run['scope_items'], **context)
    prompt = models.COMMON + models.PROMPTS[stage] + '\nINPUT:\n' + json.dumps(remap(compact(payload), mapping), ensure_ascii=False, separators=(',', ':'))
    return mapping, prompt


def call(service, run, stage, key, context, deps, by_id, supplied=None):
    supplied = supplied or {}
    uid = stage + ':' + key
    unit = next((u for u in run['analysis_units'] if u['id']==uid), None)
    if unit is None:
        unit = dict(id=uid, stage=stage, group_id=key, status='queued', attempts=[], error=None)
        run['analysis_units'].append(unit)
    mapping, prompt = make_prompt(run, stage, context, deps, supplied)
    input_hash = profile.digest([prompt, run['recipe']])
    unit['dependency_ids'] = sorted(set(deps))
    unit['provided_block_ids'] = sorted(raw_refs(context))
    citation_ids = unit['provided_block_ids']
    try:
        if not set(deps) <= allowed_ids(service, list(by_id.values())):
            raise ValueError('사용 중단/재검토 근거가 원문 또는 파생 입력에 포함됨')
        if unit['status'] == 'succeeded':
            if unit['input_hash'] != input_hash:
                raise ValueError('성공 단위의 입력 해시 변경: 새 실행 필요')
            return unit['output']
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
        alignment = schema.get('$defs', {}).get('Alignment')
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
        for name, field in [('ObservationRevision','classification'), ('RelationRevision','negation'), ('HierarchyRevision','child_ref'), ('Deferred',None), ('RelationCheck','negation')]:
            definition = schema.get('$defs', {}).get(name)
            if definition:
                ids = [mapping[i] for i,c in supplied.items() if field is None or field in c]
                if stage=='revision':
                    ids = [mapping[i] for i in context['target_ids'] if field is None or field in supplied[i]]
                definition['properties']['candidate_ref']['enum'] = ids or ['']
                if name=='RelationCheck':
                    definition['required'] = list(definition['properties'])
                    schema['required'] = list(schema['properties'])
                    definition['properties']['evidence_id']['enum'] = ['', *[mapping[i] for i in citation_ids]]
                    schema['properties']['relation_checks'].update(minItems=len(context.get('unapproved_relations', [])), maxItems=len(context.get('unapproved_relations', [])))
        if stage=='revision':
            for field, marker in [('observations','classification'), ('relations','negation'), ('hierarchies','child_ref')]:
                schema['properties'][field]['maxItems'] = min(5, sum(marker in supplied[i] for i in context['target_ids']))
        hierarchy_schema = schema.get('$defs', {}).get('Hierarchy') or schema.get('$defs', {}).get('HierarchyRevision')
        if hierarchy_schema:
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
            if 'cq_ids' in props:
                for field, values in [('cq_ids', run['cqs']), ('scope_item_ids', run['scope_items'])]:
                    if values:
                        props[field]['items']['enum'] = [c['id'] for c in values]
                    else:
                        # Ollama rejects enum=[] even on an optional array. Preserve the empty selection.
                        props[field]['maxItems'] = 0
                definition['required'] = list(props)
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
            variant['properties'][field]['minItems'] = max(1, variant['properties'][field].get('minItems', 0))
            variants.append(variant)
        schema = {'$defs':schema.get('$defs', {}), 'anyOf':variants}
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
            output = models.OUTPUTS[stage].model_validate_json(metadata['text']).model_dump()
            output = remap(output, {v:k for k,v in mapping.items()})
            if not set(deps) <= allowed_ids(service, list(by_id.values())):
                raise ValueError('호출 중 입력 근거 사용 상태 변경')
            output = normalize(output, stage, run, citation_ids, by_id, supplied)
            if stage in {'concept', 'relation'}:
                rows = output['observations' if stage=='concept' else 'relations']
                primary = raw_refs(context.get('blocks', []))
                if rows and not any(primary & set(c['evidence_ids']) for c in rows) and not output['gaps']:
                    raise ValueError('주 분석 원문 근거 또는 해당 자료의 분석 공백 필요')
            if stage == 'critic':
                expected = {(h['child_ref'],h['parent_ref'],h['relation']) for h in context.get('taxonomy', {}).get('hierarchies', [])}
                actual = {(h['child_ref'],h['parent_ref'],h['relation']) for h in output['hierarchy_checks']}
                if expected != actual:
                    raise ValueError('제안 계층의 양방향 반례 검토 누락/추가')
                expected_relations = {c['id'] for c in context.get('unapproved_relations', [])}
                checks = [c['candidate_ref'] for c in output['relation_checks']]
                if len(checks)!=len(set(checks)) or set(checks)!=expected_relations:
                    raise ValueError('제안 관계의 부정 범위 검토 누락/추가')
            if stage=='revision':
                covered = {h['candidate_id'] for h in output['history']} | {d['candidate_ref'] for d in output['deferred']}
                if covered != set(context['target_ids']):
                    raise ValueError('수정 대상의 수정 또는 명시적 보류 누락')
            unit.update(output=output, status='succeeded')
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
            result = dispatch(service, run, index, blocks, action)
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
            for c in run['base_candidates']]


def process_group(service, run, group, index, blocks, by_id, context_map):
    key = group['id']; base = base_context(run)
    links = {c['id'] for c in run['cqs'] + run['scope_items']}
    base = [c for c in base if links & set(c.get('cq_ids', [])) or c.get('name', '') in ' '.join(by_id[i]['text'] for i in group['block_ids'])]
    group.pop('error', None)
    group['analysis_grounded'] = grounded_analysis(run, group, allowed_ids(service, blocks))
    group['status'] = 'analysis_succeeded' if group['analysis_grounded'] else 'unvisited'
    raw = packet(group['block_ids'], by_id, context_map)
    deps = [b['ref'] for b in raw] + [e['evidence_id'] for c in base for e in c['evidence']]
    base_raw = packet(list(dict.fromkeys(e['evidence_id'] for c in base for e in c['evidence'])), by_id, context_map)
    deps += [b['ref'] for b in base_raw]
    common = dict(blocks=raw, reviewed_base=base, tool_originals=[b for b in base_raw if b['ref'] not in {r['ref'] for r in raw}], selection_reason=group['reason'])
    scout_unit = next(u for u in run['analysis_units'] if u['id']=='scout:structure')
    common, deps, supplied_tools = with_tool_context(service, run, common, deps, [scout_unit], by_id, context_map)
    supplied = {c['id']:c for c in base}
    supplied.update(supplied_tools)
    needed = sum(not any(u['id']==stage+':'+key and u['status']=='succeeded' for u in run['analysis_units'])
                 for stage in ('concept','relation'))
    if needed: needed += 2 # Reserve synthesis and independent review before another analysis group.
    if run['metrics']['llm_calls'] + needed > run['recipe']['budgets']['model_calls']:
        group['error'] = '분석 및 Builder/Critic 예약 호출 예산 부족'
        return
    group['status'] = 'raw_provided'
    concepts = call(service, run, 'concept', key, common, deps, by_id, supplied)
    if concepts is None: return
    apply_actions(service, run, index, blocks, 'concept', key, concepts)
    observations = [c for c in concepts['observations'] if not c['validation'] and not c['outside_scope_reason']]
    supplied.update({c['id']:c for c in observations})
    concept_unit = next(u for u in run['analysis_units'] if u['id']=='concept:'+key)
    common, deps, related = with_tool_context(service, run, common, deps, [concept_unit], by_id, context_map)
    supplied.update(related)
    relations = call(service, run, 'relation', key, dict(common, unapproved_observations=observations), deps, by_id, supplied)
    if relations is None: return
    apply_actions(service, run, index, blocks, 'relation', key, relations)
    group['analysis_grounded'] = grounded_analysis(run, group, allowed_ids(service, blocks))
    group['status'] = 'analysis_succeeded'
    save(service, run)


def grounded_analysis(run, group, available):
    for stage, field in (('concept','observations'), ('relation','relations')):
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
    for group in run.get('frontier', []):
        group['analysis_grounded'] = grounded_analysis(run, group, available)
    outputs = [u for u in run['analysis_units'] if u['status']=='succeeded' and set(u.get('dependency_ids', [])) <= available]
    original_observations = [c for u in outputs if u['stage']=='concept' for c in u['output'].get('observations', [])]
    original_relations = [c for u in outputs if u['stage']=='relation' for c in u['output'].get('relations', [])]
    rows = {c['id']:c for c in original_observations+original_relations}
    history = [h for u in outputs for h in u['output'].get('history', [])]
    for h in history:
        if h['candidate_id'] in rows: rows[h['candidate_id']] = h['after']
    blocked_revisions = {h['candidate_id'] for u in run['analysis_units'] if u['status']=='succeeded' and not set(u.get('dependency_ids', [])) <= available for h in u.get('output', {}).get('history', [])}
    rows = {i:c for i,c in rows.items() if i not in blocked_revisions}
    observations = [c for c in rows.values() if 'classification' in c]
    relations = [c for c in rows.values() if 'negation' in c]
    candidates = observations + relations
    reviewed = {g['id'] for g in run.get('candidate_groups', []) if g['status']=='review_issues_generated'
                and any(u['id']=='critic:'+g['id'] for u in outputs)}
    processed = {g['id'] for g in run.get('frontier', []) if all(any(u['id']==stage+':'+g['id'] for u in outputs) for stage in ('concept','relation'))}
    required_pending = [g['id'] for g in run.get('frontier', []) if g['required'] and g['id'] not in processed]
    required_pending += [g['id'] for g in run.get('candidate_groups', []) if g['id'] not in reviewed]
    reviewed_candidates = {i for g in run.get('candidate_groups', []) if g['id'] in reviewed for i in g['primary_candidate_ids']}
    unreviewed_candidates = sorted(c['id'] for c in original_observations+original_relations if not c['validation'] and not c['outside_scope_reason'] and c['id'] not in reviewed_candidates)
    no_result = [dict(group_id=g['id'], empty_roles=[stage for stage in ('concept','relation')
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
    analyzed = concept_linked & relation_linked
    selected = {i for g in run.get('frontier', []) for i in g['block_ids']}
    unfulfilled = sorted({i for r in run['extra_requests'] for i in r['block_ids']} - provided)
    titles = [f['title'] for f in run['frozen_input']['files']]
    reference_gaps = [dict(file_id=p['file_id'], reference=ref, status='자료 필요: 선택 목록 표제에서 참조 대상 미확인')
                      for p in run.get('profiles', []) for ref in p['reference_expressions'] if not any(ref in title for title in titles)]
    run['result'] = dict(reference_gaps=reference_gaps, unfulfilled_read_requests=unfulfilled, payload_version='a2-analysis-v2', review_status='unreviewed',
        original_observations=original_observations, original_relations=original_relations, revision_history=history,
        revisions=[dict(unit_id=u['id'], **u['output']) for u in outputs if u['stage']=='revision'],
        revision_deferrals=[d for g in run.get('candidate_groups', []) for d in g.get('revision_deferrals', [])],
        observations=[c for c in observations if not c['outside_scope_reason']],
        relations=[c for c in relations if not c['outside_scope_reason']],
        outside_scope=[c for c in candidates if c['outside_scope_reason']],
        alignments=[a for u in outputs for a in u['output'].get('alignments', [])],
        taxonomy=[dict(unit_id=u['id'], **u['output']) for u in outputs if u['stage']=='builder'],
        critiques=[dict(unit_id=u['id'], **u['output']) for u in outputs if u['stage']=='critic'],
        coverage=coverage, gaps=gaps, failures=failures, mandatory_pending=required_pending,
        unavailable_block_ids=sorted({b['id'] for b in blocks}-available),
        structure_surveyed=len(blocks), raw_provided=len(provided), analysis_succeeded=len(analyzed),
        analysis_groups=len(run.get('frontier', [])), processed_analysis_groups=len(processed),
        candidate_groups=len(run.get('candidate_groups', [])), no_result_groups=no_result, unreviewed_candidate_ids=unreviewed_candidates,
        selected_analysis_block_ids=sorted(selected), not_selected_block_ids=sorted({b['id'] for b in blocks}-selected),
        concept_evidence_block_ids=sorted(concept_linked), relation_evidence_block_ids=sorted(relation_linked),
        evidence_linked_block_ids=sorted(concept_linked | relation_linked), both_roles_evidence_block_ids=sorted(analyzed),
        processed_without_linked_evidence_ids=sorted({i for g in run.get('frontier', []) if g['id'] in processed for i in g['block_ids']}-(concept_linked|relation_linked)),
        review_groups=len(reviewed), unvisited_block_ids=sorted({b['id'] for b in blocks}-provided),
        unanalysed_block_ids=sorted({b['id'] for b in blocks}-analyzed),
        incomplete_file_ids=[u['file_id'] for u in run['units'] if u['status']!='succeeded'],
        unprocessed_features=[dict(file_id=g['file_id'], features=g['features']) for g in run.get('frontier', [])
                              if not g.get('analysis_grounded') and g['features']])
    has_errors = any(u.get('tool_errors') for u in outputs) or any(g.get('error') for g in run.get('frontier', []) + run.get('candidate_groups', []))
    incomplete = bool(required_pending or unreviewed_candidates or no_result or run['result']['revision_deferrals'] or failures or has_errors or unfulfilled or run['result']['incomplete_file_ids'] or
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
            run.update(profiles=profiles, frontier=frontier, full_frontier=full_frontier, candidate_groups=[],

                scout_frontier=[{k:g[k] for k in ('id','file_id','priority','input_chars','reason')} for g in frontier],
                expected_analysis_calls=1+2*len(frontier), reserved_builder_critic_calls=2,
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
        for round_number in range(run['recipe']['budgets']['additional_rounds']+1):
            pending = [g for g in run['frontier'] if g['round']==round_number]
            pending.sort(key=lambda g: (g['priority'], not g.get('requested_by_scout', False)))
            for group in pending:
                if cancelled(service, run): return
                process_group(service, run, group, index, blocks, by_id, context_map)
                save(service, run)
            from .discovery_synthesis import synthesize
            synthesize(service, run, round_number, index, blocks, by_id, context_map)
            if round_number == run['recipe']['budgets']['additional_rounds'] or run.get('analysis_block_ids') is not None: break
            assigned = {i for g in run['frontier'] for i in g['block_ids']}
            for request in run['extra_requests']:
                ids = [i for i in request['block_ids'] if i not in assigned]
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

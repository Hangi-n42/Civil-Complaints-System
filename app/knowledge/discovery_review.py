"""Per-record Critic validity shared by completion, revision and A3 conversion."""
from collections import Counter
from copy import deepcopy
from uuid import uuid4

from pydantic import ValidationError

from . import discovery_models as models, discovery_profile as profile, discovery_segments as segments, discovery_design as design


def fingerprint(candidate):
    return profile.digest({k:v for k,v in candidate.items() if k not in {'origin_dependency_ids','analysis_group_id'}})


def with_selected_base_types(candidates, run):
    from .discovery_analysis import base_context
    selected = {c.get(field) for c in candidates.values() if 'negation' in c for field in ('subject','object')}
    return {**{c['id']:c for c in base_context(run) if c['id'] in selected}, **candidates}


def binding_fingerprints(candidate, candidates):
    if 'negation' not in candidate: return {}
    return {field:fingerprint(candidates[candidate[field]]) if candidates.get(candidate.get(field), {}).get('classification')=='type' and not any(candidates[candidate[field]].get(k) for k in ('validation','evidence_validation','outside_scope_reason','deprecated')) else None
            for field in ('subject','object') if candidate.get('source_relation') or candidates.get(candidate.get(field), {}).get('classification')=='type'}


def dependencies_current(review, identifier, candidates=None):
    contract = review.get('review_dependency_contract')
    if contract is None and 'binding_dependency_hashes' not in review: return True  # Stored legacy contract.
    if contract != 'selected-types-v1': return False
    recorded = review.get('binding_dependency_hashes', {}).get(identifier)
    if recorded is None or any(not h for h in recorded.values()): return False
    roles=review.get('role_source_hashes', {}).get(identifier, {})
    if any(not h for h in roles.values()): return False
    return candidates is None or identifier in candidates and recorded==binding_fingerprints(candidates[identifier],candidates) and roles==design.role_fingerprints(candidates[identifier],candidates)


def latest_by_candidate(critiques, candidates):
    hashes={i:fingerprint(c) for i,c in candidates.items()}
    latest = {i:review for review in critiques if review.get('review_component') not in {'proposition','binding'} for i,h in review.get('review_coverage', {}).get('candidate_hashes', {}).items()
              if i in hashes and h==hashes[i]}
    # An incomplete new review cannot fall back to an older supported judgment.
    return {i:r for i,r in latest.items() if dependencies_current(r,i,candidates)}


def valid_ids(review, candidates=None, latest=None):
    if review.get('review_component') in {'proposition','binding'}: return set()
    coverage = review.get('review_coverage')
    if coverage is None:
        if review.get('review_dependency_contract') or 'binding_dependency_hashes' in review: return set()
        # A representative view needs its own review; legacy raw judgments cannot cover it.
        if candidates and any(c.get('candidate_view_version') for c in candidates.values()): return set()
        return None  # Stored legacy reviews retain their original contract.
    valid = {i for i in coverage['valid_candidate_ids'] if dependencies_current(review,i,candidates)}
    if latest is not None: valid = {i for i in valid if latest.get(i) is review}
    if candidates is not None:
        valid = {i for i in valid if i in candidates and coverage['candidate_hashes'].get(i)==fingerprint(candidates[i])}
    return valid


def normalize(output, run, deps, by_id, supplied, context, normalize_hierarchy, validate_refs, require_issue_cause=False):
    checks_contract = require_issue_cause and run.get('recipe', {}).get('review_contract') == 'checks-v1'
    binding_reasons = checks_contract and run['recipe'].get('binding_reason_contract') == 'per-endpoint-v1'
    declared = set(context.get('review_target_ids', supplied))
    expected = {i:c for i,c in supplied.items() if i in declared and c.get('review_status')!='reviewed'}
    relations = {i for i,c in expected.items() if 'negation' in c}
    observations = {i for i,c in expected.items() if 'classification' in c} if 'review_target_ids' in context else set()
    hierarchies = {(h['child_ref'],h['parent_ref'],h['relation']):h['id']
                   for h in context.get('taxonomy', {}).get('hierarchies', [])}
    provided = segments.originals(context)
    pending, errors, issue_ids = set(), [], {}
    local_refs = [i.get('local_ref') for i in output['issues'] if isinstance(i,dict) and i.get('local_ref')]
    issue_counts = Counter(local_refs)

    def problem(section, index, raw, reason, targets):
        pending.update(set(targets) & expected.keys())
        errors.append(dict(section=section,index=index,record=deepcopy(raw),reason=reason,candidate_ids=sorted(targets)))

    for section, model in [('issues',models.Issue), ('relation_checks',models.RelationCheck), ('observation_checks',models.RelationCheck),
                           ('hierarchy_checks',models.Hierarchy), ('missing_meanings',models.MissingMeaning)]:
        records = output.get(section, [])
        def key(record):
            fields = ('child_ref','parent_ref','relation') if section=='hierarchy_checks' else ('candidate_ref',)
            values = tuple(record.get(f) if isinstance(record.get(f),str) else None for f in fields)
            return values if section=='hierarchy_checks' else values[0]
        counts = Counter(key(r) for r in records if isinstance(r,dict))
        accepted = []
        for index, raw in enumerate(records):
            target = key(raw) if isinstance(raw,dict) else None
            identifier = hierarchies.get(target) if section=='hierarchy_checks' else target
            targets = {identifier} if identifier in expected else set(expected) if section=='issues' and not identifier else set()
            try:
                if section=='issues' and require_issue_cause and isinstance(raw,dict) and 'cause' not in raw:
                    targets = {identifier} if identifier in expected else set()
                    raise ValueError('새 쟁점의 명시적 cause 누락; 기본 원인으로 복구하지 않음')
                if checks_contract and section=='issues' and isinstance(raw,dict) and identifier in relations | observations and raw.get('cause') in {'content_error','endpoint'}:
                    raise ValueError('새 계약의 내용/연결 쟁점은 세부 판정에서만 도출')
                parsed = raw
                if checks_contract and section in models.SEMANTIC_FIELDS and isinstance(raw,dict):
                    checks = raw.get('semantic_checks', {})
                    if set(checks) != set(models.SEMANTIC_FIELDS[section]):
                        raise ValueError('필수 의미 항목 판정 누락')
                    judgment = 'refuted' if 'refuted' in checks.values() else 'unknown' if 'unknown' in checks.values() else 'supported'
                    parsed = dict(raw,judgment=judgment)
                item = model.model_validate(parsed).model_dump()
                segments.restore(item, by_id, provided)
                validate_refs(item)
                if section in {'relation_checks','observation_checks','hierarchy_checks'} and counts[target]!=1:
                    raise ValueError('중복 검토 대상; 어느 판정도 선택하지 않음')
                if section=='issues':
                    if issue_counts[item['local_ref']]!=1: raise ValueError('응답 내부 쟁점 local_ref 중복')
                    if item['candidate_ref'] and item['candidate_ref'] not in supplied:
                        raise ValueError('검토 대상 후보 참조 불일치')
                    if item['target_ref'] and item['target_ref'] not in supplied:
                        raise ValueError('대응 정의가 실제 제공 범위 밖')
                    if item['cause'] in {'evidence_error','endpoint','alignment'} and not item['candidate_ref']:
                        raise ValueError('원인별 보완은 실제 대상 후보 필요')
                    if item['cause'] in {'source_absent','budget_exhausted'} and not item['defer_reason']:
                        raise ValueError('자료 미제공/예산 종료의 구체 보류 사유 필요')
                    if item['cause']=='budget_exhausted':
                        budget, metrics = run['recipe']['budgets'], run['metrics']
                        if (metrics['llm_calls']<budget['model_calls'] and metrics['model_total_s']+metrics.get('interrupted_time_reserve_s',0)<budget['model_seconds']
                                and (not item['candidate_ref'] or budget['revisions'])):
                            raise ValueError('서버 잔여량으로 확인되지 않은 예산 종료 판단')
                    if not item['evidence_ids'] and not item['counter_evidence_ids'] and not item['defer_reason'].strip():
                        raise ValueError('근거 없는 쟁점에는 명시적 보류 사유 필요')
                    item['id']='di_'+uuid4().hex
                    issue_ids[item['local_ref']]=item['id']
                elif section in {'relation_checks','observation_checks'}:
                    if item['candidate_ref'] not in (relations if section=='relation_checks' else observations):
                        raise ValueError('이번 주검토 대상 밖 ID')
                    if item['judgment']!='unknown' and not (item['quote'] or item.get('evidence_refs')):
                        raise ValueError('후보 판단에는 원문 인용 필요')
                    if item['quote'] and not item.get('source_refs'):
                        refs, problems = segments.references(dict(evidence_ids=[item['evidence_id']],
                            source_quotes=[dict(evidence_id=item['evidence_id'],quote=item['quote'])]), by_id, provided)
                        if problems: raise ValueError('; '.join(problems))
                        item['evidence_refs']=refs
                    if section=='relation_checks' and 'review_scope' in context and item['judgment']=='supported':
                        candidate=supplied[item['candidate_ref']]
                        if set(item['semantic_checks'])!={'subject','object','conditions','statement_type'} or any(v!='supported' for v in item['semantic_checks'].values()):
                            raise ValueError('지지 판정에는 원문 끝점·조건/예외·진술 종류의 각각의 대조 필요')
                        for field in ('subject','object'):
                            label=candidate.get('endpoint_labels', {}).get(field)
                            if not label: raise ValueError('독립 대조할 원문 끝점 표현 미확인: '+field)
                            if context.get('review_component')!='proposition' and candidate.get('source_relation') and supplied.get(candidate[field], {}).get('classification')!='type':
                                item.setdefault('binding_validation', []).append('연결 유형 정의가 이번 검수에 제공되지 않음: '+field)
                    if context.get('review_component')=='proposition' and (item['binding_checks'] or item['binding_reasons']):
                        raise ValueError('원명제 전용 응답에 유형 연결 판정을 포함할 수 없음')
                    if checks_contract and section=='relation_checks' and context.get('review_component')!='proposition':
                        candidate=supplied[item['candidate_ref']]
                        if candidate.get('source_relation'):
                            if set(item['binding_checks']) != {'subject','object'}:
                                raise ValueError('유형 연결의 주체/목적어 판정 누락')
                            if binding_reasons and (set(item['binding_reasons']) != {'subject','object'} or
                                    any(not reason.strip() or len(reason)>400 for reason in item['binding_reasons'].values())):
                                raise ValueError('유형 연결의 끝점별 구체 사유 누락 또는 길이 초과')
                            for field,judgment in item['binding_checks'].items():
                                if supplied.get(candidate[field], {}).get('classification')!='type':
                                    raise ValueError('연결 유형 정의가 이번 검수에 제공되지 않음: '+field)
                                if judgment!='supported':
                                    reason=item['binding_reasons'][field] if binding_reasons else item['reason']
                                    item.setdefault('binding_validation', []).append('유형 연결 '+field+' '+judgment+': '+reason)
                        elif item['binding_checks']:
                            raise ValueError('유형 연결 없는 원명제에 binding 판정을 추가할 수 없음')
                    if binding_reasons and item['binding_reasons'] and (section=='observation_checks' or not supplied[item['candidate_ref']].get('source_relation')):
                        raise ValueError('유형 연결 없는 후보에 연결 사유를 추가할 수 없음')
                    if section=='observation_checks' and require_issue_cause and item['judgment']=='supported':
                        # Fresh generation only; stored Critic records keep their original contract.
                        if set(item['semantic_checks'])!=set(models.SEMANTIC_FIELDS[section]) or any(v!='supported' for v in item['semantic_checks'].values()):
                            raise ValueError('지지 판정에는 분류·정의 전체·조건·예외의 각각의 대조 필요')
                elif section=='hierarchy_checks':
                    if target not in hierarchies: raise ValueError('제안하지 않은 계층 검토')
                    # The existing Builder validation checks kind/direction/evidence contracts.
                    checked=normalize_hierarchy({'hierarchies':[item]}, 'builder', run, deps, by_id, supplied)['hierarchies'][0]
                    if checked['validation']: raise ValueError('; '.join(checked['validation']))
                    item=checked
                    item['id']=identifier
                else:
                    if context.get('review_scope', {}).get('missing_meanings_allowed') is False:
                        raise ValueError('양쪽 종류 비교 미실시 범위에서 누락 의미를 요청할 수 없음')
                    refs, problems = segments.references(item, by_id, provided)
                    if not item['source_quotes'] and not item['source_refs']: problems.append('누락 복구의 정확한 원문 구절 필요')
                    if not item['cq_ids'] and not item['scope_item_ids'] or item['outside_scope_reason']: problems.append('복구의 허용 질문/범위 연결 필요')
                    if not set(item['cq_ids']) <= {q['id'] for q in run['cqs']} or not set(item['scope_item_ids']) <= {q['id'] for q in run['scope_items']}: problems.append('복구의 허용 질문/범위 밖 연결')
                    if problems: raise ValueError('; '.join(problems))
                    owned=context.get('review_scope', {}).get('primary_source_spans')
                    if owned is not None:
                        if any(not any(s['block_id']==r['block_id'] and s['span'][0]<=r['span'][0]<r['span'][1]<=s['span'][1] for s in owned) for r in refs):
                            raise ValueError('누락 재추출 인용이 이번 주검토 소유 구간 밖')
                        item['primary_source_spans']=deepcopy(owned)
                    item.update(evidence_refs=refs,validation=[])
                    if 'review_scope' in context:
                        if not set(item['compared_candidate_ids']) <= supplied.keys(): raise ValueError('미제공 후보를 의미 대조했다고 주장할 수 없음')
                        if not item['comparison_reason'].strip(): raise ValueError('미표현 의미와 실제 비교 범위의 사유 필요')
                        for marker in ('classification','negation'):
                            compared=supplied if context.get('review_focus') else expected
                            primary={i for i,c in compared.items() if marker in c and
                                (set(item['cq_ids']) & set(c.get('cq_ids', [])) or set(item['scope_item_ids']) & set(c.get('scope_item_ids', [])))}
                            if primary and not primary & set(item['compared_candidate_ids']):
                                raise ValueError('주검토 관측/관계의 의미 대조 미확인; 누락 재추출 보류')
                        item['assessment_scope']='provided_only'
                accepted.append(item)
            except (ValidationError, ValueError, KeyError, TypeError) as exc:
                problem(section,index,raw,str(exc),targets)
        output[section]=accepted
        if section in {'relation_checks','observation_checks','hierarchy_checks'}:
            required = relations if section=='relation_checks' else observations if section=='observation_checks' else set(hierarchies.values())
            covered = {c['id'] if section=='hierarchy_checks' else c['candidate_ref'] for c in accepted}
            for identifier in sorted(required-covered-pending):
                problem(section,None,None,'필수 후보 검토 누락',{identifier})
    supported = {i['candidate_ref'] for field in ('relation_checks','observation_checks')
                 for i in output[field] if i['judgment']=='supported'}
    for index, issue in enumerate(output['issues']):
        if issue['cause']=='content_error' and issue['candidate_ref'] in supported:
            problem('issues',index,issue,'동일 후보의 지지 판정과 내용 오류 쟁점 충돌',{issue['candidate_ref']})
    actions=[]
    previous={i['id'] for u in run.get('analysis_units', []) if u['status']=='succeeded' for i in u.get('output', {}).get('issues', [])}
    for index, action in enumerate(output['actions']):
        if action['action']=='request_evidence':
            identifier=issue_ids.get(action['issue_id'],action['issue_id'])
            if identifier not in set(issue_ids.values()) | previous:
                problem('actions',index,action,'유효한 쟁점 없는 근거 요청',set())
                continue
            action['issue_id']=identifier
        actions.append(action)
    # Conflicting/invalid judgments never drive a revision or recovery through another record.
    output['issues']=[i for i in output['issues'] if i['candidate_ref'] not in pending and not (pending and not i['candidate_ref'])]
    output['relation_checks']=[i for i in output['relation_checks'] if i['candidate_ref'] not in pending]
    output['observation_checks']=[i for i in output['observation_checks'] if i['candidate_ref'] not in pending]
    output['hierarchy_checks']=[i for i in output['hierarchy_checks'] if i['id'] not in pending]
    if checks_contract:
        for field in ('relation_checks','observation_checks'):
            for check in output[field]:
                causes = (['content_error'] if check['judgment']=='refuted' else [])
                if 'refuted' in check['binding_checks'].values(): causes.append('endpoint')
                for cause in causes:
                    if any(i['candidate_ref']==check['candidate_ref'] and i['cause']==cause for i in output['issues']): continue
                    reason='; '.join(k+': '+check['binding_reasons'][k] for k,v in check['binding_checks'].items() if v=='refuted') if binding_reasons and cause=='endpoint' else check['reason']
                    output['issues'].append(dict(id='di_'+uuid4().hex,candidate_ref=check['candidate_ref'],
                        cause=cause,target_ref='',reason=reason,evidence_ids=[r['evidence_id'] for r in check.get('evidence_refs', [])],
                        evidence_refs=deepcopy(check.get('evidence_refs', [])),counter_evidence_ids=[],defer_reason='',derived_from=field))
        output['needs_revision']=any(i['cause'] in {'content_error','evidence_error','endpoint'} for i in output['issues'])
    valid_issue_ids={i['id'] for i in output['issues']} | previous
    output['actions']=[a for a in actions if a['action']!='request_evidence' or a['issue_id'] in valid_issue_ids]
    output['record_errors']=errors
    output['review_dependency_contract']='selected-types-v1'
    output['binding_dependency_hashes']={i:binding_fingerprints(c,supplied) for i,c in expected.items()}
    output['role_source_hashes']={i:design.role_fingerprints(c,supplied) for i,c in expected.items()}
    output['review_coverage']=dict(expected_candidate_ids=sorted(expected),valid_candidate_ids=sorted(expected.keys()-pending),
        pending_candidate_ids=sorted(pending),candidate_hashes={i:fingerprint(c) for i,c in expected.items()})
    if 'review_target_ids' in context:
        judgments = {i['candidate_ref']:i['judgment'] for field in ('observation_checks','relation_checks') for i in output[field]}
        judgments.update({h['id']:'unknown' if any(h[d]['judgment']=='unknown' for d in ('a_to_b','b_to_a')) else h['a_to_b']['judgment'] for h in output['hierarchy_checks']})
        output['review_outcomes']={j:sorted(i for i,v in judgments.items() if v==j) for j in ('supported','refuted','unknown')}
    if 'review_scope' in context:
        output['review_scope']=dict(context['review_scope'],provided_source_refs=[b['source_ref'] for b in provided if b.get('source_ref')])
    return output


def normalize_binding(output, supplied, context, by_id):
    identifier=context['review_target_ids'][0]
    if set(output)!={'candidate_ref','binding_checks','binding_reasons','source_refs'} or output['candidate_ref']!=identifier:
        raise ValueError('연결 전용 응답의 대상/필드 불일치')
    if set(output['binding_checks'])!={'subject','object'} or set(output['binding_reasons'])!={'subject','object'}:
        raise ValueError('연결 전용 응답의 끝점 누락')
    if any(v not in {'supported','refuted','unknown'} for v in output['binding_checks'].values()):
        raise ValueError('연결 판정값 오류')
    if any(not isinstance(v,str) or not v.strip() or len(v)>400 for v in output['binding_reasons'].values()):
        raise ValueError('연결 사유 누락 또는 길이 초과')
    if not isinstance(output['source_refs'],list) or not output['source_refs']:
        raise ValueError('연결 판단의 제공 원문 근거 누락')
    dependencies=binding_fingerprints(supplied[identifier],supplied)
    if set(dependencies)!={'subject','object'} or not all(dependencies.values()):
        raise ValueError('선택 유형 정의 부재')
    segments.restore(output,by_id,segments.originals(context))
    issues=[]
    if 'refuted' in output['binding_checks'].values():
        issues.append(dict(id='di_'+uuid4().hex,candidate_ref=identifier,cause='endpoint',target_ref='',
            reason='; '.join(k+': '+output['binding_reasons'][k] for k,v in output['binding_checks'].items() if v=='refuted'),
            evidence_ids=list(output['evidence_ids']),evidence_refs=deepcopy(output['evidence_refs']),counter_evidence_ids=[],defer_reason='',derived_from='binding_check'))
    return dict(binding_check=output,issues=issues,actions=[],needs_revision=bool(issues),record_errors=[],
        review_dependency_contract='selected-types-v1',binding_dependency_hashes={identifier:dependencies},
        role_source_hashes={identifier:design.role_fingerprints(supplied[identifier],supplied)},
        review_coverage=dict(expected_candidate_ids=[identifier],valid_candidate_ids=[identifier],pending_candidate_ids=[],
            candidate_hashes={identifier:fingerprint(supplied[identifier])}))


def complete_reviews(outputs):
    """Read projection only: combine real calls, never persist a synthetic success unit."""
    result=[]
    for original in outputs:
        component=original.get('review_component')
        if component=='binding': continue
        if component!='proposition':
            result.append(original);continue
        review=deepcopy(original)
        review.update(review_component='complete',component_unit_ids=[original['unit_id']])
        coverage=review['review_coverage'];pending=set(coverage['pending_candidate_ids'])
        for identifier in original['binding_target_ids']:
            matches=[b for b in outputs if b.get('review_component')=='binding'
                and b.get('review_bundle_id')==original['review_bundle_id']
                and b.get('review_scope_hash')==original['review_scope_hash']
                and b.get('binding_target_ids')==original['binding_target_ids']
                and b.get('binding_check', {}).get('candidate_ref')==identifier
                and identifier in b['review_coverage']['valid_candidate_ids']
                and dependencies_current(b,identifier)
                and b['review_coverage']['candidate_hashes'].get(identifier)==coverage['candidate_hashes'].get(identifier)
                and b.get('binding_dependency_hashes', {}).get(identifier)==original.get('binding_dependency_hashes', {}).get(identifier)
                and b.get('role_source_hashes', {}).get(identifier,{})==original.get('role_source_hashes', {}).get(identifier,{})]
            check=next((c for c in review['relation_checks'] if c['candidate_ref']==identifier),None)
            if len(matches)!=1 or check is None or identifier not in coverage['valid_candidate_ids']:
                pending.add(identifier)
                review.setdefault('record_errors', []).append(dict(candidate_ids=[identifier],reason='동일 묶음·원문 범위·현재 관계/선택 유형의 필수 부분 검수 미완료'))
                continue
            binding=matches[0];item=binding['binding_check']
            review['component_unit_ids'].append(binding['unit_id'])
            check.update(binding_checks=deepcopy(item['binding_checks']),binding_reasons=deepcopy(item['binding_reasons']),
                binding_evidence_refs=deepcopy(item['evidence_refs']))
            check['binding_validation']=['유형 연결 '+k+' '+v+': '+item['binding_reasons'][k] for k,v in item['binding_checks'].items() if v!='supported']
            review['issues'].extend(deepcopy(binding['issues']))
        coverage['pending_candidate_ids']=sorted(pending)
        coverage['valid_candidate_ids']=sorted(set(coverage['valid_candidate_ids'])-pending)
        review['review_outcomes']={k:[i for i in ids if i not in pending] for k,ids in review.get('review_outcomes', {}).items()}
        review['relation_checks']=[c for c in review['relation_checks'] if c['candidate_ref'] not in pending]
        review['issues']=[i for i in review['issues'] if i.get('candidate_ref') not in pending]
        review['needs_revision']=any(i.get('cause') in {'content_error','evidence_error','endpoint'} for i in review['issues'])
        result.append(review)
    return result

"""Saved CQ/scope judgments through the existing serial call and recovery contracts."""
from copy import deepcopy

from . import discovery_profile as profile, discovery_review as reviews, discovery_scope as scope
from . import discovery_segments as segments, discovery_claims as claims


def fingerprint(context, supplied):
    return profile.digest([context['requirement'],{i:reviews.fingerprint(c) for i,c in supplied.items()},
        [(v['ref'],v.get('span',[0,len(v['text'])]),v['text'],v.get('analysis_target'),v.get('context_only')) for v in segments.originals(context)],
        context.get('context_gaps',[]),context.get('requirement_scope',{}),context.get('recovery_targets',[])])


def packet(run, result, kind, requirement, by_id, context_map, groups=None):
    from . import discovery_analysis as a2, discovery_synthesis as synthesis
    field='cq_ids' if kind=='cq' else 'scope_item_ids'
    all_rows={c['id']:c for c in result.get('observations',[])+result.get('relations',[])}
    all_rows.update({h['id']:h for t in result.get('taxonomy',[]) for h in t.get('hierarchies',[])})
    all_rows.update({h['candidate_id']:a2.identities.history_view(run,h) for h in result.get('revision_history',[])})
    all_rows=reviews.with_selected_base_types(all_rows,run)
    selected={i for i,c in all_rows.items() if requirement['id'] in c.get(field,[])}
    while True:
        linked={i for i,c in all_rows.items() if c.get('child_ref') in selected}
        linked.update(c[k] for i,c in all_rows.items() if i in selected for k in ('child_ref','parent_ref','subject','object') if c.get(k) in all_rows)
        if linked<=selected: break
        selected |= linked
    if groups is not None:
        blocks={i for g in groups for i in g['block_ids']}
        selected={i for i in selected if blocks & set(all_rows[i].get('evidence_ids',[]))}
        pending=list(selected)
        while pending:
            c=all_rows[pending.pop()]
            linked={c[k] for k in ('child_ref','parent_ref','subject','object') if c.get(k) in all_rows}
            linked.update(i for i,h in all_rows.items() if h.get('child_ref')==c['id'])
            pending.extend(linked-selected);selected |= linked
    rows=[all_rows[i] for i in sorted(selected) if not all_rows[i].get('outside_scope_reason')]
    context,deps,supplied=synthesis.context_for(rows,by_id,context_map)
    # Requirements examine the selected analysis scope, including spans with no candidates.
    raw=[]
    for group in run.get('frontier',[]) if groups is None else groups:
        raw.extend(segments.packet(group,by_id,context_map,a2.packet))
    context['blocks']=list({(v['ref'],tuple(v.get('span',[0,len(v['text'])])),v.get('analysis_target'),v.get('context_only')):v for v in raw}.values())
    context['requirement_scope']=dict(complete_input=groups is None,omitted_group_ids=[] if groups is None else [g['id'] for g in run['frontier'] if g not in groups])
    context['requirement']=dict(kind=kind,**requirement)
    context['selected_hierarchies']=[c for c in rows if 'child_ref' in c]
    context['recovery_targets']=[{k:deepcopy(r.get(k)) for k in ('id','meanings','evidence_refs','target')}
        for r in run.get('recovery_requests',[]) if (r.get('requirement_key')==kind+':'+requirement['id'] or any(requirement['id'] in m.get(field,[]) for m in r.get('meanings',[]))) and not r.get('validation')]
    if groups is not None:
        def owned(request):
            target=request['target']
            if isinstance(target,dict): return target.get('candidate_id') in supplied
            return any(v['ref']==block and not v.get('context_only') and
                v.get('span',[0,len(v['text'])])[0]<span[1] and span[0]<v.get('span',[0,len(v['text'])])[1]
                for block,span in target for v in raw)
        context['recovery_targets']=[r for r in context['recovery_targets'] if owned(r)]
    context,deps=scope.source_context(context,sorted(set(deps)|{v['ref'] for v in raw}),by_id)
    return context,deps,supplied


def packets(run,result,kind,requirement,by_id,context_map):
    from .discovery_synthesis import fits
    whole=packet(run,result,kind,requirement,by_id,context_map)
    if fits(run,'requirements',*whole): return [whole]
    # Reuse the existing semantic working units; partial views cannot certify the full CQ.
    parts=[];seen=set()
    for group in run.get('frontier',[]):
        key=profile.digest([group['block_ids'],group.get('segments',[])])
        if key in seen: continue
        seen.add(key)
        parts.append(packet(run,result,kind,requirement,by_id,context_map,[group]))
    return parts or [whole]


def normalize(output, context, supplied, by_id):
    if output['requirement_id']!=context['requirement']['id']: raise ValueError('요구 검수 대상 불일치')
    expected={r['id'] for r in context['recovery_targets']};answered=[]
    for item in output['meanings']:
        scope.locations(item,supplied)
        if item['judgment']=='supported' and item['cause']!='fulfilled': raise ValueError('충족 판정과 미완료 원인 충돌')
        if item['judgment']!='supported' and item['cause']=='fulfilled': raise ValueError('미확인/반박을 충족으로 표시할 수 없음')
        if item['cause']=='endpoint' and (not item.get('endpoint_fields') or item['candidate_ref'] not in supplied or 'negation' not in supplied[item['candidate_ref']]):
            raise ValueError('끝점 교정은 현재 관계 후보 필요')
        if item['cause'] in {'endpoint','extraction_missing'} and item['judgment']!='refuted':
            raise ValueError('자동 복구는 원문에 따른 명시 반박 필요')
        if item['cause']=='extraction_missing' and not item.get('evidence_refs'): raise ValueError('누락 생성은 실제 원문 필요')
        answered.extend(item['recovery_ids'])
    if set(answered)!=expected or len(answered)!=len(expected): raise ValueError('기존 누락 의미의 현재 충족 대조 누락/중복')
    output['judgment']=claims.aggregate(i['judgment'] for i in output['meanings'])
    output['assessment_scope']=deepcopy(context['requirement_scope'])
    if not context['requirement_scope']['complete_input']:
        output['judgment']=claims.aggregate([output['judgment'],'unknown'])
        output['reason']+='; 입력 한도에 따른 부분 검수, 요구 전체의 결합 충족 미확인'
    output['assessment_fingerprint']=fingerprint(context,supplied)
    output['requirement_kind']=context['requirement']['kind']
    output['resolved_recovery_ids']=[i for m in output['meanings'] if m['judgment']=='supported' for i in m['recovery_ids']]
    return output


def saved(run, result, by_id, available):
    context_map=profile.contexts(list(by_id.values()))
    assessments=[]
    for kind,items in [('cq',run['cqs']),('scope',run['scope_items'])]:
        for q in items:
            parts=[]
            for context,deps,supplied in packets(run,result,kind,q,by_id,context_map):
                stamp=fingerprint(context,supplied)
                matches=[u for u in run['analysis_units'] if u['stage']=='requirements' and u['status']=='succeeded'
                    and u['output'].get('assessment_fingerprint')==stamp and set(u['dependency_ids'])<=available]
                parts.append(dict(unit_id=matches[-1]['id'],**deepcopy(matches[-1]['output'])) if matches else
                    dict(judgment='unknown',meanings=[],reason='현재 요구·후보·근거의 유효한 충족 검수 없음',resolved_recovery_ids=[],
                        pending_recovery_ids=[r['id'] for r in context['recovery_targets']]))
            resolved={i for p in parts for i in p['resolved_recovery_ids']}
            unresolved={i for p in parts for m in p['meanings'] if m['judgment']!='supported' for i in m['recovery_ids']}
            unresolved.update(i for p in parts for i in p.get('pending_recovery_ids',[]))
            assessments.append(dict(requirement_id=q['id'],requirement_kind=kind,judgment=claims.aggregate(p['judgment'] for p in parts),
                meanings=[m for p in parts for m in p['meanings']],reason='; '.join(dict.fromkeys(p['reason'] for p in parts)),
                resolved_recovery_ids=sorted(resolved-unresolved),parts=parts))
    return assessments


def assess(service,run,blocks,by_id,context_map, *, rechecked=False):
    from . import discovery_analysis as a2
    corrected=False
    original_targets=profile.digest(run.get('recovery_requests',[]))
    snapshot=deepcopy(run);a2.finish(snapshot,blocks,a2.allowed_ids(service,blocks))
    for kind,items in [('cq',run['cqs']),('scope',run['scope_items'])]:
        for q in items:
            if a2.cancelled(service,run): return
            for context,deps,supplied in packets(run,snapshot['result'],kind,q,by_id,context_map):
                stamp=fingerprint(context,supplied);key=kind+':'+q['id']+':'+stamp[:20]
                existing=next((u for u in run['analysis_units'] if u['id']=='requirements:'+key),None)
                if existing and (existing.get('attempts') or existing.get('status')=='failed'): continue
                output=a2.call(service,run,'requirements',key,context,deps,by_id,supplied)
                if output is None: continue
                for item in output['meanings']:
                    if item['cause'] not in {'extraction_missing','endpoint'}: continue
                    owners=[g['id'] for g in run['frontier'] if any(e['block_id'] in g['block_ids'] for e in item.get('evidence_refs',[]))]
                    group=dict(id='requirement:'+kind+':'+q['id'],analysis_group_ids=owners,candidates=list(supplied.values()),
                        primary_candidate_ids=list(supplied))
                    previous={r['id'] for r in run.get('recovery_requests',[])}
                    if item['cause']=='extraction_missing':
                        need=dict(item,cq_ids=[q['id']] if kind=='cq' else [],scope_item_ids=[q['id']] if kind=='scope' else [],
                            validation=[],outside_scope_reason='',compared_candidate_ids=list(supplied),comparison_reason=item['reason'])
                        a2.queue_recovery(run,dict(missing_meanings=[need]),group,by_id)
                    else:
                        a2.queue_recovery(run,dict(issues=[dict(item,reason=item['reason'],cause='endpoint')]),group,by_id)
                        from . import discovery_synthesis as synthesis
                        cid=item['candidate_ref']
                        owner=next((g for g in run['candidate_groups'] if cid in g['primary_candidate_ids'] and not g.get('correction_plan')),None)
                        current=reviews.with_selected_base_types(dict(supplied),run)
                        prior=reviews.latest_by_candidate(snapshot['result']['critiques'],current).get(cid)
                        proof=next((c for c in (prior or {}).get('relation_checks',[]) if c['candidate_ref']==cid and c['judgment']=='supported'),None)
                        if owner and proof and cid in (reviews.valid_ids(prior,current) or set()):
                            before=len([u for u in run['analysis_units'] if u['stage']=='builder' and u.get('parent_group_id')])
                            # A new requirement judgment is repair input, never a rewritten Critic verdict.
                            check=dict(deepcopy(item),repair_source='requirements',
                                assessment_unit_id='requirements:'+key,assessment_fingerprint=output['assessment_fingerprint'],
                                binding_checks={field:'refuted' for field in item['endpoint_fields']},
                                binding_reasons={field:item['reason'] for field in item['endpoint_fields']})
                            repair=dict(issues=[],relation_checks=[],observation_checks=[],requirement_binding_checks=[check],
                                review_coverage=deepcopy(prior['review_coverage']),
                                review_dependency_contract=prior.get('review_dependency_contract'),
                                binding_dependency_hashes=deepcopy(prior.get('binding_dependency_hashes',{})),
                                role_source_hashes=deepcopy(prior.get('role_source_hashes',{})))
                            taxonomy=next(u['output'] for u in run['analysis_units'] if u['id']=='builder:'+owner['id'])
                            if owner.get('correction_plan')==[]: owner.pop('correction_plan')
                            synthesis.revise(service,run,owner,repair,taxonomy,by_id,context_map)
                            corrected |= len([u for u in run['analysis_units'] if u['stage']=='builder' and u.get('parent_group_id')])>before

                    for r in run.get('recovery_requests',[]):
                        if r['id'] not in previous: r['requirement_key']=kind+':'+q['id']
                a2.save(service,run)
    if not rechecked and (corrected or original_targets!=profile.digest(run.get('recovery_requests',[]))):
        assess(service,run,blocks,by_id,context_map,rechecked=True)

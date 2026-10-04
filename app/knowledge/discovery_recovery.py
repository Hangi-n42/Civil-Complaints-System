"""Current blockers over preserved failures and source-owned recovery receipts."""
from . import discovery_review as reviews, discovery_candidates as identities, discovery_design as design


def resolve_endpoint_reviews(run, current, latest, available):
    """Project a matching completed repair onto its separate endpoint review request."""
    def signature(request):
        target=request.get('target',{})
        if not isinstance(target,dict): return None
        endpoints=set(target.get('endpoints',[]))
        if not endpoints or not endpoints<={'subject','object'} or target.get('candidate_id')!=request.get('candidate_ref'): return None
        meanings=tuple(sorted((m.get('meaning',''),m.get('target_ref',''),m.get('defer_reason','')) for m in request.get('meanings',[])))
        if not meanings: return None
        need=tuple(request.get(k,'') for k in ('meaning','target_ref','defer_reason'))
        return request.get('critic_group_id'),request.get('candidate_ref'),tuple(sorted(endpoints)),need,meanings
    units={u['id']:u for u in run['analysis_units']}
    companions=[r for r in run.get('recovery_requests',[]) if r['cause']=='endpoint' and r['role']=='builder'
        and not r.get('validation') and r.get('proposal_review_status')=='current_critic_supported' and r.get('semantic_status')=='supported']
    for request in run.get('recovery_requests',[]):
        if request['cause']!='endpoint' or request['role']!='review': continue
        request.pop('current_resolution',None)
        key=signature(request)
        if request.get('validation') or key is None: continue
        matches=[r for r in companions if signature(r)==key]
        if len(matches)!=1: continue
        companion=matches[0];identifier=request['candidate_ref'];candidate=current.get(identifier,{})
        review=latest.get(identifier,{})
        if identifier not in (reviews.valid_ids(review,current) or set()) or not candidate.get('source_relation') or candidate.get('unresolved_endpoints'): continue
        checks=[c for c in review.get('relation_checks',[]) if c['candidate_ref']==identifier]
        if len(checks)!=1 or checks[0]['judgment']!='supported' or checks[0].get('binding_checks')!={'subject':'supported','object':'supported'}: continue
        unit=units.get(companion.get('unit_id'),{})
        if unit.get('stage')!='builder' or unit.get('status')!='succeeded' or unit.get('parent_group_id')!=request['critic_group_id'] or not set(unit.get('dependency_ids',[]))<=available: continue
        history=[h for h in unit['output'].get('history',[]) if h['candidate_id']==identifier]
        owners=[c for g in run.get('candidate_groups',[]) if g['id']==request['critic_group_id']
            for c in g.get('candidates',[])+g.get('design_candidates',[]) if c['id']==identifier]
        if len(history)!=1 or len(owners)!=1: continue
        record=history[0]
        if reviews.fingerprint(owners[0])!=reviews.fingerprint(record['before']): continue
        if set(record['before'].get('unresolved_endpoints',[]))!=set(request['target']['endpoints']): continue
        if reviews.fingerprint(identities.history_view(run,record))!=reviews.fingerprint(candidate): continue
        source=design.source_projection(owners[0])
        if not source.get('evidence_refs') or any(design.source_projection(c)!=source for c in (record['before'],record['after'],candidate)): continue
        review_units=review.get('component_unit_ids') or [review.get('unit_id')]
        if not review_units or any(units.get(uid,{}).get('status')!='succeeded' or not set(units[uid].get('dependency_ids',[]))<=available for uid in review_units): continue
        request.update(semantic_status='supported',proposal_review_status='current_critic_supported',current_resolution=dict(
            companion_request_id=companion['id'],builder_unit_id=unit['id'],review_unit_ids=review_units))


def active_blockers(run,current,latest,available):
    result=run['result'];requests=run.get('recovery_requests',[])
    units={u['id']:u for u in run['analysis_units']}
    resolved={r['id'] for r in requests if r.get('semantic_status')=='supported' and r.get('proposal_ids') and
        r.get('proposal_review_status')=='current_requirement_supported' and not r.get('unattempted_meanings')}
    def owned_done(uid,trigger=None):
        owned=[r for r in requests if r.get('original_unit_id')==uid and (trigger is None or r.get('trigger')==trigger)]
        return bool(owned) and all(r['id'] in resolved for r in owned)
    error_done={r['original_error_id'] for r in requests if r['id'] in resolved and r.get('original_error_id')}
    assessments={(a['requirement_kind'],a['requirement_id']):a for a in result.get('requirement_assessments',[])}
    histories={h['candidate_id'] for h in result.get('revision_history',[])}
    def corrected(identifier):
        candidate=current.get(identifier,{});review=latest.get(identifier)
        keys=[('cq',i) for i in candidate.get('cq_ids',[])]+[('scope',i) for i in candidate.get('scope_item_ids',[])]
        return identifier in histories and review and identifier in (reviews.valid_ids(review,current) or set()) and keys and all(
            assessments.get(k,{}).get('judgment')=='supported' for k in keys) and any(
            c['candidate_ref']==identifier and c['judgment']=='supported' and not c.get('binding_validation')
            for f in ('observation_checks','relation_checks') for c in review.get(f,[])) and not candidate.get('unresolved_endpoints')
    errors=[];binding=[];tools=[]
    for unit in units.values():
        output=unit.get('output') or {}
        row_errors=output.get('record_errors',[])
        for error in row_errors:
            if error.get('id') in error_done: continue
            if unit['stage']=='critic' and error.get('candidate_ids') and all(corrected(i) for i in error['candidate_ids']): continue
            errors.append({**error,'unit_id':unit['id']})
        binding.extend(dict(unit_id=unit['id'],**e) for e in output.get('binding_errors',[])
            if not e.get('candidate_ids') or not all(corrected(i) for i in e['candidate_ids']))
        tools.extend(dict(unit_id=unit['id'],error=e) for e in unit.get('tool_errors',[]))
    def role_done(group,role):
        uid=role+':'+group['id'];unit=units.get(uid,{})
        if not set(unit.get('dependency_ids',[]))<=available: return False
        if unit.get('status')!='succeeded':
            # Only a recovery explicitly linked to this whole failure can supersede it.
            return owned_done(uid,'unit_failure')
        if any(e.get('unit_id')==uid for e in errors): return False
        field='observations' if role=='concept' else 'relations'
        rows=unit['output'].get(field,[])
        return any(not c.get('validation') and not c.get('outside_scope_reason') for c in rows) or owned_done(uid)
    groups={g['id']:g for g in run.get('frontier',[])}
    done=set()
    for identifier,g in groups.items():
        if not all(role_done(g,role) for role in g.get('roles',['concept','relation'])): continue
        if g.get('capacity_pending') and not all(owned_done(role+':'+identifier,'output_capacity') for role in g.get('roles',['concept','relation'])
            if g.get('capacity',{}).get('roles',{}).get(role,{}).get('output_count')==g.get('capacity',{}).get('roles',{}).get(role,{}).get('limit')): continue
        if any('번호 목록' in reason for reason in g.get('capacity_pending',[])): continue
        done.add(identifier)
    for g in run.get('candidate_groups',[]):
        ids=g.get('primary_candidate_ids',[])+g.get('design_candidate_ids',[])
        if ids and any(corrected(i) for i in ids) and all(i in latest and i in (reviews.valid_ids(latest[i],current) or set()) for i in ids):
            done.add(g['id'])
    def context_replaced(unit):
        identifiers=unit.get('context_candidate_ids',[])
        if not identifiers or not (unit['stage']=='context' or unit.get('context_dependency_ids')): return False
        for identifier in identifiers:
            c=current.get(identifier,{});review=latest.get(identifier,{})
            keys=[('cq',i) for i in c.get('cq_ids',[])]+[('scope',i) for i in c.get('scope_item_ids',[])]
            proof=review.get('context_unit_ids',[])
            if not proof or unit['id'] in proof or not keys or any(assessments.get(k,{}).get('judgment')!='supported' for k in keys): return False
            if identifier not in (reviews.valid_ids(review,current) or set()): return False
            if not any(v['candidate_ref']==identifier and v['judgment']=='supported' for v in review.get('observation_checks',[])): return False
            if any(units.get(uid,{}).get('status')!='succeeded' or not set(units[uid]['dependency_ids'])<=available for uid in proof): return False
        return True
    failures=[f for f in result['failures'] if not owned_done(f['unit_id'],'unit_failure') and not context_replaced(units.get(f['unit_id'],{}))]
    return dict(record_errors=errors,binding_errors=binding,tool_errors=tools,failures=failures,
        capacity_pending=[p for p in result['capacity_pending'] if p['group_id'] not in done],
        mandatory_pending=[i for i in result['mandatory_pending'] if i not in done],
        no_result_groups=[g for g in result['no_result_groups'] if g['group_id'] not in done],
        group_errors=[dict(group_id=g['id'],error=g['error']) for g in list(groups.values())+run.get('candidate_groups',[])
            if g.get('error') and g['id'] not in done],
        analysis_pending_unit_ids=[role+':'+g['id'] for g in groups.values() for role in g.get('roles',['concept','relation'])
            if units.get(role+':'+g['id'],{}).get('status')!='succeeded' and not role_done(g,role)])

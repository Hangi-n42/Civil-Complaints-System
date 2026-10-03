"""Bounded cross-document draft comparison and one revision per candidate group."""
from copy import deepcopy

from . import discovery_analysis as a2, discovery_profile as profile, discovery_segments as segments, discovery_review as reviews
from . import discovery_candidates as identities


def evidence_ids(candidate):
    return list(dict.fromkeys(candidate.get('evidence_ids', []) + [e['evidence_id'] for e in candidate.get('evidence', [])]
        + [e for direction in ('a_to_b','b_to_a') for field in ('evidence_ids','counter_evidence_ids')
           for e in candidate.get(direction, {}).get(field, [])]))


def context_for(candidates, by_id, context_map):
    ids = list(dict.fromkeys(i for c in candidates for i in evidence_ids(c)))
    full = {i for c in candidates if not c.get('evidence_refs') for i in evidence_ids(c)}
    views = []
    for c in candidates:
        for ref in c.get('evidence_refs', []):
            if ref['block_id'] in full: continue
            b = by_id[ref['block_id']]
            matching = [v for v in segments.split(b) if v['span'][0] <= ref['span'][0] and ref['span'][1] <= v['span'][1]]
            view = matching[0] if matching else dict(block_id=b['id'],span=[0,len(b['text'])],shared_spans=[],recipe=segments.VERSION)
            if view not in views: views.append(view)
    views += [dict(block_id=i,span=[0,len(by_id[i]['text'])],shared_spans=[],recipe=segments.VERSION) for i in full]
    raw = segments.packet(dict(block_ids=ids,segments=views), by_id, context_map, a2.packet)
    context = dict(blocks=raw,
        reviewed_base=[c for c in candidates if c.get('review_status')=='reviewed'],
        unapproved_observations=[c for c in candidates if c.get('review_status')!='reviewed' and 'classification' in c],
        unapproved_relations=[c for c in candidates if 'negation' in c])
    deps = sorted({b['ref'] for b in raw} | {i for c in candidates for i in c.get('origin_dependency_ids', [])})
    return context, deps, {c['id']:c for c in candidates}


def fits(run, stage, context, deps, supplied, reserve=0):
    _, prompt = a2.make_prompt(run, stage, context, deps, supplied)
    return (len(prompt)+reserve <= run['recipe']['input_chars'] and
            len(prompt.encode())+reserve*3+run['recipe']['num_predict'] <= run['recipe']['num_ctx'])


def assemble(run, round_number, by_id, context_map, available):
    # ponytail: CQ/scope buckets plus stable source rotation, not semantic equivalence or all-pairs.
    identities.register(run)
    buckets = {}; by_link = {}; revisions = {}
    for unit in run['analysis_units']:
        if unit['status']!='succeeded' or not unit.get('output', {}).get('history'): continue
        for item in unit['output']['history']:
            revisions[identities.identifier(run,item['candidate_id'])] = (identities.view(run,item['after'],revised=True), unit['dependency_ids'])
    seen = set()
    for unit in run['analysis_units']:
        if unit['stage'] not in {'concept','relation','builder'} or unit['status']!='succeeded' or not set(unit['dependency_ids']) <= available:
            continue
        source_groups = run['candidate_groups'] if unit['stage']=='builder' else run['frontier']
        group = next(g for g in source_groups if g['id']==unit.get('parent_group_id',unit['group_id']))
        for row in unit['output'].get('observations', []) + unit['output'].get('relations', []) + unit['output'].get('modeled_relations', []):
            origin = identities.dependencies(run,row['id'])
            if not origin <= available: continue
            row = identities.view(run,row)
            revised, revision_deps = revisions.get(row['id'], (row, []))
            if not set(revision_deps) <= available: continue
            row = revised
            if row['outside_scope_reason'] or (row['validation'] and row['validation']!=row.get('evidence_validation')): continue
            links = sorted(['cq:'+i for i in row['cq_ids']] + ['scope:'+i for i in row['scope_item_ids']])
            candidate=dict(row, origin_dependency_ids=sorted(set(unit['dependency_ids']) | set(revision_deps) | origin), analysis_group_id=group.get('analysis_group_ids',[group['id']])[0])
            if group['round']==round_number and row['id'] not in seen: buckets.setdefault(links[0], []).append(candidate)
            seen.add(row['id'])
            for link in links: by_link.setdefault(link, {})[candidate['id']]=candidate
    assigned={i for g in run['candidate_groups'] for i in g['primary_candidate_ids']+g.get('design_candidate_ids', [])+g.get('correction_candidate_ids', [])}
    assigned.update(identities.identifier(run,c['id']) for u in run['analysis_units']
                    if u.get('parent_group_id') and u['status']=='succeeded' for c in u['output'].get('observations', []))
    groups = []
    for anchor, rows in sorted(buckets.items()):
        sources = {}
        for c in rows:
            if c['id'] in assigned: continue
            sources.setdefault(by_id[c['evidence_ids'][0]]['source_group'], []).append(c)
        if not sources: continue
        ordered = [values[n] for n in range(max(map(len, sources.values()))) for _,values in sorted(sources.items()) if n<len(values)]
        current = []
        for candidate in ordered:
            trial = current + [candidate]
            ctx, deps, supplied = context_for(trial, by_id, context_map)
            if current and (len(trial)>12 or sum(c.get('statement_type') in {'rule','definition'} for c in trial)>2 or not fits(run,'builder',ctx,deps,supplied,reserve=3000)):
                groups.append(dict(anchor=anchor, candidates=current)); current=[]
            current.append(candidate)
        if current: groups.append(dict(anchor=anchor,candidates=current))
    for group in groups:
        own = group['candidates']; own_ids={c['id'] for c in own}
        # Reviewed definitions and related unapproved observations are comparison-only.
        links={link for c in own for link in ['cq:'+i for i in c['cq_ids']]+['scope:'+i for i in c['scope_item_ids']]}
        omitted_analysis = {i for g in run['frontier'] if g['id'] in {c['analysis_group_id'] for c in own} for i in g.get('omitted_comparison_ids', [])}
        related = [c for c in a2.base_context(run) if c['id'] in omitted_analysis or links & {'cq:'+i for i in c.get('cq_ids', [])}]
        matches={i:c for link in sorted(links) for i,c in by_link.get(link, {}).items() if i not in own_ids}
        related += list(matches.values())
        group['omitted_related_ids'] = []
        included = list(own)
        for candidate in related:
            ctx,deps,supplied=context_for(included+[candidate],by_id,context_map)
            if len(included)<12 and fits(run,'builder',ctx,deps,supplied,reserve=3000): included.append(candidate)
            else: group['omitted_related_ids'].append(candidate['id'])
        group.update(id='cg_'+profile.digest([round_number,sorted(own_ids)])[:20], round=round_number,
            candidates=included, primary_candidate_ids=sorted(own_ids), status='pending',
            analysis_group_ids=sorted({c['analysis_group_id'] for c in own}))
    # A compact pair preserves a deferred reviewed definition without enlarging a primary packet.
    base = {c['id']:c for c in a2.base_context(run)}
    for group in list(groups):
        for identifier in group['omitted_related_ids']:
            if identifier not in base: continue
            primary = next(c for c in group['candidates'] if c['id'] in group['primary_candidate_ids'])
            pair = [primary,base[identifier]]
            ctx,deps,supplied = context_for(pair,by_id,context_map)
            if fits(run,'builder',ctx,deps,supplied,reserve=3000):
                groups.append(dict(group,id='compare_'+profile.digest([group['id'],identifier])[:20],
                    candidates=pair,primary_candidate_ids=[primary['id']],omitted_related_ids=[],comparison_only=True))
    return groups


def add_retrieved(run, stage, context, deps, supplied, identifiers, by_id, context_map):
    omitted = []
    for identifier in dict.fromkeys(identifiers):
        extra = a2.packet([identifier], by_id, context_map)
        trial = deepcopy(context)
        existing = a2.raw_refs(trial)
        trial.setdefault('independently_retrieved', []).extend(b for b in extra if b['ref'] not in existing)
        trial_deps = sorted(set(deps) | {b['ref'] for b in extra})
        if fits(run,stage,trial,trial_deps,supplied): context,deps=trial,trial_deps
        else: omitted.append(identifier)
    return context,deps,omitted


def add_terms(run, stage, context, deps, supplied, unit, by_id, context_map):
    omitted=[]
    for result in unit.get('tool_results', []):
        for term in result.get('terms', []):
            raw=a2.packet(evidence_ids(term),by_id,context_map)
            trial=deepcopy(context)
            trial.setdefault('comparison_terms', []).append(term)
            existing=a2.raw_refs(trial)
            trial.setdefault('tool_originals', []).extend(b for b in raw if b['ref'] not in existing)
            trial_deps=sorted(set(deps) | {b['ref'] for b in raw} | set(term.get('origin_dependency_ids', [])))
            trial_supplied=dict(supplied, **{term['id']:term})
            if fits(run,stage,trial,trial_deps,trial_supplied): context,deps,supplied=trial,trial_deps,trial_supplied
            else: omitted.append(term['id'])
    return context,deps,supplied,omitted


def review_context(run, group, taxonomy, by_id, context_map, history=(), extra=()):
    effective = {c['id']:c for c in group['candidates']}
    effective.update({c['id']:c for c in group['design_candidates']})
    endpoints = {r[k] for r in taxonomy.get('modeled_relations', []) for k in ('subject','object')}
    endpoints.update(h[k] for h in taxonomy['hierarchies'] for k in ('child_ref','parent_ref'))
    effective.update({i:c for i,c in group['builder_tool_context']['terms'].items() if i in endpoints})
    effective.update({c['id']:c for c in extra})
    effective.update({h['candidate_id']:identities.view(run,h['after'],revised=True) for h in history})
    context,deps,supplied=context_for(list(effective.values()),by_id,context_map)
    supplied.update({h['id']:h for h in taxonomy['hierarchies']})
    context['review_target_ids']=sorted(set(group['primary_candidate_ids']+group.get('design_candidate_ids', [])+
        [h['id'] for h in taxonomy['hierarchies']]+[c['id'] for c in extra]))
    context['comparison_candidate_ids']=sorted(supplied.keys()-set(context['review_target_ids']))
    if group.get('comparison_only'): context['comparison_only']=True
    primary,_,_ = context_for([c for i,c in effective.items() if i in context['review_target_ids']],by_id,context_map)
    primary_views = {(v['ref'],tuple(v.get('span',[0,len(v['text'])]))) for v in primary['blocks']}
    for view in context['blocks']:
        if group.get('comparison_only') or (view['ref'],tuple(view.get('span',[0,len(view['text'])]))) not in primary_views:
            view.update(analysis_target=False,context_only=True)
    # Resolved endpoints and reasons already appear on the modeled relations.
    context['taxonomy']={k:v for k,v in taxonomy.items() if k not in {'observations','modeled_relations','relation_bindings'}}
    coverage = [t for g in run['frontier'] if g['id'] in group['analysis_group_ids'] for t in g.get('analysis_target_coverage', [])]
    if coverage:
        context['analysis_target_coverage'] = [{k:v for k,v in t.items() if k!='source_ref'} for t in coverage]
    return context,deps,supplied


def review_batches(context, deps, supplied, by_id, context_map):
    """Prepare stable focused calls through the existing serial runner."""
    result=[]
    targets=set(context['review_target_ids'])
    for role, marker in [('relations','negation'),('observations','classification')]:
        ids=sorted(i for i in targets if marker in supplied[i] or role=='observations' and 'child_ref' in supplied[i])
        for n in range(0,len(ids),2):
            primary=ids[n:n+2];needed=set(primary)
            pending=list(primary)
            while pending:
                candidate=supplied[pending.pop()]
                links=list(candidate.get('source_relation_ids', []))
                fields=('subject','object') if candidate.get('source_relation') else ('child_ref','parent_ref')
                links += [candidate[k] for k in fields if k in candidate]
                for identifier in links:
                    if identifier in supplied and identifier not in needed:
                        needed.add(identifier);pending.append(identifier)
            terms={i:deepcopy(supplied[i]) for i in sorted(needed)}
            required,_,_=context_for(list(terms.values()),by_id,context_map)
            raw_ids=a2.raw_refs(required)
            part=deepcopy(context)
            for field in ('blocks','independently_retrieved','tool_originals'):
                if field in part:part[field]=[v for v in part[field] if v['ref'] in raw_ids]
            for field,kind in [('unapproved_relations','negation'),('unapproved_observations','classification')]:
                part[field]=[terms[i] for i in primary if kind in terms[i]]
            part['reviewed_base']=[]
            part['comparison_terms']=[c for i,c in terms.items() if i not in primary]
            part['taxonomy']=dict(hierarchies=[terms[i] for i in primary if 'child_ref' in terms[i]])
            part['review_target_ids']=primary
            part['comparison_candidate_ids']=sorted(needed-set(primary))
            part['review_focus']=role
            coverage=[dict(t,candidate_ids=sorted(set(t['candidate_ids']) & set(primary)))
                      for t in context.get('analysis_target_coverage', []) if set(t['candidate_ids']) & set(primary)]
            owned=[]
            for ref in [r for i in primary for r in terms[i].get('evidence_refs', [])] + coverage:
                span=dict(block_id=ref['block_id'],span=list(ref['span']))
                if span not in owned: owned.append(span)
            if context.get('comparison_only'): owned=[];coverage=[]
            provided=segments.originals(part)
            for s in owned:
                a,z=s['span']
                if any(v['ref']==s['block_id'] and v.get('span',[0,len(v['text'])])==[a,z] for v in provided): continue
                parent=next((v for v in provided if v['ref']==s['block_id'] and
                    v.get('span',[0,len(v['text'])])[0]<=a<z<=v.get('span',[0,len(v['text'])])[1]),None)
                if parent:
                    offset=parent.get('span',[0])[0]
                    part['blocks'].append(dict(parent,text=parent['text'][a-offset:z-offset],span=[a,z]))
            # Exact saved spans only: a legacy block ID cannot establish paragraph ownership.
            for view in segments.originals(part):
                a,z=view.get('span',[0,len(view['text'])])
                own=any(s['block_id']==view['ref'] and s['span'][0]<=a<z<=s['span'][1] for s in owned)
                view.update(analysis_target=own,context_only=not own)
            part['analysis_target_coverage']=coverage
            part['review_scope']=dict(part.get('review_scope', {}),extent='provided_only',whole_input_assessed=False,
                omitted_comparison_ids=sorted(set(part.get('review_scope', {}).get('omitted_comparison_ids', [])) | (supplied.keys()-needed)),
                omitted_block_ids=sorted(a2.raw_refs(context)-a2.raw_refs(part)),
                primary_source_spans=owned,
                missing_meanings_allowed=bool(owned) and all(any(kind in c for c in terms.values()) for kind in ('classification','negation')))
            result.append(dict(key=role+':'+profile.digest(primary)[:16],context=part,dependency_ids=list(deps),supplied=terms))
    return result


def review_ids(group, revised=False):
    return group.get('revision_review_unit_ids' if revised else 'review_unit_ids',
                     [group.get('revision_review_unit_id')] if revised and group.get('revision_review_unit_id') else [] if revised else ['critic:'+group['id']])


def pending_review_units(run, group, by_id, context_map):
    if 'review_unit_ids' in group: return group['review_unit_ids']
    builder=next((u for u in run['analysis_units'] if u['id']=='builder:'+group['id'] and u['status']=='succeeded'),None)
    if builder:
        taxonomy=identities.output(run,builder['output'])
        context,deps,supplied=review_context(run,group,taxonomy,by_id,context_map)
        return ['critic:'+group['id']+':'+b['key'] for b in review_batches(context,deps,supplied,by_id,context_map)]
    primary=[c for c in group['candidates'] if c['id'] in group['primary_candidate_ids']]
    relations=sum('negation' in c for c in primary)
    observations=sum('classification' in c for c in primary)
    designs=0 if group.get('comparison_only') else 2*sum(c.get('statement_type') in {'rule','definition'} for c in primary)
    hierarchies=a2.models.Taxonomy.model_json_schema()['properties']['hierarchies']['maxItems']
    count=(relations+1)//2+(observations+designs+hierarchies+1)//2
    # Reservation identifiers only; no synthetic successful execution units.
    return ['critic:'+group['id']+':reserved:'+str(n) for n in range(count)]


def combined_review(outputs):
    """Transient revision input; persisted critiques remain individual real calls."""
    result={field:[v for output in outputs for v in output.get(field, [])] for field in
        ('issues','missing_meanings','relation_checks','observation_checks','hierarchy_checks','record_errors','gaps','actions','capacity_pending')}
    result['issues']=[issue for output in outputs for issue in output.get('issues', [])
                      if not issue.get('candidate_ref') or issue['candidate_ref'] in set(output['review_coverage']['expected_candidate_ids']) & set(output['review_coverage']['valid_candidate_ids'])]
    result['needs_revision']=any(o['needs_revision'] and (not o.get('issues') or any(i in result['issues'] for i in o['issues'])) for o in outputs)
    result['review_coverage']={field:sorted({v for o in outputs for v in o['review_coverage'][field]}) for field in
        ('expected_candidate_ids','valid_candidate_ids','pending_candidate_ids')}
    result['review_coverage']['candidate_hashes']={i:h for o in outputs for i,h in o['review_coverage']['candidate_hashes'].items()}
    if any('review_dependency_contract' in o or 'binding_dependency_hashes' in o for o in outputs):
        result['review_dependency_contract']='selected-types-v1'
        result['binding_dependency_hashes']={i:h for o in outputs for i,h in o.get('binding_dependency_hashes', {}).items()}
    return result


def focused_reviews(service,run,group,context,deps,supplied,by_id,context_map,index=None,blocks=None,revised=False):
    batches=review_batches(context,deps,supplied,by_id,context_map)
    prefix=group['id']+(':revision1:review' if revised else '')
    field='revision_review_unit_ids' if revised else 'review_unit_ids'
    group[field]=['critic:'+prefix+':'+b['key'] for b in batches]
    a2.save(service,run)
    outputs=[]
    for batch in batches:
        if a2.cancelled(service,run): break
        key=prefix+':'+batch['key']
        output=a2.call(service,run,'critic',key,batch['context'],batch['dependency_ids'],by_id,batch['supplied'])
        if output is None: continue
        outputs.append(output)
        if not revised: a2.apply_actions(service,run,index,blocks,'critic',key,output)
        a2.queue_recovery(run,output,group,by_id)
        if revised and any(a['action']!='finish' for a in output.get('actions', [])):
            group['revision_deferrals'].extend(dict(candidate_ref=i,reason='수정 후 Critic의 추가 도구 요청 미처리; 사람 검수로 보류') for i in batch['context']['review_target_ids'])
    return combined_review(outputs) if len(outputs)==len(batches) and outputs else None


def revise(service, run, group, review, taxonomy, by_id, context_map):
    candidates = dict(group.get('builder_tool_context', {}).get('terms', {}))
    candidates.update({c['id']:c for c in group['candidates'] + group.get('design_candidates', [])})
    candidates.update({c['id']:c for c in taxonomy['hierarchies']})
    source_issues = [dict(candidate_ref=e['relation_ref'],cause='content_error',reason=e['reason'],
                         evidence_ids=[],counter_evidence_ids=[]) for e in group.get('source_errors', [])]
    issues = review['issues'] + source_issues
    target_ids = {i['candidate_ref'] for i in issues if i.get('cause','content_error') in {'content_error','evidence_error'}}
    target_ids.update(c['candidate_ref'] for field in ('relation_checks','observation_checks')
                      for c in review.get(field, []) if c['judgment']=='refuted')
    evidence_only = {i['candidate_ref'] for i in issues if i.get('cause')=='evidence_error'}
    evidence_only.update(i for i,c in candidates.items() if c.get('evidence_validation'))
    evidence_only -= {i['candidate_ref'] for i in issues if i.get('cause','content_error')=='content_error'}
    target_ids.update(evidence_only)
    valid = reviews.valid_ids(review,candidates)
    if valid is not None: target_ids &= valid
    editable=set(group['primary_candidate_ids']+group.get('design_candidate_ids', [])) | {c['id'] for c in taxonomy['hierarchies']}
    group['revision_deferrals'] = [dict(candidate_ref=i,reason='비교 후보/검토 기준은 이 묶음에서 수정하지 않음; 담당 묶음 또는 사람 검수로 보류') for i in sorted(target_ids-editable)]
    target_ids &= editable
    binding_ids = {c['candidate_ref'] for c in review.get('relation_checks', [])
                   if c['judgment']=='supported' and 'refuted' in c.get('binding_checks', {}).values()
                   and c['candidate_ref'] in editable and (valid is None or c['candidate_ref'] in valid)
                   and candidates[c['candidate_ref']].get('source_relation')}
    binding_ids -= target_ids
    # Persist the actual target/unit correspondence once, including across cancellation.
    plan=group.setdefault('correction_plan', [dict(candidate_id=i,stage=stage,
        key=group['id']+(':'+('revision1' if stage=='revision' else 'binding1')+':'+i))
        for stage,ids in [('revision',target_ids),('builder',binding_ids)] for i in sorted(ids)])
    if not plan: return
    if not run['recipe']['budgets']['revisions']:
        group['revision_deferrals'].extend(dict(candidate_ref=p['candidate_id'],reason='수정 예산 0; 사람 검수로 보류') for p in plan)
        return
    units={u['id']:u for u in run['analysis_units']}
    unfinished=[p for p in plan if not units.get(p['stage']+':'+p['key'], {}).get('attempts')]
    successful=[units[p['stage']+':'+p['key']] for p in plan if units.get(p['stage']+':'+p['key'], {}).get('status')=='succeeded']
    history=[h for u in successful for h in u['output'].get('history', [])]
    extra=[c for u in successful if u['stage']=='builder' for c in identities.output(run,u['output']).get('observations', [])]
    pending=[p['stage'] for p in unfinished]
    if unfinished or history:
        if group.get('revision_review_unit_ids'):
            pending += ['critic' for uid in group['revision_review_unit_ids'] if units.get(uid,{}).get('status')!='succeeded']
        else:
            context,deps,supplied=review_context(run,group,taxonomy,by_id,context_map,history,extra)
            count=len(review_batches(context,deps,supplied,by_id,context_map))
            # Each one-relation Builder may add two endpoint types: at most one more focused batch.
            count += sum(p['stage']=='builder' for p in unfinished)
            pending += ['critic']*count
    estimates=run.get('role_time_estimates', {})
    required_s=sum(estimates.get(stage, {}).get('estimate_s',run['recipe']['call_timeout']) for stage in pending)
    budget=run['recipe']['budgets'];metrics=run['metrics']
    remaining_s=budget['model_seconds']-metrics['model_total_s']-metrics.get('interrupted_time_reserve_s',0)
    group['revision_reservation']=dict(pending_stages=pending,model_calls=len(pending),estimated_model_s=required_s)
    if budget['model_calls']-metrics['llm_calls']<len(pending) or remaining_s<required_s:
        group['revision_deferrals'].extend(dict(candidate_ref=p['candidate_id'],reason='수정과 필수 재검수의 호출/시간 예산 부족; 자동 증액 없음') for p in plan)
        return
    history=[];extra=[];all_deps=set();provided=[]
    effective_hierarchies=deepcopy(taxonomy['hierarchies'])
    for p in plan:
        if a2.cancelled(service,run): return
        identifier,stage,key=p['candidate_id'],p['stage'],p['key'];uid=stage+':'+key
        existing=units.get(uid)
        for request in run.get('recovery_requests', []):
            if request['role']==stage and request.get('candidate_ref')==identifier and request['critic_group_id']==group['id']:
                request['unit_id']=uid
        if existing and existing.get('attempts') and existing['status']!='succeeded':
            group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='수정 1회 사용 후 실패/중단: '+str(existing.get('error') or '결과 저장 미완료')))
            continue
        effective=dict(candidates)
        effective.update({h['candidate_id']:identities.view(run,h['after'],revised=True) for h in history})
        effective.update({c['id']:c for c in extra})
        effective.update({h['id']:h for h in effective_hierarchies})
        # Full dependencies validate cross-target hierarchy/endpoint consistency after each success.
        context,deps,supplied=context_for(list(effective.values()),by_id,context_map)
        checks=[c for field in ('relation_checks','observation_checks') for c in review.get(field, []) if c['candidate_ref']==identifier]
        selected_issues=[i for i in issues if not i.get('candidate_ref') or i['candidate_ref']==identifier]
        extra_ids=[e for i in selected_issues for f in ('evidence_ids','counter_evidence_ids') for e in i.get(f, [])]
        extra_ids += [r['evidence_id'] for c in checks for r in c.get('evidence_refs', [])]
        raw=a2.packet(list(dict.fromkeys(extra_ids)),by_id,context_map)
        context['blocks'] += [b for b in raw if b['ref'] not in a2.raw_refs(context)]
        deps=sorted(set(deps) | {b['ref'] for b in raw})
        if stage=='revision':
            for field in ('unapproved_observations','unapproved_relations','reviewed_base'): context.pop(field)
            context.update(target_ids=[identifier],targets=[effective[identifier]],
                evidence_only_ids=[identifier] if identifier in evidence_only else [],
                source_change_ids=[identifier] if effective[identifier].get('source_relation') and identifier not in evidence_only else [],
                comparison_candidates=[c for i,c in effective.items() if i!=identifier],issues=selected_issues,
                relation_checks=[c for c in checks if 'negation' in effective[identifier]],
                observation_checks=[c for c in checks if 'classification' in effective[identifier]])
        else:
            original=effective[identifier]
            supplied[identifier]=deepcopy(original['source_relation'])
            context.update(unapproved_relations=[supplied[identifier]],design_relation_ids=[identifier],
                binding_before=original,parent_group_id=group['id'],binding_checks=checks)
        omitted=[];term_omissions=[]
        for critic in [u for u in run['analysis_units'] if u['id'] in review_ids(group) and u['status']=='succeeded']:
            requested=[i for r in critic.get('tool_results', []) for i in r.get('block_ids', [])]
            deps=sorted(set(deps) | set(critic['dependency_ids']))
            context,deps,missing=add_retrieved(run,stage,context,deps,supplied,requested,by_id,context_map);omitted.extend(missing)
            context,deps,supplied,missing=add_terms(run,stage,context,deps,supplied,critic,by_id,context_map);term_omissions.extend(missing)
        group['omitted_revision_term_ids']=term_omissions;group['omitted_revision_context_ids']=omitted
        if not fits(run,stage,context,deps,supplied):
            group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='필수 원문 전체가 수정 입력 한도를 초과하여 보류'))
            continue
        result=a2.call(service,run,stage,key,context,deps,by_id,supplied)
        unit=next(u for u in run['analysis_units'] if u['id']==uid)
        if result is None:
            group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='수정 결과 미확정: '+str(unit.get('error') or '취소/중단')))
            continue
        history.extend(result.get('history', []));all_deps.update(unit['dependency_ids']);provided.extend(unit['provided_block_ids'])
        effective_hierarchies=[identities.view(run,h) for h in result.get('effective_hierarchies',effective_hierarchies)]
        if stage=='builder':
            extra.extend(identities.output(run,result).get('observations', []))
            if not result.get('history'):
                group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='연결 교정 미완료; '+str(result.get('source_errors') or result.get('binding_errors') or result.get('relation_bindings'))))
    group['correction_candidate_ids']=sorted({c['id'] for c in extra})
    if history:
        revised_taxonomy=deepcopy(taxonomy)
        revised_taxonomy['hierarchies']=effective_hierarchies
        context,deps,supplied=review_context(run,group,revised_taxonomy,by_id,context_map,history,extra)
        deps=sorted(set(deps)|all_deps)
        context['review_scope']=deepcopy(group.get('review_scope',dict(extent='provided_only',whole_input_assessed=False)))
        context['review_search_status']=[{k:v for k,v in item.items() if k!='block_ids'} for item in group.get('critic_searches', [])]
        context,deps,omitted=add_retrieved(run,'critic',context,deps,supplied,provided,by_id,context_map)
        group['omitted_revision_review_context_ids']=omitted
        group['revision_review_status']='미검수 수정 제안; 사람이 재검수해야 함'
        if focused_reviews(service,run,group,context,deps,supplied,by_id,context_map,revised=True) is not None:
            group['revision_review_status']='수정 제안의 AI 재검수 저장; 사람 수락 아님'


def synthesize(service, run, round_number, index, blocks, by_id, context_map, allow_revisions=True):
    if a2.cancelled(service,run): return
    run['candidate_groups'].extend(assemble(run,round_number,by_id,context_map,a2.allowed_ids(service,blocks)))
    a2.save(service,run)
    revisions = []
    for group in a2.ordered_groups(run, [g for g in run['candidate_groups'] if g['round']==round_number], 'review:'+str(round_number)):
        if a2.cancelled(service,run): return
        key=group['id'];group.pop('error',None)
        context,deps,supplied=context_for(group['candidates'],by_id,context_map)
        context['design_relation_ids'] = [] if group.get('comparison_only') else [i for i in group['primary_candidate_ids'] if supplied[i].get('statement_type') in {'rule','definition'}]
        alignments = [identities.alignment(run,a) for u in run['analysis_units'] if u['status']=='succeeded' for a in u['output'].get('alignments', [])]
        context['candidate_alignments'] = [{k:v for k,v in a.items() if k not in {'target_snapshot','target_fingerprint'}} for a in alignments
            if a['observation_ref'] in supplied and a['target_id'] in supplied
            and (a.get('target_scope')!='run_candidate' or a.get('target_fingerprint')==identities.exact_key(supplied[a['target_id']]))]
        if 'builder_tool_context' not in group:
            units = [u for u in run['analysis_units'] if u['stage']=='concept' and u['status']=='succeeded' and u['group_id'] in group['analysis_group_ids']]
            ids = [i for u in units for r in u.get('tool_results', []) for i in r.get('block_ids', [])]
            trial, trial_deps, omitted = add_retrieved(run,'builder',context,deps,supplied,ids,by_id,context_map)
            trial_supplied = dict(supplied); term_omissions = []
            for unit in units:
                trial,trial_deps,trial_supplied,missing = add_terms(run,'builder',trial,trial_deps,trial_supplied,unit,by_id,context_map)
                term_omissions.extend(missing)
            links = {i for c in group['candidates'] for i in c.get('cq_ids', [])+c.get('scope_item_ids', [])}
            prior = [c for c in a2.lookup(service,run,'','type',blocks) if c.get('support_type')=='design_proposal'
                     and c['id'] not in trial_supplied and links & set(c.get('cq_ids', [])+c.get('scope_item_ids', []))]
            trial,trial_deps,trial_supplied,missing = add_terms(run,'builder',trial,trial_deps,trial_supplied,
                dict(tool_results=[dict(terms=prior)]),by_id,context_map)
            term_omissions.extend(missing)
            group['builder_tool_context'] = dict(context={k:trial[k] for k in ('independently_retrieved','tool_originals','comparison_terms') if k in trial},
                dependency_ids=sorted(set(trial_deps)-set(deps)),terms={i:c for i,c in trial_supplied.items() if i not in supplied})
            group['omitted_builder_context_ids'],group['omitted_builder_term_ids'] = omitted,term_omissions
        extra = group['builder_tool_context']
        context.update(deepcopy(extra['context']));deps=sorted(set(deps)|set(extra['dependency_ids']))
        supplied.update(deepcopy(extra['terms']))
        taxonomy=a2.call(service,run,'builder',key,context,deps,by_id,supplied)
        if taxonomy is None: continue
        a2.apply_actions(service,run,index,blocks,'builder',key,taxonomy)
        new_design_ids = {c['id'] for c in taxonomy.get('observations', []) if identities.identifier(run,c['id'])==c['id']}
        taxonomy = identities.output(run,taxonomy)
        # Preserve the original Builder input on resume; overlay designs only for downstream consumers.
        group['design_candidates'] = taxonomy.get('observations', []) + taxonomy.get('modeled_relations', [])
        group['source_errors'] = taxonomy.get('source_errors', [])
        group['design_candidate_ids'] = [c['id'] for c in taxonomy.get('observations', []) if c['id'] in new_design_ids]
        a2.review_reservation(run,round_number,by_id,context_map,a2.allowed_ids(service,blocks))
        context,deps,supplied=review_context(run,group,taxonomy,by_id,context_map)
        try:
            if 'critic_context_ids' not in group:
                label=' '.join(c.get('label',c.get('subject','')) for c in group['candidates'][:3])
                searches=[]; retrieved=[]
                for purpose,query in [('critic_related',label[:200]),
                                      ('critic_counter',(label[:100]+' 제외 다만 경우 변경')[:200])]:
                    try:
                        ids=a2.search(service,run,index,blocks,query,purpose)
                        retrieved.extend(ids)
                        searches.append(dict(purpose=purpose,status='succeeded',block_ids=ids))
                    except ValueError as exc:
                        searches.append(dict(purpose=purpose,status='incomplete',reason=str(exc)))
                group['critic_searches']=searches
                group['critic_context_ids']=list(dict.fromkeys(retrieved));a2.save(service,run)
            context['review_search_status']=[{k:v for k,v in item.items() if k!='block_ids'}
                                             for item in group.get('critic_searches', [])]
            builder_unit=next(u for u in run['analysis_units'] if u['id']=='builder:'+key)
            requested=[i for r in builder_unit.get('tool_results', []) for i in r.get('block_ids', [])]
            context,deps,omitted=add_retrieved(run,'critic',context,deps,supplied,group['critic_context_ids']+requested,by_id,context_map)
            context,deps,supplied,term_omissions=add_terms(run,'critic',context,deps,supplied,builder_unit,by_id,context_map)
            group['omitted_critic_term_ids']=term_omissions
            group['omitted_critic_context_ids']=omitted
            context['comparison_candidate_ids']=sorted(supplied.keys()-set(context['review_target_ids']))
            if 'review_scope' not in group:
                known={identities.identifier(run,c['id']) for u in run['analysis_units'] if u['status']=='succeeded' for field in ('observations','relations') for c in u['output'].get(field, [])}
                group['review_scope']=dict(extent='provided_only',whole_input_assessed=False,
                    known_not_provided=len(known-supplied.keys()),omitted_comparison_ids=sorted(set(group.get('omitted_related_ids', [])+term_omissions)))
            context['review_scope']=deepcopy(group['review_scope'])
            review=focused_reviews(service,run,group,context,deps,supplied,by_id,context_map,index,blocks)
            if review is None: continue
            group['status']='review_issues_generated'
            needs_context=any(r.get('block_ids') or r.get('terms') for u in run['analysis_units'] if u['id'] in review_ids(group) for r in u.get('tool_results', []))
            candidate_revision = bool(group.get('source_errors')) or review['needs_revision'] and (not review.get('missing_meanings') or any(i.get('candidate_ref') for i in review['issues']))
            if candidate_revision or needs_context or any((c['judgment']=='refuted' if run['recipe'].get('review_contract')=='checks-v1' else c['judgment']!='supported') for field in ('relation_checks','observation_checks') for c in review.get(field, [])) or any(c.get('evidence_validation') for c in supplied.values()):
                revisions.append((group,review,taxonomy))
        except ValueError as exc:
            group['error']=str(exc)
        a2.save(service,run)
    succeeded = {u['id'] for u in run['analysis_units'] if u['status']=='succeeded'}
    pending = [i for g in run['candidate_groups'] for i in ['builder:'+g['id']]+review_ids(g) if i not in succeeded]
    for group,review,taxonomy in revisions:
        if a2.cancelled(service,run): return
        if pending or not allow_revisions:
            group['revision_deferred_reason'] = '미완료 주분석/미검수 Builder/Critic 묶음 우선; 수정 호출 보류'
        else:
            group.pop('revision_deferred_reason',None)
            try:
                revise(service,run,group,review,taxonomy,by_id,context_map)
            except ValueError as exc:
                group['error']=str(exc)
        a2.save(service,run)

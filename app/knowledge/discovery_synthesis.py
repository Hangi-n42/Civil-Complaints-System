"""Bounded cross-document draft comparison and one revision per candidate group."""
from copy import deepcopy

from . import discovery_analysis as a2, discovery_profile as profile, discovery_segments as segments, discovery_review as reviews


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
    buckets = {}; by_link = {}; revisions = {}
    for unit in run['analysis_units']:
        if unit['stage']!='revision' or unit['status']!='succeeded': continue
        for item in unit['output']['history']:
            revisions[item['candidate_id']] = (item['after'], unit['dependency_ids'])
    for unit in run['analysis_units']:
        if unit['stage'] not in {'concept','relation','builder'} or unit['status']!='succeeded' or not set(unit['dependency_ids']) <= available:
            continue
        source_groups = run['candidate_groups'] if unit['stage']=='builder' else run['frontier']
        group = next(g for g in source_groups if g['id']==unit['group_id'])
        for row in unit['output'].get('observations', []) + unit['output'].get('relations', []) + unit['output'].get('modeled_relations', []):
            revised, revision_deps = revisions.get(row['id'], (row, []))
            if not set(revision_deps) <= available: continue
            row = revised
            if row['outside_scope_reason'] or (row['validation'] and row['validation']!=row.get('evidence_validation')): continue
            links = sorted(['cq:'+i for i in row['cq_ids']] + ['scope:'+i for i in row['scope_item_ids']])
            candidate=dict(row, origin_dependency_ids=sorted(set(unit['dependency_ids']) | set(revision_deps)), analysis_group_id=group.get('analysis_group_ids',[group['id']])[0])
            if group['round']==round_number: buckets.setdefault(links[0], []).append(candidate)
            for link in links: by_link.setdefault(link, {})[candidate['id']]=candidate
    assigned={i for g in run['candidate_groups'] for i in g['primary_candidate_ids']+g.get('design_candidate_ids', [])}
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
            if current and (len(trial)>12 or not fits(run,'builder',ctx,deps,supplied,reserve=3000)):
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


def revise(service, run, group, review, taxonomy, by_id, context_map):
    candidates = {c['id']:c for c in group['candidates']}
    candidates.update({c['id']:c for c in group.get('design_candidates', [])})
    candidates.update({c['id']:c for c in taxonomy['hierarchies']})
    issues = review['issues']
    routed = {i['candidate_ref'] for i in issues if i.get('cause') in {'endpoint','alignment','source_absent','budget_exhausted'}}
    target_ids = {i['candidate_ref'] for i in issues if i['candidate_ref'] and i.get('cause','content_error') in {'content_error','evidence_error'}}
    target_ids.update(i['candidate_ref'] for i in review['relation_checks'] if i['judgment']!='supported' and i['candidate_ref'] not in routed)
    evidence_only = {i['candidate_ref'] for i in issues if i.get('cause')=='evidence_error'}
    evidence_only.update(i for i,c in candidates.items() if c.get('evidence_validation'))
    evidence_only -= {i['candidate_ref'] for i in issues if i.get('cause','content_error')=='content_error'}
    target_ids.update(evidence_only)
    if not target_ids and not (issues or review.get('missing_meanings') or review.get('record_errors')):
        target_ids=set(group['primary_candidate_ids'])
    target_ids &= set(candidates)
    valid = reviews.valid_ids(review,candidates)
    if valid is not None: target_ids &= valid
    editable=set(group['primary_candidate_ids']+group.get('design_candidate_ids', [])) | {c['id'] for c in taxonomy['hierarchies']}
    group['revision_deferrals'] = [dict(candidate_ref=i,reason='비교 후보/검토 기준은 이 묶음에서 수정하지 않음; 담당 묶음 또는 사람 검수로 보류') for i in sorted(target_ids-editable)]
    target_ids &= editable
    if not run['recipe']['budgets']['revisions']:
        group['revision_deferrals'].extend(dict(candidate_ref=i,reason='수정 예산 0; 사람 검수로 보류') for i in sorted(target_ids))
        for request in run.get('recovery_requests', []):
            if request['role']=='revision' and request.get('candidate_ref') in target_ids:
                request.update(status='budget_exhausted',stop_cause='budget_exhausted',reason='수정 예산 0; 자동 증액 없음')
        return
    existing=next((u for u in run['analysis_units'] if u['id']=='revision:'+group['id']+':revision1'),None)
    if existing and existing['attempts'] and existing['status']!='succeeded':
        group['revision_deferrals'].extend(dict(candidate_ref=i,reason='수정 1회 사용 후 실패/중단: '+str(existing.get('error') or '결과 저장 미완료')+'; 사람 검수로 보류') for i in sorted(target_ids))
        return
    selected = []
    context = {}; deps=[]; supplied={}
    for identifier in sorted(target_ids):
        trial_ids=selected+[identifier]
        required=set(trial_ids)
        if any('classification' in candidates[i] or 'child_ref' in candidates[i] for i in trial_ids):
            required.update(c['id'] for c in taxonomy['hierarchies'])
        for i in list(required):
            for key in ('child_ref','parent_ref'):
                if candidates[i].get(key) in candidates: required.add(candidates[i][key])
        trial, trial_deps, trial_supplied = context_for([candidates[i] for i in sorted(required)],by_id,context_map)
        issues=[i for i in review['issues'] if not i['candidate_ref'] or i['candidate_ref'] in required]
        checks=[i for i in review['relation_checks'] if i['candidate_ref'] in required]
        extra_ids=[e for i in issues for f in ('evidence_ids','counter_evidence_ids') for e in i[f]]
        extra_ids += [e['evidence_id'] for i in checks for e in i.get('evidence_refs', [])]
        extra_ids += [i['evidence_id'] for i in checks if i['evidence_id']]
        extra=a2.packet(list(dict.fromkeys(extra_ids)),by_id,context_map)
        trial['blocks'] += [b for b in extra if b['ref'] not in a2.raw_refs(trial)]
        trial_deps=sorted(set(trial_deps) | {b['ref'] for b in extra})
        trial.pop('unapproved_observations'); trial.pop('unapproved_relations'); trial.pop('reviewed_base')
        trial.update(target_ids=trial_ids, targets=[candidates[i] for i in trial_ids], evidence_only_ids=sorted(set(trial_ids)&evidence_only),
            comparison_candidates=[candidates[i] for i in sorted(required-set(trial_ids))], issues=issues, relation_checks=checks)
        if fits(run,'revision',trial,trial_deps,trial_supplied):
            selected=trial_ids;context,deps,supplied=trial,trial_deps,trial_supplied
        else:
            group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='필수 원문 전체가 수정 입력 한도를 초과하여 보류'))
    if not selected: return
    unit=next(u for u in run['analysis_units'] if u['id']=='critic:'+group['id'])
    requested=[i for r in unit.get('tool_results', []) for i in r.get('block_ids', [])]
    deps=sorted(set(deps) | set(unit['dependency_ids']))
    context,deps,omitted=add_retrieved(run,'revision',context,deps,supplied,requested,by_id,context_map)
    context,deps,supplied,term_omissions=add_terms(run,'revision',context,deps,supplied,unit,by_id,context_map)
    group['omitted_revision_term_ids']=term_omissions
    group['omitted_revision_context_ids']=omitted
    for request in run.get('recovery_requests', []):
        if request['role']=='revision' and request.get('candidate_ref') in selected and request['critic_group_id']==group['id']:
            request['unit_id']='revision:'+group['id']+':revision1'
    result=a2.call(service,run,'revision',group['id']+':revision1',context,deps,by_id,supplied)
    if result is not None:
        group['revision_unit_id']='revision:'+group['id']+':revision1'
        group['revision_review_status']='미검수 수정 제안; 사람이 재검수해야 함'
    else:
        unit=next(u for u in run['analysis_units'] if u['id']=='revision:'+group['id']+':revision1')
        group['revision_deferrals'].extend(dict(candidate_ref=i,reason='수정 결과 미확정: '+str(unit.get('error') or '취소/중단')+'; 사람 검수로 보류') for i in selected)


def synthesize(service, run, round_number, index, blocks, by_id, context_map):
    if a2.cancelled(service,run): return
    run['candidate_groups'].extend(assemble(run,round_number,by_id,context_map,a2.allowed_ids(service,blocks)))
    a2.save(service,run)
    for group in [g for g in run['candidate_groups'] if g['round']==round_number]:
        if a2.cancelled(service,run): return
        key=group['id'];group.pop('error',None)
        context,deps,supplied=context_for(group['candidates'],by_id,context_map)
        context['design_relation_ids'] = [] if group.get('comparison_only') else [i for i in group['primary_candidate_ids'] if supplied[i].get('statement_type') in {'rule','definition'}]
        taxonomy=a2.call(service,run,'builder',key,context,deps,by_id,supplied)
        if taxonomy is None: continue
        a2.apply_actions(service,run,index,blocks,'builder',key,taxonomy)
        # Preserve the original Builder input on resume; overlay designs only for downstream consumers.
        group['design_candidates'] = taxonomy.get('observations', []) + taxonomy.get('modeled_relations', [])
        group['design_candidate_ids'] = [c['id'] for c in taxonomy.get('observations', [])]
        effective = {c['id']:c for c in group['candidates']}
        effective.update({c['id']:c for c in group['design_candidates']})
        context,deps,supplied=context_for(list(effective.values()),by_id,context_map)
        supplied.update({h['id']:h for h in taxonomy['hierarchies']})
        context['taxonomy']={k:v for k,v in taxonomy.items() if k not in {'observations','modeled_relations'}}
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
            review=a2.call(service,run,'critic',key,context,deps,by_id,supplied)
            if review is None: continue
            a2.apply_actions(service,run,index,blocks,'critic',key,review)
            group['status']='review_issues_generated'
            a2.queue_recovery(run, review, group, by_id)
            critic_unit=next(u for u in run['analysis_units'] if u['id']=='critic:'+key)
            needs_context=any(r.get('block_ids') or r.get('terms') for r in critic_unit.get('tool_results', []))
            candidate_revision = review['needs_revision'] and (not review.get('missing_meanings') or any(i.get('candidate_ref') for i in review['issues']))
            if candidate_revision or needs_context or any(c['judgment']!='supported' for c in review['relation_checks']) or any(c.get('evidence_validation') for c in effective.values()):
                revise(service,run,group,review,taxonomy,by_id,context_map)
        except ValueError as exc:
            group['error']=str(exc)
        a2.save(service,run)

"""Bounded cross-document draft comparison and one revision per candidate group."""
from copy import deepcopy

from . import discovery_analysis as a2, discovery_profile as profile, discovery_segments as segments, discovery_review as reviews
from . import discovery_candidates as identities, discovery_claims as claims, discovery_scope as scope


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


def input_size(run, stage, context, deps, supplied):
    return a2.input_size(run,stage,context,deps,supplied)


def fits(run, stage, context, deps, supplied, reserve=0):
    size=input_size(run,stage,context,deps,supplied)
    return (size['input_chars']+reserve <= size['input_chars_limit'] and
            size['request_input_bytes']+reserve*3 <= size['input_bytes_limit'])


def assemble(run, round_number, by_id, context_map, available):
    # ponytail: CQ/scope buckets plus stable source rotation, not semantic equivalence or all-pairs.
    identities.register(run)
    buckets = {}; by_link = {}; revisions = {}
    for unit in run['analysis_units']:
        if unit['status']!='succeeded' or not unit.get('output', {}).get('history'): continue
        for item in unit['output']['history']:
            revisions[identities.identifier(run,item['candidate_id'])] = (identities.history_view(run,item), unit['dependency_ids'])
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
            if run['recipe'].get('context_contract')=='scope-v1': ctx,deps=scope.source_context(ctx,deps,by_id)
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
            if run['recipe'].get('context_contract')=='scope-v1': ctx,deps=scope.source_context(ctx,deps,by_id)
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
            if run['recipe'].get('context_contract')=='scope-v1': ctx,deps=scope.source_context(ctx,deps,by_id)
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
        if run['recipe'].get('context_contract')=='scope-v1':
            trial.pop('context_contract',None)
            trial,trial_deps=scope.source_context(trial,trial_deps,by_id)
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
            if run['recipe'].get('context_contract')=='scope-v1':
                trial.pop('context_contract',None)
                trial,trial_deps=scope.source_context(trial,trial_deps,by_id)
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
    effective.update({h['candidate_id']:identities.history_view(run,h) for h in history})
    context,deps,supplied=context_for(list(effective.values()),by_id,context_map)
    supplied.update({h['id']:h for h in taxonomy['hierarchies']})
    context['review_target_ids']=sorted(set(group['primary_candidate_ids']+group.get('design_candidate_ids', [])+
        [h['id'] for h in taxonomy['hierarchies']]+[c['id'] for c in extra]))
    if history and run['recipe'].get('context_contract')=='scope-v1':
        context['revision_comparisons']={h['candidate_id']:dict(before=deepcopy(h['before']),after=deepcopy(effective[h['candidate_id']]),
            expected_meanings=deepcopy(h.get('preservation_basis',[])),required_context=deepcopy(h.get('required_context',[]))) for h in history}
    if history and run['recipe'].get('claim_review_contract')=='claims-v1':
        affected={h['candidate_id'] for h in history} | {c['id'] for c in extra}
        while True:
            related={i for i,c in supplied.items() if affected & (set(c.get('source_relation_ids', [])) |
                {c.get(k) for k in ('subject','object','child_ref','parent_ref')} |
                {c.get('role_basis', {}).get('relation_ref') if c.get('role_basis') else None})}
            if related<=affected: break
            affected |= related
        context['review_target_ids']=sorted(set(context['review_target_ids']) & affected)
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
    if run['recipe'].get('context_contract')=='scope-v1': context,deps=scope.source_context(context,deps,by_id)
    return context,deps,supplied


def review_batches(context, deps, supplied, by_id, context_map):
    """Prepare stable focused calls through the existing serial runner."""
    result=[]
    targets=set(context['review_target_ids'])
    for role, marker in [('relations','negation'),('observations','classification')]:
        ids=sorted(i for i in targets if marker in supplied[i] or role=='observations' and 'child_ref' in supplied[i])
        size=1 if role=='observations' and context.get('context_contract')=='scope-v1' else 2
        for n in range(0,len(ids),size):
            primary=ids[n:n+size];needed=set(primary)
            if role=='observations' and context.get('context_contract')=='scope-v1':
                primary_types={i for i in primary if supplied[i].get('classification')=='type'}
                needed.update(i for i,c in supplied.items() if c.get('source_relation') and
                    primary_types.intersection((c.get('subject'),c.get('object'))))
            pending=list(needed)
            while pending:
                candidate=supplied[pending.pop()]
                links=list(candidate.get('source_relation_ids', []))
                if context.get('context_contract')=='scope-v1':
                    links += [i for i,c in supplied.items() if c.get('child_ref')==candidate.get('id')]
                    links += [l['candidate_ref'] for c in candidate.get('scope_assessment', {}).get('required_meanings', []) for l in c['locations']]
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
            if context.get('context_contract')=='scope-v1':
                part['selected_hierarchies']=[c for i,c in terms.items() if i not in primary and 'child_ref' in c]
                part.pop('context_contract',None)
                part,batch_deps=scope.source_context(part,deps,by_id)
            else: batch_deps=deps
            part['revision_comparisons']={i:c for i,c in context.get('revision_comparisons',{}).items() if i in primary}
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
            key=role+':'+profile.digest(primary)[:16]
            bindings=[i for i in primary if terms[i].get('source_relation')]
            if role=='relations' and bindings:
                if context.get('context_contract')=='scope-v1': part['review_scope']['missing_meanings_allowed']=False
                part.update(review_component='proposition',binding_target_ids=bindings)
                result.append(dict(key=key+':proposition',bundle_key=key,context=part,dependency_ids=list(batch_deps),supplied=terms))
                for identifier in bindings:
                    binding=deepcopy(part)
                    binding.update(review_component='binding',review_target_ids=[identifier],comparison_candidate_ids=sorted(terms.keys()-{identifier}))
                    result.append(dict(key=key+':binding:'+identifier,bundle_key=key,context=binding,dependency_ids=list(batch_deps),supplied=terms))
            else:
                result.append(dict(key=key,context=part,dependency_ids=list(batch_deps),supplied=terms))
    return result


def review_ids(group, revised=False):
    return group.get('revision_review_unit_ids' if revised else 'review_unit_ids',
                     [group.get('revision_review_unit_id')] if revised and group.get('revision_review_unit_id') else [] if revised else ['critic:'+group['id']])


def pending_review_units(run, group, by_id, context_map):
    if 'review_unit_ids' in group: return group['review_unit_ids']+group.get('review_context_unit_ids',[])
    builder=next((u for u in run['analysis_units'] if u['id']=='builder:'+group['id'] and u['status']=='succeeded'),None)
    if builder:
        taxonomy=identities.output(run,builder['output'])
        context,deps,supplied=review_context(run,group,taxonomy,by_id,context_map)
        batches=review_batches(context,deps,supplied,by_id,context_map)
        return list(dict.fromkeys(['critic:'+group['id']+':'+b['key'] for b in batches]+[uid for b in batches for uid in scope.context_unit_ids(run,b['context'],by_id,b['supplied'])]))
    primary=[c for c in group['candidates'] if c['id'] in group['primary_candidate_ids']]
    relations=sum('negation' in c for c in primary)
    observations=sum('classification' in c for c in primary)
    designs=0 if group.get('comparison_only') else 2*sum(c.get('statement_type') in {'rule','definition'} for c in primary)
    hierarchies=a2.models.Taxonomy.model_json_schema()['properties']['hierarchies']['maxItems']
    count=(relations+1)//2+relations+(observations+designs+hierarchies if run['recipe'].get('context_contract')=='scope-v1' else (observations+designs+hierarchies+1)//2)
    # Reservation identifiers only; no synthetic successful execution units.
    return ['critic:'+group['id']+':reserved:'+str(n) for n in range(count)]+(
        ['context:'+group['id']+':reserved:'+str(n) for n in range((observations+designs)*(2 if run['recipe'].get('context_applicability_contract')=='scoped-v1' else 1))] if run['recipe'].get('source_context_contract')=='independent-v1' else [])


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
        for field in ('meaning_dependency_hashes','role_source_hashes'):
            result[field]={i:h for o in outputs for i,h in o.get(field,{}).items()}
    return result


def focused_reviews(service,run,group,context,deps,supplied,by_id,context_map,index=None,blocks=None,revised=False,revision_key=None):
    batches=review_batches(context,deps,supplied,by_id,context_map)
    prefix=group['id']+(':revision1:review'+(':'+revision_key if revision_key else '') if revised else '')
    field='revision_review_unit_ids' if revised else 'review_unit_ids'
    group['review_context_unit_ids']=list(dict.fromkeys(group.get('review_context_unit_ids',[])+[uid for b in batches for uid in scope.context_unit_ids(run,b['context'],by_id,b['supplied'])]))
    group[field]=list(dict.fromkeys((group.get(field,[]) if revision_key else [])+['critic:'+prefix+':'+b['key'] for b in batches]))
    a2.save(service,run)
    outputs=[]
    for batch in batches:
        if a2.cancelled(service,run): break
        key=prefix+':'+batch['key']
        if batch.get('bundle_key'): batch['context']['review_bundle_id']=prefix+':'+batch['bundle_key']
        output=a2.call(service,run,'critic',key,batch['context'],batch['dependency_ids'],by_id,batch['supplied'])
        group['review_context_unit_ids']=list(dict.fromkeys([i for i in group['review_context_unit_ids'] if ':apply-pending:' not in i]+[uid for b in batches for uid in scope.context_unit_ids(run,b['context'],by_id,b['supplied'])]))
        if output is None: continue
        outputs.append(dict(unit_id='critic:'+key,**output))
        if not revised: a2.apply_actions(service,run,index,blocks,'critic',key,output)
        if not output.get('review_component'): a2.queue_recovery(run,output,group,by_id)
        if revised and any(a['action']!='finish' for a in output.get('actions', [])):
            group['revision_deferrals'].extend(dict(candidate_ref=i,reason='수정 후 Critic의 추가 도구 요청 미처리; 사람 검수로 보류') for i in batch['context']['review_target_ids'])
    complete=reviews.complete_reviews(outputs)
    for output in complete:
        if output.get('review_component')=='complete': a2.queue_recovery(run,output,group,by_id)
    return combined_review(complete) if len(outputs)==len(batches) and complete else None


def binding_repairs(group,review,taxonomy,candidates):
    valid=reviews.valid_ids(review,candidates)
    failed={i for e in taxonomy.get('binding_errors',[]) for i in e['candidate_ids']}
    return {c['candidate_ref'] for c in review.get('relation_checks',[]) if c['judgment']=='supported'
        and c['candidate_ref'] in failed & set(group['primary_candidate_ids'])
        and valid is not None and c['candidate_ref'] in valid}


def binding_after_revision(review, record, candidates):
    """Only a current, preserved source revision can open its one binding repair."""
    if not review: return False
    identifier=record['candidate_id'];current=candidates.get(identifier,{})
    valid=reviews.valid_ids(review,candidates)
    if valid is None or identifier not in valid or reviews.fingerprint(current)!=reviews.fingerprint(record['after']): return False
    checks=[c for c in review.get('relation_checks',[]) if c['candidate_ref']==identifier]
    if len(checks)!=1: return False
    check=checks[0]
    if check['judgment']!='supported' or not check.get('correction_complete') or not current.get('revision_basis_hash') or check.get('preservation_basis_hash')!=current['revision_basis_hash']: return False
    if current.get('source_relation'): return 'refuted' in check.get('binding_checks',{}).values()
    return bool(record['before'].get('source_relation') and current.get('endpoint_mode')=='source_text')


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
    target_ids.update(c['candidate_ref'] for c in review.get('grounded_repairs',[]) if c['cause']=='content_error')
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
    binding_ids.update(binding_repairs(group,review,taxonomy,candidates)-target_ids)
    binding_ids.update(c['candidate_ref'] for c in review.get('requirement_binding_checks',[])
        if c['judgment']=='refuted' and c.get('repair_source') in {'requirements','grounded_requirements'}
        and c['candidate_ref'] in editable and (valid is None or c['candidate_ref'] in valid)
        and candidates[c['candidate_ref']].get('source_relation') and c['candidate_ref'] not in target_ids)
    # Persist the actual target/unit correspondence once, including across cancellation.
    plan=group.setdefault('correction_plan', [dict(candidate_id=i,stage=stage,
        key=group['id']+(':'+('revision1' if stage=='revision' else 'binding1')+':'+i))
        for stage,ids in [('revision',target_ids),('builder',binding_ids)] for i in sorted(ids)])
    if not plan: return
    if not run['recipe']['budgets']['revisions']:
        group['revision_deferrals'].extend(dict(candidate_ref=p['candidate_id'],reason='수정 예산 0; 사람 검수로 보류') for p in plan)
        return
    units={u['id']:u for u in run['analysis_units']}
    history=[];extra=[];all_deps=set();provided=[];followup_reviews={}
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
        effective.update({h['candidate_id']:identities.history_view(run,h) for h in history})
        effective.update({c['id']:c for c in extra})
        effective.update({h['id']:h for h in effective_hierarchies})
        target_review=review;target_issues=issues
        if p.get('after_revision'):
            completed=followup_reviews.get(p['after_revision'])
            if not completed or not binding_after_revision(*completed,effective):
                group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='내용 수정의 현재 명제·정상 보존 재검수 미확정; 유형 재연결 보류'))
                continue
            target_review=completed[0];target_issues=target_review['issues']
        # Full dependencies validate cross-target hierarchy/endpoint consistency after each success.
        context,deps,supplied=context_for(list(effective.values()),by_id,context_map)
        focused=stage=='revision' and 'classification' in effective[identifier] and run['recipe'].get('revision_context_contract')=='target-source-v1'
        if focused:
            target=effective[identifier]
            source_ids=list(dict.fromkeys(target.get('source_relation_ids', []) +
                ([target['role_basis']['relation_ref']] if target.get('role_basis') else [])))
            natural=[dict(deepcopy(effective[i].get('source_relation') or effective[i]),id=i)
                for i in source_ids if i in effective and i!=identifier]
            # Keep the source snapshot in target; never promote a stale snapshot to a current supplied ID.
            context,_,supplied=context_for([target]+natural,by_id,context_map)
            if target.get('role_source'):
                source_context,source_deps,_=context_for([target['role_source']],by_id,context_map)
                context['blocks'] += [b for b in source_context['blocks'] if b not in context['blocks']]
                deps=sorted(set(deps)|set(source_deps))
            context['omitted_comparison_candidate_ids']=sorted(effective.keys()-supplied.keys())
        checks=[c for field in ('relation_checks','observation_checks','requirement_binding_checks','grounded_repairs') for c in target_review.get(field, []) if c['candidate_ref']==identifier]
        selected_issues=[i for i in target_issues if not i.get('candidate_ref') or i['candidate_ref']==identifier]
        extra_ids=[e for i in selected_issues for f in ('evidence_ids','counter_evidence_ids') for e in i.get(f, [])]
        extra_ids += [r['evidence_id'] for c in checks for r in c.get('evidence_refs', [])]
        if focused:
            refs=[r for item in selected_issues+checks for field in ('evidence_refs','counter_evidence_refs') for r in item.get(field, [])]
            extra_ids=list(dict.fromkeys(extra_ids+[r['block_id'] for r in refs]))
            evidence=[dict(id=i,evidence_ids=[i],evidence_refs=[r for r in refs if r['block_id']==i and r.get('span')]) for i in extra_ids]
            raw=context_for(evidence,by_id,context_map)[0]['blocks']
            provided_views=segments.originals(context)
            context['blocks'] += [b for b in raw if not any(v['ref']==b['ref'] and
                v.get('span',[0,len(v['text'])])[0]<=b.get('span',[0,len(b['text'])])[0] and
                b.get('span',[0,len(b['text'])])[1]<=v.get('span',[0,len(v['text'])])[1] for v in provided_views)]
        else:
            raw=a2.packet(list(dict.fromkeys(extra_ids)),by_id,context_map)
            context['blocks'] += [b for b in raw if b['ref'] not in a2.raw_refs(context)]
        deps=sorted(set(deps) | {b['ref'] for b in raw})
        if stage=='revision':
            for field in ('unapproved_observations','unapproved_relations','reviewed_base'): context.pop(field)
            context.update(target_ids=[identifier],targets=[effective[identifier]],
                evidence_only_ids=[identifier] if identifier in evidence_only else [],
                source_change_ids=[identifier] if effective[identifier].get('source_relation') and identifier not in evidence_only else [],
                comparison_candidates=[c for i,c in supplied.items() if i!=identifier],issues=selected_issues,
                relation_checks=[c for c in checks if 'negation' in effective[identifier]],
                observation_checks=[c for c in checks if 'classification' in effective[identifier]])
            if run['recipe'].get('claim_review_contract')=='claims-v1':
                context.update(claims.revision_context(checks,reviews.fingerprint(effective[identifier])))
                context['required_meanings']=[m for c in checks for m in c.get('definition_completeness',{}).get('required_meanings',[])]
        else:
            original=effective[identifier]
            supplied[identifier]=deepcopy(original.get('source_relation') or original)
            context.update(unapproved_relations=[supplied[identifier]],design_relation_ids=[identifier],
                binding_before=original,parent_group_id=group['id'],binding_checks=checks,
                previous_binding_errors=[deepcopy(e) for e in taxonomy.get('binding_errors',[]) if identifier in e['candidate_ids']])
        if run['recipe'].get('context_contract')=='scope-v1':
            context['preservation_basis']=scope.preservation_basis(effective[identifier],checks)
            context['required_context']=scope.required_context(effective[identifier],checks)
        grounded=[c for c in checks if c.get('repair_source')=='grounded_requirements']
        if grounded:
            context['grounded_repairs']=deepcopy(grounded)
            context['preservation_basis']=[m for c in grounded for m in c['preservation_basis']]
            context['required_context']=[m for c in grounded for m in c['required_context']]
        omitted=[];term_omissions=[]
        for critic in [u for u in run['analysis_units'] if u['id'] in review_ids(group) and u['status']=='succeeded']:
            requested=[i for r in critic.get('tool_results', []) for i in r.get('block_ids', [])]
            deps=sorted(set(deps) | set(critic['dependency_ids']))
            context,deps,missing=add_retrieved(run,stage,context,deps,supplied,requested,by_id,context_map);omitted.extend(missing)
            context,deps,supplied,missing=add_terms(run,stage,context,deps,supplied,critic,by_id,context_map);term_omissions.extend(missing)
        if focused:
            context['omitted_comparison_candidate_ids']=sorted(effective.keys()-supplied.keys())
        group['omitted_revision_term_ids']=term_omissions;group['omitted_revision_context_ids']=omitted
        if run['recipe'].get('context_contract')=='scope-v1':
            context.pop('context_contract',None)
            context,deps=scope.source_context(context,deps,by_id)
        if not fits(run,stage,context,deps,supplied):
            group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='필수 원문 전체가 수정 입력 한도를 초과하여 보류',
                **input_size(run,stage,context,deps,supplied)))
            continue
        validation=dict(validation_supplied=effective) if focused else {}
        if not existing or existing['status']!='succeeded':
            # Reserve one repair and its actual review components before starting it.
            preview=[dict(candidate_id=identifier,before=effective[identifier],after=effective[identifier])]
            review_input,review_deps,review_terms=review_context(run,group,taxonomy,by_id,context_map,preview)
            batches=review_batches(review_input,review_deps,review_terms,by_id,context_map)
            count=len(batches)
            context_ids={uid for b in batches for uid in scope.context_unit_ids(run,b['context'],by_id,b['supplied'])}
            context_count=len(context_ids-{u['id'] for u in run['analysis_units'] if u['status']=='succeeded' or u['stage']=='context' and u.get('attempts')})
            if stage=='builder' and run['recipe'].get('source_context_contract')=='independent-v1': context_count+=4 if run['recipe'].get('context_applicability_contract')=='scoped-v1' else 2
            if stage=='builder': count+=(2 if run['recipe'].get('context_contract')=='scope-v1' else 1)+(0 if effective[identifier].get('source_relation') else 1)
            required_calls,required_seconds=a2.requirement_reservation(run,by_id,future=True)
            stages=[stage]+['context']*context_count+['critic']*count
            needed_s=sum(run.get('role_time_estimates',{}).get(s,{}).get('estimate_s',run['recipe']['call_timeout']) for s in stages)+required_seconds
            budget=run['recipe']['budgets'];metrics=run['metrics']
            group['revision_reservation']=dict(candidate_id=identifier,pending_stages=stages+['requirements']*required_calls,
                model_calls=len(stages)+required_calls,estimated_model_s=needed_s)
            if budget['model_calls']-metrics['llm_calls']<len(stages)+required_calls or budget['model_seconds']-metrics['model_total_s']-metrics.get('interrupted_time_reserve_s',0)<needed_s:
                group['revision_deferrals'].append(dict(candidate_ref=identifier,reason='수정과 필수 재검수·요구 확인의 호출/시간 예산 부족; 자동 증액 없음'))
                continue
        result=a2.call(service,run,stage,key,context,deps,by_id,supplied,**validation)
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
        if result.get('history'):
            revised_taxonomy=deepcopy(taxonomy)
            revised_taxonomy['hierarchies']=effective_hierarchies
            current_group=dict(group,candidates=list({c['id']:effective.get(c['id'],c) for c in group['candidates']+extra}.values()),
                design_candidates=[effective.get(c['id'],c) for c in group['design_candidates']])
            current_extra=identities.output(run,result).get('observations',[]) if stage=='builder' else []
            context,deps,supplied=review_context(run,current_group,revised_taxonomy,by_id,context_map,result['history'],current_extra)
            deps=sorted(set(deps)|all_deps)
            context['review_scope']=deepcopy(group.get('review_scope',dict(extent='provided_only',whole_input_assessed=False)))
            context['review_search_status']=[{k:v for k,v in item.items() if k!='block_ids'} for item in group.get('critic_searches', [])]
            context,deps,omitted=add_retrieved(run,'critic',context,deps,supplied,provided,by_id,context_map)
            group['omitted_revision_review_context_ids']=omitted
            group['revision_review_status']='미검수 수정 제안; 사람이 재검수해야 함'
            updated=focused_reviews(service,run,group,context,deps,supplied,by_id,context_map,revised=True,revision_key=stage+':'+identifier)
            if updated is not None:
                group['revision_review_status']='수정 제안의 AI 재검수 저장; 사람 수락 아님'
            if stage=='revision':
                record=next(h for h in result['history'] if h['candidate_id']==identifier)
                record=dict(record,after=identities.history_view(run,record))
                followup_reviews[uid]=(updated,record)
                if binding_after_revision(updated,record,supplied) and not any(p['stage']=='builder' and p['candidate_id']==identifier for p in plan):
                    plan.append(dict(candidate_id=identifier,stage='builder',key=group['id']+':binding1:'+identifier,after_revision=uid))
                    a2.save(service,run)


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
            candidate_revision = bool(group.get('source_errors')) or bool(binding_repairs(group,review,taxonomy,supplied)) or review['needs_revision'] and (not review.get('missing_meanings') or any(i.get('candidate_ref') for i in review['issues']))
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

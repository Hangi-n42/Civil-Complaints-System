"""Bounded source -> expression -> join execution on the existing run ledger."""
from copy import deepcopy
import json

from . import discovery_meanings as meanings, discovery_profile as profile
from . import discovery_segments as segments, discovery_review as reviews, discovery_scope as scope


def phase(context):
    return context.get('meaning_phase')


def prompt(context):
    mode=phase(context)
    payload=deepcopy(context)
    for key in ('expected_source_refs','source_fingerprint','meaning_phase'):
        payload.pop(key,None)
    if mode=='grounding' and 'previous_meanings' in payload:
        payload['previous_meanings']=[{k:m[k] for k in ('meaning_key','meaning','applies_to','conditions','exceptions','time','negation','relation_kind','premise_keys','evidence_refs') if k in m} for m in payload['previous_meanings']]
    from .discovery_analysis import compact
    if 'candidates' in payload: payload['candidates']=compact(payload['candidates'])
    def references(value):
        if isinstance(value,list): return [references(v) for v in value]
        if not isinstance(value,dict): return value
        return {k:references(v) for k,v in value.items() if k not in {'quote','body','local_ref','dependency_hash','candidate_hashes'}}
    for field in ('discoveries','source_assessment','meanings','expressions','previous_meanings'):
        if field in payload: payload[field]=references(payload[field])
    return meanings.PROMPTS[mode]+'\ntext_from은 같은 블록의 큰 원문을 재사용한다. span은 원래 블록 기준 위치이다. 반드시 지정된 JSON 형식으로 응답한다.\nINPUT:\n'+json.dumps(segments.compact_text(payload),ensure_ascii=False,separators=(',',':'))


def contract(context,supplied):
    model=meanings.OUTPUTS[phase(context)];schema=model.model_json_schema()
    refs=[v['source_ref'] for v in segments.originals(context)]
    known=[m['meaning_key'] for m in context.get('source_assessment',{}).get('meanings',context.get('meanings',[]))]
    def constrain(node):
        if isinstance(node,list):
            for child in node: constrain(child)
        elif isinstance(node,dict):
            props=node.get('properties',{})
            for field in ('source_refs','examined_source_refs'):
                if field in props: props[field]['items']['enum']=refs or ['']
            if 'candidate_ref' in props: props['candidate_ref']['enum']=sorted(supplied) or ['']
            if 'meaning_key' in props: props['meaning_key']['enum']=known or ['']
            if 'preserve_keys' in props: props['preserve_keys']['items']['enum']=known or ['']
            for child in node.values(): constrain(child)
    constrain(schema)
    return model,schema,0,set()


def normalize(output,context,supplied):
    if phase(context)=='grounding':
        context=dict(context,expected_source_refs=[v['source_ref'] for v in segments.originals(context)])
        return meanings.grounding(output,context)
    if phase(context)=='representation': return meanings.representation(output,context,supplied)
    return meanings.join(output,context)


def unit(run,identifier):
    return next((u for u in run.get('analysis_units',[]) if u['id']==identifier and u['status']=='succeeded'),None)


def candidate_hash(supplied):
    return profile.digest({i:reviews.fingerprint(c) for i,c in supplied.items()})


def source_packet(run,context,by_id):
    requirement=context['requirement'];kind=requirement['kind'];qid=requirement['id']
    views=deepcopy(segments.originals(context))
    value=dict(meaning_phase='grounding',context_phase='grounding',requirement=deepcopy(requirement),
        target=dict(label=requirement.get('question',requirement.get('description','')),scope_kind='requirement',
            cq_ids=[qid] if kind=='cq' else [],scope_item_ids=[qid] if kind=='scope' else []),
        blocks=views,requirement_scope=deepcopy(context['requirement_scope']),
        discoveries=[{k:deepcopy(m[k]) for k in ('meaning','applies_to','evidence_refs','missing_source') if k in m}
            for m in context.get('source_context_proposals',[])],
        reference_availability=deepcopy(context.get('context_gaps',[])),
        input_inventory=[dict(block_id=b['id'],title=b.get('title',''),source_version_id=b['source_version_id'],parse_run_id=b['parse_run_id']) for b in by_id.values() if not run.get('analysis_block_ids') or b['id'] in run['analysis_block_ids']])
    # Discovery suggestions are hypotheses. Candidate assertions and previous verdicts never enter this packet.
    value['source_fingerprint']=profile.digest([value,[(v['ref'],by_id[v['ref']]['source_version_id'],by_id[v['ref']]['parse_run_id']) for v in views]])
    return value


def descriptor(mode,key,context,deps,supplied=None,ready=True):
    stage='context' if mode=='grounding' else 'requirements'
    return dict(mode=mode,stage=stage,key=key,id=stage+':'+key,context=context,deps=deps,supplied=supplied or {},ready=ready)


def packet_descriptors(run,result,kind,q,by_id,cm):
    from . import discovery_requirements as req, discovery_synthesis as synthesis
    groups=run.get('frontier',[])
    prepared=[req.packet(run,result,kind,q,by_id,cm,[g]) for g in groups] if len(groups)>1 else [req.packet(run,result,kind,q,by_id,cm)]
    records=[];grounds=[];representations=[];all_supplied={};seen=set()
    for context,deps,supplied in prepared:
        src=source_packet(run,context,by_id)
        fingerprint=src['source_fingerprint']
        if fingerprint in seen: continue
        seen.add(fingerprint)
        key='grounding:'+kind+':'+q['id']+':'+fingerprint
        g=descriptor('grounding',key,src,deps);records.append(g)
        current=unit(run,g['id'])
        # A single source challenge per immutable source packet; old receipts remain readable.
        candidates=[u for u in run.get('analysis_units',[]) if u.get('grounding_base_id')==g['id'] and u['status']=='succeeded']
        if candidates: current=candidates[-1]
        if current: grounds.append(current)
        source_id=current['id'] if current else g['id']
        current_source=deepcopy(current['output']) if current else dict(meanings=[])
        receipt=dict(unit_id=source_id,assessment_hash=current_source.get('assessment_hash'))
        representation=dict(meaning_phase='representation',requirement=context['requirement'],
            blocks=deepcopy(segments.originals(context)),source_assessment=current_source,source_receipt=receipt,
            candidates=[{k:deepcopy(c[k]) for k in ('id','label','classification','definition','subject','predicate','object','conditions','exceptions','time','negation','role_source','source_relation','child_ref','parent_ref','relation','definition_mode') if k in c} for c in supplied.values()])
        rkey='representation:'+source_id+':'+candidate_hash(supplied)
        r=descriptor('representation',rkey,representation,deps,supplied,ready=current is not None)
        records.append(r)
        saved=unit(run,r['id'])
        if saved: representations.append(saved)
        all_supplied.update(supplied)
    # Join only the actual meaning addresses and their selected current fields, not all source/candidate JSON again.
    ms={m['meaning_key']:m for g in grounds for m in g['output']['meanings']}
    expressions=[dict(deepcopy(c),representation_unit_id=r['id']) for r in representations for c in r['output']['checks']]
    blocks=[]
    for m in ms.values():
        for e in m.get('evidence_refs',[]):
            v=dict(ref=e['block_id'],span=e['span'],text=by_id[e['block_id']]['text'][slice(*e['span'])])
            if v not in blocks: blocks.append(v)
    locations=[]
    for c in expressions:
        for loc in c['locations']:
            locations.append(dict(loc,value=deepcopy(all_supplied[loc['candidate_ref']].get(loc['field']))))
    join_context=dict(meaning_phase='join',requirement=dict(kind=kind,**q),meanings=list(ms.values()),
        expressions=expressions,locations=locations,blocks=blocks,
        coverage=[dict(group_id=g['id'],block_ids=g['block_ids'],status=g.get('status'),analysis_grounded=g.get('analysis_grounded',False)) for g in run['frontier']],
        source_receipts=[dict(unit_id=g['id'],assessment_hash=g['output']['assessment_hash']) for g in grounds])
    representation_ids=[d['id'] for d in records if d['mode']=='representation']
    join_key='join:'+kind+':'+q['id']+':'+profile.digest([representation_ids,join_context['coverage']])
    records.append(descriptor('join',join_key,join_context,sorted({v['ref'] for v in blocks}),all_supplied,
        ready=len(representations)==len(seen) and bool(ms)))
    return records


def plan(run,result,by_id):
    cm=profile.contexts(list(by_id.values()))
    return [d for kind,items in [('cq',run['cqs']),('scope',run['scope_items'])] for q in items
        for d in packet_descriptors(run,result,kind,q,by_id,cm)]


def pending_calls(run,by_id,*,future=False,excluding=None):
    from . import discovery_analysis as a2
    snapshot=deepcopy(run);a2.finish(snapshot,list(by_id.values()),set(by_id))
    attempted={u['id'] for u in run.get('analysis_units',[]) if u.get('attempts') or u['status'] in {'succeeded','failed'}}
    pending={d['id']:d['stage'] for d in plan(run,snapshot['result'],by_id) if d['id'] not in attempted and d['id']!=excluding}
    if future:
        for kind,items in [('cq',run['cqs']),('scope',run['scope_items'])]:
            for q in items:
                for mode in ('representation','join'):
                    pending.setdefault('requirements:after-repair:'+mode+':'+kind+':'+q['id'],'requirements')
    return pending


def compatible(m,c,run):
    action=c['action']
    cause={'maintain':'fulfilled','not_applicable':'fulfilled','refutation':'refuted','gap':'source_absent','recover':'extraction_missing','correct':'content_error','refresh':'unverified'}[action]
    if action=='correct' and set(c['repair_fields'])<={'subject','object'}: cause='endpoint'
    judgment='supported' if action in {'maintain','not_applicable','refutation'} else 'refuted' if action in {'recover','correct'} else 'unknown'
    recovery_ids=[r['id'] for r in run.get('recovery_requests',[]) if m['meaning_key'] in r.get('meaning_keys',[])]
    return dict(deepcopy(m),locations=deepcopy(c['locations']),action=action,cause=cause,judgment=judgment,
        role=c['role'],candidate_ref=c['locations'][0]['candidate_ref'] if c['locations'] else '',
        endpoint_fields=c['repair_fields'] if cause=='endpoint' else [],repair_fields=c['repair_fields'],preserve_keys=c['preserve_keys'],
        candidate_hashes=c['candidate_hashes'],source_receipt=c['source_receipt'],recovery_ids=recovery_ids,reason=c['reason'])


def saved(run,result,by_id,available):
    output=[];cm=profile.contexts(list(by_id.values()))
    for kind,items in [('cq',run['cqs']),('scope',run['scope_items'])]:
        for q in items:
            ds=packet_descriptors(run,result,kind,q,by_id,cm);parts=[];checks=[];pending=[]
            for d in ds:
                u=unit(run,d['id'])
                if not u or not set(u.get('dependency_ids',[]))<=available or not d['ready']:
                    pending.append(d['id']);continue
                if d['mode']=='representation':
                    known={m['meaning_key']:m for m in d['context']['source_assessment']['meanings']}
                    checks.extend(compatible(known[c['meaning_key']],c,run) for c in u['output']['checks'])
                parts.append(dict(unit_id=u['id'],**deepcopy(u['output'])))
            joins=[p for p in parts if 'connections' in p]
            challenged={c['meaning_key'] for p in parts for c in p.get('source_challenges',[])}
            for c in checks:
                if c['meaning_key'] in challenged: c.update(judgment='unknown',cause='unverified',action='refresh')
            join_ok=bool(joins) and all(c['premises_complete'] and c['scope_consistent'] and c['expression_consistent'] for j in joins for c in j['connections'])
            values=[c['judgment'] for c in checks]+(['unknown'] if pending or not join_ok else [])
            from .discovery_claims import aggregate
            output.append(dict(requirement_id=q['id'],requirement_kind=kind,judgment=aggregate(values) if values else 'unknown',
                meanings=checks,parts=parts,pending_units=pending,join_assessments=joins,
                reason='근거·표현·문서 간 연결 현재 판정 대조'+('; 미완료 단위/연결 있음' if pending or not join_ok else ''),
                resolved_recovery_ids=sorted({r for c in checks if c['judgment']=='supported' for r in c['recovery_ids']})))
    return output


def authorized(run,request,by_id):
    """The exact current plan must still contain the receipt that authorized recovery."""
    from . import discovery_analysis as a2
    snapshot=deepcopy(run);a2.finish(snapshot,list(by_id.values()),set(by_id))
    expected=next((d for d in plan(run,snapshot['result'],by_id) if d['id']==request.get('representation_unit_id') and d['ready']),None)
    receipt=request.get('source_receipt')
    if not expected or expected['context']['source_receipt']!=receipt: return False
    expression=unit(run,expected['id'])
    if not expression or expression['output'].get('source_receipt')!=receipt or expression['output'].get('source_challenges'): return False
    return bool(request.get('meaning_keys')) and all(any(c['meaning_key']==k and c['action']=='recover'
        for c in expression['output']['checks']) for k in request['meaning_keys'])


def challenge(service,run,d,output,by_id):
    from . import discovery_analysis as a2
    requests=output.get('source_challenges',[])
    if not requests: return False
    receipts=[d['context']['source_receipt']] if d['mode']=='representation' else d['context']['source_receipts']
    changed=False
    for receipt in receipts:
        original=unit(run,receipt['unit_id'])
        keys={m['meaning_key'] for m in original['output']['meanings']}
        selected=[c for c in requests if c['meaning_key'] in keys]
        if not selected: continue
        base=original.get('grounding_base_id',original['id'])
        if any(u.get('grounding_base_id')==base for u in run.get('analysis_units',[])): continue
        ctx=deepcopy(original['grounding_context'])
        ctx['previous_meanings']=deepcopy(original['output']['meanings'])
        for c in selected:
            for e in c.get('evidence_refs',[]):
                view=dict(ref=e['block_id'],span=e['span'],text=by_id[e['block_id']]['text'][slice(*e['span'])])
                if view not in ctx['blocks']: ctx['blocks'].append(view)
        ctx['source_challenges']=[{k:c[k] for k in ('meaning_key','reason','proposed_meaning','evidence_refs')} for c in selected]
        ctx['source_fingerprint']=profile.digest([ctx['source_fingerprint'],ctx['source_challenges']])
        key='challenge:'+base+':'+profile.digest(ctx['source_challenges'])
        result=a2.call(service,run,'context',key,ctx,sorted({v['ref'] for v in ctx['blocks']}),by_id,{})
        created=next((u for u in run.get('analysis_units',[]) if u['id']=='context:'+key),None)
        if created:
            created['grounding_base_id']=base;created['grounding_context']=ctx
            a2.save(service,run)
        changed |= result is not None
    return changed


def route(service,run,descriptor,output,by_id,cm,result):
    from . import discovery_analysis as a2, discovery_synthesis as synthesis
    source=descriptor['context']['source_assessment']
    known={m['meaning_key']:m for m in source['meanings']}
    checks={c['meaning_key']:c for c in output['checks']}
    challenged={c['meaning_key'] for c in output['source_challenges']}
    corrected=False
    for key,c in checks.items():
        if key in challenged or c['action'] not in {'recover','correct'}: continue
        m=compatible(known[key],c,run)
        fields=descriptor['context']['requirement'];qid=fields['id'];kind=fields['kind']
        owners=[g['id'] for g in run['frontier'] if any(e['block_id'] in g['block_ids'] for e in m.get('evidence_refs',[]))]
        supplied=descriptor['supplied']
        group=dict(id='grounded:'+kind+':'+qid,analysis_group_ids=owners,candidates=list(supplied.values()),primary_candidate_ids=list(supplied))
        need=dict(m,meaning_keys=[key],representation_unit_id=descriptor['id'],generated_by_grounding=True,
            cq_ids=[qid] if kind=='cq' else [],scope_item_ids=[qid] if kind=='scope' else [],validation=[],outside_scope_reason='',
            compared_candidate_ids=list(supplied),comparison_reason=c['reason'],requirement_key=kind+':'+qid)
        previous={r['id'] for r in run.get('recovery_requests',[])}
        a2.queue_recovery(run,dict(missing_meanings=[need]) if c['action']=='recover' else dict(issues=[need]),group,by_id)
        requests=[r for r in run.get('recovery_requests',[]) if r['id'] not in previous or r.get('candidate_ref')==m['candidate_ref'] and m['candidate_ref']]
        for request in requests:
            for field in ('meaning_keys','source_receipt','representation_unit_id','generated_by_grounding','requirement_key','candidate_hashes','repair_fields','preserve_keys'):
                request[field]=deepcopy(need[field])
        if c['action']=='recover': continue
        # Each independently wrong candidate location is a bounded repair, not a whole-group rewrite.
        for cid in dict.fromkeys(p['candidate_ref'] for p in c['locations']):
            owner=next((g for g in run['candidate_groups'] if cid in g['primary_candidate_ids']+g.get('design_candidate_ids',[])),None)
            if not owner: continue
            if any(p['candidate_id']==cid for p in owner.get('correction_plan',[])): continue
            taxonomy=next((u['output'] for u in run.get('analysis_units',[]) if u['id']=='builder:'+owner['id'] and u['status']=='succeeded'),None)
            if taxonomy is None: continue
            normal=[dict(deepcopy(known[k]),locations=deepcopy(v['locations']),judgment='supported') for k,v in checks.items()
                if v['action']=='maintain' and any(loc['candidate_ref']==cid for loc in v['locations'])]
            check=dict(deepcopy(m),candidate_ref=cid,repair_source='grounded_requirements',
                assessment_unit_id=descriptor['id'],preservation_basis=normal,required_context=[deepcopy(known[key])])
            check['binding_checks']={f:'refuted' for f in c['repair_fields'] if f in {'subject','object'}}
            check['binding_reasons']={f:c['reason'] for f in check['binding_checks']}
            repair=dict(issues=[],relation_checks=[],observation_checks=[],
                grounded_repairs=[check],requirement_binding_checks=[check] if m['cause']=='endpoint' else [])
            # Keep prior meaningful corrections; append only new candidate targets.
            existing=owner.pop('correction_plan',[])
            before=len(run['analysis_units'])
            synthesis.revise(service,run,owner,repair,taxonomy,by_id,cm)
            owner['correction_plan']=existing+owner.get('correction_plan',[])
            for request in requests:
                if request.get('candidate_ref')==cid:
                    match=next((p for p in owner['correction_plan'] if p['candidate_id']==cid),None)
                    if match: request.update(unit_id=match['stage']+':'+match['key'],critic_group_id=owner['id'])
            corrected |= len(run['analysis_units'])>before
    return corrected


def assess(service,run,blocks,by_id,cm,*,rechecked=False):
    from . import discovery_analysis as a2
    corrected=False
    # A source challenge is one re-entry; a product correction is one separate bounded pass.
    for attempt in range(2):
        restart=False
        for mode in ('grounding','representation','join'):
            snapshot=deepcopy(run);a2.finish(snapshot,blocks,a2.allowed_ids(service,blocks))
            for d in plan(run,snapshot['result'],by_id):
                if d['mode']!=mode or not d['ready']: continue
                if a2.cancelled(service,run): return
                existing=next((u for u in run.get('analysis_units',[]) if u['id']==d['id']),None)
                if existing:
                    if existing['status']!='succeeded': continue
                    output=existing['output']
                else:
                    output=a2.call(service,run,d['stage'],d['key'],d['context'],d['deps'],by_id,d['supplied'])
                    stored=next((u for u in run.get('analysis_units',[]) if u['id']==d['id']),None)
                    if stored and mode=='grounding': stored['grounding_context']=deepcopy(d['context'])
                    if output is None: continue
                if mode in {'representation','join'}:
                    if challenge(service,run,d,output,by_id): restart=True;continue
                    if mode=='representation' and not rechecked:
                        corrected |= route(service,run,d,output,by_id,cm,snapshot['result'])
                a2.save(service,run)
        if not restart: break
    if corrected and not rechecked:
        assess(service,run,blocks,by_id,cm,rechecked=True)


def shared_meanings(run,context):
    views=segments.originals(context)
    selected={(q['id'],'cq') for q in run.get('cqs',[])} | {(q['id'],'scope') for q in run.get('scope_items',[])}
    targets=[c for field in ('targets','unapproved_observations','unapproved_relations') for c in context.get(field,[])]
    if targets:
        selected={(i,kind) for c in targets for kind,field in [('cq','cq_ids'),('scope','scope_item_ids')] for i in c.get(field,[])}
    superseded={u['grounding_base_id'] for u in run.get('analysis_units',[]) if u.get('grounding_base_id') and u['status']=='succeeded'}
    values={}
    for u in run.get('analysis_units',[]):
        if u['status']!='succeeded' or u['id'] in superseded: continue
        for m in u.get('output',{}).get('meanings',[]):
            requirement=m.get('body',{}).get('requirement',{})
            if m.get('validation') or (requirement.get('id'),requirement.get('kind')) not in selected: continue
            refs=m.get('evidence_refs',[])
            if refs and all(any(v['ref']==e['block_id'] and v.get('span',[0,len(v['text'])])[0]<=e['span'][0] and
                    e['span'][1]<=v.get('span',[0,len(v['text'])])[1] and
                    v['text'][e['span'][0]-v.get('span',[0])[0]:e['span'][1]-v.get('span',[0])[0]]==e['quote'] for v in views) for e in refs):
                values[m['meaning_key']]=deepcopy(m)
    # These are already explicitly scoped to this correction/recovery packet by its owner.
    for m in context.get('required_context',[])+context.get('recovery_meanings',[]):
        if m.get('meaning_key') and m['meaning_key'] not in values: values[m['meaning_key']]=deepcopy(m)
    return list(values.values())

"""Source context and selected meaning locations; semantic decisions remain model reviews."""
from copy import deepcopy
import json

from . import discovery_review as reviews, discovery_segments as segments, discovery_claims as claims, discovery_design as design


def source_context(context, deps, by_id):
    context=deepcopy(context)
    if context.get('context_contract')=='scope-v1': return context, deps
    # Reuse structural segments, never expand a small quote into an unbounded block.
    views=segments.originals(context)
    requested=[]
    for view in views:
        if view.get('context_only'): continue
        block=by_id[view['ref']]; parts=segments.split(block)
        start,end=view.get('span',[0,len(view['text'])])
        matches=[n for n,p in enumerate(parts) if p['span'][0]<end and start<p['span'][1]]
        indexes={i for n in matches for i in (n-1,n,n+1) if 0<=i<len(parts)}
        for i in sorted(indexes):
            for span in [parts[i]['span'],*parts[i]['shared_spans']]:
                requested.append((block,span))
        if 'block_index' in block:
            for other in by_id.values():
                if other['source_version_id']==block['source_version_id'] and other['parse_run_id']==block['parse_run_id'] and other.get('file_id')==block.get('file_id') and abs(other.get('block_index',-10)-block['block_index'])==1:
                    edge=segments.split(other)[-1 if other['block_index']<block['block_index'] else 0]
                    requested.extend((other,span) for span in [edge['span'],*edge['shared_spans']])
    additions=[];gaps=[]
    for block,span in requested:
        if any(v['ref']==block['id'] and v.get('span',[0,len(v['text'])])[0]<=span[0] and span[1]<=v.get('span',[0,len(v['text'])])[1] for v in views+additions): continue
        if span[1]-span[0]>4000:
            # ponytail: bound adjacent context; larger prose needs explicit read/structural partition.
            gaps.append(dict(block_id=block['id'],span=span,reason='구조 문맥이 단일 입력 창을 초과; 추가 읽기/분할 필요, 충분성 미확인'))
            continue
        additions.append(dict(ref=block['id'],text=block['text'][slice(*span)],span=span,
            locator=block['locator'],title=block.get('title',''),context_only=True,analysis_target=False))
    context.setdefault('tool_originals',[]).extend(additions)
    context['context_gaps']=gaps
    context['context_contract']='scope-v1'
    return context, sorted(set(deps)|{v['ref'] for v in additions})


def locations(item, supplied):
    selected={}
    for location in item['locations']:
        identifier=location['candidate_ref'];target=supplied.get(identifier)
        if target is None or any(target.get(k) for k in ('validation','evidence_validation','outside_scope_reason','deprecated')):
            raise ValueError('충족 위치가 제공된 유효 후보 밖')
        field=location['field'];quote=location.get('quote')
        if field=='structure':
            if 'child_ref' not in target or quote: raise ValueError('구조 위치는 실제 제공 계층 ID 필요')
            if quote is None: location.update(quote='',selection_mode='whole_field')
        else:
            text=target.get(field,'')
            if field=='role_source': text=json.dumps(text,ensure_ascii=False,sort_keys=True) if isinstance(text,dict) and text else ''
            if quote is None and isinstance(text,str) and text.strip():
                quote=text;location.update(quote=text,selection_mode='whole_field')
            if not isinstance(text,str) or not quote or quote not in text:
                raise ValueError('충족 구절이 현재 후보 필드에 없음')
        pending=[identifier]
        while pending:
            i=pending.pop()
            if i in selected: continue
            if i not in supplied: raise ValueError('충족 구조의 끝점 정의 미제공')
            value=supplied[i]
            if any(value.get(k) for k in ('validation','evidence_validation','outside_scope_reason','deprecated')):
                raise ValueError('충족 구조의 끝점이 제공된 유효 후보 밖')
            selected[i]=reviews.fingerprint(value)
            links=[value[k] for k in ('child_ref','parent_ref') if k in value]
            if value.get('source_relation'): links += [value[k] for k in ('subject','object')]
            pending.extend(links)
    if item['judgment']=='supported' and not selected:
        raise ValueError('충족 판정의 현재 표현 위치 누락')
    if item['judgment']!='unknown' and not item.get('evidence_refs'):
        raise ValueError('필수 의미 지지/반박의 실제 원문 누락')
    if not item.get('evidence_refs') and not item.get('missing_source'):
        raise ValueError('필수 문맥의 원문 또는 구체 자료 공백 필요')
    return selected


def restore(check, supplied):
    assessment=check['definition_completeness']
    hashes={}
    for item in assessment['required_meanings']:
        hashes.update(locations(item,supplied))
    assessment['judgment']=claims.aggregate([assessment['judgment'],*(i['judgment'] for i in assessment['required_meanings'])])
    check['semantic_checks']['definition']=claims.aggregate([assessment['judgment'],*(i['judgment'] for i in check['claim_reviews'])])
    check['judgment']=claims.aggregate(check['semantic_checks'].values())
    failed=[i['reason'] for i in assessment['required_meanings'] if i['judgment']!='supported']
    if failed: check['reason']='; '.join(failed)
    return hashes


def preservation_basis(before, checks):
    values=[]
    for check in checks:
        for claim in check.get('claim_reviews',[]):
            if claim['judgment']=='supported':
                values.append(dict(meaning=claim['claim'],applies_to=claim['field'],evidence_refs=deepcopy(claim.get('evidence_refs',[]))))
        for item in check.get('definition_completeness',{}).get('required_meanings',[]):
            if item['judgment']=='supported': values.append({k:deepcopy(item.get(k)) for k in ('meaning','applies_to','evidence_refs')})
        if 'negation' in before:
            source=design.source_projection(before)
            for field,judgment in check.get('semantic_checks',{}).items():
                if judgment=='supported' and source.get(field):
                    values.append(dict(meaning=str(source[field]),applies_to=field,evidence_refs=deepcopy(check.get('evidence_refs',[]))))
    from .discovery_profile import digest
    return list({digest(v):dict(v,meaning_key=digest(v)) for v in values}.values())


def revision_record(before, after, reason, context):
    """Both source revisions and binding repairs carry the same comparison receipt."""
    from .discovery_profile import digest
    context=context or {}
    checks=context.get('observation_checks',[])+context.get('relation_checks',[])+context.get('binding_checks',[])
    basis=deepcopy(context['preservation_basis']) if 'preservation_basis' in context else preservation_basis(before,checks)
    needed=deepcopy(context['required_context']) if 'required_context' in context else required_context(before,checks)
    after['revision_basis_hash']=digest([before,basis,needed])
    return dict(candidate_id=before['id'],before=deepcopy(before),after=deepcopy(after),reason=reason,
        preservation_basis=basis,required_context=needed)


def required_context(before, checks):
    from .discovery_profile import digest
    items=list(before.get('context_needs',[]))
    items += [m for c in checks for m in c.get('definition_completeness',{}).get('required_meanings',[])]
    for check in checks:
        for item in check.get('context_checks',[]):
            if item['status']=='corrected':
                if item.get('replacement'): items.append(dict(item['replacement'],replaces_meaning_key=item['meaning_key']))
            elif item['status']!='not_applicable': items.append(item)
    values=[]
    for m in items:
        value={k:deepcopy(m.get(k,'' if k=='missing_source' else [])) for k in ('meaning','applies_to','evidence_refs','missing_source')}
        if m.get('replaces_meaning_key'): value['replaces_meaning_key']=m['replaces_meaning_key']
        values.append(dict(value,meaning_key=m.get('meaning_key') or digest(value)))
    return list({v['meaning_key']:v for v in values}.values())


def preserve(check, context, supplied):
    comparison=context.get('revision_comparisons',{}).get(check['candidate_ref']) or {}
    hashes={};outcomes={}
    source_needs=context.get('source_requirements',{}).get(check['candidate_ref'],[])
    comparison=deepcopy(comparison)
    comparison['required_context']=list({m['meaning_key']:m for m in comparison.get('required_context',[])+source_needs}.values())
    pairs=[('expected_meanings','preservation_checks')]
    if 'definition_completeness' in check: pairs.append(('required_context','context_checks'))
    for source,field in pairs:
        originals={v['meaning_key']:v for v in comparison.get(source,[])}
        expected=set(originals)
        records=check.get(field,[])
        if len(records)!=len(expected) or {v['meaning_key'] for v in records}!=expected:
            raise ValueError('수정 전 정상 의미의 직접 대조 누락/중복/범위 밖' if source=='expected_meanings' else '교정 필수 문맥의 직접 대조 누락/중복/범위 밖')
        verdicts=[]
        for item in records:
            basis=originals[item['meaning_key']]
            item.update(meaning=basis['meaning'],applies_to=basis['applies_to'])
            if item['status']=='not_applicable':
                target=supplied.get(check['candidate_ref'],{})
                requirement=context.get('requirement')
                allowed={requirement['kind']+':'+requirement['id']} if requirement else {
                    kind+':'+i for kind,key in [('cq','cq_ids'),('scope','scope_item_ids')] for i in target.get(key,[])}
                if field!='context_checks' or not item.get('requirement_refs') or not set(item['requirement_refs'])<=allowed:
                    raise ValueError('문맥 적용 제외에는 현재 요구 참조 필요; 정상 보존 의미는 제외 불가')
                if item['locations'] or item.get('replacement'): raise ValueError('문맥 적용 제외를 현재 충족/정정 의미로 표시할 수 없음')
                locations(dict(item,judgment='refuted'),supplied)  # Actual source evidence is still required.
                check.setdefault('not_applicable_context_keys',[]).append(item['meaning_key'])
                continue
            if field=='context_checks' and item['status']=='corrected':
                replacement=item.get('replacement')
                if not replacement: raise ValueError('문맥 정정에는 남는 필수 의미와 현재 판정 필요')
                hashes.update(locations(dict(item,judgment='refuted'),supplied))
                hashes.update(locations(replacement,supplied))
                verdicts.append(replacement['judgment'])
                continue
            judgment='refuted' if item['status']=='lost' else 'unknown' if item['status']=='unknown' else 'supported'
            # A prior requirement or supported claim can be corrected with actual source evidence.
            location_judgment='refuted' if item['status']=='corrected' and not item['locations'] else judgment
            hashes.update(locations(dict(item,judgment=location_judgment),supplied))
            verdicts.append(judgment)
        outcomes[field]=claims.aggregate(verdicts) if verdicts else 'supported'
    if context.get('revision_comparisons',{}).get(check['candidate_ref']):
        check['preservation_basis_hash']=supplied[check['candidate_ref']].get('revision_basis_hash')
        if not check['preservation_basis_hash']: raise ValueError('수정 전후 비교 지문 누락')
    if context.get('revision_comparisons',{}).get(check['candidate_ref']) or source_needs:
        check['preservation_judgment']=outcomes['preservation_checks']
        if 'context_checks' in outcomes: check['required_context_judgment']=outcomes['context_checks']
        check['judgment']=claims.aggregate([check['judgment'],*outcomes.values()])
        check['correction_complete']=check['judgment']=='supported'
        if any(v!='supported' for v in outcomes.values()):
            check['reason']='; '.join(v['replacement']['reason'] if v.get('replacement') else v['reason'] for _,field in pairs for v in check.get(field,[]) if v['status'] in {'lost','unknown'} or (v.get('replacement') or {}).get('judgment') in {'refuted','unknown'})
    if context.get('applicability_pending'):
        check['judgment']=claims.aggregate([check['judgment'],'unknown'])
        check['correction_complete']=False
    if context.get('applicability_receipts'): check['applicability_receipts']=deepcopy(context['applicability_receipts'])
    return hashes


def discovery_requests(run,context,by_id,supplied):
    """Candidate definitions/verdicts never enter source-only discovery."""
    if run['recipe'].get('source_context_contract')!='independent-v1': return []
    from .discovery_profile import digest
    from . import discovery_analysis as a2, discovery_models as models
    views=[]
    for v in segments.originals(context):
        b=by_id[v['ref']]
        span=[0,len(b['text'])] if len(b['text'])<=4000 else v.get('span',[0,len(v['text'])])
        view=dict(ref=b['id'],text=b['text'][slice(*span)],span=span,locator=b['locator'])
        if view not in views: views.append(view)
    views.sort(key=lambda v:(v['ref'],v['span']))
    sources=[(v,by_id[v['ref']]['source_version_id'],by_id[v['ref']]['parse_run_id']) for v in views]
    requests=[]
    for identifier in context.get('review_target_ids',[]):
        c=supplied[identifier]
        if 'classification' not in c: continue
        target=dict(label=c['label'],cq_ids=c.get('cq_ids',[]),scope_item_ids=c.get('scope_item_ids',[]),
            source_anchors=[dict(block_id=r['block_id'],span=r['span']) for r in c.get('evidence_refs',[]) if r.get('span')])
        if c.get('role_source'):
            target['source_role']={k:deepcopy(c['role_source'][k]) for k in ('subject','predicate','object','conditions','exceptions','time') if k in c['role_source']}
            target['role_endpoint']=(c.get('role_basis') or {}).get('endpoint')
        selected=views  # Keep supplied supplemental text, including potentially relevant effective dates.
        packet=dict(target=target,blocks=deepcopy(selected),context_contract='scope-v1')
        deps=sorted({v['ref'] for v in selected})
        _,prompt=a2.make_prompt(run,'context',packet,deps,{})
        key=digest([{k:v for k,v in target.items() if k!='source_anchors'},prompt,models.ContextDiscovery.model_json_schema(),run.get('model_identity',{}).get('review'),
            run['recipe'].get('num_predict'),sources])
        requests.append((identifier,key,packet,deps))
    return requests


def discover(service,run,context,by_id,supplied):
    from . import discovery_analysis as a2
    context=deepcopy(context);context.update(source_requirements={},applicability_receipts=[],applicability_pending=[])
    for identifier,key,packet,deps in discovery_requests(run,context,by_id,supplied):
        old=next((u for u in run['analysis_units'] if u['id']=='context:'+key),None)
        if old and old.get('attempts') and old['status']!='succeeded':
            raise ValueError('원문 문맥 발견 미완료; 기존 후보 보존, 동일 실패 자동 재호출 없음')
        if old and old['status']=='succeeded':
            if not set(deps)<=a2.allowed_ids(service,list(by_id.values())):
                raise ValueError('사용 중단/재검토 근거가 성공 문맥에 포함됨')
            output=old['output']
        else:
            output=a2.call(service,run,'context',key,packet,deps,by_id)
        unit=next(u for u in run['analysis_units'] if u['id']=='context:'+key)
        unit['context_candidate_ids']=list(dict.fromkeys(unit.get('context_candidate_ids',[])+[identifier]))
        if output is None: raise ValueError('원문 문맥 발견 미완료; 기존 후보 보존')
        if run['recipe'].get('context_applicability_contract')=='scoped-v1':
            request=candidate_application(run,identifier,key,packet,by_id)
            required,receipt,pending=apply_context(service,run,request,by_id)
            context['source_requirements'][identifier]=required
            context.setdefault('applicability_receipts',[]).append(receipt)
            context.setdefault('applicability_pending',[]).extend(pending)
        else: context['source_requirements'][identifier]=required_context(dict(context_needs=output['context_needs']),[])
    return context


def discovered_context(run,by_id,supplied,kind=None,requirement_id=None,*,with_units=False):
    """Recompute the same source/CQ/target key before reusing a saved proposal."""
    from .discovery_profile import digest
    items=[];unit_ids=[]
    for u in run['analysis_units']:
        if u['stage']!='context' or u.get('context_phase') or u['status']!='succeeded' or not set(u['dependency_ids'])<=by_id.keys(): continue
        if kind and requirement_id not in u.get('context_target',{}).get('cq_ids' if kind=='cq' else 'scope_item_ids',[]): continue
        identifiers=[i for i in u.get('context_candidate_ids',[]) if i in supplied]
        views=[dict(ref=v['block_id'],span=v['span'],text=by_id[v['block_id']]['text'][slice(*v['span'])]) for v in u['source_ref_map'].values()]
        current=dict(blocks=views,review_target_ids=identifiers)
        if not any('context:'+key==u['id'] for _,key,_,_ in discovery_requests(run,current,by_id,supplied)): continue
        items.extend(required_context(dict(context_needs=u['output']['context_needs']),[]));unit_ids.append(u['id'])
    result=list({digest(v):v for v in items}.values())
    return (result,sorted(unit_ids)) if with_units else result


def attach_saved(run,context,by_id,supplied):
    context=deepcopy(context);context.update(source_requirements={},applicability_receipts=[],applicability_pending=[])
    for identifier,key,packet,_ in discovery_requests(run,context,by_id,supplied):
        unit=next((u for u in run['analysis_units'] if u['id']=='context:'+key and u['status']=='succeeded'),None)
        if unit:
            if run['recipe'].get('context_applicability_contract')=='scoped-v1':
                required,receipt,pending=application_receipt(run,candidate_application(run,identifier,key,packet,by_id))
                context['source_requirements'][identifier]=required
                context.setdefault('applicability_receipts',[]).append(receipt)
                context.setdefault('applicability_pending',[]).extend(pending)
            else: context['source_requirements'][identifier]=required_context(dict(context_needs=unit['output']['context_needs']),[])
    return context


def context_check_schema(schema,context,stage,supplied=None):
    """Constrain required receipt keys, never their semantic decisions."""
    template=schema.get('$defs',{}).get('ContextCheck') or schema.get('$defs',{}).get('PreservationCheck')
    if not template: return
    def bind(node,meanings,field='context_checks',allowed=()):
        keys=list(dict.fromkeys(m['meaning_key'] for m in meanings))
        item=deepcopy(schema['$defs']['ContextCheck'] if field=='context_checks' else schema['$defs']['PreservationCheck'])
        if keys: item['properties']['meaning_key']['enum']=keys
        if field=='context_checks':
            outside=deepcopy(item);corrected=deepcopy(item)
            item['properties']['status']['enum']=['maintained','lost','unknown']
            item['properties']['requirement_refs']['maxItems']=0
            item['properties']['replacement']={'type':'null'}
            corrected['properties']['status']={'type':'string','const':'corrected'}
            corrected['properties']['replacement']={'$ref':'#/$defs/RequiredMeaning'}
            corrected['properties']['requirement_refs']['maxItems']=0
            corrected['required']=list(dict.fromkeys(corrected['required']+['replacement']))
            variants=[item,corrected]
            if allowed:
                outside['properties']['status']={'type':'string','const':'not_applicable'}
                outside['properties']['requirement_refs']=dict(type='array',items=dict(type='string',enum=list(allowed)),minItems=1)
                outside['properties']['source_refs']['minItems']=1
                outside['properties']['locations']['maxItems']=0
                outside['required']=list(dict.fromkeys(outside['required']+['requirement_refs']))
                outside['properties']['replacement']={'type':'null'}
                variants.append(outside)
            item={'anyOf':variants}
        for branch in item.get('anyOf',[item]):
            branch['properties'].pop('meaning_key',None)
            branch['required']=[v for v in branch.get('required',[]) if v!='meaning_key']
        node['properties'][field]=dict(type='object',properties={k:deepcopy(item) for k in keys},required=keys,additionalProperties=False)
        node['required']=list(dict.fromkeys(node.get('required',[])+[field]))
    if stage=='requirements':
        for node in schema.get('anyOf',[schema]):
            r=context.get('requirement')
            bind(node,context.get('source_context_needs',[]),allowed=[r['kind']+':'+r['id']] if r else [])
            requests=[r['id'] for r in context.get('unassigned_recovery_targets',[])]
            if requests:
                item=deepcopy(schema['$defs']['RecoveryAttribution'])
                item['properties'].pop('request_id')
                item['required']=[k for k in item['required'] if k!='request_id']
                meaning=deepcopy(schema['$defs']['RequirementMeaning'])
                def omit_link(value):
                    if isinstance(value,list):
                        for v in value: omit_link(v)
                    elif isinstance(value,dict):
                        value.get('properties',{}).pop('recovery_ids',None)
                        if 'required' in value: value['required']=[k for k in value['required'] if k!='recovery_ids']
                        for v in value.values(): omit_link(v)
                omit_link(meaning)
                related=deepcopy(item);other=deepcopy(item)
                related['properties']['relevance']={'type':'string','const':'related'}
                related['properties']['meanings']=dict(type='array',items=meaning,minItems=1)
                related['required'].append('meanings')
                other['properties']['relevance']={'type':'string','enum':['unrelated','unknown']}
                node['properties']['recovery_attributions']=dict(type='object',properties={k:{'anyOf':[deepcopy(related),deepcopy(other)]} for k in requests},required=requests,additionalProperties=False)
                node['properties']['meanings']['minItems']=0  # Related slots are flattened before the stored min-one check.
                node['required']=list(dict.fromkeys(node.get('required',[])+['recovery_attributions']))
        return
    def bind_relations(node):
        if 'anyOf' in node:
            for branch in node['anyOf']: bind_relations(branch)
            return
        variants=[];changed=False
        for identifier in node.get('properties',{}).get('candidate_ref',{}).get('enum',[]):
            branch=deepcopy(node);branch['properties']['candidate_ref']={'type':'string','const':identifier}
            comparison=context.get('revision_comparisons',{}).get(identifier)
            if comparison is not None:
                bind(branch,comparison.get('expected_meanings',[]),'preservation_checks');changed=True
            variants.append(branch)
        if changed: node.clear();node['anyOf']=variants
    bind_relations(schema.get('$defs',{}).get('RelationCheck',{}))
    original=schema.get('$defs',{}).get('ObservationCheck')
    if not original or 'context_checks' not in original.get('properties',{}): return
    variants=[]
    for identifier in original['properties']['candidate_ref'].get('enum',[]):
        node=deepcopy(original);node['properties']['candidate_ref']={'type':'string','const':identifier}
        meanings=context.get('source_requirements',{}).get(identifier,[])+context.get('revision_comparisons',{}).get(identifier,{}).get('required_context',[])
        target=(supplied or {}).get(identifier,{})
        fields=[k for k in ('definition','conditions','exceptions','time') if isinstance(target.get(k),str) and target[k].strip()]
        if fields and 'claim_reviews' in node['properties']:
            claim=deepcopy(schema['$defs']['ClaimReview'])
            for branch in claim.get('anyOf',[claim]): branch['properties']['field']['enum']=fields
            node['properties']['claim_reviews']['items']=claim
        allowed=[kind+':'+i for kind,key in [('cq','cq_ids'),('scope','scope_item_ids')] for i in target.get(key,[])]
        bind(node,meanings,allowed=allowed)
        bind(node,context.get('revision_comparisons',{}).get(identifier,{}).get('expected_meanings',[]),'preservation_checks')
        variants.append(node)
    if variants: schema['$defs']['ObservationCheck']={'anyOf':variants}


def location_schema(schema,supplied):
    """Select current addresses; stored text is restored without generated quote copies."""
    if 'MeaningLocation' not in schema.get('$defs',{}): return
    def require_current(node):
        if isinstance(node,list):
            for child in node: require_current(child)
        elif isinstance(node,dict):
            for child in list(node.values()): require_current(child)
            props=node.get('properties',{})
            if 'locations' not in props: return
            field,value=('status','maintained') if 'status' in props else ('judgment','supported')
            declared=props.get(field,{})
            allowed=declared.get('enum',[declared['const']] if 'const' in declared else [])
            if value not in allowed: return
            if len(allowed)==1:
                props['locations']['minItems']=1
            else:
                current=deepcopy(node);other=deepcopy(node)
                current['properties'][field]={'type':'string','const':value}
                current['properties']['locations']['minItems']=1
                other['properties'][field]={'type':'string','enum':[v for v in allowed if v!=value]}
                node.clear();node['anyOf']=[current,other]
    require_current(schema)
    variants=[]
    for c in supplied:
        if any(c.get(k) for k in ('validation','evidence_validation','outside_scope_reason','deprecated')): continue
        fields=[k for k in ('definition','conditions','exceptions','time','subject','predicate','object') if isinstance(c.get(k),str) and c[k].strip()]
        if isinstance(c.get('role_source'),dict) and c['role_source']: fields.append('role_source')
        if 'child_ref' in c: fields.append('structure')
        if fields: variants.append(dict(type='object',properties=dict(candidate_ref=dict(type='string',const=c['id']),field=dict(type='string',enum=fields)),required=['candidate_ref','field'],additionalProperties=False))
    if variants: schema['$defs']['MeaningLocation']={'anyOf':variants}
    else:
        def empty(node):
            if isinstance(node,list):
                for v in node:empty(v)
            elif isinstance(node,dict):
                if 'locations' in node.get('properties',{}):node['properties']['locations']['maxItems']=0
                for v in node.values():empty(v)
        empty(schema)


def restore_receipts(output):
    """Keep stored/API receipt lists; keyed model output cannot repeat a required address."""
    for row in [output]+output.get('observation_checks',[])+output.get('relation_checks',[]):
        if not isinstance(row,dict): continue  # Per-record Critic validation reports malformed rows.
        for field,key_field in (('context_checks','meaning_key'),('preservation_checks','meaning_key'),('recovery_attributions','request_id'),('decisions','meaning_key')):
            records=row.get(field)
            if not isinstance(records,dict): continue
            if any(not isinstance(item,dict) or item.get(key_field,key)!=key for key,item in records.items()):
                continue  # Preserve the invalid map for existing per-record validation.
            if field=='recovery_attributions':
                if any(set(records)&set(m.get('recovery_ids',[])) for m in row.get('meanings',[])):
                    raise ValueError('미귀속 요청 의미는 해당 요청 답칸에서만 연결')
                for key,item in records.items():
                    meanings=item.pop('meanings',None)
                    if item.get('relevance')=='related':
                        if not isinstance(meanings,list) or not meanings: raise ValueError('관련 요청의 실제 의미 대조 누락')
                        if any(not isinstance(m,dict) or 'recovery_ids' in m for m in meanings): raise ValueError('요청 답칸의 의미에 중복 연결 기입 불가')
                        row.setdefault('meanings',[]).extend(dict(m,recovery_ids=[key]) for m in meanings)
                    elif meanings is not None: raise ValueError('미관련/미확인 요청에 복구 의미 연결 불가')
            row[field]=[dict(item,**{key_field:key}) for key,item in records.items()]


def applicability_schema(schema, context):
    item=deepcopy(schema['$defs']['ContextApplicabilityDecision'])
    item['properties'].pop('meaning_key');item['required'].remove('meaning_key')
    required=deepcopy(item);mixed=deepcopy(item);unknown=deepcopy(item)
    required['properties']['applicability']['enum']=['required','not_applicable']
    required['properties']['source_refs']['minItems']=1
    required['properties']['remaining']['maxItems']=0
    mixed['properties']['applicability']={'type':'string','const':'mixed'}
    mixed['properties']['source_refs']['minItems']=1
    mixed['properties']['remaining']['minItems']=1
    mixed['required'].append('remaining')
    unknown['properties']['applicability']={'type':'string','const':'unknown'}
    unknown['properties']['remaining']['maxItems']=0
    keys=[m['meaning_key'] for m in context['proposals']]
    for node in schema.get('anyOf',[schema]):
        node['properties']['decisions']=dict(type='object',properties={k:dict(anyOf=deepcopy([required,mixed,unknown])) for k in keys},required=keys,additionalProperties=False)


def normalize_applicability(output, context):
    from .discovery_profile import digest
    originals={m['meaning_key']:m for m in context['proposals']}
    decisions=output['decisions']
    if len(decisions)!=len(originals) or {d['meaning_key'] for d in decisions}!=set(originals):
        raise ValueError('문맥 적용성의 제안 대조 누락/중복/범위 밖')
    required=[];pending=[]
    for decision in decisions:
        key=decision['meaning_key'];status=decision['applicability']
        decision['original_proposal']=deepcopy(originals[key])
        if status!='unknown' and not decision.get('evidence_refs'): raise ValueError('문맥 적용성 판단의 실제 원문 누락')
        if status=='mixed':
            if not decision['remaining']: raise ValueError('혼합 문맥의 남는 필수 의미 누락')
            for meaning in decision['remaining']:
                if not meaning.get('evidence_refs') and not meaning['missing_source']: raise ValueError('정정 문맥 근거/자료 공백 누락')
                item=dict(deepcopy(meaning),replaces_meaning_key=key)
                required.append(dict(item,meaning_key=digest(item)))
        else:
            if decision['remaining']: raise ValueError('혼합 외 문맥에 새 필수 의미 기입 불가')
            if status=='required': required.append(deepcopy(originals[key]))
            elif status=='unknown': pending.append(key)
    output.update(required_context=required,unresolved_keys=pending)
    return output


def applicability_request(run,target,proposals,views,by_id,discovery_ids,scope_limit=None):
    from . import discovery_analysis as a2, discovery_models as models, discovery_profile as profile
    packet=dict(target=deepcopy(target),proposals=deepcopy(proposals),blocks=deepcopy(views),context_contract='scope-v1',context_phase='applicability')
    deps=sorted({v['ref'] for v in views})
    _,prompt=a2.make_prompt(run,'context',packet,deps,{})
    sources=[(v['ref'],by_id[v['ref']]['source_version_id'],by_id[v['ref']]['parse_run_id'],v.get('span'),v['text']) for v in views]
    units={u['id']:u for u in run['analysis_units']}
    stamp=profile.digest([prompt,models.ContextApplicability.model_json_schema(),run.get('model_identity',{}).get('review'),
        {k:run['recipe'].get(k) for k in ('num_ctx','num_predict','think','endpoint')},sources,scope_limit,
        [(i,units[i]['output']) for i in sorted(discovery_ids)]])
    return 'apply:'+stamp,packet,deps


def application_receipt(run,request):
    from .discovery_profile import digest
    key,_,deps=request;uid='context:'+key
    unit=next((u for u in run['analysis_units'] if u['id']==uid and u['status']=='succeeded' and set(deps)<=set(u['dependency_ids'])),None)
    if unit:
        return deepcopy(unit['output']['required_context']),dict(unit_id=uid,output_hash=digest(unit['output'])),deepcopy(unit['output']['unresolved_keys'])
    return [],dict(unit_id=uid,output_hash=None),[uid]


def apply_context(service,run,request,by_id):
    from . import discovery_analysis as a2
    key,packet,deps=request;uid='context:'+key
    old=next((u for u in run['analysis_units'] if u['id']==uid),None)
    if old and old['status']=='succeeded':
        if not set(deps)<=a2.allowed_ids(service,list(by_id.values())): raise ValueError('적용성 근거 사용 상태 변경')
    elif not old or not old.get('attempts'):
        a2.call(service,run,'context',key,packet,deps,by_id)
    return application_receipt(run,request)


def candidate_application(run,identifier,key,packet,by_id):
    unit=next((u for u in run['analysis_units'] if u['id']=='context:'+key and u['status']=='succeeded'),None)
    if not unit: return None
    target=dict(packet['target'],scope_kind='candidate')
    proposals=required_context(dict(context_needs=unit['output']['context_needs']),[])
    return applicability_request(run,target,proposals,packet['blocks'],by_id,[unit['id']])


def context_unit_ids(run,context,by_id,supplied):
    ids=[]
    for identifier,key,packet,_ in discovery_requests(run,context,by_id,supplied):
        ids.append('context:'+key)
        if run['recipe'].get('context_applicability_contract')=='scoped-v1':
            source=next((u for u in run['analysis_units'] if u['id']=='context:'+key),None)
            if source and source['status']!='succeeded' and source.get('attempts'): continue
            request=candidate_application(run,identifier,key,packet,by_id)
            ids.append('context:'+request[0] if request else 'context:apply-pending:'+key)
    return list(dict.fromkeys(ids))


def requirement_application(run,context,by_id):
    if run['recipe'].get('context_applicability_contract')!='scoped-v1' or not context.get('source_context_proposals'): return None
    requirement=context['requirement'];kind=requirement['kind'];identifier=requirement['id']
    target=dict(label=requirement.get('question',requirement.get('description',requirement.get('label',''))),scope_kind='requirement',
        cq_ids=[identifier] if kind=='cq' else [],scope_item_ids=[identifier] if kind=='scope' else [])
    views=segments.originals(context)
    return applicability_request(run,target,context['source_context_proposals'],views,by_id,context['source_discovery_unit_ids'],context['requirement_scope'])


def attach_requirement(run,context,by_id,service=None):
    context=deepcopy(context)
    request=requirement_application(run,context,by_id)
    if not request: return context
    required,receipt,pending=apply_context(service,run,request,by_id) if service else application_receipt(run,request)
    context.update(source_context_needs=required,applicability_receipts=[receipt],applicability_pending=pending)
    return context



def current_applicability_ids(run, unit, by_id, candidates, available):
    """Read-only validity of this review's saved applicability receipts."""
    output=unit.get('output') or {}
    if 'applicability_receipts' not in output: return None  # Stored legacy contract.
    valid=set(output.get('review_coverage',{}).get('valid_candidate_ids',[]))
    receipts={r['unit_id']:r for r in output['applicability_receipts']}
    for identifier in unit.get('context_candidate_ids',[]):
        matched=False
        if identifier not in candidates:
            valid.discard(identifier);continue
        for source in run['analysis_units']:
            if source['id'] not in unit.get('context_dependency_ids',[]) or source['stage']!='context' or source.get('context_phase') or source['status']!='succeeded': continue
            if not set(source['dependency_ids'])<=available: continue
            views=[dict(ref=v['block_id'],span=v['span'],text=by_id[v['block_id']]['text'][slice(*v['span'])]) for v in source['source_ref_map'].values()]
            for cid,key,packet,_ in discovery_requests(run,dict(blocks=views,review_target_ids=[identifier]),by_id,{identifier:candidates[identifier]}):
                if 'context:'+key!=source['id']: continue
                request=candidate_application(run,cid,key,packet,by_id)
                if request:
                    _,receipt,_=application_receipt(run,request)
                    matched |= bool(receipt['output_hash'] and receipts.get(receipt['unit_id'])==receipt and set(request[2])<=available)
        if not matched: valid.discard(identifier)
    return sorted(valid)

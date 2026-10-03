"""Source context and selected meaning locations; semantic decisions remain model reviews."""
from copy import deepcopy
import json

from . import discovery_review as reviews, discovery_segments as segments, discovery_claims as claims


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
        field=location['field'];quote=location['quote']
        if field=='structure':
            if 'child_ref' not in target or quote: raise ValueError('구조 위치는 실제 제공 계층 ID 필요')
        else:
            text=target.get(field,'')
            if field=='role_source': text=json.dumps(text,ensure_ascii=False,sort_keys=True)
            if not isinstance(text,str) or not quote or quote not in text:
                raise ValueError('충족 구절이 현재 후보 필드에 없음')
        pending=[identifier]
        while pending:
            i=pending.pop()
            if i in selected: continue
            if i not in supplied: raise ValueError('충족 구조의 끝점 정의 미제공')
            value=supplied[i];selected[i]=reviews.fingerprint(value)
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
            for field,judgment in check.get('semantic_checks',{}).items():
                if judgment=='supported' and before.get(field):
                    values.append(dict(meaning=str(before[field]),applies_to=field,evidence_refs=deepcopy(check.get('evidence_refs',[]))))
    from .discovery_profile import digest
    return list({digest(v):dict(v,meaning_key=digest(v)) for v in values}.values())


def preserve(check, context, supplied):
    comparison=context.get('revision_comparisons',{}).get(check['candidate_ref'])
    expected={v['meaning_key'] for v in (comparison or {}).get('expected_meanings',[])}
    records=check.get('preservation_checks',[])
    if len(records)!=len(expected) or {v['meaning_key'] for v in records}!=expected:
        raise ValueError('수정 전 정상 의미의 직접 대조 누락/중복/범위 밖')
    hashes={};verdicts=[]
    for item in records:
        judgment='refuted' if item['status']=='lost' else 'unknown' if item['status']=='unknown' else 'supported'
        # A previously supported mistake may be removed, with a new source-grounded reason.
        location_judgment='refuted' if item['status']=='corrected' and not item['locations'] else judgment
        hashes.update(locations(dict(item,judgment=location_judgment),supplied))
        verdicts.append(judgment)
    if comparison:
        check['preservation_basis_hash']=supplied[check['candidate_ref']].get('revision_basis_hash')
        if not check['preservation_basis_hash']: raise ValueError('수정 전후 비교 지문 누락')
        check['preservation_judgment']=claims.aggregate(verdicts) if verdicts else 'supported'
        check['judgment']=claims.aggregate([check['judgment'],check['preservation_judgment']])
        check['correction_complete']=check['judgment']=='supported'
        if check['preservation_judgment']!='supported':
            check['reason']='; '.join(v['reason'] for v in records if v['status'] in {'lost','unknown'})
    return hashes

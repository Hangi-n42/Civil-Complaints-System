"""K3: isolated one-shot corrections use the existing runner and current review ledger."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, ontology_changes
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import done, request, model
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare
from app.tests.unit.test_knowledge_ontology_changes import listing


def test_three_targets_keep_two_successes_when_one_fails_and_resume_does_not_retry(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;attempted=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='concept':
            value['observations'].append(dict(value['observations'][0],local_ref='o3',label='세 번째 유형'))
        if stage=='builder': value['hierarchies']=[]
        if stage=='critic':
            for check in value['observation_checks']:
                current=next(c for c in data['unapproved_observations'] if c['id']==check['candidate_ref'])
                if not current['definition'].startswith('수정 완료'):
                    check['semantic_checks']['definition']='refuted'
        if stage=='revision':
            assert len(data['target_ids'])==len(data['targets'])==1
            target=data['targets'][0];attempted.append(target['id'])
            if len(attempted)==1: raise ValueError('첫 대상의 독립 실패')
            row={k:target[k] for k in a2.models.Observation.model_fields if k in target}
            row.update(local_ref='o1',candidate_ref=target['id'],reason='근거 범위로 수정',definition='수정 완료 '+target['label'])
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=20,additional_rounds=0,revisions=1)))['run_id'])
    assert len(attempted)==len(set(attempted))==3
    assert len(run['result']['revision_history'])==2 and len(run['result']['failures'])==1
    changed={h['candidate_id'] for h in run['result']['revision_history']}
    assert set(attempted[1:])==changed
    assert all(c['definition'].startswith('수정 완료') for c in run['result']['observations'] if c['id'] in changed)
    before=deepcopy([u for u in run['analysis_units'] if u['status']=='succeeded'])
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(attempted)==3
    assert [u for u in resumed['analysis_units'] if u['status']=='succeeded']==before
    assert resumed['result']['revision_history']==run['result']['revision_history']
    cid=ontology_changes.publish(service,resumed['id'])['changeset_id']
    rows=listing(service,cid)['candidates']
    assert all(not c['origin'].get('review_errors') for c in rows if c['origin'].get('candidate_id') in changed)
    bad=next(c for c in rows if c['origin'].get('candidate_id')==attempted[0])
    assert not bad['can_accept']


@pytest.mark.parametrize('mode',['success','cancel','new_type_cancel','failed','unknown','no_budget'])
def test_binding_correction_keeps_source_id_neighbor_and_current_a3(service,model,monkeypatch,mode):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;bad_id=[];corrections=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='relation': value['relations'].append(dict(value['relations'][0],local_ref='r2',conditions='정상 이웃 조건'))
        if stage=='builder':
            value['hierarchies']=[]
            if 'binding_checks' in data:
                corrections.append(data['design_relation_ids'][0])
                assert data['design_relation_ids']==bad_id
                assert len(value['relation_bindings'])==1
                if mode=='failed': raise ValueError('연결 교정의 독립 실패 원인')
                if mode=='new_type_cancel':
                    new=dict(label='입주자 유형',classification='type',definition='원문에서 선정되는 대상',
                        support_type='design_proposal',classification_reason='원문 역할',conditions='',exceptions='',time='',
                        abstraction_level='업무 대상',review_signals=[],source_relation_ids=bad_id,design_reason='직접 대상 역할',
                        source_refs=[data['blocks'][0]['source_ref']],cq_ids=['cq1'],scope_item_ids=[],outside_scope_reason='')
                    value['relation_bindings'][0]['object_ref']=new
                if mode=='cancel': service.cancel(run['id'])
            else:
                row=value['relation_bindings'][0];bad_id.append(row['relation_ref']);row['object_ref']=row['subject_ref']
        if stage=='critic':
            bindings={b['relation_ref']:b for b in data['relation_bindings']}
            for check in value['relation_checks']:
                b=bindings[check['candidate_ref']]
                if b['subject_ref']==b['object_ref']:
                    check['binding_checks']['object']='unknown' if mode=='unknown' else 'refuted'
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    call=a2.call
    def crash_after_save(*args,**kwargs):
        result=call(*args,**kwargs)
        if args[2]=='builder' and args[4].get('binding_before') and result and len(corrections)==1 and not args[1].get('test_interrupted'):
            args[1]['test_interrupted']=True
            service.cancel(args[1]['id'])
            raise ValueError('성공 단위 저장 직후 중단')
        return result
    if mode=='new_type_cancel': monkeypatch.setattr(a2,'call',crash_after_save)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=20,additional_rounds=0,revisions=0 if mode=='no_budget' else 1)))['run_id'])
    if mode in {'unknown','no_budget'}:
        assert corrections==[] and not run['result']['revision_history']
        cid=ontology_changes.publish(service,run['id'])['changeset_id']
        assert not next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==bad_id[0])['can_accept']
        return
    if mode=='failed':
        failed=next(u for u in run['analysis_units'] if u.get('parent_group_id'))
        assert failed['status']=='failed' and '연결 교정의 독립 실패 원인' in failed['error']
        assert not run['result']['revision_history']
        resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
        assert corrections==bad_id
        assert next(u for u in resumed['analysis_units'] if u.get('parent_group_id'))==failed
        return
    if mode in {'cancel','new_type_cancel'}:
        assert run['status']=='cancelled'
        original_groups=len(run['candidate_groups'])
        run=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(run['candidate_groups'])==1
    assert corrections==bad_id and len(run['result']['revision_history'])==1,run['result']['failures']
    history=run['result']['revision_history'][0];before,after=history['before'],history['after']
    assert before['id']==after['id']==bad_id[0] and before['source_relation']==after['source_relation']
    assert before['subject']==before['object'] and after['subject']!=after['object']
    current=next(c for c in run['result']['relations'] if c['id']==bad_id[0])
    assert current['object']==after['object']
    assert not run['result']['design_pending_relation_ids'] and not run['result']['review_pending_candidate_ids']
    assert not run['result']['unresolved_recovery_requests']
    assert run['status']=='review_ready'
    builder=next(u for u in run['analysis_units'] if u['stage']=='builder' and not u.get('parent_group_id'))
    neighbor=next(c for c in builder['output']['modeled_relations'] if c['id']!=bad_id[0])
    assert next(c for c in run['result']['relations'] if c['id']==neighbor['id'])==a2.identities.view(run,neighbor)
    cid=ontology_changes.publish(service,run['id'])['changeset_id']
    row=next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==bad_id[0])
    assert not row['origin'].get('review_errors') and not row['unresolved_issues']
    assert all(c['binding_checks']['object']=='supported' for c in row['origin']['relation_checks'])
    count=len(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(model)==count and again['result']['revision_history']==run['result']['revision_history']


def test_correction_reuses_builder_tool_type_and_final_hierarchy_fingerprint(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis, discovery_review as reviews
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;seen=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='critic' and value['observation_checks'] and not any(u['stage']=='revision' and u['status']=='succeeded' for u in run['analysis_units']):
            value['observation_checks'][0]['semantic_checks']['definition']='refuted'
        if stage=='revision':
            target=data['targets'][0]
            row={k:target[k] for k in a2.models.Observation.model_fields if k in target}
            row.update(local_ref='o1',candidate_ref=target['id'],reason='정의만 보완',definition='근거 정의 보완')
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=20,additional_rounds=0,revisions=1)))['run_id'])
    revision=next(u for u in run['analysis_units'] if u['stage']=='revision')
    hierarchy=revision['output']['effective_hierarchies'][0]
    current=a2.identities.view(run,hierarchy)
    followups=[u for u in run['analysis_units'] if u['id'] in run['candidate_groups'][0]['revision_review_unit_ids']]
    assert any(reviews.valid_ids(u['output'],{current['id']:current})=={current['id']} for u in followups)
    assert any(h['id']==current['id'] for t in run['result']['taxonomy'] for h in t['hierarchies'])
    # A reused type may live only in the initial Builder tool context.
    group=deepcopy(run['candidate_groups'][0]);group.pop('correction_plan')
    relation=next(c for c in group['design_candidates'] if c.get('source_relation'))
    target=next(c for c in group['candidates'] if c['id']==relation['object'])
    group['candidates']=[c for c in group['candidates'] if c['id']!=target['id']]
    group['builder_tool_context']['terms'][target['id']]=target
    review=dict(issues=[],relation_checks=[dict(candidate_ref=relation['id'],judgment='supported',
        binding_checks=dict(subject='supported',object='refuted'),evidence_refs=[],evidence_id='')])
    review['review_coverage']=dict(valid_candidate_ids=[relation['id']],candidate_hashes={relation['id']:reviews.fingerprint(relation)})
    taxonomy=next(t for t in run['result']['taxonomy'] if t['unit_id']=='builder:'+group['id'])
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    def inspect(service,run,stage,key,context,deps,by_id,supplied):
        assert stage=='builder' and supplied[target['id']]['definition']==target['definition']
        assert any(c['id']==target['id'] for c in context['unapproved_observations'])
        seen.append(target['id'])
        raise ValueError('검사 종료')
    monkeypatch.setattr(a2,'call',inspect)
    with pytest.raises(ValueError,match='검사 종료'):
        synthesis.revise(service,run,group,review,taxonomy,by_id,a2.profile.contexts(blocks))
    assert seen==[target['id']]

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
            row.update(local_ref='o1',candidate_ref=target['id'],reason='근거 범위로 수정',definition='수정 완료 '+target['label'],direct_definition_source_refs=[data['blocks'][0]['source_ref']])
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=20,additional_rounds=0,revisions=1)))['run_id'])
    assert len(attempted)==len(set(attempted))==3
    revisions=[n for n,stage in enumerate(model) if stage=='revision']
    assert 'critic' in model[revisions[1]+1:revisions[2]]  # Complete one successful target before starting the next.
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


def test_budget_for_one_complete_target_does_not_wait_for_all_repairs(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;revise=synthesis.revise
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='builder': value['hierarchies']=[]
        if stage=='critic':
            for check in value['observation_checks']:
                candidate=next(c for c in data['unapproved_observations'] if c['id']==check['candidate_ref'])
                if not candidate['definition'].startswith('수정 완료'): check['semantic_checks']['definition']='refuted'
        if stage=='revision':
            target=data['targets'][0];row={k:v for k,v in target.items() if k in a2.models.Observation.model_fields}
            row.update(local_ref='o1',candidate_ref=target['id'],reason='오류 주장 수정',definition='수정 완료 '+target['label'],direct_definition_source_refs=[data['blocks'][0]['source_ref']])
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        result['text']=json.dumps(value,ensure_ascii=False);return result
    def limited(service,run,*args,**kwargs):
        run['recipe']['budgets']['model_calls']=run['metrics']['llm_calls']+2
        group=args[0]
        group['primary_candidate_ids']=[c['id'] for c in group['candidates'] if 'classification' in c]
        return revise(service,run,*args,**kwargs)
    monkeypatch.setattr(a2,'model_call',generated);monkeypatch.setattr(synthesis,'revise',limited)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=20,additional_rounds=0,revisions=1)))['run_id'])
    assert model[-2:]==['revision','critic']
    assert len(run['result']['revision_history'])==1
    assert run['result']['revision_deferrals']  # Other target remains explicitly unfinished.


def test_second_binding_repair_retains_type_declared_by_first_in_post_review(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    raw=deepcopy(run['result']['relations'][0]['source_relation'])
    rows=[dict(raw,id='raw1'),dict(raw,id='raw2')]
    new_type=dict(deepcopy(run['result']['observations'][0]),id='shared_new_type')
    group=dict(id='two_repairs',candidates=rows,design_candidates=[],primary_candidate_ids=['raw1','raw2'],design_candidate_ids=[],
        analysis_group_ids=[],builder_tool_context=dict(terms={}))
    review=dict(issues=[],relation_checks=[dict(candidate_ref=r['id'],judgment='supported') for r in rows])
    taxonomy=dict(hierarchies=[],binding_errors=[dict(candidate_ids=[r['id']],record=dict(subject_ref='t1'),reason='미선언 유형') for r in rows])
    run['recipe']['budgets'].update(model_calls=30,model_seconds=20000)
    events=[]
    monkeypatch.setattr(synthesis.reviews,'valid_ids',lambda *_:{'raw1','raw2'})
    monkeypatch.setattr(a2,'cancelled',lambda *_:False);monkeypatch.setattr(a2,'save',lambda *_:None)
    def called(service,current,stage,key,context,deps,by_id,supplied,**_):
        before=context['binding_before'];identifier=before['id'];events.append(('builder',identifier))
        after=dict(before,subject=new_type['id'],object=new_type['id'],source_relation=deepcopy(before),unresolved_endpoints=[])
        output=dict(observations=[deepcopy(new_type)] if identifier=='raw1' else [],modeled_relations=[after],
            history=[dict(candidate_id=identifier,before=before,after=after,reason='끝점 연결')])
        current['analysis_units'].append(dict(id='builder:'+key,stage='builder',status='succeeded',attempts=[{}],dependency_ids=deps,provided_block_ids=deps,output=output))
        current['metrics']['llm_calls']+=1
        return output
    def checked(service,current,owner,context,deps,supplied,*_,**kwargs):
        identifier=kwargs['revision_key'].split(':')[-1];events.append(('critic',identifier))
        assert new_type['id'] in supplied and supplied[new_type['id']]['definition']==new_type['definition']
        assert owner['primary_candidate_ids']==['raw1','raw2'] and owner['design_candidate_ids']==[]
        current['metrics']['llm_calls']+=1
        return {}
    monkeypatch.setattr(a2,'call',called);monkeypatch.setattr(synthesis,'focused_reviews',checked)
    synthesis.revise(service,run,group,review,taxonomy,by,cm)
    assert events==[('builder','raw1'),('critic','raw1'),('builder','raw2'),('critic','raw2')]


@pytest.mark.parametrize('raw_after',[False,True])
def test_content_revision_continues_once_to_current_binding_repair(service,model,monkeypatch,raw_after):
    from app.knowledge import discovery_synthesis as syn, discovery_scope as scope
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    original=deepcopy(run['result']['relations'][0]);identifier=original['id']
    types=deepcopy(run['result']['observations'])
    group=dict(id='after_content',candidates=[original],design_candidates=types,primary_candidate_ids=[identifier],
        design_candidate_ids=[],analysis_group_ids=[],builder_tool_context=dict(terms={}))
    review=dict(issues=[],relation_checks=[dict(candidate_ref=identifier,judgment='refuted')],
        review_coverage=dict(valid_candidate_ids=[identifier],candidate_hashes={identifier:syn.reviews.fingerprint(original)}))
    run['recipe']['context_contract']='scope-v1';run['recipe']['budgets'].update(model_calls=200,model_seconds=200000)
    calls=[];checks=[];saved={}
    monkeypatch.setattr(a2,'cancelled',lambda *_:False);monkeypatch.setattr(a2,'save',lambda *_:None)
    def called(service,current,stage,key,context,deps,by_id,supplied,**_):
        uid=stage+':'+key
        if uid in saved: return saved[uid]
        calls.append(stage)
        before=context['targets'][0] if stage=='revision' else context['binding_before']
        if stage=='revision':
            after=deepcopy(before.get('source_relation') or before) if raw_after else deepcopy(before)
            after.update(id=identifier,conditions='revised normal condition')
            if raw_after: after.update(subject='revised source actor',endpoint_mode='source_text')
        else:
            assert before['conditions']=='revised normal condition'
            assert bool(before.get('source_relation')) is (not raw_after)
            after=dict(deepcopy(before),subject=original['subject'],object=original['object'],
                source_relation=deepcopy(before.get('source_relation') or before))
        output=dict(observations=[],history=[scope.revision_record(before,after,'actual correction',context)])
        saved[uid]=output
        current['analysis_units'].append(dict(id=uid,stage=stage,status='succeeded',attempts=[{}],dependency_ids=deps,provided_block_ids=deps,output=output))
        current['metrics']['llm_calls']+=1
        return output
    def checked(service,current,owner,context,deps,supplied,*_,**kwargs):
        checks.append(kwargs['revision_key'])
        row=supplied[identifier]
        return dict(issues=[],relation_checks=[dict(candidate_ref=identifier,judgment='supported',correction_complete=True,
            preservation_basis_hash=row['revision_basis_hash'],binding_checks=dict(subject='refuted',object='supported') if row.get('source_relation') else {})],
            review_coverage=dict(valid_candidate_ids=[identifier],candidate_hashes={identifier:syn.reviews.fingerprint(row)}))
    monkeypatch.setattr(a2,'call',called);monkeypatch.setattr(syn,'focused_reviews',checked)
    syn.revise(service,run,group,review,dict(hierarchies=[]),by,cm)
    assert calls==['revision','builder']
    assert checks==['revision:'+identifier,'builder:'+identifier]
    assert [p['stage'] for p in group['correction_plan']]==['revision','builder']
    assert group['correction_plan'][1]['after_revision']=='revision:after_content:revision1:'+identifier
    syn.revise(service,run,group,review,dict(hierarchies=[]),by,cm)
    assert calls==['revision','builder'] and len(group['correction_plan'])==2


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
                assert data['binding_checks'][0]['binding_reasons']['object']=='선정되는 대상이 행위자 유형에 잘못 연결됨'
                assert data['design_relation_ids']==bad_id
                assert set(data['fixed_binding_refs'])=={'subject_ref'}
                bind_schema=next(v for v in schema['$defs']['RelationBinding']['anyOf'] if v['properties']['decision'].get('const')=='bind')
                assert bind_schema['properties']['subject_ref']['const']==data['fixed_binding_refs']['subject_ref']
                assert len(value['relation_bindings'])==1
                if mode=='failed': raise ValueError('연결 교정의 독립 실패 원인')
                if mode=='new_type_cancel':
                    from app.tests.unit.test_knowledge_discovery_roles import role_wire
                    new=role_wire(data,data['unapproved_relations'][0])
                    value['observations']=[dict(new,local_ref='t1')]
                    value['relation_bindings'][0]['object_ref']='t1'
                if mode=='cancel': service.cancel(run['id'])
            else:
                row=value['relation_bindings'][0];bad_id.append(row['relation_ref']);row['object_ref']=row['subject_ref']
        if stage=='binding':
            bindings={b['relation_ref']:b for b in data['relation_bindings']}
            for check in [value]:
                b=bindings[check['candidate_ref']]
                if b['subject_ref']==b['object_ref']:
                    check['binding_checks']['object']='unknown' if mode=='unknown' else 'refuted'
                    check['binding_reasons']['object']='선정되는 대상이 행위자 유형에 잘못 연결됨'
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
    assert before['subject']==after['subject']
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


@pytest.mark.parametrize('change_fixed',[False,True])
def test_binding_storage_rejects_fixed_endpoint_change_even_if_model_ignores_schema(service,model,monkeypatch,change_fixed):
    from app.knowledge import discovery_synthesis as syn
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    before=deepcopy(run['result']['relations'][0]);rows=run['result']['observations']
    context,deps,supplied=syn.context_for([before['source_relation'],*rows],by,cm)
    context.update(binding_before=before,design_relation_ids=[before['id']],parent_group_id='fixed_endpoint',
        fixed_binding_refs={'subject_ref':before['subject']})
    run['recipe']['budgets'].update(model_calls=30,model_seconds=20000)
    original=a2.model_call
    async def generated(prompt,schema,*args):
        result=await original(prompt,schema,*args);value=json.loads(result['text'])
        data=json.loads(prompt.split('\nINPUT:\n')[1]);fixed=data['fixed_binding_refs']['subject_ref']
        value['hierarchies']=[]
        row=value['relation_bindings'][0]
        row['subject_ref']=next(c['id'] for c in data['unapproved_observations'] if c['id']!=fixed) if change_fixed else fixed
        result['text']=json.dumps(value);return result
    monkeypatch.setattr(a2,'model_call',generated)
    output=a2.call(service,run,'builder','fixed_endpoint',context,deps,by,supplied)
    if change_fixed:
        assert output is None and '정상 끝점 변경' in run['analysis_units'][-1]['error']
    else:
        assert output and output['history'][0]['after']['subject']==before['subject']


@pytest.mark.parametrize('repair_source',['critic','requirements','both','stale'])
def test_correction_reuses_builder_tool_type_and_final_hierarchy_fingerprint(service,model,monkeypatch,repair_source):
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
            row.update(local_ref='o1',candidate_ref=target['id'],reason='정의만 보완',definition='근거 정의 보완',direct_definition_source_refs=[data['blocks'][0]['source_ref']])
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
    if repair_source=='both': review['relation_checks'][0]['binding_checks']['subject']='refuted'
    if repair_source=='stale': review['review_coverage']['candidate_hashes'][relation['id']]='stale'
    if repair_source=='requirements':
        review['requirement_binding_checks']=[dict(candidate_ref=relation['id'],judgment='refuted',repair_source='requirements',
            assessment_unit_id='requirements:q',assessment_fingerprint='current-requirement',binding_checks=dict(object='refuted'),
            binding_reasons=dict(object='현재 요구 검수의 실제 끝점 반박'),evidence_refs=[])]
        review['relation_checks'][0]['binding_checks']['object']='supported'
    taxonomy=next(t for t in run['result']['taxonomy'] if t['unit_id']=='builder:'+group['id'])
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    def inspect(service,run,stage,key,context,deps,by_id,supplied):
        assert stage=='builder' and supplied[target['id']]['definition']==target['definition']
        assert context['fixed_binding_refs']==({} if repair_source=='both' else {'subject_ref':relation['subject']})
        assert any(c['id']==target['id'] for c in context['unapproved_observations'])
        if repair_source=='requirements':
            assert context['binding_checks'][-1]['repair_source']=='requirements'
            assert review['relation_checks'][0]['binding_checks']['object']=='supported'
        seen.append(target['id'])
        raise ValueError('검사 종료')
    monkeypatch.setattr(a2,'call',inspect)
    if repair_source=='stale':
        synthesis.revise(service,run,group,review,taxonomy,by_id,a2.profile.contexts(blocks))
        assert seen==[] and group['correction_plan']==[]
        return
    with pytest.raises(ValueError,match='검사 종료'):
        synthesis.revise(service,run,group,review,taxonomy,by_id,a2.profile.contexts(blocks))
    assert seen==[target['id']]


def test_scope_binding_builder_history_survives_required_post_comparison(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as syn, discovery_scope as scope
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    run['recipe']['context_contract']='scope-v1'
    run['recipe']['budgets'].update(model_calls=30,model_seconds=20000)
    monkeypatch.setattr(a2,'recipe',lambda budget:dict(run['recipe'],budgets=budget))
    blocks=a2.load_blocks(service,run);by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    raw=deepcopy(run['result']['relations'][0]['source_relation'])
    rows=run['result']['observations']
    context,deps,supplied=syn.context_for([raw,*rows],by,cm)
    basis=scope.preservation_basis(raw,[dict(semantic_checks=dict(conditions='supported'))])
    context.update(binding_before=raw,design_relation_ids=[raw['id']],parent_group_id='repair',preservation_basis=basis,required_context=[])
    original=a2.model_call
    async def generated(*args):
        result=await original(*args);value=json.loads(result['text']);value['hierarchies']=[]
        result['text']=json.dumps(value);return result
    monkeypatch.setattr(a2,'model_call',generated)
    output=a2.call(service,run,'builder','scope_repair',context,deps,by,supplied)
    assert output is not None,run['analysis_units'][-1].get('error')
    history=output['history'][0]
    assert history['preservation_basis']==basis and history['required_context']==[]
    after=a2.identities.history_view(run,history)
    assert after['revision_basis_hash']==output['modeled_relations'][0]['revision_basis_hash']
    check=dict(candidate_ref=raw['id'],judgment='supported',preservation_checks=[dict(m,status='maintained',
        evidence_refs=[dict(block_id=deps[0])],locations=[dict(candidate_ref=raw['id'],field='conditions')],reason='정상 조건 보존') for m in basis])
    comparison=dict(revision_comparisons={raw['id']:dict(expected_meanings=basis,required_context=[])})
    scope.preserve(check,comparison,{**{c['id']:c for c in rows},raw['id']:after})
    assert check['correction_complete']


@pytest.mark.parametrize('raw_after',[False,True])
@pytest.mark.parametrize('context_limit',[49152,98304])
def test_relation_call_reaches_model_with_nested_preservation_schema(service,model,monkeypatch,raw_after,context_limit):
    from app.knowledge import discovery_synthesis as syn, discovery_scope as scope
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    run['recipe']['context_contract']='scope-v1';run['recipe']['review_evidence_contract']='semantic-checks-v1'
    # This checks schema delivery separately from the production capacity gate.
    run['recipe'].update(num_ctx=context_limit,requirements_num_ctx=context_limit)
    run['recipe']['budgets'].update(model_calls=40,model_seconds=20000)
    monkeypatch.setattr(a2,'recipe',lambda budget:dict(run['recipe'],budgets=budget))
    blocks=a2.load_blocks(service,run);by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    group=run['candidate_groups'][0]
    taxonomy=next(u['output'] for u in run['analysis_units'] if u['stage']=='builder')
    before=run['result']['relations'][0]
    basis=scope.preservation_basis(before,[dict(semantic_checks={'conditions':'supported'})])
    assert basis
    after=dict(deepcopy(before['source_relation']),id=before['id'],endpoint_mode='source_text') if raw_after else deepcopy(before)
    history=scope.revision_record(before,after,'kept meaning',dict(preservation_basis=basis,required_context=[]))
    context,deps,supplied=syn.review_context(run,group,taxonomy,by,cm,[history])
    batch=next(b for b in syn.review_batches(context,deps,supplied,by,cm) if b['context'].get('review_focus')=='relations' and b['context'].get('review_component')!='binding')
    assert batch['context'].get('review_component')==(None if raw_after else 'proposition')
    batch['context']['review_bundle_id']='wire-finalization'
    captured=[]
    async def capture(prompt,schema,stage,current,timeout):
        def leaves(node):
            if 'anyOf' in node:
                return [leaf for child in node['anyOf'] for leaf in leaves(child)]
            return [node]
        if stage=='critic':
            assert a2.models.PROPOSITION_SCOPE_RULE in prompt
            rows=leaves(schema['$defs']['RelationCheck'])
            assert rows and any(r['properties']['preservation_checks']['type']=='object' for r in rows)
            if not raw_after: assert all('binding_checks' not in r['properties'] and 'binding_reasons' not in r['properties'] for r in rows)
            assert any(r['properties']['source_refs'].get('minItems')==1 for r in rows)
        seen=set()
        def check_locations(node):
            if isinstance(node,list):
                for child in node:check_locations(child)
            elif isinstance(node,dict):
                props=node.get('properties',{})
                if 'locations' in props:
                    field,value=('status','maintained') if 'status' in props else ('judgment','supported')
                    declared=props.get(field,{})
                    allowed=declared.get('enum',[declared['const']] if 'const' in declared else [])
                    seen.update(allowed)
                    assert props['locations'].get('minItems',0)==(1 if value in allowed else 0)
                    if value in allowed:assert allowed==[value]
                for child in node.values():check_locations(child)
        check_locations(schema)
        assert {'supported','refuted','unknown','maintained','corrected','lost'}<=seen
        captured.append(schema)
        raise ValueError('test stopped after final schema reached model boundary')
    monkeypatch.setattr(a2,'model_call',capture)
    assert a2.call(service,run,'critic','wire-finalization',batch['context'],batch['dependency_ids'],by,batch['supplied']) is None
    if context_limit==49152:
        assert not captured
        assert '원문과 응답 스키마' in run['analysis_units'][-1]['error']
        assert not run['analysis_units'][-1]['attempts']
        return
    assert len(captured)==1,run['analysis_units'][-1].get('error')
    assert 'test stopped after final schema' in run['analysis_units'][-1]['error']
    from app.knowledge import discovery_requirements as requirements
    packet=requirements.packet(run,run['result'],'cq',run['cqs'][0],by,cm)
    assert a2.call(service,run,'requirements','locations-wire',packet[0],packet[1],by,packet[2]) is None
    assert len(captured)==2,run['analysis_units'][-1].get('error')

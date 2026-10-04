"""Source judgment is distinct from expression and does not certify model quality."""
from copy import deepcopy
import json

import pytest
from app.knowledge import discovery_analysis as a2, discovery_meanings as m, discovery_grounding as engine
from app.tests.unit.test_knowledge_discovery_scope import requirement_fixture


def source(status='supported', **kwargs):
    return dict(local_ref='a',meaning='조건 A이면 선정한다',applies_to='제공 업무',relation_kind='obligation',
        conditions='A',exceptions='',time='',negation='affirmed',applicability='required',source_status=status,
        evidence_refs=[dict(block_id='e',source_version_id='v',parse_run_id='p',span=[0,2],quote='주체')],
        source_refs=['s'],missing_source='',availability='provided',premise_refs=[],premises_complete=True,reason='원문 대조',supersedes='',**kwargs)


def grounded(rows):
    return m.grounding(dict(meanings=rows,examined_source_refs=['s'],reason='대조'),
        dict(requirement={'id':'q'},expected_source_refs=['s'],source_fingerprint='fixed'))


@pytest.mark.parametrize('status,assertion,expression,expected',[
    ('supported','asserted','represented','maintain'),('supported','absent','missing','recover'),
    ('supported','asserted','incorrect','correct'),('unknown','absent','missing','gap'),
    ('unknown','qualified_unknown','represented','gap'),('unknown','asserted','incorrect','correct'),
    ('refuted','absent','missing','refutation'),('refuted','asserted','incorrect','correct')])
def test_server_action_table(status,assertion,expression,expected):
    meaning=grounded([source(status)])['meanings'][0]
    assert m.action(meaning,dict(assertion=assertion,status=expression))==expected


@pytest.mark.parametrize('status',['unknown','refuted'])
def test_uncertain_premise_does_not_block_correction_of_asserted_claim(status):
    meaning=grounded([source(status)])['meanings'][0];meaning['premises_current']=False
    assert m.action(meaning,dict(assertion='asserted',status='incorrect'))=='correct'
    meaning['validation']=['순환 전제']
    assert m.action(meaning,dict(assertion='asserted',status='incorrect'))=='refresh'


def test_premise_keys_cycle_and_unknown_only_block_dependent_generation():
    first=source('unknown');second=dict(source(),local_ref='b',meaning='전제에 의존한 연결',premise_refs=['a'])
    third=dict(source(),local_ref='c',meaning='독립 의무')
    values=grounded([first,second,third])['meanings']
    assert [v['premises_current'] for v in values]==[True,False,True]
    assert m.action(values[1],dict(assertion='absent',status='missing'))=='refresh'
    assert m.action(values[2],dict(assertion='absent',status='missing'))=='recover'
    first['premise_refs']=['b'];cyclic=grounded([first,second,third])['meanings']
    assert cyclic[0]['validation'] and cyclic[1]['validation'] and not cyclic[2]['validation']
    second['premise_refs']=['outside'];assert grounded([second])['meanings'][0]['validation']


def test_unknown_does_not_require_invented_external_source_and_or_stays_compound():
    row=source('unknown');row.update(availability='ambiguous',meaning='A 또는 B이면 권한 있음')
    value=grounded([row])['meanings'][0]
    assert value['missing_source']=='' and value['premise_keys']==[]
    row['availability']='external_missing'
    with pytest.raises(ValueError,match='자료명'): grounded([row])


def test_key_changes_only_with_body_and_preserves_prior_history_on_supersession():
    original=grounded([source()]);prior=deepcopy(original)
    same=source('refuted');assert grounded([same])['meanings'][0]['meaning_key']==original['meanings'][0]['meaning_key']
    after=dict(source(),meaning='조건 B이면 선정한다',supersedes=original['meanings'][0]['meaning_key'])
    changed=m.grounding(dict(meanings=[after],examined_source_refs=['s'],reason='정정'),
        dict(requirement={'id':'q'},expected_source_refs=['s'],source_fingerprint='fixed',previous_meanings=original['meanings']))
    assert changed['meanings'][0]['meaning_key']!=original['meanings'][0]['meaning_key']
    assert original==prior


def test_candidate_free_grounding_and_plan_reserves_same_ready_keys(monkeypatch):
    req,run,result,by,cm=requirement_fixture();run['id']='fixed'
    run['recipe']['meaning_contract']=m.CONTRACT
    candidate=result['observations'][0];candidate['definition']='DO_NOT_SEND_CANDIDATE_ASSERTION'
    first=engine.plan(run,result,by)
    assert [d['mode'] for d in first]==['grounding','representation','join']
    raw=first[0]
    _,prompt=a2.make_prompt(run,raw['stage'],raw['context'],raw['deps'],{})
    assert 'DO_NOT_SEND_CANDIDATE_ASSERTION' not in prompt and not raw['supplied']
    monkeypatch.setattr(a2,'finish',lambda copy,*_:copy.update(result=deepcopy(result)))
    assert set(engine.pending_calls(run,by))=={d['id'] for d in first}
    changed=deepcopy(result);changed['observations'][0]['definition']='changed'
    second=engine.plan(run,changed,by)
    assert first[0]['id']==second[0]['id'] and first[1]['id']!=second[1]['id']
    assert all(not d['ready'] for d in first[1:])


def test_real_call_contract_restores_source_and_separates_saved_receipts(monkeypatch):
    req,run,result,by,cm=requirement_fixture();run.update(id='fixed',model_identity={},metrics=dict(llm_calls=0,model_total_s=0))
    run['recovery_requests']=[];run['recipe']['meaning_contract']=m.CONTRACT
    calls=[]
    monkeypatch.setattr(a2,'finish',lambda copy,*_:copy.update(result=deepcopy(result)))
    monkeypatch.setattr(a2,'model_identity',lambda _:{});monkeypatch.setattr(a2,'save',lambda *_:None)
    monkeypatch.setattr(a2,'cancelled',lambda *_:False);monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by))
    async def model(prompt,schema,stage,current,timeout):
        import jsonschema
        data=json.loads(prompt.split('\nINPUT:\n')[1]);calls.append(stage)
        if stage=='grounding':
            row={k:v for k,v in source().items() if k!='evidence_refs'}
            row['source_refs']=[v['source_ref'] for v in data['blocks']]
            value=dict(meanings=[row],examined_source_refs=row['source_refs'],reason='대역')
        elif 'source_assessment' in data:
            key=data['source_assessment']['meanings'][0]['meaning_key']
            value=dict(checks=[dict(meaning_key=key,status='represented',assertion='asserted',locations=[dict(candidate_ref='c',field='definition')],
                repair_fields=[],preserve_keys=[],role='concept',reason='대역')],source_challenges=[],reason='대역')
        else:
            value=dict(connections=[dict(meaning_key=r['meaning_key'],premises_complete=True,scope_consistent=True,expression_consistent=True,reason='대역') for r in data['meanings']],source_challenges=[],reason='대역')
        jsonschema.validate(value,schema)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',model)
    engine.assess(None,run,list(by.values()),by,cm)
    assert calls==['grounding','requirements','requirements'],[(u['id'],u.get('error')) for u in run['analysis_units']]
    assert all(u['status']=='succeeded' for u in run['analysis_units'])
    assert engine.saved(run,result,by,set(by))[0]['judgment']=='supported'
    original=deepcopy(run['analysis_units']);engine.assess(None,run,list(by.values()),by,cm)
    assert len(calls)==3 and original==run['analysis_units']
    result['observations'][0]['definition']='다른 표현'
    assert engine.saved(run,result,by,set(by))[0]['judgment']=='unknown'
    # No source reparse or new source call when only the candidate changes.
    engine.assess(None,run,list(by.values()),by,cm)
    assert calls==['grounding','requirements','requirements','requirements','requirements']


def receipt_fixture(monkeypatch):
    _,run,result,by,cm=requirement_fixture();run['id']='fixed';run['recipe']['meaning_contract']=m.CONTRACT
    run['recovery_requests']=[]
    monkeypatch.setattr(a2,'finish',lambda copy,*_:copy.update(result=deepcopy(result)))
    descriptor=engine.plan(run,result,by)[0]
    context=a2.segments.bind(descriptor['context'],run['id'],'ground',stable=True)
    row=source();row['source_refs']=[v['source_ref'] for v in context['blocks']]
    row.pop('evidence_refs')
    value=dict(meanings=[row],examined_source_refs=row['source_refs'],reason='대역')
    a2.segments.restore(value,by,a2.segments.originals(context))
    output=engine.normalize(value,context,{})
    run['analysis_units'].append(dict(id=descriptor['id'],stage='context',status='succeeded',output=output,
        dependency_ids=['e'],attempts=[{}],grounding_context=deepcopy(descriptor['context'])))
    expression=engine.plan(run,result,by)[1];key=output['meanings'][0]['meaning_key']
    check=dict(meaning_key=key,status='missing',assertion='absent',locations=[],repair_fields=[],preserve_keys=[],role='concept',reason='대역 누락')
    value=engine.normalize(dict(checks=[check],source_challenges=[],reason='대역'),expression['context'],expression['supplied'])
    run['analysis_units'].append(dict(id=expression['id'],stage='requirements',status='succeeded',output=value,dependency_ids=['e'],attempts=[{}]))
    request=dict(meaning_keys=[key],representation_unit_id=expression['id'],source_receipt=value['source_receipt'])
    return run,result,by,cm,expression,value,request


def test_recovery_requires_exact_current_source_scope_and_candidate_receipts(monkeypatch):
    run,result,by,_,_,_,request=receipt_fixture(monkeypatch)
    assert engine.authorized(run,request,by)
    prior=deepcopy(result);result['observations'][0]['definition']='이미 누락을 표현함'
    assert not engine.authorized(run,request,by)
    result.update(prior);by['e']['text']+='새 전제'
    assert not engine.authorized(run,request,by)
    by['e']['text']=by['e']['text'][:-4];run['cqs'][0]['question']='다른 적용 범위'
    assert not engine.authorized(run,request,by)


def test_genuine_missing_routes_to_existing_owned_recovery_queue(monkeypatch):
    run,result,by,cm,d,output,request=receipt_fixture(monkeypatch)
    engine.route(None,run,d,output,by,cm,result)
    assert len(run['recovery_requests'])==1
    recovery=run['recovery_requests'][0]
    assert recovery['role']=='concept' and recovery['owner_group_ids']==['g']
    assert recovery['source_receipt']==request['source_receipt'] and engine.authorized(run,recovery,by)
    engine.route(None,run,d,output,by,cm,result)
    assert len(run['recovery_requests'])==1


def test_shared_meanings_do_not_leak_across_requirement_or_empty_addresses(monkeypatch):
    run,result,by,_,_,_,_=receipt_fixture(monkeypatch)
    context=dict(blocks=[dict(ref='e',text=by['e']['text'])])
    assert len(engine.shared_meanings(run,context))==1
    original=deepcopy(run['analysis_units'][0]['output']['meanings'][0])
    run['analysis_units'][0]['output']['meanings'][0]['evidence_refs']=[]
    assert not engine.shared_meanings(run,context)
    run['analysis_units'][0]['output']['meanings'][0]=original
    run['cqs'][0]['id']='other'
    assert not engine.shared_meanings(run,context)


def test_challenge_only_once_preserves_old_receipt_and_normal_meanings(monkeypatch):
    run,result,by,_,d,_,_=receipt_fixture(monkeypatch)
    original=deepcopy(run['analysis_units'][0]);key=original['output']['meanings'][0]['meaning_key'];called=[]
    challenge=dict(meaning_key=key,reason='새 전제',proposed_meaning='한정된 의미',evidence_refs=original['output']['meanings'][0]['evidence_refs'])
    def call(service,current,stage,unit_key,ctx,deps,blocks,supplied):
        called.append(ctx)
        current['analysis_units'].append(dict(id=stage+':'+unit_key,status='succeeded',stage=stage,output=deepcopy(original['output'])))
        return current['analysis_units'][-1]['output']
    monkeypatch.setattr(a2,'call',call);monkeypatch.setattr(a2,'save',lambda *_:None)
    assert engine.challenge(None,run,d,dict(source_challenges=[challenge]),by)
    assert not engine.challenge(None,run,d,dict(source_challenges=[challenge]),by)
    assert len(called)==1 and run['analysis_units'][0]==original
    wire=json.loads(engine.prompt(called[0]).split('\nINPUT:\n')[1])
    assert 'source_status' not in wire['previous_meanings'][0]


def test_partial_revision_receives_current_proof_and_normal_meaning_preservation(monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    run,result,by,cm,d,output,_=receipt_fixture(monkeypatch)
    key=output['checks'][0]['meaning_key'];candidate=result['observations'][0]
    primary=d['context']['source_assessment']['meanings'][0]
    normal=dict(deepcopy(primary),meaning_key='normal',meaning='정상 역할')
    d['context']['source_assessment']['meanings'].append(normal)
    output['checks'][0].update(action='correct',status='incorrect',assertion='asserted',locations=[dict(candidate_ref='c',field='definition')],repair_fields=['definition'],preserve_keys=['normal'])
    output['checks'].append(dict(deepcopy(output['checks'][0]),meaning_key='normal',action='maintain',status='represented',repair_fields=[],preserve_keys=[]))
    run['candidate_groups']=[dict(id='owner',primary_candidate_ids=['c'],candidates=[candidate],design_candidates=[],analysis_group_ids=['g'])]
    run['analysis_units'].append(dict(id='builder:owner',stage='builder',status='succeeded',output=dict(hierarchies=[])))
    seen=[]
    def revise(service,current,owner,repair,taxonomy,blocks,contexts):
        seen.append(deepcopy(repair))
        owner['correction_plan']=[dict(candidate_id='c',stage='revision',key='owner:revision1:c')]
    monkeypatch.setattr(synthesis,'revise',revise)
    engine.route(None,run,d,output,by,cm,result)
    assert len(seen)==1
    repair=seen[0]['grounded_repairs'][0]
    assert repair['repair_fields']==['definition'] and repair['source_receipt']==output['source_receipt']
    assert repair['preservation_basis'][0]['meaning_key']=='normal'
    assert repair['required_context'][0]['meaning_key']==key
    engine.route(None,run,d,output,by,cm,result)
    assert len(seen)==1  # A saved per-candidate plan is not reset by requirements.


def test_per_frontier_source_packets_and_join_use_cross_document_addresses(monkeypatch):
    run,result,by,_,_,_,_=receipt_fixture(monkeypatch)
    by['e2']=dict(by['e'],id='e2',text='다른 문서 정의',source_version_id='v2')
    run['frontier'].append(dict(id='g2',block_ids=['e2'],segments=[],roles=['concept'],round=0))
    descriptors=engine.plan(run,result,by)
    sources=[d for d in descriptors if d['mode']=='grounding']
    assert len(sources)==2
    assert {v['ref'] for v in sources[0]['context']['blocks']}=={'e'}
    assert {v['ref'] for v in sources[1]['context']['blocks']}=={'e2'}
    assert not descriptors[-1]['ready']
    assert descriptors[-1]['context']['requirement']['id']=='q'


def test_examined_parent_covers_contained_views_but_not_unread_text():
    context=dict(requirement={'id':'q'},expected_source_refs=['parent','child'],source_fingerprint='fixed',
        blocks=[dict(ref='e',source_ref='parent',span=[0,6],text='ABCDEF'),dict(ref='e',source_ref='child',span=[1,3],text='BC')])
    output=dict(meanings=[source()],examined_source_refs=['parent'],reason='큰 원문 전체 조사')
    assert m.grounding(output,context)['meanings']
    output=dict(meanings=[source()],examined_source_refs=['child'],reason='일부만 조사')
    with pytest.raises(ValueError,match='조사 범위'): m.grounding(output,context)

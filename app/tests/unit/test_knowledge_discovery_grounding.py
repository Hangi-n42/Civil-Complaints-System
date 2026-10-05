"""Source judgment is distinct from expression and does not certify model quality."""
from copy import deepcopy
import json

import pytest
from app.knowledge import discovery_analysis as a2, discovery_meanings as m, discovery_grounding as engine
from app.tests.unit.test_knowledge_discovery_scope import requirement_fixture


def source(status='supported', **kwargs):
    return dict(statement_type='rule',judgment_kind='source_content',local_negation='',read_block_ids=[],local_ref='a',meaning='조건 A이면 선정한다',applies_to='제공 업무',relation_kind='obligation',
        conditions='A',exceptions='',time='',negation='affirmed',applicability='required',source_status=status,
        evidence_refs=[dict(block_id='e',source_version_id='v',parse_run_id='p',span=[0,2],quote='주체')],
        source_refs=['s'],missing_source='',availability='provided',premise_refs=[],premises_complete=True,reason='원문 대조',supersedes='',**kwargs)


def grounded(rows):
    return m.grounding(dict(meanings=rows,examined_source_refs=['s'],reason='대조'),
        dict(requirement={'id':'q'},expected_source_refs=['s'],source_fingerprint='fixed'))


@pytest.mark.parametrize('status,expression,expected',[
    ('supported','represented','maintain'),('supported','missing','recover'),
    ('supported','incorrect','correct'),('unknown','missing','gap'),
    ('unknown','represented','gap'),('unknown','incorrect','correct'),
    ('refuted','missing','refutation'),('refuted','incorrect','correct')])
def test_server_action_table(status,expression,expected):
    meaning=grounded([source(status)])['meanings'][0]
    assert m.action(meaning,dict(status=expression))==expected


@pytest.mark.parametrize('status',['unknown','refuted'])
def test_uncertain_premise_does_not_block_correction_of_asserted_claim(status):
    meaning=grounded([source(status)])['meanings'][0];meaning['premises_current']=False
    assert m.action(meaning,dict(status='incorrect'))=='correct'
    meaning['validation']=['순환 전제']
    assert m.action(meaning,dict(status='incorrect'))=='refresh'


def test_premise_keys_cycle_and_unknown_only_block_dependent_generation():
    first=source('unknown');second=dict(source(),local_ref='b',meaning='전제에 의존한 연결',premise_refs=['a'])
    third=dict(source(),local_ref='c',meaning='독립 의무')
    values=grounded([first,second,third])['meanings']
    assert [v['premises_current'] for v in values]==[True,False,True]
    assert m.action(values[1],dict(status='missing'))=='refresh'
    assert m.action(values[2],dict(status='missing'))=='recover'
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


@pytest.mark.parametrize('malformed',[False,True])
def test_real_call_contract_restores_source_and_separates_saved_receipts(monkeypatch,malformed):
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
            if malformed: value['meanings'].append(dict(row,local_ref='bad',meaning='검사 오류',availability='external_missing',missing_source=''))
        elif 'source_assessment' in data:
            key=data['source_assessment']['meanings'][0]['meaning_key']
            value=dict(checks={key:dict(status='represented',locations=[dict(candidate_ref='c',field='definition')],
                repair_fields=[],preserve_keys=[],role='concept',reason='대역')},source_challenges=[],reason='대역')
        else:
            value=dict(connections=[dict(meaning_key=r['meaning_key'],premises_complete=True,scope_consistent=True,expression_consistent=True,reason='대역') for r in data['meanings']],source_challenges=[],reason='대역')
        jsonschema.validate(value,schema)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',model)
    engine.assess(None,run,list(by.values()),by,cm)
    assert calls==['grounding','requirements','requirements'],[(u['id'],u.get('error')) for u in run['analysis_units']]
    assert all(u['status']=='succeeded' for u in run['analysis_units'])
    assert engine.saved(run,result,by,set(by))[0]['judgment']==('unknown' if malformed else 'supported')
    if malformed:
        assert len(run['analysis_units'][0]['output']['meanings'])==1
        assert len(run['analysis_units'][0]['output']['record_errors'])==1
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
    check=dict(meaning_key=key,status='missing',locations=[],repair_fields=[],preserve_keys=[],role='concept',reason='대역 누락')
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


@pytest.mark.parametrize('challenged_normal',[False,True])
def test_partial_revision_receives_current_proof_and_normal_meaning_preservation(monkeypatch,challenged_normal):
    from app.knowledge import discovery_synthesis as synthesis
    run,result,by,cm,d,output,_=receipt_fixture(monkeypatch)
    key=output['checks'][0]['meaning_key'];candidate=result['observations'][0]
    primary=d['context']['source_assessment']['meanings'][0]
    normal=dict(deepcopy(primary),meaning_key='normal',meaning='정상 역할')
    d['context']['source_assessment']['meanings'].append(normal)
    output['checks'][0].update(action='correct',status='incorrect',locations=[dict(candidate_ref='c',field='definition')],repair_fields=['definition'],preserve_keys=['normal'])
    output['checks'].append(dict(deepcopy(output['checks'][0]),meaning_key='normal',action='maintain',status='represented',repair_fields=[],preserve_keys=[]))
    run['candidate_groups']=[dict(id='owner',primary_candidate_ids=['c'],candidates=[candidate],design_candidates=[],analysis_group_ids=['g'])]
    run['analysis_units'].append(dict(id='builder:owner',stage='builder',status='succeeded',output=dict(hierarchies=[])))
    seen=[]
    def revise(service,current,owner,repair,taxonomy,blocks,contexts):
        seen.append(deepcopy(repair))
        owner['correction_plan']=[dict(candidate_id='c',stage='revision',key='owner:revision1:c')]
    monkeypatch.setattr(synthesis,'revise',revise)
    if challenged_normal: output['source_challenges']=[dict(meaning_key='normal')]
    engine.route(None,run,d,output,by,cm,result)
    assert len(seen)==1
    repair=seen[0]['grounded_repairs'][0]
    assert repair['repair_fields']==['definition'] and repair['source_receipt']==output['source_receipt']
    assert [m['meaning_key'] for m in repair['preservation_basis']]==([] if challenged_normal else ['normal'])
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


def test_record_isolation_preserves_independent_rows_and_failed_dependency(monkeypatch):
    run,result,by,_,_,_,_=receipt_fixture(monkeypatch)
    ctx=a2.segments.bind(engine.plan(run,result,by)[0]['context'],'fixed','g',stable=True)
    row={k:v for k,v in source().items() if k!='evidence_refs'}
    row['source_refs']=[ctx['blocks'][0]['source_ref']]
    rows=[row,dict(row,local_ref='duplicate'),dict(row,local_ref='bad',meaning='bad',negation='invalid'),
        dict(row,local_ref='badref',meaning='badref',source_refs=['outside']),
        dict(row,local_ref='dependent',meaning='dependent',premise_refs=['bad']),
        dict(row,local_ref='normal',meaning='normal')]
    output=m.records(dict(meanings=rows,examined_source_refs=[v['source_ref'] for v in ctx['blocks']],reason='대역'),ctx,{},by,'g')
    assert len(output['record_errors'])==3
    assert len(output['meanings'])==3
    assert output['meanings'][1]['validation'] and not output['meanings'][2]['validation']
    assert rows[2]['negation']=='invalid'  # raw preserved, no semantic correction


def test_malformed_challenge_blocks_only_named_meaning_and_dependents(monkeypatch):
    run,result,by,cm,d,output,request=receipt_fixture(monkeypatch)
    primary=d['context']['source_assessment']['meanings'][0]
    sibling=dict(deepcopy(primary),meaning_key='sibling',meaning='독립 정상')
    dependent=dict(deepcopy(primary),meaning_key='dependent',premise_keys=[primary['meaning_key']])
    rows=d['context']['source_assessment']['meanings'];rows.extend([sibling,dependent])
    checks=[dict(deepcopy(output['checks'][0]),meaning_key=row['meaning_key']) for row in rows]
    raw=dict(checks=[{k:v for k,v in c.items() if k in m.Expression.model_fields} for c in checks],
        source_challenges=[dict(meaning_key=primary['meaning_key'],reason='',proposed_meaning='수정',source_refs=[])],reason='대역')
    value=m.records(raw,d['context'],d['supplied'],by,d['id'])
    assert len(value['checks'])==3 and len(value['record_errors'])==1
    assert m.blocked_keys(value,rows)=={primary['meaning_key'],'dependent'}
    run['analysis_units'][-1]['output']=value
    # Inspect the current descriptor while testing the actual authorization boundary.
    monkeypatch.setattr(engine,'plan',lambda *_:[d])
    assert not engine.authorized(run,request,by)
    assert engine.authorized(run,dict(request,meaning_keys=['sibling']),by)
    engine.route(None,run,d,value,by,cm,result)
    assert [r['meaning_keys'] for r in run['recovery_requests']]==[['sibling']]


def test_bad_representation_and_join_rows_remain_pending(monkeypatch):
    run,result,by,_,d,output,_=receipt_fixture(monkeypatch)
    raw={k:v for k,v in output['checks'][0].items() if k in m.Expression.model_fields}
    raw.update(locations=[dict(candidate_ref='outside',field='definition')],)
    value=m.records(dict(checks=[raw],source_challenges=[],reason='대역'),d['context'],d['supplied'],by,d['id'])
    assert not value['checks'] and value['record_errors'] and value['pending_meaning_keys']==[raw['meaning_key']]
    context=dict(meaning_phase='join',meanings=d['context']['source_assessment']['meanings'],blocks=[])
    joined=m.records(dict(connections=[dict(meaning_key=raw['meaning_key'],premises_complete='wrong',scope_consistent=True,expression_consistent=True,reason='대역')],
        source_challenges=[],reason='대역'),context,{},by,'join')
    assert joined['record_errors'] and joined['pending_meaning_keys']==[raw['meaning_key']]


def test_refresh_uses_frozen_read_and_new_plan_without_repeating_original(monkeypatch):
    run,result,by,cm,d,_,_=receipt_fixture(monkeypatch)
    original=run['analysis_units'][0];before=deepcopy(original)
    by['e2']=dict(by['e'],id='e2',text='추가 정의 원문',source_version_id='v2',parse_run_id='p2',file_id='f2',block_index=0)
    original['grounding_context']['input_inventory'].append(dict(block_id='e2',title='동명 제목',source_version_id='v2',parse_run_id='p2'))
    row=original['output']['meanings'][0];row.update(source_status='unknown',availability='internal_unselected',read_block_ids=['e2'])
    # Use a fixed source descriptor to exercise the execution loop after an existing E.
    base=dict(id=original['id'])
    refresh=engine.refresh_descriptor(original,base['id'],by)
    reads=[];calls=[]
    monkeypatch.setattr(engine,'plan',lambda *_:[refresh])
    monkeypatch.setattr(a2,'cancelled',lambda *_:False);monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by));monkeypatch.setattr(a2,'save',lambda *_:None)
    def read(service,identifier,file_id,**kwargs):
        reads.append((identifier,file_id,kwargs));return dict(items=[by['e2']])
    monkeypatch.setattr(a2.grounding,'read',read)
    def call(service,current,stage,key,context,deps,blocks,supplied):
        calls.append(context)
        out=deepcopy(original['output']);out['meanings'][0].update(availability='provided',read_block_ids=[])
        current['analysis_units'].append(dict(id=stage+':'+key,status='succeeded',output=out))
        return out
    monkeypatch.setattr(a2,'call',call)
    assert refresh['id'] in engine.pending_calls(run,by)
    engine.assess(None,run,list(by.values()),by,cm,rechecked=True)
    engine.assess(None,run,list(by.values()),by,cm,rechecked=True)
    assert len(reads)==len(calls)==1
    assert calls[0]['blocks'][-1]['text']=='추가 정의 원문'
    assert calls[0]['source_fingerprint']!=before['output']['source_fingerprint']
    assert run['analysis_units'][-1]['read_selection'][0]['source_version_id']=='v2'
    assert original['output']['meanings'][0]['availability']=='internal_unselected'


def test_capacity_split_preserves_shared_exception_and_original_addresses(monkeypatch):
    _,run,result,by,_=requirement_fixture()
    block=by['e'];block['text']='적용 범위\n'+''.join(f'{n}. 규칙 {n} 내용\n' for n in range(1,9))+'다만 제외 조건은 유지한다.'
    ctx=dict(meaning_phase='grounding',blocks=[dict(ref='e',text=block['text'])],source_fingerprint='whole')
    monkeypatch.setattr(a2,'input_size',lambda *_:dict(input_chars=100,input_chars_limit=1,request_input_bytes=100,input_bytes_limit=1))
    parts=engine.source_parts(run,ctx,by)
    assert len(parts)>1
    for part in parts:
        assert part['split_parent_fingerprint']=='whole'
        assert all(v['text']==block['text'][slice(*v['span'])] for v in part['blocks'])
        assert any('적용 범위' in v['text'] for v in part['blocks'])
        assert any('다만 제외 조건' in v['text'] for v in part['blocks'])
    covered={i for p in parts for v in p['blocks'] for i in range(*v['span'])}
    assert set(range(len(block['text'])))<=covered


def test_representation_after_refresh_receipt_uses_the_same_new_source(monkeypatch):
    run,result,by,_,_,_,_=receipt_fixture(monkeypatch)
    base=run['analysis_units'][0]
    by['e2']=dict(by['e'],id='e2',text='새 근거',source_version_id='v2',parse_run_id='p2')
    base['id']=engine.plan(run,result,by)[0]['id']
    context=deepcopy(base['grounding_context']);context['blocks'].append(dict(ref='e2',text='새 근거',span=[0,4]))
    current=dict(deepcopy(base),id='context:refresh',grounding_base_id=base['id'],grounding_context=context)
    current['output']['assessment_hash']='new-receipt'
    run['analysis_units'].append(current)
    descriptor=next(d for d in engine.plan(run,result,by) if d['mode']=='representation')
    assert descriptor['context']['source_receipt']==dict(unit_id='context:refresh',assessment_hash='new-receipt')
    assert descriptor['deps']==['e','e2']
    assert descriptor['context']['blocks'][-1]==dict(ref='e2',text='새 근거',span=[0,4])
    wire=a2.segments.bind(descriptor['context'],'fixed',descriptor['id'],stable=True)
    refs={v['source_ref']:v for v in a2.segments.originals(wire)}
    assert any(v['ref']=='e2' and v['text']=='새 근거' for v in refs.values())


def test_same_candidate_errors_are_collected_before_one_revision(monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    run,result,by,cm,d,output,_=receipt_fixture(monkeypatch)
    primary=d['context']['source_assessment']['meanings'][0]
    second=dict(deepcopy(primary),meaning_key='second',meaning='다른 잘못된 조건')
    normal=dict(deepcopy(primary),meaning_key='normal',meaning='보존할 정상 역할')
    d['context']['source_assessment']['meanings'] += [second,normal]
    first=output['checks'][0]
    first.update(action='correct',status='incorrect',locations=[dict(candidate_ref='c',field='definition')],repair_fields=['definition'],preserve_keys=['normal'])
    output['checks'] += [dict(deepcopy(first),meaning_key='second',locations=[dict(candidate_ref='c',field='conditions')],repair_fields=['conditions']),
        dict(deepcopy(first),meaning_key='normal',action='maintain',status='represented',repair_fields=[])]
    run['candidate_groups']=[dict(id='owner',primary_candidate_ids=['c'],candidates=result['observations'],design_candidates=[],analysis_group_ids=['g'])]
    run['analysis_units'].append(dict(id='builder:owner',stage='builder',status='succeeded',output=dict(hierarchies=[])))
    old=dict(id='unrelated',candidate_ref='c',meaning_keys=['old'],source_receipt={'old':'proof'})
    run['recovery_requests'].append(deepcopy(old));seen=[]
    def revise(service,current,owner,repair,*_):
        seen.append(repair);owner['correction_plan']=[dict(candidate_id='c',stage='revision',key='one')]
    monkeypatch.setattr(synthesis,'revise',revise)
    engine.route(None,run,d,output,by,cm,result)
    assert len(seen)==1
    assert {tuple(c['repair_fields']) for c in seen[0]['grounded_repairs']}=={('definition',),('conditions',)}
    assert all(c['preservation_basis'][0]['meaning_key']=='normal' for c in seen[0]['grounded_repairs'])
    assert run['recovery_requests'][0]==old
    request=run['recovery_requests'][1]
    assert set(request['grounding_authorizations'])=={primary['meaning_key'],'second'}
    assert len(request['meanings'])==2


def test_merged_missing_requests_preserve_each_current_authorization(monkeypatch):
    run,result,by,cm,d,output,_=receipt_fixture(monkeypatch)
    primary=d['context']['source_assessment']['meanings'][0]
    second=dict(deepcopy(primary),meaning_key='second',meaning='두 번째 필요한 의미')
    d['context']['source_assessment']['meanings'].append(second)
    output['checks'].append(dict(deepcopy(output['checks'][0]),meaning_key='second'))
    run['analysis_units'][-1]['output']=output
    monkeypatch.setattr(engine,'plan',lambda *_:[d])
    engine.route(None,run,d,output,by,cm,result)
    assert len(run['recovery_requests'])==1
    request=run['recovery_requests'][0]
    assert len(request['meanings'])==2
    assert engine.authorized_keys(run,request,by)=={primary['meaning_key'],'second'}
    output['source_challenges']=[dict(meaning_key=primary['meaning_key'])]
    assert engine.authorized_keys(run,request,by)=={'second'}
    assert engine.authorized(run,request,by)  # The independent second meaning remains runnable.


def test_supersession_schema_only_allows_real_previous_addresses(monkeypatch):
    run,result,by,_,_,_,_=receipt_fixture(monkeypatch)
    ctx=a2.segments.bind(engine.plan(run,result,by)[0]['context'],'fixed','g',stable=True)
    _,schema,_,_=engine.contract(ctx,{})
    assert schema['$defs']['SourceMeaning']['properties']['supersedes']['enum']==['']
    ctx['previous_meanings']=[dict(meaning_key='actual_previous')]
    _,schema,_,_=engine.contract(ctx,{})
    assert schema['$defs']['SourceMeaning']['properties']['supersedes']['enum']==['','actual_previous']
    row=source('unknown');row.update(availability='external_missing',missing_source='external_missing')
    with pytest.raises(ValueError,match='자료명'): grounded([row])
    row.update(missing_source='문서명',read_block_ids=['e'])
    with pytest.raises(ValueError,match='내부 원문'): grounded([row])


def test_merged_request_is_not_resolved_when_one_submitted_meaning_has_no_current_r():
    run=dict(recovery_requests=[dict(id='merged',meaning_keys=['a','b']),dict(id='independent',meaning_keys=['c'])])
    checks=[dict(meaning_key='a',judgment='supported'),dict(meaning_key='c',judgment='supported')]
    assert engine.resolved_requests(run,checks)=={'independent'}
    checks.append(dict(meaning_key='b',judgment='unknown'))
    assert engine.resolved_requests(run,checks)=={'independent'}
    checks[-1]['judgment']='supported'
    assert engine.resolved_requests(run,checks)=={'merged','independent'}


@pytest.mark.parametrize('read_first',[True,False])
def test_internal_read_and_one_semantic_challenge_have_independent_limits(monkeypatch,read_first):
    run,result,by,_,expression,_,_=receipt_fixture(monkeypatch)
    original=run['analysis_units'][0];base=original['id']
    by['e2']=dict(by['e'],id='e2',text='추가 원문',source_version_id='v2',parse_run_id='p2')
    original['grounding_context']['input_inventory'].append(dict(block_id='e2',source_version_id='v2',parse_run_id='p2'))
    original['output']['meanings'][0].update(availability='internal_unselected',read_block_ids=['e2'])
    key=original['output']['meanings'][0]['meaning_key'];calls=[]
    request=dict(source_challenges=[dict(meaning_key=key,reason='원문 조건 대조',proposed_meaning='원문 조건에 맞는 의미',
        evidence_refs=original['output']['meanings'][0]['evidence_refs'])])
    def call(service,current,stage,unit_key,ctx,*_):
        calls.append(unit_key)
        current['analysis_units'].append(dict(id=stage+':'+unit_key,status='succeeded',output=deepcopy(original['output']),grounding_context=ctx))
        return current['analysis_units'][-1]['output']
    monkeypatch.setattr(a2,'call',call);monkeypatch.setattr(a2,'save',lambda *_:None)
    def challenge(current):
        d=deepcopy(expression)
        d['context']['source_receipt']=dict(unit_id=current['id'],assessment_hash=current['output']['assessment_hash'])
        return engine.challenge(None,run,d,request,by)
    def read(current):
        d=engine.refresh_descriptor(current,base,by)
        assert d is not None
        call(None,run,d['stage'],d['key'],d['context'])
        created=run['analysis_units'][-1]
        created.update(grounding_base_id=base,grounding_actions=d['grounding_actions'])
        return created
    if read_first:
        current=read(original)
        assert challenge(current)
        current=run['analysis_units'][-1]
    else:
        assert challenge(original)
        current=read(run['analysis_units'][-1])
    assert engine.followup_actions(current)=={'read','challenge'}
    assert not challenge(current)
    assert engine.refresh_descriptor(current,base,by) is None
    assert len(calls)==2
    assert original['output']['meanings'][0]['availability']=='internal_unselected'


def test_later_authorized_missing_meaning_gets_new_group_without_repeating_first(monkeypatch):
    run,result,by,cm,d,output,_=receipt_fixture(monkeypatch)
    by['e'].update(file_id='f',source_group='test')
    primary=d['context']['source_assessment']['meanings'][0];first=primary['meaning_key']
    d['context']['source_assessment']['meanings'].append(dict(deepcopy(primary),meaning_key='second',meaning='두 번째 누락'))
    output['checks'].append(dict(deepcopy(output['checks'][0]),meaning_key='second'))
    monkeypatch.setattr(engine,'plan',lambda *_:[d])
    engine.route(None,run,d,output,by,cm,result)
    request=run['recovery_requests'][0]
    allowed={first}
    monkeypatch.setattr(engine,'authorized_keys',lambda *_:set(allowed))
    one=a2.recovery_groups(run,1,by)
    assert len(one)==1 and [m['meaning_keys'] for m in one[0]['recovery_meanings']]==[[first]]
    first_snapshot=deepcopy(one[0]);run['frontier'].extend(one)
    assert a2.recovery_groups(run,1,by)==[]
    request['status']='proposals_created';allowed.add('second')
    two=a2.recovery_groups(run,2,by)
    assert len(two)==1 and two[0]['id']!=one[0]['id']
    assert [m['meaning_keys'] for m in two[0]['recovery_meanings']]==[['second']]
    assert one[0]==first_snapshot
    assert set(request['group_ids'])=={one[0]['id'],two[0]['id']}
    assert not request['unattempted_meanings']
    assert a2.recovery_groups(run,2,by)==[]


def test_keyed_expression_and_targeted_supersession():
    _,run,result,by,cm=requirement_fixture();run['recipe']['meaning_contract']=m.CONTRACT
    source_output=grounded([source(),dict(source(),local_ref='b',meaning='독립 규칙')])
    key,other=[r['meaning_key'] for r in source_output['meanings']]
    ctx=dict(meaning_phase='representation',source_assessment=source_output,source_receipt={'unit_id':'u'},blocks=[])
    _,schema,_,_=engine.contract(ctx,{})
    assert set(schema['properties']['checks']['required'])=={key,other}
    assert 'assertion' not in schema['$defs']['Expression']['properties']
    row=dict(status='missing',locations=[],repair_fields=[],preserve_keys=[],role='concept',reason='실제 표현 누락')
    normalized=m.records(dict(checks={key:row},source_challenges=[],reason='대조'),ctx,{},by,'r')
    assert normalized['checks'][0]['action']=='recover' and normalized['pending_meaning_keys']==[other]
    ctx=dict(meaning_phase='grounding',previous_meanings=source_output['meanings'],reassess_meaning_keys=[key],blocks=[])
    _,schema,_,_=engine.contract(ctx,{})
    assert schema['$defs']['SourceMeaning']['properties']['supersedes']['enum']==['',key]

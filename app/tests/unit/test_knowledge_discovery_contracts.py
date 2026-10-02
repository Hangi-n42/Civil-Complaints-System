"""Per-target role contracts; stored legacy citation records remain readable."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_design as design, discovery_synthesis as synthesis
from app.knowledge import ontology_changes
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import done, request, response, model, source_response
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def test_expanded_input_selects_comparison_and_keeps_byte_and_actual_token_guards(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    assert (run['recipe']['input_chars'],run['recipe']['num_ctx'],run['recipe']['num_predict'])==(24000,32768,4096)
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks};bid=blocks[0]['id']
    term=dict(id='comparison',classification='type',definition='x'*13000,evidence_ids=[bid])
    context=dict(blocks=[dict(ref=bid,text=blocks[0]['text'])],comparison_terms=[term])
    old=deepcopy(run);old['recipe']['input_chars']=12000
    _,_,old_terms=a2.analysis_context(old,'scout',context,{term['id']:term},{})
    selected,deps,terms=a2.analysis_context(run,'scout',context,{term['id']:term},{})
    assert not old_terms and terms=={term['id']:term} and selected['blocks']==context['blocks']
    assert synthesis.fits(run,'scout',selected,deps,terms) and not synthesis.fits(old,'scout',selected,deps,terms)
    assert a2.call(service,run,'scout','expanded',selected,deps,by_id,terms) is not None
    assert 12000<run['analysis_units'][-1]['input_chars']<24000
    count=len(model)
    assert a2.call(service,run,'scout','bytes',dict(blocks=context['blocks'],note='가'*11000),deps,by_id) is None
    assert len(model)==count and '컨텍스트' in run['analysis_units'][-1]['error']
    original=a2.model_call
    async def overflow(*args,**kwargs):
        result=await original(*args,**kwargs);result['prompt_eval_count']=30000;return result
    monkeypatch.setattr(a2,'model_call',overflow)
    assert a2.call(service,run,'scout','tokens',dict(blocks=context['blocks']),deps,by_id) is None
    assert len(model)==count+1 and '토큰' in run['analysis_units'][-1]['error']


def test_builder_target_binding_defer_missing_and_duplicate_are_separate():
    types={i:dict(id=i,classification='type') for i in ('a','b')}
    rules={i:dict(id=i,statement_type='rule',subject='사업자',object='입주자',conditions='A 또는 B, 다만 C 제외',
        validation=[],evidence_ids=['e']) for i in ('r1','r2','r3')}
    supplied={**types,**rules};original=deepcopy(supplied)
    first=dict(relation_ref='r1',subject_ref='a',object_ref='b',reason='주어진 유형 정의와 대조')
    output=dict(observations=[],relation_bindings=[first,dict(relation_ref='r2',decision='defer',reason='입주자 유형 정의 미제공')])
    design.bind(output,supplied,{},dict(design_relation_ids=list(rules)))
    coverage=output['binding_coverage']
    assert coverage['bound_relation_ids']==['r1'] and coverage['deferred_relation_ids']==['r2']
    assert coverage['pending_relation_ids']==['r3']
    assert output['modeled_relations'][0]['source_relation']==rules['r1'] and supplied==original
    duplicate=a2.models.Taxonomy.model_validate(dict(observations=[],relation_bindings=[first]*5+[dict(first,relation_ref='r3')],
        hierarchies=[],alias_proposals=[],gaps=[],actions=[])).model_dump(warnings=False)
    design.bind(duplicate,supplied,{},dict(design_relation_ids=list(rules)))
    assert duplicate['binding_coverage']['bound_relation_ids']==['r3']
    assert duplicate['binding_coverage']['pending_relation_ids']==['r1','r2']
    empty=dict(observations=[],relation_bindings=[])
    design.bind(empty,supplied,{},dict(design_relation_ids=[]))
    assert not empty['binding_errors'] and not empty['binding_coverage']['pending_relation_ids']


@pytest.mark.parametrize('bad',['missing','duplicate','unsupported','outside','unknown'])
def test_observation_judgments_preserve_valid_sibling_and_a3(service,model,monkeypatch,bad):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def review(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);item=value['observation_checks'][1]
            if bad=='missing': value['observation_checks'].pop()
            elif bad=='duplicate': value['observation_checks'].extend(deepcopy(item) for _ in range(17))
            elif bad=='unsupported': item.update(evidence_id='',quote='')
            elif bad=='outside': item['evidence_id']='outside'
            else: item.update(judgment='unknown',evidence_id='',quote='',reason='유형의 범위에 필요한 정의가 없음')
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',review)
    run=done(service,service.start(request(source['id']))['run_id'])
    critic=next(u for u in run['analysis_units'] if u['stage']=='critic')
    group=run['candidate_groups'][0];review=critic['output'];first,second=run['result']['observations']
    expected=set(group['primary_candidate_ids'])|{h['id'] for h in run['result']['taxonomy'][0]['hierarchies']}
    assert set(review['review_coverage']['expected_candidate_ids'])==expected
    assert first['id'] in review['review_coverage']['valid_candidate_ids']
    assert (second['id'] in review['review_coverage']['pending_candidate_ids'])==(bad!='unknown')
    if bad=='unknown': assert review['review_outcomes']['unknown']
    cid=ontology_changes.publish(service,run['id'])['changeset_id']
    with service.repository.connect() as db: changes=service.repository.get(db,'changesets',cid)['candidates']
    good=next(c for c in changes if c['origin']['candidate_id']==first['id'])
    unresolved=next(c for c in changes if c['origin']['candidate_id']==second['id'])
    assert good['origin']['observation_checks'] and not good['origin'].get('review_errors')
    assert unresolved['review_status']=='deferred'


@pytest.mark.parametrize('comparison_only',[False,True])
def test_new_generation_schema_citations_and_target_bounds(service,model,monkeypatch,comparison_only):
    import jsonschema
    source=prepare(service,file_ids=['current:0']);seen={}
    if comparison_only:
        assemble=synthesis.assemble
        def comparison(*args): return [dict(g,comparison_only=True) for g in assemble(*args)]
        monkeypatch.setattr(synthesis,'assemble',comparison)
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(response(prompt,stage),data)
        # Pydantic defaults are materialized for the generation schema's complete envelope.
        if stage=='builder': value.setdefault('observations', [])
        if stage=='concept':
            for c in value['observations']:
                c.update(classification_reason='원문의 일반 유형',conditions='',exceptions='',time='')
        if stage=='relation':
            for c in value['relations']:
                c.pop('endpoint_labels',None)
                c.pop('local_ref')
        jsonschema.validate(value,schema)
        if stage=='builder':
            assert all(v['properties']['relation_bindings']['minItems']==v['properties']['relation_bindings']['maxItems']==len(data['design_relation_ids'])<=5 for v in schema['anyOf'])
        if stage=='critic':
            assert set(data['review_target_ids']).isdisjoint(data['comparison_candidate_ids'])
            if comparison_only:
                assert not any(v.get('analysis_target') and not v.get('context_only') for v in data['blocks'])
        seen[stage]=len(prompt)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']==('partial' if comparison_only else 'review_ready'),run['result']['failures']
    assert not run['result']['failures']
    assert max(seen.values())<=run['recipe']['input_chars']
    print('E2 actual input chars:',seen)
    if not comparison_only:
        trial=deepcopy(run);trial['candidate_groups']=[]
        trial['analysis_units']=[u for u in trial['analysis_units'] if u['stage'] in {'scout','concept','relation'}]
        unit=next(u for u in trial['analysis_units'] if u['stage']=='relation')
        unit['output']['relations']=[dict(unit['output']['relations'][0],id='relation'+str(n)) for n in range(6)]
        blocks=a2.load_blocks(service,trial);by_id={b['id']:b for b in blocks}
        groups=synthesis.assemble(trial,0,by_id,a2.profile.contexts(blocks),set(by_id))
        counts=[sum(c['id'] in g['primary_candidate_ids'] and c.get('statement_type') in {'rule','definition'} for c in g['candidates']) for g in groups]
        assert sum(counts)==6 and max(counts)<=5


@pytest.mark.parametrize('model_refs', ['missing','duplicate'])
def test_fresh_relation_refs_are_server_assigned_at_call_boundary(service,model,monkeypatch,model_refs):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;raw=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='relation':
            assert all('local_ref' not in v['properties'] and 'local_ref' not in v['required']
                       for v in schema['$defs']['Relation']['anyOf'])
            value=source_response(json.loads(result['text']),json.loads(prompt.split('\nINPUT:\n')[1]))
            value['relations']*=2
            for c in value['relations']:
                c.pop('local_ref',None)
                if model_refs=='duplicate': c['local_ref']='e0'
                c.update(object='국민임대주택',direction='unresolved')
            result['text']=json.dumps(value,ensure_ascii=False);raw.append(result['text'])
        return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    unit=next(u for u in run['analysis_units'] if u['stage']=='relation')
    assert unit['status']=='succeeded',unit['error']
    rows=unit['output']['relations']
    assert [r['local_ref'] for r in rows]==['r1','r2'] and len({r['id'] for r in rows})==2
    assert unit['raw_output']==raw[0]
    for before,after in zip(json.loads(raw[0])['relations'],rows):
        for key in ('subject','predicate','object','conditions','time','direction','source_refs'):
            assert after.get(key)==before.get(key)
    legacy=a2.models.Relations.model_validate(dict(relations=[dict(r,local_ref='e0') for r in json.loads(raw[0])['relations']],gaps=[],actions=[])).model_dump()
    with pytest.raises(ValueError,match='local_ref 중복'):
        a2.normalize(legacy,'relation',run,unit['dependency_ids'],{}, {})


@pytest.mark.parametrize('targets,at_limit',[(0,False),(1,False),(3,False),(3,True),(6,True)])
def test_critic_missing_capacity_uses_unique_primary_views(service,model,monkeypatch,targets,at_limit):
    source=prepare(service,file_ids=['current:0']);original_call=a2.call;seen=[]
    def call(service,run,stage,key,context,deps,by_id,supplied=None):
        if stage=='critic':
            context=deepcopy(context);base=context['blocks'][0];text=base['text']
            views=[dict(base,text=text[n:n+1],span=[n,n+1],analysis_target=True,context_only=False) for n in range(targets)]
            context['blocks']=[dict(base,analysis_target=False),*views,*deepcopy(views),
                dict(base,span=[len(text)-1,len(text)],text=text[-1:],analysis_target=True,context_only=True)]
            context['independently_retrieved']=[dict(base,analysis_target=True)]
        return original_call(service,run,stage,key,context,deps,by_id,supplied)
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(response(prompt,stage),data)
        if stage=='critic':
            limit=max(2,min(5,targets));seen.append(limit)
            assert all(v['properties']['missing_meanings']['maxItems']==limit for v in schema['anyOf'])
            assert 'cause' in schema['$defs']['Issue']['required']
            if at_limit:
                value['missing_meanings']=[dict(role='relation',meaning=f'검수 대기 의미 {n}',source_refs=[data['blocks'][0]['source_ref']],
                    cq_ids=['cq1'],scope_item_ids=[],outside_scope_reason='',compared_candidate_ids=data['review_target_ids'],
                    comparison_reason='제공 관측과 관계를 대조') for n in range(limit)]
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'call',call);monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=5,additional_rounds=0,revisions=0)))['run_id'])
    unit=next(u for u in run['analysis_units'] if u['stage']=='critic')
    assert unit['status']=='succeeded',unit['error']
    output=unit['output'];assert seen==[max(2,min(5,targets))]
    assert output['capacity']['primary_analysis_targets']==targets
    assert bool(output['capacity_pending'])==at_limit
    assert '전체 검수 완료가 아님' in output['capacity']['semantic_completeness']
    assert any(p.get('stage')=='critic' for p in run['result']['capacity_pending'])==at_limit
    if at_limit: assert unit['group_id'] in run['result']['mandatory_pending'] and run['status']=='partial'


@pytest.mark.parametrize('bound',[False,True])
def test_fresh_critic_missing_cause_isolated_before_default(service,model,monkeypatch,bound):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;raw_issues=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
            issue=dict(local_ref='i1',candidate_ref=data['unapproved_observations'][1]['id'] if bound else '',
                reason='원인 필드를 생략한 쟁점',defer_reason='추가 판단 필요')
            raw_issues.append(deepcopy(issue));value['issues']=[issue]
            value['actions']=[dict(action='request_evidence',issue_id='i1',query='검토 근거',reason='쟁점 의존 요청')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=5,additional_rounds=0,revisions=0)))['run_id'])
    unit=next(u for u in run['analysis_units'] if u['stage']=='critic');assert unit['status']=='succeeded',unit['error']
    output=unit['output'];assert not output['issues'] and not output['actions']
    assert any(e['section']=='issues' and 'cause 누락' in e['reason'] for e in output['record_errors'])
    assert len(output['observation_checks'])==(1 if bound else 2)
    assert not any(r['cause']=='content_error' for r in run['result']['recovery_requests'])
    assert not any(e['action']=='request_evidence' for e in run['tool_events'])
    assert a2.models.Issue.model_validate(raw_issues[0]).cause=='content_error'  # Stored legacy default remains readable.


@pytest.mark.parametrize('concept_result',['normal','empty','failed'])
def test_relation_keeps_own_originals_without_concept_predictions(service,model,monkeypatch,concept_result):
    source=prepare(service,file_ids=['current:0','web:0']);blocks=a2.load_blocks(service,source)
    selected=[b['id'] for b in blocks if b['file_id']=='current:0'];seen={};allocate=a2.analysis_context
    def trim(run,stage,context,supplied,group,reserve=0):
        if stage=='concept':
            assert context['tool_originals']
            context=deepcopy(context);context['tool_originals']=[]
        return allocate(run,stage,context,supplied,group,reserve)
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);seen.setdefault(stage,[]).append(data)
        if stage=='builder' and not data['unapproved_observations']:
            value=dict(observations=[],relation_bindings=[dict(relation_ref=i,decision='defer',reason='유형 설계 미완료') for i in data['design_relation_ids']],
                hierarchies=[],alias_proposals=[],gaps=[],actions=[])
        else: value=response(prompt,stage)
        if stage=='scout': value['actions']=[dict(action='search',query='예외',reason='예외 원문 확인')]
        if stage=='concept' and concept_result=='empty': value=dict(observations=[],alignments=[],gaps=['이 원문에는 별도 일반 정의를 확정하지 못함'],actions=[])
        if stage=='relation':
            assert not any(k in data for k in ('unapproved_observations','reviewed_base','comparison_terms','previous_observations'))
            assert any('예외' in b['text'] for b in data['tool_originals'])
        return dict(text='{' if stage=='concept' and concept_result=='failed' else json.dumps(value,ensure_ascii=False),
            done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'analysis_context',trim);monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],analysis_block_ids=selected,analysis_selection_reason='주 분석 원문 선택',
        discovery_budgets=dict(model_calls=5,additional_rounds=0,revisions=0)))['run_id'])
    relation=next(u for u in run['analysis_units'] if u['stage']=='relation')
    assert relation['status']=='succeeded',relation['error']
    assert len(seen['relation'])==1 and seen['builder'][0]['unapproved_relations']
    assert bool(seen['builder'][0]['unapproved_observations'])==(concept_result=='normal')
    data=seen['relation'][0];assert len(relation['dependency_ids'])==len(a2.raw_refs(data))
    if concept_result!='normal': assert run['status']=='partial'
    if concept_result=='failed':
        concept=next(u for u in run['analysis_units'] if u['stage']=='concept');assert concept['status']=='failed'
        again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
        reused=next(u for u in again['analysis_units'] if u['stage']=='relation')
        assert len(seen['relation'])==1 and reused['output']==relation['output'] and reused['source_ref_map']==relation['source_ref_map']


@pytest.mark.parametrize('oversized',[False,True])
def test_resumed_concept_new_original_goes_to_builder_not_completed_relation(service,model,monkeypatch,corpus,oversized):
    if oversized:
        from hashlib import sha256
        path=corpus/'web.html';path.write_text('<body><p>예외 '+('추가 설명 '*3000)+'</p></body>',encoding='utf-8-sig')
        manifest=corpus/'manifest.json';data=json.loads(manifest.read_text())
        next(s for s in data['selected_sources'] if s['source_id']=='web')['input_files'][0]['sha256']=sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data),encoding='utf-8')
    source=prepare(service,file_ids=['current:0','web:0']);blocks=a2.load_blocks(service,source)
    selected=[b['id'] for b in blocks if b['file_id']=='current:0'];first=True;seen=[]
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);seen.append((stage,data))
        value=response(prompt,stage)
        if stage=='concept' and not first: value['actions']=[dict(action='search',query='예외',reason='재개 후 추가 원문 확인')]
        return dict(text='{' if stage=='concept' and first else json.dumps(value,ensure_ascii=False),
            done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],analysis_block_ids=selected,analysis_selection_reason='주 분석 원문 선택',
        discovery_budgets=dict(additional_rounds=0,revisions=0)))['run_id'])
    relation=deepcopy(next(u for u in run['analysis_units'] if u['stage']=='relation'));first=False
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert next(u for u in again['analysis_units'] if u['stage']=='concept')['status']=='succeeded'
    assert next(u for u in again['analysis_units'] if u['stage']=='relation')==relation
    assert sum(stage=='relation' for stage,_ in seen)==1
    builder=next(u for u in reversed(again['analysis_units']) if u['stage']=='builder')
    assert builder['status']=='succeeded',builder['error']
    provided=a2.segments.originals(json.loads(builder['prompt'].split('\nINPUT:\n')[1]))
    assert any('예외' in b['text'] for b in provided)==(not oversized)
    group=next(g for g in again['candidate_groups'] if g['id']==builder['group_id'])
    assert bool(group['omitted_builder_context_ids'])==oversized
    assert builder['input_chars']<=again['recipe']['input_chars']
    if not oversized: assert set(builder['dependency_ids'])-set(relation['dependency_ids'])
    assert not any('입력 해시 변경' in str(u.get('error')) for u in again['analysis_units'])
    before=len(seen)
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=again['id']))['run_id'])
    assert len(seen)==before
    assert next(g for g in resumed['candidate_groups'] if g['id']==group['id'])['builder_tool_context']==group['builder_tool_context']


def semantic_case():
    text='시험 원문: 사업자는 입주자를 선정할 수 있다. 잔여주택이면 일부 완화 또는 선착순이며 제1항에도 불구하고 적용한다.'
    block=dict(id='b',source_version_id='v',parse_run_id='p',locator={},text=text)
    run=dict(cqs=[dict(id='q')],scope_items=[],analysis_units=[])
    types={i:dict(id=i,label=label,classification='type',definition=label,validation=[],evidence_ids=['b'],
        evidence_refs=[dict(evidence_id='b',block_id='b',span=[0,len(text)],quote=text)])
           for i,label in [('actor','사업자'),('resident','입주자'),('housing','주택')]}
    raw=dict(local_ref='r1',subject='actor',predicate='선정할 수 있다',object='resident',endpoint_labels=dict(subject='사업자',object='입주자'),
        direction='subject_to_object',negation='affirmed',conditions='잔여주택이면 일부 완화 OR 선착순; 제1항에도 불구하고 적용',time='',
        statement_type='rule',evidence_ids=['b'],cq_ids=['q'],scope_item_ids=[],outside_scope_reason='')
    relation=a2.normalize(dict(relations=[deepcopy(raw)]),'relation',run,['b'],{'b':block},types)['relations'][0]
    context=dict(blocks=[dict(ref='b',text=text,source_ref='s1')],unapproved_relations=[relation],taxonomy=dict(hierarchies=[]),
        review_target_ids=[relation['id']],review_scope=dict(extent='provided_only',whole_input_assessed=False,known_not_provided=1))
    review=dict(issues=[],hierarchy_checks=[],gaps=[],actions=[],needs_revision=False,
        relation_checks=[dict(candidate_ref=relation['id'],judgment='supported',source_refs=['s1'],reason='끝점과 유형 정의·조건을 대조',
            semantic_checks={k:'supported' for k in ('subject','object','conditions','statement_type')})])
    return run,block,types,raw,relation,context,review


@pytest.mark.parametrize('boundary',['valid','raw_unresolved','modeled_missing_type','composed_phrase','link_error','missing_checks','object','conditions','statement_type','legacy_id_only'])
def test_relation_source_endpoints_and_qualifiers_need_explicit_review(boundary):
    run,block,types,raw,relation,context,review=semantic_case()
    original=deepcopy(relation)
    if boundary=='missing_checks': review['relation_checks'][0].pop('semantic_checks')
    elif boundary=='legacy_id_only': relation['endpoint_labels']={}
    elif boundary=='raw_unresolved': relation.update(subject='사업자',object='입주자',unresolved_endpoints=['subject','object'])
    elif boundary=='modeled_missing_type': relation.update(source_relation=original,object='missing_type')
    elif boundary=='composed_phrase': relation['endpoint_labels']['object']='잔여주택 입주자'
    elif boundary=='link_error':
        relation['object']='housing'
        review['issues']=[dict(local_ref='i1',candidate_ref=relation['id'],cause='endpoint',reason='원문 입주자 대신 적용 범위인 주택 타입 연결',defer_reason='',source_refs=['s1'])]
    elif boundary!='valid':
        review['relation_checks'][0]['semantic_checks'][boundary]='refuted'
        if boundary=='object': relation.update(object='housing',endpoint_labels=dict(subject='사업자',object='주택'))
        if boundary=='conditions': relation['conditions']='잔여주택이면 일부 완화'  # OR/priority exists only in quote.
        if boundary=='statement_type': relation['statement_type']='instance'
    supplied={**types,relation['id']:relation}
    output=a2.normalize(a2.models.Critique.model_validate(review).model_dump(),'critic',run,['b'],{'b':block},supplied,context)
    assert bool(output['review_coverage']['pending_candidate_ids'])==(boundary not in {'valid','raw_unresolved','modeled_missing_type','composed_phrase','link_error'})
    if boundary=='modeled_missing_type': assert output['relation_checks'][0]['binding_validation']
    if boundary=='link_error':
        assert output['relation_checks'][0]['judgment']=='supported'
        a2.queue_recovery(run,output,dict(id='g',primary_candidate_ids=[relation['id']],candidates=[relation]),{'b':block})
        assert run['recovery_requests'][0]['cause']=='endpoint' and run['recovery_requests'][0]['status']=='manual_review'
    if boundary=='valid':
        assert relation==original and relation['endpoint_labels']==raw['endpoint_labels']
        assert relation['object']=='resident' and relation['conditions']==raw['conditions']
        assert a2.remap(dict(subject='c0',endpoint_labels=dict(subject='c0')),{'c0':'server-id'})==dict(subject='server-id',endpoint_labels=dict(subject='c0'))
    assert not output['review_scope']['whole_input_assessed']


def test_missing_concept_must_compare_existing_relation_before_reextraction():
    run,block,types,raw,relation,context,review=semantic_case()
    review['missing_meanings']=[dict(role='concept',meaning='선정 원칙과 잔여주택 예외',source_refs=['s1'],cq_ids=['q'],
        compared_candidate_ids=list(types),comparison_reason='명칭의 concept가 없다는 이유만으로 누락 주장')]
    output=a2.normalize(a2.models.Critique.model_validate(review).model_dump(),'critic',run,['b'],{'b':block},
        {**types,relation['id']:relation},context)
    assert not output['missing_meanings'] and output['relation_checks']
    assert any(e['section']=='missing_meanings' for e in output['record_errors'])
    a2.queue_recovery(run,output,dict(id='g'),{'b':block})
    assert not run['recovery_requests']


def test_clause_response_pending_survives_critic_and_resume(service,model,monkeypatch,corpus):
    from hashlib import sha256
    text='제15조 ① 국민임대 원칙. ② 남은 주택이면 완화 또는 선착순. ③ 각 호에 따른 별도 기준. 1. LH 공급. 2. 지방공사 공급.'
    path=corpus/'current.txt';path.write_text(text,encoding='utf-8-sig')
    manifest=corpus/'manifest.json';data=json.loads(manifest.read_text())
    data['selected_sources'][0]['input_files'][0]['sha256']=sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data),encoding='utf-8')
    source=prepare(service,file_ids=['current:0']);seen={}
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=response(prompt,stage)
        if stage=='relation':
            targets=[v for v in data['blocks'] if v.get('analysis_target')]
            value['relations'][0].update(evidence_ids=[],source_refs=[targets[0]['source_ref']])
            value['target_gaps']=[dict(source_ref=targets[2]['source_ref'],reason='별표 상세 미제공')]
        if stage=='critic': seen['coverage']=data['analysis_target_coverage']
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=5,additional_rounds=0,revisions=0)))['run_id'])
    assert run['metrics']['llm_calls']==5,run['result']['failures']
    coverage=run['result']['analysis_target_coverage']
    assert len(coverage)==3 and len(seen['coverage'])==3
    assert [bool(t['candidate_ids']) for t in coverage]==[True,False,False]
    missing=[r for r in run['result']['recovery_requests'] if r.get('trigger')=='target_response']
    assert len(missing)==1 and missing[0]['target'][0][1]==coverage[1]['span']
    assert run['status']=='partial' and not run['frontier'][0]['analysis_grounded']
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert resumed['metrics']['llm_calls']==5 and resumed['result']['analysis_target_coverage']==coverage


def test_source_text_endpoints_and_builder_source_error_do_not_rewrite_original():
    run,block,types,raw,relation,context,review=semantic_case()
    raw.update(subject='사업자',object='주택',endpoint_mode='source_text')
    relation=a2.normalize(dict(relations=[deepcopy(raw)]),'relation',run,['b'],{'b':block},types)['relations'][0]
    assert relation['subject']=='사업자' and relation['object']=='주택'
    assert relation['endpoint_labels']==dict(subject='사업자',object='주택')
    assert a2.remap(dict(subject='c0',object='c1',endpoint_mode='source_text'),{'c0':'id0','c1':'id1'})['object']=='c1'
    output=dict(observations=[],relation_bindings=[dict(relation_ref=relation['id'],decision='source_error',reason='원문 선정 대상과 원관계 목적어 불일치')])
    design.bind(output,{**types,relation['id']:relation},{'b':block},dict(design_relation_ids=[relation['id']]))
    assert not output['modeled_relations'] and output['source_errors']
    group=dict(id='g',primary_candidate_ids=[relation['id']],candidates=[relation],source_errors=output['source_errors'])
    a2.queue_recovery(run,{},group,{'b':block})
    assert any(r['cause']=='content_error' and r['role']=='revision' for r in run['recovery_requests'])
    assert relation['object']=='주택'  # Preserve the wrong raw observation for explicit revision, never fix via binding.
    output=dict(observations=[],relation_bindings=[dict(relation_ref=relation['id'],decision='bind',subject_ref='actor',object_ref='resident',reason='설계 연결')])
    design.bind(output,{**types,relation['id']:relation},{'b':block},dict(design_relation_ids=[relation['id']]))
    modeled=output['modeled_relations'][0]
    assert modeled['source_relation']==relation and modeled['endpoint_labels']['object']=='주택'
    assert modeled['object']=='resident'  # Critic still receives the erroneous source endpoint independently.


def test_external_reference_gap_and_provided_rule_omission_route_separately():
    run,block,types,raw,relation,context,review=semantic_case()
    review['issues']=[dict(local_ref='i1',cause='source_absent',reason='참조 별표의 상세 수치 없음',defer_reason='별표 본문 필요')]
    review['missing_meanings']=[dict(role='relation',meaning='제공 본문의 잔여주택이면 완화 OR 선착순 허용',source_refs=['s1'],cq_ids=['q'],
        compared_candidate_ids=[relation['id'],*types],comparison_reason='기존 산출에 제공 조건의 일부가 없음')]
    supplied={**types,relation['id']:relation}
    output=a2.normalize(a2.models.Critique.model_validate(review).model_dump(warnings=False),'critic',run,['b'],{'b':block},supplied,context)
    a2.queue_recovery(run,output,dict(id='g',candidates=[relation],primary_candidate_ids=[relation['id']]),{'b':block})
    assert {(r['cause'],r['role']) for r in run['recovery_requests']}=={('source_absent','review'),('extraction_missing','relation')}


def test_literal_endpoint_survives_actual_prompt_compaction():
    raw=dict(id='rule',subject='actor',object='resident',endpoint_mode='source_text',
             endpoint_labels=dict(subject='actor',object='resident'))
    context=dict(unapproved_relations=[raw],reviewed_base=[dict(id='actor')])
    _,prompt=a2.make_prompt(dict(id='run',cqs=[],scope_items=[]),'builder',context,[],{'actor':dict(id='actor')})
    data=json.loads(prompt.split('\nINPUT:\n')[1])
    assert data['unapproved_relations'][0]['subject']=='actor'
    assert data['reviewed_base'][0]['id']=='c0' and 'endpoint_mode' not in data['unapproved_relations'][0]

"""K6 boundaries, not a model-quality benchmark."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.exceptions import GenerationError
from app.knowledge import search as local
from app.knowledge import search_answer
from app.knowledge.schemas import SearchRequest
from app.tests.unit.test_knowledge_snapshots import reviewed, create, activate, state


@pytest.fixture
def service(tmp_path,monkeypatch):
    value,selection=reviewed(tmp_path)
    # Use the real serial executor and storage, without unrelated model startup.
    value.closed=False;value.executor=ThreadPoolExecutor(max_workers=1)
    with value.repository.connect() as db:
        run=value.repository.get(db,'runs','run1');run['status']='succeeded';run['units']=[]
        value.repository.save(db,'runs',run)
    activate(value,create(value,selection))
    monkeypatch.setattr(local,'rank',lambda q,t:list(range(len(t))))
    yield value
    value.executor.shutdown()


def request(**kwargs):
    return SearchRequest(query='C001 세대수?',mode='local',**kwargs)


async def fake_model(self,prompt,**kwargs):
    payload=json.loads(prompt.split('INPUT:\n')[1]);group=payload['knowledge']['groups'][0]
    assert kwargs['num_predict']==1536 and kwargs['return_metadata']
    return dict(done=True,done_reason='stop',text=json.dumps(dict(selected_group_ids=[group['group_id']])))


@pytest.mark.parametrize('search_model', ['', 'retained-search-model'])
def test_answer_run_and_no_inference_branches(service,monkeypatch,search_model):
    monkeypatch.setattr(local.settings, 'OLLAMA_MODEL', 'generation-model')
    monkeypatch.setattr(local.settings, 'KNOWLEDGE_SEARCH_MODEL', search_model)
    monkeypatch.setattr(local.GenerationService,'call_ollama',fake_model)
    result=local.search(service,request())
    assert result['status']=='answered' and result['metrics']['llm_calls']==1
    assert result['citations'][0]['quote']=='521' and result['assertion_ids']==['count1']
    assert '여기에 근거가 없는 현재 상태' in result['limitations'][0] and '이 응답으로 확인할 수 없습니다' in result['limitations'][0]
    assert result['paths'][0]['entity_ids']==['entity1']
    with service.repository.connect() as db:
        run=service.repository.get(db,'runs',result['run_id'])
        assert run['status']=='succeeded' and run['kind']=='search' and run['input_version_ids']==['v1']
        assert run['model'] == (search_model or 'generation-model')
    unknown=local.search(service,SearchRequest(query='알 수 없는 대상',mode='local'))
    assert unknown['status']=='insufficient' and unknown['metrics']['llm_calls']==0
    state(service,'evidence','code','blocked')
    assert local.search(service,request())['metrics']['llm_calls']==0


def test_answer_candidates_preserve_input_and_separate_details(service, monkeypatch):
    _,snapshot,chosen,_,_=local.prepare(service,request())
    prompts=[search_answer.build(snapshot,chosen,request(),v) for v in ['B','C']]
    facts=[sorted([f for g in json.loads(p[0].split('INPUT:\n')[1])['groups'] for f in g['facts']],key=lambda f:f['assertion_id']) for p in prompts]
    assert facts[0]==facts[1] and prompts[0][1]==prompts[1][1]
    async def concise(self,prompt,**kwargs):
        assert kwargs['think'] is False
        return dict(done=True,done_reason='stop',text=json.dumps(dict(requirements=['세대수 조회'],answer_items=[dict(text='521세대입니다.',requirement_index=0,assertion_ids=['a1'])],limitations=[])))
    monkeypatch.setattr(local.GenerationService,'call_ollama',concise)
    result=local.search(service,request(),answer_variant='C',model='qwen3.5:4b')
    assert result['answer']=='521세대입니다.' and result['answer_style']=='concise_grounded'
    assert result['fact_details'] and result['citations'][0]['quote']=='521'
    assert result['requirements']==['세대수 조회']


@pytest.mark.parametrize('bad',['unknown','requirement','length','stale'])
def test_concise_answer_invalid_output_and_stale_clear(service,monkeypatch,bad):
    async def broken(self,prompt,**kwargs):
        if bad=='stale':state(service,'evidence','code','blocked')
        return dict(done=True,done_reason='length' if bad=='length' else 'stop',text=json.dumps(dict(requirements=['세대수'],answer_items=[dict(text='521세대입니다.',requirement_index=1 if bad=='requirement' else 0,assertion_ids=['missing' if bad=='unknown' else 'a1'])],limitations=[])))
    monkeypatch.setattr(local.GenerationService,'call_ollama',broken)
    if bad=='stale':
        result=local.search(service,request(),answer_variant='B')
        assert result['status']=='stale' and not result['fact_details'] and not result['requirements'] and not result['answer']
    else:
        with pytest.raises(GenerationError):local.search(service,request(),answer_variant='B')


def test_context_cards_follow_value_row_not_header_or_other_table():
    def ev(identifier,table,row):
        return dict(id=identifier,source_version_id='v',parse_run_id='p',locator=dict(format='pdf',physical_page=2,side='right',table=table,row=row))
    snapshot=dict(evidence={e['id']:e for e in [ev('header',1,0),ev('value',1,4),ev('other',2,4)]})
    a=dict(subject_id='s',evidence_ids=['header','value'],field_evidence=dict(value=['value']))
    same=dict(a,field_evidence=dict(value=['header','value']))
    other=dict(a,field_evidence=dict(value=['other']))
    assert search_answer.context_key(snapshot,a)==search_answer.context_key(snapshot,same)
    assert search_answer.context_key(snapshot,a)!=search_answer.context_key(snapshot,other)


def test_selected_facts_and_question_assessment(service,monkeypatch):
    async def selected(self,prompt,**kwargs):
        assert kwargs['think'] is False
        return dict(done=True,done_reason='stop',text=json.dumps(dict(checks=[dict(question_id='q1',question_condition='세대수?',verdict='not_established',basis_ids=['a1'],source_condition='521')])))
    monkeypatch.setattr(local.GenerationService,'call_ollama',selected)
    result=local.search(service,request(),answer_variant='D',model='qwen3.5:4b')
    assert '제공된 근거로는 확인할 수 없습니다' in result['answer']
    assert result['sentences'][0]['verdict']=='not_established'
    assert '521' in result['sentences'][0]['text'] and result['assertion_ids']==['count1']
    assert result['metrics']['llm_calls']==1


@pytest.mark.parametrize('bad',['question','condition','extra','unknown','empty'])
def test_selected_answer_does_not_allow_unquoted_claims(service,monkeypatch,bad):
    async def selected(self,prompt,**kwargs):
        item=dict(question_id='q1',question_condition='원문에 없는 질문' if bad=='question' else '세대수?',verdict='not_established',basis_ids=['missing' if bad=='unknown' else 'a1'],source_condition='없는 조건' if bad=='condition' else '')
        payload=dict(checks=[] if bad=='empty' else [item])
        if bad=='extra':payload['explanation']='수집 시점 차이 때문에 다릅니다.'
        return dict(done=True,done_reason='stop',text=json.dumps(payload))
    monkeypatch.setattr(local.GenerationService,'call_ollama',selected)
    with pytest.raises(GenerationError):local.search(service,request(),answer_variant='D')


def test_selected_answer_covers_five_questions_without_adding_unselected_facts(service):
    _,snapshot,chosen,_,_=local.prepare(service,request())
    question=SearchRequest(query='첫째? 둘째? 셋째? 넷째? 다섯째?',mode='local')
    payload=dict(checks=[dict(question_id=i,basis_ids=['a1'],question_condition='',source_condition='',verdict='fact_lookup') for i in search_answer.question_parts(question)])
    snapshot['assertions']['extra']=dict(chosen[0],id='extra',value=9999)
    answer,used=search_answer.parse_selected(json.dumps(payload),{'a1':'count1','a2':'extra'},snapshot,question)
    assert len(answer['requirements'])==5 and used=={'count1'}
    assert len(answer['sentences'])==1 and '9999' not in answer['sentences'][0]['text']


@pytest.mark.parametrize('timing',['before','during'])
def test_dependency_change_no_stale_text(service,monkeypatch,timing):
    if timing=='before':
        original=local.prepare
        def prepare(*args):
            result=original(*args);state(service,'evidence','count','blocked');return result
        monkeypatch.setattr(local,'prepare',prepare)
    async def changed(*args,**kwargs):
        state(service,'evidence','code','blocked')
        return await fake_model(*args,**kwargs)
    monkeypatch.setattr(local.GenerationService,'call_ollama',changed)
    result=local.search(service,request())
    assert result['status']=='stale' and result['answer'] is None
    assert not result['citations'] and not result.get('sentences') and not result['paths']
    assert result['metrics']['llm_calls']==(timing=='during')


@pytest.mark.parametrize('bad',['unknown','unlinked','length'])
def test_bad_citation_or_truncation_fails_once(service,monkeypatch,bad):
    async def broken(*args,**kwargs):
        result=await fake_model(*args,**kwargs)
        answer=json.loads(result['text'])
        if bad=='length':result['done_reason']='length'
        elif bad=='unknown':answer['selected_group_ids']=['missing']
        else:answer['text']='범위 밖 자유 문장'
        result['text']=json.dumps(answer);return result
    monkeypatch.setattr(local.GenerationService,'call_ollama',broken)
    with pytest.raises(GenerationError):local.search(service,request())
    with service.repository.connect() as db:
        run=json.loads(db.execute('SELECT payload FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()[0])
        assert run['status']=='failed' and run['metrics']['llm_calls']==1


def test_ambiguity_scope_and_two_hop_direction(service):
    with service.repository.connect() as db:
        snapshot=service.repository.get(db,'snapshots',local.ss._state(db)['active_snapshot_id'])
    link=snapshot['links']['link1']; other=dict(link,id='link2',target_entity_id='entity2')
    snapshot['entities']['entity2']=dict(snapshot['entities']['entity1'],id='entity2',official_id='C002')
    roots,choices=local.resolve(snapshot,[link,other],'단지 세대수',[])
    assert not roots and choices==['entity1','entity2']
    with pytest.raises(ValueError):local.resolve(snapshot,[link],'단지',['entity2'])
    snapshot['entities'].update({i:dict(id=i,concept_id=i) for i in ('doc','agency','far')})
    edges=[dict(id='r1',subject_id='entity1',object_entity_id='doc'),dict(id='r2',subject_id='agency',object_entity_id='doc'),dict(id='r3',subject_id='agency',object_entity_id='far')]
    snapshot['assertions'].update({a['id']:a for a in edges})
    paths=local.paths_for(snapshot,edges,['entity1'])
    assert 'r3' not in paths and paths['r2']['edges'][-1]['subject_id']=='agency'
    assert len(paths['r2']['edges'])==2
    with pytest.raises(ValueError):local.search(service,request(source_ids=['outside']))


def test_unrelated_change_and_http_errors(service,monkeypatch):
    from app.api.routers import knowledge
    async def changed(*args,**kwargs):
        state(service,'evidence','other','blocked')
        return await fake_model(*args,**kwargs)
    monkeypatch.setattr(local.GenerationService,'call_ollama',changed)
    assert local.search(service,request())['status']=='answered'
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        url='/api/v1/knowledge/search'
        assert client.post(url,json={'query':'x','mode':'global'}).status_code==422
        assert client.post(url,json={'query':'x','mode':'local','source_ids':[]}).status_code==422
        assert client.post(url,json={'query':'C001','mode':'local','answer_variant':'C'}).status_code==422
        async def failed(*args,**kwargs):raise GenerationError('timeout',code='MODEL_TIMEOUT')
        monkeypatch.setattr(local.GenerationService,'call_ollama',failed)
        result=client.post(url,json={'query':'C001','mode':'local'})
        assert result.status_code==504 and result.json()['error']['code']=='MODEL_TIMEOUT'


def test_local_entity_scope_and_general_registry_free_run(service,monkeypatch):
    from app.knowledge import extraction, extraction_store as store
    from app.knowledge.schemas import RunRequest
    with service.repository.connect() as db:
        block=service.repository.get(db,'blocks','block1');block['evidence_id']='block1';block['locator']['format']='html'
        version=service.repository.get(db,'versions','v1');version.update(format='html',processing_status='parsed',latest_parse_run_id='run1')
        service.repository.save(db,'versions',version)
        db.execute('UPDATE blocks SET payload=? WHERE id=?',(json.dumps(block),'block1'))
    entity=store.register_local_entity(service,dict(ontology_version_id='ontology1',concept_id='Complex',name='단지',source_version_id='v1',evidence_ids=['block1'],actor='test',reason='문서내개체'))
    service.blocks=lambda source,version:dict(items=[block])
    async def empty(prompt,schema,run):
        payload=json.loads(prompt.split('INPUT:\n')[1])
        return dict(done=True,text=json.dumps({'units':[dict(unit_id=u['unit_id'],subject=dict(mention='단지',concept_id='Complex',official_id=None,evidence=[]),facts=[],reason='직접 검토') for u in payload['units']]}))
    monkeypatch.setattr(extraction,'model_call',empty)
    result=extraction.start(service,RunRequest(kind='extract',source_version_ids=['v1'],ontology_version_id='ontology1',local_entity_ids=[entity['id']]))
    service.executor.submit(lambda:None).result()
    with service.repository.connect() as db:
        run=service.repository.get(db,'runs',result['run_id'])
        assert run['status']=='succeeded' and run['metrics']['llm_calls']==1
        assert service.repository.get(db,'versions','v1')['latest_parse_run_id']=='run1'
        link=dict(mention='단지',concept_id='Complex',target_entity_id=entity['id'],method='manual',scope={'source_version_id':'v1'},evidence_ids=['block1'])
        schema=store._schema(service.repository,db,run)
        assert not store._link_errors(service.repository,db,link,run,schema)
        assert 'local_entity_not_in_frozen_scope' in store._link_errors(service.repository,db,link,dict(run,entities=[]),schema)


def test_html_row_context_keeps_distinct_tables():
    from app.knowledge.extraction_contract import text_units
    blocks=[dict(id=key,source_version_id='v',parse_run_id='p',text=key,locator=dict(format='html',element_path=table,row=row))
            for key,table,row in [('h','table1',0),('a','table1',5),('b','table1',5),('x','table2',5)]]
    groups=text_units(dict(frozen_blocks=blocks),dict(block_ids=['a','b','x']))
    assert [[b['id'] for b in g['blocks']] for g in groups]==[['h','a','b'],['x']]


def test_seed_alias_change_and_same_type_direct_path(service,monkeypatch):
    async def changed(*args,**kwargs):
        with service.repository.connect() as db:
            link=service.repository.get(db,'entity_links','link1');link.update(revision=2,review_status='rejected')
            service.repository.save(db,'entity_links',link)
        return await fake_model(*args,**kwargs)
    monkeypatch.setattr(local.GenerationService,'call_ollama',changed)
    assert local.search(service,request())['status']=='stale'
    assert local.search(service,request())['metrics']['llm_calls']==0
    edges=[dict(id='r',subject_id='a',object_entity_id='b',predicate_id='connects'),dict(id='v',subject_id='b',object_entity_id=None)]
    snapshot=dict(entities={i:dict(concept_id='Same') for i in ['a','b']},assertions={a['id']:a for a in edges})
    assert local.paths_for(snapshot,edges,['a'])['v']['entity_ids']==['a','b']
    assert local.paths_for(snapshot,edges,['a','b'])['v']['entity_ids']==['b']


def test_reviewed_values_stay_with_their_source_and_all_conditions(service):
    with service.repository.connect() as db:
        snapshot=service.repository.get(db,'snapshots',local.ss._state(db)['active_snapshot_id'])
    original=snapshot['assertions']['count1']
    snapshot['sources']['source2']=dict(id='source2',title='별도 CSV')
    snapshot['versions']['v2']=dict(id='v2',source_id='source2',dates=[dict(role='자료 기준일',value='2026-08-10')])
    snapshot['evidence']['csv']=dict(snapshot['evidence']['count'],id='csv',source_version_id='v2',quote='990')
    snapshot['assertions']['csv']=dict(original,id='csv',value=990,unit='세대',evidence_ids=['csv'],field_evidence={},scope={'description':'CSV 범위'})
    condition='이전 선정: 비분양전환 공공임대. 다음 청약: 비분양전환 공공임대, 분양전환 공공임대, 공공분양.'
    snapshot['assertions']['explanation']=dict(original,id='explanation',value=condition,unit=None,
        conditions=['동일 통장'],exceptions=['개별 자격 판정 제외'],dates=[dict(role='적용일',value='2026-01-01')])
    sentences={s['assertion_ids'][0]:s for s in local.render_facts(snapshot,['count1','csv','explanation'])}
    assert '990' not in sentences['count1']['text'] and '별도 CSV' not in sentences['count1']['text']
    assert '990 세대' in sentences['csv']['text'] and '2026-08-10' in sentences['csv']['text']
    assert sentences['csv']['evidence_ids']==['csv']
    assert condition in sentences['explanation']['text']
    assert all(v in sentences['explanation']['text'] for v in ['동일 통장','개별 자격 판정 제외','2026-01-01'])


def test_bundle_keeps_comparison_and_path_without_sibling_expansion():
    # A -> document -> agency; unrelated document -> branch must not be pulled in.
    assertions={i:dict(subject_id=s,predicate_id=p) for i,s,p in
        [('count_old','a','count'),('count_new','a','count'),('r1','a','requires'),('r2','doc','issuer'),('unrelated','doc','branch')]}
    groups={('a','count'):{'count_old','count_new'},('a','requires'):{'r1'},
            ('doc','issuer'):{'r1','r2'},('doc','branch'):{'r1','unrelated'}}
    assert local.complete_bundle({'count_new'},groups,assertions)=={'count_old','count_new'}
    assert local.complete_bundle({'r2'},groups,assertions)=={'r1','r2'}
    assert local.complete_bundle({'r1'},groups,assertions)=={'r1'}


def test_no_selection_and_no_free_text_escape(service,monkeypatch):
    async def empty(*args,**kwargs):
        return dict(done=True,done_reason='stop',text=json.dumps(dict(selected_group_ids=[])))
    monkeypatch.setattr(local.GenerationService,'call_ollama',empty)
    result=local.search(service,request())
    assert result['status']=='insufficient' and not result['citations'] and not result['paths']
    assert result['coverage']['not_selected_assertion_ids']==['count1'] and result['coverage']['partial']
    assert result['metrics']['llm_calls']==1
    async def injected(*args,**kwargs):
        value=await fake_model(*args,**kwargs);body=json.loads(value['text']);body['text']='다른 출처 990으로 합성'
        value['text']=json.dumps(body);return value
    monkeypatch.setattr(local.GenerationService,'call_ollama',injected)
    with pytest.raises(GenerationError):local.search(service,request())


def test_nonrecommended_context_stays_visible_with_its_evidence(service,monkeypatch):
    original=local.prepare
    def prepared(*args):
        response,snapshot,chosen,dependencies,(prompt,groups)=original(*args)
        context=dict(chosen[0],id='context',value=6,unit='동',scope={'description':'함께 조회된 동수'},field_evidence={})
        snapshot['assertions']['context']=context
        response['paths'].append(dict(entity_ids=['entity1'],assertion_ids=['context'],edges=[]))
        response['coverage']['selected_assertion_count']=2
        groups['g2']=['context']
        return response,snapshot,chosen+[context],dependencies+[context],(prompt,groups)
    monkeypatch.setattr(local,'prepare',prepared)
    monkeypatch.setattr(local.GenerationService,'call_ollama',fake_model)
    result=local.search(service,request())
    assert result['coverage']['recommended_assertion_ids']==['count1']
    assert result['coverage']['context_assertion_ids']==['context']
    assert result['coverage']['not_selected_assertion_ids']==[]
    context=next(s for s in result['sentences'] if s['section']=='context')
    assert '6 동' in context['text'] and context['evidence_ids']
    assert '함께 조회된 맥락' in result['answer']
    assert {i for p in result['paths'] for i in p['assertion_ids']}==set(result['assertion_ids'])

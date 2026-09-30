"""A2 boundaries with deterministic model doubles; real-model evidence is in the runbook."""
from copy import deepcopy
import json
import re
from threading import Event
from time import monotonic, sleep

import pytest

from app.knowledge import discovery_analysis as a2, discovery_profile as profile, discovery_run, snapshots
from app.knowledge.schemas import RunRequest
from app.knowledge.discovery_models import Action
from app.generation.service import local_ollama_url
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def done(service, rid):
    deadline = monotonic()+15
    while monotonic() < deadline:
        run = service.run(rid)
        if run['status'] not in {'queued','running','cancel_requested'}: return run
        sleep(.01)
    raise AssertionError('작업 미종료')


def request(rid, **kwargs):
    return RunRequest(kind='discovery', discovery_mode='analyze', input_run_id=rid,
        cqs=[dict(id='cq1', question='임대 유형과 조건은 무엇인가?')], **kwargs)


def response(prompt, stage):
    data = json.loads(prompt.split('\nINPUT:\n')[1])
    ev = next((b['ref'] for b in data.get('blocks', [])), 'e0')
    action = dict(action='finish', reason='제공 범위 분석 종료')
    if stage=='scout':
        return dict(findings=['자료 구조 조사'], gaps=[], actions=[action])
    if stage=='concept':
        rows = [dict(local_ref=f'o{i}', label=label, classification='type', definition='선택 원문의 임대 유형',
            support_type='explicit', abstraction_level='업무 유형', review_signals=['사례 부족은 검토 신호'],
            evidence_ids=[ev], cq_ids=['cq1'], scope_item_ids=[], outside_scope_reason='') for i,label in enumerate(['국민임대','임대'], 1)]
        return dict(observations=rows, alignments=[], gaps=[], actions=[])
    if stage=='relation':
        return dict(relations=[dict(local_ref='r1', subject='국민임대', predicate='유형', object='임대',
            direction='subject_to_object', negation='affirmed', conditions='원문 범위', time='미확인',
            statement_type='definition', evidence_ids=[ev], cq_ids=['cq1'], scope_item_ids=[], outside_scope_reason='')], gaps=[], actions=[])
    if stage=='builder':
        obs = data['unapproved_observations']
        direction = dict(judgment='unknown', reason='정의 문맥 검수 필요', evidence_ids=[ev], counter_evidence_ids=[])
        return dict(hierarchies=[dict(child_ref=obs[0]['id'], parent_ref=obs[1]['id'], relation='is_a',
            a_to_b=direction, b_to_a=direction)], alias_proposals=[], gaps=[], actions=[])
    hierarchy = [{k:h[k] for k in ('child_ref','parent_ref','relation','a_to_b','b_to_a')} for h in data['taxonomy']['hierarchies']]
    return dict(issues=[], hierarchy_checks=hierarchy, gaps=['의미는 사람 검수 필요'], actions=[], needs_revision=False)


@pytest.fixture(autouse=True)
def model(monkeypatch):
    calls = []
    monkeypatch.setattr(a2, 'model_identity', lambda recipe: {'fixture':'digest'})
    async def fake(prompt, schema, stage, run, timeout):
        calls.append(stage)
        return dict(text=json.dumps(response(prompt,stage),ensure_ascii=False), done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2, 'model_call', fake)
    from app.retrieval.pipeline.stages import bm25_retriever
    monkeypatch.setattr(bm25_retriever, '_tokenize_korean', lambda texts: [re.findall(r'\w+', t) for t in texts])
    return calls


def test_full_roles_frozen_evidence_and_no_publication(service, model, monkeypatch):
    source = prepare(service, file_ids=['current:0'])
    before = service.sources()
    run = done(service, service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready', (run.get('error'),run['result']['failures'],run['frontier'])
    assert model==['scout','concept','relation','builder','critic']
    assert run['metrics']['llm_calls']==5 and run['metrics']['searches']==2
    assert run['result']['mandatory_pending']==[] and run['result']['analysis_succeeded']==2
    candidate=run['result']['observations'][0]
    assert candidate['review_status']=='unreviewed' and candidate['cq_ids']==['cq1']
    ref=candidate['evidence_refs'][0]
    assert service.evidence(ref['evidence_id'])['block']['text']==ref['quote']
    assert service.sources()==before
    assert a2.terms(service,run['id'],'국민')['items'][0]['id']==candidate['id']
    assert discovery_run.search(service,run['id'],'국민임대')['items']
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM ontology_versions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM changesets').fetchone()[0]==0
    from app.knowledge import discovery_inputs, parsers
    discovery_inputs.MANIFEST.write_text('{}')
    monkeypatch.setattr(parsers,'parse_unit',lambda *args: pytest.fail('재파싱'))
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert again['status']=='review_ready',again['result']['failures']
    assert model==['scout','concept','relation','builder','critic']
    assert again['result']['observations'][0]['id']==candidate['id']


def test_cancel_commits_current_call_and_resume_success_units(service, monkeypatch, model):
    source=prepare(service,file_ids=['current:0']); entered,release=Event(),Event()
    original=a2.model_call
    async def slow(prompt,schema,stage,run,timeout):
        if stage=='concept':
            assert all(v['properties']['alignments']['maxItems']==0 for v in schema['anyOf'])
            entered.set(); assert release.wait(5)
        return await original(prompt,schema,stage,run,timeout)
    monkeypatch.setattr(a2,'model_call',slow)
    rid=service.start(request(source['id']))['run_id']; assert entered.wait(5)
    service.cancel(rid);release.set()
    cancelled=done(service,rid)
    assert cancelled['status']=='cancelled' and model==['scout','concept']
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=rid))['run_id'])
    assert resumed['status']=='review_ready',resumed['result']['failures']
    assert model==['scout','concept','relation','builder','critic']
    assert resumed['metrics']['llm_calls']==5


@pytest.mark.parametrize('failure',['truncated','json','empty'])
def test_failure_not_empty_success_and_attempts_counted(service,monkeypatch,model,failure):
    source=prepare(service,file_ids=['current:0']); original=a2.model_call
    async def broken(prompt,schema,stage,run,timeout):
        data=await original(prompt,schema,stage,run,timeout)
        if stage=='concept':
            if failure=='truncated': data['done_reason']='length'
            elif failure=='json':data['text']='{'
            else:data['text']=json.dumps(dict(observations=[],alignments=[],gaps=[],actions=[]))
        return data
    monkeypatch.setattr(a2,'model_call',broken)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and run['result']['mandatory_pending']
    assert run['metrics']['llm_calls']==2 and run['result']['observations']==[]
    assert run['analysis_units'][-1]['attempts'][-1]['outcome']=='failed'
    monkeypatch.setattr(a2,'model_call',original)
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert resumed['status']=='review_ready',resumed['result']['failures']
    assert resumed['metrics']['llm_calls']==6


def test_budget_reserves_builder_critic_and_no_automatic_expansion(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets={'model_calls':4}))['run_id'])
    assert run['status']=='partial' and model==['scout']
    assert run['frontier'][0]['error'].endswith('부족')
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert resumed['metrics']['llm_calls']==1 and resumed['status']=='partial'
    with pytest.raises(ValueError):
        service.start(RunRequest(kind='discovery',retry_of_run_id=run['id'],discovery_budgets={'model_calls':48}))


def test_blocked_source_cannot_reuse_profile_candidates_or_terms(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    vid=source['input_version_ids'][0]
    snapshots.set_availability(service,dict(actor='test',reason='사용 중단',expected_status_revision=0,
        targets=[dict(type='source_version',id=vid)],state='blocked'))
    assert a2.terms(service,run['id'],'국민')['items']==[]
    assert discovery_run.search(service,run['id'],'국민')['items']==[]
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert resumed['status']=='partial' and len(model)==5
    assert resumed['result']['observations']==[] and resumed['result']['unavailable_block_ids']


def test_scope_tools_and_historical_registry_boundary(service):
    source=prepare(service,scope='historical_change')
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);index=a2.frozen_index(service,run,blocks)
    assert discovery_run.search(service,run['id'],'통합공공임대')['items']==[]
    assert a2.terms(service,run['id'],'미래')['items']==[]
    with pytest.raises(ValueError,match='scope/step'):
        discovery_run.search(service,run['id'],'임대',step=1)
    with pytest.raises(ValueError,match='범위 밖'):
        a2.dispatch(service,run,index,blocks,dict(action='read',unit_id='future:0',reason='미래'))
    with pytest.raises(ValueError):Action(action='shell',reason='실행')
    with pytest.raises(ValueError):Action(action='read',unit_id='x',query='외부',reason='실행')


def test_csv_greedy_coverage_and_table_context():
    def row(i,text):
        return dict(id=str(i),source_version_id='v',text=text,locator=dict(format='csv',physical_row=i,column_names=['유형','명칭']))
    blocks=[row(2,'유형: 국민\n명칭: A'),row(3,'유형: 국민\n명칭: B'),row(4,'유형: 국민/영구\n명칭: ')]
    value=profile.csv_profile(blocks)
    assert value['row_count']==3 and value['fields']['명칭']['missing']==1
    assert value['selected'][0]['block_id']=='4'
    assert value['uncovered_features']==[]
    assert value['selected']==profile.csv_profile(list(reversed(blocks)))['selected']
    cells=[dict(id=str(i),source_version_id='v',text=t,locator=dict(format='html',element_path='table',row=r,column=c,table_caption='조건',merged_span={'rows':1,'columns':1}))
           for i,(t,r,c) in enumerate([('유형',0,0),('조건',0,1),('국민',1,0),('제외',1,1)])]
    context=profile.contexts(cells)['2']
    assert set(context['block_ids'])=={'0','1','2','3'} and context['status']=='unconfirmed'


@pytest.mark.parametrize('url',['https://localhost:11434','http://example.com','http://127.0.0.1/x','http://user@localhost:11434','http://localhost:11434?x=1'])
def test_local_endpoint_only(url):
    with pytest.raises(ValueError):local_ollama_url(url)
    assert local_ollama_url('http://localhost:11434')=='http://127.0.0.1:11434'


def test_scout_profile_is_not_raw_read(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets={'model_calls':1}))['run_id'])
    assert model==['scout']
    assert run['result']['structure_surveyed']==2
    assert run['result']['raw_provided']==0 and len(run['result']['unvisited_block_ids'])==2


def test_all_observed_business_categories_including_mixed_are_covered():
    blocks=[dict(id=str(i),source_version_id='v',text=f'주택유형: 유형{i}/혼합\n단지코드: C{i}',
        locator=dict(format='csv',physical_row=i,column_names=['주택유형','단지코드'])) for i in range(66)]
    result=profile.csv_profile(blocks)
    assert len(result['fields']['주택유형']['observed_categories'])==66
    assert len(result['selected'])==66 and result['uncovered_features']==[]
    assert result['fields']['단지코드']['observed_categories'] is None
    assert '미선정' in result['fields']['단지코드']['category_basis']


def test_tools_feed_next_role_and_recheck_revocation(service,monkeypatch):
    source=prepare(service,file_ids=['current:0','web:0'])
    original=a2.model_call; seen=[]
    async def requesting(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);seen.append((stage,data))
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='concept':
            value=json.loads(result['text'])
            value['actions']=[dict(action='search',query='예외',reason='예외 원문 확인')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',requesting)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready',run['result']['failures']
    relation=next(data for stage,data in seen if stage=='relation' and data['tool_originals'])
    assert any('예외' in b['text'] for b in relation['tool_originals'])
    relation_unit=next(u for u in run['analysis_units'] if u['stage']=='relation' and len(u['dependency_ids'])>2)
    assert len(relation_unit['dependency_ids'])>2
    # Lookup result is comparison material with its original dependency, not an approved definition.
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    contexts=profile.contexts(blocks)
    result=a2.dispatch(service,run,a2.frozen_index(service,run,blocks),blocks,
        dict(action='lookup_term',label='국민',reason='이전 후보 비교'))
    context,deps,terms=a2.with_tool_context(service,run,{},[],[dict(tool_results=[result])],by_id,contexts)
    assert terms and context['comparison_terms'][0]['review_status']=='unreviewed' and deps
    snapshots.set_availability(service,dict(actor='test',reason='중단',expected_status_revision=0,
        targets=[dict(type='evidence',id=deps[0])],state='blocked'))
    with pytest.raises(ValueError,match='사용 중단'):
        a2.with_tool_context(service,run,{},[],[dict(tool_results=[result])],by_id,contexts)


def test_unavailable_during_call_excludes_output(service,monkeypatch):
    source=prepare(service,file_ids=['current:0']); original=a2.model_call
    async def revoke(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='concept':
            snapshots.set_availability(service,dict(actor='test',reason='중단',expected_status_revision=0,
                targets=[dict(type='source_version',id=source['input_version_ids'][0])],state='blocked'))
        return result
    monkeypatch.setattr(a2,'model_call',revoke)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and run['result']['observations']==[]
    assert run['metrics']['llm_calls']==2 and '호출 중' in run['result']['failures'][0]['error']


def test_interrupted_attempt_records_unknown_time_reserve(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    from app.knowledge.service import KnowledgeService
    with service.repository.connect() as db:
        saved=service.repository.get(db,'runs',run['id'])
        saved['status']='running';saved['analysis_units'][-1]['status']='running'
        saved['analysis_units'][-1]['attempts'][-1]=dict(started_at='unknown',outcome='started',timeout_s=360)
        service.repository.save(db,'runs',saved)
    service.shutdown()
    restarted=KnowledgeService(service.repository.path)
    try:
        recovered=restarted.run(run['id'])
        assert recovered['analysis_units'][-1]['attempts'][-1]['outcome']=='interrupted_before_result_commit'
        assert recovered['metrics']['interrupted_time_reserve_s']==360
        assert recovered['metrics']['model_total_s']==run['metrics']['model_total_s']
    finally:restarted.shutdown()


def test_alias_unknown_references_stay_invalid():
    output=dict(hierarchies=[],alias_proposals=[dict(observation_ref='unknown',target_id='also_unknown',reason='표기 유사')],gaps=[],actions=[])
    normalized=a2.normalize(output,'builder',dict(cqs=[],scope_items=[]),[],{}, {})
    assert normalized['alias_proposals'][0]['validation']
    assert normalized['alias_proposals'][0]['review_status']=='unreviewed'


def test_scout_read_resume_keeps_frozen_input_hash(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def choose(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='scout':
            data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
            value['actions']=[dict(action='read',unit_id=data['frontier'][0]['id'],reason='정의 확인')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',choose)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready'
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert resumed['status']=='review_ready',resumed['result']['failures']
    assert len(model)==5


def test_discovery_api_and_complete_object_output_schema(service,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def schema_check(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1])
        action_variants=schema['$defs']['Action']['anyOf']
        read=next(v for v in action_variants if v['properties']['action']['const']=='read')
        assert read['properties']['unit_id']['enum']==[g['id'] for g in run['frontier']]
        if stage=='concept':
            # Ollama uses union branches directly: every branch must contain the full object.
            for variant in schema['$defs']['Observation']['anyOf']:
                assert {'evidence_ids','label','classification','local_ref','definition'} <= set(variant['required'])
        import jsonschema
        empty={k:[] for k in response(prompt,stage) if k!='needs_revision'}
        if stage=='critic': empty['needs_revision']=False
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(empty,schema)
        valid=dict(empty,gaps=['주 분석 원문의 해석 미확인'])
        if stage=='critic':
            valid['hierarchy_checks']=response(prompt,stage)['hierarchy_checks']
            assert all(v['properties']['hierarchy_checks']['minItems']==len(data['taxonomy']['hierarchies']) for v in schema['anyOf'])
            for variant, expected in zip(schema['$defs']['Hierarchy']['anyOf'],data['taxonomy']['hierarchies']):
                assert all(variant['properties'][f]['const']==expected[f] for f in ('child_ref','parent_ref','relation'))
        jsonschema.validate(valid,schema)
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            assert all('local_ref' not in c for c in data['unapproved_observations'])
            hierarchy_id=data['taxonomy']['hierarchies'][0]['id']
            refs=schema['$defs']['Issue']['properties']['candidate_ref']['enum']
            assert hierarchy_id in refs and '' in refs
            value=json.loads(result['text'])
            value['issues']=[dict(local_ref='i1',candidate_ref=hierarchy_id,defer_reason='사람 검수 필요',reason='방향 재검수 필요',
                evidence_ids=[data['blocks'][0]['ref']],counter_evidence_ids=[])]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',schema_check)
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    with TestClient(app) as client:
        started=client.post('/api/v1/knowledge/runs',json=request(source['id']).model_dump(exclude_unset=True))
        assert started.status_code==200
        run=done(service,started.json()['data']['run_id']);assert run['status']=='review_ready'
        result=client.get('/api/v1/knowledge/runs/'+run['id']).json()
        assert result['success'] and result['data']['analysis_counts']['succeeded']==5
        assert client.get('/api/v1/knowledge/discovery/terms',params=dict(run_id=run['id'],label='국민')).json()['data']['items']
        found=client.get('/api/v1/knowledge/discovery/search',params=dict(run_id=run['id'],q='국민임대')).json()['data']['items'][0]
        assert found['source_id'] and found['block_index']==0


def test_request_evidence_resolves_real_issue_and_rejects_unknown(service,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def request_context(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text'])
            value['issues']=[dict(local_ref='i1',candidate_ref='',reason='공식 대응 자료 필요',
                evidence_ids=[],counter_evidence_ids=[],defer_reason='자료 미제공')]
            value['actions']=[dict(action='request_evidence',issue_id='i1',query='존재하지않는자료',reason='공식 대응 확인')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',request_context)
    run=done(service,service.start(request(source['id']))['run_id'])
    issue=run['result']['critiques'][0]['issues'][0]
    event=next(e for e in run['tool_events'] if e['action']=='request_evidence')
    assert issue['id'].startswith('di_') and event['issue_id']==issue['id']==event['result']['issue_id']
    blocks=a2.load_blocks(service,run)
    with pytest.raises(ValueError,match='쟁점 ID 불일치'):
        a2.dispatch(service,run,a2.frozen_index(service,run,blocks),blocks,
            dict(action='request_evidence',issue_id='invented',query='임대',reason='추가 확인'))


def test_explicit_gap_is_preserved_but_not_counted_as_grounded_analysis(service,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def no_relation(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='relation':
            result['text']=json.dumps(dict(relations=[],gaps=['이번 원문의 관계를 확정할 근거 부족'],actions=[]))
        return result
    monkeypatch.setattr(a2,'model_call',no_relation)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and run['result']['mandatory_pending']
    assert run['result']['review_groups']==1 and run['result']['analysis_succeeded']==0
    assert run['result']['gaps'] and run['result']['failures']==[]


@pytest.mark.parametrize('stage',['builder','critic'])
@pytest.mark.parametrize('gap',[[],[' ']])
def test_empty_design_or_review_is_not_success(service,monkeypatch,stage,gap):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def empty(prompt,schema,current,run,timeout):
        result=await original(prompt,schema,current,run,timeout)
        if current==stage:
            value=json.loads(result['text'])
            value={k:False if k=='needs_revision' else [] for k in value}
            value['gaps']=gap
            result['text']=json.dumps(value)
        return result
    monkeypatch.setattr(a2,'model_call',empty)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and run['result']['mandatory_pending']
    assert any('빈' in f['error'] for f in run['result']['failures'])


def test_exhausted_resume_preserves_successful_analysis_counts(service,monkeypatch):
    original=a2.model_call
    async def truncated_review(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':result['done_reason']='length'
        return result
    monkeypatch.setattr(a2,'model_call',truncated_review)
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets={'model_calls':5}))['run_id'])
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert run['result']['analysis_succeeded']==resumed['result']['analysis_succeeded']==2
    assert run['metrics']['llm_calls']==resumed['metrics']['llm_calls']==5
    assert resumed['status']=='partial' and resumed['result']['mandatory_pending']

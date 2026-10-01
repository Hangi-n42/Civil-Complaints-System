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
            endpoint_labels=dict(subject='국민임대',object='임대'),
            direction='subject_to_object', negation='affirmed', conditions='원문 범위', time='미확인',
            statement_type='definition', evidence_ids=[ev], cq_ids=['cq1'], scope_item_ids=[], outside_scope_reason='')], gaps=[], actions=[])
    if stage=='builder':
        obs = data['unapproved_observations']
        direction = dict(judgment='unknown', reason='정의 문맥 검수 필요', evidence_ids=[ev], counter_evidence_ids=[])
        return dict(hierarchies=[dict(child_ref=obs[0]['id'], parent_ref=obs[1]['id'], relation='is_a',
            a_to_b=direction, b_to_a=direction)], alias_proposals=[], gaps=[], actions=[],
            relation_bindings=[dict(relation_ref=i,subject_ref=obs[0]['id'],object_ref=obs[1]['id'],reason='제공 정의로 연결') for i in data.get('design_relation_ids', [])])
    if stage=='revision':
        return dict(observations=[],relations=[],hierarchies=[],deferred=[dict(candidate_ref=i,reason='사람 검수로 명시 보류한다.') for i in data['target_ids']])
    hierarchy = [{k:h[k] for k in ('child_ref','parent_ref','relation','a_to_b','b_to_a')} for h in data['taxonomy']['hierarchies']]
    def checks(rows):
        return [dict(candidate_ref=c['id'],judgment='supported',evidence_id=c['evidence_ids'][0],
            quote=next(b['text'] for b in data['blocks'] if b['ref']==c['evidence_ids'][0]),reason='선택 원문과 비교했다.',
            **(dict(semantic_checks={k:'supported' for k in ('subject','object','conditions','statement_type')}) if 'negation' in c else {}))
            for c in rows if c['id'] in data.get('review_target_ids',[c['id']])]
    return dict(issues=[], missing_meanings=[], hierarchy_checks=hierarchy,
        relation_checks=checks(data['unapproved_relations']), observation_checks=checks(data['unapproved_observations']),
        gaps=['의미는 사람 검수 필요'], actions=[], needs_revision=False)


def source_response(value, data):
    """Express the legacy test double through the new generation-only citation schema."""
    views=a2.segments.originals(data)
    def convert(row):
        if isinstance(row,list): return [convert(v) for v in row]
        if not isinstance(row,dict): return row
        result={k:convert(v) for k,v in row.items() if k not in {'evidence_ids','counter_evidence_ids','evidence_id','quote','source_quotes'}}
        if any(k in row for k in ('evidence_ids','source_refs','evidence_id')):
            ids=row.get('evidence_ids', [])+([row['evidence_id']] if row.get('evidence_id') else [])
            result['source_refs']=list(dict.fromkeys(row.get('source_refs', [])+[v['source_ref'] for i in ids for v in views if v['ref']==i]))
        if 'counter_evidence_ids' in row:
            result['counter_source_refs']=[v['source_ref'] for i in row['counter_evidence_ids'] for v in views if v['ref']==i]
        if 'relation_ref' in row: result.setdefault('decision','bind')
        return result
    return convert(value)


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
    assert run['result']['mandatory_pending']==[] and run['result']['analysis_succeeded']==1
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


@pytest.mark.parametrize('scope_only', [False, True])
def test_empty_cq_or_scope_selection_has_no_empty_ollama_enum(service, monkeypatch, scope_only):
    source = prepare(service, file_ids=['current:0'])
    original = a2.model_call
    seen = []
    async def check(prompt, schema, stage, run, timeout):
        def walk(value):
            if isinstance(value, dict):
                assert value.get('enum') != []  # Ollama rejects this even when JSON Schema accepts it.
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        walk(schema)
        if stage == 'concept':
            seen.append(stage)
            empty = 'cq_ids' if scope_only else 'scope_item_ids'
            for variant in schema['$defs']['Observation']['anyOf']:
                assert variant['properties'][empty]['maxItems'] == 0
                assert not variant['properties'][empty].get('minItems')
        result = await original(prompt, schema, stage, run, timeout)
        if scope_only:
            value = json.loads(result['text'])
            def swap(row):
                if isinstance(row, dict):
                    if 'cq_ids' in row: row.update(cq_ids=[], scope_item_ids=['scope1'])
                    for child in row.values(): swap(child)
                elif isinstance(row, list):
                    for child in row: swap(child)
            swap(value)
            result['text'] = json.dumps(value, ensure_ascii=False)
        return result
    monkeypatch.setattr(a2, 'model_call', check)
    field = 'scope_items' if scope_only else 'cqs'
    run = done(service, service.start(RunRequest(kind='discovery', discovery_mode='analyze', input_run_id=source['id'],
        **{field: [dict(id='scope1' if scope_only else 'cq1', question='유형과 조건은?')]}))['run_id'])
    assert seen and run['status']=='review_ready', run['result']['failures']


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
                assert {'source_refs','label','classification','local_ref','definition'} <= set(variant['required'])
        import jsonschema
        empty={k:[] for k in response(prompt,stage) if k!='needs_revision'}
        if stage=='critic': empty['needs_revision']=False
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(empty,schema)
        valid=dict(empty,gaps=['주 분석 원문의 해석 미확인'])
        if stage=='builder': valid.update(relation_bindings=response(prompt,stage)['relation_bindings'],observations=[])
        if stage=='critic':
            valid['hierarchy_checks']=response(prompt,stage)['hierarchy_checks']
            valid['relation_checks']=response(prompt,stage)['relation_checks']
            valid['observation_checks']=response(prompt,stage)['observation_checks']
            assert all(v['properties']['hierarchy_checks']['minItems']==len(data['taxonomy']['hierarchies']) for v in schema['anyOf'])
            for variant, expected in zip(schema['$defs']['Hierarchy']['anyOf'],data['taxonomy']['hierarchies']):
                assert all(variant['properties'][f]['const']==expected[f] for f in ('child_ref','parent_ref','relation'))
        jsonschema.validate(source_response(valid,data),schema)
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
        run=done(service,started.json()['data']['run_id']);assert run['status']=='partial',run['result']['failures']
        assert run['result']['unresolved_recovery_requests'][0]['cause']=='content_error'
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
    assert run['status']=='partial' and run['result']['no_result_groups']
    assert run['result']['processed_analysis_groups']==1
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
    assert run['result']['analysis_succeeded']==resumed['result']['analysis_succeeded']==1
    assert run['metrics']['llm_calls']==resumed['metrics']['llm_calls']==5
    assert resumed['status']=='partial' and resumed['result']['mandatory_pending']


def test_real_reviewed_base_uses_evidence_block_version_and_term_lookup(service):
    from app.knowledge import ontology_schema as ontology
    source=prepare(service,file_ids=['current:0'])
    block=discovery_run.read(service,source['id'],'current:0')['items'][0]
    base_run=dict(source,id='reviewed_base_run',kind='ontology',cqs=[dict(id='cq1',question='임대 유형은?')],
        frozen_blocks=[dict(evidence_id=block['evidence_id'],text=block['text'])])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)',(base_run['id'],json.dumps(base_run)))
        evidence=service.repository.get(db,'evidence',block['evidence_id'])
        assert 'source_version_id' not in evidence and evidence['block_id']==block['id']
    candidate=dict(id='Housing',kind='concept',name='국민임대',definition='현재 국민임대',inclusion='원문에 명시',exclusion='미확인',
        evidence=[dict(evidence_id=block['evidence_id'],quote='국민임대')],cq_ids=['cq1'])
    published=ontology.publish(service,base_run,[candidate])
    decision=ontology.decide(service,published['changeset_id'],dict(expected_changeset_revision=0,actor='tester',decisions=[dict(candidate_id='Housing',action='accept')]))
    run=done(service,service.start(request(source['id'],base_ontology_version_id=decision['reviewed_ontology_version_id']))['run_id'])
    assert run['status']=='review_ready',run.get('error')
    assert not run['result']['design_pending_relation_ids']
    term=next(c for c in a2.terms(service,run['id'],'국민')['items'] if c['id']=='Housing')
    assert term['review_status']=='reviewed'
    assert term['evidence'][0]['evidence_id']==block['evidence_id']
    other=prepare(service,file_ids=['web:0'])
    with pytest.raises(ValueError,match='범위 밖'):
        service.start(request(other['id'],base_ontology_version_id=decision['reviewed_ontology_version_id']))


def test_selected_analysis_cross_document_synthesis_and_honest_coverage(service,model):
    source=prepare(service,file_ids=['current:0','web:0'])
    blocks=a2.load_blocks(service,source)
    selected=[b['id'] for b in blocks if b['block_index']==0]
    with pytest.raises(ValueError,match='선택 이유'):
        service.start(request(source['id'],analysis_block_ids=selected))
    with pytest.raises(ValueError,match='고정 블록'):
        service.start(request(source['id'],analysis_block_ids=['outside'],analysis_selection_reason='작은 묶음'))
    run=done(service,service.start(request(source['id'],analysis_block_ids=selected,analysis_selection_reason='정의와 비교 원문의 첫 블록'))['run_id'])
    result=run['result']
    assert result['analysis_groups']==result['processed_analysis_groups']==2
    assert result['candidate_groups']==result['review_groups']==1
    assert model==['scout','concept','relation','concept','relation','builder','critic']
    group=run['candidate_groups'][0]
    assert len(group['analysis_group_ids'])==2
    assert len({c['evidence_ids'][0] for c in group['candidates']})==2
    assert all(c['review_status']=='unreviewed' for c in group['candidates'])
    assert result['analysis_succeeded']==2 and len(result['not_selected_block_ids'])==2
    assert set(result['both_roles_evidence_block_ids'])==set(selected)
    assert run['initial_full_analysis_groups']==2
    assert 'g는 후보 조립' in run['synthesis_call_formula']


@pytest.mark.parametrize('quote_valid', [True, False])
def test_revision_corrects_classification_negation_and_preserves_ids_and_history(service,monkeypatch,model,quote_valid):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def revise(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1])
        response_value=await original(prompt,schema,stage,run,timeout)
        value=json.loads(response_value['text'])
        if stage=='relation':
            value['relations'][0]['negation']='negated' # Saved v7 polarity failure shape.
        if stage=='critic':
            targets=[data['unapproved_observations'][0],data['unapproved_relations'][0],data['taxonomy']['hierarchies'][0]]
            value['issues']=[dict(local_ref=f'i{n}',candidate_ref=c['id'],reason='원문과 분류·부정·방향을 다시 대조한다.',evidence_ids=[data['blocks'][0]['ref']],counter_evidence_ids=[],defer_reason='') for n,c in enumerate(targets,1)]
            value['needs_revision']=True
        if stage=='revision':
            assert len(prompt)<=12000
            value=dict(observations=[],relations=[],hierarchies=[],deferred=[])
            for c in data['targets']:
                if 'classification' in c:
                    item={k:c[k] for k in a2.models.Observation.model_fields if k!='local_ref' and k in c}
                    text=next(b['text'] for b in data['blocks'] if b['ref']==c['evidence_ids'][0])
                    item['source_quotes']=[dict(evidence_id=c['evidence_ids'][0],quote=text[:2] if quote_valid else '이번 입력에 없는 인용')]
                    value['observations'].append(dict(item,local_ref='o1',candidate_ref=c['id'],reason='열 표기를 어휘로 보류 분류한다.',classification='vocabulary'))
                elif 'negation' in c:
                    item={k:c[k] for k in a2.models.Relation.model_fields if k!='local_ref' and k in c}
                    value['relations'].append(dict(item,local_ref='r1',candidate_ref=c['id'],reason='제외 조건은 관계 전체의 부정이 아니다.',negation='affirmed'))
                else:
                    item={k:c[k] for k in a2.models.Hierarchy.model_fields}
                    value['hierarchies'].append(dict(item,candidate_ref=c['id'],reason='계층은 미확인으로 유지한다.'))
            import jsonschema
            jsonschema.validate(source_response(value,data),schema)
        response_value['text']=json.dumps(value,ensure_ascii=False)
        return response_value
    monkeypatch.setattr(a2,'model_call',revise)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert model.count('revision')==1,run['result']['failures']
    assert len(run['result']['revision_history'])==3,run['result']['failures']
    for history in run['result']['revision_history']:
        assert history['before']['id']==history['after']['id']==history['candidate_id']
    original_row=run['result']['original_observations'][0]
    revised=next(c for c in run['result']['observations'] if c['id']==original_row['id'])
    assert run['result']['original_relations'][0]['negation']=='negated'
    assert run['result']['relations'][0]['negation']=='affirmed'
    assert original_row['classification']=='type' and revised['classification']=='vocabulary'
    terms=a2.terms(service,run['id'],'국민')['items']
    if quote_valid:
        assert next(c for c in terms if c['id']==revised['id'])['classification']=='vocabulary'
        assert len(revised['evidence_refs'][0]['quote'])==2 and revised['evidence_refs'][0]['span']==[0,2]
    else:
        assert revised['validation'] and not revised['evidence_refs']
        assert not any(c['id']==revised['id'] for c in terms)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model.count('revision')==1 and again['result']['revision_history']==run['result']['revision_history']
    assert run['status']==again['status']=='partial'
    assert revised['id'] in again['result']['unreviewed_candidate_ids']
    from app.knowledge import ontology_changes as a3
    from app.tests.unit.test_knowledge_ontology_changes import listing
    cid=a3.publish(service,again['id'])['changeset_id']
    changed={h['candidate_id'] for h in run['result']['revision_history']}
    candidates=[c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id') in changed]
    assert candidates and all(c['origin'].get('review_errors') and not c['can_accept'] for c in candidates)
    assert all(not c['origin']['relation_checks'] and not c['origin']['critiques'] for c in candidates)
    assert all(not c['hierarchy_review'].get('critic') for c in candidates)



def test_revision_bounded_whole_sources_or_explicit_deferral(service,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def issue(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);value['needs_revision']=True
            value['gaps']=['검토 전체 이력 '*2000] # Prior overflowing context must not propagate wholesale.
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',issue)
    run=done(service,service.start(request(source['id']))['run_id'])
    revision=next(u for u in run['analysis_units'] if u['stage']=='revision')
    assert revision['status']=='succeeded' and revision['input_chars']<=12000
    assert revision['output']['deferred'] and not revision['output']['history']
    payload=json.loads(revision['prompt'].split('\nINPUT:\n')[1])
    assert all(b['text'] in {b['text'] for b in a2.load_blocks(service,run)} for b in payload['blocks'])


def test_relation_review_rejects_invented_quote_and_requires_every_relation(service,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def bad_quote(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);value['relation_checks'][0]['quote']='원문에 없는 주택법상 법률 단정'
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',bad_quote)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and not run['result']['failures']
    assert '인용' in run['result']['review_record_errors'][0]['reason']
    assert run['result']['relations'][0]['id'] in run['result']['unreviewed_candidate_ids']


@pytest.mark.parametrize('revise_design', [False,True])
def test_builder_role_designs_preserve_source_rules_and_atomic_review_bundle(service,corpus,monkeypatch,model,revise_design):
    from hashlib import sha256
    from app.knowledge import ontology_changes as a3, ontology_schema as v1
    from app.tests.unit.test_knowledge_ontology_changes import listing, decide
    # Frozen LH input, rule Art.15 block 1e4c6a6dfc69410b923e15b9e748efa4 (excerpt).
    # Deterministic modeling below tests the contract, not an LLM's legal interpretation.
    text='다음 각 호의 어느 하나에 해당하는 경우에는 국토교통부장관(제1호에 해당하는 경우로 한정한다) 또는 시ㆍ도지사(제2호에 해당하는 경우로 한정한다)는 제1항 및 제2항에도 불구하고 해당 지역의 실정을 고려하여 국민임대주택을 우선공급 받을 수 있는 대상자 및 그 공급비율과 입주자 선정 순위에 관한 기준을 별도로 정할 수 있다.'
    text+=' 1. 한국토지주택공사가 국민임대주택을 건설하여 공급하는 경우 2. 지방자치단체 또는 지방공사( 「지방공기업법」 제49조 에 따라 주택사업을 목적으로 설립된 지방공사를 말한다. 이하 같다)가 국민임대주택을 건설하여 공급하는 경우'
    path=corpus/'current.txt';path.write_text(text)
    manifest=corpus/'manifest.json';data=json.loads(manifest.read_text())
    data['selected_sources'][0]['input_files'][0]['sha256']=sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def design(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='concept':
            value['observations'][0].update(label='선정 기준',classification='vocabulary',definition='원문에 사용된 기준의 명칭')
            value['observations'][1].update(label='한국토지주택공사',classification='entity',definition='특정 기관')
        if stage=='relation':
            template=value['relations'][0]
            value['relations']=[dict(template,local_ref=f'r{i}',subject=actor,object='별도 선정 기준',
                predicate='별도로 정할 수 있다',statement_type='rule',time='선택 시행본',
                conditions=f'{i}호의 경우에 한정; 제1항 및 제2항에도 불구하고 지역 실정 고려; 다른 주체와 OR')
                for i,actor in enumerate(['국토교통부장관','시ㆍ도지사'],1)]
        if stage=='builder':
            relations=data['unapproved_relations'];ev=data['blocks'][0]
            value.update(hierarchies=[],observations=[dict(local_ref=f't{i}',label=name,classification='type',
                definition=f'선택 규범을 표현하기 위한 {name}',support_type='design_proposal',
                abstraction_level='업무 역할·대상 설계',review_signals=[],evidence_ids=[],source_refs=[ev['source_ref']],
                cq_ids=['cq1'],source_relation_ids=[r['id'] for r in relations],
                design_reason='제공 용어와 개별 기관은 재사용 가능한 역할/대상 유형이 아니므로 한정하여 설계')
                for i,name in enumerate(['제1호 기준 설정 역할','제2호 기준 설정 역할','별도 기준 대상'],1)],
                relation_bindings=[dict(relation_ref=r['id'],subject_ref=f't{i}',object_ref='t3',reason='원문의 주체별 분기를 별도 역할과 대상의 관계로 표현') for i,r in enumerate(relations,1)])
        if stage=='critic':
            assert len([c for c in data['unapproved_observations'] if c['support_type']=='design_proposal'])==3
            assert 'relation_bindings' not in data['taxonomy']
            assert all(c['source_relation']['statement_type']=='rule' and c['statement_type']=='design_proposal' for c in data['unapproved_relations'])
            if revise_design:
                target=next(c for c in data['unapproved_observations'] if c['support_type']=='design_proposal')
                value.update(needs_revision=True,issues=[dict(local_ref='i1',candidate_ref=target['id'],reason='설계 유형의 표현 점검',
                    evidence_ids=target['evidence_ids'],counter_evidence_ids=[],defer_reason='')])
        if stage=='revision':
            value=dict(observations=[],relations=[],hierarchies=[],deferred=[])
            for candidate in data['targets']:
                item={k:candidate[k] for k in a2.models.Observation.model_fields if k in candidate}
                value['observations'].append(dict(item,local_ref='o1',support_type='explicit',candidate_ref=candidate['id'],reason='잘못된 explicit 승격을 시도하는 회귀 출력'))

        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',design)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']==('partial' if revise_design else 'review_ready'),run['result']['failures']
    types=[c for c in run['result']['observations'] if c['classification']=='type']
    assert len(types)==3 and all(c['support_type']=='design_proposal' for c in types)
    assert all(r['statement_type']=='rule' for r in run['result']['original_relations'])
    assert set(run['candidate_groups'][0]['design_candidate_ids'])=={c['id'] for c in types}
    for relation in run['result']['relations']:
        assert relation['subject'] in {c['id'] for c in types} and relation['object'] in {c['id'] for c in types}
        for field in ('conditions','predicate','time','negation','evidence_refs'):
            assert relation[field]==relation['source_relation'][field]
    assert any(c['support_type']=='design_proposal' for c in a2.terms(service,run['id'],'역할')['items'])
    before=list(model);again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert before==model and again['result']['relations']==run['result']['relations']
    cid=a3.publish(service,again['id'])['changeset_id']
    change=listing(service,cid);rows=[c for c in change['candidates'] if c['target_kind'] in {'class','relation'}]
    relation=next(c for c in rows if c['target_kind']=='relation')
    dependency=next(c for c in rows if c['target_kind']=='class')
    decide(service,cid,[dict(candidate_id=dependency['id'],action='defer')])
    assert a3.preview(service,cid,[relation['id']])['status']=='invalid_preview'
    with pytest.raises(ValueError): decide(service,cid,[dict(candidate_id=relation['id'],action='accept')])
    # Individual form edits are saved first and never copied to the other candidates.
    for c in rows:
        decide(service,cid,[dict(candidate_id=c['id'],action='edit',patch={'rationale':'사람의 개별 검토: '+c['after']['name']})])
    ids=[c['id'] for c in rows]
    preview=a3.preview(service,cid,ids)
    assert preview['status']=='unreviewed_preview' and set(preview['included_change_ids'])==set(ids)
    assert not any(c['review_status']=='accepted' for c in listing(service,cid)['candidates'])
    accepted=decide(service,cid,[dict(candidate_id=i,action='accept') for i in ids])
    version=v1.get_ontology(service,accepted['reviewed_ontology_version_id'])
    targets=[c for c in version['targets'] if c['kind']=='relation']
    assert len(targets)==2 and all(t['support_type']=='design_proposal' and not t.get('required') for t in targets)
    for target in targets:
        raw=target['modeling_origin']['source_relation']
        assert raw['statement_type']=='rule' and raw['conditions']==target['qualifiers']['scope']
        assert raw['evidence_refs']==target['evidence_refs'] and raw['time']==target['qualifiers']['time']
    saved=listing(service,cid)
    assert len(saved['decisions'])==len(ids)*2+1 and saved['analysis_result']==again['result']
    assert all(d['actor']=='tester' for d in saved['decisions'])
    assert '별표' not in ' '.join(c['definition'] for c in types)
    with pytest.raises(ValueError,match='슬롯 필수값'):
        decide(service,cid,[dict(candidate_id=relation['id'],action='modify',patch={'after':dict(relation['after'],required=True)})])
    assert v1.get_ontology(service,version['id'])==version
    role=next(c for c in rows if c['target_kind']=='class')
    with pytest.raises(ValueError,match='원문 명시 정의로 승격'):
        decide(service,cid,[dict(candidate_id=role['id'],action='modify',patch={
            'support_type':'explicit','qualifiers':dict(role['qualifiers'],statement_type='definition')})])


@pytest.mark.parametrize('kind', ['type','entity','vocabulary','property_value','missing','invalid','ambiguous'])
def test_builder_bindings_only_use_supplied_valid_types(kind):
    from app.knowledge import discovery_design as design
    source=dict(id='rule',statement_type='rule',subject='원문 역할',object='원문 대상',conditions='조건 A 또는 B',
        negation='affirmed',validation=[],evidence_ids=['b'])
    target=dict(id='existing',classification=kind,definition='실제로 제공된 정의',review_status='reviewed')
    supplied={'rule':source}
    if kind!='missing': supplied['existing']=target
    if kind=='invalid': target.update(classification='type',validation=['출처 정의 미제공'])
    if kind=='ambiguous':
        supplied.pop('existing')
        supplied.update(one=dict(target,id='one',classification='type',label='existing'),two=dict(target,id='two',classification='type',label='existing'))
    output=dict(observations=[],relation_bindings=[dict(relation_ref='rule',subject_ref='existing',object_ref='existing',reason='제공 정의의 범위 대조')])
    design.bind(output,supplied,{}, dict(design_relation_ids=['rule']))
    if kind=='type':
        result=output['modeled_relations'][0]
        assert result['source_relation']==source and not result['unresolved_endpoints']
    else:
        assert not output['modeled_relations'] and output['binding_coverage']['pending_relation_ids']==['rule']
    assert source['statement_type']=='rule'


def test_builder_local_refs_do_not_collide_with_supplied_ids_or_bind_undeclared_types():
    from app.knowledge import discovery_design as design
    block=dict(id='b',text='제공된 규범',source_version_id='v',parse_run_id='p',locator={})
    source=dict(id='rule',statement_type='rule',subject='원문 역할',object='원문 대상',validation=[],evidence_ids=['b'])
    supplied={'rule':source,'t1':dict(id='t1',classification='type',definition='기존 정의'),
              't2':dict(id='t2',classification='type',definition='다른 기존 정의')}
    output=dict(observations=[dict(id='new',local_ref='t1',evidence_ids=['b'],source_relation_ids=['rule'],validation=[],classification='type')],
        relation_bindings=[dict(relation_ref='rule',subject_ref='t1',object_ref='c1',reason='서로 다른 유형')])
    design.scope_local_refs(output)
    output=a2.remap(output,{'c1':'t1'})
    design.bind(output,supplied,{'b':block},dict(blocks=[dict(ref='b',text=block['text'])]))
    assert output['modeled_relations'][0]['subject']=='new' and output['modeled_relations'][0]['object']=='t1'
    missing=dict(observations=[],relation_bindings=[dict(relation_ref='rule',subject_ref='t2',object_ref='c1',reason='선언하지 않은 새 유형')])
    design.scope_local_refs(missing);missing=a2.remap(missing,{'c1':'t1'})
    design.bind(missing,supplied,{}, dict(design_relation_ids=['rule']))
    assert not missing['modeled_relations'] and missing['binding_coverage']['pending_relation_ids']==['rule']
    other=dict(observations=[],relation_bindings=[dict(relation_ref='rule',subject_ref='t1',object_ref='t1',reason='다른 묶음의 비교 관계')])
    design.bind(other,supplied,{},dict(design_relation_ids=[]))
    assert not other['modeled_relations'] and other['binding_errors']


@pytest.mark.parametrize('error', ['quote','missing','duplicate','judgment','unknown_id','direction','hierarchy_duplicate'])
def test_mixed_critic_validity_survives_resume_revision_and_a3(service,monkeypatch,model,error):
    from app.knowledge import ontology_changes as a3
    from app.tests.unit.test_knowledge_ontology_changes import listing, decide
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def mixed(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=json.loads(result['text'])
        if stage in {'concept','relation'}:
            rows=value['observations' if stage=='concept' else 'relations']
            if stage=='relation': rows.append(dict(rows[0],local_ref='r2',predicate='관련 유형'))
            for row in rows:
                row.update(evidence_ids=[],source_refs=[data['blocks'][0]['source_ref']])
        if stage=='builder':
            for h in value['hierarchies']:
                for d in ('a_to_b','b_to_a'):
                    h[d]=dict(h[d],evidence_ids=[],source_refs=[data['blocks'][0]['source_ref']])
        if stage=='critic':
            # The first judgment is independent and must survive a sibling's error.
            value['relation_checks'][0].update(evidence_id='',quote='',source_refs=[data['blocks'][0]['source_ref']])
            bad=value['relation_checks'][1]
            if error=='quote': bad['quote']='존재하지 않는 원문'
            elif error=='missing': value['relation_checks'].pop()
            elif error=='duplicate': value['relation_checks'].append(dict(bad))
            elif error=='judgment': bad['judgment']='probably'
            elif error=='unknown_id': bad['candidate_ref']='unprovided-candidate'
            elif error=='direction': value['hierarchy_checks'][0].pop('b_to_a')
            else: value['hierarchy_checks'].append(deepcopy(value['hierarchy_checks'][0]))
            value['needs_revision']=True
            # Invalid judgments cannot trigger a revision via a valid-looking issue/action.
            target=data['taxonomy']['hierarchies'][0]['id'] if error in {'direction','hierarchy_duplicate'} else bad['candidate_ref']
            value['issues']=[dict(local_ref='i1',candidate_ref=target,reason='이 대상을 수정하라',evidence_ids=[data['blocks'][0]['ref']],counter_evidence_ids=[],defer_reason='')]
            value['actions']=[dict(action='request_evidence',issue_id='i1',query='추가 근거',reason='오류 대상 근거 요청')]
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',mixed)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and not run['result']['failures'],run['result']['failures']
    critic=next(u for u in run['analysis_units'] if u['stage']=='critic')
    assert critic['status']=='succeeded' and critic['output']['record_errors']
    good,bad=run['result']['relations']
    coverage=critic['output']['review_coverage']
    assert good['id'] in coverage['valid_candidate_ids']
    target=run['result']['taxonomy'][0]['hierarchies'][0]['id'] if error in {'direction','hierarchy_duplicate'} else bad['id']
    assert target in coverage['pending_candidate_ids'] and target not in coverage['valid_candidate_ids']
    assert run['result']['mandatory_pending'] and run['result']['review_groups']==0
    assert not critic['output']['issues'] and not critic['output']['actions']
    assert 'revision' not in model and not run['result']['recovery_requests']
    check=next(c for c in critic['output']['relation_checks'] if c['candidate_ref']==good['id'])
    ref=check['evidence_refs'][0]
    assert ref['quote']==service.evidence(ref['evidence_id'])['block']['text'][slice(*ref['span'])]
    before=list(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model==before and again['status']=='partial'
    assert again['result']['critiques']==run['result']['critiques']
    cid=a3.publish(service,again['id'])['changeset_id']
    candidates=listing(service,cid)['candidates']
    valid=next(c for c in candidates if c['origin'].get('candidate_id')==good['id'])
    invalid=next(c for c in candidates if c['origin'].get('candidate_id')==target)
    assert valid['origin']['relation_checks']==[check] and not valid['origin'].get('review_errors')
    assert valid['validation']['can_accept_with_dependencies'],valid['validation']
    assert invalid['review_status']=='deferred' and not invalid['can_accept']
    assert invalid['origin']['review_errors'] and 'A2 검수 미완료' in str(invalid['validation'])
    assert not invalid['origin']['relation_checks']
    with pytest.raises(ValueError): decide(service,cid,[dict(candidate_id=invalid['id'],action='accept')])


@pytest.mark.parametrize('error', ['json','outside_evidence','duplicate_issue'])
def test_critic_envelope_failure_and_isolated_record_errors(service,monkeypatch,error):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def invalid(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text'])
            if error=='outside_evidence': value['relation_checks'][0]['evidence_id']='unprovided-evidence'
            if error=='duplicate_issue':
                issue=dict(local_ref='i1',reason='중복 참조',evidence_ids=[],counter_evidence_ids=[],defer_reason='검토 필요')
                value['issues']=[issue,dict(issue)]
            result['text']='{' if error=='json' else json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',invalid)
    run=done(service,service.start(request(source['id']))['run_id'])
    critic=next(u for u in run['analysis_units'] if u['stage']=='critic')
    assert run['status']=='partial' and critic['raw_output']
    if error=='json':
        assert critic['status']=='failed' and run['result']['failures'] and not run['result']['critiques']
    else:
        assert critic['status']=='succeeded' and critic['output']['record_errors']
        if error=='outside_evidence': assert critic['output']['observation_checks']
    from app.knowledge import ontology_changes as a3
    from app.tests.unit.test_knowledge_ontology_changes import listing
    cid=a3.publish(service,run['id'])['changeset_id']
    candidates=listing(service,cid)['candidates']
    assert any(c['origin'].get('review_errors') and not c['can_accept'] for c in candidates)
    if error=='outside_evidence': assert any(c['origin'].get('observation_checks') and not c['origin'].get('review_errors') for c in candidates)


def test_resume_adds_new_analysis_candidates_without_replacing_prior_review(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0']);original=a2.model_call;concept_calls=0
    async def fail_second(prompt,schema,stage,run,timeout):
        nonlocal concept_calls
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='concept':
            concept_calls+=1
            if concept_calls==2: result['text']='{'
        return result
    monkeypatch.setattr(a2,'model_call',fail_second)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and len(run['candidate_groups'])==1
    before=deepcopy(run['candidate_groups'][0])
    monkeypatch.setattr(a2,'model_call',original)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert again['status']=='review_ready',again['result']['failures']
    assert len(again['candidate_groups'])==2 and again['candidate_groups'][0]==before
    assert not again['result']['unreviewed_candidate_ids']
    assert model.count('builder')==model.count('critic')==2


def test_revision_inherits_full_critic_dependencies_and_blocks_revocation(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    source=prepare(service,file_ids=['current:0','web:0']); blocks=a2.load_blocks(service,source)
    selected=[b['id'] for b in blocks if b['file_id']=='current:0']; revoked=next(b['id'] for b in blocks if b['file_id']=='web:0')
    original=a2.model_call
    async def needs_revision(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            ctx=json.loads(prompt.split('\nINPUT:\n')[1]); out=json.loads(result['text'])
            out['issues']=[dict(local_ref='i1',candidate_ref=ctx['unapproved_observations'][0]['id'],reason='추가 읽은 원문을 바탕으로 판단했다.',evidence_ids=[ctx['blocks'][0]['ref']],counter_evidence_ids=[],defer_reason='')]
            out['needs_revision']=True; result['text']=json.dumps(out,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',needs_revision)
    original_revise=synthesis.revise
    def revoke_before_revise(service,run,group,review,taxonomy,by_id,contexts):
        critic=next(u for u in run['analysis_units'] if u['id']=='critic:'+group['id'])
        assert revoked in critic['dependency_ids']
        assert all(revoked not in i['evidence_ids']+i['counter_evidence_ids'] for i in review['issues'])
        snapshots.set_availability(service,dict(actor='test',reason='중단',expected_status_revision=0,targets=[dict(type='evidence',id=revoked)],state='blocked'))
        return original_revise(service,run,group,review,taxonomy,by_id,contexts)
    monkeypatch.setattr(synthesis,'revise',revoke_before_revise)
    run=done(service,service.start(request(source['id'],analysis_block_ids=selected,analysis_selection_reason='원문 선택'))['run_id'])
    revision=next(u for u in run['analysis_units'] if u['stage']=='revision')
    assert revision['status']=='failed' and revoked in revision['dependency_ids'] and 'revision' not in model


def test_completed_exact_budget_resume_needs_no_new_reservation(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets={'model_calls':5}))['run_id'])
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert again['status']==run['status']=='review_ready'
    assert run['metrics']['llm_calls']==again['metrics']['llm_calls']==5 and len(model)==5


def test_related_candidates_match_any_scope_link_and_previous_round(service):
    from app.knowledge import discovery_synthesis as synthesis
    source=prepare(service,file_ids=['current:0','web:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run); by_id={b['id']:b for b in blocks}
    # One current-round candidate shares only its second CQ with a later discovery.
    concept_units=[u for u in run['analysis_units'] if u['stage']=='concept']
    for n,u in enumerate(concept_units):
        u['output']['observations']=u['output']['observations'][:1]
        u['output']['observations'][0]['cq_ids']=['cq1','cq2'] if n==0 else ['cq2']
    run['analysis_units']=concept_units
    run['candidate_groups']=[]
    first=synthesis.assemble(run,0,by_id,profile.contexts(blocks),set(by_id))
    assert all(len(g['candidates'])==2 for g in first)
    run['candidate_groups']=[first[0]]
    next(g for g in run['frontier'] if g['id']==concept_units[1]['group_id'])['round']=1
    # Mark only the earlier observation as assigned, keeping it in the comparison pool.
    run['candidate_groups'][0]['primary_candidate_ids']=[concept_units[0]['output']['observations'][0]['id']]
    original_candidate=concept_units[0]['output']['observations'][0]
    updated=dict(original_candidate,classification='vocabulary')
    run['analysis_units'].append(dict(stage='revision',status='succeeded',dependency_ids=list(by_id),output=dict(history=[dict(candidate_id=updated['id'],after=updated)])))
    second=synthesis.assemble(run,1,by_id,profile.contexts(blocks),set(by_id))
    assert len(second)==1 and len(second[0]['candidates'])==2
    compared=next(c for c in second[0]['candidates'] if c['id']==updated['id'])
    assert compared['classification']=='vocabulary' and set(compared['origin_dependency_ids'])==set(by_id)
    assert original_candidate['classification']=='type'


def test_revision_combines_changed_and_unchanged_hierarchy_for_cycle_check():
    direction=dict(judgment='unknown',reason='검수 필요',evidence_ids=[],counter_evidence_ids=[])
    original=lambda a,b: dict(child_ref=a,parent_ref=b,relation='is_a',a_to_b=deepcopy(direction),b_to_a=deepcopy(direction))
    supplied={i:dict(id=i,classification='type') for i in ('a','b','c')}
    supplied.update(h1=dict(original('a','c'),id='h1'), h2=dict(original('b','a'),id='h2'))
    revised=dict(original('a','b'),candidate_ref='h1',reason='방향 수정')
    result=a2.normalize(dict(observations=[],relations=[],hierarchies=[revised],deferred=[]),'revision',
        dict(cqs=[],scope_items=[]),[],{},supplied)
    assert all('is_a 순환' in h['validation'] for h in result['effective_hierarchies'])
    assert result['history'][0]['before']['parent_ref']=='c'
    assert 'is_a 순환' in result['history'][0]['after']['validation']


def test_provenance_dependencies_cannot_be_new_citations_without_original(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def check(prompt,schema,stage,run,timeout):
        if stage=='builder':
            data=json.loads(prompt.split('\nINPUT:\n')[1])
            for variant in schema['$defs']['Direction']['anyOf']:
                assert 'evidence_ids' not in variant['properties']
                assert set(variant['properties']['source_refs']['items']['enum'])=={b['source_ref'] for b in a2.segments.originals(data)}
            unit=next(u for u in run['analysis_units'] if u['stage']=='builder')
            assert len(unit['dependency_ids'])>len(unit['provided_block_ids'])
        return await original(prompt,schema,stage,run,timeout)
    monkeypatch.setattr(a2,'model_call',check)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready',run['result']['failures']


def test_critic_extra_original_reaches_revision_even_without_revision_flag(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def request_more(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);value['actions']=[dict(action='search',query='국민임대',reason='추가 근거 확인')]
            assert not value['needs_revision']
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',request_more)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert model[-1]=='revision' and run['result']['revisions'][0]['deferred']
    assert not run['result']['unfulfilled_read_requests']


@pytest.mark.parametrize('marker',['classification','negation'])
def test_revision_cannot_overwrite_comparison_candidate_from_another_group(service,monkeypatch,marker):
    from app.knowledge import discovery_synthesis as synthesis, discovery_review as reviews
    source=prepare(service,file_ids=['current:0']);run=done(service,service.start(request(source['id']))['run_id'])
    group=deepcopy(run['candidate_groups'][0])
    effective={c['id']:c for c in group['candidates']+group.get('design_candidates', [])}
    comparison=next(i for i in group['primary_candidate_ids'] if marker in effective[i])
    group['primary_candidate_ids'].remove(comparison)
    review=dict(issues=[dict(candidate_ref=comparison,evidence_ids=[],counter_evidence_ids=[])],relation_checks=[],
        review_coverage=dict(valid_candidate_ids=[comparison],candidate_hashes={comparison:reviews.fingerprint(effective[comparison])}))
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    monkeypatch.setattr(a2,'call',lambda *args,**kwargs:pytest.fail('다른 묶음 후보의 중복 수정'))
    synthesis.revise(service,run,group,review,dict(hierarchies=[]),by_id,profile.contexts(blocks))
    assert group['revision_deferrals'][0]['candidate_ref']==comparison


def test_failed_revision_is_explicitly_deferred_without_second_attempt(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def broken_revision(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);value['needs_revision']=True;result['text']=json.dumps(value)
        if stage=='revision': result['text']='{'
        return result
    monkeypatch.setattr(a2,'model_call',broken_revision)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='partial' and model.count('revision')==1 and run['result']['revision_deferrals']
    failed=deepcopy(next(u for u in run['analysis_units'] if u['stage']=='revision'))
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model.count('revision')==1 and again['result']['revision_deferrals']
    assert next(u for u in again['analysis_units'] if u['stage']=='revision')==failed
    assert again['metrics']['llm_calls']==run['metrics']['llm_calls']==6


def test_compaction_only_omits_quotes_with_the_same_provided_original():
    raw = dict(ref='b1', text='조건을 포함한 원문 전체', locator={'page': 1})
    evidence = [dict(evidence_id='b1', quote='원문 전체', start=7, end=12),
                dict(evidence_id='b2', quote='원문 전체'), dict(evidence_id='b1', quote='다른 문장')]
    payload = dict(blocks=[raw], reviewed_base=[dict(evidence=evidence)])
    before = deepcopy(payload)
    compact = a2.compact(payload)
    assert payload == before and compact['blocks'] == [raw]
    assert compact['reviewed_base'][0]['evidence'] == [dict(evidence_id='b1', start=7, end=12), *evidence[1:]]


@pytest.mark.parametrize('search_budget', [0, 1])
def test_search_budget_does_not_skip_available_critic_review(service, model, search_budget):
    source = prepare(service, file_ids=['current:0'])
    run = done(service, service.start(request(source['id'], discovery_budgets=dict(searches=search_budget)))['run_id'])
    assert model == ['scout','concept','relation','builder','critic']
    assert run['status']=='partial' and run['result']['review_groups']==1
    assert len(run['result']['incomplete_review_searches'])==2-search_budget
    assert run['metrics']['searches']==search_budget
    resumed = done(service, service.start(RunRequest(kind='discovery', retry_of_run_id=run['id']))['run_id'])
    assert resumed['status']=='partial' and model == ['scout','concept','relation','builder','critic']
    assert resumed['metrics']['searches']==search_budget


@pytest.mark.parametrize('required', [True, False])
def test_one_block_list_capacity_preserves_raw_success_and_resume(service, monkeypatch, model, required):
    # The legacy unsplit/unsplittable path must still flag capacity limits.
    monkeypatch.setattr(a2.segments, 'expand', lambda frontier, blocks: frontier)
    survey = profile.survey
    def optional(*args):
        profiles, frontier, contexts = survey(*args)
        for group in frontier: group['required'] = required
        return profiles, frontier, contexts
    monkeypatch.setattr(profile, 'survey', optional)
    source = prepare(service, file_ids=['current:0'])
    load = a2.load_blocks
    text = '2020. 9. 8. 시행. 3.14 수치. ' + ' '.join(f'{i}. 유형명 조건과 제외 사항' for i in range(1,8))
    def listed(*args):
        blocks=load(*args)
        blocks[0]['text']=text
        return blocks
    monkeypatch.setattr(a2, 'load_blocks', listed)
    original = a2.model_call
    async def four(prompt, schema, stage, run, timeout):
        result = await original(prompt, schema, stage, run, timeout)
        if stage=='concept':
            assert json.loads(prompt.split('INPUT:\n')[1])['blocks'][0]['text']==text
            value=json.loads(result['text'])
            value['observations'] += [dict(value['observations'][0], local_ref='o3'),dict(value['observations'][0], local_ref='o4')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2, 'model_call', four)
    run = done(service, service.start(request(source['id']))['run_id'])
    pending=run['result']['capacity_pending'][0]
    assert len(pending['numbered_items'])==7 and pending['roles']['concept']==dict(limit=5, output_count=4)
    assert run['status']=='partial' and run['result']['processed_analysis_groups']==0
    assert run['result']['analysis_succeeded']==0 and len(run['result']['both_roles_evidence_block_ids'])==1
    assert all(u['status']=='succeeded' for u in run['analysis_units'])
    before=list(model)
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model==before and resumed['result']['capacity_pending']==run['result']['capacity_pending']
    assert not profile.numbered_items([dict(id='b',text='2020. 9. 8. 시행 1. 20명 2. 30명 3.14 수치')])


def test_role_scope_instructions_separate_primary_analysis_and_all_provided_review():
    from app.knowledge.discovery_models import COMMON, PROMPTS
    assert 'blocks가' not in COMMON
    assert 'CQ 목록은 전체 목표' in COMMON and '이번 호출 미제공' in COMMON
    for role in ('concept','relation'): assert '주 분석 대상' in PROMPTS[role]
    assert 'blocks·tool_originals·independently_retrieved의 실제 제공 packet' in COMMON
    assert 'review_target_ids' in PROMPTS['critic'] and 'design_relation_ids' in PROMPTS['builder']
    assert 'candidate_ref는 빈 문자열' in PROMPTS['critic']


@pytest.mark.parametrize('variant', ['unique','duplicate_type','entity_collision','invalid','explicit_entity','unprovided'])
def test_relation_endpoint_names_resolve_only_unique_provided_types_and_revision_keeps_ids(variant):
    row=dict(id='type1',label='대상',classification='type',validation=[])
    supplied={'type1':row}
    value='대상'
    if variant=='duplicate_type': supplied['type2']=dict(row,id='type2')
    if variant in {'entity_collision','explicit_entity'}:
        supplied['entity']=dict(row,id='entity',classification='entity')
        if variant=='explicit_entity': value='entity'
    if variant=='invalid': row['validation']=['원문 불일치']
    if variant=='unprovided': supplied={}
    raw=dict(local_ref='r1',subject=value,object=value,predicate='선정할 수 있다',
        direction='subject_to_object',negation='affirmed',conditions='잔여 대상이면 완화 또는 선착순 선택',time='',
        statement_type='rule',evidence_ids=['b'],cq_ids=['q'],scope_item_ids=[],outside_scope_reason='')
    run=dict(cqs=[dict(id='q')],scope_items=[])
    blocks={'b':dict(id='b',source_version_id='v',parse_run_id='p',locator={'line':1},text='원문')}
    result=a2.normalize({'relations':[deepcopy(raw)]},'relation',run,['b'],blocks,supplied)['relations'][0]
    assert result['subject']==('type1' if variant=='unique' else value)
    assert result['endpoint_labels']==({'subject':'대상','object':'대상'} if variant!='explicit_entity' else {})
    assert result['unresolved_endpoints']==([] if variant=='unique' else ['subject','object'])
    supplied['relation']=dict(result,id='relation')
    revision=dict(observations=[],relations=[dict(raw,candidate_ref='relation',reason='끝점 재검토')],hierarchies=[],deferred=[])
    fixed=a2.normalize(revision,'revision',run,['b'],blocks,supplied)
    assert fixed['relations'][0]['id']=='relation' and fixed['relations'][0]['subject']==result['subject']
    assert fixed['history'][0]['before']['id']=='relation'


@pytest.mark.parametrize('model_searches', [1, 2])
def test_same_two_search_budget_allows_critic_after_model_searches(service, monkeypatch, model, model_searches):
    source = prepare(service, file_ids=['current:0'])
    original = a2.model_call
    async def search_first(prompt, schema, stage, run, timeout):
        result = await original(prompt, schema, stage, run, timeout)
        if stage=='scout':
            output=json.loads(result['text'])
            output['actions']=[dict(action='search', query=q, reason='모델의 선행 탐색')
                               for q in ['국민임대','공급 조건'][:model_searches]]
            result['text']=json.dumps(output,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2, 'model_call', search_first)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(searches=2)))['run_id'])
    assert run['metrics']['searches']==2 and model.count('critic')==1
    assert run['status']=='partial' and len(run['result']['incomplete_review_searches'])==model_searches
    assert all(u['status']=='succeeded' for u in run['analysis_units'])


def test_segmented_execution_keeps_parent_evidence_and_reuses_success(service, monkeypatch, model):
    source=prepare(service,file_ids=['current:0'])
    load=a2.load_blocks
    text='공통 공급 조건. '+ ' '.join(f'{i}. 고유유형{i} 조건과 정의.' for i in range(1,8))
    def listed(*args):
        blocks=load(*args);blocks[0]['text']=text;return blocks
    monkeypatch.setattr(a2,'load_blocks',listed)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert len(run['frontier'])==4
    assert all(g.get('segments') for g in run['frontier'])
    assert all(u['status']=='succeeded' for u in run['analysis_units']),run['result']['failures']
    for row in run['result']['observations']:
        for ref in row['evidence_refs']:
            assert text[slice(*ref['span'])]==ref['quote'] and ref['block_id']==ref['evidence_id']
    before=list(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model==before and again['result']['observations']==run['result']['observations']


@pytest.mark.parametrize('role,rounds,invalid', [('concept',1,False),('relation',1,False),('concept',0,False),('concept',1,True)])
def test_critic_missing_meaning_separate_bounded_analysis(service,monkeypatch,model,role,rounds,invalid):
    source=prepare(service,file_ids=['current:0'])
    original=a2.model_call
    sent=False
    async def missing(prompt,schema,stage,run,timeout):
        nonlocal sent
        value=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]);out=json.loads(value['text'])
        if stage=='critic' and not sent:
            sent=True;b=data['blocks'][0]
            out['missing_meanings']=[dict(role=role,meaning='누락된 조건부 공급 의미',evidence_ids=[b['ref']],
                compared_candidate_ids=[c['id'] for field in ('unapproved_observations','unapproved_relations','reviewed_base','comparison_terms') for c in data.get(field,[])],
                comparison_reason='제공 관측과 관계 조건에 없는 별도 의미',
                source_quotes=[dict(evidence_id=b['ref'],quote='입력 밖 인용' if invalid else b['text'])],
                cq_ids=['cq1'],scope_item_ids=[],outside_scope_reason='')]
            out['needs_revision']=True
        if data.get('recovery_meaning'):
            if stage=='concept':
                for c in out['observations']: c['definition']='추가로 확인한 별도 의미'
            if stage=='relation': out['relations'][0]['conditions']='추가로 확인한 누락 조건'
        value['text']=json.dumps(out,ensure_ascii=False);return value
    monkeypatch.setattr(a2,'model_call',missing)
    selected=[b['id'] for b in a2.load_blocks(service,source)]
    run=done(service,service.start(request(source['id'],analysis_block_ids=selected,analysis_selection_reason='작은 원문 선택',
        discovery_budgets=dict(additional_rounds=rounds)))['run_id'])
    requests=run['result']['recovery_requests'];assert len(requests)==(0 if invalid else 1)
    recovery=[g for g in run['frontier'] if g.get('recovery_request_id')]
    if rounds and not invalid:
        assert len(recovery)==1 and requests[0]['status']=='proposals_created',run.get('error')
        assert recovery[0]['roles']==[role]
        assert requests[0]['proposal_ids'] and not any(u['stage']=='revision' for u in run['analysis_units'])
        assert requests[0] in run['result']['unresolved_recovery_requests'] and requests[0]['semantic_status']=='unverified'
        assert model.count('relation' if role=='concept' else 'concept')==1
    elif invalid:
        assert not recovery and run['status']=='partial' and run['result']['review_record_errors']
        assert not any(u['stage']=='revision' for u in run['analysis_units'])
    else:
        assert not recovery and run['status']=='partial' and run['result']['unresolved_recovery_requests']
    before=list(model)
    resumed=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert before==model and resumed['result']['recovery_requests']==requests


def test_final_prompt_allocation_keeps_primary_and_defers_comparison():
    run=dict(cqs=[dict(id='q',question='정의')],scope_items=[],recipe=a2.recipe({}))
    primary=dict(ref='primary',text='주 분석 원문 전체',locator={'row':1})
    term=dict(id='base',name='기준',definition='비교 정의',evidence=[dict(evidence_id='extra',quote='가'*16000)])
    group={}
    context,deps,supplied=a2.analysis_context(run,'concept',dict(blocks=[primary],reviewed_base=[term],tool_originals=[dict(ref='extra',text='가'*16000)]),{'base':term},group,reserve=2000)
    assert context['blocks']==[primary] and deps==['primary'] and not supplied
    assert group['omitted_comparison_ids']==['base']
    _,prompt=a2.make_prompt(run,'concept',context,deps,supplied)
    assert len(prompt)+2000<=run['recipe']['input_chars']


def test_output_capacity_queues_one_bounded_same_span_continuation():
    b=dict(id='b',text='원문 조건',locator={})
    group=dict(id='g',block_ids=['b'])
    run=dict(analysis_units=[dict(id='concept:g',status='succeeded',output=dict(observations=[{}]*5))])
    for _ in range(2):a2.capacity_status(run,group,{'b':b})
    assert len(run['recovery_requests'])==1
    r=run['recovery_requests'][0]
    assert r['role']=='concept' and r['trigger']=='output_capacity' and r['status']=='pending'
    assert r['evidence_refs']==[dict(evidence_id='b',block_id='b',span=[0,len(b['text'])])]


def test_critic_recovery_does_not_promote_comparison_only_history_to_selected_analysis():
    run=dict(analysis_block_ids=['selected-current'])
    need=dict(role='concept',meaning='이전 시행본의 정의 보완',validation=[],
              evidence_refs=[dict(block_id='comparison-history',span=[0,10])])
    a2.queue_recovery(run,dict(missing_meanings=[need]),dict(id='review'))
    assert run['recovery_requests'][0]['validation']
    assert a2.recovery_groups(run,1,{})==[]
    assert need['validation']==[]  # Preserve the original Critic judgment separately.

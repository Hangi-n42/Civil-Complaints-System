"""A4 read-only selection/context and existing A3 decision contracts."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.knowledge import discovery_run, parsers, snapshots
from app.tests.unit.test_knowledge_ontology_changes import corpus, service, analysis, prepare


def test_analysis_run_listing_paginates_without_inputs_or_model_outputs(service, monkeypatch):
    runs=[]
    for status in ('review_ready','partial','failed','cancelled','running'):
        run,_=analysis(service)
        run['status']=status
        with service.repository.connect() as db:service.repository.save(db,'runs',run)
        runs.append(run)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        first=client.get('/api/v1/knowledge/runs?limit=2').json()['data']
        assert [r['id'] for r in first['items']]==[r['id'] for r in reversed(runs[-2:])]
        second=client.get(f"/api/v1/knowledge/runs?limit=3&before={first['next_before']}").json()['data']
        assert [r['id'] for r in second['items']]==[r['id'] for r in reversed(runs[:3])]
        assert second['next_before'] is None
        assert all(r['has_result'] and 'analysis_units' not in r and 'result' not in r for r in first['items']+second['items'])
        assert client.get('/api/v1/knowledge/runs?limit=101').status_code==422
        assert client.get('/api/v1/knowledge/runs?before=0').status_code==422


def test_evidence_context_is_frozen_scoped_and_read_only(service, monkeypatch):
    run=prepare(service,file_ids=['table:0'])
    old=prepare(service,scope='historical_change')
    ids=run['units'][0]['block_ids'];chosen=ids[-1]
    original=service.evidence(chosen)
    # A newer pointer must not replace the stored run's blocks.
    with service.repository.connect() as db:
        version=service.repository.get(db,'versions',original['version']['id'])
        version['latest_parse_run_id']='newer-unrelated-parse'
        service.repository.save(db,'versions',version)
    before=service.sources()
    monkeypatch.setattr(parsers,'parse_unit',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('read must not parse')))
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        path=f'/api/v1/knowledge/evidence/{chosen}'
        current=client.get(path,params={'run_id':run['id']}).json()['data']
        assert current['block']==original['block']
        assert current['frozen_parse_run_id']==run['units'][0]['parse_run_id']
        assert current['context']['headers']==['| 코드 | 명칭 |']
        assert set(b['id'] for b in current['context']['blocks']) <= set(ids)
        assert any(b['text'].strip()=='| 코드 | 명칭 |' for b in current['context']['blocks'])
        assert client.get(path,params={'run_id':old['id']}).status_code==404
        assert 'context' not in client.get(path).json()['data']
        snapshots.set_availability(service,dict(actor='test',reason='헤더 사용 중단',targets=[dict(type='evidence',id=ids[1])],state='blocked',expected_status_revision=0))
        restricted=client.get(path,params={'run_id':run['id']}).json()['data']
        assert ids[1] not in {b['id'] for b in restricted['context']['blocks']}
        assert restricted['context']['omitted_restricted_count']==1
        assert restricted['context']['headers']==[] and restricted['context']['title'] is None
        assert ids[1] not in restricted['context']['block_ids']
        assert 'table_headers' not in restricted['block']['locator']
        assert 'table_headers' not in restricted['evidence']['locator']
        assert all('table_headers' not in b['locator'] for b in restricted['context']['blocks'])
        assert service.sources()==before


def test_review_conversion_edit_defer_reload_and_conflict(service,monkeypatch):
    run,ref=analysis(service)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        prefix='/api/v1/knowledge'
        cid=client.post(f"{prefix}/runs/{run['id']}/ontology-changes").json()['data']['changeset_id']
        data=client.get(f'{prefix}/candidates',params={'changeset_id':cid}).json()['data']
        c=data['items'][0];before_source=service.sources()
        payload=dict(expected_changeset_revision=0,expected_ontology_head_id=None,actor='검토자',
            decisions=[dict(candidate_id=c['id'],action='edit',reason='용어 표기 수정',patch={'after':dict(c['after'],name='화면 수정값')})])
        assert client.post(f'{prefix}/changes/{cid}/decisions',json=payload).status_code==200
        conflict=client.post(f'{prefix}/changes/{cid}/decisions',json=payload)
        assert conflict.status_code==409 and conflict.json()['error']['code']=='VERSION_CONFLICT'
        payload['expected_changeset_revision']=1
        payload['decisions']=[dict(candidate_id=c['id'],action='defer',reason='원문 문맥 추가 확인')]
        assert client.post(f'{prefix}/changes/{cid}/decisions',json=payload).status_code==200
        reloaded=client.get(f'{prefix}/candidates',params={'changeset_id':cid}).json()['data']
        row=reloaded['items'][0];change=reloaded['changesets'][0]
        assert row['after']['name']=='화면 수정값' and row['review_status']=='deferred'
        assert row['target_id']==c['target_id'] and row['symbol']==c['symbol']
        assert [d['action'] for d in change['decisions']]==['edit','defer']
        assert change['ontology_head_id'] is None and change['input_status']=='partial'
        assert client.get(f'{prefix}/changes/{cid}/schema-preview').json()['data']['included_change_ids']==[]
        assert service.run(run['id'])['metrics']['llm_calls']==0 and service.sources()==before_source

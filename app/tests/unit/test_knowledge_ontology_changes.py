"""A3 ledger/meaning boundaries. Fixtures are synthetic, not model quality evidence."""
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.knowledge import ontology_schema as v1, ontology_changes as a3, ontology_canonical as canonical, snapshots
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def analysis(service, base=None, lineage='test:current', observations=None, **result):
    grounded=prepare(service,file_ids=['current:0'])
    with service.repository.connect() as db:
        block=service.repository.get(db,'blocks',grounded['units'][0]['block_ids'][0])
    ref=a3._ref({'evidence_id':block['evidence_id']},{block['id']:block})
    observation=dict(id='dc_1',local_ref='o1',label='임대주택',classification='type',definition='선택 원문의 유형 정의',
        support_type='explicit',abstraction_level='업무 유형',review_signals=[],validation=[],cq_ids=['cq'],scope_item_ids=[],
        evidence_refs=[ref],evidence_ids=[ref['evidence_id']],review_status='unreviewed')
    run=dict(grounded,id=uuid4().hex,discovery_mode='analyze',status='partial',stage='analysis',
        lineage_id=lineage,base_ontology_version_id=base,cqs=[dict(id='cq',question='어떤 유형인가?')],scope_items=[],
        metrics=dict(llm_calls=0),analysis_units=[],
        result=dict(payload_version='a2-analysis-v2',review_status='unreviewed',observations=[observation] if observations is None else observations,
                    original_observations=[observation],relations=[],taxonomy=[],critiques=[],revision_history=[],
                    revisions=[],revision_deferrals=[],failures=[dict(unit_id='failed-revision',error='synthetic failure')],
                    gaps=['자료 필요'],unanalysed_block_ids=[block['id']],**result))
    with service.repository.connect() as db:
        v1._insert(db,'runs',run)
    return run,ref


def listing(service,identifier):
    return v1.candidates(service,identifier)['changesets'][0]


def add(service,identifier,rows):
    c=listing(service,identifier)
    a3.add(service,identifier,dict(expected_changeset_revision=c['revision'],actor='tester',reason='합성 경계 검수',candidates=rows))
    return listing(service,identifier)['candidates'][-len(rows):]


def proposal(ref, kind='class', **fields):
    after=dict(name='합성 유형',definition='근거에 연결된 설계 정의',**fields)
    if kind=='alias': after.pop('definition')
    return dict(target_kind=kind,after=after,
        support_type='design_proposal',qualifiers=dict(statement_type='design_proposal'),rationale='합성 구조 검증용 설계',
        evidence_refs=[ref],cq_ids=['cq'])


def decide(service,identifier,decisions,**kwargs):
    c=listing(service,identifier)
    return v1.decide(service,identifier,dict(expected_changeset_revision=c['revision'],expected_ontology_head_id=c['ontology_head_id'],
        actor='tester',decisions=[dict(reason='원문과 구조 검수',**d) for d in decisions],**kwargs))


def test_partial_conversion_identity_bad_candidate_and_edit_defer(service,monkeypatch):
    run,ref=analysis(service)
    source_before=service.sources()
    identifier=a3.publish(service,run['id'])['changeset_id']
    assert a3.publish(service,run['id'])['changeset_id']==identifier
    original=listing(service,identifier)
    assert original['input_status']=='partial' and original['analysis_result']==run['result']
    assert original['metamodel']['company_definitions']==[]
    first=original['candidates'][0]
    assert first['can_accept']
    bad=add(service,identifier,[proposal(ref)|{'after':{'unexpected':'invalid'}}])[0]
    assert not bad['can_accept'] and 'contract:' in str(bad['validation'])
    good=decide(service,identifier,[dict(candidate_id=first['id'],action='accept')])
    old_version=v1.get_ontology(service,good['reviewed_ontology_version_id'])
    assert old_version['payload_version']==2 and first['symbol'] in old_version['json_schema']['$defs']
    result=decide(service,identifier,[dict(candidate_id=first['id'],action='modify',patch={'after':dict(first['after'],name='명칭 수정')})])
    after=v1.get_ontology(service,result['reviewed_ontology_version_id'])
    assert after['targets'][0]['id']==first['target_id'] and after['targets'][0]['name']=='명칭 수정'
    assert v1.get_ontology(service,old_version['id'])==old_version
    assert after['version_hash']!=old_version['version_hash']
    head=result['ontology_head_id']
    deferred=decide(service,identifier,[dict(candidate_id=bad['id'],action='defer')])
    assert deferred['ontology_head_id']==head
    assert listing(service,identifier)['original_candidates'][0]==original['original_candidates'][0]
    assert listing(service,identifier)['id_mapping']==original['id_mapping']
    assert service.sources()==source_before
    monkeypatch.setattr(canonical,'derive',lambda _: (_ for _ in ()).throw(ValueError('compiler failure')))
    with pytest.raises(ValueError,match='compiler failure'):
        decide(service,identifier,[dict(candidate_id=first['id'],action='modify',patch={'after':dict(first['after'],name='실패 수정')})])
    assert listing(service,identifier)['ontology_head_id']==head
    assert listing(service,identifier)['revision']==deferred['changeset_revision']


def test_evidence_binding_scope_and_availability(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id']
    for patch in ({'span':[0,1]},{'quote':'원문 밖'}, {'source_version_id':'wrong'}, {'parse_run_id':'wrong'}, {'locator':{}}):
        item=add(service,cid,[proposal(ref|patch)])[0]
        assert not item['can_accept'],patch
    other=prepare(service,scope='historical_change')
    with service.repository.connect() as db:
        b=service.repository.get(db,'blocks',other['units'][0]['block_ids'][0])
    item=add(service,cid,[proposal(a3._ref({'evidence_id':b['id']},{b['id']:b}))])[0]
    assert not item['can_accept']
    first=listing(service,cid)['candidates'][0]
    snapshots.set_availability(service,dict(actor='tester',reason='근거 검토 필요',targets=[dict(type='evidence',id=ref['evidence_id'])],state='needs_review',expected_status_revision=0))
    assert not listing(service,cid)['candidates'][0]['can_accept']
    with pytest.raises(ValueError,match='수락 집합 오류'):
        decide(service,cid,[dict(candidate_id=first['id'],action='accept')])


def test_entity_value_fact_samples_are_not_classes(service):
    run,ref=analysis(service)
    source=run['result']['observations'][0]
    run['result']['observations'] += [dict(source,id='sample',classification='entity'),dict(source,id='value',classification='property_value')]
    run['result']['relations']=[dict(id='fact',statement_type='instance')]
    run['result']['revision_deferrals']=[dict(candidate_ref='dc_1',reason='실패 후 보류')]
    with service.repository.connect() as db: service.repository.save(db,'runs',run)
    c=listing(service,a3.publish(service,run['id'])['changeset_id'])
    assert len(c['candidates'])==1 and len(c['reference_material'])==3
    assert c['candidates'][0]['review_status']=='deferred'
    assert c['analysis_result']['failures']==run['result']['failures']
    bad=add(service,c['id'],[proposal(ref)|{'qualifiers':{'statement_type':'rule'}}])[0]
    assert not bad['can_accept'] and '의무/사실' in str(bad['validation'])


def direction(ref,judgment='unknown'):
    return dict(judgment=judgment,reason='합성 양방향 비교',evidence_ids=[ref['evidence_id']],counter_evidence_ids=[])


def hierarchy(ref,a,b,relation='is_a',forward='supported',reverse='unknown'):
    row=proposal(ref,'hierarchy',child_id=a,parent_id=b,relation=relation)
    row['after'].pop('name');row['after'].pop('definition')
    row['hierarchy_review']=dict(builder=dict(a_to_b=direction(ref,forward),b_to_a=direction(ref,reverse)),
                                critic=[dict(a_to_b=direction(ref,forward),b_to_a=direction(ref,reverse))])
    return row


def test_canonical_inheritance_vocabulary_alias_and_direct_yaml_read(service,monkeypatch):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id']
    parent=listing(service,cid)['candidates'][0]
    child,vocab,broader=add(service,cid,[proposal(ref),proposal(ref,'vocabulary_concept'),proposal(ref,'vocabulary_concept')])
    slot,edge,vedge,alias=add(service,cid,[proposal(ref,'attribute',domain_id=parent['target_id'],range='integer'),
        hierarchy(ref,child['target_id'],parent['target_id'],reverse='supported'),
        hierarchy(ref,vocab['target_id'],broader['target_id'],'broader'),
        proposal(ref,'alias',alias_of=vocab['target_id'])])
    assert '동치' in str(edge['validation']['semantic_review'])
    assert edge['hierarchy_review']['possible_equivalence']
    assert not edge['can_accept'] and edge['validation']['can_accept_with_dependencies']
    with pytest.raises(ValueError): decide(service,cid,[dict(candidate_id=edge['id'],action='accept')])
    preview=a3.preview(service,cid)
    assert preview['status']=='unreviewed_preview'
    all_rows=listing(service,cid)['candidates']
    result=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in all_rows])
    monkeypatch.setattr(v1,'build_schema',lambda _:pytest.fail('v1 reconstruction forbidden'))
    version=v1.get_ontology(service,result['reviewed_ontology_version_id'])
    assert version['linkml_schema']['classes'][child['symbol']]['is_a']==parent['symbol']
    assert slot['symbol'] in version['effective_class_slots'][child['symbol']]
    assert slot['symbol'] in version['json_schema']['$defs'][child['symbol']]['properties']
    registry=version['vocabulary_registry']['targets']
    assert set(registry)=={vocab['target_id'],broader['target_id'],vedge['target_id'],alias['target_id']}
    assert vocab['symbol'] not in version['linkml_schema']['classes']
    assert canonical.digest(version['vocabulary_registry'])==version['registry_hash']
    assert canonical.digest([version['schema_hash'],version['registry_hash']])==version['version_hash']
    with pytest.raises(ValueError,match='LH:complex 의미 대응'):
        service.start(RunRequest(kind='extract',source_version_ids=run['input_version_ids'],ontology_version_id=version['id'],registry_source_version_id=run['input_version_ids'][0]))


def test_cycle_kind_mismatch_and_unknown_are_visible(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id']
    a=listing(service,cid)['candidates'][0];b,vocab=add(service,cid,[proposal(ref),proposal(ref,'vocabulary_concept')])
    edges=add(service,cid,[hierarchy(ref,a['target_id'],b['target_id']),hierarchy(ref,b['target_id'],a['target_id']),
        hierarchy(ref,a['target_id'],a['target_id']),hierarchy(ref,a['target_id'],vocab['target_id'],'broader'),
        hierarchy(ref,'sample',a['target_id'],'instance_of')])
    assert all(not c['can_accept'] for c in edges)
    assert 'is_a 순환' in str(edges[0]['validation'])
    assert 'unknown은' in str(edges[0]['validation'])
    assert '종류 불일치' in str(edges[3]['validation'])
    # Independent valid definitions can still be reviewed and accepted.
    decide(service,cid,[dict(candidate_id=a['id'],action='accept')])


def test_head_cas_stale_changeset_cannot_just_replace_expected_id(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id']
    other,_=analysis(service)
    otherid=a3.publish(service,other['id'])['changeset_id']
    first=listing(service,cid)['candidates'][0];second=listing(service,otherid)['candidates'][0]
    new=decide(service,cid,[dict(candidate_id=first['id'],action='accept')])
    with pytest.raises(VersionConflict):
        decide(service,otherid,[dict(candidate_id=second['id'],action='accept')])
    with pytest.raises(VersionConflict):
        v1.decide(service,cid,dict(expected_changeset_revision=0,expected_ontology_head_id=new['ontology_head_id'],actor='tester',decisions=[dict(candidate_id=first['id'],action='defer',reason='stale')]))
    assert listing(service,otherid)['revision']==0
    # Defer does not mutate the accepted set/head even after another changeset advanced it.
    assert decide(service,otherid,[dict(candidate_id=second['id'],action='defer')])['ontology_head_id']==new['ontology_head_id']


VersionConflict=v1.VersionConflict


def test_v1_base_ids_rename_and_merge_deprecation_direct_impact(service):
    run,ref=analysis(service,observations=[])
    legacy=dict(id='legacy',kind='ontology',status='succeeded',cqs=run['cqs'],frozen_blocks=[dict(evidence_id=ref['evidence_id'],text=ref['quote'])])
    from app.tests.unit.test_knowledge_ontology_schema import proposal as old_proposal
    p=old_proposal('CONCEPT_001')|{'cq_ids':['cq'],'evidence':[dict(evidence_id=ref['evidence_id'],quote=ref['quote'])]}
    with service.repository.connect() as db:v1._insert(db,'runs',legacy)
    old=v1.publish(service,legacy,[p])
    old=v1.decide(service,old['changeset_id'],dict(actor='tester',expected_changeset_revision=0,decisions=[dict(candidate_id='CONCEPT_001',action='accept')]))
    base=old['reviewed_ontology_version_id']; original=v1.get_ontology(service,base)
    run['base_ontology_version_id']=base
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    cid=a3.publish(service,run['id'])['changeset_id']
    assert listing(service,cid)['ontology_head_id']==base
    rename=add(service,cid,[proposal(ref)|dict(support_type='explicit',qualifiers={},operation='update',target_id='CONCEPT_001',after={k:v for k,v in p.items() if k in {'name','definition','inclusion','exclusion'}})])[0]
    modified=decide(service,cid,[dict(candidate_id=rename['id'],action='modify',patch={'after':dict(rename['after'],name='표시명 수정')})])
    current=v1.get_ontology(service,modified['ontology_head_id'])
    assert current['targets'][0]['id']=='CONCEPT_001'
    assert v1.get_ontology(service,base)==original
    # Mapping is a direct unresolved reference, so retirement is retained but blocked.
    next_run,_=analysis(service,base=modified['ontology_head_id'],observations=[])
    nextid=a3.publish(service,next_run['id'])['changeset_id']
    dep=add(service,nextid,[proposal(ref)|dict(operation='deprecate',target_id='CONCEPT_001',after={})])[0]
    assert any(i['kind']=='extraction_mapping' for i in dep['affected_references']) and not dep['can_accept']


def test_merge_maps_ids_without_deleting_old_versions(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];first=listing(service,cid)['candidates'][0]
    second=add(service,cid,[proposal(ref)])[0]
    accepted=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (first,second)])
    base=accepted['ontology_head_id'];old=v1.get_ontology(service,base)
    run2,_=analysis(service,base=base,observations=[])
    cid2=a3.publish(service,run2['id'])['changeset_id']
    merge=add(service,cid2,[proposal(ref)|dict(operation='merge',target_id=first['target_id'],after={'canonical_id':second['target_id']})])[0]
    assert merge['can_accept']
    result=decide(service,cid2,[dict(candidate_id=merge['id'],action='accept')])
    new=v1.get_ontology(service,result['ontology_head_id'])
    assert new['vocabulary_registry']['replaced_ids'][first['target_id']]==second['target_id']
    assert next(t for t in new['targets'] if t['id']==first['target_id'])['deprecated']
    assert v1.get_ontology(service,base)==old


def test_api_envelope_invalid_candidate_and_expected_head(service,monkeypatch):
    from app.api.routers import knowledge
    run,ref=analysis(service)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        response=client.post(f"/api/v1/knowledge/runs/{run['id']}/ontology-changes")
        assert response.status_code==200 and response.json()['success']
        cid=response.json()['data']['changeset_id']
        row=client.get('/api/v1/knowledge/candidates',params={'changeset_id':cid}).json()['data']['items'][0]
        payload=dict(expected_changeset_revision=0,actor='tester',decisions=[dict(candidate_id=row['id'],action='accept',reason='검수')])
        assert client.post(f'/api/v1/knowledge/changes/{cid}/decisions',json=payload).status_code==422
        response=client.post(f'/api/v1/knowledge/changes/{cid}/decisions',json=payload|{'expected_ontology_head_id':None})
        assert response.status_code==200,response.json()
        assert client.post(f'/api/v1/knowledge/changes/{cid}/decisions',json=payload|{'expected_ontology_head_id':None}).status_code==409


def test_malformed_records_remain_editable_and_slot_default_compiles(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];parent=listing(service,cid)['candidates'][0]
    malformed,slot=add(service,cid,[proposal(ref)|{'target_id':[]},proposal(ref,'attribute',domain_id=parent['target_id'])])
    assert not malformed['can_accept'] and malformed['origin']['raw_proposal']['target_id']==[]
    result=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (parent,slot)])
    version=v1.get_ontology(service,result['ontology_head_id'])
    assert version['linkml_schema']['slots'][slot['symbol']]['range']=='string'
    edge=add(service,cid,[hierarchy(ref,parent['target_id'],parent['target_id'])])[0]
    edited=decide(service,cid,[dict(candidate_id=edge['id'],action='edit',patch={'hierarchy_review':{'builder':42}})])
    row=next(c for c in edited['items'] if c['id']==edge['id'])
    assert not row['can_accept'] and 'contract:' in str(row['validation'])
    assert decide(service,cid,[dict(candidate_id=edge['id'],action='defer')])['ontology_head_id']==result['ontology_head_id']


def test_builder_scope_design_support_and_successful_revision_deferral(service):
    run,ref=analysis(service)
    a=run['result']['observations'][0];a['support_type']='instance_proposal'
    b=dict(a,id='dc_b',label='상위유형');other=dict(a,id='dc_other',cq_ids=['q2'])
    run['cqs'].append(dict(id='q2',question='무관한 유형?'))
    run['result']['observations']=[a,b,other]
    h=dict(id='dh_1',child_ref='dc_1',parent_ref='dc_b',relation='is_a',
           a_to_b=direction(ref,'supported'),b_to_a=direction(ref),validation=[])
    run['result']['taxonomy']=[dict(unit_id='builder:one',hierarchies=[h])]
    run['result']['revisions']=[dict(deferred=[dict(candidate_ref='dc_1',reason='추가 자료 필요')])]
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    c=listing(service,a3.publish(service,run['id'])['changeset_id'])
    assert c['candidates'][0]['review_status']=='deferred'
    edge=next(r for r in c['candidates'] if r['kind']=='hierarchy')
    assert edge['support_type']=='design_proposal' and edge['cq_ids']==['cq']
    assert edge['hierarchy_review']['builder']['b_to_a']['judgment']=='unknown'


def test_atomic_hierarchy_replacement_and_joint_deprecation(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];a=listing(service,cid)['candidates'][0]
    b=add(service,cid,[proposal(ref)])[0]
    edge,slot=add(service,cid,[hierarchy(ref,a['target_id'],b['target_id']),proposal(ref,'attribute',domain_id=a['target_id'])])
    base=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (a,b,edge,slot)])['ontology_head_id']
    run2,_=analysis(service,base=base,observations=[])
    cid2=a3.publish(service,run2['id'])['changeset_id']
    removed,reversed_edge=add(service,cid2,[proposal(ref,'hierarchy')|dict(operation='deprecate',target_id=edge['target_id'],after={}),
        hierarchy(ref,b['target_id'],a['target_id'])])
    next_version=decide(service,cid2,[dict(candidate_id=c['id'],action='accept') for c in (removed,reversed_edge)])['ontology_head_id']
    schema=v1.get_ontology(service,next_version)['linkml_schema']['classes']
    assert 'is_a' not in schema[a['symbol']] and schema[b['symbol']]['is_a']==a['symbol']
    run3,_=analysis(service,base=next_version,observations=[])
    cid3=a3.publish(service,run3['id'])['changeset_id']
    retiring=add(service,cid3,[proposal(ref,c['target_kind'])|dict(operation='deprecate',target_id=c['target_id'],after={})
        for c in (a,b,slot,reversed_edge)])
    result=decide(service,cid3,[dict(candidate_id=c['id'],action='accept') for c in retiring])
    assert all(t['deprecated'] for t in v1.get_ontology(service,result['ontology_head_id'])['targets'])


@pytest.mark.parametrize('operation',['merge','deprecate'])
def test_merging_into_another_retired_target_is_atomic_error(service,operation):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];a=listing(service,cid)['candidates'][0];b=add(service,cid,[proposal(ref)])[0]
    base=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (a,b)])['ontology_head_id']
    run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
    rows=add(service,cid2,[proposal(ref)|dict(operation='merge',target_id=a['target_id'],after={'canonical_id':b['target_id']}),
        proposal(ref)|dict(operation=operation,target_id=b['target_id'],after={'canonical_id':a['target_id']} if operation=='merge' else {})])
    with pytest.raises(ValueError):decide(service,cid2,[dict(candidate_id=c['id'],action='accept') for c in rows])
    unchanged=listing(service,cid2)
    assert unchanged['ontology_head_id']==base and unchanged['revision']==1 and unchanged['decisions']==[]


def test_candidate_counter_evidence_and_v2_base_vocabulary_lookup(service):
    from app.knowledge import discovery_analysis as a2
    run,ref=analysis(service)
    run['result']['critiques']=[dict(unit_id='critic:fixture',issues=[dict(candidate_ref='dc_1',counter_evidence_ids=[ref['evidence_id']],reason='반례 검토 필요')])]
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    cid=a3.publish(service,run['id'])['changeset_id']
    first=listing(service,cid)['candidates'][0]
    assert first['counter_evidence_refs']==[ref]
    vocabulary=add(service,cid,[proposal(ref,'vocabulary_concept')])[0]
    slot=add(service,cid,[proposal(ref,'attribute',domain_id=first['target_id'])])[0]
    version_id=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (first,vocabulary,slot)])['ontology_head_id']
    frozen,candidates=a2._base(service,RunRequest(base_ontology_version_id=version_id),run['frozen_input'])
    assert frozen['vocabulary_registry']['targets'][vocabulary['target_id']]['kind']=='vocabulary_concept'
    assert frozen['version_hash']==v1.get_ontology(service,version_id)['version_hash']
    with service.repository.connect() as db:blocks=list(a3._blocks(service.repository,db,run).values())
    terms=a2.lookup(service,dict(run,base_candidates=candidates),'합성','vocabulary',blocks)
    assert [t['id'] for t in terms]==[vocabulary['target_id']]
    assert [t['id'] for t in a2.lookup(service,dict(run,base_candidates=candidates),'합성','property_value',blocks)]==[slot['target_id']]
    context=a2.base_context(dict(run,base_candidates=candidates))
    assert next(c for c in context if c['id']==vocabulary['target_id'])['classification']=='vocabulary'


def test_decision_failure_rolls_back_version_head_and_revision(service,monkeypatch):
    run,_=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];first=listing(service,cid)['candidates'][0]
    original=a3._insert
    def fail_decision(db,table,value):
        if table=='decisions':raise ValueError('결정 저장 실패')
        return original(db,table,value)
    monkeypatch.setattr(a3,'_insert',fail_decision)
    with pytest.raises(ValueError,match='결정 저장 실패'):
        decide(service,cid,[dict(candidate_id=first['id'],action='accept')])
    c=listing(service,cid)
    assert c['revision']==0 and c['ontology_head_id'] is None and c['decisions']==[]
    with service.repository.connect() as db:assert db.execute('SELECT COUNT(*) FROM ontology_versions').fetchone()[0]==0


def test_separate_connections_cannot_both_advance_one_lineage(service):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, RLock
    from types import SimpleNamespace
    run,_=analysis(service);other,_=analysis(service)
    cids=[a3.publish(service,r['id'])['changeset_id'] for r in (run,other)]
    payloads=[dict(expected_changeset_revision=0,expected_ontology_head_id=None,actor='tester',
        decisions=[dict(candidate_id=listing(service,cid)['candidates'][0]['id'],action='accept',reason='동시 검수')]) for cid in cids]
    barrier=Barrier(2)
    def execute(n):
        independent=SimpleNamespace(repository=service.repository,lock=RLock())
        barrier.wait()
        try:return a3.decide(independent,cids[n],payloads[n])['ontology_head_id']
        except VersionConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,range(2)))
    assert results.count('conflict')==1
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM ontology_versions').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0]==1


def test_direct_fact_snapshot_references_are_ids_not_free_text(service):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];first=listing(service,cid)['candidates'][0]
    slot=add(service,cid,[proposal(ref,'attribute',domain_id=first['target_id'])])[0]
    base=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (first,slot)])['ontology_head_id']
    with service.repository.connect() as db:
        version=service.repository.get(db,'ontology_versions',base)
        v1._insert(db,'snapshots',dict(id='snapshot',ontology=version))
        for identifier,concept in [('related',first['target_id']),('name-only','unrelated')]:
            value=dict(id=identifier,concept_id=concept,name=first['target_id'])
            db.execute('INSERT INTO entities VALUES(?,?,?,?)',(identifier,'fixture',identifier,json.dumps(value)))
        v1._insert(db,'runs',dict(id='extract-fixture',kind='extract',status='succeeded',units=[],ontology_candidates=[dict(id=first['target_id'])]))
        db.execute('INSERT INTO assertions VALUES(?,?,?,?,?)',('fact','extract-fixture','u','key',json.dumps(dict(id='fact',predicate_id=slot['target_id']))))
    second,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,second['id'])['changeset_id']
    item=add(service,cid2,[proposal(ref)|dict(operation='deprecate',target_id=first['target_id'],after={})])[0]
    assert {'snapshots:snapshot','entities:related','runs:extract-fixture'} <= set(item['affected_reference_ids'])
    assert 'entities:name-only' not in item['affected_reference_ids'] and not item['can_accept']
    item=add(service,cid2,[proposal(ref,'attribute')|dict(operation='deprecate',target_id=slot['target_id'],after={})])[0]
    assert {'assertions:fact','snapshots:snapshot'} <= set(item['affected_reference_ids'])


def test_vocabulary_rename_changes_registry_hash_without_changing_yaml(service):
    run,ref=analysis(service,observations=[])
    cid=a3.publish(service,run['id'])['changeset_id']
    term=add(service,cid,[proposal(ref,'vocabulary_concept')])[0]
    base=decide(service,cid,[dict(candidate_id=term['id'],action='accept')])['ontology_head_id']
    old=v1.get_ontology(service,base)
    later,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,later['id'])['changeset_id']
    update=add(service,cid2,[proposal(ref,'vocabulary_concept')|dict(operation='update',target_id=term['target_id'],after=dict(term['after'],name='어휘 표시명 수정'))])[0]
    version=decide(service,cid2,[dict(candidate_id=update['id'],action='accept')])['ontology_head_id']
    new=v1.get_ontology(service,version)
    assert new['schema_hash']==old['schema_hash']
    assert new['registry_hash']!=old['registry_hash'] and new['version_hash']!=old['version_hash']
    assert new['vocabulary_registry']['targets'][term['target_id']]['name']=='어휘 표시명 수정'
    assert v1.get_ontology(service,base)==old


def test_supported_critic_keeps_full_dependency_availability(service):
    run,ref=analysis(service)
    grounding=prepare(service,file_ids=['current:0','table:0'])
    for key in ('units','frozen_input','input_version_ids'):run[key]=grounding[key]
    other=next(i for u in grounding['units'] for i in u['block_ids'] if i!=ref['block_id'])
    with service.repository.connect() as db:b=service.repository.get(db,'blocks',other)
    run['result']['observations'].append(dict(run['result']['observations'][0],id='dc_2',label='다른 유형'))
    relation=dict(id='dc_rel',local_ref='r1',subject='dc_1',predicate='연결',object='dc_2',direction='subject_to_object',
        negation='affirmed',conditions='',time='',statement_type='definition',evidence_refs=[ref],cq_ids=['cq'],scope_item_ids=[],validation=[])
    run['result']['relations']=[relation]
    critique=dict(unit_id='critic:fixture',issues=[],relation_checks=[dict(candidate_ref='dc_rel',
        judgment='supported',evidence_id=other,quote=b['text'],reason='문맥 지지')])
    run['result']['critiques']=[critique]
    run['analysis_units']=[dict(id='concept:fixture',stage='concept',status='succeeded',dependency_ids=[ref['block_id']],
        output={'observations':run['result']['observations']}),dict(id='relation:fixture',stage='relation',status='succeeded',dependency_ids=[ref['block_id']],
        output={'relations':[relation]}),dict(id=critique['unit_id'],stage='critic',status='succeeded',
        dependency_ids=[ref['block_id'],other],output=critique)]
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    cid=a3.publish(service,run['id'])['changeset_id'];before=next(c for c in listing(service,cid)['candidates'] if c['target_kind']=='relation')
    assert before['validation']['can_accept_with_dependencies'] and other in before['origin']['dependency_block_ids']
    snapshots.set_availability(service,dict(actor='tester',reason='Critic 문맥 중단',targets=[dict(type='evidence',id=other)],state='blocked',expected_status_revision=0))
    after=next(c for c in listing(service,cid)['candidates'] if c['id']==before['id'])
    assert not after['can_accept'] and '파생 입력' in str(after['validation'])


@pytest.mark.parametrize('kind',['attribute','relation'])
def test_deprecated_required_slot_leaves_current_and_inherited_constraints(service,kind):
    run,ref=analysis(service)
    cid=a3.publish(service,run['id'])['changeset_id'];parent=listing(service,cid)['candidates'][0]
    child=add(service,cid,[proposal(ref)])[0]
    fields={'range':child['target_id'],'direction':'subject_to_object'} if kind=='relation' else {}
    slot,edge=add(service,cid,[proposal(ref,kind,domain_id=parent['target_id'],required=True,**fields),
        hierarchy(ref,child['target_id'],parent['target_id'])])
    base=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (parent,child,slot,edge)])['ontology_head_id']
    old=v1.get_ontology(service,base)
    assert slot['symbol'] in old['json_schema']['$defs'][child['symbol']]['required']
    run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
    dep=add(service,cid2,[proposal(ref,kind)|dict(operation='deprecate',target_id=slot['target_id'],after={})])[0]
    result=decide(service,cid2,[dict(candidate_id=dep['id'],action='accept')])
    current=v1.get_ontology(service,result['ontology_head_id'])
    for owner in (parent,child):
        assert slot['symbol'] not in current['effective_class_slots'][owner['symbol']]
        definition=current['json_schema']['$defs'][owner['symbol']]
        assert slot['symbol'] not in definition.get('required',[])
        assert slot['symbol'] not in definition.get('properties',{})
    assert next(t for t in current['targets'] if t['id']==slot['target_id'])['deprecated']
    assert current['linkml_schema']['slots'][slot['symbol']]['required']
    assert v1.get_ontology(service,base)==old


def test_deprecated_class_is_retained_without_root_item_exposure(service):
    run,ref=analysis(service);cid=a3.publish(service,run['id'])['changeset_id']
    cls=listing(service,cid)['candidates'][0]
    base=decide(service,cid,[dict(candidate_id=cls['id'],action='accept')])['ontology_head_id']
    old=v1.get_ontology(service,base)
    run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
    dep=add(service,cid2,[proposal(ref)|dict(operation='deprecate',target_id=cls['target_id'],after={})])[0]
    result=decide(service,cid2,[dict(candidate_id=dep['id'],action='accept')])
    current=v1.get_ontology(service,result['ontology_head_id']);item_slot='items_'+cls['symbol']
    assert item_slot not in current['linkml_schema']['classes'][canonical.ROOT]['slots']
    assert item_slot not in json.dumps(current['json_schema'])
    assert current['linkml_schema']['classes'][cls['symbol']]['deprecated']
    assert v1.get_ontology(service,base)==old


@pytest.mark.parametrize('state',['reject','defer','invalid'])
def test_inactive_or_invalid_hierarchy_does_not_block_review_structure(service,state):
    run,ref=analysis(service);cid=a3.publish(service,run['id'])['changeset_id']
    a=listing(service,cid)['candidates'][0];b=add(service,cid,[proposal(ref)])[0]
    decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in (a,b)])
    forward,reverse=add(service,cid,[hierarchy(ref,a['target_id'],b['target_id']),hierarchy(ref,b['target_id'],a['target_id'])])
    assert not forward['can_accept'] and 'is_a 순환' in str(forward['validation'])
    action=dict(candidate_id=reverse['id'],action=state if state!='invalid' else 'edit')
    if state=='invalid':action['patch']={'evidence_refs':[]}
    decided=decide(service,cid,[action]);current=listing(service,cid)
    forward=next(c for c in current['candidates'] if c['id']==forward['id'])
    assert forward['can_accept'] and 'is_a 순환' not in str(forward['validation'])
    preview=a3.preview(service,cid)
    assert preview['status']=='unreviewed_preview'
    assert forward['id'] in preview['included_change_ids'] and reverse['id'] in preview['excluded_change_ids']
    result=decide(service,cid,[dict(candidate_id=forward['id'],action='accept')])
    version=v1.get_ontology(service,result['ontology_head_id'])
    assert version['linkml_schema']['classes'][a['symbol']]['is_a']==b['symbol']
    assert 'is_a' not in version['linkml_schema']['classes'][b['symbol']]
    assert current['decisions'][-1]['candidate_id']==reverse['id']
    assert decided['ontology_head_id']!=result['ontology_head_id']


@pytest.mark.parametrize('kind',['class','vocabulary_concept'])
def test_sequential_merges_resolve_all_previous_ids_to_live_target(service,kind):
    run,ref=analysis(service,observations=[]);cid=a3.publish(service,run['id'])['changeset_id']
    a,b,c=add(service,cid,[proposal(ref,kind) for _ in range(3)])
    base=decide(service,cid,[dict(candidate_id=t['id'],action='accept') for t in (a,b,c)])['ontology_head_id']
    originals={base:v1.get_ontology(service,base)}
    for source,destination in ((a,b),(b,c)):
        run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
        merge=add(service,cid2,[proposal(ref,kind)|dict(operation='merge',target_id=source['target_id'],after={'canonical_id':destination['target_id']})])[0]
        assert merge['can_accept']
        preview=a3.preview(service,cid2)
        assert preview['status']=='unreviewed_preview'
        base=decide(service,cid2,[dict(candidate_id=merge['id'],action='accept')])['ontology_head_id']
        new=v1.get_ontology(service,base)
        assert preview['vocabulary_registry']['replaced_ids']==new['vocabulary_registry']['replaced_ids']
        assert all(v1.get_ontology(service,i)==old for i,old in originals.items())
        originals[base]=new
    assert new['vocabulary_registry']['replaced_ids']=={t['target_id']:c['target_id'] for t in (a,b)}
    assert {t['id']:t.get('replaced_by') for t in new['targets'] if t.get('replaced_by')}==new['vocabulary_registry']['replaced_ids']


@pytest.mark.parametrize('destination',['missing','wrong_kind','cycle','deprecate'])
def test_merged_id_cannot_resolve_to_invalid_or_retired_destination(service,destination):
    run,ref=analysis(service);cid=a3.publish(service,run['id'])['changeset_id']
    a=listing(service,cid)['candidates'][0];b,vocab=add(service,cid,[proposal(ref),proposal(ref,'vocabulary_concept')])
    base=decide(service,cid,[dict(candidate_id=t['id'],action='accept') for t in (a,b,vocab)])['ontology_head_id']
    run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
    merge=add(service,cid2,[proposal(ref)|dict(operation='merge',target_id=a['target_id'],after={'canonical_id':b['target_id']})])[0]
    base=decide(service,cid2,[dict(candidate_id=merge['id'],action='accept')])['ontology_head_id']
    old=v1.get_ontology(service,base)
    run3,_=analysis(service,base=base,observations=[]);cid3=a3.publish(service,run3['id'])['changeset_id']
    target={'missing':'absent','wrong_kind':vocab['target_id'],'cycle':a['target_id']}.get(destination)
    bad=add(service,cid3,[proposal(ref)|dict(target_id=b['target_id'],operation='merge' if target else 'deprecate',
        after={'canonical_id':target} if target else {})])[0]
    assert not bad['can_accept']
    before=listing(service,cid3)
    assert bad['id'] in a3.preview(service,cid3)['excluded_change_ids']
    with pytest.raises(ValueError):decide(service,cid3,[dict(candidate_id=bad['id'],action='accept')])
    assert listing(service,cid3)==before and v1.get_ontology(service,base)==old


@pytest.mark.parametrize('error',['missing','cycle','dependency'])
def test_invalid_hierarchy_update_keeps_base_edge_in_review_structure(service,error):
    run,ref=analysis(service);cid=a3.publish(service,run['id'])['changeset_id']
    a=listing(service,cid)['candidates'][0];b,c=add(service,cid,[proposal(ref),proposal(ref)])
    edges=add(service,cid,[hierarchy(ref,a['target_id'],b['target_id'])]+(
        [hierarchy(ref,c['target_id'],a['target_id'])] if error=='cycle' else []))
    edge=edges[0]
    base=decide(service,cid,[dict(candidate_id=t['id'],action='accept') for t in (a,b,c,*edges)])['ontology_head_id']
    old=v1.get_ontology(service,base)
    run2,_=analysis(service,base=base,observations=[]);cid2=a3.publish(service,run2['id'])['changeset_id']
    if error=='dependency':
        with service.repository.connect() as db:
            db.execute('INSERT INTO entities VALUES(?,?,?,?)',('referencing','fixture','c',json.dumps(dict(id='referencing',concept_id=c['target_id']))))
        add(service,cid2,[proposal(ref)|dict(operation='update',target_id=c['target_id'],after=dict(c['after'],definition='기존 소비자 참조가 있는 정의 변경'))])
    invalid,reverse=add(service,cid2,[hierarchy(ref,a['target_id'],'missing' if error=='missing' else c['target_id'])|dict(operation='update',target_id=edge['target_id']),
        hierarchy(ref,b['target_id'],a['target_id'])])
    assert not invalid['can_accept'] and not reverse['can_accept']
    assert 'is_a 순환' in str(reverse['validation'])
    preview=a3.preview(service,cid2)
    assert preview['status']=='unreviewed_preview' and preview['included_change_ids']==[]
    import yaml
    classes=yaml.safe_load(preview['linkml_yaml'])['classes']
    assert classes[a['symbol']]['is_a']==b['symbol'] and 'is_a' not in classes[b['symbol']]
    before=listing(service,cid2)
    with pytest.raises(ValueError,match='is_a 순환'):decide(service,cid2,[dict(candidate_id=reverse['id'],action='accept')])
    assert listing(service,cid2)==before and v1.get_ontology(service,base)==old

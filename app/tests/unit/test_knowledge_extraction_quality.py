"""Regressions for known row/value errors and manual recovery, without inference."""
from copy import deepcopy
import json
import pytest

from app.knowledge import extraction, extraction_contract as contract, extraction_store as store, ontology_schema
from app.tests.unit.test_knowledge_extraction_store import setup
from app.tests.unit.test_knowledge_extraction_run import definitions, model_result


def table_run():
    cells=[]
    for row,values in enumerate([['단지명','단 지 위 치','건설호수',None,'최초입주'],['가단지','가주소','5개동','452호','201603'],['나단지','나주소','3개동','1,300호','201106']]):
        for col,text in enumerate(values):
            if text is None:continue
            cells.append(dict(id=f'{row}-{col}',text=text,source_version_id='pdf-v1',run_id='parse1',locator=dict(format='pdf',physical_page=2,side='right',table=2,row=row,column=col,merged_span={'rows':1,'columns':2 if row==0 and col==2 else 1})))
    items=[dict(d,id=key,name=key,required=False,enum_values=[],evidence=[],cq_ids=[]) for key,d in contract.PROFILE['definitions'].items()]
    return dict(id='run1',data_run_id='run1',frozen_blocks=cells,ontology_candidates=items,ontology_version_id='ontology1',entities=[],accepted_aliases=[])


def test_pdf_maps_each_row_and_preserves_value_and_month_roles():
    run=table_run();unit=extraction.plan_units(run['frozen_blocks'])[0]
    assert unit['stage']=='pdf'
    records,coverage=contract.pdf_records(run,unit)
    assert len(records)==6 and all(c['status']=='extracted' for c in coverage)
    assert [r['values']['ATTRIBUTE_003'] for r in records if 'ATTRIBUTE_003' in r['values']]==[452,1300]
    assert [r['values']['FirstOccupancyMonth'] for r in records if 'FirstOccupancyMonth' in r['values']]==['2016-03','2011-06']
    run['ontology_candidates'][0]['definition']='다른 의미'
    assert any(c['status']=='unsupported' for c in contract.pdf_records(run,unit)[1])


def test_missing_duplicate_units_and_invalid_fact_are_visible():
    run=dict(ontology_candidates=definitions(),frozen_blocks=[dict(id='b',source_version_id='v',text='C00001 행복단지 201106',locator={})],entities=[])
    unit=dict(block_ids=['b'])
    assert contract.adapt(run,unit,{'units':[]})[1][0]['status']=='missing'
    decoded=json.loads(model_result(extraction.prompt_for(run,unit))['text'])
    decoded['units']*=2
    assert contract.adapt(run,unit,decoded)[1][0]['status']=='duplicate'
    decoded['units']=decoded['units'][:1]
    decoded['units'][0]['facts'].append(dict(decoded['units'][0]['facts'][0],raw_value=None))
    records,coverage,invalid=contract.adapt(run,unit,decoded)
    assert len(records)==1 and len(invalid)==1
    assert records[0]['values']['FirstOccupancyMonth']=='2011-06'


def test_numeric_row_and_column_mismatches_are_rejected(tmp_path):
    service,_,_,_,_,_=setup(tmp_path)
    run=table_run()
    yaml,_=ontology_schema.build_schema(run['ontology_candidates'])
    with service.repository.connect() as db:
        db.execute('UPDATE ontology_versions SET payload=? WHERE id=?',(json.dumps(dict(id='ontology1',linkml_yaml=yaml)),'ontology1'))
        db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run),'run1'))
    records,_=contract.pdf_records(run,extraction.plan_units(run['frozen_blocks'])[0])
    links,assertions,evidence=extraction.materialize(run,{'id':'pdf'},records)
    entities=[]
    for i,link in enumerate(links):
        ent=dict(id=f'ent{i}',namespace='LH:complex',official_id=f'C{i}',concept_id='CONCEPT_001',name=link['mention'])
        entities.append(ent);link.update(target_entity_id=ent['id'],method='manual')
    result=store.publish_unit(service,run,{'id':'pdf'},links,assertions,evidence,entities)
    with service.repository.connect() as db:
        schema=store._schema(service.repository,db,run)
        counts=[a for a in result['items'] if a.get('predicate_id')=='ATTRIBUTE_003']
        assert all(not c['validation_errors'] for c in counts)
        bad=dict(counts[0],value=12345)
        assert 'literal_normalization_mismatch' in store._assertion_errors(service.repository,db,bad,run,schema)
        bad=dict(counts[1],subject_link_id=counts[0]['subject_link_id'])
        assert 'table_subject_value_row_mismatch' in store._assertion_errors(service.repository,db,bad,run,schema)
        month=next(a for a in result['items'] if a.get('predicate_id')=='FirstOccupancyMonth')
        bad=dict(month,predicate_id='ATTRIBUTE_007')
        assert 'table_column_slot_mismatch' in store._assertion_errors(service.repository,db,bad,run,schema)


def test_manual_append_preserves_run_output_and_publish_idempotence(tmp_path):
    service,run,entity,link,assertion,evidence=setup(tmp_path)
    run['frozen_blocks'][0].update(source_version_id='v1',locator={})
    run['units']=[{'id':'u1','records':['unchanged']}];run['metrics']={'llm_calls':1}
    with service.repository.connect() as db:
        db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run),'run1'))
    result=store.publish_unit(service,run,{'id':'u1'},[link],[assertion],evidence,[entity])
    request=dict(expected_changeset_revision=1,actor='test',subject_link_id='link1',predicate_id='Households',block_id='block1',quote='985호',raw_value='985호',scope='미확인')
    created=store.add_manual(service,result['changeset_id'],request)
    manual=next(c for c in created['items'] if c.get('origin')=='manual')
    assert manual['value']==985 and manual['unit']=='호' and manual['review_status']=='proposed'
    with pytest.raises(ontology_schema.VersionConflict):store.add_manual(service,result['changeset_id'],request)
    repeated=store.publish_unit(service,run,{'id':'u1'},[link],[assertion],evidence,[entity])
    assert len(repeated['items'])==3
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs','run1')==run
        decision=json.loads(db.execute('SELECT payload FROM decisions').fetchone()['payload'])
        assert decision['before'] is None and decision['after']['origin']=='manual'


def test_relation_contract_and_manual_http_envelope(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    items=definitions()
    items.append(dict(items[1],id='RelatedComplex',kind='relation',range='CONCEPT_001',multivalued=True))
    run=dict(id='r',data_run_id='r',ontology_version_id='o',ontology_candidates=items,
             frozen_blocks=[dict(id='b',source_version_id='v',text='행복단지는 나단지와 관련된다.',locator={})],entities=[],accepted_aliases=[])
    unit=dict(id='u',block_ids=['b'])
    ev=[dict(block_id='b0',quote='행복단지는 나단지와 관련된다.')]
    output=dict(units=[dict(unit_id='t0',subject=dict(mention='행복단지',concept_id='CONCEPT_001',official_id=None,evidence=ev),
                facts=[dict(predicate_id='RelatedComplex',object=dict(mention='나단지',concept_id='CONCEPT_001',official_id=None,evidence=ev),
                    evidence=ev,unit=None,scope='미확인',scope_evidence=[],conditions=[],conditions_evidence=[],exceptions=[],exceptions_evidence=[])],reason='')])
    records,_,errors=contract.adapt(run,unit,output)
    assert not errors
    _,assertions,_=extraction.materialize(run,unit,records)
    assert assertions[0]['object_link_id'] and assertions[0]['value'] is None
    service,run,entity,link,assertion,evidence=setup(tmp_path)
    run['frozen_blocks'][0].update(source_version_id='v',locator={})
    with service.repository.connect() as db:db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run),'run1'))
    result=store.publish_unit(service,run,{'id':'u1'},[link],[assertion],evidence,[entity])
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    body=dict(expected_changeset_revision=1,actor='test',subject_link_id='link1',predicate_id='Households',block_id='block1',quote='985호',raw_value='985호')
    with TestClient(app) as client:
        url=f'/api/v1/knowledge/changes/{result["changeset_id"]}/assertions'
        response=client.post(url,json=body)
        assert response.status_code==200 and response.json()['success']
        assert response.json()['data']['items'][-1]['origin']=='manual'
        assert client.post(url,json=body).status_code==409

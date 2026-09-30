"""A5 storage boundaries; synthetic ledgers, no model calls or production approvals."""
from copy import deepcopy
import json

import pytest
import yaml

from app.knowledge import extraction_store as store, ontology_canonical as canonical, snapshots
from app.tests.unit.test_knowledge_extraction_store import setup
from app.tests.unit.test_knowledge_snapshots import create, activate, state


def prepared(tmp_path, required=True):
    service, old_run, entity, link, assertion, evidence = setup(tmp_path)
    block = old_run['frozen_blocks'][0]
    block.update(source_version_id='v1', parse_run_id='run1', locator={'format':'csv', 'physical_row':2})
    entity['namespace']='LH:complex'
    with service.repository.connect() as db:
        service.repository.save(db,'runs',old_run)
        base=service.repository.get(db,'ontology_versions','ontology1');base['status']='reviewed'
        db.execute('UPDATE ontology_versions SET payload=? WHERE id=?',(json.dumps(base),base['id']))
        for sid,vid,text in [('source1','v1',None),('schema-source','schema-v1','유형 설계의 근거'),('alias-source','alias-v1','이전 별칭의 근거')]:
            db.execute('INSERT INTO sources VALUES(?,?,?,?)',(sid,'test',sid,json.dumps(dict(id=sid,title=sid))))
            db.execute('INSERT INTO versions VALUES(?,?,?,?)',(vid,sid,vid,json.dumps(dict(id=vid,source_id=sid,sha256=vid,format='txt'))))
            item=block if text is None else dict(id=vid,evidence_id=vid,text=text,source_version_id=vid,parse_run_id='run1',locator={'format':'txt'})
            db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)',(item['id'],vid,'run1',vid,0,json.dumps(item)))
    first=store.publish_unit(service,old_run,{'id':'u1'},[link],[assertion],evidence,[entity])
    store.decide(service,first['changeset_id'],dict(actor='test',expected_changeset_revision=1,decisions=[
        dict(candidate_id='link1',action='accept'),dict(candidate_id='count1',action='accept')]))
    old_snapshot=create(service,dict(changeset_id=first['changeset_id'],expected_changeset_revision=2,candidate_ids=['link1','count1']))
    items=canonical.targets(base)
    items['Complex']['dependency_block_ids']=['schema-v1']
    items['Child']=dict(items['Complex'],id='Child',symbol='Child',name='하위 유형')
    items['edge']=dict(id='edge',symbol='edge',kind='hierarchy',child_id='Child',parent_id='Complex',relation='is_a')
    items['Households']['required']=required
    items['Related']=dict(items['Households'],id='Related',symbol='Related',kind='relation',range='Complex',required=False)
    version,_,_=canonical.build(base,items)
    version.update(id='ontology2',status='reviewed')
    run=deepcopy(old_run)
    run.update(id='run2',ontology_version_id=version['id'],consumer_contract={'role_targets':{'LH:complex':'Child'},'target_ids':{}})
    with service.repository.connect() as db:
        db.execute('INSERT INTO ontology_versions VALUES(?,?)',(version['id'],json.dumps(version)))
        db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],json.dumps(run)))
    new_link=dict(link,id='link2',local_candidate_key='link2',concept_id='Child',dependency_evidence_ids=['alias-v1'])
    new_assertion=dict(assertion,id='count2',local_candidate_key='count2',subject_link_id='link2')
    published=store.publish_unit(service,run,{'id':'u2'},[new_link],[new_assertion],[],[entity])
    return service, run, published['changeset_id'], old_snapshot


def accept(service,cid,revision=1):
    return store.decide(service,cid,dict(actor='test',expected_changeset_revision=revision,decisions=[
        dict(candidate_id='link2',action='accept'),dict(candidate_id='count2',action='accept')]))


def selection(cid,revision=2,ids=None):
    return dict(changeset_id=cid,expected_changeset_revision=revision,candidate_ids=ids or ['link2','count2'])


def test_v2_inherited_slots_mapped_identity_and_old_snapshot_remain_separate(tmp_path):
    service,run,cid,old=prepared(tmp_path)
    with service.repository.connect() as db:
        prior=service.repository.get(db,'snapshots',old)
        identity=service.repository.get(db,'entities','entity1')
    assert all(c['review_status']=='proposed' for c in store.candidates(service,cid)['items'])
    assert not any(c['validation_errors'] for c in store.candidates(service,cid)['items'])
    accept(service,cid)
    new=create(service,selection(cid));view=snapshots.get_snapshot(service,new)
    assert view['links'][0]['concept_id']=='Child'
    assert view['entities'][0]['concept_id']=='Complex'
    assert view['consumer_contract']==run['consumer_contract']
    assert view['run_scopes']==[dict(run_id='run2',changeset_id=cid,predicate_ids=None,block_ids=['block1'])]
    assert view['vocabulary_registry']['version']==1
    assert set(view['ontology_dependency_evidence_ids'])=={'schema-v1'}
    with service.repository.connect() as db:
        assert service.repository.get(db,'snapshots',old)==prior
        assert service.repository.get(db,'entities','entity1')==identity
        assert service.repository.get(db,'assertions','count1')['ontology_version_id']=='ontology1'
        captured=service.repository.get(db,'snapshots',new)
    assert {'schema-v1','alias-v1'} <= captured['evidence'].keys()
    assert snapshots.list_snapshots(service)['active_snapshot_id'] is None


@pytest.mark.parametrize('dependency',['schema-v1','alias-v1'])
@pytest.mark.parametrize('status',['blocked','needs_review'])
def test_schema_and_reused_alias_dependencies_gate_review_create_and_rollback(tmp_path,dependency,status):
    service,_,cid,_=prepared(tmp_path)
    state(service,'evidence',dependency,status)
    with pytest.raises(ValueError,match='usage_dependency_unavailable'):
        accept(service,cid)
    changed=store.decide(service,cid,dict(actor='test',expected_changeset_revision=1,decisions=[
        dict(candidate_id='link2',action='modify',patch={'mention':'C001'})]))
    assert changed['items'][0]['review_status']=='proposed'
    state(service,'evidence',dependency,'allowed');accept(service,cid,revision=2)
    first=create(service,selection(cid,3));activate(service,first)
    with service.repository.connect() as db:original=service.repository.get(db,'snapshots',first)
    state(service,'evidence',dependency,status)
    with pytest.raises(ValueError,match='사용 불가'):
        create(service,selection(cid,3))
    assert activate(service,first)['counts']['assertions']==0
    assert snapshots.export(service,first)['assertions']==[]
    assert len(snapshots.export(service,first,format='csv')['content'].splitlines())==1
    with service.repository.connect() as db:assert service.repository.get(db,'snapshots',first)==original


def test_required_inherited_slot_and_class_local_required_constraint(tmp_path):
    service,_,cid,_=prepared(tmp_path,required=False)
    with service.repository.connect() as db:
        version=service.repository.get(db,'ontology_versions','ontology2')
        schema=yaml.safe_load(version['linkml_yaml'])
        schema['classes']['Child']['slot_usage']={'Households':{'required':True}}
        version['linkml_yaml']=yaml.safe_dump(schema,allow_unicode=True)
        db.execute('UPDATE ontology_versions SET payload=? WHERE id=?',(json.dumps(version),version['id']))
    accept(service,cid)
    with pytest.raises(ValueError,match='필수 속성'):
        create(service,selection(cid,ids=['link2']))
    assert snapshots.get_snapshot(service,create(service,selection(cid)))['counts']['assertions']==1


def test_assertion_reaccept_does_not_reallow_changed_or_blocked_fact(tmp_path):
    service,_,cid,_=prepared(tmp_path)
    accept(service,cid);state(service,'assertion','count2','needs_review')
    reviewed=store.decide(service,cid,dict(actor='test',expected_changeset_revision=2,decisions=[dict(candidate_id='count2',action='accept')]))
    assert reviewed['items'][1]['review_status']=='accepted'
    assert snapshots.availability(service,'assertion','count2')['state']=='needs_review'
    with pytest.raises(ValueError,match='사용 불가'):create(service,selection(cid,3))
    state(service,'assertion','count2','blocked')
    with pytest.raises(ValueError,match='usage_dependency_unavailable'):
        store.decide(service,cid,dict(actor='test',expected_changeset_revision=3,decisions=[dict(candidate_id='count2',action='accept')]))


def test_v2_local_entity_and_relation_object_inheritance(tmp_path):
    service,run,cid,_=prepared(tmp_path)
    local=store.register_local_entity(service,dict(actor='test',reason='문서 개체',name='단지',concept_id='Child',
        ontology_version_id='ontology2',source_version_id='v1',evidence_ids=['block1']))
    assert local['concept_id']=='Child' and local['ontology_version_id']=='ontology2'
    accept(service,cid)
    store.add_manual(service,cid,dict(actor='test',reason='관계 검수',expected_changeset_revision=2,
        subject_link_id='link2',object_link_id='link2',predicate_id='Related',block_id='block1',quote='C001',scope='합성 자기 관계'))
    candidate=store.candidates(service,cid)['items'][-1]
    assert candidate['validation_errors']==[]
    store.decide(service,cid,dict(actor='test',expected_changeset_revision=3,decisions=[dict(candidate_id=candidate['id'],action='accept')]))
    snapshot=create(service,selection(cid,4,['link2','count2',candidate['id']]))
    assert snapshots.get_snapshot(service,snapshot)['counts']['assertions']==2
    state(service,'evidence','schema-v1','blocked')
    with pytest.raises(ValueError,match='사용 중단'):
        store.register_local_entity(service,dict(actor='test',reason='차단 확인',name='단지',concept_id='Child',
            ontology_version_id='ontology2',source_version_id='v1',evidence_ids=['block1']))


def test_unresolved_reference_classification_is_reviewed_history_not_a_new_concept(tmp_path):
    service,_,cid,_=prepared(tmp_path)
    for value in [None, {}, {'category':[],'reason':'오류'}, {'category':'new_concept','reason':' '},
                  {'category':'confirmed_concept','reason':'지원하지 않는 분류'}]:
        with pytest.raises(ValueError,match='발견 분류'):
            store.decide(service,cid,dict(actor='test',expected_changeset_revision=1,decisions=[
                dict(candidate_id='link2',action='modify',patch={'discovery_reference':value})]))
    store.decide(service,cid,dict(actor='test',expected_changeset_revision=1,decisions=[
        dict(candidate_id='link2',action='unlink',reason='연결 추가 검토')]))
    reference={'category':'ambiguity','reason':'동일 표기 대상이 하나인지 원문 보완 필요'}
    result=store.decide(service,cid,dict(actor='test',expected_changeset_revision=2,decisions=[
        dict(candidate_id='link2',action='modify',patch={'discovery_reference':reference},reason='발견 참고 분류')]))
    assert result['items'][0]['review_status']=='proposed'
    assert result['items'][0]['discovery_reference']==reference
    listing=store.candidates(service,cid)['changesets'][0]
    assert listing['decisions'][-1]['after']['discovery_reference']==reference
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM ontology_versions').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM entities').fetchone()[0]==1

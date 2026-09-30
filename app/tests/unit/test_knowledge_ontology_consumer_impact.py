"""A5 direct-consumer review uses synthetic ledgers and the existing A3 transaction."""
from copy import deepcopy
import json

import pytest

from app.knowledge import ontology_changes as changes, ontology_schema as schema, ontology_canonical as canonical, snapshots
from app.tests.unit.test_knowledge_discovery_run import corpus, service
from app.tests.unit.test_knowledge_ontology_changes import analysis, add, decide, listing, proposal as original_proposal


def proposal(ref,kind='class',**fields):
    value=original_proposal(ref,kind)
    value['after'].update(fields)
    return value


def base_version(service, with_slot=False):
    run,ref=analysis(service,observations=[])
    cid=changes.publish(service,run['id'])['changeset_id']
    first,second=add(service,cid,[proposal(ref,name='첫 유형'),proposal(ref,name='둘째 유형')])
    rows=[first,second]
    if with_slot:
        rows+=add(service,cid,[proposal(ref,'attribute',domain_id=first['target_id'],range='string')])
    result=decide(service,cid,[dict(candidate_id=c['id'],action='accept') for c in rows])
    return schema.get_ontology(service,result['ontology_head_id']),ref,rows


def next_change(service,base,ref,raw):
    run,_=analysis(service,base=base['id'],observations=[])
    cid=changes.publish(service,run['id'])['changeset_id']
    return cid,add(service,cid,[raw])[0]


def consumers(service,base,target):
    rows={
        'entities':[dict(id='entity',namespace='synthetic',official_id='one',concept_id=target)],
        # The type reaches the assertion through an entity even if the link's own type differs.
        'entity_links':[dict(id='link',concept_id='another_type',target_entity_id='entity')],
        'assertions':[dict(id=i,predicate_id='another_predicate',subject_link_id='link') for i in ('fact','blocked')]
            +[dict(id='unrelated',predicate_id='another_predicate')],
        'runs':[dict(id='past_extract',kind='extract',status='succeeded',ontology_candidates=[dict(id=target)])],
        'snapshots':[dict(id='past_snapshot',ontology=base)],
        'decisions':[dict(id='mapping',kind='lh_consumer_mapping',ontology_version_id=base['id'],target_ids={'CONCEPT_001':target})],
    }
    with service.repository.connect() as db:
        for table,values in rows.items():
            for value in values:
                payload=json.dumps(value,ensure_ascii=False)
                if table=='entities':
                    db.execute('INSERT INTO entities VALUES(?,?,?,?)',(value['id'],value['namespace'],value['official_id'],payload))
                elif table in {'entity_links','assertions'}:
                    db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?)',(value['id'],'past_extract','unit',value['id'],payload))
                else:
                    schema._insert(db,table,value)
        snapshots._write_status(db,[('assertion','blocked')],'blocked','tester','이전 사용 중단')
    return rows


def test_display_and_required_slot_impacts_preserve_existing_facts(service):
    base,ref,rows=base_version(service)
    first=rows[0]
    consumers(service,base,first['target_id'])
    cid,rename=next_change(service,base,ref,proposal(ref,name='표시명만 변경')|dict(
        operation='update',target_id=first['target_id']))
    assert rename['consumer_impact']['action']=='display_refresh' and rename['can_accept']
    assert set(rename['consumer_impact']['affected_assertion_ids'])=={'fact','blocked'}
    renamed=decide(service,cid,[dict(candidate_id=rename['id'],action='accept')])
    assert snapshots.availability(service,'assertion','fact')['state']=='allowed'
    current=schema.get_ontology(service,renamed['ontology_head_id'])
    cid,slot=next_change(service,current,ref,proposal(ref,'attribute',domain_id=first['target_id'],required=True))
    impact=slot['consumer_impact']
    assert impact['action']=='partial_extract' and impact['new_required'] and not impact['requires_resolution']
    assert impact['preserved_run_ids']==['past_extract'] and impact['preserved_snapshot_ids']==['past_snapshot']
    assert slot['can_accept'] and impact['new_facts']=='new_ontology_version_and_k4_review'
    alias=add(service,cid,[proposal(ref,'alias',alias_of=first['target_id'])])[0]
    assert alias['consumer_impact']['action']=='display_refresh'
    decide(service,cid,[dict(candidate_id=slot['id'],action='accept')])
    assert snapshots.availability(service,'assertion','fact')['state']=='allowed'
    assert schema.get_ontology(service,base['id'])==base


@pytest.mark.parametrize('patch',[
    {'after':{'name':'표시명','definition':'새 의미'}},
    {'qualifiers':{'scope':'새 적용 범위','statement_type':'design_proposal'}},
    {'qualifiers':{'time':'새 시점','statement_type':'design_proposal'}},
    {'after':{'name':'표시명','definition':'근거에 연결된 설계 정의','inclusion':'새 포함 조건'}},
])
def test_semantic_review_marks_linked_facts_and_keeps_frozen_consumers(service,patch):
    base,ref,rows=base_version(service)
    target=rows[0]['target_id']
    original=consumers(service,base,target)
    cid,c=next_change(service,base,ref,proposal(ref)|dict(operation='update',target_id=target)|patch)
    impact=c['consumer_impact']
    assert impact['action']=='semantic_review' and impact['requires_resolution'] and not c['can_accept']
    assert 'mapping_review:mapping' in impact['unresolved_reference_ids']
    with pytest.raises(ValueError,match='직접 참조 미해결'):
        decide(service,cid,[dict(candidate_id=c['id'],action='accept')])
    accepted=decide(service,cid,[dict(candidate_id=c['id'],action='accept',consumer_action='review_required')])
    saved=listing(service,cid)
    resolution=saved['candidates'][0]['consumer_resolution']
    assert resolution['marked_assertion_ids']==['fact']
    assert set(resolution['assertion_ids'])=={'fact','blocked'}
    assert resolution['actor']=='tester' and resolution['reason']=='원문과 구조 검수'
    assert resolution['ontology_version_id']==accepted['ontology_head_id']
    assert saved['decisions'][-1]['consumer_action']=='review_required'
    assert snapshots.availability(service,'assertion','fact')['state']=='needs_review'
    assert snapshots.availability(service,'assertion','blocked')['state']=='blocked'
    assert snapshots.availability(service,'assertion','unrelated')['state']=='allowed'
    with service.repository.connect() as db:
        for table,values in original.items():
            for value in values:
                assert service.repository.get(db,table,value['id'])==value
    assert schema.get_ontology(service,base['id'])==base
    # Reusing an old approval after a new meaning edit must not silently bypass review.
    with pytest.raises(ValueError,match='직접 참조 미해결'):
        decide(service,cid,[dict(candidate_id=c['id'],action='modify',patch={'after':dict(c['after'],definition='다시 바뀐 의미')})])


@pytest.mark.parametrize('operation',['deprecate','merge'])
def test_resolution_is_atomic_stale_safe_and_cannot_override_definition_references(service,monkeypatch,operation):
    base,ref,rows=base_version(service,with_slot=True)
    target=rows[0]['target_id']
    consumers(service,base,target)
    after={'canonical_id':rows[1]['target_id']} if operation=='merge' else {}
    cid,c=next_change(service,base,ref,proposal(ref)|dict(operation=operation,target_id=target,after=after))
    assert c['consumer_impact']['action']=='review_dependencies'
    current=listing(service,cid)
    request=dict(expected_changeset_revision=current['revision'],expected_ontology_head_id=base['id'],actor='tester',
        decisions=[dict(candidate_id=c['id'],action='accept',reason='직접 소비자 재검토',consumer_action='review_required')])
    with pytest.raises(ValueError,match='직접 정의 참조 미해결'):
        changes.decide(service,cid,request)
    assert snapshots.availability(service,'assertion','fact')['state']=='allowed'
    assert listing(service,cid)['revision']==current['revision']
    # Retire the directly dependent slot in the same accepted closure.
    slot=add(service,cid,[proposal(ref,'attribute')|dict(operation='deprecate',target_id=rows[2]['target_id'],after={})])[0]
    current=listing(service,cid)
    request.update(expected_changeset_revision=current['revision'])
    request['decisions'].append(dict(candidate_id=slot['id'],action='accept',reason='직접 슬롯 폐기',consumer_action='review_required'))
    stale=deepcopy(request);stale['expected_changeset_revision']-=1
    with pytest.raises(schema.VersionConflict): changes.decide(service,cid,stale)
    stale=deepcopy(request);stale['expected_ontology_head_id']=None
    with pytest.raises(schema.VersionConflict): changes.decide(service,cid,stale)
    build=canonical.build
    monkeypatch.setattr(canonical,'build',lambda *args:(_ for _ in ()).throw(ValueError('compile failure')))
    with pytest.raises(ValueError,match='compile failure'): changes.decide(service,cid,request)
    assert snapshots.availability(service,'assertion','fact')['state']=='allowed'
    assert listing(service,cid)['ontology_head_id']==base['id']
    monkeypatch.setattr(canonical,'build',build)
    result=changes.decide(service,cid,request)
    assert result['ontology_head_id']!=base['id']
    assert snapshots.availability(service,'assertion','fact')['state']=='needs_review'


@pytest.mark.parametrize('action,reason,actor',[
    ('defer','이유','tester'),('edit','이유','tester'),('accept',' ','tester'),('accept','이유',' '),
])
def test_consumer_action_requires_explicit_accept_actor_and_reason(service,action,reason,actor):
    base,ref,rows=base_version(service)
    consumers(service,base,rows[0]['target_id'])
    cid,c=next_change(service,base,ref,proposal(ref,definition='새 의미')|dict(operation='update',target_id=rows[0]['target_id']))
    current=listing(service,cid)
    with pytest.raises(ValueError):
        changes.decide(service,cid,dict(expected_changeset_revision=current['revision'],expected_ontology_head_id=base['id'],
            actor=actor,decisions=[dict(candidate_id=c['id'],action=action,reason=reason,consumer_action='review_required')]))
    assert listing(service,cid)['revision']==current['revision']
    assert snapshots.availability(service,'assertion','fact')['state']=='allowed'


def test_consumer_action_rejects_blanket_approval_without_changed_meaning(service):
    base,ref,rows=base_version(service)
    consumers(service,base,rows[0]['target_id'])
    cid,c=next_change(service,base,ref,proposal(ref,name='명칭만')|dict(operation='update',target_id=rows[0]['target_id']))
    with pytest.raises(ValueError,match='직접 참조가 있는 의미'):
        decide(service,cid,[dict(candidate_id=c['id'],action='accept',consumer_action='review_required')])
    fresh=add(service,cid,[proposal(ref)])[0]
    with pytest.raises(ValueError,match='직접 참조가 있는 의미'):
        decide(service,cid,[dict(candidate_id=fresh['id'],action='accept',consumer_action='review_required')])


@pytest.mark.parametrize('qualifiers', [{'scope':'한 업무에만 해당'}, {'time':'2024'}, {'negation':'negated'}])
def test_scoped_or_negated_alias_cannot_become_unconditional_synonym(service, qualifiers):
    base,ref,rows=base_version(service)
    consumers(service,base,rows[0]['target_id'])
    cid,alias=next_change(service,base,ref,proposal(ref,'alias',alias_of=rows[0]['target_id'])|
                         dict(qualifiers=dict(statement_type='design_proposal', **qualifiers)))
    assert not alias['can_accept']
    assert '조건부/부정 별칭' in str(alias['validation'])
    with pytest.raises(ValueError, match='조건부/부정 별칭'):
        decide(service,cid,[dict(candidate_id=alias['id'],action='accept')])
    assert listing(service,cid)['ontology_head_id']==base['id']

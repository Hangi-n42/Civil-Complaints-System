"""Exact run-local reuse without changing raw evidence, units or prior review."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_candidates as identities, discovery_review as reviews
from app.knowledge import ontology_changes, ontology_schema
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import done, request, response, model
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def observation(identifier):
    return dict(id=identifier,local_ref=identifier,label='임대',classification='type',definition='정의 그대로',
        conditions='공급 시',exceptions='',time='현재',support_type='explicit',cq_ids=['c1'],scope_item_ids=[],
        abstraction_level='유형',review_signals=[],evidence_ids=['b'],outside_scope_reason='',validation=[],
        evidence_refs=[dict(evidence_id='b',block_id='b',source_version_id='v',parse_run_id='p',span=[0,2],quote='정의')])


def unit(identifier, *rows):
    return dict(id=identifier,group_id=identifier,stage='concept',status='succeeded',input_hash='fixed-'+identifier,
        dependency_ids=['b'],output=dict(observations=list(rows)))


def run_with(*units):
    return dict(recipe=dict(candidate_version=identities.VERSION),analysis_units=list(units))


def test_exact_views_resolve_only_contract_references_and_keep_raw_and_review():
    first, second, parent = observation('one'), observation('two'), observation('parent')
    parent['definition']='다른 부모';parent['label']='주택'
    run=run_with(unit('u1',first,parent),unit('u2',second));raw=deepcopy(run['analysis_units'])
    identities.register(run)
    relation=dict(id='r',subject='two',object='parent',predicate='문자 two 보존',negation='affirmed',
                  candidate_view_version=identities.VERSION,
                  source_relation=dict(subject='two',object='parent'))
    hierarchy=dict(id='h',child_ref='two',parent_ref='parent',relation='is_a',validation=[])
    output=dict(observations=[first,second,parent],relations=[relation],hierarchies=[hierarchy],
                relation_bindings=[dict(relation_ref='r',subject_ref='two',object_ref='parent',reason='two 보존')],
                alignments=[dict(observation_ref='two',target_id='parent',reason='two는 문자열')])
    before=deepcopy(output);view=identities.output(run,output)
    assert len(view['observations'])==2
    assert view['relations'][0]['subject']==view['hierarchies'][0]['child_ref']=='one'
    assert view['alignments'][0]['observation_ref']=='one'
    assert view['relation_bindings'][0]==dict(relation_ref='r',subject_ref='one',object_ref='parent',reason='two 보존')
    assert identities.output(run,view)==view
    assert view['relations'][0]['predicate']=='문자 two 보존'
    assert view['relations'][0]['source_relation']==relation['source_relation']
    assert output==before and run['analysis_units']==raw
    candidate=view['observations'][0]
    old=dict(review_coverage=dict(valid_candidate_ids=['one'],candidate_hashes={'one':reviews.fingerprint(first)}))
    assert reviews.valid_ids(old,{'one':candidate})==set()
    assert reviews.valid_ids({}, {'one':candidate})==set()
    assert reviews.valid_ids({}, {'one':first}) is None
    current=dict(review_coverage=dict(valid_candidate_ids=['one'],candidate_hashes={'one':reviews.fingerprint(candidate)}))
    run['analysis_units'].append(unit('u3',observation('three')));identities.register(run)
    assert reviews.valid_ids(current,{'one':identities.view(run,first)})=={'one'}
    changed=dict(candidate,conditions='다른 조건')
    assert reviews.valid_ids(current,{'one':changed})==set()
    assert [x['raw_observation_id'] for x in run['candidate_identity']['discoveries']['one']]==['one','two','three']


@pytest.mark.parametrize('field,value', [('label','동의어'),('classification','entity'),('definition','다른 정의'),
    ('conditions','다른 조건'),('exceptions','예외'),('time','과거'),('support_type','design_proposal'),
    ('cq_ids',['c2']),('scope_item_ids',['s']),('validation',['근거 오류']),('evidence_refs',[])])
def test_different_or_invalid_observations_are_not_reused(field,value):
    second=observation('two');second[field]=value
    run=run_with(unit('u',observation('one'),second));identities.register(run)
    assert run['candidate_identity']['raw_to_candidate']=={'one':'one','two':'two'}


@pytest.mark.parametrize('field,value', [('source_version_id','v2'),('parse_run_id','p2'),('block_id','b2'),('span',[1,3]),('quote','다름')])
def test_different_source_identity_is_not_reused(field,value):
    second=observation('two');second['evidence_refs'][0][field]=value
    run=run_with(unit('u',observation('one'),second));identities.register(run)
    assert identities.identifier(run,'two')=='two'


def test_resume_keeps_first_registered_id_and_revised_or_revoked_source_is_not_substituted():
    earlier=unit('earlier',observation('early'));earlier['status']='failed'
    run=run_with(earlier,unit('later',observation('first')));identities.register(run)
    earlier['status']='succeeded';identities.register(run)
    assert identities.identifier(run,'early')=='first'
    run['analysis_units'].append(dict(id='revision',stage='revision',status='succeeded',output=dict(
        history=[dict(candidate_id='first',after=dict(observation('first'),definition='수정된 정의'))])))
    run['analysis_units'].append(unit('new',observation('new')));identities.register(run)
    assert identities.identifier(run,'new')=='new'
    run['analysis_units'][1]['dependency_ids'].append('revoked')
    assert identities.rows(run,[observation('early')],{'b'})==[]


@pytest.mark.parametrize('repeat_group',[False,True])
def test_relation_through_a3_and_resume_uses_representatives_without_rewriting_units(service,model,monkeypatch,repeat_group):
    source=prepare(service,file_ids=['current:0']);seen=[]
    if repeat_group:
        expand=a2.segments.expand
        def repeated(frontier,blocks):
            group=expand(frontier,blocks)[0]
            return [dict(deepcopy(group),id=group['id']+suffix) for suffix in ('_a','_b')]
        monkeypatch.setattr(a2.segments,'expand',repeated)
    async def fake(prompt,schema,stage,run,timeout):
        model.append(stage);data=json.loads(prompt.split('\nINPUT:\n')[1]);value=response(prompt,stage)
        if stage=='concept':
            value['observations'].append(dict(deepcopy(value['observations'][0]),local_ref='duplicate'))
        if stage in {'relation','builder','critic'}:
            assert len(data['unapproved_observations'])==2
            seen.append(stage)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',fake)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready',run.get('result')
    assert seen==['relation']*(2 if repeat_group else 1)+['builder','critic']
    raw=run['result']['original_observations'];representatives=run['result']['observations']
    assert len(raw)==(6 if repeat_group else 3) and len(representatives)==2
    first,duplicate=raw[0]['id'],raw[2]['id']
    assert run['candidate_identity']['raw_to_candidate'][duplicate]==first
    assert all(r['subject']==first for r in run['result']['original_relations'])
    saved=[(u['id'],deepcopy(u['output']),u['input_hash']) for u in run['analysis_units']]
    change_id=ontology_changes.publish(service,run['id'])['changeset_id']
    with service.repository.connect() as db:change=service.repository.get(db,'changesets',change_id)
    assert change['id_mapping'][first]['change_id']==change['id_mapping'][duplicate]['change_id']
    candidates=ontology_schema.candidates(service,change_id)['items']
    assert sum(c['target_kind']=='class' for c in candidates)==2
    types={c['target_id'] for c in candidates if c['target_kind']=='class'}
    assert all(c['after']['domain_id'] in types and c['after']['range'] in types for c in candidates if c['target_kind']=='relation')
    assert any(len(c['origin'].get('discoveries',[]))==2 for c in candidates)
    calls=list(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert again['status']=='review_ready',again.get('result')
    assert model==calls and again['candidate_identity']==run['candidate_identity']
    assert [(u['id'],u['output'],u['input_hash']) for u in again['analysis_units']]==saved
    legacy_review=deepcopy(again)
    for u in legacy_review['analysis_units']:
        if u['stage']=='critic': u['output'].pop('review_coverage')
    blocks=a2.load_blocks(service,legacy_review)
    a2.finish(legacy_review,blocks,{b['id'] for b in blocks})
    assert legacy_review['status']=='partial' and legacy_review['result']['review_groups']==0

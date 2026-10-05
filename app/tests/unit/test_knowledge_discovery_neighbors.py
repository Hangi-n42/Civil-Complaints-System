"""Direct extraction context is not a reviewed ontology or name-based identity."""
from copy import deepcopy
import json

import pytest
from app.knowledge import discovery_analysis as a2, discovery_synthesis as synthesis
from app.knowledge import discovery_review as reviews
from app.tests.unit.test_knowledge_discovery_scope import requirement_fixture
from app.tests.unit.test_knowledge_discovery_analysis import model, done, request
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def fixture():
    _,run,_,by,cm=requirement_fixture();run['id']='neighbors'
    run['recipe'].update(neighbor_contract='relation-neighbors-v1',num_ctx=65536,input_chars=30000)
    block=by['e'];block['text']='갑은 대상에 권한이 있다. 을은 같은 대상에 의무가 있다.'
    def relation(identifier,subject,start,end):
        return dict(id=identifier,subject=subject,object='대상',predicate='관여한다',direction='subject_to_object',
            statement_type='rule',negation='affirmed',conditions='조건 유지',time='',validation=[],outside_scope_reason='',
            evidence_ids=['e'],evidence_refs=[dict(block_id='e',evidence_id='e',source_version_id='v',parse_run_id='p',span=[start,end])])
    rows=[relation('r1','갑',0,len(block['text'])),relation('r2','을',0,len(block['text']))]
    run['analysis_units']=[dict(id='relation:g',stage='relation',status='succeeded',output=dict(relations=rows))]
    context=dict(blocks=[dict(ref='e',text=block['text'],span=[0,len(block['text'])])])
    return run,by,cm,context,rows


def test_neighbors_reach_prompt_without_merging_repeated_names_and_resume_pool():
    run,by,cm,context,rows=fixture();owner={}
    value,deps,supplied=synthesis.neighbor_context(run,'concept',context,{},owner,by,cm)
    assert len(value['relation_neighbors'])==2
    assert all(n['endpoints']['object']==[n['relation_ids'][0],'object'] for n in value['relation_neighbors'])
    _,prompt=a2.make_prompt(run,'concept',value,deps,supplied)
    payload=json.loads(prompt.split('\nINPUT:\n')[1])
    neighbor=payload['relation_neighbors'][0]
    assert neighbor['source_statement']['source_addresses'][0]['source_version_id']=='v'
    assert neighbor['source_statement']['direction']=='subject_to_object'
    assert neighbor['review_status']=='unreviewed' and neighbor['source_statement']['conditions']=='조건 유지'
    before=deepcopy(value)
    run['analysis_units'][0]['output']['relations'].append(dict(rows[0],id='later'))
    assert synthesis.neighbor_context(run,'concept',context,{},owner,by,cm)[0]==before


def test_shared_exact_mention_connects_different_relations_without_extra_model(monkeypatch):
    run,by,cm,context,rows=fixture()
    for row in rows: row['object']='권한'
    owner=dict(primary_candidate_ids=['r1'])
    result,_,_=synthesis.neighbor_context(run,'builder',context,{},owner,by,cm)
    assert set(result['conceptualization_context']['selected_relation_ids'])=={'r1','r2'}
    assert len(result['relation_neighbors'][0]['endpoints']['object'])==5
    run['recipe']['num_ctx']=100
    limited_owner=dict(primary_candidate_ids=['r1'])
    limited,_,_=synthesis.neighbor_context(run,'builder',context,{},limited_owner,by,cm)
    assert not limited['relation_neighbors'] and limited['blocks']==context['blocks']
    assert all(o['reason']=='complete_neighbor_packet_exceeds_capacity' for o in limited_owner['conceptualization_context']['builder']['omitted'])


def test_current_refutation_final_size_and_disabled_dependencies():
    run,by,cm,context,rows=fixture()
    review=dict(review_coverage=dict(candidate_hashes={'r1':reviews.fingerprint(rows[0])},valid_candidate_ids=['r1']),
        relation_checks=[dict(candidate_ref='r1',judgment='refuted')])
    run['analysis_units'].append(dict(id='critic:g',stage='critic',status='succeeded',output=review))
    owner={};value,deps,supplied=synthesis.neighbor_context(run,'concept',context,{},owner,by,cm)
    assert 'r1' not in value['conceptualization_context']['selected_relation_ids']
    assert any(o.get('reason')=='current_review_refuted' for o in owner['conceptualization_context']['concept']['omitted'])
    assert owner['conceptualization_context']['concept']['input_size']==synthesis.input_size(run,'concept',value,deps,supplied)
    run['recipe']['neighbor_contract']='disabled'
    unchanged,deps,terms=synthesis.neighbor_context(run,'builder',context,{'t':dict(id='t',origin_dependency_ids=['prior'])},{},by,cm)
    assert unchanged is context and deps==['e','prior'] and 't' in terms


def test_final_capacity_removes_actual_neighbor_with_comparison_copy():
    run,by,cm,context,_=fixture()
    term=dict(id='compare1',label='비교 유형',origin_dependency_ids=['prior'])
    context['comparison_terms']=[term];run['recipe']['input_chars']=6450
    result,deps,terms=synthesis.neighbor_context(run,'concept',context,{'compare1':term},{},by,cm)
    assert result['conceptualization_context']['selected_relation_ids']==[i for n in result['relation_neighbors'] for i in n['relation_ids']]
    assert synthesis.input_size(run,'concept',result,deps,terms)['input_chars']<=6450
    assert result['blocks']==context['blocks']


def test_repeated_mention_duplicates_share_statement_not_endpoint_identity():
    run,by,cm,context,rows=fixture()
    duplicate=dict(deepcopy(rows[0]),id='r3')
    run['analysis_units'][0]['output']['relations']=[rows[0],duplicate]
    value,deps,terms=synthesis.neighbor_context(run,'concept',context,{},dict(),by,cm)
    _,prompt=a2.make_prompt(run,'concept',value,deps,terms)
    packet=json.loads(prompt.split('\nINPUT:\n')[1]);neighbors=packet['relation_neighbors']
    assert len(neighbors)==1 and neighbors[0]['relation_ids']==['r1','r3']
    assert [o['endpoints']['object'] for o in neighbors[0]['origins']]==[['r1','object'],['r3','object']]
    assert all(o['review_status']=='unreviewed' for o in neighbors[0]['origins'])
    assert json.dumps(packet,ensure_ascii=False).count('"conditions": "조건 유지"')==1


def test_builder_neighbor_reuses_already_supplied_statement():
    run,by,cm,context,rows=fixture();context['unapproved_relations']=[rows[0]]
    value,deps,terms=synthesis.neighbor_context(run,'builder',context,{'r1':rows[0]},dict(primary_candidate_ids=['r1']),by,cm)
    _,prompt=a2.make_prompt(run,'builder',value,deps,terms)
    packet=json.loads(prompt.split('\nINPUT:\n')[1]);neighbor=packet['relation_neighbors'][0]
    assert 'source_statement' not in neighbor
    assert neighbor['source_statement_ref']==dict(field='unapproved_relations',relation_id='r1')
    assert neighbor['source_addresses'][0]['source_version_id']=='v'
    assert json.dumps(packet,ensure_ascii=False).count('"conditions": "조건 유지"')==1


@pytest.mark.parametrize('relation_failure',[False,True])
def test_product_calls_relation_before_independent_definition(service,model,monkeypatch,relation_failure):
    source=prepare(service,file_ids=['current:0']);recipe=a2.recipe;call=a2.model_call;stages=[]
    monkeypatch.setattr(a2,'recipe',lambda budgets:dict(recipe(budgets),neighbor_contract='relation-neighbors-v1'))
    async def observed(prompt,schema,stage,run,timeout):
        stages.append(stage)
        result=await call(prompt,schema,stage,run,timeout)
        if stage=='relation' and relation_failure: result['text']='{'
        return result
    monkeypatch.setattr(a2,'model_call',observed)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert stages.index('relation')<stages.index('concept')
    concept=next(u for u in run['analysis_units'] if u['stage']=='concept')
    assert concept['status']=='succeeded',concept.get('error')
    data=json.loads(concept['prompt'].split('\nINPUT:\n')[1])
    assert data['blocks'] and 'conceptualization_context' in data
    if relation_failure: assert data['conceptualization_context']['status']=='graph_pool_not_yet_extracted'

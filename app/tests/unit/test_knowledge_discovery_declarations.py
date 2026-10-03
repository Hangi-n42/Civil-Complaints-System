"""Shared Builder declarations use the real call/normalization/finish/A3 boundaries."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import discovery_analysis as a2, discovery_design as design, discovery_review as reviews
from app.knowledge import discovery_synthesis as synthesis, ontology_changes as a3, ontology_schema
from app.tests.unit.test_knowledge_discovery_analysis import done, request, model, source_response
from app.tests.unit.test_knowledge_discovery_roles import role_wire
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def test_two_relations_share_two_declarations_and_invalidate_both_reviews(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;seen=[]
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(json.loads(result['text']),data)
        if stage=='concept': value.update(observations=[],gaps=['이 시험은 관계 역할 선언을 검수'])
        if stage=='relation': value['relations'].append(dict(value['relations'][0],conditions='다른 명제 조건'))
        if stage=='builder':
            relations=data['unapproved_relations'];first=relations[0]
            value=dict(observations=[dict(role_wire(data,first,endpoint),local_ref=f't{n}')
                       for n,endpoint in enumerate(('subject','object'),1)],
                relation_bindings=[dict(relation_ref=i,decision='bind',subject_ref='t1',object_ref='t2',reason='선언한 출처 역할을 비교하여 공유') for i in data['design_relation_ids']],
                hierarchies=[],alias_proposals=[],gaps=[],actions=[])
            jsonschema.validate(value,schema)
            assert all(v['properties']['observations']['maxItems']==4 for v in schema['anyOf'])
            seen.append(deepcopy(value))
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=24,additional_rounds=0,revisions=0)))['run_id'])
    assert not run['result']['failures'],run['result']['failures']
    types=run['result']['observations'];relations=run['result']['relations']
    assert len(types)==len(relations)==2 and len(seen)==1
    assert len({r['subject'] for r in relations})==len({r['object'] for r in relations})==1
    assert relations[0]['source_relation']['conditions']!=relations[1]['source_relation']['conditions']
    source_id=seen[0]['observations'][0]['role_basis']['relation_ref']
    assert all(t['source_relation_ids']==[source_id] for t in types)
    assert all(t['role_source']['id']==source_id for t in types)
    current={c['id']:c for c in types+relations}
    assert set(current)<=set(reviews.latest_by_candidate(run['result']['critiques'],current))
    changed=deepcopy(current);changed[relations[0]['subject']]['definition']+=' 명시 수정'
    valid=reviews.latest_by_candidate(run['result']['critiques'],changed)
    assert not {r['id'] for r in relations}&set(valid)
    publication=a3.publish(service,run['id'])
    candidates=ontology_schema.candidates(service,publication['changeset_id'])['items']
    assert [c['target_kind'] for c in candidates].count('class')==2
    assert [c['target_kind'] for c in candidates].count('relation')==2


@pytest.mark.parametrize('mode',['canonical','collision','legacy','undeclared','duplicate','over_capacity','direct','initial_direct','legacy_direct'])
def test_shared_wire_ids_and_correction_capacity(service,model,monkeypatch,mode):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=24,additional_rounds=0,revisions=0)))['run_id'])
    existing=dict(run['result']['observations'][0],id='t1')
    natural=deepcopy(run['result']['relations'][0]['source_relation'])
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    _,_,context_map=a2.profile.survey(run['frozen_input']['files'],blocks)
    context,deps,supplied=synthesis.context_for([existing,natural],by_id,context_map)
    context.update(design_relation_ids=[natural['id']],binding_before=run['result']['relations'][0],parent_group_id=run['candidate_groups'][0]['id'])
    if mode=='initial_direct':
        context.pop('binding_before');context.pop('parent_group_id')
    if mode=='legacy':
        run['recipe'].pop('reference_contract')
        monkeypatch.setattr(a2,'recipe',lambda budgets:deepcopy(run['recipe']))
    if mode=='legacy_direct':
        run['recipe'].pop('builder_definition_contract')
        monkeypatch.setattr(a2,'recipe',lambda budgets:deepcopy(run['recipe']))
    async def generated(prompt,schema,stage,current,timeout):
        assert stage=='builder'
        data=json.loads(prompt.split('\nINPUT:\n')[1]);relation=data['unapproved_relations'][0]
        token='t1' if mode in {'legacy','collision'} else 't2'
        declaration=dict(role_wire(data,relation),local_ref=token)
        value=dict(observations=[declaration],relation_bindings=[dict(relation_ref=data['design_relation_ids'][0],
            decision='bind',subject_ref=data['unapproved_observations'][0]['id'],object_ref=token,reason='기존 주체와 새 대상 역할 연결')],
            hierarchies=[],alias_proposals=[],gaps=[],actions=[])
        assert all(v['properties']['observations']['maxItems']==2 for v in schema['anyOf'])
        if mode in {'direct','initial_direct','legacy_direct'}:
            declaration.pop('role_basis')
            declaration.update(label='직접 유형',definition='원문 직접 정의',conditions='',exceptions='',time='',
                source_relation_ids=[relation['id']],direct_definition_source_refs=declaration['source_refs'])
        if mode in {'collision','direct','initial_direct'}:
            with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,schema)
        else: jsonschema.validate(value,schema)
        if mode=='undeclared': value['relation_bindings'][0]['object_ref']='t5'
        if mode=='duplicate': value['observations'].append(deepcopy(declaration))
        if mode=='over_capacity':
            value['observations'] += [dict(declaration,local_ref=t) for t in ('t3','t4')]
            with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,schema)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    output=a2.call(service,run,'builder','shared_wire',context,deps,by_id,supplied)
    if mode in {'collision','duplicate','over_capacity','direct','initial_direct'}:
        assert output is None
        if mode in {'direct','initial_direct'}: assert json.loads(run['analysis_units'][-1]['raw_output'])['observations'][0]['definition']=='원문 직접 정의'
        assert any(word in run['analysis_units'][-1]['error'] for word in ('충돌','중복','상한','출처 역할 선언'))
    elif mode=='undeclared':
        assert output['binding_errors'] and not output['modeled_relations']
    else:
        assert output is not None,run['analysis_units'][-1]['error']
        assert not output['binding_errors'] and len(output['observations'])==1
        assert output['modeled_relations'][0]['subject']=='t1'
        assert output['modeled_relations'][0]['object']==output['observations'][0]['id']!='t1'


def test_scoping_keeps_distinct_role_declarations():
    value=dict(observations=[dict(local_ref='t1',role_basis=dict(relation_ref='r1',endpoint='subject')),
        dict(local_ref='t2',role_basis=dict(relation_ref='r2',endpoint='subject'))],
        relation_bindings=[dict(subject_ref='t1',object_ref='t2')])
    design.scope_local_refs(value, ['provided'])
    assert len({c['_binding_ref'] for c in value['observations']})==2
    assert [c['role_basis']['relation_ref'] for c in value['observations']]==['r1','r2']

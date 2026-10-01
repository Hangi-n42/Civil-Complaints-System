"""Per-target role contracts; stored legacy citation records remain readable."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_design as design, discovery_synthesis as synthesis
from app.knowledge import ontology_changes
from app.tests.unit.test_knowledge_discovery_analysis import done, request, response, model, source_response
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


def test_builder_target_binding_defer_missing_and_duplicate_are_separate():
    types={i:dict(id=i,classification='type') for i in ('a','b')}
    rules={i:dict(id=i,statement_type='rule',subject='사업자',object='입주자',conditions='A 또는 B, 다만 C 제외',
        validation=[],evidence_ids=['e']) for i in ('r1','r2','r3')}
    supplied={**types,**rules};original=deepcopy(supplied)
    first=dict(relation_ref='r1',subject_ref='a',object_ref='b',reason='주어진 유형 정의와 대조')
    output=dict(observations=[],relation_bindings=[first,dict(relation_ref='r2',decision='defer',reason='입주자 유형 정의 미제공')])
    design.bind(output,supplied,{},dict(design_relation_ids=list(rules)))
    coverage=output['binding_coverage']
    assert coverage['bound_relation_ids']==['r1'] and coverage['deferred_relation_ids']==['r2']
    assert coverage['pending_relation_ids']==['r3']
    assert output['modeled_relations'][0]['source_relation']==rules['r1'] and supplied==original
    duplicate=a2.models.Taxonomy.model_validate(dict(observations=[],relation_bindings=[first]*5+[dict(first,relation_ref='r3')],
        hierarchies=[],alias_proposals=[],gaps=[],actions=[])).model_dump(warnings=False)
    design.bind(duplicate,supplied,{},dict(design_relation_ids=list(rules)))
    assert duplicate['binding_coverage']['bound_relation_ids']==['r3']
    assert duplicate['binding_coverage']['pending_relation_ids']==['r1','r2']
    empty=dict(observations=[],relation_bindings=[])
    design.bind(empty,supplied,{},dict(design_relation_ids=[]))
    assert not empty['binding_errors'] and not empty['binding_coverage']['pending_relation_ids']


@pytest.mark.parametrize('bad',['missing','duplicate','unsupported','outside','unknown'])
def test_observation_judgments_preserve_valid_sibling_and_a3(service,model,monkeypatch,bad):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def review(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text']);item=value['observation_checks'][1]
            if bad=='missing': value['observation_checks'].pop()
            elif bad=='duplicate': value['observation_checks'].extend(deepcopy(item) for _ in range(17))
            elif bad=='unsupported': item.update(evidence_id='',quote='')
            elif bad=='outside': item['evidence_id']='outside'
            else: item.update(judgment='unknown',evidence_id='',quote='',reason='유형의 범위에 필요한 정의가 없음')
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',review)
    run=done(service,service.start(request(source['id']))['run_id'])
    critic=next(u for u in run['analysis_units'] if u['stage']=='critic')
    group=run['candidate_groups'][0];review=critic['output'];first,second=run['result']['observations']
    expected=set(group['primary_candidate_ids'])|{h['id'] for h in run['result']['taxonomy'][0]['hierarchies']}
    assert set(review['review_coverage']['expected_candidate_ids'])==expected
    assert first['id'] in review['review_coverage']['valid_candidate_ids']
    assert (second['id'] in review['review_coverage']['pending_candidate_ids'])==(bad!='unknown')
    if bad=='unknown': assert review['review_outcomes']['unknown']
    cid=ontology_changes.publish(service,run['id'])['changeset_id']
    with service.repository.connect() as db: changes=service.repository.get(db,'changesets',cid)['candidates']
    good=next(c for c in changes if c['origin']['candidate_id']==first['id'])
    unresolved=next(c for c in changes if c['origin']['candidate_id']==second['id'])
    assert good['origin']['observation_checks'] and not good['origin'].get('review_errors')
    assert unresolved['review_status']=='deferred'


@pytest.mark.parametrize('comparison_only',[False,True])
def test_new_generation_schema_citations_and_target_bounds(service,model,monkeypatch,comparison_only):
    import jsonschema
    source=prepare(service,file_ids=['current:0']);seen={}
    if comparison_only:
        assemble=synthesis.assemble
        def comparison(*args): return [dict(g,comparison_only=True) for g in assemble(*args)]
        monkeypatch.setattr(synthesis,'assemble',comparison)
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(response(prompt,stage),data)
        # Pydantic defaults are materialized for the generation schema's complete envelope.
        if stage=='builder': value.setdefault('observations', [])
        if stage=='concept':
            for c in value['observations']:
                c.update(classification_reason='원문의 일반 유형',conditions='',exceptions='',time='')
        jsonschema.validate(value,schema)
        if stage=='builder':
            assert all(v['properties']['relation_bindings']['minItems']==v['properties']['relation_bindings']['maxItems']==len(data['design_relation_ids'])<=5 for v in schema['anyOf'])
        if stage=='critic':
            assert set(data['review_target_ids']).isdisjoint(data['comparison_candidate_ids'])
        seen[stage]=len(prompt)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['status']=='review_ready',run['result']['failures']
    assert max(seen.values())<=run['recipe']['input_chars']
    print('E2 actual input chars:',seen)
    if not comparison_only:
        trial=deepcopy(run);trial['candidate_groups']=[]
        trial['analysis_units']=[u for u in trial['analysis_units'] if u['stage'] in {'scout','concept','relation'}]
        unit=next(u for u in trial['analysis_units'] if u['stage']=='relation')
        unit['output']['relations']=[dict(unit['output']['relations'][0],id='relation'+str(n)) for n in range(6)]
        blocks=a2.load_blocks(service,trial);by_id={b['id']:b for b in blocks}
        groups=synthesis.assemble(trial,0,by_id,a2.profile.contexts(blocks),set(by_id))
        counts=[sum(c['id'] in g['primary_candidate_ids'] and c.get('statement_type') in {'rule','definition'} for c in g['candidates']) for g in groups]
        assert sum(counts)==6 and max(counts)<=5

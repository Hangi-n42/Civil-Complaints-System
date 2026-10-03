"""Actual Critic schemas match the server's semantic-check evidence aggregation."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import discovery_analysis as a2
from app.tests.unit.test_knowledge_discovery_analysis import done, request, model, source_response
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


@pytest.mark.parametrize('current',[True,False])
def test_semantic_check_citation_and_missing_comparison_schema(service,model,monkeypatch,current):
    recipe=a2.recipe
    if not current:
        def legacy(budgets):
            value=recipe(budgets);value.pop('review_evidence_contract');return value
        monkeypatch.setattr(a2,'recipe',legacy)
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;seen=set()
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage!='critic': return result
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(json.loads(result['text']),data)
        for section,name in [('relation_checks','RelationCheck'),('observation_checks','ObservationCheck')]:
            if not value[section]: continue
            seen.add(section)
            record=deepcopy(value[section][0])
            if section=='relation_checks':
                record.pop('binding_checks',None);record.pop('binding_reasons',None)
            contract={'$defs':schema['$defs'],'$ref':'#/$defs/'+name}
            jsonschema.validate(record,contract)
            fields=list(record['semantic_checks'])
            for judgments in (['supported']*4,['refuted']+['supported']*3,
                               ['unknown']+['supported']*3,['refuted','unknown','supported','supported']):
                trial=dict(record,semantic_checks=dict(zip(fields,judgments)),source_refs=[])
                if current and ('refuted' in judgments or 'unknown' not in judgments):
                    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(trial,contract)
                else: jsonschema.validate(trial,contract)
                trial['source_refs']=record['source_refs']
                jsonschema.validate(trial,contract)
        if data.get('review_scope',{}).get('missing_meanings_allowed'):
            missing={'$defs':schema['$defs'],'$ref':'#/$defs/MissingMeaning'}
            row=dict(role='relation',meaning='현재 범위에서 확인할 누락',source_refs=[data['blocks'][0]['source_ref']],
                cq_ids=['cq1'],scope_item_ids=[],outside_scope_reason='',compared_candidate_ids=[],comparison_reason='제공 후보와 비교')
            if current:
                with pytest.raises(jsonschema.ValidationError): jsonschema.validate(row,missing)
            else: jsonschema.validate(row,missing)
            row['compared_candidate_ids']=[data['review_target_ids'][0]]
            jsonschema.validate(row,missing);seen.add('missing')
        return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=16,additional_rounds=0,revisions=0)))['run_id'])
    assert not run['result']['failures'],run['result']['failures']
    assert seen=={'relation_checks','observation_checks','missing'}

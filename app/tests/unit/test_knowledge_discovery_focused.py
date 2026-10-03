"""Focused serial review boundaries; synthetic responses are not quality evidence."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_synthesis as synthesis, discovery_review as reviews
from app.knowledge import ontology_changes, ontology_run
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import done, request, response, source_response, model
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare
from app.tests.unit.test_knowledge_ontology_changes import listing


def test_discovery_model_is_independent_of_k3(monkeypatch):
    before=ontology_run.recipe()
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REVIEW_MODEL','focused-test')
    assert a2.recipe({})['models']['review']=='focused-test'
    assert ontology_run.recipe()==before


@pytest.mark.parametrize('mode',['normal','cancel','partial'])
def test_focused_units_resume_partial_and_a3(service,model,monkeypatch,mode):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;count=0
    async def generated(prompt,schema,stage,run,timeout):
        nonlocal count
        if stage=='critic':
            count+=1
        if mode=='partial' and stage=='binding': raise ValueError('synthetic binding failure')
        value=await original(prompt,schema,stage,run,timeout)
        if stage=='critic' and count==1 and mode=='cancel':service.cancel(run['id'])
        return value
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    group=run['candidate_groups'][0]
    assert len(group['review_unit_ids'])==4 and all('reserved' not in i for i in group['review_unit_ids'])
    if mode=='cancel':
        assert run['status']=='cancelled'
        stored={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'}
        run=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
        assert all(all(u[k]==stored[u['id']][k] for k in ('output','raw_output','input_hash','attempts','dependency_ids')) for u in run['analysis_units'] if u['id'] in stored)
    critiques=[u for u in run['analysis_units'] if u['stage']=='critic']
    assert len(critiques)==4
    targets=[i for r in run['result']['critiques'] for i in r['review_coverage']['expected_candidate_ids']]
    assert len(targets)==len(set(targets))
    assert all(len(u['output']['review_coverage']['expected_candidate_ids'])<=2 for u in critiques if u['status']=='succeeded')
    assert bool(run['result']['mandatory_pending'])==(mode=='partial')
    assert run['status']==('partial' if mode=='partial' else 'review_ready')
    calls=len(model);saved=deepcopy(run['analysis_units'])
    if mode!='partial':
        again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
        assert len(model)==calls and again['analysis_units']==saved
    cid=ontology_changes.publish(service,run['id'])['changeset_id'];rows=listing(service,cid)['candidates']
    if mode=='partial':
        pending=set(run['result']['review_pending_candidate_ids'])
        assert pending and all(not c['can_accept'] for c in rows if c['origin'].get('candidate_id') in pending)


@pytest.mark.parametrize('mode',['revision','cancel_revision','budget'])
def test_focused_revision_latest_and_reservation(service,model,monkeypatch,mode):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1]);result=await original(prompt,schema,stage,run,timeout);value=json.loads(result['text'])
        if stage=='builder':value['hierarchies']=[]
        if stage=='critic' and value['relation_checks']:
            followup=any(u['stage']=='revision' and u['status']=='succeeded' for u in run['analysis_units'])
            if not followup:
                value['relation_checks'][0]['judgment']='refuted'
                value['relation_checks'][0]['semantic_checks']['conditions']='refuted'
                value['needs_revision']=True
            else: assert data['unapproved_relations'][0]['conditions']=='수정된 적용 범위'
        if stage=='revision':
            target=data['targets'][0]
            row={k:target[k] for k in a2.models.Relation.model_fields if k in target}
            row.update(local_ref='r1',candidate_ref=target['id'],reason='근거 조건 보완',conditions='수정된 적용 범위')
            row['endpoint_labels']={k:row[k] for k in ('subject','object')}
            value=dict(observations=[],relations=[row],hierarchies=[],deferred=[])
            if mode=='cancel_revision':service.cancel(run['id'])
        result['text']=json.dumps(source_response(value,data),ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=8 if mode=='budget' else 12,additional_rounds=0,revisions=1)))['run_id'])
    if mode=='cancel_revision':
        assert run['status']=='cancelled'
        saved={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'}
        run=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
        assert all(u==saved[u['id']] for u in run['analysis_units'] if u['id'] in saved)
    group=run['candidate_groups'][0]
    if mode=='budget':
        assert not run['result']['revision_history'] and run['result']['revision_deferrals']
        assert group['revision_reservation']['model_calls']==4
        return
    assert not run['result']['failures'],run['result']['failures']
    assert len(group['review_unit_ids'])==len(group['revision_review_unit_ids'])==3
    assert len([u for u in run['analysis_units'] if u['stage']=='revision'])==1
    current=run['result']['relations'][0];rid=current['id'];assert current['conditions']=='수정된 적용 범위'
    old=reviews.complete_reviews([dict(unit_id=u['id'],**u['output']) for u in run['analysis_units'] if u['id'] in group['review_unit_ids']])
    new=reviews.complete_reviews([dict(unit_id=u['id'],**u['output']) for u in run['analysis_units'] if u['id'] in group['revision_review_unit_ids']])
    assert not any(rid in (reviews.valid_ids(r,{rid:current}) or set()) for r in old)
    assert any(rid in (reviews.valid_ids(r,{c['id']:c for c in run['result']['observations']+[current]}) or set()) for r in new)
    assert not run['result']['mandatory_pending']
    cid=ontology_changes.publish(service,run['id'])['changeset_id'];rows=listing(service,cid)['candidates']
    row=next(c for c in rows if c['origin'].get('candidate_id')==rid)
    assert [c['judgment'] for c in row['origin']['relation_checks']]==['supported']


def test_focused_comparison_issue_cannot_overwrite_owner_revision():
    candidate=dict(id='candidate',classification='type');other=dict(id='other',classification='type')
    group=dict(id='g',candidates=[candidate,other],primary_candidate_ids=['candidate','other'],design_candidate_ids=[])
    issue=dict(candidate_ref='candidate',cause='content_error',reason='comparison concern')
    run=dict(recovery_requests=[],analysis_units=[],candidate_groups=[group])
    owner=dict(issues=[issue],review_coverage=dict(expected_candidate_ids=['candidate']))
    comparison=dict(issues=[issue],review_coverage=dict(expected_candidate_ids=['other']))
    a2.queue_recovery(run,owner,group);a2.queue_recovery(run,comparison,group)
    assert {(r['role'],r['status']) for r in run['recovery_requests']}=={('revision','pending'),('review','manual_review')}
    assert len({r['id'] for r in run['recovery_requests']})==2


def test_combined_review_keeps_comparison_error_out_of_owner_revision():
    def output(target,issues=()):
        return dict(needs_revision=bool(issues),issues=list(issues),review_coverage=dict(expected_candidate_ids=[target],
            valid_candidate_ids=[target],pending_candidate_ids=[],candidate_hashes={target:'hash'}))
    owner=output('minister');comparison=output('governor',[dict(candidate_ref='minister',cause='content_error',reason='outside focused target')])
    combined=synthesis.combined_review([owner,comparison])
    assert combined['issues']==[] and not combined['needs_revision']
    assert comparison['issues'] and 'minister' in combined['review_coverage']['valid_candidate_ids']


def test_binding_failure_resume_and_composition_identity_boundaries(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;binding_attempts=0
    async def generated(prompt,schema,stage,run,timeout):
        nonlocal binding_attempts
        if stage=='binding':
            binding_attempts+=1
            if binding_attempts==1: raise ValueError('first binding call failed')
        return await original(prompt,schema,stage,run,timeout)
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    rid=run['result']['relations'][0]['id']
    assert rid in run['result']['review_pending_candidate_ids'] and run['status']=='partial'
    partial=next(r for r in run['result']['critiques'] if rid in r['review_coverage']['expected_candidate_ids'])
    assert not partial['relation_checks'] and rid not in reviews.valid_ids(partial)
    saved={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'}
    run=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert binding_attempts==2 and run['status']=='review_ready'
    assert all(u==saved[u['id']] for u in run['analysis_units'] if u['id'] in saved)
    parts=[dict(unit_id=u['id'],**u['output']) for u in run['analysis_units'] if u['output'].get('review_component')]
    assert {p['review_component'] for p in parts}=={'proposition','binding'}
    assert not any(reviews.valid_ids(p) for p in parts) and not reviews.latest_by_candidate(parts,{rid:run['result']['relations'][0]})
    assert len({u['input_hash'] for u in run['analysis_units'] if u['id'] in {p['unit_id'] for p in parts}})==2
    joined=reviews.complete_reviews(parts)[0]
    assert rid in reviews.valid_ids(joined) and set(joined['component_unit_ids'])=={p['unit_id'] for p in parts}
    for field in ('review_bundle_id','review_scope_hash','candidate_hash','type_hash'):
        wrong=deepcopy(parts);binding=next(p for p in wrong if p['review_component']=='binding')
        if field=='candidate_hash':binding['review_coverage']['candidate_hashes'][rid]='different'
        elif field=='type_hash':binding['binding_dependency_hashes'][rid]['object']='different'
        else:binding[field]='different'
        result=reviews.complete_reviews(wrong)[0]
        assert rid not in reviews.valid_ids(result) and not result['relation_checks'] and result['record_errors']
    cid=ontology_changes.publish(service,run['id'])['changeset_id']
    row=next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==rid)
    assert set(joined['component_unit_ids']) <= set(row['origin']['analysis_unit_ids'])
    assert len(row['origin']['relation_checks'])==1


def test_proposition_cannot_inject_endpoint_error_into_supported_binding(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        value=json.loads(result['text'])
        if stage=='critic' and value['relation_checks']:
            check=value['relation_checks'][0]
            check.update(binding_checks=dict(subject='supported',object='refuted'),
                binding_reasons=dict(subject='오염 응답',object='별도 연결 판정을 흉내 낸 응답'))
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id']))['run_id'])
    parts={u['output'].get('review_component'):u for u in run['analysis_units'] if u.get('output',{}).get('review_component')}
    proposition=parts['proposition'];binding=parts['binding']
    assert 'refuted' in proposition['raw_output'] and proposition['output']['record_errors']
    assert binding['output']['binding_check']['binding_checks']['object']=='supported'
    assert not proposition['output']['issues'] and not run['recovery_requests']
    rid=run['result']['relations'][0]['id']
    assert rid in run['result']['review_pending_candidate_ids']
    merged=next(r for r in run['result']['critiques'] if r['unit_id']==proposition['id'])
    assert not merged['relation_checks'] and not merged['issues'] and not reviews.valid_ids(merged)

"""Cause-scoped recovery, using the existing executor and deterministic model doubles."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_profile as profile
from app.knowledge.discovery_models import Relation
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import corpus, service, model, prepare, request, done


@pytest.mark.parametrize('cause', ['endpoint','alignment','source_absent'])
def test_non_extraction_causes_preserve_relation_and_do_not_recall(service, monkeypatch, model, cause):
    source=prepare(service,file_ids=['current:0']); original=a2.model_call
    async def review(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]); value=json.loads(result['text'])
        if stage=='relation' and cause=='endpoint': value['relations'][0]['subject']='원문 역할'
        if stage=='critic':
            candidate=data['unapproved_relations'][0] if cause=='endpoint' else data['unapproved_observations'][0]
            value['issues']=[dict(local_ref='i1',candidate_ref=candidate['id'],cause=cause,
                target_ref=data['unapproved_observations'][1]['id'] if cause=='alignment' else '',
                reason='주어진 대상의 연결 또는 원문 확인 필요',defer_reason='참조 별표 본문이 이번 고정 입력에 제공되지 않음' if cause=='source_absent' else '명시 검수 필요',
                evidence_ids=[],counter_evidence_ids=[])]
            value['needs_revision']=True
        result['text']=json.dumps(value,ensure_ascii=False); return result
    monkeypatch.setattr(a2,'model_call',review)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert model==['scout','concept','relation','builder','critic']
    pending=[r for r in run['result']['unresolved_recovery_requests'] if r['cause']==cause]
    assert len(pending)==1 and pending[0]['status']==('source_absent' if cause=='source_absent' else 'manual_review')
    assert run['metrics']['recovery_calls']==0 and run['metrics']['recovery_remaining_by_cause'][cause]==1
    before=deepcopy(run['analysis_units'])
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(model)==5 and again['analysis_units']==before
    assert again['result']['original_relations']==run['result']['original_relations']


@pytest.mark.parametrize('mutate_meaning', [False,True])
def test_invalid_quote_repairs_only_evidence_without_reextracting(service,monkeypatch,model,mutate_meaning):
    source=prepare(service,file_ids=['current:0']); original=a2.model_call
    async def repair(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]); value=json.loads(result['text'])
        if stage=='relation':
            value['relations'][0]['source_quotes']=[dict(evidence_id=data['blocks'][0]['ref'],quote='제공되지 않은 구절')]
        if stage=='revision':
            target=data['targets'][0]
            assert data['evidence_only_ids']==[target['id']]
            row={k:v for k,v in target.items() if k in Relation.model_fields}
            row.update(candidate_ref=target['id'],local_ref='r1',reason='같은 의미의 실제 제공 원문 구간으로 보완',
                evidence_ids=[],source_quotes=[],source_refs=[data['blocks'][0]['source_ref']])
            if mutate_meaning: row['predicate']='다른 의무로 변경'
            value=dict(observations=[],relations=[row],hierarchies=[],deferred=[])
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',repair)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert model.count('relation')==1 and model.count('revision')==1,run.get('error')
    original_relation=run['result']['original_relations'][0]
    assert original_relation['validation'] and original_relation['evidence_validation']
    recovery=next(r for r in run['result']['recovery_requests'] if r['cause']=='evidence_error')
    assert recovery['status']==('unresolved' if mutate_meaning else 'proposals_created'),run['result']['failures']
    if not mutate_meaning:
        revised=run['result']['relations'][0]
        assert revised['id']==original_relation['id'] and revised['predicate']==original_relation['predicate']
        assert not revised['validation'] and not revised['evidence_validation']
        assert revised['evidence_refs'][0]['quote']==a2.load_blocks(service,run)[0]['text']
    before=deepcopy(run['analysis_units']); calls=list(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model==calls and again['analysis_units']==before


@pytest.mark.parametrize('outcome', ['new','repeat','failure','budget'])
def test_same_span_keeps_all_meanings_and_bounds_attempts(service,monkeypatch,model,outcome):
    source=prepare(service,file_ids=['current:0']); original=a2.model_call
    async def missing(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='critic':
            b=data['blocks'][0]
            value['missing_meanings']=[dict(role='concept',meaning=m,evidence_ids=[],source_refs=[b['source_ref']],cq_ids=['cq1'])
                for m in ['서로 다른 첫째 누락','서로 다른 둘째 누락']]
            value['needs_revision']=True
        if data.get('recovery_meanings'):
            assert len(data['recovery_meanings'])==2 and stage=='concept'
            if outcome=='new': value['observations'][0]['definition']='새로 확인한 의미 제안'
            if outcome=='repeat': value['observations'][0]['definition']='선택  원문의   임대 유형'
            if outcome=='failure': result['done_reason']='length'
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',missing)
    budgets=dict(additional_rounds=2,model_calls=5 if outcome=='budget' else 48)
    run=done(service,service.start(request(source['id'],discovery_budgets=budgets))['run_id'])
    recoveries=[r for r in run['result']['recovery_requests'] if r['cause']=='extraction_missing']
    assert len(recoveries)==1 and len(recoveries[0]['meanings'])==2
    recovery=recoveries[0]
    assert recovery['status']==('proposals_created' if outcome=='new' else 'budget_exhausted' if outcome=='budget' else 'unresolved')
    assert model.count('relation')==1 and model.count('concept')==(1 if outcome=='budget' else 2)
    assert recovery in run['result']['unresolved_recovery_requests'] and recovery['semantic_status']=='unverified'
    assert run['metrics']['recovery_calls']==(3 if outcome=='new' else 0 if outcome=='budget' else 1)
    before=deepcopy(run['analysis_units']);calls=list(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model==calls and again['analysis_units']==before
    assert again['result']['recovery_requests']==run['result']['recovery_requests']


def test_rewording_preserves_extra_meaning_without_mutating_scheduled_input():
    b=dict(id='b',text='원문의 실제 두 조건',file_id='f',source_group='s')
    group=dict(id='g',block_ids=['b'])
    run=dict(frontier=[group],analysis_units=[],analysis_block_ids=['b'])
    need=dict(role='concept',meaning='첫 조건 누락',evidence_refs=[dict(block_id='b',span=[0,3])],validation=[])
    a2.queue_recovery(run,dict(missing_meanings=[need]),group,{'b':b})
    recovery=a2.recovery_groups(run,1,{'b':b})[0]; before=deepcopy(recovery)
    a2.queue_recovery(run,dict(missing_meanings=[dict(need,meaning='같은 범위를 다른 문구로 요청')]),group,{'b':b})
    assert len(run['recovery_requests'])==1 and len(run['recovery_requests'][0]['meanings'])==2
    assert recovery==before and not a2.recovery_groups(run,2,{'b':b})
    # Even a selected comparison block is not this group's primary extraction target.
    run['analysis_block_ids'].append('comparison')
    a2.queue_recovery(run,dict(missing_meanings=[dict(need,evidence_refs=[dict(block_id='comparison',span=[0,2])])]),
        dict(id='critic',analysis_group_ids=['g']),{'b':b})
    assert run['recovery_requests'][1]['validation']
    # A later request from the true owner can still use that source's one attempt.
    comparison=dict(id='comparison',text='비교',file_id='f',source_group='s')
    own=dict(id='owner',block_ids=['comparison']);run['frontier'].append(own)
    a2.queue_recovery(run,dict(missing_meanings=[dict(need,evidence_refs=[dict(block_id='comparison',span=[0,2])])]),own,{'comparison':comparison})
    assert not run['recovery_requests'][1]['validation']
    assert len(a2.recovery_groups(run,2,{'comparison':comparison}))==1


def test_successful_unit_hash_mismatch_never_overwrites_saved_unit(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    unit=next(u for u in run['analysis_units'] if u['stage']=='concept'); before=deepcopy(unit)
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    with pytest.raises(ValueError,match='입력 해시 변경'):
        a2.call(service,run,'concept',unit['group_id'],dict(blocks=[],changed='변경된 입력'),[],by_id)
    assert unit==before and len(model)==5


def test_comparison_search_never_becomes_new_extraction(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0'])
    survey=profile.survey;original=a2.model_call
    def primary_only(files,blocks):
        profiles,frontier,contexts=survey(files,blocks)
        return profiles,[g for g in frontier if g['file_id']=='current:0'],contexts
    monkeypatch.setattr(profile,'survey',primary_only)
    async def compare(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='critic':
            value=json.loads(result['text'])
            value['actions']=[dict(action='search',query='예외 조건',reason='비교용 조건 대조')]
            result['text']=json.dumps(value,ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',compare)
    run=done(service,service.start(request(source['id']))['run_id'])
    assert run['extra_requests'] and all(r['purpose']=='comparison' for r in run['extra_requests'])
    assert len(run['frontier'])==1 and model.count('concept')==model.count('relation')==1
    assert not run.get('error'),run.get('error')

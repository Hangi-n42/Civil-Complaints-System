"""Actual-group reservations and deterministic serial ordering; no model network."""
from copy import deepcopy
from itertools import count
import json

from app.knowledge import discovery_analysis as a2, discovery_profile as profile, discovery_synthesis as synthesis
from app.knowledge.schemas import RunRequest
from app.tests.unit.test_knowledge_discovery_analysis import corpus, service, model, prepare, done


def test_fourteen_groups_reserve_unbuilt_capacity_then_actual_split_reviews(service,model):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')]))['run_id'])
    built=deepcopy(next(u for u in run['analysis_units'] if u['stage']=='builder'))
    group=deepcopy(run['candidate_groups'][0])
    for field in ('review_unit_ids','design_candidates','design_candidate_ids'):
        group.pop(field,None)
    run['candidate_groups']=[dict(deepcopy(group),id=str(n)) for n in range(14)]
    run['analysis_units']=[u for u in run['analysis_units'] if u['stage'] in {'scout','concept','relation'}]
    for u in run['analysis_units']:u['attempts']=[dict(elapsed_s=20)]
    run.pop('role_time_estimates',None)
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks};contexts=profile.contexts(blocks)
    before=deepcopy(run)
    planned=a2.review_reservation(run,0,by_id,contexts,set(by_id))
    reserved=synthesis.pending_review_units(run,run['candidate_groups'][0],by_id,contexts)
    assert all(':reserved:' in uid for uid in reserved)
    assert planned['model_calls']==14*(1+len(reserved)) and planned['model_calls']>24
    assert run['analysis_units']==before['analysis_units'] and run['candidate_groups']==before['candidate_groups']
    assert a2.review_reservation(run,0,by_id,contexts,set(by_id))==planned
    assert run['role_time_estimates']['concept']['estimate_s']==25
    assert run['role_time_estimates']['critic']['basis'].startswith('미관측')
    concept=next(u for u in run['analysis_units'] if u['stage']=='concept')
    concept['attempts'].append(dict(elapsed_s=40))
    a2.review_reservation(run,0,by_id,contexts,set(by_id))
    assert run['role_time_estimates']['concept']['estimate_s']==50
    built.update(id='builder:0',group_id='0');run['analysis_units'].append(built)
    run['candidate_groups'][0].update(design_candidates=built['output'].get('observations',[])+built['output'].get('modeled_relations',[]),design_candidate_ids=[])
    context,deps,supplied=synthesis.review_context(run,run['candidate_groups'][0],built['output'],by_id,contexts)
    batches=synthesis.review_batches(context,deps,supplied,by_id,contexts)
    actual=synthesis.pending_review_units(run,run['candidate_groups'][0],by_id,contexts)
    assert actual==['critic:0:'+b['key'] for b in batches]
    assert {'proposition','binding'} <= {b['context'].get('review_component') for b in batches}
    assert a2.review_reservation(run,0,by_id,contexts,set(by_id))['model_calls']==13*(1+len(reserved))+len(actual)


def test_round_robin_keeps_priority_and_saved_order():
    groups=[dict(id='a'+str(n),anchor='C1',priority=1,requested_by_scout=True) for n in range(3)]
    groups += [dict(id='b',anchor='C2',priority=1),dict(id='later',anchor='C2',priority=2)]
    run={}
    assert [g['id'] for g in a2.ordered_groups(run,groups,'analysis:0')]==['a0','b','a1','a2','later']
    assert [g['id'] for g in a2.ordered_groups(run,list(reversed(groups)),'analysis:0')]==['a0','b','a1','a2','later']


def test_twenty_four_calls_switch_to_review_after_both_cqs_get_analysis(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0']);survey=profile.survey;original=a2.model_call
    def many(files,blocks):
        profiles,frontier,contexts=survey(files,blocks)
        current=next(g for g in frontier if g['file_id']=='current:0')
        web=next(g for g in frontier if g['file_id']=='web:0')
        groups=[dict(current,id='first_'+str(n),anchor='C1',priority=1,requested_by_scout=True,reason='선택 C1 '+str(n)) for n in range(9)]
        groups.append(dict(web,id='second',anchor='C2',priority=1,reason='선택 C2'))
        return profiles,groups,contexts
    async def scoped(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]);value=json.loads(result['text'])
        if stage in {'concept','relation'}:
            for row in value.get('observations',[])+value.get('relations',[]):
                row['cq_ids']=['C2' if data['selection_reason']=='선택 C2' else 'C1']
                if 'definition' in row: row['definition']+=' '+data['selection_reason']
        if stage=='critic': value['needs_revision']=True
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(profile,'survey',many);monkeypatch.setattr(a2,'model_call',scoped)
    request=RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id=i,question=i+' 유형과 조건') for i in ('C1','C2')],
        discovery_budgets=dict(model_calls=24,additional_rounds=0))
    run=done(service,service.start(request)['run_id'])
    assert not run.get('error'),run.get('error')
    assert run['execution_order']['analysis:0'][:2]==['first_0','second']
    assert any(g.get('budget_allocation',{}).get('decision')=='review_existing' for g in run['frontier'])
    assert len([u for u in run['analysis_units'] if u['stage']=='concept'])<10
    assert {i for c in run['result']['observations'] for i in c['cq_ids']}=={'C1','C2'}
    review_groups={g['id']:g for g in run['candidate_groups']}
    anchors=[review_groups[i]['anchor'] for i in run['execution_order']['review:0']]
    assert anchors[:2]==['cq:C1','cq:C2']
    if 'revision' in model: assert model.index('revision')>max(i for i,s in enumerate(model) if s=='critic')
    successful={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'}
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert again['execution_order']==run['execution_order']
    assert all(u==successful[u['id']] for u in again['analysis_units'] if u['id'] in successful)
    assert again['metrics']['llm_calls']<=24


def test_later_round_failed_critic_is_reachable_on_resume(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call;failed=False
    async def interrupt_review(prompt,schema,stage,run,timeout):
        nonlocal failed
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('INPUT:\n')[1]);value=json.loads(result['text'])
        if stage=='concept' and data.get('recovery_meanings'):
            value['observations'][0]['definition']='추가 구간 의미'
        if stage=='critic':
            running=next(u for u in run['analysis_units'] if u['status']=='running')
            group=next(g for g in run['candidate_groups'] if running['id'] in synthesis.review_ids(g))
            if group['round']==0:
                value['missing_meanings']=[dict(role='concept',meaning='아직 기록되지 않은 의미',cq_ids=['cq1'],
                    source_refs=[data['blocks'][0]['source_ref']],comparison_reason='기존 유형과 관계에 없는 추가 의미',
                    compared_candidate_ids=[c['id'] for f in ('unapproved_observations','unapproved_relations','comparison_terms') for c in data.get(f,[])])]
            elif not failed:
                result['done_reason']='length';failed=True
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',interrupt_review)
    request=RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')],discovery_budgets=dict(additional_rounds=1))
    run=done(service,service.start(request)['run_id'])
    assert failed
    critic=next(u for u in run['analysis_units'] if u['stage']=='critic' and u['status']=='failed')
    before={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'};calls=len(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model[calls:]==['critic']
    assert next(u for u in again['analysis_units'] if u['id']==critic['id'])['status']=='succeeded'
    assert all(u==before[u['id']] for u in again['analysis_units'] if u['id'] in before)


def test_review_measurements_release_same_round_analysis_reservation(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0']);survey=profile.survey
    def order(files,blocks):
        profiles,frontier,contexts=survey(files,blocks)
        return profiles,[dict(g,anchor='C2' if n==0 else 'C1') for n,g in enumerate(frontier)],contexts
    monkeypatch.setattr(profile,'survey',order)
    # Deterministic elapsed time only; the model double still performs no network or sleep.
    monkeypatch.setattr(a2,'monotonic',count(0,20).__next__)
    request=RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')],
        discovery_budgets=dict(model_calls=24,model_seconds=1500,additional_rounds=0,revisions=0))
    run=done(service,service.start(request)['run_id'])
    assert not run.get('error'),run.get('error')
    first=run['initial_review_group_id']
    group=next(g for g in run['frontier'] if g['id']==first)
    assert group['budget_allocation']['decision']=='analyze_then_review'
    assert group['budget_allocation']['reserved_estimated_s']>group['budget_allocation']['remaining_model_s']
    units=run['analysis_units'];next_analysis=next(n for n,u in enumerate(units) if u['stage']=='concept' and u['group_id']!=first)
    own=[g for g in run['candidate_groups'] if first in g['analysis_group_ids']]
    required={uid for g in own for uid in synthesis.review_ids(g)}
    assert required and required <= {u['id'] for u in units[:next_analysis] if u['status']=='succeeded'}
    assert any(':binding:' in uid for uid in required)
    assert run['role_time_estimates']['builder']['initial_s']==360
    assert run['role_time_estimates']['builder']['estimate_s']==25
    assert not run['result']['mandatory_pending']
    assert run['metrics']['model_total_s']==20*len(model)<1500 and run['metrics']['llm_calls']<=24
    before=deepcopy(run['analysis_units']);calls=len(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(model)==calls and again['analysis_units']==before


def test_initial_review_failure_blocks_next_extraction_and_resume_reuses_success(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0']);original=a2.model_call;failed=False
    monkeypatch.setattr(a2,'monotonic',count(0,20).__next__)
    async def fail_binding(prompt,schema,stage,run,timeout):
        nonlocal failed
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='binding' and not failed:
            result['done_reason']='length';failed=True
        return result
    monkeypatch.setattr(a2,'model_call',fail_binding)
    run=done(service,service.start(RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')],
        discovery_budgets=dict(model_calls=24,model_seconds=1500,additional_rounds=0,revisions=0)))['run_id'])
    assert failed and run['status']=='partial'
    first=run['initial_review_group_id']
    assert {u['group_id'] for u in run['analysis_units'] if u['stage'] in {'concept','relation'}}=={first}
    assert any(':binding:' in u['id'] and u['status']=='failed' for u in run['analysis_units'])
    before={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'};calls=len(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model[calls]=='binding' and all(u==before[u['id']] for u in again['analysis_units'] if u['id'] in before)
    assert any(u['stage']=='concept' and u['group_id']!=first for u in again['analysis_units'])
    assert again['metrics']['llm_calls']<=24 and not again['result']['mandatory_pending']


def test_initial_entry_still_stops_at_actual_time_limit(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0'])
    monkeypatch.setattr(a2,'monotonic',count(0,250).__next__)
    run=done(service,service.start(RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')],
        discovery_budgets=dict(model_calls=24,model_seconds=1500,additional_rounds=0,revisions=0)))['run_id'])
    assert run['initial_review_group_id'] and run['status']=='partial'
    assert run['metrics']['model_total_s']==1500 and run['metrics']['llm_calls']==len(model)==6
    assert len([u for u in run['analysis_units'] if u['stage']=='concept'])==1
    assert run['result']['mandatory_pending'] and any('예산 종료' in f['error'] for f in run['result']['failures'])


def test_initial_entry_does_not_override_call_or_extraction_time_shortage(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0'])
    monkeypatch.setattr(a2,'monotonic',count(0,20).__next__)
    for budgets in (dict(model_calls=5,model_seconds=1500),dict(model_calls=24,model_seconds=700)):
        run=done(service,service.start(RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
            cqs=[dict(id='cq1',question='유형과 조건')],discovery_budgets=dict(budgets,additional_rounds=0,revisions=0)))['run_id'])
        assert 'initial_review_group_id' not in run
        assert [u['stage'] for u in run['analysis_units']]==['scout']
        assert run['status']=='partial'


def test_initial_extraction_failure_and_cancel_resume_same_group(service,monkeypatch,model):
    source=prepare(service,file_ids=['current:0','web:0']);original=a2.model_call;interrupted=False
    monkeypatch.setattr(a2,'monotonic',count(0,100).__next__)
    async def interrupt_concept(prompt,schema,stage,run,timeout):
        nonlocal interrupted
        result=await original(prompt,schema,stage,run,timeout)
        if stage=='concept' and not interrupted:
            interrupted=True;result['done_reason']='length';service.cancel(run['id'])
        return result
    monkeypatch.setattr(a2,'model_call',interrupt_concept)
    run=done(service,service.start(RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=source['id'],
        cqs=[dict(id='cq1',question='유형과 조건')],
        discovery_budgets=dict(model_calls=24,model_seconds=1500,additional_rounds=0,revisions=0)))['run_id'])
    assert interrupted and run['status']=='cancelled' and run['initial_review_group_id']
    before={u['id']:deepcopy(u) for u in run['analysis_units'] if u['status']=='succeeded'};calls=len(model)
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert model[calls:calls+2]==['concept','relation']
    assert all(u==before[u['id']] for u in again['analysis_units'] if u['id'] in before)
    assert again['initial_review_group_id']==run['initial_review_group_id']
    assert again['metrics']['model_total_s']<=1500 and again['metrics']['llm_calls']<=24

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
    assert pending[0]['assessment_scope']['extent']=='provided_only'
    assert not pending[0]['assessment_scope']['whole_input_assessed']
    assert run['metrics']['recovery_calls']==0 and run['metrics']['recovery_remaining_by_cause'][cause]==1
    before=deepcopy(run['analysis_units'])
    again=done(service,service.start(RunRequest(kind='discovery',retry_of_run_id=run['id']))['run_id'])
    assert len(model)==5 and again['analysis_units']==before
    assert again['result']['original_relations']==run['result']['original_relations']
    if cause=='endpoint':
        from app.knowledge import ontology_changes
        cid=ontology_changes.publish(service,run['id'])['changeset_id']
        with service.repository.connect() as db: rows=service.repository.get(db,'changesets',cid)['candidates']
        relation=next(c for c in rows if c['target_kind']=='relation')
        assert relation['origin']['relation_checks'][0]['judgment']=='supported'
        assert relation['review_status']=='deferred'


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
            value['missing_meanings']=[dict(role='concept',meaning=m,evidence_ids=[],source_refs=[b['source_ref']],cq_ids=['cq1'],
                compared_candidate_ids=[c['id'] for field in ('unapproved_observations','unapproved_relations','reviewed_base','comparison_terms') for c in data.get(field,[])],
                comparison_reason='기존 관측과 관계의 조건과 다른 누락 의미')
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


def test_recovery_span_selection_keeps_shared_context_endpoints_and_single_candidates():
    from app.knowledge import discovery_segments as segments, discovery_synthesis as synthesis
    text='공유 전제\n첫 구간의 관계\n독립된 둘째 구간\n다만 공통 예외'
    start=text.index('첫'); end=text.index('독립'); exception=text.index('다만')
    def block(identifier, value):
        return dict(id=identifier,text=value,file_id='f',source_group='s',title='문서',role='current',locator={'format':'txt'})
    by_id={b['id']:b for b in [block('b',text),block('type','직접 끝점의 유형 정의'),block('header','표 헤더')]}
    contexts={i:dict(block_ids=[i]) for i in by_id}
    view=dict(block_id='b',span=[start,end],shared_spans=[[0,start],[exception,len(text)]],recipe=segments.VERSION)
    owner=dict(id='g',block_ids=['b'],segments=[view],context_block_ids=['header'])
    def candidate(identifier, bid, span, **fields):
        return dict(id=identifier,evidence_ids=[bid],evidence_refs=[dict(block_id=bid,evidence_id=bid,span=span)],**fields)
    inside=candidate('inside','b',[start,end],classification='type',label='첫 구간')
    outside=candidate('outside','b',[end,exception],classification='type',label='둘째 구간')
    endpoint=candidate('endpoint','type',[0,len(by_id['type']['text'])],classification='type',label='직접 유형')
    legacy=dict(id='legacy',evidence_ids=['b'],evidence_refs=[dict(block_id='b')],classification='type')
    reviewed=dict(id='base',kind='concept',name='승인 유형',evidence=[dict(evidence_id='type')])
    relation=candidate('relation','b',[start,end],negation='affirmed',subject='base',object='endpoint')
    units=[dict(status='succeeded',output=dict(observations=[inside,outside,endpoint,legacy],relations=[relation]))]
    run=dict(frontier=[owner],analysis_units=units,recipe=a2.recipe({}),cqs=[],scope_items=[],base_candidates=[reviewed])
    before=deepcopy(units)
    need=dict(role='relation',meaning='첫 구간 누락 관계',evidence_refs=[dict(block_id='b',span=[start,start+2])],validation=[])
    a2.queue_recovery(run,dict(missing_meanings=[need]),owner,by_id)
    group=a2.recovery_groups(run,1,by_id)[0]
    assert {c['id'] for c in group['previous_observations']}=={'inside','endpoint','base'}
    assert set(group['required_endpoint_ids'])=={'endpoint','base'}
    assert [c['id'] for c in group['previous_relations']]==['relation']
    assert {c['candidate_id'] for c in group['omitted_recovery_candidates']}=={'outside','legacy'}
    assert 'legacy span' in group['omitted_recovery_candidates'][1]['reason']
    raw=segments.packet(group,by_id,contexts,a2.packet)
    required,_,_=synthesis.context_for([endpoint],by_id,contexts)
    context=dict(blocks=raw,tool_originals=raw+required['blocks'],reviewed_base=[reviewed],previous_observations=group['previous_observations'],
        unapproved_observations=group['previous_observations'],previous_relations=[relation],previous_candidate_ids=['inside','endpoint','relation'])
    supplied={c['id']:c for c in [inside,endpoint,relation,reviewed]}
    context,deps,supplied=a2.analysis_context(run,'relation',context,supplied,group)
    values=[c['id'] for f in ('previous_observations','unapproved_observations','previous_relations') for c in context[f]]
    assert sorted(values)==['endpoint','inside','relation']
    originals=segments.originals(context)
    assert len(originals)==len({(b['ref'],tuple(b.get('span', [])),b['text']) for b in originals})
    assert {b['text'] for b in originals}=={text[start:end],text[:start],text[exception:],'직접 끝점의 유형 정의','표 헤더'}
    assert units==before and not a2.recovery_groups(run,2,by_id)
    # Optional comparison is removed before the mandatory endpoint definition and its source.
    run['recipe']['input_chars']=1
    context,_,supplied=a2.analysis_context(run,'relation',context,supplied,group)
    assert {c['id'] for c in context['unapproved_observations']}=={'endpoint'}
    assert context['reviewed_base']==[reviewed]
    assert any(b['ref']=='type' for b in context['tool_originals'])
    assert '필수 원문' in group['input_allocation']['relation']['pending_reason']

    # Concept's explicit comparison stays required; relation endpoint types are optional context.
    concept_run=dict(run,recovery_requests=[],recipe=a2.recipe({}))
    a2.queue_recovery(concept_run,dict(missing_meanings=[dict(need,role='concept',compared_candidate_ids=['inside'])]),owner,by_id)
    concept_group=a2.recovery_groups(concept_run,1,by_id)[0]
    assert not concept_group['required_endpoint_ids'] and concept_group['required_comparison_ids']==['inside']
    assert {'inside','endpoint','base'}=={c['id'] for c in concept_group['previous_observations']}
    concept_context=dict(blocks=raw,tool_originals=required['blocks'],reviewed_base=[reviewed],
        previous_observations=concept_group['previous_observations'],previous_relations=concept_group['previous_relations'],
        recovery_meaning=concept_group['recovery_meaning'],recovery_meanings=concept_group['recovery_meanings'])
    stored=deepcopy(concept_context)
    _,prompt=a2.make_prompt(concept_run,'concept',concept_context,list(by_id),supplied)
    payload=json.loads(prompt.split('\nINPUT:\n')[1])
    assert 'recovery_meaning' not in payload and payload['recovery_meanings'] and concept_context==stored
    concept_run['recipe']['input_chars']=1
    reduced,_,_=a2.analysis_context(concept_run,'concept',concept_context,supplied,concept_group,reserve=2000)
    assert [c['id'] for c in reduced['previous_observations']]==['inside']
    assert not reduced['previous_relations'] and not reduced['reviewed_base']
    assert {'endpoint','base'}<=set(concept_group['omitted_comparison_ids'])
    assert reduced['blocks']==raw and units==before

    modeled=dict(relation,subject='inside',statement_type='design_proposal',source_relation=deepcopy(relation))
    critic_group=dict(id='cg',analysis_group_ids=['g'],candidates=[relation],design_candidates=[modeled])
    compared_run=dict(run,recovery_requests=[],candidate_groups=[critic_group],recipe=a2.recipe({}))
    a2.queue_recovery(compared_run,dict(missing_meanings=[dict(need,role='concept',compared_candidate_ids=['relation'])]),critic_group,by_id)
    compared_group=a2.recovery_groups(compared_run,1,by_id)[0]
    assert compared_group['required_comparison_ids']==['relation']
    assert compared_group['previous_relations']==[modeled]
    assert compared_group['previous_relations'][0]['source_relation']==relation and units==before
    assert 'relation' not in {c['candidate_id'] for c in compared_group['omitted_recovery_candidates']}


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


def test_target_response_recovery_keeps_only_missing_clause_as_focus():
    text='조문 ① 첫 원칙. ② 잔여 조건. ③ 각 호의 권한. 1. LH. 2. 지방공사.'
    b=dict(id='b',text=text,file_id='f',source_group='s')
    span=[text.index('②'),text.index('③')]
    group=dict(id='g',block_ids=['b'])
    run=dict(frontier=[group],analysis_units=[],analysis_block_ids=['b'])
    need=dict(role='relation',meaning='② 무응답',trigger='target_response',
              evidence_refs=[dict(block_id='b',span=span)],validation=[])
    a2.queue_recovery(run,dict(missing_meanings=[need]),group,{'b':b})
    recovery=a2.recovery_groups(run,1,{'b':b})[0]
    raw=a2.segments.packet(recovery,{'b':b},{},lambda *args:[dict(ref='b',text=text)])
    assert [v['span'] for v in raw if not v['context_only']]==[span]
    assert sum(v.get('analysis_target',False) for v in raw)==1
    assert ''.join(v['text'] for v in sorted(raw,key=lambda v:v['span']))==text
    assert all(v['context_only'] for v in raw if '①' in v['text'] or '③' in v['text'])

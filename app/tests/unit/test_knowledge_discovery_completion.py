"""Recovery boundary checks; saved-response replay and live quality are separate."""
from copy import deepcopy

import pytest

from app.knowledge import discovery_analysis as a2
from app.tests.unit.test_knowledge_discovery_claims import authored
from app.tests.unit.test_knowledge_discovery_scope import requirement_fixture
from app.tests.unit.test_knowledge_discovery_run import corpus, service


@pytest.mark.parametrize('mode',['valid','no_companion','different_endpoints','different_meaning','different_defer',
    'different_group','invalid_request','failed_builder','old_after','different_source','different_before','withdrawn',
    'changed_type','unknown','refuted','no_history','current_raw','other_cause','other_role','owner_scope','before_endpoints'])
def test_endpoint_review_resolution_requires_same_repair_source_and_current_dependencies(mode):
    from app.knowledge import discovery_recovery as recovery, discovery_review as reviews
    refs=[dict(block_id='e',source_version_id='v',parse_run_id='p',span=[0,5],quote='actor')]
    before=dict(id='r',subject='actor',predicate='may',object='target',negation='affirmed',statement_type='rule',
        conditions='condition',evidence_refs=refs,unresolved_endpoints=['subject','object'])
    after=dict(before,subject='t1',object='t2',statement_type='design_proposal',source_relation=deepcopy(before),unresolved_endpoints=[])
    current=dict(r=after,t1=dict(id='t1',classification='type',definition='actor'),t2=dict(id='t2',classification='type',definition='target'))
    check=dict(candidate_ref='r',judgment='supported',binding_checks=dict(subject='supported',object='supported'))
    review=dict(unit_id='proposition',component_unit_ids=['proposition','binding'],relation_checks=[check],
        review_coverage=dict(valid_candidate_ids=['r'],candidate_hashes={'r':reviews.fingerprint(after)}),
        review_dependency_contract='selected-types-v1',binding_dependency_hashes={'r':reviews.binding_fingerprints(after,current)},role_source_hashes={'r':{}})
    need=dict(meaning='unbound endpoints',target_ref='',defer_reason='')
    request=dict(need,id='review-request',role='review',cause='endpoint',candidate_ref='r',critic_group_id='g',
        target=dict(candidate_id='r',endpoints=['subject','object']),meanings=[dict(need,assessment_scope={'split':'first'})],
        validation=[],status='manual_review',semantic_status='unverified',proposal_review_status='unverified',proposal_ids=[])
    companion=deepcopy(request);companion.update(id='builder-request',role='builder',unit_id='builder',
        semantic_status='supported',proposal_review_status='current_critic_supported',proposal_ids=['r'])
    companion['meanings'][0]['assessment_scope']={'split':'second'}
    unit=dict(id='builder',stage='builder',status='succeeded',parent_group_id='g',dependency_ids=['e'],
        output=dict(history=[dict(candidate_id='r',before=deepcopy(before),after=deepcopy(after))]))
    run=dict(recipe={},recovery_requests=[request,companion],candidate_groups=[dict(id='g',candidates=[deepcopy(before)])],
        analysis_units=[unit,*[dict(id=i,status='succeeded',dependency_ids=['e']) for i in ('proposition','binding')]])
    available={'e'}
    if mode=='no_companion':run['recovery_requests'].remove(companion)
    if mode=='different_endpoints':companion['target']['endpoints']=['subject']
    if mode=='different_meaning':companion['meanings'][0]['meaning']='different meaning'
    if mode=='different_defer':companion['defer_reason']='needs human scope choice'
    if mode=='different_group':unit['parent_group_id']='other'
    if mode=='invalid_request':request['validation']=['outside scope']
    if mode=='failed_builder':unit['status']='failed'
    if mode=='old_after':unit['output']['history'][0]['after']['conditions']='old'
    if mode=='different_source':run['candidate_groups'][0]['candidates'][0]['evidence_refs'][0]['source_version_id']='other-version'
    if mode=='different_before':unit['output']['history'][0]['before']['conditions']='other-condition'
    if mode=='owner_scope':run['candidate_groups'][0]['candidates'][0]['cq_ids']=['different-cq']
    if mode=='before_endpoints':
        unit['output']['history'][0]['before']['unresolved_endpoints']=[]
        run['candidate_groups'][0]['candidates'][0]['unresolved_endpoints']=[]
    if mode=='withdrawn':available=set()
    if mode=='changed_type':current['t1']['definition']='other actor'
    if mode in {'unknown','refuted'}:check['binding_checks']['subject']=mode
    if mode=='no_history':unit['output']['history']=[]
    if mode=='current_raw':current['r']=deepcopy(before)
    if mode=='other_cause':request['cause']='content_error'
    if mode=='other_role':request['role']='relation'
    original=deepcopy(request)
    recovery.resolve_endpoint_reviews(run,current,{'r':review},available)
    assert (request['semantic_status']=='supported')==(mode=='valid')
    assert {k:v for k,v in request.items() if k not in {'semantic_status','proposal_review_status','current_resolution'}}=={
        k:v for k,v in original.items() if k not in {'semantic_status','proposal_review_status','current_resolution'}}
    if mode=='valid':
        assert request['current_resolution']['companion_request_id']=='builder-request'
        assert request['current_resolution']['builder_unit_id']=='builder'
        assert request['current_resolution']['review_unit_ids']==['proposition','binding']


@pytest.mark.parametrize('mode,expected',[
    ('modeled',True),('raw',True),('refuted',False),('unknown',False),('pending',False),
    ('stale',False),('no_preservation',False),('wrong_basis',False),('never_modeled',False),
    ('binding_unknown',False),('binding_supported',False),('changed_dependency',False)])
def test_binding_after_revision_requires_current_complete_source_review(mode,expected):
    from app.knowledge import discovery_synthesis as syn, discovery_review as reviews
    types={i:dict(id=i,classification='type',definition=i) for i in ('t1','t2')}
    before=dict(id='r',subject='t1',object='t2',negation='affirmed',source_relation=dict(subject='actor',object='target'))
    after=dict(before,revision_basis_hash='basis')
    if mode in {'raw','never_modeled'}:
        after=dict(id='r',subject='actor corrected',object='target',negation='affirmed',endpoint_mode='source_text',revision_basis_hash='basis')
    if mode=='never_modeled': before.pop('source_relation')
    record=dict(candidate_id='r',before=before,after=deepcopy(after))
    candidates=dict(types,r=after)
    check=dict(candidate_ref='r',judgment='supported',correction_complete=True,preservation_basis_hash='basis',binding_checks=dict(subject='refuted',object='supported'))
    review=dict(relation_checks=[check],review_coverage=dict(valid_candidate_ids=['r'],candidate_hashes={'r':reviews.fingerprint(after)}),
        review_dependency_contract='selected-types-v1',binding_dependency_hashes={'r':reviews.binding_fingerprints(after,candidates)},
        role_source_hashes={'r':{}})
    if mode in {'refuted','unknown'}: check['judgment']=mode
    if mode=='pending': review['review_coverage']['valid_candidate_ids']=[]
    if mode=='stale': after['subject']='changed'
    if mode=='no_preservation': check.pop('correction_complete')
    if mode=='wrong_basis': check['preservation_basis_hash']='older'
    if mode=='changed_dependency': types['t1']['definition']='changed'
    if mode.startswith('binding_'): check['binding_checks']['subject']=mode.removeprefix('binding_')
    assert syn.binding_after_revision(review,record,candidates) is expected


def test_modeled_relation_preservation_uses_only_supported_natural_fields_without_rewriting_history():
    from app.knowledge import discovery_scope as scope
    source=dict(subject='source actor',predicate='may select',object='source target',conditions='actual condition',
        statement_type='rule',negation='affirmed')
    before=dict(source,id='r',subject='type_actor',object='type_target',statement_type='design_proposal',source_relation=source)
    snapshot=deepcopy(before)
    check=dict(semantic_checks=dict(subject='refuted',object='supported',conditions='unknown',statement_type='supported'),evidence_refs=[dict(block_id='e')])
    basis=scope.preservation_basis(before,[check])
    assert [(m['applies_to'],m['meaning']) for m in basis]==[('object','source target'),('statement_type','rule')]
    assert all(m['evidence_refs']==check['evidence_refs'] for m in basis)
    assert before==snapshot  # IDs, raw source and original modeled record are untouched.
    old=[dict(meaning_key='old',meaning='type_target',applies_to='object',evidence_refs=[])]
    context=dict(preservation_basis=deepcopy(old),required_context=[],binding_checks=[check])
    record=scope.revision_record(before,deepcopy(before),'saved basis',context)
    assert record['before']==snapshot and record['preservation_basis']==old and context['preservation_basis']==old


def test_critic_capacity_matches_http_and_input_reservation_with_legacy_fallback(monkeypatch):
    import asyncio
    from app.knowledge import discovery_synthesis as synthesis
    recipe=a2.recipe({});run=dict(id='capacity',recipe=recipe,cqs=[],scope_items=[],frontier=[],analysis_units=[])
    sent=[]
    async def capture(self,prompt,**kwargs):
        sent.append(kwargs);return {}
    monkeypatch.setattr(a2.GenerationService,'call_ollama',capture)
    for stage,expected in [('critic',8192),('binding',8192),('concept',4096),('context',4096),('requirements',8192)]:
        asyncio.run(a2.model_call('input',{},stage,run,720))
        assert sent[-1]['num_predict']==expected and sent[-1]['timeout']==720
        context={'target':{'label':'target','cq_ids':[],'scope_item_ids':[]}} if stage=='context' else {'review_component':'binding','review_target_ids':['c']} if stage=='binding' else {}
        size=synthesis.input_size(run,'critic' if stage=='binding' else stage,context,[],{'c':dict(id='c')} if stage=='binding' else {})
        assert size['input_bytes_limit']==recipe['num_ctx']-expected
    legacy=deepcopy(recipe);legacy.pop('critic_num_predict')
    assert a2.output_tokens(legacy,'critic')==4096
    legacy.pop('requirements_num_predict')
    assert a2.output_tokens(legacy,'requirements')==4096
    # The earlier fit must reserve the same larger output as the eventual call.
    monkeypatch.setattr(a2,'make_prompt',lambda *_: ({},'x'*(recipe['num_ctx']-8192+1)))
    run['recipe']['input_chars']=recipe['num_ctx']
    assert not synthesis.fits(run,'critic',{},[],{})


@pytest.mark.parametrize('endpoint',['subject','object'])
def test_role_applicability_separates_endpoint_scope_from_whole_requirement(endpoint):
    import json
    run=dict(id='scope',recipe=a2.recipe({}),cqs=[dict(id='q',question='주체 A/B 각각의 조건과 대상')],scope_items=[])
    role=dict(subject='A',predicate='정한다',object='기준',conditions='A 조건',time='기간')
    context=dict(context_phase='applicability',target=dict(label='기준',cq_ids=['q'],scope_item_ids=[],
        scope_kind='candidate',source_role=role,role_endpoint=endpoint),blocks=[],proposals=[])
    before=deepcopy(context)
    def payload(value):
        return json.loads(a2.make_prompt(run,'context',value,[],{})[1].split('\nINPUT:\n')[1])['target']
    target=payload(context)
    assert 'requirement_scope' not in target and run['cqs'][0]['question'] not in str(target)
    assert target['source_role']==role and target['role_endpoint']==endpoint and context==before
    requirement=deepcopy(context);requirement['target']['scope_kind']='requirement'
    assert payload(requirement)['scope']==run['cqs'][0]['question'] and 'requirement_scope' not in payload(requirement)
    discovery=deepcopy(context);discovery.pop('context_phase')
    assert payload(discovery)['scope']==run['cqs'][0]['question'] and 'requirement_scope' not in payload(discovery)
    plain=deepcopy(context);plain['target'].pop('source_role');plain['target'].pop('role_endpoint')
    assert payload(plain)['scope']==run['cqs'][0]['question']


@pytest.mark.parametrize('mode',['role','added_effect','plain_target','missing_role','invalid_role','mixed_targets','legacy_claims','legacy_scope'])
def test_local_role_review_uses_primary_mode_and_keeps_assertions_and_locations(mode):
    import json
    run=dict(id='local',recipe=a2.recipe({}),cqs=[dict(id='q',question='다른 절차는 제외하는 전체 요구')],scope_items=[])
    source=dict(id='r',subject='담당자',predicate='선정한다',object='대상',conditions='조건 A에도 불구하고 조건 B')
    role=dict(id='c',classification='type',definition_mode='source_role',definition='이 출처 명제의 담당자 역할',
        role_basis=dict(relation_ref='r',endpoint='subject'),role_source=source,cq_ids=['q'])
    plain=dict(id='p',classification='type',definition_mode='synthesis',definition='일반 유형')
    supplied={'c':role,'p':plain,'r':dict(source,subject='c',object='p',source_relation=deepcopy(source))}
    target=['c']
    if mode=='added_effect':role['definition']+=' 이 역할만으로 자격을 부여한다.'
    if mode=='plain_target':target=['p']
    if mode=='missing_role':role.pop('role_source')
    if mode=='invalid_role':role['validation']=['invalid']
    if mode=='mixed_targets':target=['c','p']
    if mode=='legacy_claims':run['recipe'].pop('claim_review_contract')
    if mode=='legacy_scope':run['recipe'].pop('context_contract')
    context=dict(review_focus='observations',review_target_ids=target,blocks=[],
        unapproved_observations=[supplied[i] for i in target],comparison_terms=[c for i,c in supplied.items() if i not in target],
        source_requirements={'c':[dict(meaning='실제 한정',meaning_key='m')]},revision_comparisons={})
    before=deepcopy((context,supplied))
    _,prompt=a2.make_prompt(run,'critic',context,[],supplied)
    wire=json.loads(prompt.split('\nINPUT:\n')[1]);local=mode in {'role','added_effect'}
    assert (a2.models.SOURCE_ROLE_REVIEW_RULE in prompt)==local
    assert wire['cqs']==([] if local or mode=='plain_target' else run['cqs'])
    assert wire['source_requirements']==context['source_requirements']
    if local:
        assert wire['unapproved_observations'][0]['definition']==role['definition']
        assert wire['unapproved_observations'][0]['role_source']==source
        assert wire['unapproved_observations'][0]['role_basis']==role['role_basis']
        assert next(c for c in wire['comparison_terms'] if c['id']=='r')['conditions']==source['conditions']
        assert a2.models.CLAIM_REVIEW_RULE not in prompt and a2.models.SCOPE_RULE not in prompt
        assert '모순되지 않는 유용한 역할 표현인지 판단한다' in prompt
        assert 'design_choice라는 분류 자체로 unknown이나 supported를 정하지 않는다' in prompt
        assert '자료의 모호함·미제공은 unknown' in prompt
        representation=wire['role_representation'][0]
        assert representation['declaration']==dict(candidate_ref='c',field='definition')
        assert representation['source_role']==dict(candidate_ref='c',field='role_source')
        assert representation['selected_endpoint']==role['role_basis']
        assert representation['current_uses']==[dict(relation_ref='r',endpoint='subject',locations=[
            dict(candidate_ref='r',field='predicate'),dict(candidate_ref='r',field='conditions')])]
        from app.knowledge import discovery_scope as scope
        for location in representation['current_uses'][0]['locations']:
            selected=dict(judgment='supported',locations=[deepcopy(location)],evidence_refs=[dict(block_id='e')])
            scope.locations(selected,supplied)
            current=next(c for c in wire['comparison_terms'] if c['id']==location['candidate_ref'])
            assert selected['locations'][0]['quote']==current[location['field']]
        assert wire['review_scope']['missing_meanings_allowed'] is False
        assert 'definition_completeness' not in prompt.split('\nINPUT:\n')[0]
    else: assert 'role_representation' not in wire
    assert (context,supplied)==before


@pytest.mark.parametrize('bad',[None,'old_only','both','missing'])
def test_role_wire_coverage_restores_only_name_and_preserves_verdicts(bad):
    from app.knowledge import discovery_scope as scope
    value=dict(judgment='refuted',reason='실제 누락',required_meanings=[dict(judgment='unknown',locations=[],missing_source='외부 자료')])
    row=dict(candidate_ref='c',role_coverage=deepcopy(value),claim_reviews=[dict(judgment='refuted')])
    if bad in {'old_only','missing'}:row.pop('role_coverage')
    if bad in {'old_only','both'}:row['definition_completeness']=deepcopy(value)
    output=dict(observation_checks=[row])
    if bad:
        with pytest.raises(ValueError):scope.restore_role_review(output)
    else:
        scope.restore_role_review(output)
        assert output==dict(observation_checks=[dict(candidate_ref='c',definition_completeness=value,claim_reviews=[dict(judgment='refuted')])])


def test_role_wire_schema_preserves_nested_requirements_and_location_contract():
    from app.knowledge import discovery_scope as scope
    schema=a2.models.ScopedCritique.model_json_schema();before=deepcopy(schema)
    scope.role_schema(schema)
    def check(old,new):
        if isinstance(old,list):
            assert len(old)==len(new)
            for a,b in zip(old,new):check(a,b)
        elif isinstance(old,dict):
            assert set(new)==set(old)
            for k,v in old.items():
                if k=='properties' and 'definition_completeness' in v:
                    assert 'definition_completeness' not in new[k]
                    check(v['definition_completeness'],new[k]['role_coverage'])
                    assert {a:b for a,b in v.items() if a!='definition_completeness'}=={a:b for a,b in new[k].items() if a!='role_coverage'}
                elif k=='required':assert new[k]==['role_coverage' if s=='definition_completeness' else s for s in v]
                else:check(v,new[k])
        else:assert old==new
    check(before,schema)


@pytest.mark.parametrize('stage',['critic','requirements'])
def test_imported_lower_output_review_timings_do_not_reduce_new_capacity_reservation(monkeypatch,stage):
    from app.knowledge import discovery_synthesis as synthesis, discovery_requirements as requirements
    recipe=a2.recipe({});recipe['call_timeout']=720
    old=deepcopy(recipe);old.pop(stage+'_num_predict')
    unit=dict(id=stage+':old',stage=stage,status='succeeded',imported_recipe=old,attempts=[dict(elapsed_s=50)])
    run=dict(recipe=recipe,analysis_units=[unit],candidate_groups=[])
    before=deepcopy(unit)
    monkeypatch.setattr(synthesis,'assemble',lambda *_: [])
    monkeypatch.setattr(requirements,'pending_calls',lambda *_,**__: {})
    a2.review_reservation(run,0,{}, {},set())
    assert run['role_time_estimates'][stage]['estimate_s']==720 and unit==before
    run['analysis_units'].append(dict(id=stage+':new',stage=stage,status='succeeded',attempts=[dict(elapsed_s=400)]))
    a2.review_reservation(run,0,{}, {},set())
    assert run['role_time_estimates'][stage]['estimate_s']==500
    assert run['role_time_estimates'][stage]['observed_count']==1 and unit==before


def test_primary_type_review_includes_direct_current_uses_without_reverse_recursion():
    import json
    from app.knowledge import discovery_synthesis as synthesis, discovery_scope as scope
    from app.tests.unit.test_knowledge_discovery_review_scope import projection
    run,group,by_id,_,_,_=projection()
    run['recipe']=a2.recipe({});run['id']='uses';run['cqs']=[dict(id='q',question='두 경우의 기준과 조건')]
    other=deepcopy(group['candidates'][-1]);other.update(id='other',definition='다른 유형')
    group['candidates'][2]['object']='other'
    raw=deepcopy(group['candidates'][0]['source_relation']);raw.update(id='unmodeled',object='target')
    group['candidates'] += [other,raw]
    context,deps,supplied=synthesis.review_context(run,group,dict(hierarchies=[]),by_id,{'b':dict(block_ids=['b'])})
    context['review_target_ids']=['target'];before=deepcopy((context,supplied))
    batch=synthesis.review_batches(context,deps,supplied,by_id,{'b':dict(block_ids=['b'])})[0]
    assert set(batch['supplied'])=={'target','actor','r1','r2'}
    assert batch['context']['review_target_ids']==['target']
    assert {'r3','other','unmodeled'} <= set(batch['context']['review_scope']['omitted_comparison_ids'])
    assert (context,supplied)==before and batch['dependency_ids']==deps
    _,prompt=a2.make_prompt(run,'critic',batch['context'],deps,batch['supplied'])
    wire=json.loads(prompt.split('\nINPUT:\n')[1])
    assert {r['relation_ref'] for r in wire['relation_bindings']}=={'r1','r2'}
    relation=next(c for c in wire['comparison_terms'] if c['id']=='r2')
    assert relation['subject']=='행위자' and relation['object']=='대상'
    location=dict(judgment='supported',locations=[dict(candidate_ref='r2',field='predicate')],evidence_refs=[dict(block_id='b')])
    assert scope.locations(location,batch['supplied'])
    changed=deepcopy(context)
    next(c for c in changed['unapproved_relations'] if c['id']=='r2')['conditions']='변경된 현재 조건'
    changed_supplied=deepcopy(supplied);changed_supplied['r2']['conditions']='변경된 현재 조건'
    changed_supplied['r2']['source_relation']['conditions']='변경된 현재 조건'
    follow=synthesis.review_batches(changed,deps,changed_supplied,by_id,{'b':dict(block_ids=['b'])})[0]
    assert a2.make_prompt(run,'critic',follow['context'],deps,follow['supplied'])[1]!=prompt


def test_focused_proposition_does_not_claim_omitted_global_meanings():
    from app.knowledge import discovery_synthesis as synthesis
    from app.tests.unit.test_knowledge_discovery_review_scope import projection
    run,group,by_id,_,_,_=projection()
    run['recipe']=a2.recipe({});group['primary_candidate_ids']=['r1']
    context,deps,supplied=synthesis.review_context(run,group,dict(hierarchies=[]),by_id,{'b':dict(block_ids=['b'])})
    batches=synthesis.review_batches(context,deps,supplied,by_id,{'b':dict(block_ids=['b'])})
    assert [b['context']['review_component'] for b in batches]==['proposition','binding']
    for batch in batches:
        assert not batch['context']['review_scope']['missing_meanings_allowed']
        assert {'r2','r3'} <= set(batch['context']['review_scope']['omitted_comparison_ids'])
        assert batch['context']['review_scope']['primary_source_spans']


def concepts(rows, context, block, alignments=()):
    run=dict(recipe=dict(definition_contract='authored-v2'),cqs=[dict(id='cq1')],scope_items=[],analysis_units=[])
    return a2.concept_records(dict(observations=rows,alignments=list(alignments),gaps=[],actions=[]),
        a2.models.AuthoredConcepts,run,['e'],{'e':block},{},context,'concept:g')


@pytest.mark.parametrize('bad',['schema','source','declaration','normalize','duplicate'])
def test_concept_independent_rows_keep_good_candidate_and_error_provenance(bad):
    row,_,block,context=authored('source_extract');row.update(local_ref='good',cq_ids=['cq1'])
    invalid=deepcopy(row);invalid['local_ref']='bad'
    if bad=='schema': invalid['classification']='invalid'
    if bad=='source': invalid['source_refs']=['outside']
    if bad=='declaration': invalid['source_selection']['source_quote']='존재하지 않는 구절'
    if bad=='normalize': invalid['cq_ids']=['outside']
    rows=[row,invalid]
    if bad=='duplicate': rows.append(deepcopy(invalid))
    result=concepts(rows,context,block,[dict(observation_ref='bad',target_id='outside',reason='실패 관측 참조')])
    assert [r['local_ref'] for r in result['observations']]==['good']
    assert len(result['record_errors'])==(3 if bad=='duplicate' else 2)
    assert result['record_errors'][0]['record']==invalid
    assert result['record_errors'][0]['primary_source_spans']
    assert not result['alignments'] and result['raw_observation_count']==len(rows)


@pytest.mark.parametrize('occurrence',[None,1,2,3])
def test_repeated_exact_quote_requires_explicit_valid_occurrence(occurrence):
    row,_,block,context=authored('source_extract');row['cq_ids']=['cq1']
    quote=row['source_selection']['source_quote']
    block['text']='앞. '+quote+' 중간. '+quote+' 끝.'
    context['blocks']=[dict(ref='e',text=block['text'],span=[0,len(block['text'])],source_ref='s1')]
    row['source_selection']['occurrence']=occurrence
    result=concepts([row],context,block)
    if occurrence in {1,2}:
        ref=result['observations'][0]['definition_evidence_refs'][0]
        start=block['text'].find(quote) if occurrence==1 else block['text'].rfind(quote)
        assert ref['span']==[start,start+len(quote)] and ref['quote']==quote
        assert ref['source_version_id']=='v' and ref['parse_run_id']=='p'
    else:
        assert not result['observations'] and result['record_errors']


@pytest.mark.parametrize('with_row',[False,True])
def test_concept_envelope_still_rejects_blank_gaps(with_row):
    row,_,block,context=authored();row['cq_ids']=['cq1']
    run=dict(recipe={},cqs=[dict(id='cq1')],scope_items=[],analysis_units=[])
    with pytest.raises(ValueError,match='빈 문자열'):
        a2.concept_records(dict(observations=[row] if with_row else [],alignments=[],gaps=['   '],actions=[]),
            a2.models.AuthoredConcepts,run,['e'],{'e':block},{},context,'concept:g')


@pytest.mark.parametrize('relevance',['related','unrelated','unknown'])
def test_owned_unassigned_request_is_explicitly_compared_per_requirement(relevance):
    req,run,result,by_id,cm=requirement_fixture()
    run['recovery_requests'][0]['meanings'][0]['cq_ids']=[]
    ctx,_,supplied=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    assert not ctx['recovery_targets'] and [r['id'] for r in ctx['unassigned_recovery_targets']]==['r']
    ref=dict(block_id='e',span=[0,len(by_id['e']['text'])])
    item=dict(meaning='선정 조건',applies_to='선정',locations=[],judgment='unknown',cause='source_absent',
        evidence_refs=[],missing_source='별도 상세 조건 자료',reason='자료 미제공',recovery_ids=[],candidate_ref='',role='concept')
    if relevance=='related': item.update(judgment='refuted',cause='extraction_missing',evidence_refs=[ref],missing_source='',recovery_ids=['r'])
    output=dict(requirement_id='q',meanings=[item],reason='요구 대조',recovery_attributions=[dict(request_id='r',
        relevance=relevance,evidence_refs=[ref] if relevance!='unknown' else [],reason='원문과 현재 요구의 범위 대조')])
    checked=req.normalize(output,ctx,supplied,by_id)
    assert not checked['resolved_recovery_ids']  # Attribution alone is never recovery.
    missing=deepcopy(output);missing['recovery_attributions']=[]
    with pytest.raises(ValueError,match='미귀속'): req.normalize(missing,ctx,supplied,by_id)
    # A context-only window cannot own this request.
    run['frontier'][0]['segments']=[dict(block_id='e',span=[0,1],shared_spans=[[1,len(by_id['e']['text'])]],recipe=a2.segments.VERSION)]
    run['recovery_requests'][0]['target']=[['e',[2,len(by_id['e']['text'])]]]
    narrow,_,_=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    assert not narrow['unassigned_recovery_targets']


def test_current_raw_supported_relation_with_own_binding_error_is_repairable(monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    monkeypatch.setattr(synthesis.reviews,'valid_ids',lambda *_:{'r'})
    group=dict(primary_candidate_ids=['r','other'])
    taxonomy=dict(binding_errors=[dict(candidate_ids=['r'],record=dict(subject_ref='t1'),reason='미선언 유형')])
    review=dict(relation_checks=[dict(candidate_ref='r',judgment='supported'),dict(candidate_ref='other',judgment='unknown')])
    assert synthesis.binding_repairs(group,review,taxonomy,{'r':dict(subject='원문 주체')})=={'r'}
    monkeypatch.setattr(synthesis.reviews,'valid_ids',lambda *_:None)
    assert not synthesis.binding_repairs(group,review,taxonomy,{})
    review['relation_checks'][0]['judgment']='unknown'
    assert not synthesis.binding_repairs(group,review,taxonomy,{})


def test_historical_critic_error_replaced_only_for_explicit_actually_corrected_current_candidate(monkeypatch):
    from app.knowledge import discovery_recovery as recovery
    monkeypatch.setattr(recovery.reviews,'valid_ids',lambda *_:{'c'})
    errors=[dict(candidate_ids=['c'],reason='이전 개별 판정 오류'),dict(candidate_ids=[],reason='이전 전역 오류')]
    run=dict(analysis_units=[dict(id='critic:old',stage='critic',output=dict(record_errors=errors))],frontier=[],candidate_groups=[],
        result=dict(revision_history=[dict(candidate_id='c')],requirement_assessments=[dict(requirement_kind='cq',requirement_id='q',judgment='supported')],
            failures=[],capacity_pending=[],mandatory_pending=[],no_result_groups=[]))
    current={'c':dict(cq_ids=['q'])};latest={'c':dict(observation_checks=[dict(candidate_ref='c',judgment='supported')])}
    active=recovery.active_blockers(run,current,latest,set())
    assert [e['reason'] for e in active['record_errors']]==['이전 전역 오류']
    assert len(errors)==2
    run['result']['revision_history']=[]
    assert len(recovery.active_blockers(run,current,latest,set())['record_errors'])==2


@pytest.mark.parametrize('judgment,cause,missing,valid',[
    ('supported','fulfilled','',True),('supported','scope_conflict','',False),
    ('refuted','source_absent','시행령 원천 미제공',False),('unknown','source_absent','시행령 원천 미제공',True),
    ('unknown','source_absent','',False),('refuted','extraction_missing','',True)])
def test_requirement_generation_schema_and_validation_share_verdict_cause(judgment,cause,missing,valid):
    import jsonschema
    row=dict(meaning='요구의 실제 의미',applies_to='대상',source_refs=['s1'],missing_source=missing,
        locations=[],judgment=judgment,cause=cause,reason='원문 대조',role='concept',candidate_ref='',recovery_ids=[])
    schema=a2.models.RequirementReview.model_json_schema();a2.models.requirement_schema(schema)
    data=dict(requirement_id='q',meanings=[row],reason='요구 대조')
    if valid:
        jsonschema.validate(data,schema);a2.models.RequirementReview.model_validate(data)
    else:
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(data,schema)
        with pytest.raises(ValueError): a2.models.RequirementReview.model_validate(data)


def test_mixed_failed_claim_keeps_supported_required_meaning_in_revision_prompt_and_history():
    from app.knowledge import discovery_scope as scope
    row,_,block,context=authored();row.update(id='c',cq_ids=['cq1'])
    row=a2.models.AuthoredObservation.model_validate({k:v for k,v in row.items() if k!='id'}).model_dump()|{'id':'c'}
    check=dict(candidate_ref='c',claim_reviews=[dict(judgment='refuted',claim='정상 역할과 잘못된 효과',field='definition')],
        definition_completeness=dict(required_meanings=[dict(judgment='supported',meaning='정상 선정 역할',applies_to='대상',evidence_refs=[dict(block_id='e',span=[0,len(block['text'])])])]))
    basis=scope.preservation_basis(row,[check]);assert len(basis)==1
    run=dict(id='run',recipe=a2.recipe({}),cqs=[dict(id='cq1',question='대상 역할')],scope_items=[])
    needed=scope.required_context(row,[check])
    context.update(target_ids=['c'],targets=[row],preservation_basis=basis,required_context=needed,observation_checks=[check])
    _,prompt=a2.make_prompt(run,'revision',context,['e'],{'c':row})
    assert 'preservation_basis' in prompt and '정상 선정 역할' in prompt
    replacement=deepcopy(row);replacement.pop('id');replacement.update(candidate_ref='c',reason='근거 없는 효과만 교정')
    output=a2.normalize(dict(observations=[replacement],relations=[],hierarchies=[],deferred=[]),'revision',run,['e'],{'e':block},{'c':row},context)
    history=output['history'][0]
    assert history['preservation_basis']==basis and history['required_context']==needed
    from app.knowledge import discovery_candidates as ids
    assert ids.history_view(run,history)['revision_basis_hash']==history['after']['revision_basis_hash']
    history['required_context'][0]['meaning']='변경한 필수 의미'
    assert ids.history_view(run,history)['revision_basis_hash']!=history['after']['revision_basis_hash']


def test_final_call_schema_cannot_widen_requirement_cause_verdict(monkeypatch):
    import json
    import jsonschema
    req,run,result,by_id,cm=requirement_fixture()
    run.update(id='wire',status='running',model_identity={},metrics=dict(llm_calls=0,model_total_s=0))
    context,deps,supplied=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    captured=[]
    async def capture(prompt,schema,*_):
        captured.append((json.loads(prompt.split('\nINPUT:\n')[1]),schema))
        raise ValueError('wire capture only; no HTTP')
    monkeypatch.setattr(a2,'model_call',capture);monkeypatch.setattr(a2,'model_identity',lambda _: {})
    monkeypatch.setattr(a2,'save',lambda *_:None);monkeypatch.setattr(a2,'cancelled',lambda *_:False)
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by_id))
    monkeypatch.setattr(a2,'recipe',lambda _:deepcopy(run['recipe']))  # Execute the frozen legacy schema.
    a2.call(None,run,'requirements','capture',context,deps,by_id,supplied)
    assert len(captured)==1,run['analysis_units']
    data,schema=captured[0];ref=a2.segments.originals(data)[0]['source_ref']
    row=dict(meaning='실제 의미',applies_to='대상',source_refs=[ref],missing_source='원천 미제공',locations=[],
        judgment='unknown',cause='source_absent',reason='필요 자료 없음',role='concept',candidate_ref='',recovery_ids=['r'])
    wire=dict(requirement_id='q',meanings=[row],reason='요구 대조',context_checks={})
    jsonschema.validate(wire,schema)
    invalid=deepcopy(wire);invalid['meanings'][0]['recovery_ids']=['context-meaning-key']
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(invalid,schema)
    invalid=deepcopy(wire);invalid['meanings'][0]['locations']=[dict(candidate_ref='c',field='time',quote='')]
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(invalid,schema)
    for judgment,cause in [('supported','source_absent'),('refuted','source_absent'),('unknown','fulfilled'),('supported','scope_conflict')]:
        invalid=deepcopy(wire);invalid['meanings'][0].update(judgment=judgment,cause=cause)
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(invalid,schema)


@pytest.mark.parametrize('end_quote',['마지막 의미','없는 끝','첫 의미'])
def test_long_source_selection_restores_exact_contiguous_text_between_anchors(end_quote):
    row,_,block,context=authored('source_extract');row['cq_ids']=['cq1']
    block['text']='도입. 목록: 첫 의미; 둘째 의미; 마지막 의미. 후문.'
    context['blocks']=[dict(ref='e',text=block['text'],span=[0,len(block['text'])],source_ref='s1')]
    row['source_selection']=dict(source_ref='s1',source_quote='목록:',end_quote=end_quote)
    result=concepts([row],context,block)
    if end_quote=='없는 끝': assert result['record_errors']
    else:
        value=result['observations'][0];ref=value['definition_evidence_refs'][0]
        assert value['definition']==block['text'][slice(*ref['span'])]
        assert value['definition'].startswith('목록:') and value['definition'].endswith(end_quote)


def test_unassigned_extraction_requires_actual_current_related_missing_receipt():
    req,run,_,by_id,_=requirement_fixture();r=run['recovery_requests'][0];r['meanings'][0]['cq_ids']=[]
    assert not req.extraction_authorized(run,r,by_id)
    r['requirement_key']='cq:q'
    assert not req.extraction_authorized(run,r,by_id)  # A label alone is not a receipt.
    attr=dict(relevance='related',source_fingerprint=req.attribution_fingerprint(r,run['cqs'][0],by_id),
        assessment_unit_id='requirements:q',assessment_fingerprint='actual')
    r['requirement_attributions']={'cq:q':attr}
    unit=dict(id='requirements:q',status='succeeded',output=dict(assessment_fingerprint='actual',meanings=[dict(cause='extraction_missing',recovery_ids=['r'])]))
    run['analysis_units']=[unit]
    assert req.extraction_authorized(run,r,by_id)
    for relevance in ('unknown','unrelated'):
        attr['relevance']=relevance
        assert not req.extraction_authorized(run,r,by_id)
    attr['relevance']='related';unit['output']['meanings'][0]['cause']='source_absent'
    assert not req.extraction_authorized(run,r,by_id)
    unit['output']['meanings'][0]['cause']='extraction_missing';by_id['e']['parse_run_id']='changed'
    assert not req.extraction_authorized(run,r,by_id)


@pytest.mark.parametrize('status,expected',[('maintained','supported'),('lost','refuted'),('unknown','unknown'),('corrected','supported')])
def test_all_required_context_is_rechecked_separately_from_normal_preservation(status,expected):
    from app.knowledge import discovery_scope as scope
    source=dict(block_id='e',span=[0,8])
    original=dict(context_needs=[dict(meaning='항목별 기간',applies_to='하위 항목',evidence_refs=[source],missing_source='')])
    prior=dict(definition_completeness=dict(required_meanings=[dict(meaning='하위 기간 한정',applies_to='하위 항목',judgment='refuted',evidence_refs=[source])]))
    needed=scope.required_context(original,[prior])
    assert len(needed)==2 and not scope.preservation_basis(original,[prior])
    candidate=dict(id='c',definition='구성 목록',conditions='하위 항목만 기간 한정',revision_basis_hash='basis')
    records=[dict(m,status=status,reason='원문과 현재 표현 대조',locations=[dict(candidate_ref='c',field='conditions',quote='하위 항목만 기간 한정')] if status=='maintained' else []) for m in needed]
    check=dict(candidate_ref='c',judgment='supported',definition_completeness={},context_checks=records)
    context=dict(revision_comparisons={'c':dict(expected_meanings=[],required_context=needed)})
    if status=='corrected':
        for record in records:record['replacement']=dict(meaning='남는 조건',applies_to='하위 항목',judgment='supported',locations=[dict(candidate_ref='c',field='conditions')],evidence_refs=[source],missing_source='',reason='원문 조건은 계속 필요')
    for record in records:record.update(meaning=record['meaning_key'],applies_to='잘못 복사한 문구')
    scope.preserve(check,context,{'c':candidate})
    assert [(r['meaning'],r['applies_to']) for r in records]==[(m['meaning'],m['applies_to']) for m in needed]
    if status!='corrected': assert {m['meaning_key'] for m in scope.required_context({},[check])}=={m['meaning_key'] for m in needed}
    assert check['judgment']==expected and check['required_context_judgment']==expected
    check['context_checks']=records[:1]
    with pytest.raises(ValueError,match='필수 문맥'):scope.preserve(check,context,{'c':candidate})
    check['context_checks']=records
    if status=='corrected':
        records[0]['evidence_refs']=[]
        with pytest.raises(ValueError,match='원문 누락'):scope.preserve(check,context,{'c':candidate})


def test_source_discovery_excludes_candidate_answers_and_reuses_only_current_scope(monkeypatch):
    from app.knowledge import discovery_scope as scope
    _,run,result,by_id,_=requirement_fixture();run['recipe']=a2.recipe({});run['recipe'].pop('context_applicability_contract')
    c=result['observations'][0];c.update(definition='정답처럼 보이는 기존 주장',cq_ids=['q'])
    c['evidence_refs']=[dict(block_id='e',span=[0,5])]
    run['cqs'].append(dict(id='other',question='무관한 전체 요구'))
    ctx=dict(blocks=[dict(ref='e',text=by_id['e']['text'])],review_target_ids=['c'])
    identifier,key,packet,deps=scope.discovery_requests(run,ctx,by_id,{'c':c})[0]
    assert 'definition' not in str(packet) and '정답처럼' not in str(packet)
    assert packet['target']['source_anchors']==[dict(block_id='e',span=[0,5])]
    _,prompt=a2.make_prompt(dict(run,id='r'),'context',packet,deps,{})
    assert '무관한 전체 요구' not in prompt and 'source_anchors' not in prompt
    assert 'JSON과 짧은 한국어' not in prompt  # No mixed candidate/task COMMON instructions.
    need=dict(meaning='원문의 한정',applies_to='대상',missing_source='',evidence_refs=[dict(block_id='e',span=[0,5])])
    unit=dict(id='context:'+key,stage='context',status='succeeded',context_candidate_ids=['c'],context_target=packet['target'],
        dependency_ids=deps,source_ref_map={'s':dict(block_id='e',span=[0,len(by_id['e']['text'])])},output=dict(context_needs=[need]))
    run['analysis_units']=[unit]
    assert scope.discovered_context(run,by_id,{'c':c},'cq','q')
    assert not scope.discovered_context(run,by_id,{'c':c},'cq','other')
    assert scope.attach_saved(run,ctx,by_id,{'c':c})['source_requirements']['c']
    c['definition']='후보 정의만 변경'
    assert scope.discovered_context(run,by_id,{'c':c},'cq','q')
    run['recipe'].update(num_ctx=65536,input_chars=40000)
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by_id))
    monkeypatch.setattr(a2,'call',lambda *_:pytest.fail('동일 성공 문맥을 재호출함'))
    assert scope.discover(None,run,ctx,by_id,{'c':c})['source_requirements']['c']
    assert scope.discovered_context(run,by_id,{'c':c},'cq','q')
    run['model_identity']={'review':{'digest':'changed'}}
    assert not scope.discovered_context(run,by_id,{'c':c},'cq','q')
    run.pop('model_identity')
    old_prompt=a2.models.PROMPTS['context']
    monkeypatch.setitem(a2.models.PROMPTS,'context',old_prompt+' 새 발견 지시')
    assert not scope.discovered_context(run,by_id,{'c':c},'cq','q')
    monkeypatch.setitem(a2.models.PROMPTS,'context',old_prompt)
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set())
    with pytest.raises(ValueError,match='사용 중단'): scope.discover(None,run,ctx,by_id,{'c':c})
    for field in ('parse_run_id','source_version_id','text'):
        old=by_id['e'][field];by_id['e'][field]=old+'changed'
        assert not scope.discovered_context(run,by_id,{'c':c},'cq','q')
        by_id['e'][field]=old
    run['cqs'][0]['question']='변경된 요구'
    assert not scope.discovered_context(run,by_id,{'c':c},'cq','q')


def test_pending_saved_reviews_retain_their_source_discovery_reservations():
    from app.knowledge import discovery_synthesis as synthesis
    group=dict(review_unit_ids=['critic:g'],review_context_unit_ids=['context:source'])
    assert synthesis.pending_review_units({},group,{}, {})==['critic:g','context:source']


def test_source_context_failure_clears_only_with_current_scoped_completion(monkeypatch):
    from app.knowledge import discovery_recovery as recovery
    monkeypatch.setattr(recovery.reviews,'valid_ids',lambda *_:{'c'})
    failure=dict(unit_id='context:old',error='이전 발견 실패')
    run=dict(frontier=[],candidate_groups=[],analysis_units=[
        dict(id='context:old',stage='context',status='failed',context_candidate_ids=['c'],output=None),
        dict(id='context:new',stage='context',status='succeeded',dependency_ids=['e'],output={})],
        result=dict(revision_history=[],requirement_assessments=[dict(requirement_kind='cq',requirement_id='q',judgment='supported')],
            failures=[failure],capacity_pending=[],mandatory_pending=[],no_result_groups=[]))
    current={'c':dict(cq_ids=['q'])};latest={'c':dict(context_unit_ids=['context:new'],observation_checks=[dict(candidate_ref='c',judgment='supported')])}
    assert not recovery.active_blockers(run,current,latest,{'e'})['failures']
    assert run['result']['failures']==[failure]
    assert recovery.active_blockers(run,current,latest,set())['failures']==[failure]
    run['result']['requirement_assessments'][0]['judgment']='unknown'
    assert recovery.active_blockers(run,current,latest,{'e'})['failures']==[failure]


def test_context_receipt_wire_requires_exact_target_count_and_known_keys():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.RequirementReview.model_json_schema()
    scope.context_check_schema(schema,dict(source_context_needs=[dict(meaning_key='required')]),'requirements')
    record=dict(meaning_key='required',meaning='필수 한정',applies_to='하위 항목',source_refs=['s'],missing_source='',locations=[],status='lost',reason='아직 미표현')
    row=dict(meaning='누락',applies_to='하위 항목',source_refs=['s'],missing_source='',locations=[],judgment='refuted',cause='extraction_missing',reason='원문 대조',role='concept',candidate_ref='',recovery_ids=[])
    value=dict(requirement_id='q',meanings=[row],reason='요구 대조',context_checks={'required':{k:v for k,v in record.items() if k!='meaning_key'}})
    jsonschema.validate(value,schema)
    for records in ({},{'outside':record},{'required':record,'outside':record}):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(dict(value,context_checks=records),schema)


def test_authored_definition_longer_than_old_limit_survives_storage_conversion(service):
    from app.tests.unit.test_knowledge_ontology_changes import analysis
    from app.knowledge import ontology_changes, ontology_changes_models, discovery_design
    row,source,block,context=authored()
    text=('구성 사업과 하위 항목의 조건을 함께 보존하는 정의. '*16).strip()
    row['definition']=text
    value=a2.models.AuthoredObservation.model_validate(row).model_dump()
    output=dict(observations=[value]);discovery_design.declarations(output,{'r':source},{'e':block},context,authored=True)
    assert value['definition']==text and len(text)>240
    run,ref=analysis(service);run['result']['observations'][0]['definition']=text
    with service.repository.connect() as db:stored_block=service.repository.get(db,'blocks',ref['block_id'])
    rows,_,_=ontology_changes._convert(run,{}, {stored_block['id']:stored_block})
    assert ontology_changes_models.Definition.model_validate(rows[0]['after']).definition==text
    with pytest.raises(ValueError): a2.models.AuthoredObservation.model_validate(dict(row,definition='가'*1001))


def test_post_correction_wire_requires_each_preserved_meaning_receipt():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.ScopedCritique.model_json_schema()
    schema['$defs']['ObservationCheck']=deepcopy(schema['properties']['observation_checks']['items'])
    schema['$defs']['ObservationCheck']['properties']['candidate_ref']['enum']=['c']
    context=dict(revision_comparisons={'c':dict(expected_meanings=[dict(meaning_key='normal')],required_context=[])})
    scope.context_check_schema(schema,context,'critic')
    node=schema['$defs']['ObservationCheck']['anyOf'][0]
    receipt=dict(node['properties']['preservation_checks'],**{'$defs':schema['$defs']})
    item=dict(meaning_key='normal',meaning='정상 의미',applies_to='대상',source_refs=['s'],missing_source='',locations=[],status='lost',reason='정상 의미 소실')
    jsonschema.validate({'normal':{k:v for k,v in item.items() if k!='meaning_key'}},receipt)
    for items in ({},{'outside':item},{'normal':item,'outside':item}):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(items,receipt)


@pytest.mark.parametrize('wrapped',[False,True])
def test_relation_post_correction_wire_requires_receipts_and_forbids_unrequested_ones(wrapped):
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.ScopedCritique.model_json_schema()
    original=deepcopy(schema['properties']['relation_checks']['items'])
    original['properties']['candidate_ref']['enum']=['r','unchanged']
    schema['$defs']['RelationCheck']={'anyOf':[deepcopy(original),deepcopy(original)]} if wrapped else deepcopy(original)
    if wrapped:
        schema['$defs']['RelationCheck']['anyOf'][0]['properties']['source_refs']['minItems']=1
        schema['$defs']['RelationCheck']['anyOf'][1]['properties']['semantic_checks']={'type':'object','properties':{'subject':{'const':'unknown'}}}
    scope.context_check_schema(schema,dict(revision_comparisons={'r':dict(expected_meanings=[dict(meaning_key='normal')])}),'critic')
    nodes=schema['$defs']['RelationCheck']
    if wrapped:
        assert nodes['anyOf'][0]['anyOf'][0]['properties']['source_refs']['minItems']==1
        assert nodes['anyOf'][1]['anyOf'][0]['properties']['semantic_checks']['properties']['subject']['const']=='unknown'
        nodes=nodes['anyOf'][0]
    changed,unchanged=nodes['anyOf']
    empty=dict(unchanged['properties']['preservation_checks'],**{'$defs':schema['$defs']})
    assert empty['maxItems']==0
    jsonschema.validate([],empty)
    receipt=dict(changed['properties']['preservation_checks'],**{'$defs':schema['$defs']})
    item=dict(meaning='normal meaning',applies_to='r',source_refs=['s'],missing_source='',locations=[],status='unknown',reason='not verified')
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate([dict(item,meaning_key='invented')],empty)
    jsonschema.validate({'normal':item},receipt)
    for missing in ([],{}, {'wrong':item}, {'normal':item,'wrong':item}):
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(missing,receipt)
    output=dict(relation_checks=[dict(candidate_ref='r',preservation_checks={'normal':deepcopy(item)})])
    scope.restore_receipts(output)
    assert output['relation_checks'][0]['preservation_checks']==[dict(item,meaning_key='normal')]
    legacy=a2.models.ScopedCritique.model_json_schema();legacy['$defs']['RelationCheck']=deepcopy(original)
    scope.context_check_schema(legacy,{},'critic')
    assert all(n['properties']['preservation_checks']['maxItems']==0 for n in legacy['$defs']['RelationCheck']['anyOf'])


@pytest.mark.parametrize('quote',[None,'현재 정의','현재...정의',''])
def test_selected_current_field_restores_whole_text_only_when_quote_omitted(quote):
    from app.knowledge import discovery_scope as scope
    candidate=dict(id='c',definition='현재 정의와 하위 기간',time='',role_source=None)
    location=dict(candidate_ref='c',field='definition',quote=quote)
    item=dict(locations=[location],judgment='supported',evidence_refs=[dict(block_id='e')])
    if quote in ('현재...정의',''):
        with pytest.raises(ValueError):scope.locations(item,{'c':candidate})
    else:
        assert scope.locations(item,{'c':candidate})
        assert location['quote']==(candidate['definition'] if quote is None else quote)
        if quote is None:assert location['selection_mode']=='whole_field'
    for field in ('time','role_source'):
        item['locations']=[dict(candidate_ref='c',field=field)]
        with pytest.raises(ValueError):scope.locations(item,{'c':candidate})
    item['locations']=[dict(candidate_ref='old',field='definition')]
    with pytest.raises(ValueError):scope.locations(item,{'c':candidate})


def test_address_wire_accepts_valid_comparison_and_hierarchy_but_no_empty_or_fake_field():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    candidates=[dict(id='comparison',definition='유효 비교 유형',time='',role_source=None),dict(id='parent',definition='상위 유형'),
        dict(id='hierarchy',child_ref='comparison',parent_ref='parent'),dict(id='bad',definition='검증 실패',validation=['error'])]
    schema=a2.models.RequirementReview.model_json_schema();scope.location_schema(schema,candidates)
    wire=dict(schema['$defs']['MeaningLocation'],**{'$defs':schema['$defs']})
    for location in (dict(candidate_ref='comparison',field='definition'),dict(candidate_ref='hierarchy',field='structure')):
        jsonschema.validate(location,wire)
        item=dict(locations=[location],judgment='supported',evidence_refs=[dict(block_id='e')])
        assert scope.locations(item,{c['id']:c for c in candidates})
    for identifier,field in [('comparison','time'),('comparison','role_source'),('bad','definition'),('old','definition')]:
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(dict(candidate_ref=identifier,field=field),wire)
    item=dict(locations=[dict(candidate_ref='hierarchy',field='structure')],judgment='supported',evidence_refs=[dict(block_id='e')])
    with pytest.raises(ValueError,match='끝점'):scope.locations(item,{c['id']:c for c in candidates if c['id']!='parent'})


@pytest.mark.parametrize('component',[None,'proposition','binding'])
def test_relation_comparison_view_preserves_current_typed_locations_and_original_history(component):
    import json
    from app.knowledge import discovery_scope as scope
    natural=dict(subject='시·도지사',predicate='정할 수 있다',object='기준',statement_type='rule',negation=False,conditions='제2호 공급')
    current=dict(natural,id='r',subject='governor',object='criteria',statement_type='design_proposal',source_relation=natural,revision_basis_hash='basis')
    observation=dict(id='governor',classification='type',definition='시·도지사')
    hierarchy=dict(id='h',child_ref='governor',parent_ref='criteria')
    context=dict(review_focus='relations',review_component=component,revision_comparisons={
        'r':dict(before=dict(natural,id='r'),after=deepcopy(current)),
        'governor':dict(before=deepcopy(observation),after=deepcopy(observation)),
        'h':dict(before=deepcopy(hierarchy),after=deepcopy(hierarchy))})
    saved=deepcopy(context)
    supplied={'r':current,'governor':observation,'criteria':dict(id='criteria',definition='별도 기준')}
    original=deepcopy(supplied)
    run=dict(id='run',recipe=dict(reference_contract='canonical-v1'),cqs=[],scope_items=[])
    _,prompt=a2.make_prompt(run,'critic',context,[],supplied)
    comparisons=json.loads(prompt.split('\nINPUT:\n')[1])['revision_comparisons']
    assert comparisons['r']['after']['subject']==('governor' if component=='binding' else '시·도지사')
    assert comparisons['r']['after']['statement_type']==('design_proposal' if component=='binding' else 'rule')
    assert comparisons['r']['after']['id']=='r'
    assert comparisons['governor']==context['revision_comparisons']['governor']
    assert comparisons['h']==context['revision_comparisons']['h']
    item=dict(judgment='supported',evidence_refs=[dict(block_id='e')],locations=[dict(candidate_ref='r',field='subject')])
    assert set(scope.locations(item,supplied))=={'r','governor','criteria'}
    assert item['locations'][0]['quote']=='governor'
    assert context==saved and supplied==original


def test_context_not_applicable_requires_current_scope_and_source_without_satisfying_a_claim():
    from app.knowledge import discovery_scope as scope
    meaning=dict(meaning_key='m',meaning='다른 역할의 권한',applies_to='다른 역할')
    candidate=dict(id='c',definition='현재 역할',cq_ids=['q'],scope_item_ids=[])
    item=dict(meaning,status='not_applicable',requirement_refs=['cq:q'],evidence_refs=[dict(block_id='e')],locations=[],reason='현재 요구와 역할 밖')
    context=dict(source_requirements={'c':[meaning]})
    def checked(record):
        check=dict(candidate_ref='c',judgment='unknown',definition_completeness={},context_checks=[record])
        scope.preserve(check,context,{'c':candidate});return check
    result=checked(deepcopy(item))
    assert result['judgment']=='unknown' and result['not_applicable_context_keys']==['m']
    assert not scope.required_context({},[result])
    for patch in (dict(requirement_refs=['cq:other']),dict(requirement_refs=[]),dict(evidence_refs=[]),dict(locations=[dict(candidate_ref='c',field='definition')])):
        with pytest.raises(ValueError):checked(dict(item,**patch))
    check=dict(candidate_ref='c',judgment='supported',preservation_checks=[item])
    with pytest.raises(ValueError):scope.preserve(check,dict(revision_comparisons={'c':dict(expected_meanings=[meaning])}),{'c':candidate})


@pytest.mark.parametrize('judgment',['supported','refuted','unknown'])
def test_corrected_context_retains_remaining_meaning_and_its_actual_judgment(judgment):
    from app.knowledge import discovery_scope as scope
    candidate=dict(id='c',conditions='공급 조건 A',cq_ids=['q'])
    original=dict(meaning_key='mixed',meaning='전체 정의와 공급 조건',applies_to='주택')
    replacement=dict(meaning='공급 조건 A',applies_to='해당 공급',evidence_refs=[dict(block_id='e')],missing_source='',
        locations=[dict(candidate_ref='c',field='conditions')] if judgment=='supported' else [],judgment=judgment,reason='상세 정의를 제외해도 이 조건은 필요')
    item=dict(original,status='corrected',locations=[],evidence_refs=[dict(block_id='e')],replacement=replacement,reason='요구 범위를 원문에 따라 정정')
    check=dict(candidate_ref='c',judgment='supported',definition_completeness={},context_checks=[item])
    scope.preserve(check,dict(source_requirements={'c':[original]}),{'c':candidate})
    assert check['judgment']==judgment and item['meaning']==original['meaning']
    remaining=scope.required_context({},[check])
    assert len(remaining)==1 and remaining[0]['meaning']=='공급 조건 A' and remaining[0]['replaces_meaning_key']=='mixed'
    assert remaining[0]['meaning_key']!='mixed'


def test_context_applicability_wire_cannot_exclude_normal_preservation_or_another_cq():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.RequirementReview.model_json_schema()
    scope.context_check_schema(schema,dict(requirement=dict(kind='cq',id='q'),source_context_needs=[dict(meaning_key='m')]),'requirements')
    wire=dict(schema['properties']['context_checks'],**{'$defs':schema['$defs']})
    item=dict(meaning_key='m',meaning='다른 의미',applies_to='다른 역할',source_refs=['s'],missing_source='',locations=[],status='not_applicable',requirement_refs=['cq:q'],reason='현재 요구 밖')
    item.pop('meaning_key')
    jsonschema.validate({'m':item},wire)
    for patch in (dict(requirement_refs=[]),dict(requirement_refs=['cq:other']),dict(source_refs=[]),dict(status='corrected')):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'m':dict(item,**patch)},wire)
    with pytest.raises(ValueError):a2.models.PreservationCheck.model_validate(item)


def test_keyed_receipts_restore_existing_lists_without_changing_decisions():
    from app.knowledge import discovery_scope as scope
    output=dict(observation_checks=[dict(candidate_ref='c',context_checks={'m':dict(status='unknown',reason='실제 자료 부족')},preservation_checks={})],relation_checks=[])
    scope.restore_receipts(output)
    check=output['observation_checks'][0]
    assert check['context_checks']==[dict(meaning_key='m',status='unknown',reason='실제 자료 부족')]
    assert check['preservation_checks']==[]
    before=deepcopy(output);scope.restore_receipts(output);assert output==before
    bad=dict(observation_checks=[dict(context_checks={'m':dict(meaning_key='outside')})])
    scope.restore_receipts(bad)
    assert isinstance(bad['observation_checks'][0]['context_checks'],dict)  # Existing record validator rejects it.


def test_claim_wire_cannot_quote_empty_candidate_fields_from_source_role_context():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.ScopedCritique.model_json_schema()
    schema['$defs']['ObservationCheck']=schema['properties']['observation_checks']['items']
    schema['$defs']['ObservationCheck']['properties']['candidate_ref']['enum']=['c','other']
    candidate=dict(id='c',definition='현재 역할',conditions='',exceptions=' ',time='',role_source=dict(conditions='원문 조건',time='원문 시점'))
    scope.context_check_schema(schema,{},'critic',{'c':candidate,'other':dict(id='other',definition='다른 역할',time='실제 기간')})
    item=schema['$defs']['ObservationCheck']['anyOf'][0]['properties']['claim_reviews']['items']
    field=item['properties']['field']
    jsonschema.validate('definition',field)
    for name in ('conditions','exceptions','time'):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(name,field)
    other=schema['$defs']['ObservationCheck']['anyOf'][1]['properties']['claim_reviews']['items']
    jsonschema.validate('time',other['properties']['field'])
    assert candidate['role_source']==dict(conditions='원문 조건',time='원문 시점')


def test_unassigned_recovery_wire_requires_every_request_without_deciding_relevance():
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.RequirementReview.model_json_schema()
    scope.context_check_schema(schema,dict(requirement=dict(kind='cq',id='q'),unassigned_recovery_targets=[dict(id='r1'),dict(id='r2')]),'requirements')
    wire=dict(schema['properties']['recovery_attributions'],**{'$defs':schema['$defs']})
    records={key:dict(relevance=value,source_refs=[],reason='요구별 원문 대조') for key,value in [('r1','related'),('r2','unknown')]}
    meaning=dict(meaning='요청의 실제 의미',applies_to='대상',source_refs=['s'],missing_source='',locations=[],judgment='refuted',cause='extraction_missing',reason='실제 누락',role='relation',candidate_ref='')
    records['r1']['meanings']=[meaning]
    jsonschema.validate(records,wire)
    for bad in ({'r1':records['r1']},dict(records,other=records['r1'])):
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,wire)
    result=dict(requirement_id='q',meanings=[],reason='요청별 의미 대조',context_checks={},recovery_attributions=deepcopy(records))
    jsonschema.validate(result,schema)
    scope.restore_receipts(result)
    a2.models.RequirementReview.model_validate(result)
    assert result['recovery_attributions']==[dict({k:v for k,v in value.items() if k!='meanings'},request_id=key) for key,value in records.items()]
    assert result['meanings']==[dict(meaning,recovery_ids=['r1'])]
    assert 'recovery_attributions' in schema['required']


@pytest.mark.parametrize('assigned',[[],[dict(id='existing')]])
def test_unassigned_slot_link_cannot_also_be_emitted_in_top_level_meanings(assigned):
    import jsonschema
    from app.knowledge import discovery_scope as scope
    schema=a2.models.RequirementReview.model_json_schema()
    context=dict(requirement=dict(kind='cq',id='q'),recovery_targets=assigned,unassigned_recovery_targets=[dict(id='new')])
    a2.models.requirement_schema(schema,context)
    scope.context_check_schema(schema,context,'requirements')
    meaning=dict(meaning='제공된 누락 의미',applies_to='현재 대상',source_refs=['s'],missing_source='',locations=[],judgment='refuted',cause='extraction_missing',reason='실제 누락',role='relation',candidate_ref='')
    output=dict(requirement_id='q',meanings=[dict(meaning,recovery_ids=['existing'] if assigned else [])],reason='대조',context_checks={},
        recovery_attributions={'new':dict(relevance='related',source_refs=['s'],reason='현재 요구',meanings=[meaning])})
    jsonschema.validate(output,schema)
    bad=deepcopy(output);bad['meanings'][0]['recovery_ids']=['new']
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    scope.restore_receipts(output)
    assert output['meanings'][-1]['recovery_ids']==['new']
    a2.models.RequirementReview.model_validate(output)


@pytest.mark.parametrize('last',['supported','refuted','unknown'])
def test_one_request_multiple_meanings_resolves_only_when_all_supported(last):
    req,run,result,by,cm=requirement_fixture();context,_,supplied=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    base=dict(meaning='첫 의미',applies_to='대상',locations=[dict(candidate_ref='c',field='definition')],judgment='supported',cause='fulfilled',
        evidence_refs=[dict(block_id='e',span=[0,len(by['e']['text'])])],missing_source='',reason='대조',recovery_ids=['r'],candidate_ref='c',role='concept')
    second=dict(deepcopy(base),meaning='다른 의미',judgment=last,cause={'supported':'fulfilled','refuted':'extraction_missing','unknown':'source_absent'}[last],missing_source='외부 상세' if last=='unknown' else '')
    output=req.normalize(dict(requirement_id='q',meanings=[base,second],reason='두 의미'),context,supplied,by)
    assert output['resolved_recovery_ids']==(['r'] if last=='supported' else [])
    for ids in (['r','r'],['other'],[]):
        with pytest.raises(ValueError):req.normalize(dict(requirement_id='q',meanings=[dict(base,recovery_ids=ids)],reason='잘못된 연결'),context,supplied,by)


def test_attribution_slots_forbid_wrong_links_and_preserve_explicit_existing_requests():
    from app.knowledge import discovery_scope as scope
    meaning=dict(meaning='실제 의미',judgment='refuted')
    def value(relevance='related',nested=None):
        record=dict(relevance=relevance,meanings=[deepcopy(meaning)] if nested is None else nested)
        return dict(meanings=[dict(meaning='기존 요청 의미',recovery_ids=['existing'])],recovery_attributions={'owned':record})
    output=value();scope.restore_receipts(output)
    assert [m['recovery_ids'] for m in output['meanings']]==[['existing'],['owned']]
    for bad in (value('unrelated'),value('unknown'),value(nested=[]),value(nested=[dict(meaning,recovery_ids=['other'])])):
        with pytest.raises(ValueError):scope.restore_receipts(bad)
    bad=value();bad['meanings'][0]['recovery_ids']=['owned']
    with pytest.raises(ValueError):scope.restore_receipts(bad)


def test_current_attributed_meanings_are_carried_to_recovery_and_later_requirement():
    req,run,result,by,cm=requirement_fixture();r=run['recovery_requests'][0]
    r['meanings'][0]['cq_ids']=[]
    meanings=[dict(meaning='담당 주체',cause='extraction_missing',recovery_ids=['r']),dict(meaning='공급 조건',cause='extraction_missing',recovery_ids=['r'])]
    r.update(status='pending',owner_group_ids=['g'],critic_group_id='g',meaning='항 응답 미제출',requirement_attributions={'cq:q':dict(relevance='related',source_fingerprint=req.attribution_fingerprint(r,run['cqs'][0],by),assessment_unit_id='requirements:q',assessment_fingerprint='a')})
    run['analysis_units']=[dict(id='requirements:q',stage='requirements',status='succeeded',output=dict(assessment_fingerprint='a',meanings=meanings))]
    before=deepcopy(r['meanings'])
    groups=a2.recovery_groups(run,1,by)
    assert groups[0]['recovery_meanings']==before+meanings and r['meanings']==before
    context,_,_=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    assert context['unassigned_recovery_targets'][0]['meanings']==before+meanings
    by['e']['source_version_id']='changed'
    assert not req.attributed_meanings(run,r,by)


@pytest.mark.parametrize('status',['required','not_applicable','mixed','unknown'])
def test_context_applicability_never_claims_fulfillment_and_retains_remaining_conditions(status):
    import jsonschema
    from app.knowledge import discovery_scope as scope
    original=dict(meaning_key='m',meaning='필요 조건과 범위 밖 상세',applies_to='원문 대상',evidence_refs=[dict(block_id='e')],missing_source='')
    context=dict(proposals=[original])
    schema=a2.models.ContextApplicability.model_json_schema();scope.applicability_schema(schema,context)
    decision=dict(applicability=status,source_refs=['s'],reason='현재 요구와 원문 대조',remaining=[])
    if status=='mixed':decision['remaining']=[dict(meaning='필요 조건',applies_to='정확한 하위 대상',source_refs=['s'],missing_source='')]
    raw=dict(decisions={'m':decision});jsonschema.validate(raw,schema)
    scope.restore_receipts(raw);output=a2.models.ContextApplicability.model_validate(raw).model_dump()
    for d in output['decisions']:
        d['evidence_refs']=[dict(block_id='e')]
        for m in d['remaining']:m['evidence_refs']=[dict(block_id='e')]
    result=scope.normalize_applicability(output,context)
    assert len(result['required_context'])==int(status in {'required','mixed'})
    assert result['unresolved_keys']==(['m'] if status=='unknown' else [])
    assert result['decisions'][0]['original_proposal']==original
    if status=='mixed':
        assert result['required_context'][0]['replaces_meaning_key']=='m'
        assert result['required_context'][0]['applies_to']=='정확한 하위 대상'
    invalid=dict(decision,locations=[],judgment='supported')
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(dict(decisions={'m':invalid}),schema)
    with pytest.raises(ValueError):scope.normalize_applicability(dict(decisions=[]),context)


def test_applicability_unknown_blocks_completion_without_refuting_normal_claims():
    from app.knowledge import discovery_scope as scope
    check=dict(candidate_ref='c',judgment='supported',definition_completeness={},context_checks=[])
    scope.preserve(check,dict(applicability_pending=['m']),{'c':dict(definition='정상 의미')})
    assert check['judgment']=='unknown' and check['correction_complete'] is False
    check=dict(candidate_ref='c',judgment='unknown',definition_completeness={},context_checks=[])
    scope.preserve(check,dict(applicability_receipts=[dict(unit_id='excluded',output_hash='h')]),{})
    assert check['judgment']=='unknown'  # Excluding every proposal does not establish a claim.


def test_candidate_and_requirement_applicability_cache_are_separate_readonly_and_current(monkeypatch):
    from app.knowledge import discovery_scope as scope
    req,run,result,by,cm=requirement_fixture();run['id']='run'
    candidate=result['observations'][0]
    context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    identifier,key,packet,deps=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    assert len(scope.context_unit_ids(run,context,by,{'c':candidate}))==2
    need=dict(meaning='공급 조건',applies_to='관계',evidence_refs=[dict(block_id='e',span=[0,len(by['e']['text'])])],missing_source='')
    raw_unit=dict(id='context:'+key,stage='context',status='succeeded',context_candidate_ids=['c'],context_target=packet['target'],dependency_ids=deps,
        source_ref_map={'s':dict(block_id='e',span=[0,len(by['e']['text'])])},output=dict(context_needs=[need]))
    run['analysis_units']=[raw_unit]
    call_request=scope.candidate_application(run,identifier,key,packet,by)
    proposals=call_request[1]['proposals']
    output=scope.normalize_applicability(dict(decisions=[dict(meaning_key=m['meaning_key'],applicability='not_applicable',evidence_refs=[dict(block_id='e')],reason='이 유형 국소 정의 밖',remaining=[]) for m in proposals]),dict(proposals=proposals))
    app_unit=dict(id='context:'+call_request[0],stage='context',context_phase='applicability',status='succeeded',dependency_ids=deps,output=output)
    run['analysis_units'].append(app_unit)
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by))
    monkeypatch.setattr(a2,'call',lambda *_:pytest.fail('동일 성공 영수증 재호출 또는 읽기 중 모델 호출'))
    read=scope.attach_saved(run,context,by,{'c':candidate})
    assert not read['source_requirements']['c'] and not read['applicability_pending']
    assert scope.discover(None,run,context,by,{'c':candidate})==read
    critic=dict(context_candidate_ids=['c'],context_dependency_ids=[raw_unit['id'],app_unit['id']],output=dict(
        applicability_receipts=read['applicability_receipts'],review_coverage=dict(valid_candidate_ids=['c'])))
    assert scope.current_applicability_ids(run,critic,by,{'c':candidate},set(by))==['c']
    assert scope.current_applicability_ids(run,critic,by,{'c':candidate},set())==[]
    changed=deepcopy(app_unit['output']);app_unit['output']['decisions'][0]['reason']='변경된 적용성 판정'
    assert scope.current_applicability_ids(run,critic,by,{'c':candidate},set(by))==[]
    app_unit['output']=changed
    app_unit.update(status='failed',attempts=[dict(outcome='error')])
    assert scope.apply_context(None,run,call_request,by)[2]  # No automatic retry of the same failure.
    app_unit.update(status='succeeded',attempts=[])
    ctx,_,_=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    assert ctx['source_context_proposals']==proposals and ctx['applicability_pending']
    whole=scope.requirement_application(run,ctx,by)
    assert whole[0]!=call_request[0]  # The candidate's exclusion cannot remove the CQ's condition.
    _,prompt=a2.make_prompt(run,'context',whole[1],whole[2],{})
    assert candidate['definition'] not in prompt and 'supported' not in prompt.split('INPUT:',1)[1]
    old=call_request[0];candidate['definition']='수정된 정의'
    assert scope.candidate_application(run,identifier,key,packet,by)[0]==old
    run['cqs'][0]['question']='변경된 업무 범위'
    assert scope.candidate_application(run,identifier,key,packet,by)[0]!=old
    run['cqs'][0]['question']='선정 조건은?';raw_unit['output']['context_needs'][0]['meaning']='새 발견'
    assert scope.candidate_application(run,identifier,key,packet,by)[0]!=old



def test_invalid_latest_applicability_receipt_never_falls_back_to_old_supported():
    from app.knowledge import discovery_review as reviews
    candidate=dict(id='c',definition='변하지 않은 정의')
    coverage=dict(candidate_hashes={'c':reviews.fingerprint(candidate)},valid_candidate_ids=['c'])
    old=dict(review_coverage=coverage)
    latest=dict(review_coverage=coverage,applicability_current_ids=[])
    assert reviews.latest_by_candidate([old,latest],{'c':candidate})=={}
    assert reviews.valid_ids(latest,{'c':candidate})==set()


def test_requirement_reservation_matches_failed_without_attempts_skip_but_not_context(monkeypatch):
    from app.knowledge import discovery_scope as scope
    req,run,result,by,cm=requirement_fixture();run['result']=result
    context,_,supplied=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    key='requirements:cq:q:'+req.fingerprint(context,supplied)[:20]
    run['analysis_units']=[dict(id=key,stage='requirements',status='failed',attempts=[]),
        dict(id='context:apply:pending',stage='context',context_phase='applicability',status='failed',attempts=[])]
    monkeypatch.setattr(a2,'finish',lambda *_:None)
    monkeypatch.setattr(scope,'requirement_application',lambda *_:('apply:pending',{},['e']))
    context,_,supplied=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    run['analysis_units'][0]['id']='requirements:cq:q:'+req.fingerprint(context,supplied)[:20]
    assert req.pending_calls(run,by)=={'context:apply:pending':'context'}


def test_failed_discovery_does_not_reserve_an_unreachable_applicability_child():
    from app.knowledge import discovery_scope as scope
    _,run,result,by,_=requirement_fixture();candidate=result['observations'][0]
    context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    _,key,_,_=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    uid='context:'+key
    run['analysis_units']=[dict(id=uid,stage='context',status='failed',attempts=[dict(outcome='error')])]
    assert scope.context_unit_ids(run,context,by,{'c':candidate})==[uid]
    assert run['analysis_units'][0]['status']=='failed'


@pytest.mark.parametrize('invalid',[None,'quote','source_version_id','span'])
def test_type_application_adds_only_verified_source_address_without_rediscovery(invalid):
    import json
    from app.knowledge import discovery_scope as scope
    _,run,result,by,_=requirement_fixture();run['id']='local-type'
    candidate=deepcopy(result['observations'][0]);candidate.update(definition_mode='source_extract',cq_ids=[])
    b=by['e'];ref=dict(block_id='e',source_version_id=b['source_version_id'],parse_run_id=b['parse_run_id'],span=[0,2],quote=b['text'][:2])
    if invalid:ref[invalid]={'quote':'wrong','source_version_id':'old','span':[0,99999]}[invalid]
    context=dict(blocks=[dict(ref='e',text=b['text'])],review_target_ids=['c'])
    baseline=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    candidate['definition_evidence_refs']=[ref]
    _,key,packet,deps=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    assert key==baseline[1]  # Broad independent source proposals remain reusable.
    run['analysis_units']=[dict(id='context:'+key,stage='context',status='succeeded',output=dict(context_needs=[]))]
    before=deepcopy(packet);request=scope.candidate_application(run,'c',key,packet,by)
    sent=json.loads(a2.make_prompt(run,'context',request[1],deps,{})[1].split('\nINPUT:\n')[1])
    assert packet==before and sent['blocks'] and 'definition' not in sent['target']
    assert ('definition_source_addresses' in sent['target'])==(invalid is None)
    if invalid is None:
        assert sent['target']['definition_source_addresses']==[{k:ref[k] for k in ('block_id','source_version_id','parse_run_id','span')}]
        assert sent['target']['definition_mode']=='source_extract' and '별도 업무 규칙' in sent['target']['scope']
        old=scope.candidate_application(run,'c',key,baseline[2],by)
        assert request[0]!=old[0]  # Applicability must be recomputed for the changed question.


def test_observation_critic_receives_only_primary_linked_questions():
    import json
    run=dict(id='local',recipe=a2.recipe({}),cqs=[dict(id='q1',question='primary'),dict(id='q2',question='comparison')],
        scope_items=[dict(id='s1',description='primary scope'),dict(id='s2',description='comparison scope')])
    supplied={'c':dict(id='c',classification='type',cq_ids=[],scope_item_ids=[]),
        'other':dict(id='other',classification='type',cq_ids=['q2'],scope_item_ids=['s2'])}
    context=dict(review_focus='observations',review_target_ids=['c'],blocks=[],unapproved_observations=[supplied['c']],comparison_terms=[supplied['other']])
    def payload(stage):return json.loads(a2.make_prompt(run,stage,context,[],supplied)[1].split('\nINPUT:\n')[1])
    assert payload('critic')['cqs']==[] and payload('critic')['scope_items']==[]
    supplied['c'].update(cq_ids=['q1'],scope_item_ids=['s1'])
    assert payload('critic')['cqs']==run['cqs'][:1] and payload('critic')['scope_items']==run['scope_items'][:1]
    assert payload('requirements')['cqs']==run['cqs'] and payload('requirements')['scope_items']==run['scope_items']


@pytest.mark.parametrize('mode,shared',[('single',False),('initial',True),('multiple',True),('legacy',True),('old_inline',False)])
def test_single_binding_correction_uses_existing_inline_contract_only(mode,shared):
    from app.knowledge import discovery_design as design
    run=dict(recipe=a2.recipe({}));context=dict(binding_before={'id':'r'},design_relation_ids=['r'])
    if mode=='initial':context.pop('binding_before')
    if mode=='multiple':context['design_relation_ids'].append('r2')
    if mode=='legacy':run['recipe'].pop('builder_correction_contract')
    if mode=='old_inline':run['recipe'].pop('builder_declaration_contract')
    assert design.shared_types(run,context) is shared


@pytest.mark.parametrize('thinking',[False,True])
def test_native_think_option_reaches_existing_calls_and_separates_source_cache(monkeypatch,thinking):
    import asyncio
    from app.knowledge import discovery_scope as scope
    sent=[]
    async def capture(self,prompt,**kwargs):sent.append(kwargs);return {}
    monkeypatch.setattr(a2.GenerationService,'call_ollama',capture)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_THINK',thinking)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_NUM_CTX',65536)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_INPUT_CHARS',40000)
    _,run,result,by,_=requirement_fixture()
    assert run['recipe']['think'] is thinking
    assert run['recipe']['num_ctx']==65536 and run['recipe']['input_chars']==40000
    candidate=result['observations'][0];context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    key=scope.discovery_requests(run,context,by,{'c':candidate})[0][1]
    legacy=deepcopy(run);legacy['recipe'].pop('think')
    old=scope.discovery_requests(legacy,context,by,{'c':candidate})[0][1]
    assert (key==old) is (not thinking)
    for stage in ('context','applicability','critic','builder','requirements','binding'):
        asyncio.run(a2.model_call('input',{},stage,run,720))
        assert sent[-1]['think']==(run['recipe']['binding_think'] if stage=='binding' else thinking)
        assert sent[-1]['num_ctx']==65536
        assert sent[-1]['num_predict']==(8192 if stage in {'binding','critic','requirements'} or stage in {'builder','applicability'} and thinking else 4096)
    from app.knowledge import discovery_synthesis as synthesis
    application=dict(context_phase='applicability',target=dict(label='역할',scope_kind='candidate',cq_ids=[],scope_item_ids=[]),blocks=[],proposals=[])
    size=synthesis.input_size(run,'context',application,[],{})
    assert size['input_bytes_limit']==65536-(8192 if thinking else 4096)
    app_key=scope.applicability_request(run,application['target'],[],[],{},[])[0]
    previous=deepcopy(run);previous['recipe'].pop('applicability_num_predict')
    assert scope.discovery_requests(previous,context,by,{'c':candidate})[0][1]==key
    assert (scope.applicability_request(previous,application['target'],[],[],{},[])[0]==app_key) is (not thinking)
    run['recipe']['binding_think']=True
    asyncio.run(a2.model_call('input',{},'binding',run,720))
    assert sent[-1]['think'] is True


def test_cancellation_during_context_discovery_prevents_next_critic_call(monkeypatch):
    from app.knowledge import discovery_scope as scope
    run=dict(id='cancel-discovery',recipe=a2.recipe({}),cqs=[],scope_items=[],analysis_units=[],metrics=dict(llm_calls=0))
    cancelled=[False]
    monkeypatch.setattr(a2,'cancelled',lambda *_:cancelled[0])
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set())
    monkeypatch.setattr(a2,'make_prompt',lambda *_:({},'input'))
    monkeypatch.setattr(scope,'attach_saved',lambda _,context,*__:context)
    def discover(_,current,context,*rest):
        cancelled[0]=True
        return context
    monkeypatch.setattr(scope,'discover',discover)
    monkeypatch.setattr(a2,'model_identity',lambda *_:pytest.fail('취소 후 Critic 준비/호출 금지'))
    assert a2.call(None,run,'critic','after-discovery',dict(blocks=[],review_target_ids=[]),[],{},{}) is None
    assert run['metrics']['llm_calls']==0 and run['analysis_units'][0]['attempts']==[]


@pytest.mark.parametrize('state',['failed','cancelled','missing','succeeded','legacy'])
def test_failed_required_applicability_skips_critic_http_without_semantic_verdict(monkeypatch,state):
    from app.knowledge import discovery_scope as scope
    dependency=dict(id='context:apply:required',stage='context',status='failed' if state in {'legacy','missing'} else state)
    run=dict(id='failed-application',recipe=a2.recipe({}),cqs=[],scope_items=[],analysis_units=[] if state=='missing' else [dependency],metrics=dict(llm_calls=0))
    if state=='legacy':run['recipe'].pop('context_applicability_contract')
    monkeypatch.setattr(a2,'recipe',lambda *_:run['recipe'])
    monkeypatch.setattr(a2,'save',lambda *_:None)
    monkeypatch.setattr(a2,'cancelled',lambda *_:False)
    monkeypatch.setattr(a2,'allowed_ids',lambda *_:set())
    monkeypatch.setattr(a2,'make_prompt',lambda *_:({},'input'))
    monkeypatch.setattr(scope,'attach_saved',lambda _,context,*__:context)
    monkeypatch.setattr(scope,'discover',lambda _,current,context,*__:context)
    monkeypatch.setattr(scope,'context_unit_ids',lambda *_:[dependency['id']])
    class ReadyForModel(BaseException):pass
    def ready(*_):raise ReadyForModel()
    monkeypatch.setattr(a2,'model_identity',ready)
    args=(None,run,'critic','after-application',dict(blocks=[],review_target_ids=[]),[],{},{})
    if state in {'failed','cancelled','missing'}:
        assert a2.call(*args) is None
        unit=run['analysis_units'][-1]
        assert unit['status']=='failed' and '필수 문맥 준비 미완료' in unit['error'] and 'output' not in unit
        assert run['metrics']['llm_calls']==0 and unit['attempts']==[]
    else:
        with pytest.raises(ReadyForModel):a2.call(*args)


def test_role_declaration_purpose_only_enters_applicability_not_independent_source_discovery():
    import json
    from app.knowledge import discovery_scope as scope
    _,run,result,by,_=requirement_fixture()
    source=dict(id='r',subject='담당자',predicate='선정한다',object='대상',conditions='해당 조건',time='')
    candidate=dict(result['observations'][0],label='대상',definition_mode='source_role',
        role_basis=dict(relation_ref='r',endpoint='object'),role_source=source,definition='UNTRUSTED_GENERATED_EFFECT')
    context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    _,key,packet,deps=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    declaration=packet['candidate_application_target']['declaration_scope']
    assert declaration['role_basis']==candidate['role_basis'] and '선정 자격' in str(declaration['does_not_establish'])
    original_prompt=a2.make_prompt(run,'context',packet,deps,{})[1]
    assert 'declaration_scope' not in original_prompt and 'UNTRUSTED_GENERATED_EFFECT' not in original_prompt
    run['analysis_units'].append(dict(id='context:'+key,stage='context',status='succeeded',output=dict(context_needs=[])))
    _,application,app_deps=scope.candidate_application(run,'c',key,packet,by)
    prompt=a2.make_prompt(run,'context',application,app_deps,{})[1]
    wire=json.loads(prompt.split('\nINPUT:\n')[1])
    assert wire['target']['definition_mode']=='source_role' and wire['target']['declaration_scope']==declaration
    assert wire['target']['source_role']['conditions']==source['conditions']
    assert 'UNTRUSTED_GENERATED_EFFECT' not in prompt
    altered=deepcopy(candidate);altered['definition']='DIFFERENT_GENERATED_CLAIM'
    _,same_key,same_packet,_=scope.discovery_requests(run,context,by,{'c':altered})[0]
    assert same_key==key and same_packet['candidate_application_target']==packet['candidate_application_target']
    invalid=deepcopy(candidate);invalid['role_basis']['endpoint']='outside'
    assert 'candidate_application_target' not in scope.discovery_requests(run,context,by,{'c':invalid})[0][2]


def test_remaining_contract_reaches_model_prompt_and_only_changes_applicability_cache(monkeypatch):
    from app.knowledge import discovery_scope as scope
    _,run,result,by,_=requirement_fixture()
    candidate=result['observations'][0];context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    _,key,packet,deps=scope.discovery_requests(run,context,by,{'c':candidate})[0]
    source_prompt=a2.make_prompt(run,'context',packet,deps,{})[1]
    source_schema=a2.models.ContextDiscovery.model_json_schema()
    run['analysis_units'].append(dict(id='context:'+key,stage='context',status='succeeded',output=dict(context_needs=[])))
    app_key,application,app_deps=scope.candidate_application(run,'c',key,packet,by)
    rule=a2.models.APPLICABILITY_REMAINING_RULE
    assert rule in a2.make_prompt(run,'context',application,app_deps,{})[1]
    assert rule==a2.models.ContextApplicability.model_json_schema()['$defs']['ContextApplicabilityDecision']['properties']['remaining']['description']
    assert rule not in source_prompt and rule not in str(source_schema)
    monkeypatch.setitem(a2.models.PROMPTS,'context_applicability',a2.models.PROMPTS['context_applicability'].replace(rule,''))
    assert scope.candidate_application(run,'c',key,packet,by)[0]!=app_key
    assert scope.discovery_requests(run,context,by,{'c':candidate})[0][1]==key
    assert a2.make_prompt(run,'context',packet,deps,{})[1]==source_prompt
    assert a2.models.ContextDiscovery.model_json_schema()==source_schema


def test_requirements_capacity_changes_only_its_http_and_preserves_context_cache(monkeypatch):
    import asyncio
    from app.knowledge import discovery_scope as scope, discovery_synthesis as synthesis
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_NUM_CTX',65536)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX',0)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT',8192)
    _,prior,result,by,_=requirement_fixture()
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX',81920)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT',16384)
    run=deepcopy(prior);run['recipe']=a2.recipe(prior['recipe']['budgets'])
    candidate=result['observations'][0];context=dict(blocks=[dict(ref='e',text=by['e']['text'])],review_target_ids=['c'])
    assert scope.discovery_requests(run,context,by,{'c':candidate})[0][1]==scope.discovery_requests(prior,context,by,{'c':candidate})[0][1]
    target=dict(label='대상',scope_kind='candidate',cq_ids=[],scope_item_ids=[])
    assert scope.applicability_request(run,target,[],[],{},[])[0]==scope.applicability_request(prior,target,[],[],{},[])[0]
    sent=[]
    async def capture(self,prompt,**kwargs):sent.append(kwargs);return {}
    monkeypatch.setattr(a2.GenerationService,'call_ollama',capture)
    for stage in ('requirements','context','applicability','critic','builder','binding'):
        asyncio.run(a2.model_call('input',{},stage,run,1800))
        assert sent[-1]['num_ctx']==(81920 if stage=='requirements' else 65536)
        assert sent[-1]['num_predict']==(16384 if stage=='requirements' else a2.output_tokens(prior['recipe'],stage))
    schema_bytes=synthesis.input_size(run,'requirements',{},[],{})['schema_bytes']
    monkeypatch.setattr(a2,'make_prompt',lambda *_: ({},'x'*(60000-schema_bytes)))
    run['recipe']['input_chars']=70000
    assert synthesis.fits(run,'requirements',{},[],{})
    assert not synthesis.fits(run,'critic',{},[],{})
    legacy=deepcopy(run['recipe']);legacy.pop('requirements_num_ctx')
    assert a2.context_tokens(legacy,'requirements')==65536


def test_requirements_context_support_is_checked_only_on_review_model(monkeypatch):
    from types import SimpleNamespace
    current=a2.recipe({});current.update(num_ctx=65536,requirements_num_ctx=81920,models=dict(draft='draft',review='review'))
    lengths=dict(draft=65536,review=81920)
    def response(value):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:value)
    class Client:
        def __init__(self,**_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def get(self,url):return response(dict(models=[dict(name=k,digest=k) for k in lengths]))
        def post(self,url,json):return response(dict(model_info={'model.context_length':lengths[json['model']]}))
    monkeypatch.setattr(a2.httpx,'Client',Client)
    assert a2.model_identity(current)['draft']['context_length']==65536
    lengths['review']=65536
    with pytest.raises(ValueError,match='컨텍스트'):a2.model_identity(current)
    lengths.update(draft=65535,review=81920)
    with pytest.raises(ValueError,match='컨텍스트'):a2.model_identity(current)


@pytest.mark.parametrize('actual_tokens',[65536,65537])
@pytest.mark.parametrize('overflow',[False,True])
def test_requirement_call_uses_selected_context_for_preflight_and_actual_tokens(monkeypatch,actual_tokens,overflow):
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_NUM_CTX',65536)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_INPUT_CHARS',70000)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX',81920)
    monkeypatch.setattr(a2.settings,'KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT',16384)
    req,run,result,by,cm=requirement_fixture()
    run.update(id='capacity',status='running',model_identity={},metrics=dict(llm_calls=0,model_total_s=0))
    context,deps,supplied=req.packet(run,result,'cq',run['cqs'][0],by,cm)
    original=a2.make_prompt;called=[]
    size=a2.input_size(run,'requirements',context,deps,supplied)
    prompt_bytes=size['input_bytes_limit']-size['schema_bytes']+int(overflow)
    frozen=deepcopy(context)
    def padded(*args,**kwargs):
        mapping,prompt=original(*args,**kwargs)
        return mapping,prompt+' '*(prompt_bytes-len(prompt.encode()))
    async def capture(*_):
        called.append(True)
        # The intentionally empty record isolates the capacity check before schema validation.
        return dict(text='{}',done=True,done_reason='stop',prompt_eval_count=actual_tokens)
    monkeypatch.setattr(a2,'make_prompt',padded);monkeypatch.setattr(a2,'model_call',capture)
    monkeypatch.setattr(a2,'model_identity',lambda _:{});monkeypatch.setattr(a2,'save',lambda *_:None)
    monkeypatch.setattr(a2,'cancelled',lambda *_:False);monkeypatch.setattr(a2,'allowed_ids',lambda *_:set(by))
    monkeypatch.setattr(a2,'recipe',lambda _:deepcopy(run['recipe']))
    from app.knowledge import discovery_synthesis as synthesis
    assert synthesis.fits(run,'requirements',context,deps,supplied) is (not overflow)
    assert context==frozen
    a2.call(None,run,'requirements','capacity',context,deps,by,supplied)
    unit=run['analysis_units'][-1]
    if overflow:
        assert not called and not unit['attempts'] and run['metrics']['llm_calls']==0
        assert '응답 스키마' in unit['error']
        return
    assert called==[True],unit
    assert unit['schema_bytes']==size['schema_bytes']
    assert unit['request_input_bytes']==size['input_bytes_limit']
    assert ('실제 입력 토큰/컨텍스트 확인 실패' in unit['error']) is (actual_tokens==65537)
    assert '보수적 토큰 상한' not in unit['error']

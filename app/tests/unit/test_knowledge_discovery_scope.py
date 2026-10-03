"""Scope contracts: structural checks do not certify model meaning judgments."""
from copy import deepcopy
import pytest
from app.knowledge import discovery_scope as scope, discovery_review as reviews, discovery_analysis as a2
from app.knowledge import ontology_canonical as canonical
from app.tests.unit.test_knowledge_discovery_claims import authored, claim_record


def checked(verdict='supported', missing=False):
    candidate,_,block,context=authored();candidate['id']='c'
    raw=claim_record(candidate)
    raw['definition_completeness']['required_meanings']=[dict(meaning='조건 A의 선정 역할',applies_to='이 명제의 대상 역할',
        source_refs=[] if missing else ['s1'],missing_source='외부 별표 상세 미제공' if missing else '',
        locations=[dict(candidate_ref='c',field='definition',quote=candidate['definition'])] if verdict=='supported' else [],
        judgment=verdict,reason='실제 적용 범위 대조')]
    context.update(review_target_ids=['c'])
    run=dict(recipe=dict(review_contract='checks-v1',claim_review_contract='claims-v1',context_contract='scope-v1'),cqs=[dict(id='cq1')],scope_items=[])
    output=dict(issues=[],observation_checks=[raw],relation_checks=[],hierarchy_checks=[],missing_meanings=[],gaps=[],actions=[],needs_revision=False)
    return reviews.normalize(output,run,['e'],{'e':block},{'c':candidate},context,None,lambda _:None,True),candidate


@pytest.mark.parametrize('verdict,missing',[('supported',False),('refuted',False),('unknown',True)])
def test_required_meaning_aggregate_and_external_unknown(verdict,missing):
    output,_=checked(verdict,missing)
    assert not output['record_errors']
    assert output['observation_checks'][0]['judgment']==verdict
    assert output['needs_revision']==(verdict=='refuted')


def test_selected_hierarchy_and_parent_changes_invalidate_same_text():
    child=dict(id='c',definition='공공임대의 공급 방식',classification='type')
    parent=dict(id='p',definition='재정 지원 범위',classification='type')
    h=dict(id='h',child_ref='c',parent_ref='p',relation='is_a')
    supplied={c['id']:c for c in (child,parent,h)}
    meaning=dict(locations=[dict(candidate_ref='h',field='structure',quote='')],judgment='supported',evidence_refs=[dict(block_id='e')])
    hashes=scope.locations(meaning,supplied)
    assert set(hashes)=={'h','c','p'}
    review=dict(review_dependency_contract='selected-types-v1',binding_dependency_hashes={'c':{}},meaning_dependency_hashes={'c':hashes})
    assert reviews.dependencies_current(review,'c',supplied)
    parent['definition']='다른 범위'
    assert not reviews.dependencies_current(review,'c',supplied)


def test_long_block_does_not_expand_small_quote_to_full_text():
    text=''.join(f'{n}. 업무{n}의 정의입니다. '+('설명 '*90)+'\n' for n in range(1,80))
    b=dict(id='e',text=text,source_version_id='v',parse_run_id='p',locator=dict(format='txt'))
    context=dict(blocks=[dict(ref='e',text=text[:30],span=[0,30])])
    expanded,deps=scope.source_context(context,['e'],{'e':b})
    assert sum(len(v['text']) for v in a2.segments.originals(expanded))<len(text)
    assert expanded['tool_originals'] and deps==['e']
    assert scope.source_context(expanded,deps,{'e':b})==(expanded,deps)


def test_unstructured_long_context_records_gap_instead_of_truncating():
    b=dict(id='e',text='가'*30000,source_version_id='v',parse_run_id='p',locator={})
    expanded,_=scope.source_context(dict(blocks=[dict(ref='e',text='가'*10,span=[0,10])]),['e'],{'e':b})
    assert not expanded['tool_originals'] and expanded['context_gaps']


def test_scope_metadata_currentness_after_canonical_dependency_change():
    parent=dict(id='p',name='상위',definition='범위 A',qualifiers={},evidence_refs=[])
    origin=dict(scope_dependencies={'p':canonical.scope_hash(parent)})
    assert canonical.scope_current(origin,{'p':parent})
    assert not canonical.scope_current(origin,{'p':dict(parent,definition='범위 B')})
    assert not canonical.scope_current(origin,{'p':dict(parent,deprecated=True)})


@pytest.mark.parametrize('status,judgment',[('maintained','supported'),('corrected','supported'),('lost','refuted'),('unknown','unknown')])
def test_before_after_meaning_preservation(status,judgment):
    candidate=dict(id='c',definition='선정 대상',conditions='조건 A',revision_basis_hash='current')
    item=dict(meaning_key='m',meaning='조건 A에서 선정되는 역할',applies_to='출처 역할',status=status,
        source_refs=[],evidence_refs=[dict(block_id='e')] if status!='unknown' else [],missing_source='상세 미제공' if status=='unknown' else '',
        reason='원문에 따른 의미 대조',locations=[dict(candidate_ref='c',field='conditions',quote='조건 A')] if status in {'maintained','corrected'} else [])
    check=dict(candidate_ref='c',judgment='supported',preservation_checks=[item])
    context=dict(revision_comparisons={'c':dict(expected_meanings=[dict(meaning_key='m')])})
    scope.preserve(check,context,{'c':candidate})
    assert check['judgment']==judgment
    assert check['correction_complete']==(judgment=='supported')
    check['preservation_checks']=[]
    with pytest.raises(ValueError,match='누락'): scope.preserve(check,context,{'c':candidate})


def test_changed_before_or_preservation_basis_invalidates_revision_fingerprint():
    from app.knowledge import discovery_candidates as ids
    h=dict(before=dict(id='c',definition='정상 역할과 오류 효과'),after=dict(id='c',definition='정상 역할'),preservation_basis=[dict(meaning='정상 역할')])
    original=ids.history_view({},h)
    h['preservation_basis'][0]['meaning']='다른 역할'
    assert reviews.fingerprint(original)!=reviews.fingerprint(ids.history_view({},h))


def test_grounded_correction_can_remove_a_previously_supported_error():
    candidate=dict(id='c',definition='선정 역할',revision_basis_hash='basis')
    check=dict(candidate_ref='c',judgment='supported',preservation_checks=[dict(meaning_key='m',status='corrected',locations=[],
        evidence_refs=[dict(block_id='e')],reason='선정이 자격 부여를 뜻한다는 이전 판단 오류를 원문으로 정정')])
    scope.preserve(check,dict(revision_comparisons={'c':dict(expected_meanings=[dict(meaning_key='m')])}),{'c':candidate})
    assert check['correction_complete']


def requirement_fixture():
    from app.knowledge import discovery_requirements as req
    b=dict(id='e',text='주체는 조건 A에서 대상을 선정한다.',source_version_id='v',parse_run_id='p',locator=dict(format='txt'),source_group='s',file_id='f',title='자료',role='current')
    c=dict(id='c',label='대상',classification='type',definition='선정 대상',cq_ids=['q'],scope_item_ids=[],evidence_ids=['e'],evidence_refs=[],review_status='unreviewed')
    group=dict(id='g',block_ids=['e'],segments=[],roles=['concept'],round=0)
    recovery=dict(id='r',cause='extraction_missing',role='concept',target=[['e',[0,len(b['text'])]]],validation=[],
        meanings=[dict(meaning='조건 A',cq_ids=['q'],scope_item_ids=[])],evidence_refs=[])
    run=dict(recipe=a2.recipe(dict(model_calls=40,model_seconds=12000,additional_rounds=1,revisions=1,searches=0)),
        cqs=[dict(id='q',question='선정 조건은?')],scope_items=[],frontier=[group],base_candidates=[],analysis_units=[],recovery_requests=[recovery])
    result=dict(observations=[c],relations=[],taxonomy=[])
    by_id={'e':b};cm=a2.profile.contexts([b])
    return req,run,result,by_id,cm


def test_shared_critic_recovery_and_scope_metadata_change_fingerprint():
    req,run,result,by_id,cm=requirement_fixture()
    ctx,_,supplied=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    assert [r['id'] for r in ctx['recovery_targets']]==['r'] # no requirement_key on Critic request
    original=req.fingerprint(ctx,supplied)
    run['recovery_requests'][0]['meanings'].append(dict(meaning='조건 B',cq_ids=['q']))
    changed,_,_=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    assert req.fingerprint(changed,supplied)!=original
    ctx['blocks'][0]['analysis_target']=False
    assert req.fingerprint(ctx,supplied)!=original


def test_requirement_splits_existing_working_units_without_full_source_rejoin(monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    req,run,result,by_id,cm=requirement_fixture()
    second=dict(by_id['e'],id='f',text='다른 자료의 조건 B',source_group='other')
    by_id['f']=second;cm=a2.profile.contexts(list(by_id.values()))
    run['frontier'].append(dict(run['frontier'][0],id='g2',block_ids=['f']))
    monkeypatch.setattr(synthesis,'fits',lambda run,stage,ctx,*_:len(ctx['blocks'])==1)
    packets=req.packets(run,result,'cq',run['cqs'][0],by_id,cm)
    assert len(packets)==2
    assert [{b['ref'] for b in ctx['blocks']} for ctx,_,_ in packets]==[{'e'},{'f'}]
    assert all(not ctx['requirement_scope']['complete_input'] for ctx,_,_ in packets)


def test_requirement_resolution_requires_every_current_part_and_same_meaning(monkeypatch):
    req,run,result,by_id,cm=requirement_fixture()
    ctx,deps,supplied=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    other=deepcopy(ctx);other['requirement_scope']['complete_input']=False
    parts=[(ctx,deps,supplied),(other,deps,supplied)]
    monkeypatch.setattr(req,'packets',lambda *_:parts)
    for n,(context,_,_) in enumerate(parts):
        run['analysis_units'].append(dict(id=str(n),stage='requirements',status='succeeded',dependency_ids=deps,
            output=dict(assessment_fingerprint=req.fingerprint(context,supplied),judgment='supported' if n==0 else 'refuted',
                reason='실제 의미 대조',meanings=[dict(judgment='supported' if n==0 else 'refuted',recovery_ids=['r'])],resolved_recovery_ids=['r'] if n==0 else [])))
    assessment=req.saved(run,result,by_id,set(by_id))[0]
    assert assessment['judgment']=='refuted' and not assessment['resolved_recovery_ids']
    run['analysis_units'].pop()
    assert not req.saved(run,result,by_id,set(by_id))[0]['resolved_recovery_ids']
    run['analysis_units'][0]['output']['resolved_recovery_ids']=[]
    run['recovery_requests'][0]['meanings'].append(dict(meaning='새 의미',cq_ids=['q']))
    changed,_,_=req.packet(run,result,'cq',run['cqs'][0],by_id,cm)
    parts[:]=[(changed,deps,supplied)]
    assert req.saved(run,result,by_id,set(by_id))[0]['judgment']=='unknown'


def test_partitioned_recovery_only_reviews_its_owned_source(monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    req,run,result,by_id,cm=requirement_fixture()
    by_id['f']=dict(by_id['e'],id='f',text='조건 B의 대상',source_group='other')
    cm=a2.profile.contexts(list(by_id.values()))
    run['frontier'].append(dict(run['frontier'][0],id='g2',block_ids=['f']))
    run['recovery_requests'].append(dict(deepcopy(run['recovery_requests'][0]),id='r2',target=[['f',[0,len(by_id['f']['text'])]]]))
    monkeypatch.setattr(synthesis,'fits',lambda run,stage,ctx,*_:len(ctx['blocks'])==1)
    packets=req.packets(run,result,'cq',run['cqs'][0],by_id,cm)
    assert [[r['id'] for r in ctx['recovery_targets']] for ctx,_,_ in packets]==[['r'],['r2']]
    for n,(ctx,deps,supplied) in enumerate(packets):
        rid=ctx['recovery_targets'][0]['id']
        run['analysis_units'].append(dict(id=str(n),stage='requirements',status='succeeded',dependency_ids=deps,
            output=dict(assessment_fingerprint=req.fingerprint(ctx,supplied),judgment='unknown',reason='전체 결합 미확인',
                meanings=[dict(judgment='supported',recovery_ids=[rid])],resolved_recovery_ids=[rid])))
    judgment=req.saved(run,result,by_id,set(by_id))[0]
    assert judgment['judgment']=='unknown' and judgment['resolved_recovery_ids']==['r','r2']


def test_human_edit_removes_current_scope_snapshot_but_keeps_history():
    from app.knowledge import ontology_changes as changes
    row=dict(after=dict(name='대상',definition='이전 정의'),qualifiers={},origin=dict(definition_mode='synthesis',
        scope_assessment=dict(judgment='supported'),scope_dependencies={'p':'hash'},scope_current=True,scope_context=[dict(id='p',definition='이전 상위')]))
    changes.record_definition_edit(row,dict(after=dict(name='대상',definition='사람 수정 정의')))
    assert not any(k in row['origin'] for k in ('scope_assessment','scope_dependencies','scope_current','scope_context'))
    assert row['origin']['generation_origin']['scope_context'][0]['definition']=='이전 상위'


from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare
from app.tests.unit.test_knowledge_discovery_analysis import model, request, done


def test_finish_counts_final_requirement_resolution_without_model_calls(service,model,monkeypatch):
    from app.knowledge import discovery_requirements as req
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    run['recipe']['context_contract']='scope-v1'
    run['recovery_requests']=[dict(id='missing',cause='extraction_missing',role='concept',status='unresolved',validation=[],meanings=[])]
    # This test isolates finish aggregation; saved semantic judgment is a contract double.
    monkeypatch.setattr(req,'saved',lambda *_:[dict(requirement_id='cq1',requirement_kind='cq',judgment='supported',
        reason='현재 저장 판정 대역',meanings=[dict(judgment='supported',recovery_ids=['missing'])],resolved_recovery_ids=['missing'])])
    def forbidden(*_,**__): raise AssertionError('finish must not call a model')
    monkeypatch.setattr(a2,'model_call',forbidden)
    blocks=a2.load_blocks(service,run)
    a2.finish(run,blocks,{b['id'] for b in blocks})
    assert run['recovery_requests'][0]['semantic_status']=='supported'
    assert run['result']['unresolved_recovery_requests']==[]
    assert run['metrics']['recovery_remaining_by_cause']=={}


@pytest.mark.parametrize('spare_seconds',[10,2000])
def test_review_consumption_preserves_requirement_calls_under_budget_pressure(service,model,monkeypatch,spare_seconds):
    import json
    from app.knowledge import discovery_synthesis as synthesis
    from app.tests.unit.test_knowledge_discovery_claims import SCOPED_RECIPE
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    candidate=run['result']['observations'][0]
    ctx,deps,supplied=synthesis.context_for([candidate],by_id,a2.profile.contexts(blocks))
    ctx.update(review_target_ids=[candidate['id']],taxonomy=dict(hierarchies=[]))
    monkeypatch.setattr(a2,'recipe',SCOPED_RECIPE)
    run['recipe']=a2.recipe(dict(model_calls=2,model_seconds=2000,additional_rounds=0,revisions=0,searches=0))
    run['recipe']['budgets']['model_seconds']=run['recipe']['call_timeout']+spare_seconds
    run['model_identity']=a2.model_identity(run['recipe'])
    run.update(analysis_units=[],metrics=dict(llm_calls=0,model_total_s=0,searches=0),review_reservation=dict(requirement_calls=1))
    called=[]
    async def generated(prompt,schema,stage,run,timeout):
        called.append(stage)
        if stage=='critic':
            assert timeout<=spare_seconds
            raise ValueError('예산 대역: 후보 검수 미완료')
        output=dict(requirement_id='cq1',reason='추가 자료 필요',meanings=[dict(meaning='자료가 필요한 역할',applies_to='질문',
            source_refs=[],missing_source='다른 조문의 정의',locations=[],judgment='unknown',reason='본문 미제공',
            cause='source_absent',role='concept',candidate_ref='',recovery_ids=[])])
        return dict(text=json.dumps(output,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=30)
    monkeypatch.setattr(a2,'model_call',generated)
    assert a2.call(service,run,'critic','one',ctx,deps,by_id,supplied) is None
    assert a2.call(service,run,'critic','two',ctx,deps,by_id,supplied) is None
    assert called==['critic']
    context=dict(blocks=ctx['blocks'],requirement=dict(id='cq1',kind='cq',question='업무 범위?'),
        requirement_scope=dict(complete_input=True,omitted_group_ids=[]),recovery_targets=[])
    result=a2.call(service,run,'requirements','q',context,deps,by_id,supplied)
    assert result['judgment']=='unknown'
    assert called==['critic','requirements'] and run['metrics']['llm_calls']==2
    assert not run['analysis_units'][1]['attempts'] and '요구' in run['analysis_units'][1]['error']

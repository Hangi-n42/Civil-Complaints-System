"""Authored-v2 boundaries; model doubles test contracts, not semantic accuracy."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import discovery_analysis as a2, discovery_design as design, discovery_claims as claims
from app.knowledge import discovery_review as reviews, ontology_changes as changes, ontology_canonical as canonical
from app.tests.unit.test_knowledge_discovery_analysis import done, request, response, source_response, model
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare
from app.tests.unit.test_knowledge_discovery_roles import declaration_fixture
from app.tests.unit.test_knowledge_ontology_changes import listing, decide

SCOPED_RECIPE=a2.recipe
def CURRENT_RECIPE(budgets):
    value=SCOPED_RECIPE(budgets)
    value.pop('context_contract',None)
    value.pop('source_context_contract',None)
    return value


def authored(mode='synthesis'):
    row,source,block,context=declaration_fixture()
    row.pop('role_basis')
    row.update(definition_mode=mode,label='대상 X',definition='조건 A에서 선정되는 대상',
        conditions='조건 A',exceptions='B 제외',time='',design_reason='원문 역할을 일반 업무 유형으로 구분')
    if mode=='source_extract':
        for key in ('definition','conditions','exceptions','time'): row.pop(key,None)
        row.update(source_selection=dict(source_ref='s1',source_quote='기관은 대상 X를 선정하여야 한다.'),support_type='explicit')
    return row,source,block,context


@pytest.mark.parametrize('mode',['source_extract','synthesis'])
def test_authoring_materializes_exact_source_or_explicit_design(mode):
    row,source,block,context=authored(mode)
    output=dict(observations=[a2.models.AuthoredObservation.model_validate(row).model_dump()])
    design.declarations(output,{'r':source},{'e':block},context,authored=True)
    value=output['observations'][0]
    assert value['definition_mode']==mode
    ref=value['definition_evidence_refs'][0]
    assert block['text'][slice(*ref['span'])]==ref['quote']
    assert ref['parse_run_id']=='p' and ref['source_version_id']=='v'
    if mode=='source_extract': assert value['definition']==row['source_selection']['source_quote']
    else: assert value['support_type']=='design_proposal'


@pytest.mark.parametrize('bad',['stitched','mixed','outside','mode'])
def test_source_extract_rejects_nonliteral_or_mixed_declaration(bad):
    row,source,block,context=authored('source_extract')
    if bad=='stitched': row['source_selection']['source_quote']='기관은 선정하여야 한다.'
    if bad=='mixed': row['definition']='다른 정의'
    if bad=='outside': row['source_selection']['source_ref']='not-provided'
    if bad=='mode': row['definition_mode']='synthesis'
    with pytest.raises(ValueError):
        design.declarations(dict(observations=[row]),{'r':source},{'e':block},context,authored=True)


def claim_record(candidate, refs=('s1',), verdict='supported'):
    return dict(candidate_ref=candidate['id'],reason='정의와 근거 대조',source_refs=list(refs),
        semantic_checks=dict(classification='supported',conditions='supported',exceptions='supported'),
        definition_completeness=dict(judgment='supported',reason='대상 역할과 한정 범위를 설명함'),
        claim_reviews=[dict(field=f,candidate_quote=candidate[f],claim=candidate[f],nature='factual',
            source_refs=list(refs),judgment=verdict,reason='제공 구간의 역할 및 한정 대조')
            for f in ('definition','conditions','exceptions','time') if candidate.get(f)])


@pytest.mark.parametrize('mode',['valid','refuted','unknown','omitted','wrong_quote','bad_ref','empty_claims','free_aggregate','tautology'])
def test_claim_coverage_sources_and_code_aggregate(mode):
    row,source,block,context=authored()
    row['id']='c';raw=claim_record(row)
    if mode=='refuted': raw['claim_reviews'][0]['judgment']='refuted'
    if mode=='unknown': raw=claim_record(row,refs=(),verdict='unknown')
    if mode=='omitted': raw['claim_reviews'].pop()
    if mode=='wrong_quote': raw['claim_reviews'][0]['candidate_quote']='현재 후보에 없는 표현'
    if mode=='bad_ref': raw['claim_reviews'][0]['source_refs']=['outside']
    if mode=='empty_claims': raw['claim_reviews']=[]
    if mode=='free_aggregate': raw['semantic_checks']['definition']='supported'
    if mode=='tautology': raw['definition_completeness']=dict(judgment='refuted',reason='명칭 반복으로 역할 설명 없음')
    output=a2.models.ClaimCritique.model_validate(dict(issues=[],observation_checks=[raw],relation_checks=[],
        hierarchy_checks=[],missing_meanings=[],gaps=[],actions=[],needs_revision=False)).model_dump(warnings=False)
    context.update(review_target_ids=['c'])
    run=dict(recipe=dict(review_contract='checks-v1',claim_review_contract='claims-v1'),cqs=[dict(id='cq1')],scope_items=[])
    result=reviews.normalize(output,run,['e'],{'e':block},{'c':row},context,None,lambda _:None,True)
    if mode in {'omitted','wrong_quote','bad_ref','empty_claims','free_aggregate'}:
        assert result['review_coverage']['pending_candidate_ids']==['c']
        assert not result['observation_checks'] and not result['issues']
    else:
        check=result['observation_checks'][0]
        assert check['judgment']==('refuted' if mode in {'refuted','tautology'} else mode if mode=='unknown' else 'supported')
        assert check['claim_reviews'][0]['candidate_span']==[0,len(row['definition'])]
        assert bool(result['issues'])==(mode in {'refuted','tautology'})
        assert claims.revision_context([check],reviews.fingerprint(row))['target_fingerprint']==reviews.fingerprint(row)


@pytest.mark.parametrize('scoped',[False,True])
@pytest.mark.parametrize('correction',[False,True])
def test_new_wire_generation_review_revision_and_human_roundtrip(service,model,monkeypatch,correction,scoped):
    monkeypatch.setattr(a2,'recipe',SCOPED_RECIPE if scoped else CURRENT_RECIPE)
    checked=[]
    async def generated(prompt,schema,stage,run,timeout):
        data=json.loads(prompt.split('\nINPUT:\n')[1])
        if stage=='requirements':
            candidate=data['unapproved_observations'][0]
            value=dict(requirement_id=data['requirement']['id'],reason='계약 대역: 실제 의미 품질 아님',meanings=[dict(meaning='업무 유형',applies_to='제공 범위',source_refs=[v['source_ref'] for v in a2.segments.originals(data)],missing_source='',locations=[dict(candidate_ref=candidate['id'],field='definition',quote=candidate['definition'])],judgment='supported',reason='대역 대조',cause='fulfilled',role='concept',candidate_ref='',recovery_ids=[r['id'] for r in data['recovery_targets']])])
            value['context_checks']=[dict(meaning_key=m['meaning_key'],meaning=m['meaning'],applies_to=m['applies_to'],source_refs=[v['source_ref'] for v in a2.segments.originals(data)],missing_source='',locations=[dict(candidate_ref=candidate['id'],field='definition',quote=candidate['definition'])],status='maintained',reason='문맥 제안 대조 계약 대역') for m in data.get('source_context_needs',[])]
        else: value=source_response(response(prompt,stage),data)
        if stage=='concept':
            for row in value['observations']:
                row.update(definition_mode='synthesis',support_type='design_proposal',design_reason='근거의 역할 통합',classification_reason='업무 유형',conditions='원문 범위',exceptions='',time='')
        if stage=='critic' and value['observation_checks']:
            candidates={c['id']:c for c in data['unapproved_observations']}
            value['observation_checks']=[claim_record(candidates[c['candidate_ref']],
                refs=[v['source_ref'] for v in a2.segments.originals(data)]) for c in value['observation_checks']]
            if correction:
                for check in value['observation_checks']:
                    c=candidates[check['candidate_ref']]
                    if c['label']=='국민임대' and c['definition_mode']=='synthesis':
                        check['claim_reviews'][0].update(judgment='refuted',reason='계약 검사에서 지정한 정의 오류')
        if stage=='revision' and correction:
            target=data['targets'][0]
            assert data['target_fingerprint'] and data['failed_claims'] and data['preserve_claims']
            assert data['failed_claims'][0]['evidence_locations']
            row={k:v for k,v in target.items() if k in a2.models.Observation.model_fields}
            for key in ('definition','conditions','exceptions','time','evidence_ids','source_quotes'): row.pop(key,None)
            selected=a2.segments.originals(data)[0]
            row.update(local_ref='o1',candidate_ref=target['id'],reason='원문 구간으로 정의 방식 전환',definition_mode='source_extract',
                support_type='explicit',design_reason='',source_refs=[selected['source_ref']],
                source_selection=dict(source_ref=selected['source_ref'],source_quote=selected['text']))
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        if scoped:
            for row in value.get('observations',[]):
                if stage in {'concept','revision'}: row['context_needs']=[]
            if stage=='critic':
                candidates={c['id']:c for c in data.get('unapproved_observations',[])+data.get('unapproved_relations',[])}
                for check in value['observation_checks']:
                    c=candidates[check['candidate_ref']]
                    check['context_checks']=[dict(meaning_key=m['meaning_key'],meaning=m['meaning'],applies_to=m['applies_to'],source_refs=[v['source_ref'] for v in a2.segments.originals(data)],missing_source='',locations=[dict(candidate_ref=c['id'],field='definition',quote=c['definition'])],status='maintained',reason='필수 의미 후속 대조 계약 대역') for m in list({m['meaning_key']:m for m in data.get('revision_comparisons',{}).get(c['id'],{}).get('required_context',[])+data.get('source_requirements',{}).get(c['id'],[])}.values())]
                    check['definition_completeness']['required_meanings']=[dict(meaning='선택 범위의 정의',applies_to='제공 원문',source_refs=check['claim_reviews'][0]['source_refs'],missing_source='',locations=[dict(candidate_ref=c['id'],field='definition',quote=c['definition'])],judgment='supported',reason='계약 대역')]
                for check in value['observation_checks']+value['relation_checks']:
                    c=candidates[check['candidate_ref']]
                    check['preservation_checks']=[dict(meaning_key=m['meaning_key'],meaning=m['meaning'],applies_to=m['applies_to'],source_refs=[v['source_ref'] for v in a2.segments.originals(data)],missing_source='',locations=[dict(candidate_ref=c['id'],field='definition' if 'definition' in c else 'predicate',quote=c.get('definition',c.get('predicate')))],status='maintained',reason='대역 검수; 실제 의미 성공 아님') for m in data.get('revision_comparisons',{}).get(c['id'],{}).get('expected_meanings',[])]
        if stage=='critic' and not data.get('relation_bindings'):

            for check in value['relation_checks']: check.pop('binding_checks',None)
        if stage=='builder': value.setdefault('observations',[])
        if stage=='relation':
            for row in value['relations']:
                row.pop('local_ref',None);row.pop('endpoint_labels',None)
            value['target_gaps']=[]
        if scoped:
            def addresses(node):
                if isinstance(node,list):
                    for v in node:addresses(v)
                elif isinstance(node,dict):
                    for location in node.get('locations',[]):location.pop('quote',None)
                    for v in node.values():addresses(v)
            addresses(value)
            for check in ([value] if stage=='requirements' else value.get('observation_checks',[])):
                for field in ('context_checks','preservation_checks'):
                    if isinstance(check.get(field),list):
                        check[field]={m['meaning_key']:{k:v for k,v in m.items() if k!='meaning_key'} for m in check[field]}
        jsonschema.validate(value,schema)
        checked.append(stage)
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    assert not run['result']['failures'],run['result']['failures']
    if scoped:
        from app.knowledge.discovery_requirements import pending_calls
        by_id={b['id']:b for b in a2.load_blocks(service,run)}
        assert not pending_calls(run,by_id)
        assert set(pending_calls(run,by_id,future=True).values())=={'context','requirements'}
    obs=next(c for c in run['result']['observations'] if c['label']=='국민임대')
    assert obs['definition_mode']==('source_extract' if correction else 'synthesis')
    if correction:
        history=run['result']['revision_history'][0]
        assert history['before']['definition_mode']=='synthesis' and history['after']['definition_mode']=='source_extract'
        assert history['before']['id']==history['after']['id']
        assert 'revision' in checked
    assert any(c.get('claim_reviews') for r in run['result']['critiques'] for c in r['observation_checks'])
    cid=changes.publish(service,run['id'])['changeset_id']
    row=next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==obs['id'])
    assert row['origin']['ai_review_current'] and row['can_accept']
    saved=decide(service,cid,[dict(candidate_id=row['id'],action='modify',patch=dict(after=dict(row['after'],definition='사람이 범위를 검토하여 수정한 정의'),unresolved_issues=[]))])
    edited=next(c for c in listing(service,cid)['candidates'] if c['id']==row['id'])
    assert edited['origin']['definition_mode']=='human_edited_unclassified'
    assert not edited['origin']['ai_review_current']
    assert edited['origin']['generation_origin']['definition_mode']==obs['definition_mode']
    with service.repository.connect() as db:
        version=service.repository.get(db,'ontology_versions',saved['reviewed_ontology_version_id'])
    reread=canonical.targets(version)[row['target_id']]
    assert reread['modeling_origin']['definition_mode']=='human_edited_unclassified'
    assert reread['modeling_origin']['observation_checks'][0]['claim_reviews']
    assert a2.base_context(dict(base_candidates=[reread]))[0]['definition_mode']=='human_edited_unclassified'
    assert {'concept','critic','builder','binding'}<=set(checked)
    if scoped:
        assert 'requirements' in checked
        assert run['result']['requirement_assessments'][0]['judgment']=='supported'
        if correction:
            assert any(c.get('preservation_checks') and c['correction_complete'] for r in run['result']['critiques'] for c in r['observation_checks'])


def test_extraction_receives_selected_type_scope_and_current_authoring_mode(monkeypatch):
    from app.knowledge import extraction
    role=dict(id='actor',kind='concept',definition='출처의 주체 역할',qualifiers=dict(scope='제공 명제 한정'),
        modeling_origin=dict(definition_mode='source_role',role_source=dict(subject='기관',predicate='선정할 수 있다',
            object='대상',conditions='남은 주택이 있을 때',time='현행',negation='affirmed',statement_type='rule')))
    edited=dict(id='tenant',kind='concept',definition='사람 수정',modeling_origin=dict(definition_mode='human_edited_unclassified',
        generation_origin=dict(definition_mode='source_extract')))
    relation=dict(id='select',kind='relation',domain_id='actor',range='tenant',definition='선정 관계',qualifiers=dict(scope='잔여 주택'))
    run=dict(frozen_blocks=[],ontology_candidates=[role,edited,relation,dict(id='unrelated',kind='concept')])
    monkeypatch.setattr(extraction.contract,'text_units',lambda *_:[])
    monkeypatch.setattr(extraction.contract,'fact_definitions',lambda *_:[relation])
    data=json.loads(extraction.prompt_for(run,{ }).split('\nINPUT:\n')[1])
    defs={d['id']:d for d in data['definitions']}
    assert set(defs)=={'actor','tenant','select'}
    assert defs['actor']['source_role_scope']['conditions']=='남은 주택이 있을 때'
    assert defs['select']['qualifiers']=={'scope':'잔여 주택'}
    assert defs['tenant']['definition_mode']=='human_edited_unclassified'
    assert 'generation_origin' not in defs['tenant']


@pytest.mark.parametrize('mode,expected',[('source_extract','explicit'),('synthesis','design_proposal')])
def test_role_revision_authoring_transition_does_not_inherit_legacy_support(mode,expected):
    row,source,block,context=authored(mode)
    original=dict(row,id='c',source_relation_ids=['r'],definition_mode='source_role',support_type='design_proposal')
    row.update(candidate_ref='c',reason='작성 방식 변경')
    output=dict(observations=[a2.models.AuthoredObservationRevision.model_validate(row).model_dump()],relations=[],hierarchies=[],deferred=[])
    design.declarations(output,{'r':source,'c':original},{'e':block},context,authored=True)
    a2.segments.restore(output,{'e':block},context['blocks'])
    run=dict(recipe=dict(definition_contract='authored-v2'),cqs=[dict(id='cq1')],scope_items=[])
    result=a2.normalize(output,'revision',run,['e'],{'e':block},{'c':original},context)
    assert result['history'][0]['after']['support_type']==expected
    assert result['history'][0]['after']['source_relation_ids']==[]
    assert result['history'][0]['before']==original


def test_same_alignment_preserves_existing_definition_provenance(service):
    from app.tests.unit.test_knowledge_ontology_changes import analysis
    run,ref=analysis(service)
    source=run['result']['observations'][0]
    source.update(definition_mode='source_extract',source_selection=dict(source_ref='s',source_quote=source['definition']))
    check=dict(candidate_ref=source['id'],judgment='supported',reason='새 표현 검토',claim_reviews=[dict(candidate_quote=source['definition'])])
    run['result']['critiques']=[dict(unit_id='critic',observation_checks=[check])]
    run['result']['alignments']=[dict(observation_ref=source['id'],target_id='old',meaning='same',reason='같은 의미',target_scope='reviewed')]
    target=dict(id='old',symbol='Old',kind='class',name=source['label'],definition='기존의 다른 표현 정의',
        qualifiers={},evidence_refs=[ref],support_type='design_proposal',modeling_origin=dict(definition_mode='synthesis',design_reason='기존 설계'))
    with service.repository.connect() as db:
        block=service.repository.get(db,'blocks',ref['block_id'])
    rows,_,_=changes._convert(run,{'old':target},{block['id']:block})
    row=rows[0]
    assert row['after']['definition']==target['definition']
    assert row['origin']['definition_mode']=='synthesis' and row['support_type']=='design_proposal'
    assert not row['origin']['ai_review_current'] and not row['origin']['observation_checks']
    assert row['origin']['proposal_observation_checks'][0]['claim_reviews'][0]['candidate_quote']==source['definition']
    assert row['origin']['proposal_generation_origin']['definition_mode']=='source_extract'
    current=canonical.project(None,rows)['old']
    assert current['modeling_origin']['definition_mode']=='synthesis'
    assert not current['modeling_origin']['ai_review_current']

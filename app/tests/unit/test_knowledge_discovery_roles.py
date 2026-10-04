"""Source-role declarations exercise real normalization/history/A3, with model doubles."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import discovery_analysis as a2, discovery_design as design, discovery_review as reviews
from app.knowledge import discovery_candidates as identities, ontology_changes as a3, ontology_canonical as canonical
from app.knowledge import ontology_schema
from app.tests.unit.test_knowledge_discovery_analysis import done, request, model, source_response
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare
from app.tests.unit.test_knowledge_ontology_changes import listing, decide


def role_wire(data, source, endpoint='object'):
    return dict(classification='type',support_type='design_proposal',
        classification_reason='제공 명제의 역할',
        abstraction_level='이 명제 안의 역할',review_signals=[],cq_ids=['cq1'],scope_item_ids=[],outside_scope_reason='',
        source_refs=[v['source_ref'] for v in a2.segments.originals(data) if v['ref'] in source['evidence_ids']],
        design_reason='제공 명제의 대상 역할을 구분',
        role_basis=dict(relation_ref=source['id'],endpoint=endpoint))


@pytest.mark.parametrize('correction',[False,True])
def test_role_builder_correction_dependency_and_a3_roundtrip(service,model,monkeypatch,correction):
    source=prepare(service,file_ids=['current:0']);original=a2.model_call
    async def generated(prompt,schema,stage,run,timeout):
        result=await original(prompt,schema,stage,run,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);value=source_response(json.loads(result['text']),data)
        if stage=='builder':
            value['hierarchies']=[];value.setdefault('observations',[])
            if not correction or data.get('binding_checks'):
                natural=data['unapproved_relations'][0]
                value['relation_bindings'][0]['object_ref']=role_wire(data,natural)
            else:
                value['relation_bindings'][0]['object_ref']=value['relation_bindings'][0]['subject_ref']
            inline=bool(data.get('binding_checks')) and run['recipe'].get('builder_correction_contract')=='inline-single-v1'
            if not inline: design.inline_types(value)
            jsonschema.validate(value,schema)
            if inline:
                assert a2.models.SHARED_TYPE_RULE not in prompt
                bad=deepcopy(value);bad['relation_bindings'][0]['object_ref']='t1'
                with pytest.raises(jsonschema.ValidationError): jsonschema.validate(bad,schema)
        if stage=='binding' and correction and not any(u.get('parent_group_id') and u['status']=='succeeded' for u in run['analysis_units']):
            value['binding_checks']['object']='refuted'
            value['binding_reasons']['object']='모형 검사에서 지정한 잘못된 대상 유형'
        result['text']=json.dumps(value,ensure_ascii=False);return result
    monkeypatch.setattr(a2,'model_call',generated)
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=16,additional_rounds=0,revisions=1)))['run_id'])
    assert not run['result']['failures'],run['result']['failures']
    roles=[c for c in run['result']['observations'] if c.get('role_basis')]
    assert len(roles)==1,(run['candidate_groups'],run['result'])
    role=roles[0];relation=run['result']['relations'][0]
    builder=next(u for u in run['analysis_units'] if any(c.get('role_basis') for c in u.get('output',{}).get('observations',[])))
    raw=json.loads(builder['raw_output'])
    declaration=raw['relation_bindings'][0]['object_ref'] if correction else next(c for c in raw['observations'] if c.get('role_basis'))
    assert isinstance(declaration,dict) and 'definition' not in declaration
    assert role['definition_declaration']['definition']==''
    assert role['role_source']==relation['source_relation']
    assert '필요충분 정의나 실제 발생 사실을 선언하지 않음' in role['definition']
    current={c['id']:c for c in run['result']['observations']+run['result']['relations']}
    valid=reviews.latest_by_candidate(run['result']['critiques'],current)
    assert role['id'] in valid and relation['id'] in valid
    before=deepcopy(current)
    changed=deepcopy(current);changed[relation['id']]['source_relation']['conditions']='변경된 출처 조건'
    assert role['id'] not in reviews.latest_by_candidate(run['result']['critiques'],changed)
    assert relation['id'] not in reviews.latest_by_candidate(run['result']['critiques'],changed)
    missing=dict(current);missing.pop(relation['id'])
    assert role['id'] not in reviews.latest_by_candidate(run['result']['critiques'],missing)
    changed=deepcopy(current);changed[role['id']]['definition']+=' 변경'
    assert relation['id'] not in reviews.latest_by_candidate(run['result']['critiques'],changed)
    assert current==before
    different=dict(role,role_basis=dict(role['role_basis'],endpoint='subject'))
    assert identities.exact_key(role)!=identities.exact_key(different)
    cid=a3.publish(service,run['id'])['changeset_id']
    row=next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==role['id'])
    assert row['can_accept'],row
    accepted=decide(service,cid,[dict(candidate_id=row['id'],action='accept')])
    version=ontology_schema.get_ontology(service,accepted['reviewed_ontology_version_id'])
    target=next(c for c in version['candidates'] if c['id']==row['target_id'])
    assert target['modeling_origin']['role_basis']==role['role_basis']
    assert target['modeling_origin']['role_source']==role['role_source']
    reread=a2.base_context(dict(base_candidates=[target]))[0]
    assert reread['role_basis']==role['role_basis'] and reread['role_source']==role['role_source']
    # A canonical ot_ type can be selected under a new discovery relation ID only
    # while the identical current natural proposition and exact evidence are supplied.
    reused=dict(relation,id='new-relation',object=reread['id'],source_relation=dict(relation['source_relation'],id='new-relation'))
    selected={reused['id']:reused,reread['id']:reread,relation['subject']:current[relation['subject']]}
    from app.knowledge import discovery_synthesis as synthesis
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    reused_context,_,_=synthesis.context_for(list(selected.values()),by_id,a2.profile.contexts(blocks))
    reused_context=a2.segments.bind(reused_context,run['id'],'reused-role',stable=True)
    reused_context['review_target_ids']=[reused['id']]
    binding=reviews.normalize_binding(dict(candidate_ref=reused['id'],binding_checks=dict(subject='supported',object='supported'),
        binding_reasons=dict(subject='제공 역할 대조',object='재조회한 역할과 현재 출처 대조'),
        source_refs=[v['source_ref'] for v in a2.segments.originals(reused_context)]),selected,reused_context,by_id)
    assert reviews.dependencies_current(binding,reused['id'],selected)
    changed=deepcopy(selected);changed[reused['id']]['source_relation']['conditions']='새 조건'
    assert not reviews.dependencies_current(binding,reused['id'],changed)
    assert design.role_fingerprints(reread,{reread['id']:reread})=={reread['id']:None}
    # Explicit direct-definition A3 update replaces the prior provenance as a whole.
    update=deepcopy(row);update.update(operation='update',origin=dict(definition_mode='direct',
        direct_definition_evidence_refs=role['evidence_refs'],definition_declaration=dict(definition='직접 정의')))
    update['after']['definition']='직접 정의'
    items=canonical.project(version,[update]);payload,_,_=canonical.build(version,items)
    direct=canonical.read(dict(payload,status='reviewed'))['candidates'][0]
    assert direct['modeling_origin']['definition_mode']=='direct'
    assert not {'role_basis','role_source','source_relations'} & direct['modeling_origin'].keys()
    assert not a2.base_context(dict(base_candidates=[direct]))[0].get('role_basis')
    if correction: assert run['result']['revision_history'] and builder.get('parent_group_id')

    # A real successful source Revision must flow through finish and A3 dependency checks.
    from app.knowledge import discovery_synthesis as synthesis
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    context,deps,supplied=synthesis.context_for(list(current.values()),by_id,a2.profile.contexts(blocks))
    context.update(target_ids=[relation['id']],targets=[relation],source_change_ids=[relation['id']])
    async def source_revision(prompt,schema,stage,trial,timeout):
        result=await original(prompt,schema,stage,trial,timeout)
        data=json.loads(prompt.split('\nINPUT:\n')[1]);target=data['targets'][0]
        row={k:target[k] for k in a2.models.Relation.model_fields if k in target}
        row.update(candidate_ref=target['id'],local_ref='r1',conditions='새 출처 한정',reason='출처 조건의 명시적 변경')
        result['text']=json.dumps(dict(observations=[],relations=[row],hierarchies=[],deferred=[]),ensure_ascii=False)
        return result
    monkeypatch.setattr(a2,'model_call',source_revision)
    changed=a2.call(service,run,'revision','source_condition_changed',context,deps,by_id,supplied)
    assert changed is not None,run['analysis_units'][-1]['error']
    a2.finish(run,blocks,set(by_id))
    assert {role['id'],relation['id']}<=set(run['result']['review_pending_candidate_ids'])
    converted,_,_=a3._convert(run,{},by_id)
    deferred=next(c for c in converted if c['origin'].get('candidate_id')==role['id'])
    assert deferred['review_status']=='deferred' and deferred['origin']['review_errors']


def declaration_fixture():
    text='조건 A에서 기관은 대상 X를 선정하여야 한다. 다만 B는 제외한다.'
    block=dict(id='e',source_version_id='v',parse_run_id='p',locator=dict(page=1),text=text)
    view=dict(ref='e',text=text,span=[0,len(text)],source_ref='s1')
    ref=dict(evidence_id='e',block_id='e',source_version_id='v',parse_run_id='p',locator=block['locator'],span=view['span'],quote=text)
    source=dict(id='r',subject='기관',predicate='선정하여야 한다',object='대상 X',direction='subject_to_object',
        statement_type='rule',negation='negated',conditions='조건 A, 다만 B 제외',time='2026년 한정',
        endpoint_mode='source_text',evidence_ids=['e'],evidence_refs=[ref],validation=[])
    context=dict(blocks=[view]);data=dict(context)
    row=role_wire(data,source);row['local_ref']='t1'
    return row,source,block,context


@pytest.mark.parametrize('bad',['mixed','unknown_source','endpoint','missing_evidence','not_provided','no_direct_selection','free_label','free_conditions','free_exceptions','free_time'])
def test_invalid_declaration_is_rejected_without_silent_rewrite(bad):
    row,source,block,context=declaration_fixture()
    if bad.startswith('free_'): row[bad.removeprefix('free_')]='원문 밖 주장'
    if bad=='mixed': row['definition']='선정이 자격을 부여한다'
    if bad=='unknown_source': row['role_basis']['relation_ref']='other'
    if bad=='endpoint': row['role_basis']['endpoint']='wrong'
    if bad=='missing_evidence': source['evidence_refs']=[]
    if bad=='not_provided': row['source_refs']=['not_provided']
    if bad=='no_direct_selection': row.pop('role_basis');row['definition']='자유 정의'
    output=dict(observations=[row])
    with pytest.raises(ValueError): design.declarations(output,{'r':source},{'e':block},context)
    assert row.get('definition','') in {'','선정이 자격을 부여한다','자유 정의'}


def test_role_snapshot_qualifiers_and_source_hash_exclude_modeling_cycle():
    row,source,block,context=declaration_fixture()
    design.declarations(dict(observations=[row]),{'r':source},{'e':block},context)
    row['id']='t'
    assert row['role_source']==source
    assert len(row['definition'])<=240
    assert row['label']==source['object'] and row['conditions']==row['time']==row['exceptions']==''
    assert row['role_source']['negation']=='negated' and row['role_source']['predicate']=='선정하여야 한다'
    first=design.role_fingerprints(row,{'r':source})
    modeled=dict(source,subject='t',object='other',statement_type='design_proposal',source_relation=deepcopy(source),design_reason='설계')
    assert design.role_fingerprints(row,{'r':modeled})==first
    for key in ('conditions','negation','time','predicate'):
        changed=deepcopy(modeled);changed['source_relation'][key]='변경'
        assert design.role_fingerprints(row,{'r':changed})=={'t':None}
    assert design.role_fingerprints(row,{})=={'t':None}


def test_explicit_legacy_to_role_to_direct_revision_records_actual_history(service,model,monkeypatch):
    from app.knowledge import discovery_synthesis as synthesis
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id']))['run_id'])
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks};contexts=a2.profile.contexts(blocks)
    target=run['result']['observations'][0];natural=run['result']['original_relations'][0]
    before=deepcopy(target);assert not target.get('role_basis') and not target.get('definition_mode')
    original=a2.model_call
    for transition in ('role','direct'):
        async def generated(prompt,schema,stage,trial,timeout):
            result=await original(prompt,schema,stage,trial,timeout)
            data=json.loads(prompt.split('\nINPUT:\n')[1]);provided=data['comparison_candidates'][0]
            row=role_wire(data,provided);row.pop('source_relation_ids',None)
            row.update(local_ref='o1',candidate_ref=data['targets'][0]['id'],reason='외부 검수에 따른 명시적 '+transition+' 전환')
            if transition=='direct':
                row.pop('role_basis');row.update(label='직접 정의 유형',definition='제공 원문에 직접 정의된 유형',direct_definition_source_refs=row['source_refs'],conditions='',exceptions='',time='')
            value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
            jsonschema.validate(value,schema)
            result['text']=json.dumps(value,ensure_ascii=False);return result
        monkeypatch.setattr(a2,'model_call',generated)
        context,deps,supplied=synthesis.context_for([target,natural],by_id,contexts)
        context.update(target_ids=[target['id']],targets=[target],comparison_candidates=[natural])
        output=a2.call(service,run,'revision','explicit_'+transition,context,deps,by_id,supplied)
        assert output is not None,run['analysis_units'][-1]['error']
        history=output['history'][0]
        assert history['before']==target and history['reason'].endswith(transition+' 전환')
        target=history['after']
        assert target['id']==before['id']
        if transition=='role':
            assert target['role_source']==natural and target['definition_mode']=='source_role'
        else:
            assert target['definition_mode']=='direct'
            assert not target.get('role_basis') and not target.get('role_source') and not target.get('source_relation_ids')
            assert target['direct_definition_evidence_refs']
        a2.finish(run,blocks,set(by_id))
        assert target['id'] in run['result']['review_pending_candidate_ids']
        assert len(run['result']['revision_history'])==(1 if transition=='role' else 2)
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    cid=a3.publish(service,run['id'])['changeset_id']
    row=next(c for c in listing(service,cid)['candidates'] if c['origin'].get('candidate_id')==target['id'])
    assert row['origin']['definition_mode']=='direct' and not row['origin'].get('role_basis')
    assert not row['can_accept']  # Explicit external correction still requires a new current review.


def test_legacy_schema_and_decoder_stay_exact_while_new_wire_is_separate():
    from pydantic import ValidationError
    models=a2.models
    assert a2.profile.digest({k:v.model_json_schema() for k,v in models.OUTPUTS.items()})=='693afb830e82eae59e353b3d3cafb8dc9e8dbc338d7740fd313d473f896b229c'
    for stage in ('builder','revision'):
        assert models.output_model(stage) is models.OUTPUTS[stage]
        assert models.output_model(stage,'source-role-v1') is not models.OUTPUTS[stage]
    old=dict(local_ref='t1',label='기존 유형',classification='type',definition='기존 정의',support_type='design_proposal',
        abstraction_level='유형',review_signals=[],source_relation_ids=['r'],design_reason='기존 사유')
    assert models.DesignedType.model_validate(old).definition=='기존 정의'
    for patch in ({'label':''},{'definition':''},{'source_relation_ids':[]},{'role_basis':dict(relation_ref='r',endpoint='object')}):
        with pytest.raises(ValidationError): models.DesignedType.model_validate(dict(old,**patch))
    revision={k:v for k,v in old.items() if k not in {'source_relation_ids','design_reason'}}
    revision.update(candidate_ref='c',reason='기존 변경 사유')
    assert models.ObservationRevision.model_validate(revision).definition=='기존 정의'
    for patch in ({'label':''},{'definition':''},{'direct_definition_source_refs':['s']},{'role_basis':dict(relation_ref='r',endpoint='object')}):
        with pytest.raises(ValidationError): models.ObservationRevision.model_validate(dict(revision,**patch))
    row,_,_,_=declaration_fixture()
    assert models.DeclaredType.model_validate(row).role_basis.endpoint=='object'
    assert not models.DeclaredType.model_validate(row).definition

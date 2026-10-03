"""Observation Revision narrows model input while server validation retains all candidates."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import discovery_analysis as a2, discovery_synthesis as synthesis
from app.tests.unit.test_knowledge_discovery_analysis import done, request, model
from app.tests.unit.test_knowledge_discovery_run import corpus, service, prepare


@pytest.mark.parametrize('mode',['normal','hidden_target','hidden_role','classification','legacy','cap'])
def test_revision_model_scope_full_validation_and_deferral(service,model,monkeypatch,mode):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=24,additional_rounds=0,revisions=1)))['run_id'])
    group=deepcopy(run['candidate_groups'][0]);group.pop('correction_plan',None)
    taxonomy=next(u['output'] for u in run['analysis_units'] if u['id']=='builder:'+group['id'])
    target=next(c for c in group['candidates'] if c.get('classification')=='type')
    relation=next(c for c in group['design_candidates'] if c.get('source_relation'))
    target.update(source_relation_ids=[relation['id']],role_source=deepcopy(relation['source_relation']))
    hidden=next(c for c in group['candidates'] if c.get('classification') and c['id']!=target['id'])
    frozen=deepcopy(group);calls=[];rechecks=[]
    if mode=='legacy': run['recipe'].pop('revision_context_contract')
    if mode=='cap': run['recipe']['input_chars']=10
    monkeypatch.setattr(a2,'recipe',lambda budgets:deepcopy(run['recipe']))
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks}
    review=dict(issues=[dict(candidate_ref=target['id'],cause='content_error',reason='정의 보완',
        evidence_ids=target['evidence_ids'],counter_evidence_ids=hidden['evidence_ids'])])
    review['review_coverage']=dict(valid_candidate_ids=[target['id']],candidate_hashes={target['id']:a2.reviews.fingerprint(target)})
    async def generated(prompt,schema,stage,current,timeout):
        assert stage=='revision'
        data=json.loads(prompt.split('\nINPUT:\n')[1]);calls.append(data)
        assert data['targets'][0]['role_source']['conditions']==target['role_source']['conditions']
        assert data['targets'][0]['role_source']['time']==target['role_source']['time']
        natural=next(c for c in data['comparison_candidates'] if c['id']==relation['id'])
        if mode!='legacy':
            assert len(data['comparison_candidates'])==1
            assert natural['subject']==relation['source_relation']['subject']
            assert natural['conditions']==relation['source_relation']['conditions']
            assert hidden['id'] in data['omitted_comparison_candidate_ids']
            assert hidden['id'] not in schema['$defs']['RoleBasis']['properties']['relation_ref']['enum']
        row={k:v for k,v in target.items() if k in a2.models.Observation.model_fields}
        row.update(candidate_ref=target['id'],reason='제공 정의 범위 보완',design_reason='기존 정의 명시 수정',definition='명시적으로 수정한 정의',
            source_refs=[v['source_ref'] for v in a2.segments.originals(data)],direct_definition_source_refs=[data['blocks'][0]['source_ref']])
        row.pop('evidence_ids',None);row.pop('source_quotes',None)
        if mode=='classification': row['classification']='vocabulary'
        if mode=='hidden_target': row['candidate_ref']=hidden['id']
        if mode=='hidden_role':
            for key in ('label','definition','conditions','exceptions','time','direct_definition_source_refs'): row.pop(key,None)
            row.update(role_basis=dict(relation_ref=hidden['id'],endpoint='subject'),support_type='design_proposal',design_reason='미제공 참조')
        value=dict(observations=[row],relations=[],hierarchies=[],deferred=[])
        if mode in {'hidden_target','hidden_role'}:
            with pytest.raises(jsonschema.ValidationError): jsonschema.validate(value,schema)
        else:
            assert jsonschema.Draft202012Validator(schema).is_valid(value), '유효 응답 대역 스키마 불일치'
        return dict(text=json.dumps(value,ensure_ascii=False),done=True,done_reason='stop',prompt_eval_count=100,eval_count=50)
    monkeypatch.setattr(a2,'model_call',generated)
    call=a2.call;captured=[]
    def record(service,run,stage,key,context,deps,by_id,supplied,**kwargs):
        captured.append((stage,key,deepcopy(context),list(deps),dict(supplied),deepcopy(kwargs)))
        return call(service,run,stage,key,context,deps,by_id,supplied,**kwargs)
    monkeypatch.setattr(a2,'call',record)
    def recheck(service,run,group,context,deps,supplied,by_id,context_map,revised=False):
        assert revised
        assert hidden['id'] in supplied and relation['id'] in supplied
        assert supplied[relation['id']]['subject']==relation['subject']
        assert target['id'] in context['review_target_ids'] and relation['id'] in context['review_target_ids']
        rechecks.append(deepcopy(context))
    monkeypatch.setattr(synthesis,'focused_reviews',recheck)
    synthesis.revise(service,run,group,review,taxonomy,by_id,a2.profile.contexts(blocks))
    if mode=='cap':
        assert not calls
        deferred=group['revision_deferrals'][0]
        assert deferred['input_chars']>deferred['input_chars_limit']==10
        assert deferred['input_bytes_limit']==28672
    else:
        unit=next(u for u in run['analysis_units'] if u['stage']=='revision')
        if mode in {'hidden_target','hidden_role'}:
            assert unit['status']=='failed' and not rechecks
            assert '범위 밖' in unit['error'] or '유효 자연어' in unit['error']
        else:
            assert unit['status']=='succeeded',unit.get('error')
            assert unit['output']['history'][0]['before']==target
            assert len(rechecks)==1
            hierarchy=unit['output']['effective_hierarchies'][0]
            assert bool(hierarchy['validation'])==(mode=='classification')
            if mode=='classification': assert '구조 관계의 대상 종류 불일치' in hierarchy['validation']
            if mode!='legacy':
                # Hidden current state participates in immutable unit reuse, not in the wire schema.
                stage,key,context,deps,supplied,kwargs=captured[0]
                count=len(calls)
                assert call(service,run,stage,key,context,deps,by_id,supplied,**kwargs)==unit['output']
                assert len(calls)==count
                kwargs['validation_supplied'][hidden['id']]['definition']='다른 서버 상태'
                with pytest.raises(ValueError,match='입력 해시 변경'):
                    call(service,run,stage,key,context,deps,by_id,supplied,**kwargs)
    assert group['candidates']==frozen['candidates'] and group['design_candidates']==frozen['design_candidates']


def test_required_counter_span_in_same_block_is_preserved_without_whole_block(service,model,monkeypatch):
    source=prepare(service,file_ids=['current:0'])
    run=done(service,service.start(request(source['id'],discovery_budgets=dict(model_calls=24,additional_rounds=0,revisions=1)))['run_id'])
    group=deepcopy(run['candidate_groups'][0]);group.pop('correction_plan',None)
    taxonomy=next(u['output'] for u in run['analysis_units'] if u['id']=='builder:'+group['id'])
    target=next(c for c in group['candidates'] if c.get('classification')=='type')
    relation=next(c for c in group['design_candidates'] if c.get('source_relation'))
    blocks=a2.load_blocks(service,run);by_id={b['id']:b for b in blocks};block=by_id[target['evidence_ids'][0]]
    block['text']='\n'.join(marker+' 제공 문맥'*100 for marker in '①②③④⑤⑥⑦⑧')
    spans=a2.segments.split(block)
    assert len(spans)>1
    def ref(span):
        return dict(target['evidence_refs'][0],span=span,quote=block['text'][slice(*span)])
    early,late=ref(spans[0]['span']),ref(spans[-1]['span'])
    target['evidence_refs']=[late]
    relation['source_relation']['evidence_refs']=[late]
    relation['evidence_refs']=[late]
    target.update(source_relation_ids=[relation['id']],role_source=deepcopy(relation['source_relation']))
    hidden=next(c for c in group['candidates'] if c.get('classification') and c['id']!=target['id'])
    hidden['evidence_refs']=[early]
    review=dict(issues=[dict(candidate_ref=target['id'],cause='content_error',reason='별도 구간 반례',
        evidence_ids=[block['id']],evidence_refs=[late],counter_evidence_ids=[block['id']],counter_evidence_refs=[early])],
        review_coverage=dict(valid_candidate_ids=[target['id']],candidate_hashes={target['id']:a2.reviews.fingerprint(target)}))
    def inspect(service,run,stage,key,context,deps,by_id,supplied,**kwargs):
        assert hidden['id'] not in supplied and hidden['id'] in kwargs['validation_supplied']
        views=[v for v in a2.segments.originals(context) if v['ref']==block['id']]
        for required in (early,late):
            assert all(any(v['span'][0]<=a<z<=v['span'][1] for v in views)
                for a,z in [s['span'] for s in a2.segments.clause_views([dict(ref=block['id'],text=required['quote'],span=required['span'])])])
        assert all(v['text']==block['text'][slice(*v['span'])] and len(v['text'])<len(block['text']) for v in views)
        raise RuntimeError('필수 구간 확인 완료')
    monkeypatch.setattr(a2,'call',inspect)
    with pytest.raises(RuntimeError,match='필수 구간 확인 완료'):
        synthesis.revise(service,run,group,review,taxonomy,by_id,a2.profile.contexts(blocks))

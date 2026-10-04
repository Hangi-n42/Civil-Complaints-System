"""L3: focused source ownership continues through missing-meaning recovery."""
from copy import deepcopy

import pytest

from app.knowledge import discovery_analysis as a2, discovery_segments as segments, discovery_synthesis as synthesis


def projection(legacy=False):
    text='제15조 ① 첫 항의 의무. ② 둘째 항의 권한. ③ 셋째 항의 조건.'
    block=dict(id='b',text=text,title='자료',source_version_id='v',parse_run_id='p',locator={},role='article',file_id='f',source_group='s')
    by_id={'b':block}
    contexts={'b':dict(block_ids=['b'])}
    views=segments.clause_views([dict(ref='b',text=text)])
    bound=segments.bind(dict(blocks=views),'run','fixture',stable=True)
    refs,_=segments.references(dict(source_refs=[v['source_ref'] for v in bound['blocks'][1:]]),by_id,bound['blocks'])
    def grounded(identifier,ref,**fields):
        return dict(id=identifier,evidence_ids=['b'],evidence_refs=[] if legacy else [ref],cq_ids=['q'],scope_item_ids=[],**fields)
    actor=grounded('actor',refs[0],classification='type',definition='행위자',source_relation_ids=['r1'])
    target=grounded('target',refs[0],classification='type',definition='대상')
    relations=[]
    for n,ref in enumerate(refs,1):
        raw=grounded('r'+str(n),ref,subject='행위자',object='대상',predicate='행위',negation='affirmed',endpoint_labels=dict(subject='행위자',object='대상'))
        relations.append(dict(raw,subject='actor',object='target',source_relation=raw))
    coverage=[dict(block_id='b',span=r['span'],candidate_ids=['r'+str(n)],gaps=[],semantic_status='unverified') for n,r in enumerate(refs,1)]
    run=dict(recipe=dict(review_contract='checks-v1'),analysis_units=[],cqs=[dict(id='q')],scope_items=[],
        frontier=[dict(id='g',block_ids=['b'],analysis_target_coverage=[] if legacy else coverage)])
    group=dict(id='cg',candidates=relations+[actor,target],design_candidates=[],primary_candidate_ids=['r1','r2','r3'],
        design_candidate_ids=[],analysis_group_ids=['g'],builder_tool_context=dict(terms={}))
    context,deps,supplied=synthesis.review_context(run,group,dict(hierarchies=[]),by_id,contexts)
    before=deepcopy((run,group,context,supplied))
    batch=next(b for b in synthesis.review_batches(context,deps,supplied,by_id,contexts)
               if b['context']['review_target_ids']==['r3'] and b['context'].get('review_component')=='proposition')
    assert (run,group,context,supplied)==before
    return run,group,by_id,context,batch,refs


def test_product_projection_keeps_text_and_marks_only_current_primary():
    run,group,by_id,parent,batch,refs=projection()
    ctx=batch['context']
    assert ctx['review_target_ids']==['r3']
    assert 'r1' in ctx['comparison_candidate_ids'] and 'r2' in ctx['review_scope']['omitted_comparison_ids']
    assert [(v['ref'],v['text'],v.get('span')) for v in ctx['blocks']]==[(v['ref'],v['text'],v.get('span')) for v in parent['blocks']]
    assert [v['span'] for v in ctx['blocks'] if v['analysis_target']]==[refs[2]['span']]
    assert [t['candidate_ids'] for t in ctx['analysis_target_coverage']]==[['r3']]
    assert len(run['frontier'][0]['analysis_target_coverage'])==3
    assert not ctx['review_scope']['whole_input_assessed']
    *_,legacy,_=projection(legacy=True)
    assert not legacy['context']['review_scope']['missing_meanings_allowed']
    assert not legacy['context']['review_scope']['primary_source_spans']
    assert all(v['context_only'] for v in legacy['context']['blocks'])


def test_exact_quote_adds_address_inside_provided_text_without_expanding_ownership():
    run,group,by_id,context,batch,refs=projection()
    contexts={'b':dict(block_ids=['b'])}
    candidate=group['candidates'][2]
    narrow=deepcopy(refs[2]);narrow['span'][0]+=2
    narrow['quote']=by_id['b']['text'][slice(*narrow['span'])]
    candidate['evidence_refs']=[narrow]
    run['frontier'][0]['analysis_target_coverage']=[]
    context,deps,supplied=synthesis.review_context(run,group,dict(hierarchies=[]),by_id,contexts)
    batch=next(b for b in synthesis.review_batches(context,deps,supplied,by_id,contexts)
               if b['context']['review_target_ids']==['r3'] and b['context'].get('review_component')=='proposition')
    ctx=segments.bind(batch['context'],'run','critic',stable=True)
    owned=[v for v in ctx['blocks'] if v['analysis_target']]
    assert len(owned)==1 and owned[0]['span']==narrow['span'] and owned[0]['text']==narrow['quote']
    compact=segments.compact_text(ctx)
    alias=next(v for v in compact['blocks'] if v.get('analysis_target'))
    assert 'text_from' in alias and 'text' not in alias
    assert next(v for v in segments.originals(compact) if v['analysis_target'])['text']==narrow['quote']


@pytest.mark.parametrize('selection',['own','other','mixed'])
def test_missing_scope_validation_and_recovery_keep_exact_span(selection):
    run,group,by_id,parent,batch,refs=projection()
    ctx=segments.bind(batch['context'],'run','critic',stable=True)
    own=next(v['source_ref'] for v in ctx['blocks'] if v['analysis_target'])
    other=next(v['source_ref'] for v in ctx['blocks'] if v.get('span')==refs[0]['span'])
    selected={'own':[own],'other':[other],'mixed':[own,other]}[selection]
    output=dict(issues=[],hierarchy_checks=[],observation_checks=[],actions=[],gaps=[],needs_revision=False,
        relation_checks=[dict(candidate_ref='r3',reason='정상 명제',source_refs=[other],
            semantic_checks={k:'supported' for k in a2.models.SEMANTIC_FIELDS['relation_checks']})],
        missing_meanings=[dict(role='relation',meaning='주범위 안 미표현 조건',source_refs=selected,cq_ids=['q'],
            compared_candidate_ids=['r3','r1','actor','target'],comparison_reason='제공된 기존 표현과 대조')])
    result=a2.normalize(output,'critic',run,batch['dependency_ids'],by_id,batch['supplied'],ctx,require_issue_cause=True)
    assert result['relation_checks']  # Other review citations still allow comparison context.
    assert bool(result['missing_meanings'])==(selection=='own')
    a2.queue_recovery(run,result,group,by_id)
    if selection=='own':
        assert run['recovery_requests'][0]['target']==[['b',refs[2]['span']]]
        assert not run['recovery_requests'][0]['validation']
        run['candidate_groups']=[group]
        recovery=a2.recovery_groups(run,1,by_id)[0]
        assert recovery['segments'][0]['span']==refs[2]['span']
        packet=segments.packet(recovery,by_id,{'b':dict(block_ids=['b'])},a2.packet)
        assert [v['span'] for v in packet if v.get('analysis_target')]==[refs[2]['span']]
        assert all(v['text']==by_id['b']['text'][slice(*v['span'])] for v in packet)
    else:
        assert not run['recovery_requests']
        assert any('소유 구간 밖' in e['reason'] for e in result['record_errors'])

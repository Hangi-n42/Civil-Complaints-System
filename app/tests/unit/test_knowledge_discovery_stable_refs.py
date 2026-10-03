"""K1: immutable addresses survive role, selection and resume changes."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_segments as segments


def test_canonical_prompt_refs_survive_role_selection_and_resume():
    b = dict(id='block-id', text='첫 조건. 둘째 조건.', source_version_id='v', parse_run_id='p', locator={'page': 1})
    candidate = dict(id='candidate-id', classification='type', definition='역할', evidence_ids=[b['id']])
    context = dict(blocks=[dict(ref=b['id'], text=b['text'], span=[0,len(b['text'])])],
                   targets=[candidate], target_ids=[candidate['id']])
    before = deepcopy(context)
    run = dict(id='original-run', cqs=[], scope_items=[], recipe=dict(reference_contract='canonical-v1'))
    outputs = []
    for stage, run_id, supplied in [('critic','original-run',{candidate['id']:candidate}),
                                   ('revision','resumed-run',{'other':dict(id='other'),candidate['id']:candidate})]:
        mapping, prompt = a2.make_prompt(dict(run,id=run_id), stage, context, [b['id']], supplied, stage)
        data = json.loads(prompt.split('\nINPUT:\n')[1]); outputs.append(data)
        assert mapping[candidate['id']] == candidate['id'] and mapping[b['id']] == b['id']
        assert data['targets'][0]['id'] == candidate['id']
    assert outputs[0]['blocks'] == outputs[1]['blocks'] and context == before
    view = outputs[0]['blocks'][0]
    item = dict(source_refs=[view['source_ref']], evidence_ids=[b['id']])
    segments.restore(item, {b['id']:b}, outputs[1]['blocks'])
    assert item['evidence_refs'][0]['source_version_id'] == 'v'
    with pytest.raises(ValueError,match='제공되지 않은'):
        segments.restore(dict(source_refs=[view['source_ref']]), {b['id']:b}, [])


def test_stable_refs_distinguish_block_span_and_text_and_preserve_legacy():
    views = [dict(ref='b',text='반복',span=[0,2]),dict(ref='b',text='반복',span=[3,5]),
             dict(ref='b',text='변경',span=[0,2]),dict(ref='other',text='반복',span=[0,2])]
    a = segments.bind(dict(blocks=views),'run','critic:g',stable=True)
    z = segments.bind(dict(blocks=list(reversed(views))),'resumed','revision:g',stable=True)
    assert len({v['source_ref'] for v in a['blocks']}) == 4
    assert a['blocks'] == list(reversed(z['blocks']))
    legacy = segments.bind(dict(blocks=views),'run','critic:g')
    assert legacy != a and legacy == segments.bind(dict(blocks=views),'run','critic:g')


def test_relation_critic_projects_shared_type_uses_without_mutating_or_fetching_types():
    run=dict(id='run',cqs=[],scope_items=[],recipe=dict(reference_contract='canonical-v1'))
    actor=dict(id='actor',classification='type',label='행위자',definition='선정하는 주체',conditions='제공 조건',exceptions='',time='현재')
    omitted=dict(id='omitted',classification='type',definition='이번 입력에 없는 정의')
    raw=dict(id='r1',subject='공급자',object='선정 대상',negation='affirmed')
    r1=dict(raw,subject='actor',object='omitted',source_relation=raw,design_reason='미검증 설계 이유')
    r2=dict(r1,id='r2',object='actor',source_relation=dict(raw,id='r2',object='다른 행위자'))
    standalone=dict(raw,id='raw')
    context=dict(blocks=[],review_focus='relations',unapproved_relations=[r1,r2,standalone],comparison_terms=[actor],taxonomy=dict(hierarchies=[]))
    supplied={c['id']:c for c in (actor,omitted,r1,r2,standalone)}
    before=deepcopy((context,supplied))
    def projected(stage='critic',focus='relations',ctx=context):
        _,prompt=a2.make_prompt(run,stage,dict(ctx,review_focus=focus),[],supplied)
        return json.loads(prompt.split('\nINPUT:\n')[1])
    data=projected();selected=data['comparison_terms'][0]
    assert {k:v for k,v in selected.items() if k!='binding_uses'}==actor
    assert selected['binding_uses']==[
        dict(relation_ref='r1',endpoint='subject',source_expression='공급자'),
        dict(relation_ref='r2',endpoint='subject',source_expression='공급자'),
        dict(relation_ref='r2',endpoint='object',source_expression='다른 행위자')]
    assert data['unapproved_relations']==[raw,r2['source_relation'],standalone]
    assert data['relation_bindings']==[dict(relation_ref='r1',subject_ref='actor',object_ref='omitted'),dict(relation_ref='r2',subject_ref='actor',object_ref='actor')]
    assert len(data['comparison_terms'])==1 and (context,supplied)==before
    observations=projected(focus='observations')
    assert observations['comparison_terms']==[actor]
    assert all(b['reason']=='미검증 설계 이유' for b in observations['relation_bindings'])
    for stage in ('builder','revision'):
        ctx=dict(context,targets=[r1],target_ids=['r1'])
        assert projected(stage=stage,ctx=ctx)['unapproved_relations']==context['unapproved_relations']
    current=deepcopy(context);current['comparison_terms'][0]['definition']='수정 후 현재 정의'
    assert projected(ctx=current)['comparison_terms'][0]['definition']=='수정 후 현재 정의'
    assert projected(ctx=current)['comparison_terms'][0]['binding_uses']==selected['binding_uses']


def test_selected_type_dependency_contract_is_local_and_fail_closed():
    from app.knowledge import discovery_review as reviews, discovery_synthesis as synthesis
    actor=dict(id='actor',classification='type',definition='행위 역할',conditions='',exceptions='',time='현재')
    other=dict(actor,id='other')
    raw=dict(id='raw',subject='행위자',object='대상',negation='affirmed')
    relation=dict(raw,id='r',subject='actor',object='actor',source_relation=raw)
    candidates={c['id']:c for c in (actor,other,raw,relation)}
    coverage=dict(expected_candidate_ids=list(candidates),valid_candidate_ids=list(candidates),pending_candidate_ids=[],
        candidate_hashes={i:reviews.fingerprint(c) for i,c in candidates.items()})
    legacy=dict(review_coverage=coverage,issues=[],needs_revision=False)
    review=dict(legacy,review_dependency_contract='selected-types-v1',
        binding_dependency_hashes={i:reviews.binding_fingerprints(c,candidates) for i,c in candidates.items()})
    before=deepcopy(review)
    assert review['binding_dependency_hashes']['r']==dict(subject=reviews.fingerprint(actor),object=reviews.fingerprint(actor))
    unrelated=dict(candidates,other=dict(other,definition='무관한 수정'))
    assert 'r' in reviews.valid_ids(review,unrelated)
    for field in ('definition','conditions','exceptions','time'):
        changed=dict(candidates,actor=dict(actor,**{field:'수정'}))
        assert 'r' not in reviews.valid_ids(review,changed)
        assert 'raw' in reviews.valid_ids(review,changed) and 'other' in reviews.valid_ids(review,changed)
        assert 'r' in reviews.valid_ids(legacy,changed)  # Do not rewrite stored legacy judgments.
    missing=dict(candidates);missing.pop('actor')
    assert 'r' not in reviews.valid_ids(review,missing)
    for key in ('binding_dependency_hashes','review_coverage'):
        incomplete=deepcopy(review);incomplete.pop(key)
        assert 'r' not in reviews.valid_ids(incomplete,candidates)
    incomplete=deepcopy(review);incomplete['binding_dependency_hashes'].pop('r')
    assert 'r' not in reviews.latest_by_candidate([review,incomplete],candidates)
    combined=synthesis.combined_review([review])
    assert reviews.valid_ids(combined,candidates)==set(candidates)
    assert 'r' not in reviews.valid_ids(combined,missing)
    assert review==before and reviews.valid_ids({}) is None
    assert reviews.valid_ids(dict(review_dependency_contract='selected-types-v1'))==set()
    base=dict(actor,kind='concept',review_status='reviewed')
    selected=reviews.with_selected_base_types({'r':relation},dict(base_candidates=[base,dict(other,kind='concept')]))
    assert set(selected)=={'r','actor'} and selected['actor']==base
    base_review=dict(review,binding_dependency_hashes={'r':reviews.binding_fingerprints(relation,selected)})
    assert 'r' in reviews.valid_ids(base_review,selected)
    changed=reviews.with_selected_base_types({'r':relation,'actor':dict(base,definition='현재 정의')},dict(base_candidates=[base]))
    assert 'r' not in reviews.valid_ids(base_review,changed)

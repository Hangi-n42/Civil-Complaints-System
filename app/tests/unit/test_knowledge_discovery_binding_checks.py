"""K2: source truth and endpoint typing are independent review decisions."""
from copy import deepcopy

import pytest

from app.knowledge import discovery_analysis as a2, discovery_review as reviews, discovery_segments as segments


def normalized(semantic='supported', binding='supported', *, missing=False, legacy=False):
    block=dict(id='b',text='사업자는 입주자를 선정한다.',source_version_id='v',parse_run_id='p',locator={'page':1})
    raw=dict(id='r',subject='사업자',object='입주자',negation='affirmed',endpoint_labels=dict(subject='사업자',object='입주자'))
    candidates={'r':dict(raw,subject='actor',object='housing',source_relation=raw),
                'actor':dict(id='actor',classification='type',definition='선정하는 주체'),
                'housing':dict(id='housing',classification='type',definition='주택')}
    context=segments.bind(dict(blocks=[dict(ref='b',text=block['text'])],review_target_ids=['r'],review_scope={}), 'run','critic',stable=True)
    check=dict(candidate_ref='r',reason='원명제와 실제 연결 정의를 독립 대조',source_refs=[context['blocks'][0]['source_ref']],
               semantic_checks={k:semantic for k in a2.models.SEMANTIC_FIELDS['relation_checks']})
    if not missing: check['binding_checks']=dict(subject='supported',object=binding)
    output=dict(issues=[],relation_checks=[check],observation_checks=[],hierarchy_checks=[],missing_meanings=[],actions=[],gaps=[],needs_revision=False)
    run=dict(recipe={} if legacy else dict(review_contract='checks-v1'),analysis_units=[],cqs=[],scope_items=[])
    if legacy:
        check['judgment']='supported'
        output['issues']=[dict(local_ref='i1',cause='content_error',candidate_ref='r',reason='과거 모순',
                              evidence_ids=['b'],counter_evidence_ids=[],defer_reason='')]
    original=deepcopy(output)
    result=a2.normalize(deepcopy(output),'critic',run,['b'],{'b':block},candidates,context,require_issue_cause=True)
    assert output==original
    return result,candidates


@pytest.mark.parametrize('semantic,binding,causes', [('supported','refuted',['endpoint']),
    ('refuted','supported',['content_error']),('supported','supported',[]),('unknown','unknown',[])])
def test_independent_checks_derive_one_issue_and_unknown_stays_unconfirmed(semantic,binding,causes):
    result,candidates=normalized(semantic,binding)
    check=result['relation_checks'][0]
    assert check['judgment']==semantic and check['binding_checks']['object']==binding
    assert [i['cause'] for i in result['issues']]==causes
    assert bool(check.get('binding_validation'))==(binding!='supported')
    assert reviews.valid_ids(result,candidates)=={'r'}
    candidates['r']['object']='actor'
    assert reviews.valid_ids(result,candidates)==set()


def test_missing_binding_is_pending_and_legacy_contradiction_stays_failed():
    missing,_=normalized(missing=True)
    assert not missing['relation_checks'] and missing['review_coverage']['pending_candidate_ids']==['r']
    assert not missing['issues']
    legacy,_=normalized(legacy=True)
    assert not legacy['relation_checks'] and legacy['review_coverage']['pending_candidate_ids']==['r']
    assert '충돌' in legacy['record_errors'][0]['reason']


@pytest.mark.parametrize('definition,checks,expected', [
    ('공급하고 선정하는 주체', ('supported','supported','supported','supported'), 'supported'),
    ('조건 없이 선정할 수 있는 주체', ('supported','supported','refuted','supported'), 'refuted'),
    ('원문 밖 구체 자격을 갖춘 주체', ('supported','refuted','supported','supported'), 'refuted'),
    ('별표에서 정한 자격의 주체', ('supported','unknown','unknown','supported'), 'unknown'),
])
def test_definition_checks_preserve_decision_boundaries_without_inferring_empty_fields(definition, checks, expected):
    # These supplied judgments exercise storage/routing, not a model's semantic accuracy.
    block=dict(id='b',text='사업자는 공급하고 선정한다. 자격은 별표에 따른다.',source_version_id='v',parse_run_id='p',locator={})
    candidate=dict(id='c',classification='type',definition=definition,conditions='',exceptions='')
    context=segments.bind(dict(blocks=[dict(ref='b',text=block['text'])],review_target_ids=['c'],review_scope={}), 'run','critic',stable=True)
    check=dict(candidate_ref='c',reason='정의의 실제 주장과 제공 근거 대조',source_refs=[context['blocks'][0]['source_ref']],
               semantic_checks=dict(zip(a2.models.SEMANTIC_FIELDS['observation_checks'], checks)))
    output=dict(issues=[],relation_checks=[],observation_checks=[check],hierarchy_checks=[],missing_meanings=[],actions=[],gaps=[],needs_revision=False)
    run=dict(recipe=dict(review_contract='checks-v1'),analysis_units=[],cqs=[],scope_items=[])
    result=a2.normalize(output,'critic',run,['b'],{'b':block},{'c':candidate},context,require_issue_cause=True)
    assert result['observation_checks'][0]['judgment']==expected
    assert result['observation_checks'][0]['semantic_checks']==check['semantic_checks']
    assert [i['cause'] for i in result['issues']]==(['content_error'] if expected=='refuted' else [])
    assert result['needs_revision']==(expected=='refuted')

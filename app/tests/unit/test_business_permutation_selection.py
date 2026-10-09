"""Six mappings are a fixed mean of semantic log scores, not a vote."""
import importlib.util
import itertools
import math
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('permutation',SCRIPTS/'compare_business_permutation_selection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def rows_for(semantic):
    return [dict(mapping=key,status='completed',selection=dict(option_logprobs={code:semantic[label] for code,label in mapping.items()})) for key,mapping in m.MAPPINGS.items()]


def test_all_positions_balanced_and_inverse_mapping_correct():
    assert len(m.MAPPINGS)==6
    for code in m.base.TOKENS:
        for label in m.LABELS:assert sum(v[code]==label for v in m.MAPPINGS.values())==2
    rows=rows_for(dict(zip(m.LABELS,[-2.,-1.,-3.])))
    result=m.aggregate(rows)
    assert result['label']=='unsupported' and result['mean_logprobs']['unsupported']==-1
    for perm in itertools.permutations(rows):assert m.aggregate(perm)['mean_logprobs']==result['mean_logprobs']


def test_additive_code_bias_cancels_but_no_probability_average_is_used():
    rows=rows_for(dict(zip(m.LABELS,[-2.,-1.,-3.])))
    for row in rows:
        for code,bias in zip(m.base.TOKENS,[-12.,-6.,0.]):row['selection']['option_logprobs'][code]+=bias
    assert m.aggregate(rows)['mean_logprobs']==dict(zip(m.LABELS,[-8.,-7.,-9.]))
    for index,row in enumerate(rows):
        for code,label in m.MAPPINGS[row['mapping']].items():
            row['selection']['option_logprobs'][code]=math.log((.6 if index<4 else .0001) if label=='supported' else .3 if label=='unsupported' else .01)
    assert m.aggregate(rows)['label']=='unsupported'


@pytest.mark.parametrize('fault',['missing','duplicate','failed','nonfinite','tie'])
def test_failure_and_final_tie_never_become_unsupported(fault):
    rows=rows_for(dict(zip(m.LABELS,[-2.,-1.,-3.])))
    if fault=='missing':rows.pop()
    if fault=='duplicate':rows[-1]=rows[0]
    if fault=='failed':rows[0]['status']='failed'
    if fault=='nonfinite':rows[0]['selection']['option_logprobs']['1']=float('-inf')
    if fault=='tie':rows=rows_for(dict(zip(m.LABELS,[-1.,-1.,-3.])))
    assert m.aggregate(rows)['label'] is None


def test_individual_tie_is_retained_for_mean_and_valid_greedy_tie_is_allowed():
    rows=rows_for(dict(zip(m.LABELS,[-2.,-1.,-3.])))
    rows[0]['selection']['option_logprobs']={'1':-1.,'2':-1.,'3':-3.}
    assert m.aggregate(rows)['label']=='unsupported'
    response=dict(tokens=[1],completion_probabilities=[dict(top_logprobs=[dict(id=i,logprob=v) for i,v in enumerate([-1.,-1.,-2.])])])
    selected=m.base.select(response,3,{'1':0,'2':1,'3':2},allow_ties=True)
    assert selected['option_tie'] and selected['code'] is None


def test_either_A_correct_union_must_all_survive_and_unresolved_counts():
    criteria=dict(expected={'normal':'supported','protected':'unsupported','gain':'unsupported','H07':None},protected=['normal','protected'],both_A_wrong=['gain'])
    cases=[dict(id=id,label=label) for id,label in criteria['expected'].items()]
    assert m.gate(cases,criteria)['passed']
    cases[1]['label']=None
    result=m.gate(cases,criteria)
    assert not result['passed'] and result['denominator']==3 and 'protected' in result['damaged_protected']

"""Decision scores, source contracts and gates must not turn format failures into gains."""
import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('label_selection',SCRIPTS/'compare_business_label_selection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def response(probs):
    return {'tokens':[max(range(len(probs)),key=probs.__getitem__)],
            'completion_probabilities':[{'top_logprobs':[{'id':i,'logprob':math.log(p)} for i,p in enumerate(probs)]}]}


def test_relative_selection_is_not_native_greedy_or_correctness_probability():
    r=m.select(response([.2,.1,.05,.65]),4,{'1':0,'2':1,'3':2})
    assert r['code']=='1' and r['native_greedy_outside_options']
    assert r['option_mass']==pytest.approx(.35)
    assert r['relative_option_preferences']['1']==pytest.approx(4/7)
    assert r['margin']==pytest.approx(math.log(2))
    assert not r['correctness_probability']


@pytest.mark.parametrize('kind',['duplicate','nonfinite','tie'])
def test_invalid_distribution_is_not_unsupported(kind):
    r=response([.2,.1,.05,.65])
    values=r['completion_probabilities'][0]['top_logprobs']
    if kind=='duplicate':values[3]['id']=0
    if kind=='nonfinite':values[2]['logprob']=float('-inf')
    if kind=='tie':values[1]['logprob']=values[0]['logprob']
    with pytest.raises(ValueError):m.select(r,4,{'1':0,'2':1,'3':2})


def gate_rows(a_error_label):
    expected={'n':'supported','H02':'contradicted','A02':'unsupported','e':'unsupported','H07':None}
    criteria=dict(expected=expected,normal=['n'])
    rows=[]
    for id,label in expected.items():
        rows.extend([dict(id=id,arm='A',readable_label=a_error_label if id=='e' else label),
                     dict(id=id,arm='B',label=label)])
    return rows,criteria


def test_format_only_difference_cannot_pass_promotion_gate():
    rows,criteria=gate_rows(None)
    assert not m.check_gate(rows,criteria)['passed']
    rows,criteria=gate_rows('supported')
    assert m.check_gate(rows,criteria)['passed']
    rows[1]['label']='unsupported'
    assert not m.check_gate(rows,criteria)['passed']


def test_a_requires_real_fields_and_verbatim_source():
    case=dict(raw={'Event':'본문'},blocks=[dict(id='b1',text='첫째\n둘째')])
    answer=dict(label='1',error_fields=[],evidence=[dict(block_id='b1',quote='첫째\n둘째')],reason='의미 보존')
    content=json.dumps(answer,ensure_ascii=False,separators=(',',':'))[len(m.PREFIX):]
    assert m.parse_a(content,case,m.MAPPINGS['primary'])==answer
    answer['evidence'][0]['quote']='첫째 둘째'
    with pytest.raises(ValueError,match='nonverbatim'):
        m.parse_a(json.dumps(answer,ensure_ascii=False,separators=(',',':'))[len(m.PREFIX):],case,m.MAPPINGS['primary'])


def test_incomplete_a_generation_cannot_create_semantic_gain():
    rows,criteria=gate_rows('supported')
    next(r for r in rows if r['id']=='e' and r['arm']=='A')['generation_incomplete']=True
    assert not m.check_gate(rows,criteria)['passed']


def test_first_position_must_match_returned_greedy_token():
    r=response([.2,.1,.05,.65]);r['tokens']=[0]
    with pytest.raises(ValueError,match='first_position'):
        m.select(r,4,{'1':0,'2':1,'3':2})

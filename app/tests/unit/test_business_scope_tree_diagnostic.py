"""Synthetic Boolean/address contracts only; not a semantic evaluation set."""
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('scope_diagnostic',SCRIPTS/'compare_business_scope_tree.py')
scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
sys.path.remove(str(SCRIPTS))


def structure(prefix,conditions,effects,guard):
    return dict(atoms=[dict(id=x,kind='condition') for x in conditions]+[dict(id=x,kind='effect') for x in effects],
        branches=[dict(id=prefix,guard=guard,effects=effects)])


def literal(atom,positive=True):
    return dict(atom=atom,positive=positive)


def setup_pair():
    source=structure('s',['s:p'],['s:x','s:y'],[[literal('s:p')]])
    claim=structure('c',['c:q'],['c:x'],[[literal('c:q')]])
    mapping=dict(condition_links=[dict(source='s:p',claim='c:q',relation='equivalent')],
        effect_links=[dict(claim='c:x',entails=['s:x'],opposes=[],unrelated=['s:y'],unknown=[])])
    return source,claim,mapping


def test_directional_constraints_and_partial_effects():
    source,claim,mapping=setup_pair()
    assert scope.compare(source,claim,mapping)['verdict']=='S'  # Additional source effect need not be claimed.
    mapping['condition_links'][0]['relation']='claim_implies_source'
    assert scope.compare(source,claim,mapping)['verdict']=='S'
    mapping['condition_links'][0]['relation']='source_implies_claim'
    result=scope.compare(source,claim,mapping)
    assert result['verdict']=='N'
    assert result['trace'][0]['scope_witness']=={'c:q':True,'s:p':False}


def test_explicit_exclusion_does_not_create_outside_refutation():
    source,claim,mapping=setup_pair()
    source['branches'][0]['guard']=[[literal('s:p',False)]]
    result=scope.compare(source,claim,mapping)
    assert result['verdict']=='N' and result['trace'][0]['opposed_worlds']==0
    mapping['effect_links'][0].update(entails=[],opposes=['s:x'])
    source['branches'][0]['guard']=[[literal('s:p')]]
    assert scope.compare(source,claim,mapping)['verdict']=='R'


def test_unknown_is_failure_and_contradictory_guards_do_not_vacuously_pass():
    source,claim,mapping=setup_pair()
    mapping['condition_links'][0]['relation']='unknown'
    with pytest.raises(ValueError,match='condition_mapping_unknown'):scope.compare(source,claim,mapping)
    mapping['condition_links'][0]['relation']='equivalent'
    mapping['effect_links'][0].update(unrelated=[],unknown=['s:y'])
    with pytest.raises(ValueError,match='effect_mapping_unknown'):scope.compare(source,claim,mapping)
    mapping['effect_links'][0].update(unrelated=['s:y'],unknown=[])
    claim['branches'][0]['guard']=[[literal('c:q'),literal('c:q',False)]]
    with pytest.raises(ValueError,match='vacuous_claim_guard'):scope.compare(source,claim,mapping)


def test_boolean_or_and_unconditional_guard():
    assert scope.active([[]],{})
    guard=[[literal('p'),literal('q')],[literal('r',False)]]
    assert scope.active(guard,dict(p=True,q=True,r=True))
    assert scope.active(guard,dict(p=False,q=True,r=False))
    assert not scope.active(guard,dict(p=True,q=False,r=True))


def test_exact_spans_and_unsupported_status():
    original=dict(blocks=[dict(id='b',text='조건이면 항목을 갖춘다.')])
    doc=dict(id='d',status='complete',coverage=[dict(block_id='b',status='extracted')],
        atoms=[dict(id='d:a',kind='effect',modality='required_item',refs=[dict(block_id='b',quote='항목')])],
        branches=[dict(id='b1',guard=[[]],effects=['d:a'])])
    scope.validate(doc,original)
    doc['atoms'][0]['refs'][0]['quote']='없는 문구'
    with pytest.raises(ValueError,match='nonunique_or_absent_span'):scope.validate(doc,original)
    doc['status']='unsupported'
    with pytest.raises(ValueError,match='parser_unsupported'):scope.validate(doc,original)

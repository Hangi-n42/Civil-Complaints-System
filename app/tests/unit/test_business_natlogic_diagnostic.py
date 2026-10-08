"""Generic composition/address checks; none are model-quality labels."""
import importlib.util
from itertools import combinations, product
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('natlogic', Path(__file__).resolve().parents[3]/'scripts/compare_business_natlogic.py')
nl=importlib.util.module_from_spec(spec)
spec.loader.exec_module(nl)


def test_dfa_never_asserts_false_support_or_refutation_on_finite_sets():
    universe={0,1,2}
    sets=[set(x) for n in range(1,4) for x in combinations(universe,n)]
    for premise, current, following in product(sets,repeat=3):
        state='S' if premise <= current else 'R' if premise.isdisjoint(current) else 'N'
        relationships=dict(equivalent=current==following, forward=current<following,
            reverse=current>following, negation=current.isdisjoint(following) and current|following==universe,
            alternation=current.isdisjoint(following) and current|following!=universe)
        for op, holds in relationships.items():
            if not holds: continue
            verdict=nl.TRANSITIONS[state][op]
            if verdict=='S': assert premise <= following
            if verdict=='R': assert premise.isdisjoint(following)
    assert nl.compose(['negation','negation'])[0]=='S'
    assert nl.compose(['reverse','negation'])[0]=='N'
    with pytest.raises(ValueError,match='empty_proof'):nl.compose([])


def test_hard_labels_do_not_turn_uncertainty_into_document_nei():
    votes={op:['no','no'] for op in nl.PRIORITY}
    assert nl.select_operator(votes,'unclear')[0]=='independent'
    votes['reverse']=['yes','yes']
    assert nl.compose([nl.select_operator(votes,'unclear')[0]])[0]=='N'
    votes['equivalent']=['yes','yes']
    assert nl.select_operator(votes,'unclear')[0]=='equivalent'
    votes['equivalent']=['yes','no']
    votes['reverse']=['no','no']
    assert nl.select_operator(votes,'unclear')[2]=='microjudgment_disagreement'
    votes['equivalent']=['unknown','no']
    assert nl.select_operator(votes,'unclear')[0] is None


def test_unicode_partition_and_exact_source_address_preserve_raw_text():
    candidate=dict(id='synthetic',hypothesis='  한글 조건이면 문서(가)를 낸다. ')
    units=nl.tokens(candidate['hypothesis'])
    assert ''.join(units)==candidate['hypothesis']
    block=dict(id='b',text='상위 조건\n문서(가)를 낸다.')
    part=dict(end=len(units),evidence=[dict(block_id='b',quote=block['text'])],signal='unclear',scope_supported=True,reason='test')
    pair=nl.aligned_pairs(candidate,[part],[block])[0]
    assert pair['claim_span']==candidate['hypothesis']
    assert pair['evidence'][0]['end_char']==len(block['text'])
    with pytest.raises(ValueError,match='incomplete_coverage'):
        nl.aligned_pairs(candidate,[dict(part,end=len(units)-1)],[block])
    with pytest.raises(ValueError,match='partition_boundary'):
        nl.aligned_pairs(candidate,[dict(part,end=0)],[block])
    with pytest.raises(ValueError,match='nonunique_or_absent_evidence'):
        nl.aligned_pairs(candidate,[part],[dict(block,text=block['text']*2)])

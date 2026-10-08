"""Generic completeness and evidence contracts; no semantic gold examples."""
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('qa_diagnostic',SCRIPTS/'compare_business_qa.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
sys.path.remove(str(SCRIPTS))


def test_missing_duplicate_and_unknown_cannot_be_removed_from_denominator():
    with pytest.raises(ValueError):qa.exact_rows([dict(id='q')],['q','r'])
    with pytest.raises(ValueError):qa.exact_rows([dict(id='q'),dict(id='q')],['q','q'])
    ok=dict(valid_question=True,verdict='supported')
    assert qa.aggregate([ok],True)=='S'
    assert qa.aggregate([ok],False) is None
    assert qa.aggregate([],True) is None
    assert qa.aggregate([ok,dict(valid_question=True,verdict='unresolved')],True) is None
    assert qa.aggregate([dict(valid_question=False,verdict='not_supported')],True) is None
    assert qa.aggregate([ok,dict(valid_question=True,verdict='not_supported')],True)=='N'
    assert qa.aggregate([dict(valid_question=True,verdict='contradicted')],True)=='R'


def test_whole_cited_block_and_parent_are_preserved_without_rewriting_answer():
    blocks=[dict(id='h',text='특정 조건'),dict(id='b',text='항목 (적용 한정)'),dict(id='x',text='다른 내용')]
    parents=[dict(block_id='b',parent_block_ids=['h'])]
    answer=dict(answerable=True,answer='항목',evidence=[dict(block_id='b',quote='항목')])
    expanded=qa.grounded_answer(answer,blocks,parents)
    assert expanded['cited_blocks']==blocks[:2]
    assert expanded['answer']==answer['answer']
    assert expanded['source_parents']==parents
    with pytest.raises(ValueError,match='nonunique_or_absent_evidence'):
        qa.grounded_answer(dict(answer,evidence=[dict(block_id='b',quote='없는 문구')]),blocks,parents)
    with pytest.raises(ValueError,match='answer_without_evidence'):
        qa.grounded_answer(dict(answer,evidence=[]),blocks,parents)

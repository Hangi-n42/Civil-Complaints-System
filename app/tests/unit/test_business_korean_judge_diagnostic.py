"""Reasoning boundaries and exact evidence must not be mistaken for valid judgments."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('korean_judge', SCRIPTS / 'compare_business_korean_judge.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CASE = {'id': 'x', 'raw': {'Event': '예약 가능'}, 'blocks': [{'id': 'b1', 'text': '예약\n가능'}]}
ANSWER = dict(id='x', label='supported', error_fields=[], evidence=[{'block_id': 'b1', 'quote': '예약\n가능'}], reason='가능을 보존함')


def response(answer=ANSWER):
    return dict(content='검토 중 <|im_end|>\n<|im_start|>assistant\n'+json.dumps(answer, ensure_ascii=False), stop_type='word', truncated=False)


def test_official_template_preserves_reasoning_and_final_boundary():
    text = module.prompt(CASE)
    assert text.startswith('<|im_start|>tool_list\n<|im_end|>\n<|im_start|>system\n')
    assert text.endswith('<|im_end|>\n<|im_start|>assistant/think\n')
    assert '<|im_end|>' not in module.SETTINGS['stop']
    assert module.parse_answer(response(), CASE) == ANSWER


def test_missing_final_boundary_and_truncation_are_not_semantic_labels():
    with pytest.raises(ValueError, match='boundary'):
        module.parse_answer(dict(content=json.dumps(ANSWER)), CASE)
    with pytest.raises(ValueError, match='limit'):
        module.parse_answer(dict(response(), stop_type='limit'), CASE)


@pytest.mark.parametrize('change', [
    {'id':'other'}, {'label':'incorrect'}, {'error_fields':['invented']},
    {'label':'unsupported', 'error_fields':[]},
    {'evidence':[{'block_id':'b1','quote':'예약 가능'}]},
    {'evidence':[{'block_id':'wrong','quote':'예약'}]},
])
def test_invalid_identity_fields_and_nonverbatim_quote_fail(change):
    with pytest.raises(ValueError):
        module.parse_answer(response(dict(ANSWER, **change)), CASE)

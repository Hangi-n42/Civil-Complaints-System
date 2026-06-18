from __future__ import annotations

import json

import pytest

from app.evaluation.civil_llm_rubric import CivilComplaintRubricEvaluator


@pytest.mark.asyncio
async def test_runtime_rubric_runs_rule_fallback_and_applies_missing_citation_cap():
    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=False)

    result = await evaluator.evaluate(
        case_id="CMP-1",
        complaint_text="가로등 고장으로 야간 보행이 불편합니다. 처리 절차를 알려주세요.",
        generated_answer=(
            "1. 귀하의 민원 내용을 확인했습니다.\n\n"
            "3. 검토 의견은 다음과 같습니다. 담당부서에서 현장을 확인하고 처리 절차를 안내드리겠습니다.\n\n"
            "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시기 바랍니다."
        ),
        references=[],
        citations=[],
        citation_validation={"is_valid": False, "mismatch_count": 0},
    )

    assert result["judge_status"] == "rule_fallback"
    assert result["rule_features"]["postprocessed_citation_count"] == 0
    assert result["safety_layer"]["cap_reason"] == "missing_citation"
    assert result["safety_layer"]["final_q0_score_0_10"] <= 4.0
    assert result["diagnostics"]["human_review_required"] is True
    assert set(result["llm_rubric_raw"].keys()) == {
        "q0",
        "q1",
        "q2",
        "q3",
        "q4",
        "q5",
        "q6",
        "q7",
    }


@pytest.mark.asyncio
async def test_runtime_rubric_uses_independent_q_prompts_and_q2_reference_only():
    prompts: list[str] = []

    async def fake_llm_call(prompt: str, **kwargs):
        prompts.append(prompt)
        return json.dumps({"choice": 4, "confidence": 0.8})

    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=True)
    result = await evaluator.evaluate(
        case_id="CMP-2",
        complaint_text="도로 파손과 불법 주차로 위험합니다.",
        generated_answer="검토 의견은 다음과 같습니다. 도로 파손은 현장 확인 후 보수 가능 여부를 안내드립니다.",
        references=[
            {
                "doc_id": "DOC-1",
                "case_id": "CASE-1",
                "title": "도로 보수 처리 기준",
                "snippet": "도로 파손 민원은 현장 확인 후 담당 부서에서 보수 여부를 검토합니다.",
            }
        ],
        citations=[
            {
                "doc_id": "DOC-1",
                "source": "retrieval",
                "quote": "도로 파손 민원은 현장 확인 후 검토합니다.",
            }
        ],
        citation_validation={"is_valid": True, "mismatch_count": 0},
        llm_call=fake_llm_call,
    )

    assert result["judge_status"] == "llm_judge"
    assert len(prompts) == 8
    assert "[생성 답변]" in prompts[0]
    assert "[생성 답변]" not in prompts[2]
    assert result["llm_rubric_raw"]["q0"]["source"] == "llm_judge_synthetic_probs"
    assert result["llm_rubric_raw"]["q0"]["argmax"] == 4

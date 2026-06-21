from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from app.evaluation.ares_lite import AresLiteCase, AresLiteCitation, AresLiteContext, AresLiteEvaluator
from app.evaluation.ares_lite.report_builder import (
    build_ares_lite_report,
    merge_ares_lite_summary_into_rubric_report,
)


def test_ares_lite_scores_relevant_grounded_answer_high():
    case = AresLiteCase(
        case_id="CASE-1",
        query="도로 파손으로 차량 통행이 위험하고 보행자 안전도 우려됩니다.",
        request_segments=["도로 파손으로 인한 차량 통행 위험", "보행자 안전 우려"],
        retrieved_contexts=[
            AresLiteContext(
                context_id="CTX-1",
                content="도로 파손 민원은 현장 확인 후 보수 가능 여부를 검토하고 보행자 안전 조치를 안내합니다.",
                rank=1,
                score=0.91,
            )
        ],
        generated_answer=(
            "3. 검토 의견은 다음과 같습니다. 도로 파손으로 인한 차량 통행 위험과 보행자 안전 우려에 대해 "
            "담당부서에서 현장 확인 후 보수 가능 여부를 검토하고 필요한 안전 조치를 안내드리겠습니다."
        ),
        citations=[
            AresLiteCitation(
                doc_id="CTX-1",
                quote="도로 파손 민원은 현장 확인 후 보수 가능 여부를 검토하고 보행자 안전 조치를 안내합니다.",
            )
        ],
    )

    result = AresLiteEvaluator().evaluate(case)["ares_lite"]

    assert result["context_relevance"]["average_score"] >= 7.0
    assert result["context_relevance"]["metric"] == "context_relevance"
    assert result["answer_faithfulness"]["metric"] == "answer_faithfulness"
    assert result["answer_relevance"]["metric"] == "answer_relevance"
    assert result["answer_relevance"]["missing_segments"] == []
    assert result["answer_relevance"]["missing_points"] == []
    assert result["answer_faithfulness"]["unsupported_claims"] == []
    assert result["rubric_connections"]["answer_relevance"] == [
        "q0.overall_quality",
        "manual_completeness_features",
        "q7.conciseness_if_overlong",
    ]
    assert result["evaluation_scope"]["mode"] == "ares_lite_rule_fallback"
    assert result["evaluation_scope"]["llm_judge_used"] is False
    assert result["risk_level"] in {"low", "medium"}


def test_ares_lite_llm_judge_path_uses_document_metrics():
    async def fake_llm_call(prompt: str, **kwargs):
        schema = kwargs.get("response_schema") or {}
        properties = schema.get("properties", {})
        if "unsupported_claims" in properties:
            return json.dumps(
                {
                    "score": 6.0,
                    "label": "partially_grounded",
                    "unsupported_claims": [
                        {
                            "sentence": "다음 주까지 보수 완료될 예정입니다.",
                            "reason": "검색 근거에 구체 일정이 없음",
                        }
                    ],
                    "revision_hint": "확정 일정을 조건부 검토 표현으로 바꾸세요.",
                },
                ensure_ascii=False,
            )
        if "missing_points" in properties:
            return json.dumps(
                {
                    "score": 7.0,
                    "label": "mostly_relevant",
                    "missing_points": ["불법 주정차 위험"],
                    "revision_hint": "불법 주정차 위험에 대한 안내를 추가하세요.",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "score": 8.0,
                "label": "relevant",
                "reason": "도로 파손과 통행 위험 근거가 직접 관련됨",
            },
            ensure_ascii=False,
        )

    case = AresLiteCase(
        case_id="CASE-LLM",
        query="도로 파손과 불법 주정차로 위험합니다.",
        request_segments=["도로 파손 위험", "불법 주정차 위험"],
        retrieved_contexts=[
            AresLiteContext(
                context_id="CTX-1",
                content="도로 파손 민원은 현장 확인 후 보수 가능 여부를 검토합니다.",
            )
        ],
        generated_answer="도로 파손은 다음 주까지 보수 완료될 예정입니다.",
    )

    result = asyncio.run(AresLiteEvaluator(judge_mode="separate").evaluate_async(case, llm_call=fake_llm_call))[
        "ares_lite"
    ]

    assert result["evaluation_scope"]["mode"] == "ares_lite_llm_judge"
    assert result["evaluation_scope"]["llm_judge_used"] is True
    assert result["context_relevance"]["contexts"][0]["source"] == "llm_judge"
    assert result["answer_faithfulness"]["unsupported_claims"][0]["reason"] == "검색 근거에 구체 일정이 없음"
    assert result["answer_relevance"]["missing_points"] == ["불법 주정차 위험"]


def test_ares_lite_integrated_llm_judge_is_default():
    calls = []

    async def fake_llm_call(prompt: str, **kwargs):
        calls.append({"prompt": prompt, "schema": kwargs.get("response_schema")})
        return json.dumps(
            {
                "context_relevance": {
                    "average_score": 8.0,
                    "label": "relevant",
                    "contexts": [
                        {
                            "context_id": "CTX-1",
                            "score": 8.0,
                            "label": "relevant",
                            "reason": "directly related to the damaged road complaint",
                        }
                    ],
                    "low_relevance_contexts": [],
                    "revision_hint": "",
                },
                "answer_faithfulness": {
                    "score": 6.0,
                    "label": "partially_grounded",
                    "unsupported_claims": [
                        {
                            "sentence": "next week repair is guaranteed",
                            "reason": "the schedule is not visible in the evidence",
                        }
                    ],
                    "revision_hint": "rewrite fixed schedules as conditional review language",
                },
                "answer_relevance": {
                    "score": 7.0,
                    "label": "mostly_relevant",
                    "covered_segments": ["road damage"],
                    "missing_points": ["illegal parking risk"],
                    "revision_hint": "mention the parking risk segment",
                },
            },
            ensure_ascii=False,
        )

    case = AresLiteCase(
        case_id="CASE-INTEGRATED",
        query="road damage and illegal parking risk",
        request_segments=["road damage", "illegal parking risk"],
        retrieved_contexts=[
            AresLiteContext(context_id="CTX-1", content="road damage should be inspected before repair")
        ],
        generated_answer="3. repair will be completed next week.",
    )

    result = asyncio.run(AresLiteEvaluator().evaluate_async(case, llm_call=fake_llm_call))["ares_lite"]

    assert len(calls) == 1
    assert result["evaluation_scope"]["mode"] == "ares_lite_llm_integrated_judge"
    assert result["evaluation_scope"]["llm_judge_used"] is True
    assert result["context_relevance"]["contexts"][0]["source"] == "llm_integrated_judge"
    assert result["answer_faithfulness"]["unsupported_claims"][0]["reason"] == (
        "the schedule is not visible in the evidence"
    )
    assert result["answer_relevance"]["missing_points"] == ["illegal parking risk"]


def test_ares_lite_detects_unsupported_schedule_and_missing_segment():
    case = AresLiteCase(
        case_id="CASE-2",
        query="도로 파손과 불법 주정차로 위험합니다.",
        request_segments=["도로 파손 위험", "불법 주정차 위험"],
        retrieved_contexts=[
            AresLiteContext(
                context_id="CTX-1",
                content="도로 파손 민원은 현장 확인 후 보수 가능 여부를 검토합니다.",
                rank=1,
            )
        ],
        generated_answer=(
            "3. 검토 의견은 다음과 같습니다. 도로 파손은 다음 주까지 보수 완료될 예정입니다. "
            "담당부서에서 현장 확인을 진행하겠습니다."
        ),
        citations=[],
    )

    result = AresLiteEvaluator().evaluate(case)["ares_lite"]

    assert result["answer_faithfulness"]["score"] < 6.0
    assert result["answer_faithfulness"]["unsupported_claims"]
    assert result["answer_relevance"]["missing_segments"] == ["불법 주정차 위험"]
    assert result["risk_level"] == "high"


def test_ares_lite_report_builder_summarizes_results():
    evaluator = AresLiteEvaluator()
    results = [
        evaluator.evaluate(
            AresLiteCase(
                case_id="CASE-1",
                query="가로등 고장",
                retrieved_contexts=[AresLiteContext(context_id="CTX-1", content="가로등 고장 현장 확인")],
                generated_answer="가로등 고장은 현장 확인 후 조치 가능 여부를 안내드립니다.",
            )
        )
    ]

    report = build_ares_lite_report(results)

    assert report["tool"] == "ares_lite"
    assert report["case_count"] == 1
    assert "overall_average" in report["summary"]
    assert report["rubric_connections"]["answer_relevance"][0] == "q0.overall_quality"


def test_ares_lite_report_can_be_merged_into_rubric_report():
    ares_report = build_ares_lite_report(
        [
            {
                "case_id": "CASE-1",
                "ares_lite": {
                    "overall_score": 7.0,
                    "risk_level": "medium",
                    "recommended_revision": ["근거 보강"],
                    "context_relevance": {"average_score": 7.0},
                    "answer_faithfulness": {"score": 6.0},
                    "answer_relevance": {"score": 8.0},
                },
            }
        ]
    )

    merged = merge_ares_lite_summary_into_rubric_report(
        {"rubric_version": "civil_llm_rubric_q0_q7_v1.0"},
        ares_report,
    )

    assert merged["rubric_version"] == "civil_llm_rubric_q0_q7_v1.0"
    assert merged["ares_lite_summary"]["summary"]["overall_average"] == 7.0
    assert merged["ares_lite_summary"]["rubric_connections"]["answer_relevance"][1] == "manual_completeness_features"


def test_ares_lite_cli_writes_report_and_scores(tmp_path):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "report.json"
    scores_path = tmp_path / "scores.jsonl"
    rubric_report_path = tmp_path / "rubric_report.json"
    merged_rubric_path = tmp_path / "rubric_report_with_ares.json"
    input_path.write_text(
        json.dumps(
            {
                "case_id": "CASE-CLI",
                "query": "도로 파손 위험",
                "retrieved_contexts": [
                    {"context_id": "CTX-1", "content": "도로 파손은 현장 확인 후 보수 여부를 검토합니다."}
                ],
                "answer": "도로 파손은 현장 확인 후 보수 여부를 검토하겠습니다.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    rubric_report_path.write_text(
        json.dumps({"rubric_version": "civil_llm_rubric_q0_q7_v1.0"}, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_ares_lite_civil_replies.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--scores-output",
            str(scores_path),
            "--use-rule-fallback",
            "--rubric-report",
            str(rubric_report_path),
            "--merged-rubric-output",
            str(merged_rubric_path),
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=True,
    )

    assert completed.returncode == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    scores = scores_path.read_text(encoding="utf-8").strip().splitlines()
    merged_rubric = json.loads(merged_rubric_path.read_text(encoding="utf-8"))
    assert report["case_count"] == 1
    assert len(scores) == 1
    assert merged_rubric["ares_lite_summary"]["case_count"] == 1

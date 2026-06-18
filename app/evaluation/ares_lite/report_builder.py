"""Report helpers for ARES-lite evaluation runs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

ARES_LITE_RUBRIC_CONNECTIONS = {
    "context_relevance": ["q2.reference_adequacy", "retrieval_failure_diagnostic"],
    "answer_faithfulness": ["q2.reference_adequacy", "q4.citation_support", "semantic_risk_flags"],
    "answer_relevance": ["q0.overall_quality", "manual_completeness_features", "q7.conciseness_if_overlong"],
}


def build_ares_lite_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [item for item in results if isinstance(item.get("ares_lite"), dict)]
    risk_counts = Counter(item["ares_lite"].get("risk_level", "unknown") for item in scored)

    def average(path: tuple[str, ...]) -> float:
        values = []
        for item in scored:
            current: Any = item
            for key in path:
                current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, (int, float)):
                values.append(float(current))
        return round(fmean(values), 2) if values else 0.0

    low_cases = [
        {
            "case_id": item.get("case_id"),
            "overall_score": item["ares_lite"].get("overall_score"),
            "risk_level": item["ares_lite"].get("risk_level"),
            "recommended_revision": item["ares_lite"].get("recommended_revision", []),
        }
        for item in scored
        if item["ares_lite"].get("risk_level") in {"high", "medium"}
    ]

    return {
        "tool": "ares_lite",
        "version": "ares_lite_civil_v1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(scored),
        "rubric_connections": ARES_LITE_RUBRIC_CONNECTIONS,
        "scope": {
            "mode": "offline_rule_based_ares_lite",
            "llm_judge_used": False,
            "notes": [
                "ARES-lite는 LLM-Rubric을 대체하지 않고 RAG 원인 진단 신호로 사용합니다.",
                "현재 LLM-Rubric은 Q0~Q7 구조이므로 Q0/manual_completeness/Q7 보조 신호로 연결합니다.",
            ],
        },
        "summary": {
            "overall_average": average(("ares_lite", "overall_score")),
            "context_relevance_average": average(("ares_lite", "context_relevance", "average_score")),
            "answer_faithfulness_average": average(("ares_lite", "answer_faithfulness", "score")),
            "answer_relevance_average": average(("ares_lite", "answer_relevance", "score")),
            "risk_counts": dict(risk_counts),
        },
        "low_cases": low_cases[:100],
        "results": results,
    }


def merge_ares_lite_summary_into_rubric_report(
    rubric_report: dict[str, Any],
    ares_report: dict[str, Any],
) -> dict[str, Any]:
    """Attach ARES-lite summary to an existing LLM-Rubric report object."""
    merged = dict(rubric_report)
    merged["ares_lite_summary"] = {
        "tool": ares_report.get("tool"),
        "version": ares_report.get("version"),
        "generated_at": ares_report.get("generated_at"),
        "case_count": ares_report.get("case_count"),
        "summary": ares_report.get("summary", {}),
        "rubric_connections": ares_report.get("rubric_connections", ARES_LITE_RUBRIC_CONNECTIONS),
        "low_cases": ares_report.get("low_cases", []),
    }
    return merged

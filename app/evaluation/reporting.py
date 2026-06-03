"""검색 평가 실행 요약 리포트 유틸리티."""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.artifacts import append_jsonl


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
    ordered = sorted(values)
    return {
        "p50": round(_percentile(ordered, 50), 2),
        "p95": round(_percentile(ordered, 95), 2),
        "p99": round(_percentile(ordered, 99), 2),
        "avg": round(statistics.fmean(ordered), 2),
    }


def build_gate(metrics: dict[str, float], latency_ms: dict[str, float]) -> dict[str, Any]:
    recall_10 = metrics.get("R@10", metrics.get("Recall@10", metrics.get("recall_at_10", 0.0)))
    ndcg_10 = metrics.get("nDCG@10", metrics.get("nDCG@10(rel=2)", 0.0))
    latency_p95 = latency_ms.get("p95", 0.0)
    checks = [
        {"name": "recall_at_10_present", "label": "Recall@10 산출 여부", "passed": recall_10 >= 0.0, "value": recall_10},
        {"name": "ndcg_at_10_present", "label": "nDCG@10 산출 여부", "passed": ndcg_10 >= 0.0, "value": ndcg_10},
        {
            "name": "latency_p95_budget",
            "label": "p95 지연 시간 예산 준수 여부",
            "passed": latency_p95 <= 12000,
            "value": latency_p95,
            "threshold": 12000,
        },
    ]
    return {"checks": checks, "all_passed": all(bool(check["passed"]) for check in checks)}


def append_run_summary(path: str | Path, summary: dict[str, Any]) -> None:
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        **summary,
    }
    append_jsonl(path, row)


def _percentile(ordered_values: list[float], percentile: int) -> float:
    if len(ordered_values) == 1:
        return ordered_values[0]
    rank = (len(ordered_values) - 1) * (percentile / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered_values) - 1)
    fraction = rank - lower
    return ordered_values[lower] + (ordered_values[upper] - ordered_values[lower]) * fraction


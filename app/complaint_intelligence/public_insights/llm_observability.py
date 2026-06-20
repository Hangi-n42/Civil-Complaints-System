"""PublicAgencyInsight Local LLM 운영 관측 리포트."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app.complaint_intelligence.repository import AnalysisRunRecord


def build_llm_observability_report(runs: list[AnalysisRunRecord]) -> dict[str, Any]:
    """분석 run metadata의 llm_metrics만 사용해 운영 관측 지표를 집계한다."""

    sorted_runs = sorted(runs, key=lambda item: item.started_at)
    metrics_list = [
        run.metadata.get("llm_metrics")
        for run in sorted_runs
        if isinstance(run.metadata.get("llm_metrics"), dict)
    ]
    provider_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    error_type_counts: Counter[str] = Counter()
    durations: list[float] = []
    actionability_scores: list[float] = []
    grounding_scores: list[float] = []
    confidence_scores: list[float] = []
    quality_gate_total = 0
    quality_gate_pass = 0
    grounding_total = 0
    grounding_pass = 0
    total_candidates = 0
    total_attempts = 0
    total_fallbacks = 0
    total_timeouts = 0
    total_slow = 0
    total_discarded = 0

    for metrics in metrics_list:
        provider = str(metrics.get("llm_provider") or "unknown")
        model = str(metrics.get("llm_model") or "unknown")
        provider_counts[provider] += 1
        model_counts[model] += 1
        total_candidates += int(metrics.get("candidate_trace_count") or metrics.get("candidate_count") or 0)
        total_attempts += int(metrics.get("llm_attempt_count") or 0)
        total_fallbacks += int(metrics.get("fallback_count") or 0)
        total_slow += int(metrics.get("slow_llm_count") or 0)
        total_discarded += int(metrics.get("discarded_count") or 0)

        errors = metrics.get("error_types") or {}
        if isinstance(errors, dict):
            for error_type, count in errors.items():
                safe_count = int(count or 0)
                error_type_counts[str(error_type)] += safe_count
                if str(error_type) == "TimeoutError":
                    total_timeouts += safe_count

        traces = metrics.get("candidate_traces") or []
        if isinstance(traces, list):
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                _append_number(durations, trace.get("llm_duration_ms"))
                _append_number(actionability_scores, trace.get("avg_actionability_score"))
                _append_number(grounding_scores, trace.get("grounding_score"))
                _append_number(confidence_scores, trace.get("confidence"))
                if "quality_gate_failures" in trace:
                    quality_gate_total += 1
                    if not trace.get("quality_gate_failures") and trace.get("path") != "discarded":
                        quality_gate_pass += 1
                if isinstance(trace.get("grounding_score"), (int, float)):
                    grounding_total += 1
                    if float(trace["grounding_score"]) >= 0.65:
                        grounding_pass += 1

    period_start, period_end = _period(sorted_runs)
    duration_count = len(durations)
    denominator = max(1, total_candidates)
    return {
        "run_count": len(sorted_runs),
        "llm_run_count": len(metrics_list),
        "provider_counts": dict(sorted(provider_counts.items())),
        "model_counts": dict(sorted(model_counts.items())),
        "quality_gate_pass_rate": _rate(quality_gate_pass, quality_gate_total),
        "grounding_pass_rate": _rate(grounding_pass, grounding_total),
        "fallback_rate": _rate(total_fallbacks, denominator),
        "timeout_rate": _rate(total_timeouts, max(1, total_attempts)),
        "error_type_counts": dict(sorted(error_type_counts.items())),
        "avg_llm_duration_ms": _avg(durations),
        "p95_llm_duration_ms": _percentile(durations, 0.95),
        "slow_llm_rate": _rate(total_slow, max(1, duration_count)),
        "avg_actionability_score": _avg(actionability_scores),
        "avg_grounding_score": _avg(grounding_scores),
        "avg_confidence": _avg(confidence_scores),
        "discarded_count": total_discarded,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
    }


def _append_number(target: list[float], value: Any) -> None:
    if isinstance(value, (int, float)):
        target.append(float(value))


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return round(ordered[index], 4)


def _period(runs: list[AnalysisRunRecord]) -> tuple[datetime | None, datetime | None]:
    if not runs:
        return None, None
    return runs[0].started_at, runs[-1].completed_at or runs[-1].started_at

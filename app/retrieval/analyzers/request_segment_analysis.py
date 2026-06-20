"""request_segments analyzer runtime selector.

규칙 기반 analyzer를 기본값으로 유지하되, 설정이 명시적으로 켜진 경우에만
LLM hybrid wrapper를 호출한다. 외부 API 계약은 바꾸지 않고 호출부의 진입점만
한 곳으로 모으기 위한 얇은 선택 계층이다.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.retrieval.analyzers.complexity_analyzer import (
    build_analyzer_output,
    is_request_segments_low_confidence,
)


def build_request_segment_analysis(
    text: str,
    topic_type: str = "general",
    *,
    title: str | None = None,
    question: str | None = None,
) -> dict:
    """설정에 따라 rule-only 또는 LLM hybrid request_segments 분석을 실행한다."""
    mode = str(settings.REQUEST_SEGMENT_LLM_MODE or "off").strip().lower()
    if mode not in {"shadow", "assist"}:
        return build_analyzer_output(text=text, topic_type=topic_type, title=title, question=question)

    from app.retrieval.analyzers.request_segment_hybrid import build_analyzer_output_hybrid

    return build_analyzer_output_hybrid(
        text=text,
        topic_type=topic_type,
        title=title,
        question=question,
    )


def enrich_request_segment_trace(trace: dict[str, Any], analyzer_output: dict[str, Any] | None = None) -> dict[str, Any]:
    """routing_trace에 request_segments 신뢰 신호를 같은 키로 채운다."""
    enriched = dict(trace or {})
    analyzer = analyzer_output if isinstance(analyzer_output, dict) else {}
    complexity_trace = enriched.get("complexity_trace")
    if not isinstance(complexity_trace, dict):
        complexity_trace = analyzer.get("complexity_trace") if isinstance(analyzer.get("complexity_trace"), dict) else {}
    complexity_trace = dict(complexity_trace or {})

    request_segments = enriched.get("request_segments") or analyzer.get("request_segments") or []
    fallback_used = _coerce_bool(
        enriched.get("fallback_used"),
        analyzer.get("fallback_used"),
        complexity_trace.get("fallback_used"),
        complexity_trace.get("fallback_segment_used"),
        default=False,
    )
    truncated = _coerce_bool(
        enriched.get("truncated"),
        analyzer.get("truncated"),
        complexity_trace.get("truncated"),
        complexity_trace.get("segment_limit_applied"),
        default=False,
    )
    intent_count = _coerce_int(
        enriched.get("intent_count"),
        analyzer.get("intent_count"),
        complexity_trace.get("intent_count"),
        len(request_segments) if isinstance(request_segments, list) else None,
        default=0,
    )
    complexity_level = str(
        enriched.get("complexity_level")
        or analyzer.get("complexity_level")
        or complexity_trace.get("complexity_level")
        or ""
    )
    low_confidence = _coerce_bool(
        enriched.get("request_segments_low_confidence"),
        analyzer.get("request_segments_low_confidence"),
        complexity_trace.get("request_segments_low_confidence"),
        default=is_request_segments_low_confidence(
            complexity_level=complexity_level,
            fallback_used=fallback_used,
        ),
    )
    llm_confidence = enriched.get("llm_fallback_confidence")
    if llm_confidence is None:
        llm_confidence = complexity_trace.get("llm_fallback_confidence")

    complexity_trace["intent_count"] = intent_count
    complexity_trace["fallback_used"] = fallback_used
    complexity_trace["truncated"] = truncated
    complexity_trace["request_segments_low_confidence"] = low_confidence

    enriched["intent_count"] = intent_count
    enriched["fallback_used"] = fallback_used
    enriched["truncated"] = truncated
    enriched["request_segments_low_confidence"] = low_confidence
    if llm_confidence is not None:
        enriched["llm_fallback_confidence"] = llm_confidence
    enriched["complexity_trace"] = complexity_trace
    return enriched


def _coerce_bool(*values: Any, default: bool = False) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return bool(value)
    return default


def _coerce_int(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default

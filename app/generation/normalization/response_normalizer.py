"""Week6 unified QA response normalizer."""

from __future__ import annotations

from typing import Any, Dict, List


REQUIRED_KEYS = {
    "routing_trace",
    "structured_output",
    "answer",
    "citations",
    "legal_citations",
    "legal_citation_warnings",
    "limitations",
    "latency_ms",
    "quality_signals",
    "generation_metadata",
}


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_citations(value: Any) -> List[Dict[str, str]]:
    items = value if isinstance(value, list) else []
    normalized: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id") or item.get("case_id") or "").strip()
        source = str(item.get("source") or "retrieval").strip() or "retrieval"
        quote = str(item.get("quote") or item.get("snippet") or "").strip()
        normalized.append(
            {
                "doc_id": doc_id,
                "source": source,
                "quote": quote,
            }
        )
    return normalized


def _normalize_legal_citations(value: Any) -> List[Dict[str, Any]]:
    """Public API에 노출 가능한 법령 인용 필드만 통과시킨다."""
    items = value if isinstance(value, list) else []
    allowed = ("law_name", "article_no", "law_id", "public_url", "verified")
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        citation = {key: item.get(key) for key in allowed if item.get(key) is not None}
        if "verified" in citation:
            citation["verified"] = bool(citation["verified"])
        normalized.append(citation)
    return normalized


def normalize_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(payload)

    data["routing_trace"] = data.get("routing_trace") or {
        "topic_type": "general",
        "complexity_level": "medium",
        "complexity_score": 0.5,
        "complexity_trace": {},
        "route_reason": "routing_trace가 누락되어 기본값으로 대체했습니다.",
    }

    structured_output = data.get("structured_output") if isinstance(data.get("structured_output"), dict) else {}
    data["structured_output"] = {
        "summary": str(structured_output.get("summary") or ""),
        "action_items": _as_string_list(structured_output.get("action_items")),
        "request_segments": _as_string_list(structured_output.get("request_segments")),
    }

    data["answer"] = str(data.get("answer") or "")
    data["citations"] = _normalize_citations(data.get("citations"))
    data["legal_citations"] = _normalize_legal_citations(data.get("legal_citations"))
    data["legal_citation_warnings"] = _as_string_list(
        data.get("legal_citation_warnings")
    )
    data["limitations"] = _as_string_list(data.get("limitations"))

    latency_ms = data.get("latency_ms") if isinstance(data.get("latency_ms"), dict) else {}
    data["latency_ms"] = {
        "analyzer": int(latency_ms.get("analyzer", 0) or 0),
        "router": int(latency_ms.get("router", 0) or 0),
        "retrieval": int(latency_ms.get("retrieval", 0) or 0),
        "generation": int(latency_ms.get("generation", 0) or 0),
    }

    quality = data.get("quality_signals") if isinstance(data.get("quality_signals"), dict) else {}
    normalized_quality = {
        "citation_coverage": float(quality.get("citation_coverage", 0.0) or 0.0),
        "hallucination_flag": bool(quality.get("hallucination_flag", False)),
        "segment_coverage": float(quality.get("segment_coverage", 0.0) or 0.0),
    }
    for key, value in quality.items():
        if key not in normalized_quality:
            normalized_quality[key] = value
    data["quality_signals"] = normalized_quality

    generation_metadata = (
        data.get("generation_metadata")
        if isinstance(data.get("generation_metadata"), dict)
        else {}
    )
    generation_mode = str(generation_metadata.get("generation_mode") or "default").strip()
    normalized_generation_metadata = {
        "fallback_used": bool(generation_metadata.get("fallback_used", False)),
        "parse_retry_count": max(
            0,
            int(generation_metadata.get("parse_retry_count", 0) or 0),
        ),
        "grounding_evidence_count": max(
            0,
            int(generation_metadata.get("grounding_evidence_count", 0) or 0),
        ),
        "citation_count": max(
            0,
            int(generation_metadata.get("citation_count", 0) or 0),
        ),
        "generation_mode": generation_mode or "default",
        "legal_grounding_status": str(
            generation_metadata.get("legal_grounding_status") or "not_requested"
        ),
        "legal_grounding_error": str(
            generation_metadata.get("legal_grounding_error") or ""
        ),
    }
    if isinstance(generation_metadata.get("civil_llm_rubric"), dict):
        normalized_generation_metadata["civil_llm_rubric"] = generation_metadata[
            "civil_llm_rubric"
        ]
    if isinstance(generation_metadata.get("prometheus_revision"), dict):
        normalized_generation_metadata["prometheus_revision"] = generation_metadata[
            "prometheus_revision"
        ]
    data["generation_metadata"] = normalized_generation_metadata

    return data


def validate_unified_contract(payload: Dict[str, Any]) -> List[str]:
    missing = [key for key in sorted(REQUIRED_KEYS) if key not in payload]

    if not isinstance(payload.get("routing_trace"), dict):
        missing.append("routing_trace")
    if not isinstance(payload.get("structured_output"), dict):
        missing.append("structured_output")
    if not isinstance(payload.get("citations"), list):
        missing.append("citations")
    if not isinstance(payload.get("legal_citations"), list):
        missing.append("legal_citations")
    if not isinstance(payload.get("legal_citation_warnings"), list):
        missing.append("legal_citation_warnings")
    if not isinstance(payload.get("limitations"), list):
        missing.append("limitations")
    if not isinstance(payload.get("latency_ms"), dict):
        missing.append("latency_ms")
    if not isinstance(payload.get("quality_signals"), dict):
        missing.append("quality_signals")
    if not isinstance(payload.get("generation_metadata"), dict):
        missing.append("generation_metadata")

    return sorted(set(missing))

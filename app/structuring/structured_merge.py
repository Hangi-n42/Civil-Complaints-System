"""① 구조화 병합 — Track A.

StructuredLLMOutput(제약 디코딩 결과) + Rule NER → 통합 후보 필드 생성.
4요소 + result_status + roles(민원인/유발자/조치객체) + (선택)② 자기검증 적용.

기존 ResultMerger(FourElementsLLMOutput)는 그대로 두고, 제약 디코딩 경로용 별도 함수.
순수 함수 → stub verify_fn 으로 테스트 가능.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from app.structuring.merger import _NON_NULL_TO_CONFIDENCE, _find_span
from app.structuring.schemas import RuleBasedNERResult, StructuredLLMOutput
from app.structuring.verifier import VerifyFn, verify_candidate

_TEXT_FIELDS = ["observation", "result", "request", "context"]
_ROLE_FIELDS = ["complainant", "respondent", "target_object"]


def _field_dict(raw_text: str, text: str, base_conf: float):
    text = (text or "").strip()
    if text:
        s, e, src = _find_span(raw_text, text)
        return {"text": text, "confidence": base_conf, "evidence_span": [s, e]}, src
    return {"text": "", "confidence": 0.0, "evidence_span": [0, 0]}, "inferred"


def merge_structured(
    raw_text: str,
    ner_result: RuleBasedNERResult,
    structured: StructuredLLMOutput,
    llm_latency_ms: int,
    llm_model: str,
    verify_fn: Optional[VerifyFn] = None,
) -> Dict[str, Any]:
    """제약 디코딩 결과 → 통합 후보 dict. verify_fn 주어지면 ② 자기검증 적용."""
    texts = {f: getattr(structured, f, "") for f in _TEXT_FIELDS}
    non_null = sum(1 for v in texts.values() if (v or "").strip())
    base_conf = _NON_NULL_TO_CONFIDENCE.get(non_null, 0.0)
    structured_by = "constrained" if non_null > 0 else "fallback"

    built: Dict[str, Any] = {}
    span_sources: Dict[str, str] = {}
    for fname in _TEXT_FIELDS:
        d, src = _field_dict(raw_text, texts[fname], base_conf)
        span_sources[fname] = src
        if fname == "result":
            d["status"] = (structured.result_status if d["text"] else "pending")
        built[fname] = d

    roles: Dict[str, Any] = {}
    for rname in _ROLE_FIELDS:
        rtext = (getattr(structured, rname, "") or "").strip()
        s, e, _ = _find_span(raw_text, rtext) if rtext else (0, 0, "inferred")
        roles[rname] = {"text": rtext, "evidence_span": [s, e]}

    candidate_fragment: Dict[str, Any] = {
        **built,
        "roles": roles,
        "entities": ner_result.entities,
        "structured_by": structured_by,
        "extraction_meta": {
            "llm_model": llm_model,
            "llm_latency_ms": llm_latency_ms,
            "ner_latency_ms": ner_result.extraction_latency_ms,
            "llm_non_null_count": non_null,
            "span_sources": span_sources,
            "decoding": "constrained_schema",
        },
    }

    if verify_fn is not None:
        verify_candidate(raw_text, candidate_fragment, verify_fn)  # 4요소 grounding+보정+환각제거

    return candidate_fragment

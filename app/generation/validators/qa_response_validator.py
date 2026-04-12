"""QA 응답 citation/validation 공통 유틸."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


_CITE_TOKEN_PATTERN = re.compile(r"\[\[출처\s*(\d+)\]\]")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_citation_tokens(answer: str) -> Set[int]:
    return {int(match) for match in _CITE_TOKEN_PATTERN.findall(answer or "")}


def normalize_citations(raw_citations: List[Dict[str, Any]], context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """context와 정합한 citation만 ref_id를 부여해 정규화한다."""
    context_by_chunk = {
        str(item.get("chunk_id", "")): item
        for item in context
        if str(item.get("chunk_id", ""))
    }

    source = raw_citations if raw_citations else context[:3]
    normalized: List[Dict[str, Any]] = []

    for item in source:
        raw_chunk_id = str(item.get("chunk_id") or "")
        ctx = context_by_chunk.get(raw_chunk_id, {})

        chunk_id = raw_chunk_id or str(ctx.get("chunk_id") or "")
        if not chunk_id:
            continue

        if chunk_id not in context_by_chunk:
            continue

        ctx = context_by_chunk[chunk_id]
        case_id = str(item.get("case_id") or ctx.get("case_id") or "")
        context_case_id = str(ctx.get("case_id") or "")
        if not case_id or (context_case_id and case_id != context_case_id):
            continue

        doc_id = str(item.get("doc_id") or ctx.get("doc_id") or "").strip() or None
        snippet = str(item.get("snippet") or ctx.get("snippet") or "").strip()

        if not snippet or not chunk_id:
            continue

        citation: Dict[str, Any] = {
            "ref_id": len(normalized) + 1,
            "chunk_id": chunk_id,
            "case_id": case_id,
            "snippet": snippet,
            "relevance_score": _safe_float(item.get("relevance_score", item.get("score", 0.0))),
            "source": str(item.get("source") or "retrieval"),
        }
        if doc_id:
            citation["doc_id"] = doc_id

        normalized.append(citation)

    return normalized


def ensure_citation_tokens(answer: str, citations: List[Dict[str, Any]]) -> str:
    """answer 본문에 누락된 [[출처 n]] 토큰을 자동 보완한다."""
    rendered = (answer or "").strip()
    if not rendered:
        if citations:
            snippets = [str(item.get("snippet", "")).strip() for item in citations[:2]]
            snippets = [text for text in snippets if text]
            if snippets:
                rendered = f"검색 근거 요약: {' / '.join(snippets)}"
            else:
                rendered = "검색 근거 기반으로 핵심 조치가 필요합니다."
        else:
            rendered = "검색 근거가 부족하여 일반 원칙 중심으로 답변합니다."

    missing_tokens: List[str] = []
    for citation in citations:
        token = f"[[출처 {citation['ref_id']}]]"
        if token not in rendered:
            missing_tokens.append(token)

    if missing_tokens:
        rendered = rendered + " " + " ".join(missing_tokens)

    return rendered


def build_validation_result(
    answer: str,
    citations: List[Dict[str, Any]],
    limitations: str,
    context: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """QA 응답 검증 결과(is_valid/errors/warnings)를 생성한다."""
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if "폴백" in limitations:
        warnings.append(
            {
                "code": "FALLBACK_RESPONSE",
                "message": "모델 파싱 불안정으로 폴백 답변이 제공되었습니다.",
            }
        )

    if not citations:
        warnings.append(
            {
                "code": "EMPTY_CITATIONS",
                "message": "근거 citation이 비어 있습니다.",
            }
        )

    if not limitations.strip():
        errors.append(
            {
                "code": "LIMITATIONS_REQUIRED",
                "message": "limitations는 빈 문자열일 수 없습니다.",
            }
        )

    if not citations:
        errors.append(
            {
                "code": "CITATIONS_REQUIRED",
                "message": "성공 응답에는 최소 1개 이상의 citation이 필요합니다.",
            }
        )

    ref_ids = [int(item.get("ref_id", 0)) for item in citations]
    if len(ref_ids) != len(set(ref_ids)):
        errors.append(
            {
                "code": "DUPLICATE_REF_ID",
                "message": "citations.ref_id는 응답 내에서 유일해야 합니다.",
            }
        )

    token_ids = _extract_citation_tokens(answer)
    if token_ids != set(ref_ids):
        errors.append(
            {
                "code": "CITATION_TOKEN_MISMATCH",
                "message": "answer의 [[출처 n]] 토큰과 citations.ref_id가 1:1로 일치해야 합니다.",
            }
        )

    context_by_chunk = {
        str(item.get("chunk_id", "")): str(item.get("case_id", ""))
        for item in context
        if str(item.get("chunk_id", ""))
    }

    for citation in citations:
        chunk_id = str(citation.get("chunk_id") or "")
        case_id = str(citation.get("case_id") or "")
        snippet = str(citation.get("snippet") or "").strip()

        if not snippet:
            errors.append(
                {
                    "code": "EMPTY_SNIPPET",
                    "message": "citation.snippet은 빈 문자열일 수 없습니다.",
                }
            )

        if chunk_id not in context_by_chunk:
            errors.append(
                {
                    "code": "CHUNK_NOT_IN_CONTEXT",
                    "message": f"chunk_id '{chunk_id}'가 검색 결과에 존재하지 않습니다.",
                }
            )
            continue

        if case_id != context_by_chunk[chunk_id]:
            errors.append(
                {
                    "code": "CASE_ID_MISMATCH",
                    "message": f"chunk_id '{chunk_id}'의 case_id가 검색 결과와 일치하지 않습니다.",
                }
            )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }

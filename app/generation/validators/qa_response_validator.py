"""QA 응답 citation/validation 공통 유틸."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


_CITE_TOKEN_PATTERN = re.compile(r"\[\[출처\s*(\d+)\]\]")
_DEBUG_METADATA_PATTERN = re.compile(
    r"\s*\(?\s*(?:chunk_id=)?CASE-\d+__chunk-\d+(?:\s+case_id=CASE?-\d+|\s+case_id=\d+)?(?:\s+score=[0-9.]+)?\s*\)?",
    flags=re.IGNORECASE,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_citation_tokens(answer: str) -> Set[int]:
    return {int(match) for match in _CITE_TOKEN_PATTERN.findall(answer or "")}


def sanitize_answer_text(answer: str) -> str:
    """사용자 답변에 노출되면 안 되는 retrieval 메타데이터를 제거한다."""
    rendered = str(answer or "").strip()
    if not rendered:
        return ""

    rendered = _DEBUG_METADATA_PATTERN.sub("", rendered)
    rendered = re.sub(r"\(\s*chunk_id=[^)]+\)", "", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\[\[\s*\"[^\"]{0,500}\"\s*\]\]", "", rendered)
    rendered = re.sub(r"(?m)^\s*\[\[\".*?\"\]\]\s*$", "", rendered)
    rendered = re.sub(r"(?m)^\s*#{1,6}\s*", "", rendered)
    rendered = rendered.replace("**", "")
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    return rendered.strip()


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

    # 모델이 citations를 반환했더라도(=raw_citations 존재) 전부 무효로 필터링되면
    # 컨텍스트 기반 fallback을 사용해 최소 1개 citation을 확보한다.
    if raw_citations and not normalized and context:
        return normalize_citations([], context)

    return normalized


def ensure_citation_tokens(answer: str, citations: List[Dict[str, Any]]) -> str:
    """answer 본문에 누락된 [[출처 n]] 토큰을 자동 보완한다."""
    rendered = sanitize_answer_text(answer)
    if not rendered:
        if citations:
            snippets = [str(item.get("snippet", "")).strip() for item in citations[:2]]
            snippets = [text for text in snippets if text]
            if snippets:
                rendered = (
                    "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                    "2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. "
                    "접수된 취지와 확인 가능한 자료를 함께 고려하여 처리 가능 여부를 검토하는 사안입니다.\n\n"
                    f"3. 검토 의견은 다음과 같습니다. {' / '.join(snippets)} "
                    "위 내용을 바탕으로 담당부서에서는 현장 여건, 관련 기준, 필요한 후속 절차를 종합적으로 확인할 수 있습니다.\n\n"
                    "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
                )
            else:
                rendered = (
                    "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                    "2. 현재 인용 근거의 세부 내용이 충분하지 않아 담당부서 검토가 필요합니다.\n\n"
                    "3. 접수 내용과 관련 자료를 확인한 뒤 필요한 조치 가능 여부와 후속 안내 사항을 검토하겠습니다.\n\n"
                    "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 친절히 안내해 드리겠습니다. 감사합니다. 끝."
                )
        else:
            rendered = (
                "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                "2. 현재 확인 가능한 자료가 충분하지 않아 담당부서 확인 및 추가 검토가 필요합니다.\n\n"
                "3. 민원 취지, 발생 장소, 관련 자료가 확인되면 현장 여건과 행정 처리 기준을 종합적으로 검토하겠습니다.\n\n"
                "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 친절히 안내해 드리겠습니다. 감사합니다. 끝."
            )

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

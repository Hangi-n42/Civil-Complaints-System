"""Generation API 라우터"""

from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.generation import QARequest, QAResponse
from app.core.config import settings
from app.core.exceptions import GenerationError, RetrievalError
from app.generation.service import get_generation_service
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])

CONTRACT_VERSION = "qa-v1.1"
_CITE_TOKEN_PATTERN = re.compile(r"\[\[CITE:(\d+)\]\]")


def _confidence_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.5

    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_citation_tokens(answer: str) -> Set[int]:
    return {int(match) for match in _CITE_TOKEN_PATTERN.findall(answer or "")}


def _normalize_citations(
    raw_citations: List[Dict[str, Any]],
    context: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
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


def _ensure_citation_tokens(answer: str, citations: List[Dict[str, Any]]) -> str:
    rendered = (answer or "").strip()
    if not rendered:
        rendered = "검색 근거 기반 답변을 생성했지만 본문이 비어 있어 요약 문장을 제공하지 못했습니다."

    missing_tokens: List[str] = []
    for citation in citations:
        token = f"[[CITE:{citation['ref_id']}]]"
        if token not in rendered:
            missing_tokens.append(token)

    if missing_tokens:
        rendered = rendered + " " + " ".join(missing_tokens)

    return rendered


def _validation_warnings(limitations: str, citations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
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

    return warnings


def _build_validation_result(
    answer: str,
    citations: List[Dict[str, Any]],
    limitations: str,
    context: List[Dict[str, Any]],
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    warnings = _validation_warnings(limitations=limitations, citations=citations)

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
                "message": "answer의 [[CITE:n]] 토큰과 citations.ref_id가 1:1로 일치해야 합니다.",
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


@router.post("/qa", response_model=QAResponse)
async def generate_qa(request: QARequest, response: Response) -> QAResponse | JSONResponse:
    """검색 결과 기반 RAG QA 응답을 생성한다."""
    request_id = make_request_id()
    response.headers["X-Contract-Version"] = CONTRACT_VERSION

    if not request.query.strip():
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="질문(query)은 비어 있을 수 없습니다.",
            retryable=False,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    start = perf_counter()
    retrieval_service = get_retrieval_service()
    generation_service = get_generation_service()

    try:
        if request.use_search_results and request.search_results:
            context = [item.model_dump() for item in request.search_results]
        else:
            filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
            context = await retrieval_service.search(
                query=request.query,
                top_k=request.top_k,
                filters=filters,
            )
    except RetrievalError as e:
        return error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message="검색 인덱스가 준비되지 않았습니다. 인덱싱 후 다시 시도해주세요.",
            retryable=True,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    try:
        result = await generation_service.generate_qa(query=request.query, context=context)
    except GenerationError as e:
        error_code = getattr(e, "code", "PROCESSING_ERROR")
        retryable = bool(getattr(e, "retryable", True))
        details = getattr(e, "details", None)
        message = str(e)

        if error_code == "PROCESSING_ERROR":
            upper = message.upper()
            if "TIMEOUT" in upper:
                error_code = "MODEL_TIMEOUT"
                message = "응답 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            elif "OOM" in upper:
                error_code = "OOM_DETECTED"
                message = "메모리 용량 초과로 답변 생성이 중단되었습니다. 검색 범위를 줄여 다시 시도해주세요."
            elif "JSON" in upper:
                error_code = "PARSE_JSON_DECODE_ERROR"
                message = "모델 응답을 JSON으로 파싱하지 못했습니다."

        if error_code == "PARSE_RETRY_EXHAUSTED" and not message.strip():
            message = "모델 응답을 JSON으로 안정적으로 파싱하지 못했습니다."

        return error_response(
            request_id=request_id,
            error_code=error_code,
            message=message,
            retryable=retryable,
            details=details,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    took_ms = int((perf_counter() - start) * 1000)
    citations = _normalize_citations(result.get("citations", []), context=context)
    answer = _ensure_citation_tokens(result.get("answer", ""), citations=citations)
    confidence = _confidence_label(result.get("confidence", 0.5))
    limitations = str(result.get("limitations", "")).strip() or "검색 범위 내 데이터에 기반한 답변입니다."
    validation = _build_validation_result(
        answer=answer,
        citations=citations,
        limitations=limitations,
        context=context,
    )

    if not validation["is_valid"]:
        return error_response(
            request_id=request_id,
            error_code="PARSE_SCHEMA_MISMATCH",
            message="생성 응답 검증에 실패했습니다.",
            retryable=False,
            details={"validation_errors": validation["errors"]},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    used_top_k = len(context) if request.use_search_results and request.search_results else request.top_k

    return QAResponse(
        success=True,
        request_id=request_id,
        timestamp=now_iso(),
        answer=answer,
        citations=citations,
        confidence=confidence,
        limitations=limitations,
        meta={
            "processing_time": round(took_ms / 1000, 2),
            "model": str(result.get("model", settings.OLLAMA_MODEL)),
            "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다.",
            "generated_at": now_iso(),
            "validator_version": "be3-val-v0.1",
        },
        qa_validation=validation,
        search_trace={
            "used_top_k": used_top_k,
            "retrieved_count": len(context),
        },
    )

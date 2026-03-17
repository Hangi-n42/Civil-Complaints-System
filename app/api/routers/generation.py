"""Generation API 라우터"""

from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.schemas.generation import QARequest, QAResponse
from app.core.config import settings
from app.core.exceptions import GenerationError, RetrievalError
from app.generation.service import get_generation_service
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])


def _request_id() -> str:
    return f"REQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


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


def _error_response(
    *,
    request_id: str,
    error_code: str,
    message: str,
    retryable: bool,
    status_code: int,
    details: Dict[str, Any] | None = None,
) -> JSONResponse:
    payload: Dict[str, Any] = {
        "status": "error",
        "request_id": request_id,
        "timestamp": _now_iso(),
        "error_code": error_code,
        "message": message,
        "retryable": retryable,
    }
    if details:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


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

    for idx, item in enumerate(source, start=1):
        ctx = context_by_chunk.get(str(item.get("chunk_id", "")), {})
        case_id = str(item.get("case_id") or ctx.get("case_id") or "")
        doc_id = str(item.get("doc_id") or ctx.get("doc_id") or case_id or "")
        chunk_id = str(item.get("chunk_id") or ctx.get("chunk_id") or "")
        snippet = str(item.get("snippet") or ctx.get("snippet") or "").strip()

        if not snippet:
            continue

        normalized.append(
            {
                "ref_id": idx,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "case_id": case_id,
                "snippet": snippet,
                "relevance_score": float(item.get("relevance_score", item.get("score", 0.0))),
                "source": "retrieval",
            }
        )

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


@router.post("/qa", response_model=QAResponse)
async def generate_qa(request: QARequest) -> QAResponse | JSONResponse:
    """검색 결과 기반 RAG QA 응답을 생성한다."""
    request_id = _request_id()

    if not request.query.strip():
        return _error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="질문(query)은 비어 있을 수 없습니다.",
            retryable=False,
            status_code=400,
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
        return _error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message="검색 인덱스가 준비되지 않았습니다. 인덱싱 후 다시 시도해주세요.",
            retryable=True,
            status_code=503,
            details={"reason": str(e)},
        )

    try:
        result = await generation_service.generate_qa(query=request.query, context=context)
    except GenerationError as e:
        error_text = str(e)
        upper = error_text.upper()
        if "TIMEOUT" in upper:
            error_code = "MODEL_TIMEOUT"
            message = "응답 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            retryable = True
        elif "OOM" in upper:
            error_code = "OOM_DETECTED"
            message = "메모리 용량 초과로 답변 생성이 중단되었습니다. 검색 범위를 줄여 다시 시도해주세요."
            retryable = True
        elif "JSON" in upper:
            error_code = "JSON_PARSE_ERROR"
            message = "모델 응답 파싱에 실패했습니다. 다시 시도해주세요."
            retryable = True
        else:
            error_code = "PROCESSING_ERROR"
            message = "답변 생성 중 오류가 발생했습니다."
            retryable = True

        return _error_response(
            request_id=request_id,
            error_code=error_code,
            message=message,
            retryable=retryable,
            status_code=500,
            details={"reason": error_text},
        )

    took_ms = int((perf_counter() - start) * 1000)
    citations = _normalize_citations(result.get("citations", []), context=context)
    answer = _ensure_citation_tokens(result.get("answer", ""), citations=citations)
    confidence = _confidence_label(result.get("confidence", 0.5))
    limitations = str(result.get("limitations", "검색 범위 기반 응답입니다."))
    warnings = _validation_warnings(limitations=limitations, citations=citations)

    return QAResponse(
        request_id=request_id,
        timestamp=_now_iso(),
        answer=answer,
        citations=citations,
        confidence=confidence,
        limitations=limitations,
        meta={
            "processing_time": round(took_ms / 1000, 2),
            "model": str(result.get("model", settings.OLLAMA_MODEL)),
            "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다.",
            "generated_at": _now_iso(),
            "validator_version": "be3-val-v0.1",
        },
        qa_validation={
            "is_valid": len(warnings) == 0,
            "errors": [],
            "warnings": warnings,
        },
    )

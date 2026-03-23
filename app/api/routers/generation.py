"""Generation API 라우터"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.generation import QARequest, QAResponse
from app.core.config import settings
from app.core.exceptions import GenerationError, RetrievalError
from app.generation.service import get_generation_service
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
)
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])

CONTRACT_VERSION = "qa-v1.1"


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
    citations = normalize_citations(result.get("citations", []), context=context)
    answer = ensure_citation_tokens(result.get("answer", ""), citations=citations)
    confidence = _confidence_label(result.get("confidence", 0.5))
    limitations = str(result.get("limitations", "")).strip() or "검색 범위 내 데이터에 기반한 답변입니다."
    validation = build_validation_result(
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

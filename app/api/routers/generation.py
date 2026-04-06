"""Generation API 라우터"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.generation import QARequest, QAResponse, CitationValidation
from app.core.config import settings
from app.core.exceptions import GenerationError, RetrievalError
from app.core.logging import api_logger
from app.generation.context_mapper import map_retrieval_to_qa_context
from app.generation.citation.citation_mapper import get_citation_mapper
from app.generation.service import get_generation_service
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
)
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])

CONTRACT_VERSION = "qa-v1.1"
QA_LATENCY_WARN_MS = 8000


def _log_error(
    *,
    endpoint: str,
    request_id: str,
    error_code: str,
    retryable: bool,
    took_ms: int,
    message: str,
) -> None:
    api_logger.error(
        "api_error endpoint=%s request_id=%s error_code=%s retryable=%s latency_ms=%s message=%s",
        endpoint,
        request_id,
        error_code,
        retryable,
        took_ms,
        message,
    )


def _log_success(*, endpoint: str, request_id: str, took_ms: int, retrieved_count: int) -> None:
    api_logger.info(
        "api_success endpoint=%s request_id=%s latency_ms=%s retrieved_count=%s",
        endpoint,
        request_id,
        took_ms,
        retrieved_count,
    )

    if took_ms > QA_LATENCY_WARN_MS:
        api_logger.warning(
            "api_perf_warning endpoint=%s request_id=%s code=PERF_LATENCY_THRESHOLD_EXCEEDED latency_ms=%s threshold_ms=%s",
            endpoint,
            request_id,
            took_ms,
            QA_LATENCY_WARN_MS,
        )


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
    start = perf_counter()
    response.headers["X-Contract-Version"] = CONTRACT_VERSION

    if not request.query.strip():
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="BAD_REQUEST",
            retryable=False,
            took_ms=took_ms,
            message="질문(query)은 비어 있을 수 없습니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="질문(query)은 비어 있을 수 없습니다.",
            retryable=False,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    retrieval_service = get_retrieval_service()
    generation_service = get_generation_service()

    try:
        if request.use_search_results and request.search_results:
            raw_context = [item.model_dump() for item in request.search_results]
        else:
            filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
            raw_context = await retrieval_service.search(
                query=request.query,
                top_k=request.top_k,
                filters=filters,
            )
    except RetrievalError as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            retryable=True,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message="검색 인덱스가 준비되지 않았습니다. 인덱싱 후 다시 시도해주세요.",
            retryable=True,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            retryable=False,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="검색 단계에서 예기치 못한 오류가 발생했습니다.",
            retryable=False,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    context_policy = (
        request.context_window_policy.model_dump()
        if request.context_window_policy
        else None
    )
    context, context_trace = map_retrieval_to_qa_context(
        retrieval_results=raw_context,
        top_k=request.top_k,
        policy=context_policy,
    )

    if not context:
        took_ms = int((perf_counter() - start) * 1000)
        if request.use_search_results and request.search_results:
            _log_error(
                endpoint="/api/v1/qa",
                request_id=request_id,
                error_code="BAD_REQUEST",
                retryable=False,
                took_ms=took_ms,
                message="QA 컨텍스트를 구성할 수 없습니다. search_results 형식을 확인해주세요.",
            )
            return error_response(
                request_id=request_id,
                error_code="BAD_REQUEST",
                message="QA 컨텍스트를 구성할 수 없습니다. search_results 형식을 확인해주세요.",
                retryable=False,
                details={"hint": "chunk_id/case_id/snippet이 포함되어야 합니다."},
                headers={"X-Contract-Version": CONTRACT_VERSION},
            )

        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="RESOURCE_NOT_FOUND",
            retryable=False,
            took_ms=took_ms,
            message="질문과 관련된 검색 결과를 찾지 못했습니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="RESOURCE_NOT_FOUND",
            message="질문과 관련된 검색 결과를 찾지 못했습니다.",
            retryable=False,
            details={"query": request.query},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    try:
        result = await generation_service.generate_qa(query=request.query, context=context)
    except GenerationError as e:
        error_code = getattr(e, "code", "PROCESSING_ERROR")
        retryable = bool(getattr(e, "retryable", True))
        details = getattr(e, "details", None) or {}
        upstream_status = getattr(e, "upstream_status", None)
        message = str(e)

        # 제너릭 PROCESSING_ERROR를 더 구체적인 코드로 분류
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
        
        # PARSE_RETRY_EXHAUSTED를 Week 4 표준 에러코드 QA_PARSE_ERROR로 변환
        if error_code == "PARSE_RETRY_EXHAUSTED":
            error_code = "QA_PARSE_ERROR"
            message = "JSON 파싱 실패 (재시도 정책 모두 소진)"

        # upstream_status를 details에 포함
        if upstream_status is not None:
            details["upstream_status"] = upstream_status

        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code=error_code,
            retryable=retryable,
            took_ms=took_ms,
            message=message,
        )

        return error_response(
            request_id=request_id,
            error_code=error_code,
            message=message,
            retryable=retryable,
            details=details,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            retryable=False,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="생성 단계에서 예기치 못한 오류가 발생했습니다.",
            retryable=False,
            details={"reason": str(e)},
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
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="PARSE_SCHEMA_MISMATCH",
            retryable=False,
            took_ms=took_ms,
            message="생성 응답 검증에 실패했습니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="PARSE_SCHEMA_MISMATCH",
            message="생성 응답 검증에 실패했습니다.",
            retryable=False,
            details={"validation_errors": validation["errors"]},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    used_top_k = min(request.top_k, len(context)) if request.top_k > 0 else len(context)
    _log_success(
        endpoint="/api/v1/qa",
        request_id=request_id,
        took_ms=took_ms,
        retrieved_count=len(context),
    )

    # Citation 정합성 검증
    citation_mapper = get_citation_mapper()
    is_valid, mismatch_count, mismatch_details = citation_mapper.validate_citations_against_context(
        citations=[c.model_dump() if hasattr(c, 'model_dump') else c for c in citations],
        retrieval_context=context,
    )

    if not is_valid:
        api_logger.warning(
            "citation_validation_failed request_id=%s mismatch_count=%d",
            request_id,
            mismatch_count,
        )

    return QAResponse(
        success=True,
        request_id=request_id,
        timestamp=now_iso(),
        data={
            "answer": answer,
            "citations": citations,
            "confidence": confidence,
            "limitations": limitations,
            "latency_ms": took_ms,
        },
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
            "context_budget_chars": context_trace["context_budget_chars"],
            "context_used_chars": context_trace["context_used_chars"],
            "context_truncated_count": context_trace["context_truncated_count"],
            "context_dropped_count": context_trace["context_dropped_count"],
        },
        citation_validation=CitationValidation(
            is_valid=is_valid,
            mismatch_count=mismatch_count,
            details={"mismatches": mismatch_details} if mismatch_details else None,
        ),
    )

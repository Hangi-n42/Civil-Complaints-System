"""Generation API 라우터"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.generation import QARequest, QAResponse
from app.core.exceptions import GenerationError, RetrievalError
from app.core.logging import api_logger
from app.generation.context_mapper import map_retrieval_to_qa_context
from app.generation.citation.citation_mapper import get_citation_mapper
from app.generation.normalization.response_normalizer import (
    normalize_response,
    validate_unified_contract,
)
from app.generation.service import get_generation_service
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
)
from app.retrieval.router.adaptive_router import (
    DEFAULT_COMPLEXITY_LEVEL,
    build_route_key,
    build_strategy_id,
    parse_route_key,
)
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])

CONTRACT_VERSION = "qa-v1.1"
QA_LATENCY_WARN_MS = 8000


def _derive_request_segments(query: str) -> list[str]:
    cleaned = str(query or "").strip()
    if not cleaned:
        return []

    delimiters = [" 및 ", " 그리고 ", ",", ";"]
    segments = [cleaned]
    for delimiter in delimiters:
        next_segments = []
        for item in segments:
            next_segments.extend(item.split(delimiter))
        segments = next_segments

    normalized = [item.strip() for item in segments if item.strip()]
    return normalized if normalized else [cleaned]


def _is_strategy_consistent(strategy_id: str, route_key: str) -> bool:
    topic, complexity = parse_route_key(route_key)
    expected = build_strategy_id(topic, complexity)
    return strategy_id == expected


def _normalize_route_key(route_key: str) -> str:
    topic, complexity = parse_route_key(route_key)
    return build_route_key(topic, complexity)


def _validate_week6_qa_request(request: QARequest) -> str | None:
    if not str(request.complaint_id or "").strip():
        return "complaint_id is required"
    if not request.query.strip():
        return "query is required"
    if request.routing_hint is None:
        return "routing_hint is required"

    if not str(request.routing_hint.strategy_id or "").strip():
        return "routing_hint.strategy_id is required"
    if not str(request.routing_hint.route_key or "").strip():
        return "routing_hint.route_key is required"
    if "/" not in request.routing_hint.route_key:
        return "routing_hint.route_key must contain topic/complexity format"

    normalized_route_key = _normalize_route_key(request.routing_hint.route_key)
    if request.routing_hint.route_key.count("/") != 1:
        return "routing_hint.route_key must contain exactly one slash (topic/complexity)"

    if not _is_strategy_consistent(
        request.routing_hint.strategy_id,
        normalized_route_key,
    ):
        return "routing_hint.strategy_id and routing_hint.route_key are inconsistent"
    if request.routing_hint.top_k < 1:
        return "routing_hint.top_k must be >= 1"
    if request.routing_hint.snippet_max_chars < 120:
        return "routing_hint.snippet_max_chars must be >= 120"
    return None


def _build_trace_from_route_key(route_key: str, query: str) -> dict:
    topic_type, complexity_level = parse_route_key(route_key)

    if complexity_level == "high":
        complexity_score = 0.8
    elif complexity_level == "low":
        complexity_score = 0.3
    else:
        complexity_score = 0.55

    return {
        "topic_type": topic_type,
        "complexity_level": complexity_level,
        "complexity_score": complexity_score,
        "request_segments": _derive_request_segments(query),
        "complexity_trace": {
            "intent_count": 1,
            "constraint_count": 0,
            "entity_diversity": 1,
            "policy_reference_count": 0,
            "cross_sentence_dependency": False,
        },
        "route_reason": "search 단계 routing_hint 값을 그대로 계승했습니다.",
    }


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


def _compose_answer_from_payload(result: dict, citations: list[dict]) -> str:
    """모델 answer가 비거나 템플릿 문구일 때 근거 기반 최소 답변을 합성한다."""
    raw_answer = str(result.get("answer", "") or "").strip()
    fallback_marker = "본문이 비어 있어 요약 문장을 제공하지 못했습니다"
    if raw_answer and fallback_marker not in raw_answer:
        return raw_answer

    structured = result.get("structured_output") if isinstance(result.get("structured_output"), dict) else {}
    summary = str(structured.get("summary", "") or "").strip()
    actions = structured.get("action_items") if isinstance(structured.get("action_items"), list) else []
    actions = [str(item).strip() for item in actions if str(item).strip()]

    parts: list[str] = []
    if summary:
        parts.append(summary)
    if actions:
        parts.append("우선 조치: " + ", ".join(actions[:3]))
    elif summary:
        parts.append("우선 조치: 현장 점검, 담당 부서 확인, 재발 방지 계획 수립")
    if citations:
        quote = str(citations[0].get("snippet", "") or "").strip()
        if quote:
            parts.append(f"근거: {quote[:160]}")

    if parts:
        return " ".join(parts)

    if citations:
        quote = str(citations[0].get("snippet", "") or "").strip()
        if quote:
            return f"우선 조치: 현장 점검, 담당 부서 확인, 재발 방지 계획 수립. 근거: {quote[:160]}"

    return "우선 조치: 현장 점검, 담당 부서 확인, 재발 방지 계획 수립."


@router.post("/qa", response_model=QAResponse)
async def generate_qa(request: QARequest, response: Response) -> QAResponse | JSONResponse:
    """검색 결과 기반 RAG QA 응답을 생성한다."""
    request_id = str(request.request_id or "").strip() or make_request_id()
    start = perf_counter()
    response.headers["X-Contract-Version"] = CONTRACT_VERSION

    validation_message = _validate_week6_qa_request(request)
    if validation_message:
        took_ms = int((perf_counter() - start) * 1000)
        error_code = (
            "ROUTING_STRATEGY_INCONSISTENT"
            if "inconsistent" in validation_message
            else "VALIDATION_ERROR"
        )
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code=error_code,
            retryable=False,
            took_ms=took_ms,
            message=validation_message,
        )
        return error_response(
            request_id=request_id,
            error_code=error_code,
            message=validation_message,
            status_code=400,
            retryable=False,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    retrieval_service = get_retrieval_service()
    generation_service = get_generation_service()

    try:
        retrieval_start = perf_counter()
        effective_top_k = request.routing_hint.top_k if request.routing_hint else request.top_k
        if request.use_search_results and request.search_results:
            raw_context = [item.model_dump() for item in request.search_results]
        else:
            filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
            raw_context = await retrieval_service.search(
                query=request.query,
                top_k=effective_top_k,
                filters=filters,
            )
        retrieval_elapsed_ms = int((perf_counter() - retrieval_start) * 1000)
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
    context, _context_trace = map_retrieval_to_qa_context(
        retrieval_results=raw_context,
        top_k=effective_top_k,
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
        generation_start = perf_counter()
        route_key = _normalize_route_key(request.routing_hint.route_key) if request.routing_hint else f"general/{DEFAULT_COMPLEXITY_LEVEL}"
        routing_trace = (
            request.routing_trace.model_dump()
            if request.routing_trace is not None
            else _build_trace_from_route_key(route_key, request.query)
        )
        result = await generation_service.generate_qa(
            query=request.query,
            context=context,
            routing_trace=routing_trace,
        )
        generation_elapsed_ms = int((perf_counter() - generation_start) * 1000)
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
    answer = ensure_citation_tokens(_compose_answer_from_payload(result, citations), citations=citations)
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

    response_citations = []
    for item in citations:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        response_citations.append(
            {
                "doc_id": str(item.get("doc_id") or item.get("case_id") or ""),
                "source": str(item.get("source") or "retrieval"),
                "quote": str(item.get("snippet") or ""),
            }
        )

    route_key = _normalize_route_key(request.routing_hint.route_key) if request.routing_hint else f"general/{DEFAULT_COMPLEXITY_LEVEL}"
    strategy_id = request.routing_hint.strategy_id if request.routing_hint else build_strategy_id("general", DEFAULT_COMPLEXITY_LEVEL)
    routing_trace = (
        request.routing_trace.model_dump()
        if request.routing_trace is not None
        else _build_trace_from_route_key(route_key, request.query)
    )

    generated_structured = result.get("structured_output") if isinstance(result.get("structured_output"), dict) else {}
    unified_payload = normalize_response(
        {
            "complaint_id": request.complaint_id,
            "strategy_id": strategy_id,
            "route_key": route_key,
            "routing_trace": routing_trace,
            "structured_output": {
                "summary": generated_structured.get("summary", ""),
                "action_items": generated_structured.get("action_items", []),
                "request_segments": generated_structured.get(
                    "request_segments",
                    routing_trace.get("request_segments", []),
                ),
            },
            "answer": answer,
            "citations": response_citations,
            "limitations": result.get("limitations", [limitations]),
            "latency_ms": {
                "analyzer": 0,
                "router": 0,
                "retrieval": retrieval_elapsed_ms,
                "generation": generation_elapsed_ms,
            },
            "quality_signals": {
                "citation_coverage": 1.0 if response_citations else 0.0,
                "hallucination_flag": False,
                "segment_coverage": 1.0 if routing_trace.get("request_segments") else 0.0,
            },
        }
    )

    contract_missing = validate_unified_contract(unified_payload)
    if contract_missing:
        return error_response(
            request_id=request_id,
            error_code="VALIDATION_ERROR",
            message="/qa unified response contract validation failed",
            status_code=500,
            retryable=False,
            details={"missing_fields": contract_missing},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    return QAResponse(
        success=True,
        request_id=request_id,
        timestamp=now_iso(),
        data=unified_payload,
    )

"""Retrieval API 라우터"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.retrieval import (
    IndexRequest,
    IndexResponse,
    IndexResponseData,
    SearchRequest,
    SearchResponse,
    SearchResponseData,
)
from app.core.exceptions import RetrievalError
from app.core.logging import api_logger
from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output
from app.retrieval.router.adaptive_router import route as route_adaptive
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["retrieval"])

SEARCH_LATENCY_WARN_MS = 2000


def _normalize_department_answers(item: dict) -> dict[str, str]:
    """부서별 답변 맵을 표준화한다."""
    candidates = [
        item.get("answers_by_admin_unit"),
        item.get("department_answers"),
        (item.get("metadata") or {}).get("answers_by_admin_unit"),
        (item.get("metadata") or {}).get("department_answers"),
    ]

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        normalized: dict[str, str] = {}
        for raw_key, raw_value in candidate.items():
            key = str(raw_key or "").strip()
            value = str(raw_value or "").strip()
            if key:
                normalized[key] = value
        if normalized:
            return normalized

    return {}


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


def _log_success(*, endpoint: str, request_id: str, took_ms: int, count: int) -> None:
    api_logger.info(
        "api_success endpoint=%s request_id=%s latency_ms=%s count=%s",
        endpoint,
        request_id,
        took_ms,
        count,
    )


def _log_perf_warning(*, endpoint: str, request_id: str, took_ms: int, threshold_ms: int, code: str) -> None:
    if took_ms > threshold_ms:
        api_logger.warning(
            "api_perf_warning endpoint=%s request_id=%s code=%s latency_ms=%s threshold_ms=%s",
            endpoint,
            request_id,
            code,
            took_ms,
            threshold_ms,
        )


def _log_routing_decision(
    *,
    endpoint: str,
    request_id: str,
    analyzer_latency: int,
    route_key: str,
    strategy_id: str,
    complexity_level: str,
    complexity_score: float,
    router_latency: int,
    applied_params: dict,
) -> None:
    api_logger.info(
        "routing_decision endpoint=%s request_id=%s analyzer_latency_ms=%s route_key=%s strategy_id=%s complexity_level=%s complexity_score=%.3f router_latency_ms=%s applied_params=%s",
        endpoint,
        request_id,
        analyzer_latency,
        route_key,
        strategy_id,
        complexity_level,
        complexity_score,
        router_latency,
        applied_params,
    )


def _detect_topic_type(query: str) -> str:
    query_lower = query.lower()
    topic_keywords = {
        "welfare": ["복지", "급여", "기초생활", "수급", "임대주택"],
        "traffic": ["도로", "교통", "신호", "불법주정차", "가로등"],
        "environment": ["환경", "소음", "악취", "미세먼지", "폐기물"],
        "construction": ["공사", "건축", "안전", "보수", "시설"],
    }
    for topic, keywords in topic_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            return topic
    return "general"


def _build_routing_payload(query: str) -> dict:
    topic_type = _detect_topic_type(query)
    analyzer_started = perf_counter()
    analyzer_output = build_analyzer_output(text=query, topic_type=topic_type)
    analyzer_latency_ms = int((perf_counter() - analyzer_started) * 1000)

    router_started = perf_counter()
    routing_decision = route_adaptive(
        topic_type=analyzer_output["topic_type"],
        complexity_level=analyzer_output["complexity_level"],
        complexity_score=analyzer_output["complexity_score"],
    )

    router_latency_ms = int((perf_counter() - router_started) * 1000)

    request_segments = analyzer_output["request_segments"]
    applied_params = {
        "top_k": routing_decision.applied_params.top_k,
        "snippet_max_chars": routing_decision.applied_params.snippet_max_chars,
        "chunk_policy": routing_decision.applied_params.chunk_policy,
        "retrieval_policy": routing_decision.retrieval_policy,
    }
    merge_policy = "dedupe_max_score" if len(request_segments) > 1 else "single_query"

    return {
        "strategy_id": routing_decision.strategy_id,
        "route_key": routing_decision.route_key,
        "retrieval_policy": routing_decision.retrieval_policy,
        "request_segments": request_segments,
        "merge_policy": merge_policy,
        "routing_hint": {
            "strategy_id": routing_decision.strategy_id,
            "route_key": routing_decision.route_key,
            "top_k": routing_decision.applied_params.top_k,
            "snippet_max_chars": routing_decision.applied_params.snippet_max_chars,
            "chunk_policy": routing_decision.applied_params.chunk_policy,
        },
        "routing_trace": {
            "topic_type": analyzer_output["topic_type"],
            "complexity_level": analyzer_output["complexity_level"],
            "complexity_score": analyzer_output["complexity_score"],
            "request_segments": request_segments,
            "complexity_trace": analyzer_output["complexity_trace"],
            "route_reason": routing_decision.route_reason,
            "route_key": routing_decision.route_key,
            "strategy_id": routing_decision.strategy_id,
            "applied_filters": {},
            "segment_count": len(request_segments) if request_segments else 1,
            "merge_policy": merge_policy,
            "retrieval_policy": routing_decision.retrieval_policy,
        },
        "analyzer_output": analyzer_output,
        "analyzer_latency_ms": analyzer_latency_ms,
        "router_latency_ms": router_latency_ms,
        "applied_params": applied_params,
    }


@router.post("/index", response_model=IndexResponse, status_code=202)
async def index_documents(request: IndexRequest) -> IndexResponse:
    """구조화 레코드를 인덱싱한다."""
    request_id = request.request_id or make_request_id()
    start = perf_counter()

    cases = request.cases or []

    if not cases:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/index",
            request_id=request_id,
            error_code="BAD_REQUEST",
            retryable=False,
            took_ms=took_ms,
            message="cases는 최소 1건 이상이어야 합니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="cases는 최소 1건 이상이어야 합니다.",
            status_code=400,
        )

    service = get_retrieval_service()

    try:
        rebuild = request.action == "bulk"
        result = await service.index_documents(
            documents=[record.model_dump(exclude_none=True) for record in cases],
            rebuild=rebuild,
            collection_name=request.collection_name,
        )
    except RetrievalError as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/index",
            request_id=request_id,
            error_code="PROCESSING_ERROR",
            retryable=True,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="PROCESSING_ERROR",
            message=str(e),
            status_code=500,
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/index",
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            retryable=False,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="인덱싱 단계에서 예기치 못한 오류가 발생했습니다.",
            status_code=500,
            retryable=False,
            details={"reason": str(e)},
        )

    took_ms = int((perf_counter() - start) * 1000)
    _log_success(
        endpoint="/api/v1/index",
        request_id=request_id,
        took_ms=took_ms,
        count=int(result.get("indexed_count", 0)),
    )
    indexed_count = int(result.get("indexed_count", 0))
    failed_count = max(0, len(cases) - indexed_count)
    data = IndexResponseData(
        indexed_count=indexed_count,
        failed_count=failed_count,
        collection_name=request.collection_name,
        elapsed_ms=took_ms,
        chunk_count=int(result.get("chunk_count", 0)),
        index_name=str(result.get("index_name", request.collection_name)),
        rebuild=request.action == "bulk",
        records=result.get("records", []),
        took_ms=took_ms,
    )
    return IndexResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest) -> SearchResponse:
    """메타데이터 필터 기반 시맨틱 검색."""
    request_id = request.request_id or make_request_id()
    start = perf_counter()

    if not request.query.strip():
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/search",
            request_id=request_id,
            error_code="BAD_REQUEST",
            retryable=False,
            took_ms=took_ms,
            message="query는 비어 있을 수 없습니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="query는 비어 있을 수 없습니다.",
            status_code=400,
        )

    routing = _build_routing_payload(request.query)
    service = get_retrieval_service()

    try:
        filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
        applied_filters = {
            **filters,
            "topic_type": routing["routing_trace"]["topic_type"],
            "route_key": routing["route_key"],
            "strategy_id": routing["strategy_id"],
            "retrieval_policy": routing["retrieval_policy"],
            "segment_count": routing["routing_trace"]["segment_count"],
            "merge_policy": routing["merge_policy"],
        }
        routing["routing_trace"]["applied_filters"] = applied_filters
        routing["applied_params"]["applied_filters"] = applied_filters
        routing["applied_params"]["segment_count"] = routing["routing_trace"]["segment_count"]
        routing["applied_params"]["merge_policy"] = routing["merge_policy"]
        results = await service.search(
            query=request.query,
            top_k=routing["routing_hint"]["top_k"],
            filters=filters,
            collection_name=request.collection_name,
            topic_type=routing["routing_trace"]["topic_type"],
            request_segments=routing["request_segments"],
            retrieval_policy=routing["retrieval_policy"],
            snippet_max_chars=routing["routing_hint"]["snippet_max_chars"],
        )
    except RetrievalError as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/search",
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            retryable=True,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message=str(e),
            status_code=503,
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/search",
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
            status_code=500,
            retryable=False,
            details={"reason": str(e)},
        )

    took_ms = int((perf_counter() - start) * 1000)
    _log_success(
        endpoint="/api/v1/search",
        request_id=request_id,
        took_ms=took_ms,
        count=len(results),
    )
    _log_perf_warning(
        endpoint="/api/v1/search",
        request_id=request_id,
        took_ms=took_ms,
        threshold_ms=SEARCH_LATENCY_WARN_MS,
        code="PERF_RETRIEVAL_SLOW",
    )

    _log_routing_decision(
        endpoint="/api/v1/search",
        request_id=request_id,
        route_key=routing["route_key"],
        strategy_id=routing["strategy_id"],
        complexity_level=routing["routing_trace"]["complexity_level"],
        complexity_score=routing["routing_trace"]["complexity_score"],
        analyzer_latency=routing["analyzer_latency_ms"],
        router_latency=routing["router_latency_ms"],
        applied_params=routing["applied_params"],
    )

    formatted_results = []
    for item in results:
        summary = item.get("summary") or {}
        raw_content = item.get("content") if isinstance(item.get("content"), dict) else {}
        observation = str(summary.get("observation") or raw_content.get("observation") or "")
        request_text = str(summary.get("request") or raw_content.get("request") or "")
        snippet = str(item.get("snippet") or observation or "")
        case_id = str(item.get("case_id") or item.get("doc_id") or "")
        doc_id = str(item.get("doc_id") or case_id)
        chunk_id = str(item.get("chunk_id") or f"{case_id}__chunk-0") if case_id else str(item.get("chunk_id") or "")
        score = float(item.get("score", 0.0) or 0.0)
        answers_by_admin_unit = _normalize_department_answers(item)
        content = {
            "observation": observation,
            "result": str(raw_content.get("result") or ""),
            "request": request_text,
            "context": str(raw_content.get("context") or ""),
        }
        metadata = item.get("metadata") or {}
        matched_segments = metadata.get("matched_segments") or item.get("matched_segments") or []
        formatted_results.append(
            {
                "rank": int(item.get("rank", 0)),
                "case_id": case_id,
                "similarity_score": score,
                "content": content,
                "metadata": {
                    "created_at": metadata.get("created_at"),
                    "category": metadata.get("category"),
                    "region": metadata.get("region"),
                    "entity_labels": metadata.get("entity_labels", []),
                    "strategy_id": routing["strategy_id"],
                    "route_key": routing["route_key"],
                    "topic_type": routing["routing_trace"]["topic_type"],
                    "retrieval_policy": routing["retrieval_policy"],
                    "matched_segments": matched_segments,
                },
                "doc_id": doc_id,
                "score": score,
                "chunk_id": chunk_id,
                "title": item.get("title"),
                "snippet": snippet,
                "summary": {
                    "observation": observation,
                    "request": request_text,
                },
                "answers_by_admin_unit": answers_by_admin_unit,
                # Backward compatibility alias for FE variants
                "department_answers": answers_by_admin_unit,
            }
        )

    data = SearchResponseData(
        complaint_id=request.complaint_id,
        strategy_id=routing["strategy_id"],
        route_key=routing["route_key"],
        routing_hint=routing["routing_hint"],
        routing_trace=routing["routing_trace"],
        retrieved_docs=formatted_results,
        results=formatted_results,
        total_found=len(formatted_results),
        elapsed_ms=took_ms,
        query=request.query,
        top_k=request.top_k,
        count=len(formatted_results),
        took_ms=took_ms,
    )
    return SearchResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )

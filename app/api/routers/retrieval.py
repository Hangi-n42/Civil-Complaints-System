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


def _build_routing_payload(query: str, top_k: int) -> dict:
    topic_type = _detect_topic_type(query)
    query_len = len(query.strip())
    intent_count = 1 + int("및" in query or "그리고" in query or "," in query)
    constraint_count = sum(1 for token in ["기한", "예산", "법", "규정", "절차"] if token in query)
    entity_diversity = min(3, max(1, sum(1 for token in ["기관", "부서", "주민", "사업자"] if token in query) + 1))
    policy_reference_count = int("법" in query or "조례" in query or "규정" in query)
    cross_sentence_dependency = any(token in query for token in ["또한", "한편", "다만", "그리고"])

    score = min(
        1.0,
        round(
            0.2
            + min(0.3, query_len / 200.0)
            + min(0.2, intent_count * 0.08)
            + min(0.2, constraint_count * 0.08)
            + (0.1 if cross_sentence_dependency else 0.0),
            2,
        ),
    )
    if score >= 0.75:
        complexity_level = "high"
    elif score >= 0.5:
        complexity_level = "medium"
    else:
        complexity_level = "low"

    chunk_policy = "expanded" if complexity_level == "high" else ("balanced" if complexity_level == "medium" else "compact")
    snippet_max_chars = 1100 if complexity_level == "high" else (900 if complexity_level == "medium" else 700)
    strategy_id = f"topic_{topic_type}_{complexity_level}_v1"
    route_key = f"{topic_type}/{complexity_level}"

    return {
        "strategy_id": strategy_id,
        "route_key": route_key,
        "routing_hint": {
            "strategy_id": strategy_id,
            "route_key": route_key,
            "top_k": top_k,
            "snippet_max_chars": snippet_max_chars,
            "chunk_policy": chunk_policy,
        },
        "routing_trace": {
            "topic_type": topic_type,
            "complexity_level": complexity_level,
            "complexity_score": score,
            "complexity_trace": {
                "intent_count": intent_count,
                "constraint_count": constraint_count,
                "entity_diversity": entity_diversity,
                "policy_reference_count": policy_reference_count,
                "cross_sentence_dependency": cross_sentence_dependency,
            },
            "route_reason": f"{topic_type} 주제와 {complexity_level} 복잡도에 맞춰 {chunk_policy} 검색 전략을 선택했습니다.",
        },
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

    service = get_retrieval_service()

    try:
        filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
        results = await service.search(
            query=request.query,
            top_k=request.top_k,
            filters=filters,
            collection_name=request.collection_name,
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

    routing = _build_routing_payload(request.query, request.top_k)

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

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

    formatted_results = []
    for item in results:
        summary = item.get("summary") or {}
        content = {
            "observation": str(summary.get("observation") or ""),
            "result": "",
            "request": str(summary.get("request") or ""),
            "context": "",
        }
        metadata = item.get("metadata") or {}
        formatted_results.append(
            {
                "rank": int(item.get("rank", 0)),
                "case_id": str(item.get("case_id", "")),
                "similarity_score": float(item.get("score", 0.0) or 0.0),
                "content": content,
                "metadata": {
                    "created_at": metadata.get("created_at"),
                    "category": metadata.get("category"),
                    "region": metadata.get("region"),
                    "entity_labels": metadata.get("entity_labels", []),
                },
                # Backward compatibility fields
                "doc_id": item.get("doc_id"),
                "score": float(item.get("score", 0.0) or 0.0),
                "chunk_id": item.get("chunk_id"),
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "summary": {
                    "observation": content["observation"],
                    "request": content["request"],
                },
            }
        )

    data = SearchResponseData(
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

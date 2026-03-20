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
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


@router.post("/index", response_model=IndexResponse)
async def index_documents(request: IndexRequest) -> IndexResponse:
    """구조화 레코드를 인덱싱한다."""
    request_id = make_request_id()

    if not request.records:
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="records는 최소 1건 이상이어야 합니다.",
            status_code=400,
        )

    start = perf_counter()
    service = get_retrieval_service()

    try:
        result = await service.index_documents(
            documents=[record.model_dump(exclude_none=True) for record in request.records],
            rebuild=request.rebuild,
        )
    except RetrievalError as e:
        return error_response(
            request_id=request_id,
            error_code="PROCESSING_ERROR",
            message=str(e),
            status_code=500,
        )

    took_ms = int((perf_counter() - start) * 1000)
    data = IndexResponseData(took_ms=took_ms, **result)
    return IndexResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest) -> SearchResponse:
    """메타데이터 필터 기반 시맨틱 검색."""
    request_id = make_request_id()

    if not request.query.strip():
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="query는 비어 있을 수 없습니다.",
            status_code=400,
        )

    start = perf_counter()
    service = get_retrieval_service()

    try:
        filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
        results = await service.search(
            query=request.query,
            top_k=request.top_k,
            filters=filters,
        )
    except RetrievalError as e:
        return error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message=str(e),
            status_code=503,
        )

    took_ms = int((perf_counter() - start) * 1000)
    data = SearchResponseData(
        query=request.query,
        top_k=request.top_k,
        results=results,
        count=len(results),
        took_ms=took_ms,
    )
    return SearchResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )

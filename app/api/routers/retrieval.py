"""Retrieval API 라우터"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.api.schemas.retrieval import (
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
)
from app.core.exceptions import RetrievalError
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


@router.post("/index", response_model=IndexResponse)
async def index_documents(request: IndexRequest) -> IndexResponse:
    """구조화 레코드를 인덱싱한다."""
    if not request.records:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BAD_REQUEST",
                "message": "records는 최소 1건 이상이어야 합니다.",
            },
        )

    start = perf_counter()
    service = get_retrieval_service()

    try:
        result = await service.index_documents(
            documents=[record.model_dump(exclude_none=True) for record in request.records],
            rebuild=request.rebuild,
        )
    except RetrievalError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PROCESSING_ERROR",
                "message": str(e),
            },
        ) from e

    took_ms = int((perf_counter() - start) * 1000)
    return IndexResponse(took_ms=took_ms, **result)


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest) -> SearchResponse:
    """메타데이터 필터 기반 시맨틱 검색."""
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BAD_REQUEST",
                "message": "query는 비어 있을 수 없습니다.",
            },
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
        raise HTTPException(
            status_code=503,
            detail={
                "code": "INDEX_NOT_READY",
                "message": str(e),
            },
        ) from e

    took_ms = int((perf_counter() - start) * 1000)
    return SearchResponse(
        query=request.query,
        top_k=request.top_k,
        results=results,
        count=len(results),
        took_ms=took_ms,
    )

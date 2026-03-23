"""Retrieval API 라우터"""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.retrieval import (
    IngestRequest,
    IngestResponse,
    IngestResponseData,
    IndexRequest,
    IndexResponse,
    IndexResponseData,
    SearchRequest,
    SearchResponse,
    SearchResponseData,
    StructureRequest,
    StructureResponse,
    StructureResponseData,
)
from app.core.exceptions import IngestionError, RetrievalError, StructuringError
from app.ingestion.service import get_ingestion_service
from app.retrieval.service import get_retrieval_service
from app.structuring.service import get_structuring_service

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


def _build_validation_issue(field: str, code: str, message: str) -> dict:
    return {
        "field": field,
        "code": code,
        "message": message,
    }


def _to_issue_list(raw_issues: list[str], *, warning: bool = False) -> list[dict]:
    issues = []
    prefix = "VAL_WARNING" if warning else "VAL_ERROR"

    for item in raw_issues:
        key = str(item or "unknown")
        if ":" in key:
            field_hint, value_hint = key.split(":", 1)
            field = field_hint.replace("_", ".")
            message = value_hint or key
        else:
            field = "validation"
            message = key

        issues.append(
            _build_validation_issue(
                field=field,
                code=f"{prefix}_{field.upper().replace('.', '_')}",
                message=message,
            )
        )

    return issues


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest) -> IngestResponse | object:
    """민원 원문을 정제/마스킹/중복제거하여 입수한다."""
    request_id = make_request_id()

    if not request.records:
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="records는 최소 1건 이상이어야 합니다.",
            status_code=400,
        )

    normalized_records = []
    validation_errors = []

    for idx, record in enumerate(request.records):
        payload = record.model_dump(exclude_none=True)
        text = str(payload.get("raw_text") or payload.get("text") or "").strip()
        if not text:
            validation_errors.append(
                _build_validation_issue(
                    field=f"records[{idx}].text",
                    code="REQ_REQUIRED_FIELD_MISSING",
                    message="text 또는 raw_text 중 하나는 필수입니다.",
                )
            )
            continue

        normalized = dict(payload)
        normalized["text"] = text
        normalized_records.append(normalized)

    if validation_errors:
        return error_response(
            request_id=request_id,
            error_code="VALIDATION_ERROR",
            message="요청 검증에 실패했습니다.",
            status_code=422,
            details={"validation_errors": validation_errors},
        )

    service = get_ingestion_service()
    try:
        processed = await service.process(
            normalized_records,
            clean=True,
            mask_pii=request.mask_pii,
            deduplicate=request.deduplicate,
        )
    except IngestionError as e:
        return error_response(
            request_id=request_id,
            error_code="PROCESSING_ERROR",
            message=str(e),
            status_code=500,
        )

    processed_case_ids = {
        str(item.get("case_id") or "")
        for item in processed
        if str(item.get("case_id") or "")
    }

    result_rows = []
    for item in processed:
        result_rows.append(
            {
                "case_id": str(item.get("case_id") or "UNKNOWN"),
                "status": "accepted",
                "normalized_text": str(item.get("text") or ""),
            }
        )

    if request.deduplicate:
        for src in normalized_records:
            case_id = str(src.get("case_id") or "")
            if case_id and case_id not in processed_case_ids:
                result_rows.append(
                    {
                        "case_id": case_id,
                        "status": "skipped",
                        "normalized_text": str(src.get("text") or ""),
                    }
                )

    data = IngestResponseData(
        ingested_count=len(processed),
        skipped_count=max(0, len(normalized_records) - len(processed)),
        mask_pii=request.mask_pii,
        deduplicate=request.deduplicate,
        records=result_rows,
    )

    return IngestResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )


@router.post("/structure", response_model=StructureResponse)
async def structure_documents(request: StructureRequest) -> StructureResponse | object:
    """민원 원문을 4요소/엔티티로 구조화하고 validation 결과를 반환한다."""
    request_id = make_request_id()

    if not request.records:
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="records는 최소 1건 이상이어야 합니다.",
            status_code=400,
        )

    service = get_structuring_service()
    results = []

    for idx, record in enumerate(request.records):
        payload = record.model_dump(exclude_none=True)
        text = str(payload.get("raw_text") or payload.get("text") or "").strip()
        if not text:
            return error_response(
                request_id=request_id,
                error_code="VALIDATION_ERROR",
                message="요청 검증에 실패했습니다.",
                status_code=422,
                details={
                    "validation_errors": [
                        _build_validation_issue(
                            field=f"records[{idx}].text",
                            code="REQ_REQUIRED_FIELD_MISSING",
                            message="text 또는 raw_text 중 하나는 필수입니다.",
                        )
                    ]
                },
            )

        try:
            structured = await service.structure(payload)
        except StructuringError as e:
            return error_response(
                request_id=request_id,
                error_code="PROCESSING_ERROR",
                message=str(e),
                status_code=500,
            )

        raw_validation = structured.get("validation", {}) if isinstance(structured, dict) else {}
        errors = _to_issue_list(raw_validation.get("errors", []), warning=False)
        warnings = _to_issue_list(raw_validation.get("warnings", []), warning=True)

        result_item = {
            "case_id": str(structured.get("case_id") or ""),
            "source": str(structured.get("source") or "unknown"),
            "created_at": str(structured.get("created_at") or now_iso()),
            "category": structured.get("category"),
            "region": structured.get("region"),
            "raw_text": str(structured.get("raw_text") or ""),
            "observation": structured.get("observation") or {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
            "result": structured.get("result") or {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
            "request": structured.get("request") or {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
            "context": structured.get("context") or {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
            "entities": structured.get("entities") or [],
            "metadata": structured.get("metadata") if isinstance(structured.get("metadata"), dict) else {},
            "supervision": structured.get("supervision") if isinstance(structured.get("supervision"), dict) else None,
            "confidence_score": float(structured.get("confidence_score", 0.0) or 0.0),
            "structured_at": str(structured.get("structured_at") or now_iso()),
            "validation": {
                "is_valid": bool(raw_validation.get("is_valid", len(errors) == 0)),
                "errors": errors,
                "warnings": warnings,
            },
        }
        results.append(result_item)

    invalid_count = sum(1 for item in results if not item["validation"]["is_valid"])
    data = StructureResponseData(
        structured_count=len(results),
        invalid_count=invalid_count,
        results=results,
    )

    return StructureResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=data,
    )


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

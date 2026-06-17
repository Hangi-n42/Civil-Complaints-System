"""BE1 구조화 API 라우터."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Dict

from fastapi import APIRouter

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.structuring import StructureRequest, StructureResponse
from app.core.exceptions import StructuringError
from app.core.logging import api_logger
from app.structuring.service import get_structuring_service

router = APIRouter(prefix="/api/v1", tags=["structuring"])


def _has_structuring_input(payload: Dict[str, Any]) -> bool:
    """구조화 가능한 본문 필드가 하나라도 있는지 확인한다."""
    return any(str(payload.get(key) or "").strip() for key in ("text", "raw_text", "consulting_content"))


@router.post("/structure", response_model=StructureResponse)
async def structure_case(request: StructureRequest) -> Dict[str, Any]:
    """단건 민원을 BE1 구조화 결과로 변환한다."""
    started = perf_counter()
    request_id = request.request_id or make_request_id()
    payload = request.model_dump(exclude_none=True, exclude={"request_id"})

    if not _has_structuring_input(payload):
        return error_response(
            request_id=request_id,
            error_code="BAD_REQUEST",
            message="구조화할 text, raw_text 또는 consulting_content가 필요합니다.",
            status_code=400,
            retryable=False,
            details={"required_any_of": ["text", "raw_text", "consulting_content"]},
        )

    try:
        structured = await get_structuring_service().structure(payload)
    except StructuringError as exc:
        api_logger.exception("structure_api_failed request_id=%s error=%s", request_id, exc)
        return error_response(
            request_id=request_id,
            error_code="PROCESSING_ERROR",
            message="민원 구조화 중 오류가 발생했습니다.",
            status_code=500,
            retryable=True,
            details={"error": str(exc)},
        )
    except Exception as exc:
        api_logger.exception("structure_api_unexpected_error request_id=%s error=%s", request_id, exc)
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="예상하지 못한 구조화 API 오류가 발생했습니다.",
            status_code=500,
            retryable=False,
            details={"error": str(exc)},
        )

    took_ms = int((perf_counter() - started) * 1000)
    api_logger.info(
        "api_success endpoint=/api/v1/structure request_id=%s latency_ms=%s case_id=%s",
        request_id,
        took_ms,
        structured.get("case_id"),
    )
    return {
        "success": True,
        "request_id": request_id,
        "timestamp": now_iso(),
        "data": structured,
    }

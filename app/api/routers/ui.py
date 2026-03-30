"""UI 전용 케이스 API 라우터."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.api.error_utils import error_response, make_request_id, now_iso
from app.core.logging import api_logger
from app.ui.services.ui_case_adapter import load_ui_cases_from_week2_sample

router = APIRouter(prefix="/api/v1/ui", tags=["ui"])


@router.get("/cases")
async def list_ui_cases():
    """UI(Home/Queue) 전용 케이스 목록을 반환한다."""
    request_id = make_request_id()
    sample_path = (
        Path(__file__).resolve().parents[3]
        / "reports"
        / "week2_entity_audit"
        / "week2_structured_sample_10.json"
    )

    try:
        cases = load_ui_cases_from_week2_sample(sample_path)
    except Exception as exc:
        api_logger.error(
            "api_error endpoint=%s request_id=%s error_code=%s message=%s",
            "/api/v1/ui/cases",
            request_id,
            "INTERNAL_SERVER_ERROR",
            str(exc),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="UI 케이스 로딩 중 오류가 발생했습니다.",
            retryable=False,
            details={
                "path": str(sample_path),
                "reason": str(exc),
            },
        )

    return {
        "success": True,
        "request_id": request_id,
        "timestamp": now_iso(),
        "data": {
            "count": len(cases),
            "cases": cases,
        },
    }

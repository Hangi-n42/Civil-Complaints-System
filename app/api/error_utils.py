"""API 공통 에러 응답/매핑 유틸."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from fastapi.responses import JSONResponse


# Week2 계약 기준 공통 에러 정책
# HTTP 상태코드 매핑 규칙:
#   4xx (클라이언트 오류): retryable=False
#   - 400: 잘못된 요청
#   - 401: 인증 실패
#   - 404: 리소스/모델 미존재
#   - 422: 유효성 검사 실패
#   5xx (서버 오류): retryable=True (재시도 권장)
#   - 500: 일반 처리 오류
#   - 503: 서비스 이용 불가 (Ollama 미기동/준비 중)
#   - 504: 게이트웨이 타임아웃 (응답 시간 초과)
ERROR_POLICY: Dict[str, Dict[str, Any]] = {
    "BAD_REQUEST": {"status_code": 400, "retryable": False},
    "FILTER_INVALID": {"status_code": 400, "retryable": False},
    "VALIDATION_ERROR": {"status_code": 422, "retryable": False},
    "INDEX_NOT_READY": {"status_code": 503, "retryable": True},
    "MODEL_NOT_FOUND": {"status_code": 404, "retryable": False},  # 모델 미존재
    "MODEL_TIMEOUT": {"status_code": 504, "retryable": True},  # 응답 시간 초과
    "MODEL_NOT_READY": {"status_code": 503, "retryable": True},  # Ollama 미기동/연결거부
    "OOM_DETECTED": {"status_code": 503, "retryable": True},
    "PARSE_SCHEMA_MISMATCH": {"status_code": 422, "retryable": False},
    "PARSE_JSON_DECODE_ERROR": {"status_code": 500, "retryable": True},
    "PARSE_JSON_BLOCK_EXTRACTION_FAILED": {"status_code": 500, "retryable": True},
    "PARSE_RETRY_EXHAUSTED": {"status_code": 500, "retryable": False},
    "PROCESSING_ERROR": {"status_code": 500, "retryable": True},
    "INTERNAL_SERVER_ERROR": {"status_code": 500, "retryable": False},
    # Week 4 QA 특화 에러코드
    "QA_PARSE_ERROR": {"status_code": 500, "retryable": True},  # JSON 파싱 실패 (재시도 권장)
    "CITATION_MISMATCH": {"status_code": 500, "retryable": True},  # citation 정합성 불일치
    "INVALID_QA_REQUEST": {"status_code": 400, "retryable": False},  # 잘못된 QA 요청
    "GENERATION_TIMEOUT": {"status_code": 504, "retryable": True},  # 생성 타임아웃
    # Week 6 BE3 계약 확장
    "PROMPT_BUILD_ERROR": {"status_code": 500, "retryable": True},
    "NORMALIZE_RESPONSE_ERROR": {"status_code": 500, "retryable": True},
    "ROUTING_STRATEGY_INCONSISTENT": {"status_code": 400, "retryable": False},
}


def make_request_id() -> str:
    return f"REQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def get_status_code(error_code: str, default: int = 500) -> int:
    policy = ERROR_POLICY.get(error_code)
    if not policy:
        return default
    return int(policy.get("status_code", default))


def get_retryable(error_code: str, *, status_code: Optional[int] = None) -> bool:
    policy = ERROR_POLICY.get(error_code)
    if policy and "retryable" in policy:
        return bool(policy["retryable"])

    if status_code is None:
        status_code = get_status_code(error_code)
    return status_code >= 500


def _to_json_safe(value: Any) -> Any:
    """JSONResponse 직렬화가 가능한 형태로 재귀 변환한다."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Exception):
        return str(value)

    if isinstance(value, Mapping):
        return {str(k): _to_json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]

    return str(value)


def error_response(
    *,
    request_id: str,
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    status_code: Optional[int] = None,
    retryable: Optional[bool] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    resolved_status = status_code if status_code is not None else get_status_code(error_code)
    resolved_retryable = (
        bool(retryable)
        if retryable is not None
        else get_retryable(error_code, status_code=resolved_status)
    )

    payload: Dict[str, Any] = {
        "success": False,
        "request_id": request_id,
        "timestamp": now_iso(),
        "error": {
            "code": error_code,
            "message": message,
            "retryable": resolved_retryable,
            "details": _to_json_safe(details or {}),
        },
    }

    return JSONResponse(
        status_code=resolved_status,
        content=payload,
        headers=dict(headers) if headers else None,
    )

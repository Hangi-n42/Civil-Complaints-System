"""FE용 retrieval 응답 파서."""

from __future__ import annotations

from typing import Any, Dict


class ResponseContractError(ValueError):
    """API 응답이 계약을 위반했을 때 발생."""


def _ensure_success_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ResponseContractError("응답 payload는 객체여야 합니다.")

    if payload.get("success") is not True:
        raise ResponseContractError("성공 응답이 아닙니다.")

    if not payload.get("request_id"):
        raise ResponseContractError("request_id가 누락되었습니다.")

    if not payload.get("timestamp"):
        raise ResponseContractError("timestamp가 누락되었습니다.")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ResponseContractError("data 객체가 누락되었거나 형식이 잘못되었습니다.")

    return data


def parse_search_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """검색 응답 래퍼를 파싱해 data 객체를 반환한다."""
    data = _ensure_success_payload(payload)

    required_keys = ["results", "total_found", "elapsed_ms"]
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise ResponseContractError(f"search data 필수 필드 누락: {', '.join(missing)}")

    if not isinstance(data.get("results"), list):
        raise ResponseContractError("results는 배열이어야 합니다.")

    return data


def parse_index_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """인덱스 응답 래퍼를 파싱해 data 객체를 반환한다."""
    data = _ensure_success_payload(payload)

    required_keys = ["indexed_count", "failed_count", "collection_name", "elapsed_ms"]
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise ResponseContractError(f"index data 필수 필드 누락: {', '.join(missing)}")

    return data

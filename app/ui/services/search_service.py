from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st
from urllib import error as urlerror
from urllib import request as urlrequest


def get_friendly_error_message(err_code: int, raw_msg: str) -> str:
    """HTTP 상태코드/에러 메시지를 사용자 친화적으로 변환한다."""

    msg = (raw_msg or "").strip()
    lowered = msg.lower()

    if err_code == 400:
        return "검색 조건이 올바르지 않습니다. 필터를 다시 확인해주세요."
    if err_code == 404:
        return "검색 API 경로를 찾을 수 없습니다. (서버 점검 중)"
    if err_code in (408, 504) or "timeout" in lowered or "timed out" in lowered:
        return "검색 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요."
    if err_code in (500, 503):
        return "검색 서버에 일시적인 장애가 발생했습니다. 관리자에게 문의하세요."

    return f"검색 중 알 수 없는 오류가 발생했습니다. ({msg})"


def post_json(base_url: str, path: str, payload: dict, timeout: float = 25.0) -> tuple[dict, int, str | None]:
    """BE API POST 호출 유틸."""

    if st.session_state.get("ui_force_mock", False):
        return {}, 0, "UI_FORCE_MOCK enabled (API disabled)"

    url = f"{base_url.rstrip('/')}{path}"
    req = urlrequest.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return parsed, int(getattr(response, "status", 200)), None
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        return parsed, int(getattr(e, "code", 500)), str(e)
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {}, 0, str(e)


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def normalize_search_results_from_api(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """/api/v1/search 응답을 UI 표시용 포맷으로 정규화한다."""

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    normalized: List[Dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}

        summary = item.get("summary")
        summary = summary if isinstance(summary, dict) else None

        score = float(item.get("score", 0.0) or 0.0)
        created_at = metadata.get("created_at")
        category = metadata.get("category")
        region = metadata.get("region")
        entity_labels = metadata.get("entity_labels", [])
        entity_labels = entity_labels if isinstance(entity_labels, list) else []

        normalized.append(
            {
                # BE2 contract fields
                "rank": int(item.get("rank", 0) or 0),
                "doc_id": str(item.get("doc_id", "")),
                "score": score,
                "chunk_id": str(item.get("chunk_id", "")),
                "case_id": str(item.get("case_id", "")),
                "title": str(item.get("title", "유사 민원")),
                "snippet": str(item.get("snippet", "")),
                "summary": summary,
                "metadata": {
                    "created_at": created_at,
                    "category": category,
                    "region": region,
                    "entity_labels": entity_labels,
                },
                # UI convenience/backward compatibility
                "similarity_score": score,
                "received_at": created_at or "-",
                "created_at": created_at,
                "category": category or "-",
                "region": region or "-",
                "entity_labels": entity_labels,
            }
        )
    return normalized


def search_cases_via_api_with_filters(
    query: str,
    top_k: int,
    date_range: Any,
    region: str,
    category: str,
    entity_labels: List[str],
) -> tuple[List[Dict[str, Any]], str | None]:
    """지정된 필터로 /api/v1/search를 호출한다.

    Returns:
        (results, friendly_error_message)
    """

    date_from = None
    date_to = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_from = _to_iso_date(date_range[0])
        date_to = _to_iso_date(date_range[1])

    filters: Dict[str, Any] = {}
    if region and region != "전체":
        filters["region"] = region
    if category and category != "전체":
        filters["category"] = category
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    if entity_labels:
        filters["entity_labels"] = entity_labels

    payload = {
        "query": query,
        "top_k": top_k,
        "filters": filters or None,
    }

    res, status_code, err = post_json(st.session_state.api_base_url, "/api/v1/search", payload, timeout=25.0)

    if err:
        return [], get_friendly_error_message(int(status_code or 0), str(err))

    if isinstance(res, dict) and res.get("success") is True:
        return normalize_search_results_from_api(res), None

    raw_msg = (
        str(res.get("error", {}).get("message", "검색 응답 처리 실패"))
        if isinstance(res, dict)
        else "검색 응답 처리 실패"
    )
    return [], get_friendly_error_message(0, raw_msg)


def search_similar_cases_for_workbench(query: str, top_k: int = 5) -> tuple[List[Dict[str, Any]], str | None]:
    """워크벤치(스크린샷) 테이블에 바로 넣을 유사 민원 rows를 만든다.

    - API 사용 가능하면 /api/v1/search 결과를 축약 변환
    - mock/오류면 UI 고정 더미 2개로 폴백
    """

    if not query:
        query = "유사 민원"

    # In demo mode, avoid noisy errors and show stable rows.
    if st.session_state.get("ui_force_mock", False):
        return (
            [
                {"case_id": "CASE_20231102-09", "date": "2023.11.02", "similarity": "92%", "status": "COMPLETED"},
                {"case_id": "CASE_20240115-04", "date": "2024.01.15", "similarity": "88%", "status": "COMPLETED"},
            ],
            None,
        )

    results, err = search_cases_via_api_with_filters(
        query=query,
        top_k=top_k,
        date_range=(None, None),
        region="전체",
        category="전체",
        entity_labels=[],
    )

    if err or not results:
        return (
            [
                {"case_id": "CASE_20231102-09", "date": "2023.11.02", "similarity": "92%", "status": "COMPLETED"},
                {"case_id": "CASE_20240115-04", "date": "2024.01.15", "similarity": "88%", "status": "COMPLETED"},
            ],
            err,
        )

    rows: List[Dict[str, Any]] = []
    for item in results[: max(1, int(top_k or 5))]:
        case_id = str(item.get("case_id") or item.get("doc_id") or "-")
        created_at = item.get("created_at") or (item.get("metadata", {}) or {}).get("created_at")
        date_text = str(created_at or "-")
        try:
            score = float(item.get("score", item.get("similarity_score", 0.0)) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        rows.append(
            {
                "case_id": case_id,
                "date": date_text,
                "similarity": f"{int(round(score * 100))}%",
                "status": "COMPLETED" if score >= 0.5 else "PENDING",
            }
        )
    return rows, None

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import streamlit as st
from urllib import error as urlerror
from urllib import request as urlrequest

from app.core.title_builder import build_case_title

def _extract_admin_units_from_text(text: str) -> list[str]:
    """텍스트에서 부서(ADMIN_UNIT) 후보를 가볍게 추출한다.

    BE 검색 결과에는 보통 entity_labels만 있고 entity text가 없어서,
    워크벤치 유사민원 UI 데모 안정성을 위해 UI 레이어에서만 사용하는 휴리스틱이다.
    """

    if not text:
        return []

    candidates: list[str] = []
    patterns = [
        r"\b\d{1,2}\s*부서\b",  # 1부서, 2 부서
        r"[가-힣]{2,}(?:과|팀|국|실)\b",  # 도로과, 환경팀, 교통국
    ]

    for pat in patterns:
        for m in re.finditer(pat, text):
            token = (m.group(0) or "").strip()
            if token and token not in candidates:
                candidates.append(token)

    return candidates[:5]


def _build_department_tracks(
    *,
    admin_units: list[str],
    complaint: str,
    default_answer: str,
    answers_by_unit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    answers_by_unit = answers_by_unit if isinstance(answers_by_unit, dict) else None

    for unit in admin_units:
        unit_answer = ""
        if answers_by_unit and unit in answers_by_unit:
            unit_answer = str(answers_by_unit.get(unit) or "").strip()
        if not unit_answer:
            unit_answer = default_answer or "(부서별 답변 데이터 없음)"

        tracks.append(
            {
                "admin_unit": unit,
                "complaint": complaint,
                "answer": unit_answer,
            }
        )

    return tracks


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


def get_friendly_error_message_for_api(api_name: str, err_code: int, raw_msg: str) -> str:
    """API 종류(/search, /qa 등)에 따라 사용자 메시지를 표준화한다."""

    name = (api_name or "").strip().lower()
    base = get_friendly_error_message(err_code, raw_msg)
    if name in ("qa", "/qa"):
        # search 문구를 qa 문구로 치환(최소 변경)
        return base.replace("검색", "QA")
    return base


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


def normalize_qa_response_from_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """/api/v1/qa 응답을 UI 표시용 포맷으로 정규화한다.

    허용 입력:
    - {success: true, answer, citations, limitations, ...}
    - {success: true, data: {answer, citations, limitations, ...}}
    """

    if not isinstance(payload, dict):
        return {
            "success": False,
            "answer": "",
            "citations": [],
            "limitations": None,
            "confidence": None,
            "meta": {},
            "qa_validation": None,
            "error": {"message": "QA 응답이 올바른 JSON 객체가 아닙니다."},
        }

    root_success = payload.get("success")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    src = data if data is not None else payload

    success = bool(root_success) if root_success is not None else bool(src.get("answer") or src.get("citations"))
    citations = src.get("citations")
    citations = citations if isinstance(citations, list) else []

    return {
        "success": success,
        "answer": str(src.get("answer", "") or ""),
        "citations": citations,
        "limitations": src.get("limitations"),
        "confidence": src.get("confidence"),
        "meta": src.get("meta", {}) if isinstance(src.get("meta"), dict) else {},
        "qa_validation": src.get("qa_validation") if isinstance(src.get("qa_validation"), dict) else None,
        "error": payload.get("error") if isinstance(payload.get("error"), dict) else None,
    }


def run_qa_via_api(
    *,
    query: str,
    top_k: int,
    use_search_results: bool,
    search_results: list[dict[str, Any]] | None,
    filters: dict[str, Any] | None,
    timeout: float = 35.0,
) -> tuple[Dict[str, Any], str | None]:
    """/api/v1/qa를 호출하고 (normalized_payload, friendly_error) 를 반환한다."""

    payload = {
        "query": query,
        "top_k": int(top_k or 5),
        "use_search_results": bool(use_search_results),
        "search_results": search_results or [],
        "filters": filters or None,
    }

    res, status_code, err = post_json(st.session_state.api_base_url, "/api/v1/qa", payload, timeout=timeout)
    if err and not res:
        return {}, get_friendly_error_message_for_api("qa", int(status_code or 0), str(err))

    normalized = normalize_qa_response_from_api(res)
    if normalized.get("success") is True:
        return normalized, None

    raw_msg = "QA 응답 생성 실패"
    if isinstance(res, dict):
        raw_msg = str((res.get("error") or {}).get("message") or raw_msg)
    return normalized, get_friendly_error_message_for_api("qa", int(status_code or 0), raw_msg)


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

        normalized_title = build_case_title(
            explicit_title=item.get("title"),
            observation=(summary or {}).get("observation"),
            request=(summary or {}).get("request"),
            chunk_text=item.get("snippet"),
            category=category,
        )

        normalized.append(
            {
                # BE2 contract fields
                "rank": int(item.get("rank", 0) or 0),
                "doc_id": str(item.get("doc_id", "")),
                "score": score,
                "chunk_id": str(item.get("chunk_id", "")),
                "case_id": str(item.get("case_id", "")),
                "title": normalized_title,
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
                {
                    "case_id": "CASE_20231102-09",
                    "date": "2023.11.02",
                    "similarity": "92%",
                    "status": "COMPLETED",
                    "complaint": "지하차도 진입부 조명이 소등되어 야간 시야 확보가 어렵습니다. 조속한 점검이 필요합니다.",
                    "answer": "현장 점검을 실시하고 고장 가로등을 교체하겠습니다. 임시 안전 표지 설치 후 복구 일정을 안내드립니다.",
                    "department_tracks": [
                        {
                            "admin_unit": "도로과",
                            "complaint": "지하차도 진입부 조명이 소등되어 야간 시야 확보가 어렵습니다.",
                            "answer": "현장 점검 후 고장 조명을 교체하고, 복구 일정을 안내하겠습니다.",
                        }
                    ],
                },
                {
                    "case_id": "CASE_20240115-04",
                    "date": "2024.01.15",
                    "similarity": "88%",
                    "status": "COMPLETED",
                    "complaint": "아파트 인근 무단투기로 악취가 심합니다. 단속 강화와 CCTV 설치 검토를 요청합니다.",
                    "answer": "관계 부서와 합동 단속을 진행하고 취약 시간대 순찰을 강화하겠습니다. CCTV 설치는 현장 여건 검토 후 추진하겠습니다.",
                    "department_tracks": [
                        {
                            "admin_unit": "1부서",
                            "complaint": "무단투기 단속 강화 요청",
                            "answer": "취약 시간대 합동 단속을 우선 시행하고, 계도문 부착 및 수거 주기를 조정하겠습니다.",
                        },
                        {
                            "admin_unit": "2부서",
                            "complaint": "악취 민원(현장 정비) 요청",
                            "answer": "현장 정비 및 소독을 진행하고, 재발 구간에 임시 적치 금지 안내물을 설치하겠습니다.",
                        },
                        {
                            "admin_unit": "3부서",
                            "complaint": "CCTV 설치 검토 요청",
                            "answer": "설치 후보 지점을 현장 여건(전원/사각지대/민원 빈도) 기준으로 검토 후 설치 계획을 회신하겠습니다.",
                        },
                    ],
                },
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
                {
                    "case_id": "CASE_20231102-09",
                    "date": "2023.11.02",
                    "similarity": "92%",
                    "status": "COMPLETED",
                    "complaint": "지하차도 진입부 조명이 소등되어 야간 시야 확보가 어렵습니다. 조속한 점검이 필요합니다.",
                    "answer": "현장 점검을 실시하고 고장 가로등을 교체하겠습니다. 임시 안전 표지 설치 후 복구 일정을 안내드립니다.",
                    "department_tracks": [
                        {
                            "admin_unit": "도로과",
                            "complaint": "지하차도 진입부 조명 소등",
                            "answer": "현장 점검 후 고장 조명을 교체하고, 복구 일정을 안내하겠습니다.",
                        }
                    ],
                },
                {
                    "case_id": "CASE_20240115-04",
                    "date": "2024.01.15",
                    "similarity": "88%",
                    "status": "COMPLETED",
                    "complaint": "아파트 인근 무단투기로 악취가 심합니다. 단속 강화와 CCTV 설치 검토를 요청합니다.",
                    "answer": "관계 부서와 합동 단속을 진행하고 취약 시간대 순찰을 강화하겠습니다. CCTV 설치는 현장 여건 검토 후 추진하겠습니다.",
                    "department_tracks": [
                        {
                            "admin_unit": "1부서",
                            "complaint": "무단투기 단속 강화 요청",
                            "answer": "취약 시간대 합동 단속을 우선 시행하고, 계도문 부착 및 수거 주기를 조정하겠습니다.",
                        },
                        {
                            "admin_unit": "2부서",
                            "complaint": "악취 민원(현장 정비) 요청",
                            "answer": "현장 정비 및 소독을 진행하고, 재발 구간에 임시 적치 금지 안내물을 설치하겠습니다.",
                        },
                        {
                            "admin_unit": "3부서",
                            "complaint": "CCTV 설치 검토 요청",
                            "answer": "설치 후보 지점을 현장 여건(전원/사각지대/민원 빈도) 기준으로 검토 후 설치 계획을 회신하겠습니다.",
                        },
                    ],
                },
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

        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        complaint = str(summary.get("observation") or item.get("title") or item.get("snippet") or "").strip()
        answer = str(
            summary.get("request")
            or item.get("answer")
            or item.get("final_answer")
            or item.get("response")
            or (item.get("metadata", {}) or {}).get("answer")
            or ""
        ).strip()
        if not answer:
            # 데이터셋/인덱스에 '답변' 필드가 없는 경우에도 UI는 두 칸을 유지한다.
            answer = "(답변 데이터 없음)"

        # 복합 민원(다부서) 데모를 위한 부서 트랙 구성
        answers_by_unit = (
            item.get("answers_by_admin_unit")
            or item.get("department_answers")
            or (item.get("metadata", {}) or {}).get("answers_by_admin_unit")
            or (item.get("metadata", {}) or {}).get("department_answers")
        )
        admin_units = _extract_admin_units_from_text(complaint) or _extract_admin_units_from_text(str(item.get("snippet") or ""))
        department_tracks = _build_department_tracks(
            admin_units=admin_units,
            complaint=complaint,
            default_answer=answer,
            answers_by_unit=answers_by_unit if isinstance(answers_by_unit, dict) else None,
        )

        rows.append(
            {
                "case_id": case_id,
                "date": date_text,
                "similarity": f"{int(round(score * 100))}%",
                "status": "COMPLETED" if score >= 0.5 else "PENDING",
                "complaint": complaint,
                "answer": answer,
                "department_tracks": department_tracks,
            }
        )
    return rows, None

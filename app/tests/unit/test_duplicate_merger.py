from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import get_complaint_intelligence_service


BASE_TIME = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_duplicate_groups():
    service = get_complaint_intelligence_service()
    service.duplicate_merge_service.clear()
    yield
    service.duplicate_merge_service.clear()


def _event(
    event_id: str,
    *,
    region: str = "행복아파트",
    minutes_ago: int = 0,
    department: str = "환경관리과",
    request_text: str = "공사 소음 저감 조치 요청",
    observation: str = "행복아파트 앞 공사장에서 소음과 진동이 반복됩니다.",
    result: str = "야간 휴식에 불편이 발생했습니다.",
    context: str = "같은 아파트 단지 주변에서 반복 접수된 민원입니다.",
    entity_texts: list[str] | None = None,
    request_segments: list[str] | None = None,
    body: str | None = None,
) -> dict:
    return {
        "id": event_id,
        "received_at": (BASE_TIME - timedelta(minutes=minutes_ago)).isoformat(),
        "body": body or f"{region} 공사 소음 반복 신고입니다.",
        "region": region,
        "final_department": department,
        "civil_category": "생활불편",
        "entity_texts": entity_texts or [region, "공사장", "소음", "진동"],
        "request_segments": request_segments or [request_text],
        "structured_elements": {
            "observation": {"text": observation},
            "result": {"text": result},
            "request": {"text": request_text},
            "context": {"text": context},
        },
    }


def _run_analysis(client: TestClient, events: list[dict]) -> dict:
    response = client.post("/complaint-intelligence/duplicate-groups/run-analysis", json={"events": events})
    assert response.status_code == 200
    return response.json()["data"]


def test_same_apartment_noise_complaints_create_candidate_group_with_contract_fields() -> None:
    client = TestClient(app)
    events = [
        _event(
            "noise-basic",
            minutes_ago=30,
            observation="행복아파트 앞 공사 소음이 반복됩니다.",
            context="행복아파트 정문 주변 반복 민원입니다.",
            entity_texts=["행복아파트", "공사장", "소음"],
        ),
        _event(
            "noise-rich",
            minutes_ago=5,
            observation="행복아파트 정문 공사장에서 야간 소음과 진동이 반복됩니다.",
            result="입주민 수면 방해와 생활 불편이 누적됩니다.",
            request_text="야간 공사 소음 저감 조치와 작업 시간 안내 요청",
            context="행복아파트 정문과 1단지 출입구 주변에서 같은 내용이 반복 접수됩니다.",
            entity_texts=["행복아파트", "1단지 출입구", "공사장", "야간 소음", "진동"],
            request_segments=["야간 공사 소음 저감 조치 요청", "작업 시간 안내 요청"],
        ),
    ]

    data = _run_analysis(client, events)

    assert data["count"] == 1
    group = data["duplicate_groups"][0]
    assert group["status"] == "candidate"
    assert group["representative_complaint_id"] == "noise-rich"
    assert set(group["member_complaint_ids"]) == {"noise-basic", "noise-rich"}
    assert group["evidence"]
    assert "confirm" in group["allowed_actions"]
    assert "draft_reply" in group["blocked_actions"]
    assert group["representative"]["selection_reason"]


def test_same_keywords_different_locations_get_location_mismatch_or_separate_groups() -> None:
    client = TestClient(app)
    events = [
        _event("noise-happy", region="행복아파트", entity_texts=["행복아파트", "공사장", "소음"]),
        _event("noise-blue", region="푸른아파트", entity_texts=["푸른아파트", "공사장", "소음"]),
    ]

    data = _run_analysis(client, events)

    if data["count"] == 0:
        assert data["duplicate_groups"] == []
    else:
        codes = {flag["code"] for flag in data["duplicate_groups"][0]["risk_flags"]}
        assert "LOCATION_MISMATCH" in codes


def test_request_type_mismatch_is_reported_for_same_event_group() -> None:
    client = TestClient(app)
    events = [
        _event(
            "parking-enforcement",
            region="연희초등학교",
            department="교통지도과",
            request_text="불법 주정차 단속 강화 요청",
            observation="연희초등학교 앞 불법 주정차가 반복됩니다.",
            entity_texts=["연희초등학교", "불법주정차"],
        ),
        _event(
            "parking-compensation",
            region="연희초등학교",
            department="교통지도과",
            request_text="불법 주정차 차량으로 인한 차량 파손 피해 보상 요청",
            observation="연희초등학교 앞 같은 위치에서 차량 파손 피해가 발생했습니다.",
            entity_texts=["연희초등학교", "불법주정차"],
        ),
    ]

    data = _run_analysis(client, events)

    group = data["duplicate_groups"][0]
    codes = {flag["code"] for flag in group["risk_flags"]}
    assert "REQUEST_TYPE_MISMATCH" in codes
    assert "LEGAL_RIGHTS_OR_DEADLINE_RISK" in codes


def test_candidate_draft_reply_is_rejected_with_409() -> None:
    client = TestClient(app)
    data = _run_analysis(client, [_event("draft-candidate-1"), _event("draft-candidate-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/draft-reply")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_GROUP_NOT_CONFIRMED"


def test_confirmed_group_returns_pii_safe_draft_reply_payload() -> None:
    client = TestClient(app)
    events = [
        _event(
            "draft-safe-1",
            observation="서울로 123 101동 202호 앞 공사 소음이 반복됩니다. 010-1234-5678로 연락 요청",
            context="행복아파트 같은 위치에서 반복된 민원입니다.",
            body="서울로 123 101동 202호 앞 공사 소음입니다. 010-1234-5678 연락 바랍니다.",
        ),
        _event(
            "draft-safe-2",
            minutes_ago=12,
            observation="서울로 123 주변 공사 소음과 진동이 반복됩니다.",
            context="행복아파트 주변 같은 공사장 관련 민원입니다.",
        ),
    ]
    data = _run_analysis(client, events)
    merge_id = data["duplicate_groups"][0]["merge_id"]

    confirm_response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["data"]["duplicate_group"]["status"] == "confirmed"

    draft_response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/draft-reply")
    assert draft_response.status_code == 200
    payload = draft_response.json()["data"]["draft_reply_payload"]
    serialized = draft_response.text

    assert payload["merge_id"] == merge_id
    assert payload["representative"]["structured_elements"]
    assert "010-1234-5678" not in serialized
    assert "101동 202호" not in serialized
    assert "[REDACTED:PHONE]" in serialized
    assert "개별 보상" in " ".join(payload["prohibited_content_rules"])


def test_rejected_and_split_groups_cannot_build_draft_reply() -> None:
    client = TestClient(app)
    rejected_data = _run_analysis(client, [_event("reject-1"), _event("reject-2", minutes_ago=5)])
    rejected_id = rejected_data["duplicate_groups"][0]["merge_id"]
    reject_response = client.post(f"/complaint-intelligence/duplicate-groups/{rejected_id}/reject")
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["duplicate_group"]["status"] == "rejected"
    rejected_draft = client.post(f"/complaint-intelligence/duplicate-groups/{rejected_id}/draft-reply")
    assert rejected_draft.status_code == 409

    get_complaint_intelligence_service().duplicate_merge_service.clear()
    split_data = _run_analysis(client, [_event("split-1"), _event("split-2", minutes_ago=5)])
    split_id = split_data["duplicate_groups"][0]["merge_id"]
    split_response = client.post(f"/complaint-intelligence/duplicate-groups/{split_id}/split")
    assert split_response.status_code == 200
    assert split_response.json()["data"]["duplicate_group"]["status"] == "split"
    split_draft = client.post(f"/complaint-intelligence/duplicate-groups/{split_id}/draft-reply")
    assert split_draft.status_code == 409

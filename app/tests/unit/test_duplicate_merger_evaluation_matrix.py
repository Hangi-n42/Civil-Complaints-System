from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeConflict, DuplicateMergeService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


def _event(
    event_id: str,
    *,
    region: str = "행복아파트",
    hours_ago: int = 0,
    department: str = "환경관리과",
    civil_category: str = "생활불편",
    observation: str = "행복아파트 앞 공사장에서 소음과 진동이 반복됩니다.",
    result: str = "야간 휴식에 불편이 발생했습니다.",
    request: str = "공사 소음 저감 조치 요청",
    context: str = "같은 아파트 단지 주변에서 반복 접수된 민원입니다.",
    entity_texts: list[str] | None = None,
    request_segments: list[str] | None = None,
    body: str | None = None,
    structured: bool = True,
) -> dict:
    payload = {
        "id": event_id,
        "received_at": (BASE_TIME - timedelta(hours=hours_ago)).isoformat(),
        "body": body or f"{region} {request}",
        "region": region,
        "final_department": department,
        "civil_category": civil_category,
        "entity_texts": entity_texts if entity_texts is not None else [region, "공사장", "소음", "진동"],
        "request_segments": request_segments if request_segments is not None else [request],
    }
    if structured:
        payload["structured_elements"] = {
            "observation": {"text": observation},
            "result": {"text": result},
            "request": {"text": request},
            "context": {"text": context},
        }
    return payload


def _analyze(events: list[dict]) -> tuple[DuplicateMergeService, list]:
    service = DuplicateMergeService()
    models = [ComplaintIntelligenceEvent.model_validate(event) for event in events]
    return service, service.run_analysis(models)


def _codes(group) -> set[str]:
    return {flag.code for flag in group.risk_flags}


def _blockers(group) -> set[str]:
    return {flag.code for flag in group.risk_flags if flag.severity == "blocker"}


def test_duplicate_merger_operational_scenario_matrix() -> None:
    service, groups = _analyze(
        [
            _event(
                "noise-basic",
                hours_ago=1,
                observation="행복아파트 정문 공사 소음이 반복됩니다.",
                entity_texts=["행복아파트", "정문", "공사장", "소음"],
            ),
            _event(
                "noise-rich",
                request="야간 공사 소음 저감 조치와 작업 시간 안내 요청",
                context="행복아파트 정문과 1단지 출입구 주변에서 같은 내용이 반복 접수됩니다.",
                entity_texts=["행복아파트", "1단지 출입구", "공사장", "야간 소음", "진동"],
            ),
        ]
    )
    assert len(groups) == 1
    assert groups[0].representative_complaint_id == "noise-rich"
    assert "confirm" in groups[0].allowed_actions
    assert "draft_reply" in groups[0].blocked_actions
    assert not _blockers(groups[0])
    with pytest.raises(DuplicateMergeConflict) as candidate_draft:
        service.build_draft_reply_payload(groups[0].merge_id)
    assert candidate_draft.value.code == "DUPLICATE_GROUP_NOT_CONFIRMED"

    _, department_groups = _analyze(
        [
            _event("dept-noise-1", department="환경관리과"),
            _event("dept-noise-2", department="도로관리과"),
        ]
    )
    assert len(department_groups) == 1
    assert "DEPARTMENT_MISMATCH" in _blockers(department_groups[0])
    assert "confirm" not in department_groups[0].allowed_actions

    service, request_groups = _analyze(
        [
            _event(
                "parking-enforcement",
                region="연희초등학교",
                department="교통지도과",
                request="불법 주정차 단속 강화 요청",
                observation="연희초등학교 앞 불법 주정차가 반복됩니다.",
                entity_texts=["연희초등학교", "불법주정차", "차량"],
            ),
            _event(
                "parking-compensation",
                region="연희초등학교",
                department="교통지도과",
                request="불법 주정차 차량으로 인한 차량 파손 피해 보상 요청",
                observation="연희초등학교 앞 같은 위치에서 차량 파손 피해가 발생했습니다.",
                entity_texts=["연희초등학교", "불법주정차", "차량"],
            ),
        ]
    )
    assert len(request_groups) == 1
    assert {"REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"} <= _codes(request_groups[0])
    with pytest.raises(DuplicateMergeConflict) as blocked_confirm:
        service.confirm_group(request_groups[0].merge_id)
    assert blocked_confirm.value.code == "DUPLICATE_GROUP_BLOCKED_BY_RISK"

    _, time_groups = _analyze([_event("wide-time-1"), _event("wide-time-2", hours_ago=120)])
    assert len(time_groups) == 1
    assert "TIME_WINDOW_TOO_WIDE" in _codes(time_groups[0])
    assert time_groups[0].recommendation_level == "review"

    _, low_evidence_groups = _analyze(
        [
            _event(
                "low-evidence-1",
                body="행복아파트 공사 소음 반복 신고입니다.",
                entity_texts=[],
                request_segments=[],
                structured=False,
            ),
            _event(
                "low-evidence-2",
                body="행복아파트 공사 소음 반복 신고입니다.",
                entity_texts=[],
                request_segments=[],
                structured=False,
            ),
        ]
    )
    assert len(low_evidence_groups) == 1
    assert "LOW_EVIDENCE" in _codes(low_evidence_groups[0])

    _, safety_groups = _analyze(
        [
            _event(
                "road-safety",
                region="중앙로12길",
                department="도로관리과",
                request="도로 침하 사고 위험 긴급 점검 요청",
                observation="중앙로12길 도로가 내려앉아 사고 위험이 있습니다.",
                entity_texts=["중앙로12길", "도로침하", "싱크홀"],
            ),
            _event(
                "road-inquiry",
                region="중앙로12길",
                department="도로관리과",
                request="도로 파임 접수 처리 절차 문의",
                observation="중앙로12길 도로 파임 접수 처리 절차가 궁금합니다.",
                entity_texts=["중앙로12길", "도로파임"],
            ),
        ]
    )
    assert len(safety_groups) == 1
    assert "SAFETY_AND_INCONVENIENCE_MIXED" in _blockers(safety_groups[0])


def test_confirmed_draft_payload_masks_pii_and_preserves_safety_contract() -> None:
    service, groups = _analyze(
        [
            _event(
                "pii-noise-1",
                observation="서울로 123 101동 202호 앞 공사 소음입니다. 010-1234-5678 연락 요청",
                context="행복아파트 같은 위치에서 반복된 민원입니다.",
                body="서울로 123 101동 202호 앞 공사 소음입니다. 010-1234-5678 연락 바랍니다.",
            ),
            _event(
                "pii-noise-2",
                hours_ago=1,
                observation="서울로 123 주변 공사 소음과 진동이 반복됩니다.",
                context="행복아파트 주변 같은 공사장 관련 민원입니다.",
            ),
        ]
    )
    assert len(groups) == 1
    confirmed = service.confirm_group(groups[0].merge_id)
    payload = service.build_draft_reply_payload(confirmed.merge_id)
    serialized = payload.model_dump_json()

    assert payload.merge_id == confirmed.merge_id
    assert payload.representative.structured_elements
    assert "010-1234-5678" not in serialized
    assert "101동 202호" not in serialized
    assert "[REDACTED:PHONE]" in serialized
    assert any("개별 보상" in rule for rule in payload.prohibited_content_rules)


@pytest.mark.xfail(
    reason="현재 위치 판단은 같은 광역 region을 exact로 처리해 서로 다른 세부 장소를 과잉 후보화할 수 있습니다.",
    strict=False,
)
def test_broad_region_with_different_precise_sites_should_be_blocked_or_split() -> None:
    _, groups = _analyze(
        [
            _event(
                "broad-region-a",
                region="중구",
                request="공사 소음 저감 조치 요청",
                observation="중구청 앞 공사장 소음이 반복됩니다.",
                entity_texts=["중구청 앞", "공사장", "소음"],
            ),
            _event(
                "broad-region-b",
                region="중구",
                request="공사 소음 저감 조치 요청",
                observation="중구문화센터 앞 공사장 소음이 반복됩니다.",
                entity_texts=["중구문화센터 앞", "공사장", "소음"],
            ),
        ]
    )
    assert not groups or {"LOCATION_MISMATCH", "LOCATION_AMBIGUOUS"} & _codes(groups[0])

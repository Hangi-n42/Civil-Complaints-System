from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import set_complaint_intelligence_service
from app.complaint_intelligence.duplicate_merger.candidate_generator import DuplicateCandidateGenerator
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from scripts.build_complaint_intelligence_demo_seed import build_demo_seed
from scripts.prepare_complaint_intelligence_real_replay import (
    choose_seed_payload,
    count_seed_events,
)
from scripts.seed_complaint_intelligence_demo import (
    build_service,
    load_seed,
    seed_events,
    validate_dashboard,
    validate_pii,
    validate_scenarios,
)


SEED_PATH = Path("data/demo/complaint_intelligence_demo_events.json")
AS_OF = datetime.fromisoformat("2026-06-20T09:00:00+09:00")


def test_demo_seed_json_loads_as_complaint_intelligence_events() -> None:
    seed = load_seed(SEED_PATH)
    events = seed_events(seed)

    assert events
    assert all(isinstance(event, ComplaintIntelligenceEvent) for event in events)
    assert all(event.masked_text for event in events)
    assert all("010-1234-5678" not in event.masked_text for event in events)


def test_build_script_extracts_candidates_from_fixture_data(tmp_path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            [
                {"source_id": "road-1", "raw_text": "도로에 싱크홀 침하 구멍이 생겨 위험합니다.", "consulting_category": "도로관리과"},
                {"source_id": "park-1", "raw_text": "어린이보호구역 불법주정차 단속을 요청합니다.", "consulting_category": "교통지도과"},
                {"source_id": "waste-1", "raw_text": "대형폐기물 배출 스티커 신청 방법 안내가 필요합니다.", "consulting_category": "청소행정과"},
                {"source_id": "welfare-1", "raw_text": "복지 지원 기준과 신청 서류 절차가 어렵습니다.", "consulting_category": "복지정책과"},
                {"source_id": "odor-1", "raw_text": "하수 냄새와 악취가 밤마다 심합니다.", "consulting_category": "환경관리과"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    seed, report = build_demo_seed(
        input_paths=[fixture],
        as_of=AS_OF,
        min_events_per_scenario=1,
        max_events_per_scenario=1,
        allow_synthetic_fill=False,
    )

    assert len(seed["scenarios"]) == 5
    assert all(len(scenario["events"]) == 1 for scenario in seed["scenarios"])
    assert all(
        event["latitude"] is not None and event["longitude"] is not None
        for scenario in seed["scenarios"]
        for event in scenario["events"]
    )
    assert all(
        not scenario["events"][0]["title"].startswith("demo-")
        for scenario in seed["scenarios"]
    )
    assert all(
        len({event["title"] for event in scenario["events"]}) == len(scenario["events"])
        for scenario in seed["scenarios"]
    )
    assert all(
        scenario["events"][0]["entity_texts"]
        and scenario["events"][0]["request_segments"]
        and scenario["events"][0]["responsible_unit"]
        for scenario in seed["scenarios"]
    )
    assert {scenario["events"][0]["region"] for scenario in seed["scenarios"]} >= {
        "서울특별시 중구",
        "인천광역시 서구",
        "전북특별자치도 전주시 덕진구",
        "대전광역시 중구",
        "울산광역시 남구",
    }
    assert all(item["synthetic_event_count"] == 0 for item in report["scenarios"])


def test_replay_seed_fields_create_confirmable_duplicate_candidates(tmp_path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            [
                {"source_id": "park-1", "raw_text": "어린이보호구역 불법주정차 차량 단속을 요청합니다.", "consulting_category": "교통지도과"},
                {"source_id": "park-2", "raw_text": "어린이보호구역 불법주차 차량이 반복되어 현장단속이 필요합니다.", "consulting_category": "교통지도과"},
                {"source_id": "waste-1", "raw_text": "대형폐기물 배출 스티커 신청 방법 안내가 필요합니다.", "consulting_category": "청소행정과"},
                {"source_id": "waste-2", "raw_text": "대형폐기물 수거 신청 절차와 배출 방법을 알고 싶습니다.", "consulting_category": "청소행정과"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    seed, _report = build_demo_seed(
        input_paths=[fixture],
        as_of=AS_OF,
        min_events_per_scenario=0,
        max_events_per_scenario=2,
        allow_synthetic_fill=False,
    )
    events = [
        ComplaintIntelligenceEvent.model_validate(event)
        for scenario in seed["scenarios"]
        for event in scenario["events"]
    ]
    groups = DuplicateCandidateGenerator().generate(events)

    assert groups
    assert any("confirm" in group.allowed_actions for group in groups)
    assert all(not (event.title or "").startswith("demo-") for event in events)


def test_seed_script_runs_real_pipeline_and_creates_dashboard_read_model(tmp_path) -> None:
    service, seed, alerts, insights = _run_seed(tmp_path)

    state = service.get_dashboard_state()
    dashboard = validate_dashboard(state, alerts, insights)
    scenario_results = validate_scenarios(seed, alerts, insights, service)

    assert dashboard["passed"] is True
    assert state.event_count > 0
    assert len(alerts) >= 1
    assert len(insights) >= 1
    assert all(item["passed"] for item in scenario_results)


def test_threshold_validation_fails_when_alerts_and_insights_are_empty() -> None:
    state = SimpleNamespace(
        as_of=None,
        latest_event_at=None,
        event_count=0,
        active_alert_count=0,
        high_priority_insight_count=0,
    )

    result = validate_dashboard(state, [], [])

    assert result["passed"] is False
    assert {failure["code"] for failure in result["failures"]} >= {
        "NO_EVENTS",
        "NO_ALERT_CREATED",
        "NO_PUBLIC_INSIGHT_CREATED",
    }


def test_real_replay_prepare_keeps_existing_seed_when_new_build_is_empty(tmp_path) -> None:
    seed_path = tmp_path / "real_replay.json"
    existing_seed = {
        "scenarios": [
            {
                "id": "existing",
                "events": [{"id": "existing-1"}],
            }
        ]
    }
    generated_seed = {"scenarios": [{"id": "empty", "events": []}]}
    seed_path.write_text(json.dumps(existing_seed), encoding="utf-8")

    selected_seed, should_write_seed, fallback = choose_seed_payload(generated_seed, seed_path)

    assert selected_seed == existing_seed
    assert should_write_seed is False
    assert fallback is not None
    assert fallback["existing_event_count"] == 1
    assert count_seed_events(selected_seed) == 1


def test_real_replay_prepare_fails_before_db_reset_when_no_seed_data(tmp_path) -> None:
    generated_seed = {"scenarios": [{"id": "empty", "events": []}]}

    try:
        choose_seed_payload(generated_seed, tmp_path / "missing.json")
    except RuntimeError as exc:
        assert "기존 seed도 비어" in str(exc)
    else:
        raise AssertionError("empty real_replay seed must fail instead of overwriting data")


def test_seed_pipeline_masks_pii_in_reports_dashboard_and_evidence_pack(tmp_path) -> None:
    seed = {
        "mode": "replay",
        "source_name": "pii_demo",
        "as_of": AS_OF.isoformat(),
        "scenarios": [
            {
                "id": "pii_sinkhole",
                "label": "도로 침하/싱크홀 급증",
                "expected_alert": True,
                "expected_insight_types": ["SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"],
                "events": [
                    {
                        "id": f"pii-sinkhole-{index}",
                        "received_at": (AS_OF - timedelta(minutes=10 + index * 5)).isoformat(),
                        "body": f"010-1234-5678로 연락 주세요. 101동 202호 앞 도로 싱크홀 침하 구멍 위험 신고 {index}",
                        "region": "중구",
                        "final_department": "도로관리과",
                        "status": "open",
                    }
                    for index in range(5)
                ],
            }
        ],
    }
    events = seed_events(seed)
    safe_seed = {
        **seed,
        "scenarios": [
            {
                **seed["scenarios"][0],
                "events": [event.model_dump(mode="json") for event in events],
            }
        ],
    }
    service = build_service(tmp_path / "pii.db", demo_thresholds=False)
    service.run_analysis(events, mode="replay", source_name="pii_demo", as_of=AS_OF)
    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()

    pii = validate_pii(safe_seed, alerts, insights, service)

    assert pii["passed"] is True
    assert "010-1234-5678" not in json.dumps([alert.model_dump(mode="json") for alert in alerts], ensure_ascii=False)
    assert all(service.get_public_insight_evidence_pack(insight.insight_id) is not None for insight in insights)


def test_default_seed_without_demo_thresholds_creates_alert_and_insight(tmp_path) -> None:
    service, _seed, alerts, insights = _run_seed(tmp_path)

    assert service.get_dashboard_state().active_alert_count >= 1
    assert len(alerts) >= 1
    assert len(insights) >= 1


def test_dashboard_endpoint_contract_after_demo_seed_run(tmp_path) -> None:
    service, _seed, _alerts, _insights = _run_seed(tmp_path)
    set_complaint_intelligence_service(service)
    client = TestClient(app)

    response = client.get("/complaint-intelligence/dashboard")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["event_count"] > 0
    assert data["summary"]["active_alert_count"] >= 1
    assert data["issue_alerts"]
    assert data["public_insights"]
    set_complaint_intelligence_service(None)


def _run_seed(tmp_path):
    seed = load_seed(SEED_PATH)
    events = seed_events(seed)
    service = build_service(tmp_path / "demo_seed.db", demo_thresholds=False)
    service.run_analysis(
        events,
        mode=str(seed.get("mode") or "replay"),
        source_name=str(seed.get("source_name") or "complaint_intelligence_demo"),
        as_of=datetime.fromisoformat(str(seed.get("as_of"))),
    )
    return service, seed, service.list_issue_alerts(), service.list_public_insights()

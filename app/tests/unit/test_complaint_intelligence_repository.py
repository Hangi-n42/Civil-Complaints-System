from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import set_complaint_intelligence_service
from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.duplicate_merger.schemas import (
    DuplicateMergeRecord,
    DuplicateRepresentative,
)
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.repository import InMemoryComplaintIntelligenceRepository
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicAgencyInsight,
    PublicInsightEvidence,
    RecommendedAction,
    RepresentativeComplaint,
)
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.complaint_intelligence.sqlite_repository import SQLiteComplaintIntelligenceRepository


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_global_service() -> None:
    """API 테스트가 실제 데모 SQLite DB를 건드리지 않도록 공유 서비스를 되돌린다."""

    yield
    set_complaint_intelligence_service(None)


def test_sqlite_repository_round_trips_read_models_without_raw_pii(tmp_path) -> None:
    db_path = tmp_path / "ci.db"
    repository = SQLiteComplaintIntelligenceRepository(db_path)
    event = _event("sqlite-1", "010-1234-5678로 연락 주세요. 서울로 123 101동 202호 앞 도로 침하")
    alert = _alert("issue-sqlite-1", event)
    insight = _insight("insight-sqlite-1", event)
    pack = _evidence_pack("candidate-sqlite-1", event)
    group = _duplicate_group("merge-sqlite-1", event.id)

    repository.save_analysis_run(
        run_id="run-sqlite-1",
        mode="replay",
        source_name="civil_policy_qna_demo",
        event_count=1,
        started_at=BASE_TIME,
        as_of=BASE_TIME,
        metadata={"purpose": "unit"},
    )
    repository.complete_analysis_run("run-sqlite-1", status="completed", completed_at=BASE_TIME)
    repository.save_events([event])
    repository.save_issue_alerts([alert])
    repository.save_public_insights([insight])
    repository.save_evidence_pack(insight.insight_id, pack)
    repository.save_duplicate_groups([group])

    restored_event = repository.get_events([event.id])[0]
    restored_alert = repository.list_issue_alerts()[0]
    restored_insight = repository.get_public_insight(insight.insight_id)
    restored_pack = repository.get_evidence_pack(insight.insight_id)
    restored_group = repository.get_duplicate_group(group.merge_id)
    restored_runs = repository.list_analysis_runs(limit=5)
    state = repository.get_dashboard_state()

    assert restored_event.id == event.id
    assert restored_alert.id == alert.id
    assert restored_insight is not None
    assert restored_insight.insight_id == insight.insight_id
    assert restored_pack is not None
    assert restored_pack.candidate_id == pack.candidate_id
    assert restored_group is not None
    assert restored_group.merge_id == group.merge_id
    assert len(restored_runs) == 1
    assert restored_runs[0].run_id == "run-sqlite-1"
    assert restored_runs[0].metadata["purpose"] == "unit"
    assert state.as_of == BASE_TIME
    assert state.latest_event_at == event.received_at
    assert state.event_count == 1
    assert state.active_alert_count == 1
    assert state.high_priority_insight_count == 1

    payload_text = _sqlite_payload_text(db_path)
    assert "010-1234-5678" not in payload_text
    assert "101동 202호" not in payload_text
    assert "[REDACTED:PHONE]" in payload_text


def test_service_uses_sqlite_repository_across_new_instances(tmp_path) -> None:
    db_path = tmp_path / "ci_service.db"
    config = _sqlite_config(db_path)
    events = [_sinkhole_event(index) for index in range(5)]

    first_service = ComplaintIntelligenceService(
        repository=SQLiteComplaintIntelligenceRepository(db_path),
        config=config,
    )
    first_result = first_service.run_analysis(
        events,
        mode="replay",
        source_name="civil_policy_qna_demo",
        as_of=BASE_TIME,
    )

    second_service = ComplaintIntelligenceService(
        repository=SQLiteComplaintIntelligenceRepository(db_path),
        config=config,
    )
    alerts = second_service.list_issue_alerts()
    insights = second_service.list_public_insights()
    state = second_service.get_dashboard_state()

    assert first_result.run_id
    assert first_result.mode == "replay"
    assert alerts
    assert insights
    assert second_service.get_public_insight(insights[0].insight_id) is not None
    assert second_service.get_public_insight_evidence_pack(insights[0].insight_id) is not None
    assert state.as_of == BASE_TIME
    assert state.latest_event_at == BASE_TIME
    assert state.event_count == 5


def test_dashboard_api_reads_persisted_state_after_service_recreation(tmp_path) -> None:
    db_path = tmp_path / "ci_api.db"
    config = _sqlite_config(db_path)
    first_service = ComplaintIntelligenceService(
        repository=SQLiteComplaintIntelligenceRepository(db_path),
        config=config,
    )
    set_complaint_intelligence_service(first_service)
    client = TestClient(app)

    response = client.post(
        "/complaint-intelligence/dashboard/run-analysis",
        json={
            "mode": "replay",
            "source_name": "civil_policy_qna_demo",
            "as_of": BASE_TIME.isoformat(),
            "events": [_sinkhole_event(index).model_dump(mode="json") for index in range(5)],
        },
    )

    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    assert summary["as_of"] == BASE_TIME.isoformat()
    assert summary["latest_event_at"] == BASE_TIME.isoformat()
    assert summary["event_count"] == 5

    second_service = ComplaintIntelligenceService(
        repository=SQLiteComplaintIntelligenceRepository(db_path),
        config=config,
    )
    set_complaint_intelligence_service(second_service)
    dashboard = client.get("/complaint-intelligence/dashboard")

    assert dashboard.status_code == 200
    data = dashboard.json()["data"]
    assert data["summary"]["event_count"] == 5
    assert data["summary"]["active_alert_count"] >= 1
    assert data["issue_alerts"]
    assert data["public_insights"]


def test_in_memory_repository_remains_available_for_fallback() -> None:
    repository = InMemoryComplaintIntelligenceRepository()
    event = _event("memory-1", "대형폐기물 배출 방법 안내가 부족합니다.")

    repository.save_events([event])

    assert repository.get_events([event.id])[0].id == event.id
    assert repository.get_dashboard_state().event_count == 1
    repository.clear()
    assert repository.get_dashboard_state().event_count == 0


def _sqlite_config(db_path) -> object:
    config = get_complaint_intelligence_config()
    return replace(
        config,
        repository="sqlite",
        db_path=str(db_path),
        public_insight_llm_provider="fake",
        public_insight_llm_enabled=True,
        public_insight_min_candidate_complaint_count=4,
        min_affected_count=4,
    )


def _event(event_id: str, text: str) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=BASE_TIME,
        body=text,
        region="중구",
        final_department="도로관리과",
        status="open",
    )


def _sinkhole_event(index: int) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=f"sinkhole-{index}",
        received_at=BASE_TIME - timedelta(minutes=index * 5),
        body=f"중구 도로 싱크홀 침하 구멍 위험 신고 {index}",
        region="중구",
        final_department="도로관리과",
    )


def _alert(alert_id: str, event: ComplaintIntelligenceEvent) -> IssueAlert:
    return IssueAlert(
        id=alert_id,
        severity="WARNING",
        title="중구 도로침하 민원 급증",
        summary="현재 관측 기준 도로침하 민원이 증가했습니다.",
        topic="도로침하",
        keywords=["도로", "침하"],
        region="중구",
        recent_count=1,
        baseline=0.0,
        surge_ratio=3.0,
        first_seen=event.received_at,
        last_seen=event.received_at,
        representative_complaints=[
            RepresentativeComplaint(id=event.id, masked_text=event.masked_text, region=event.region, received_at=event.received_at)
        ],
        related_ids=[event.id],
        confidence=0.9,
        explanation="테스트 경보입니다.",
    )


def _insight(insight_id: str, event: ComplaintIntelligenceEvent) -> PublicAgencyInsight:
    return PublicAgencyInsight(
        insight_id=insight_id,
        type="SAFETY_RISK_SIGNAL",
        priority="HIGH",
        title="중구 도로침하 안전 점검 필요",
        summary="현재 관측 기준 도로침하 민원이 접수되었습니다.",
        problem_diagnosis="도로 침하로 시민 안전 위험 가능성이 있습니다.",
        topic="도로침하",
        target_area="현장 대응",
        affected_region={"dominant_region": "중구"},
        related_department="도로관리과",
        affected_count=1,
        window_start=event.received_at,
        window_end=event.received_at,
        metrics={"complaint_count": 1},
        evidence=[
            PublicInsightEvidence(
                complaint_id=event.id,
                masked_text=event.masked_text,
                region=event.region,
                received_at=event.received_at,
                department=event.final_department,
                status=event.status,
            )
        ],
        representative_complaint_ids=[event.id],
        linked_alert_ids=["issue-sqlite-1"],
        recommended_actions=[
            RecommendedAction(
                action="도로 침하 의심 지점 현장 점검을 실시합니다.",
                horizon="IMMEDIATE",
                action_type="FIELD_INSPECTION",
                responsible_unit_hint="도로관리과",
                why="안전 위험 민원이 접수되었습니다.",
                supporting_evidence_ids=[event.id],
                expected_impact="사고 위험을 줄일 수 있습니다.",
            )
        ],
        expected_impact="현장 점검으로 안전 위험을 낮출 수 있습니다.",
        uncertainty=["현장 상태는 담당자 확인이 필요합니다."],
        requires_human_review=True,
        confidence=0.9,
        grounding_score=0.95,
        created_at=BASE_TIME,
        explanation="마스킹된 근거 민원을 기반으로 생성했습니다.",
    )


def _evidence_pack(candidate_id: str, event: ComplaintIntelligenceEvent) -> PublicInsightEvidencePack:
    return PublicInsightEvidencePack(
        candidate_id=candidate_id,
        type_hint="SAFETY_RISK_SIGNAL",
        topic_label="도로침하",
        region_summary={"dominant_region": "중구", "counts": {"중구": 1}},
        window_start=event.received_at,
        window_end=event.received_at,
        complaint_count=1,
        representative_complaints=[
            {
                "complaint_id": event.id,
                "created_at": event.received_at.isoformat(),
                "masked_text": event.masked_text,
                "region": event.region,
                "department": event.final_department,
                "status": event.status,
            }
        ],
        linked_alert_ids=["issue-sqlite-1"],
        allowed_action_catalog=["긴급 현장 점검"],
    )


def _duplicate_group(merge_id: str, event_id: str) -> DuplicateMergeRecord:
    return DuplicateMergeRecord(
        merge_id=merge_id,
        representative_complaint_id=event_id,
        member_complaint_ids=[event_id],
        confidence=0.8,
        recommendation_level="review",
        allowed_actions=["confirm", "split", "reject"],
        blocked_actions=["draft_reply"],
        representative=DuplicateRepresentative(
            complaint_id=event_id,
            selection_reason="가장 최근 접수된 민원입니다.",
            quality_score=0.8,
        ),
        score_breakdown={"semantic": 0.8},
        location_state="exact",
        request_types={event_id: "safety_action"},
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _sqlite_payload_text(db_path) -> str:
    connection = sqlite3.connect(str(db_path))
    try:
        chunks: list[str] = []
        for table in ("ci_events", "ci_issue_alerts", "ci_public_insights", "ci_evidence_packs", "ci_duplicate_groups"):
            rows = connection.execute(f"SELECT payload_json FROM {table}").fetchall()
            chunks.extend(row[0] for row in rows)
        return "\n".join(chunks)
    finally:
        connection.close()

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import (
    set_complaint_intelligence_scheduler,
    set_complaint_intelligence_service,
)
from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.public_insights import PublicAgencyInsightEngine
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.repository import InMemoryComplaintIntelligenceRepository
from app.complaint_intelligence.scheduler import ComplaintIntelligenceScheduler
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.service import ComplaintIntelligenceService


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """공유 서비스/스케줄러가 다른 테스트에 영향을 주지 않도록 격리한다."""

    yield
    set_complaint_intelligence_scheduler(None)
    set_complaint_intelligence_service(None)


def test_scheduler_run_once_analyzes_persisted_events_and_records_metadata() -> None:
    config = _config(scheduler_enabled=True)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    repository.save_events(_sinkhole_events(5))

    scheduler = ComplaintIntelligenceScheduler(service, config=config)
    result = scheduler.run_once()

    assert result.ran is True
    assert result.run_id
    assert result.event_count == 5
    assert repository.list_issue_alerts()
    assert repository.list_public_insights()

    run = repository.list_analysis_runs(limit=1)[0]
    assert run.metadata["trigger"] == "scheduler"
    assert run.metadata["llm_metrics"]["llm_provider"] == "fake"
    assert run.metadata["llm_metrics"]["candidate_count"] >= 1
    assert run.metadata["llm_metrics"]["fallback_count"] == 0


def test_scheduler_noops_until_min_events() -> None:
    config = _config(scheduler_enabled=True, scheduler_min_events=6)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    repository.save_events(_sinkhole_events(5))

    result = ComplaintIntelligenceScheduler(service, config=config).run_once()

    assert result.ran is False
    assert result.reason == "not_enough_events"
    assert repository.list_analysis_runs() == []


def test_run_analysis_metadata_records_llm_failure_and_fallback() -> None:
    config = _config()
    public_service = PublicInsightService(config=config, llm_provider=_TimeoutProvider())
    service = ComplaintIntelligenceService(
        repository=InMemoryComplaintIntelligenceRepository(),
        public_insight_engine=PublicAgencyInsightEngine(service=public_service),
        config=config,
    )

    service.run_analysis(_sinkhole_events(5), mode="manual", source_name="unit")

    run = service.list_analysis_runs(limit=1)[0]
    metrics = run.metadata["llm_metrics"]
    assert metrics["llm_attempt_count"] >= 1
    assert metrics["llm_failure_count"] >= 1
    assert metrics["fallback_count"] >= 1
    assert metrics["error_types"]["TimeoutError"] >= 1
    assert all("010-" not in str(trace) for trace in metrics["candidate_traces"])


def test_scheduler_api_run_once_and_analysis_runs_are_pii_safe() -> None:
    config = _config(scheduler_enabled=True)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    repository.save_events(_sinkhole_events(5, include_pii=True))
    scheduler = ComplaintIntelligenceScheduler(service, config=config)
    set_complaint_intelligence_service(service)
    set_complaint_intelligence_scheduler(scheduler)
    client = TestClient(app)

    run_response = client.post("/complaint-intelligence/scheduler/run-once")
    assert run_response.status_code == 200
    assert run_response.json()["data"]["ran"] is True

    status_response = client.get("/complaint-intelligence/scheduler/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["scheduler"]["last_result"]["ran"] is True

    runs_response = client.get("/complaint-intelligence/analysis-runs")
    assert runs_response.status_code == 200
    payload = runs_response.text
    assert "trigger" in payload
    assert "llm_metrics" in payload
    assert "010-1234-5678" not in payload
    assert "101동 202호" not in payload


class _TimeoutProvider:
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise TimeoutError("unit timeout")


def _config(**overrides):
    base = get_complaint_intelligence_config()
    defaults = {
        "repository": "memory",
        "min_recent_count": 3,
        "min_surge_ratio": 2.5,
        "public_insight_llm_enabled": True,
        "public_insight_llm_provider": "fake",
        "public_insight_min_candidate_complaint_count": 4,
        "min_affected_count": 4,
        "scheduler_enabled": False,
        "scheduler_batch_size": 20,
        "scheduler_min_events": 4,
        "scheduler_interval_seconds": 60.0,
        "scheduler_source_name": "unit_scheduler",
        "scheduler_mode": "realtime",
    }
    defaults.update(overrides)
    return replace(base, **defaults)


def _sinkhole_events(count: int, *, include_pii: bool = False) -> list[ComplaintIntelligenceEvent]:
    events: list[ComplaintIntelligenceEvent] = []
    for index in range(count):
        pii = " 010-1234-5678 101동 202호" if include_pii and index == 0 else ""
        events.append(
            ComplaintIntelligenceEvent(
                id=f"scheduler-sinkhole-{index}",
                received_at=BASE_TIME - timedelta(minutes=index * 5),
                body=f"중구 도로 싱크홀 침하 구멍이 생겨 위험합니다 {index}{pii}",
                region="중구",
                final_department="도로관리과",
                status="open",
            )
        )
    return events

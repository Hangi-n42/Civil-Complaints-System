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
from app.complaint_intelligence.collector import (
    CollectorBatch,
    NoopComplaintEventCollector,
    RepositoryReplayCollector,
)
from app.complaint_intelligence.config import get_complaint_intelligence_config
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


def test_noop_collector_returns_empty_batch() -> None:
    batch = NoopComplaintEventCollector(source_name="unit_noop").collect_since(BASE_TIME, limit=10)

    assert batch.source_name == "unit_noop"
    assert batch.mode == "realtime"
    assert batch.events == []
    assert batch.watermark == BASE_TIME


def test_repository_replay_collector_returns_events_after_watermark() -> None:
    repository = InMemoryComplaintIntelligenceRepository()
    events = [_event("old", minutes=30), _event("new-1", minutes=10), _event("new-2", minutes=5)]
    repository.save_events(events)
    collector = RepositoryReplayCollector(repository, source_name="unit_replay")

    batch = collector.collect_since(BASE_TIME - timedelta(minutes=20), limit=10)

    assert batch.source_name == "unit_replay"
    assert batch.mode == "replay"
    assert [event.id for event in batch.events] == ["new-1", "new-2"]
    assert batch.watermark == BASE_TIME - timedelta(minutes=5)


def test_scheduler_uses_collector_batch_and_records_collector_metadata() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(5), source_name="unit_stream"),
    )

    result = scheduler.run_once()

    assert result.ran is True
    run = repository.list_analysis_runs(limit=1)[0]
    assert run.metadata["trigger"] == "scheduler"
    assert run.metadata["collector_source_name"] == "unit_stream"
    assert run.metadata["collector_mode"] == "replay"
    assert run.metadata["collector_event_count"] == 5
    assert run.metadata["collector_watermark"] == BASE_TIME.isoformat()


def test_scheduler_does_not_analyze_when_collector_batch_is_below_min_events() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(2), source_name="unit_stream"),
    )

    result = scheduler.run_once()

    assert result.ran is False
    assert result.reason == "not_enough_events"
    assert repository.list_analysis_runs() == []


def test_collector_poll_once_api_saves_events_without_exposing_raw_pii() -> None:
    config = _config()
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(
            [
                ComplaintIntelligenceEvent(
                    id="collector-pii-1",
                    received_at=BASE_TIME,
                    body="010-1234-5678로 연락 주세요. 101동 202호 앞 도로가 꺼졌습니다.",
                    region="중구",
                )
            ],
            source_name="unit_stream",
        ),
    )
    set_complaint_intelligence_service(service)
    set_complaint_intelligence_scheduler(scheduler)
    client = TestClient(app)

    response = client.post("/complaint-intelligence/collector/poll-once")

    assert response.status_code == 200
    payload = response.text
    assert response.json()["data"]["event_count"] == 1
    assert "010-1234-5678" not in payload
    assert "101동 202호" not in payload
    stored = repository.get_events(["collector-pii-1"])[0]
    assert "010-1234-5678" not in stored.masked_text
    assert "101동 202호" not in stored.masked_text


class _StaticCollector:
    def __init__(self, events: list[ComplaintIntelligenceEvent], *, source_name: str = "static") -> None:
        self.events = events
        self.source_name = source_name

    def collect_since(self, watermark: datetime | None, limit: int) -> CollectorBatch:
        selected = [event for event in self.events if watermark is None or event.received_at > watermark]
        if limit > 0:
            selected = selected[:limit]
        return CollectorBatch(
            source_name=self.source_name,
            mode="replay",
            events=selected,
            watermark=max((event.received_at for event in selected), default=watermark),
            metadata={"collector": "static"},
        )


def _config(**overrides):
    defaults = {
        "repository": "memory",
        "min_recent_count": 3,
        "min_surge_ratio": 2.5,
        "public_insight_llm_enabled": True,
        "public_insight_llm_provider": "fake",
        "public_insight_min_candidate_complaint_count": 4,
        "min_affected_count": 4,
        "scheduler_enabled": False,
        "scheduler_min_events": 4,
        "scheduler_batch_size": 20,
        "collector": "repository_replay",
        "collector_limit": 20,
        "collector_source_name": "unit_replay",
    }
    defaults.update(overrides)
    return replace(get_complaint_intelligence_config(), **defaults)


def _event(event_id: str, *, minutes: int) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=BASE_TIME - timedelta(minutes=minutes),
        body=f"도로 침하 민원 {event_id}",
        region="중구",
    )


def _sinkhole_events(count: int) -> list[ComplaintIntelligenceEvent]:
    return [
        ComplaintIntelligenceEvent(
            id=f"collector-sinkhole-{index}",
            received_at=BASE_TIME - timedelta(minutes=index),
            body=f"중구 도로 싱크홀 침하 구멍이 생겨 위험합니다 {index}",
            region="중구",
            final_department="도로관리과",
            status="open",
        )
        for index in range(count)
    ]

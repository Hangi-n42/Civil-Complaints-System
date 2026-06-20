from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import (
    set_complaint_intelligence_scheduler,
    set_complaint_intelligence_service,
)
from app.complaint_intelligence.collector import CollectorBatch
from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.repository import (
    CollectorCheckpointRecord,
    InMemoryComplaintIntelligenceRepository,
)
from app.complaint_intelligence.scheduler import ComplaintIntelligenceScheduler
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.complaint_intelligence.sqlite_repository import SQLiteComplaintIntelligenceRepository


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """공유 서비스와 스케줄러가 다른 테스트에 영향을 주지 않도록 격리한다."""

    yield
    set_complaint_intelligence_scheduler(None)
    set_complaint_intelligence_service(None)


def test_in_memory_repository_saves_and_restores_collector_checkpoint() -> None:
    repository = InMemoryComplaintIntelligenceRepository()
    repository.save_collector_checkpoint(_checkpoint(metadata={"debug": "010-1234-5678"}))

    restored = repository.get_collector_checkpoint("repository_replay", "unit_replay")
    checkpoints = repository.list_collector_checkpoints()

    assert restored is not None
    assert restored.watermark == BASE_TIME
    assert restored.last_event_count == 5
    assert restored.metadata["debug"] == "[REDACTED:PHONE]"
    assert checkpoints == [restored]


def test_sqlite_repository_saves_and_restores_checkpoint_across_instances(tmp_path) -> None:
    db_path = tmp_path / "ci_checkpoint.db"
    first = SQLiteComplaintIntelligenceRepository(db_path)
    first.save_collector_checkpoint(_checkpoint(metadata={"debug": "010-1234-5678"}))

    second = SQLiteComplaintIntelligenceRepository(db_path)
    restored = second.get_collector_checkpoint("repository_replay", "unit_replay")

    assert restored is not None
    assert restored.watermark == BASE_TIME
    assert restored.updated_at == BASE_TIME + timedelta(minutes=1)
    assert restored.metadata["debug"] == "[REDACTED:PHONE]"


def test_scheduler_restores_last_watermark_from_repository_checkpoint() -> None:
    config = _config()
    repository = InMemoryComplaintIntelligenceRepository()
    repository.save_collector_checkpoint(_checkpoint())
    service = ComplaintIntelligenceService(repository=repository, config=config)

    scheduler = ComplaintIntelligenceScheduler(service, config=config)

    status = scheduler.status()
    assert status["last_watermark"] == BASE_TIME.isoformat()
    assert status["checkpoint"]["watermark"] == BASE_TIME.isoformat()


def test_scheduler_run_once_success_saves_checkpoint() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(5), metadata={"debug": "010-1234-5678"}),
    )

    result = scheduler.run_once()

    checkpoint = repository.get_collector_checkpoint("repository_replay", "unit_replay")
    assert result.ran is True
    assert checkpoint is not None
    assert checkpoint.watermark == BASE_TIME
    assert checkpoint.last_event_count == 5
    assert checkpoint.metadata["trigger"] == "scheduler"
    assert checkpoint.metadata["collector_name"] == "repository_replay"
    assert checkpoint.metadata["collector_batch"]["debug"] == "[REDACTED:PHONE]"


def test_scheduler_poll_once_saves_separate_poll_checkpoint() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(2)),
    )

    result = scheduler.poll_once()

    checkpoint = repository.get_collector_checkpoint("repository_replay:poll", "unit_replay")
    assert result.event_count == 2
    assert checkpoint is not None
    assert checkpoint.watermark == BASE_TIME
    assert checkpoint.metadata["trigger"] == "collector_poll"
    assert repository.get_collector_checkpoint("repository_replay", "unit_replay") is None


def test_scheduler_not_enough_events_with_partial_batch_advances_checkpoint() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(2)),
    )

    first = scheduler.run_once()
    second = scheduler.run_once()

    checkpoint = repository.get_collector_checkpoint("repository_replay", "unit_replay")
    assert first.ran is False
    assert first.event_count == 2
    assert second.ran is False
    assert second.event_count == 0
    assert checkpoint is not None
    assert checkpoint.watermark == BASE_TIME
    assert checkpoint.last_event_count == 2
    assert repository.list_analysis_runs() == []


def test_scheduler_analysis_failure_does_not_advance_checkpoint() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    service.run_analysis = _raise_analysis_failure  # type: ignore[method-assign]
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(_sinkhole_events(5)),
    )

    result = scheduler.run_once()

    assert result.ran is False
    assert result.reason == "analysis_failed"
    assert repository.get_collector_checkpoint("repository_replay", "unit_replay") is None


def test_collector_status_api_returns_checkpoint_without_raw_pii() -> None:
    config = _config(scheduler_min_events=4)
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(repository=repository, config=config)
    scheduler = ComplaintIntelligenceScheduler(
        service,
        config=config,
        collector=_StaticCollector(
            _sinkhole_events(5, include_pii=True),
            metadata={"debug": "010-1234-5678"},
        ),
    )
    scheduler.run_once()
    set_complaint_intelligence_service(service)
    set_complaint_intelligence_scheduler(scheduler)
    client = TestClient(app)

    response = client.get("/complaint-intelligence/collector/status")

    assert response.status_code == 200
    collector = response.json()["data"]["collector"]
    assert collector["checkpoint"]["watermark"] == BASE_TIME.isoformat()
    assert collector["checkpoint"]["metadata"]["collector_batch"]["debug"] == "[REDACTED:PHONE]"
    assert "010-1234-5678" not in response.text
    assert "101동 202호" not in response.text


def _checkpoint(metadata: dict[str, Any] | None = None) -> CollectorCheckpointRecord:
    return CollectorCheckpointRecord(
        collector_name="repository_replay",
        source_name="unit_replay",
        mode="replay",
        watermark=BASE_TIME,
        last_event_count=5,
        updated_at=BASE_TIME + timedelta(minutes=1),
        metadata=metadata or {"trigger": "scheduler"},
    )


def _raise_analysis_failure(*args, **kwargs):
    raise RuntimeError("unit failure")


class _StaticCollector:
    def __init__(
        self,
        events: list[ComplaintIntelligenceEvent],
        *,
        source_name: str = "unit_replay",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events = events
        self.source_name = source_name
        self.metadata = metadata or {"collector": "static"}

    def collect_since(self, watermark: datetime | None, limit: int) -> CollectorBatch:
        selected = [event for event in self.events if watermark is None or event.received_at > watermark]
        if limit > 0:
            selected = selected[:limit]
        return CollectorBatch(
            source_name=self.source_name,
            mode="replay",
            events=selected,
            watermark=max((event.received_at for event in selected), default=watermark),
            metadata=dict(self.metadata),
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
        "checkpoint_enabled": True,
    }
    defaults.update(overrides)
    return replace(get_complaint_intelligence_config(), **defaults)


def _sinkhole_events(count: int, *, include_pii: bool = False) -> list[ComplaintIntelligenceEvent]:
    events: list[ComplaintIntelligenceEvent] = []
    for index in range(count):
        pii = " 010-1234-5678 101동 202호" if include_pii and index == 0 else ""
        events.append(
            ComplaintIntelligenceEvent(
                id=f"checkpoint-sinkhole-{index}",
                received_at=BASE_TIME - timedelta(minutes=index),
                body=f"중구 도로 싱크홀 침하 구멍이 생겨 위험합니다 {index}{pii}",
                region="중구",
                final_department="도로관리과",
                status="open",
            )
        )
    return events

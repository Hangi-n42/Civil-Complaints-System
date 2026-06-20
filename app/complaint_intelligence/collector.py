"""Complaint Intelligence 이벤트 수집기 인터페이스와 데모 replay 구현."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from app.complaint_intelligence.repository import ComplaintIntelligenceRepository
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


CollectorMode = Literal["realtime", "replay", "manual"]


@dataclass(frozen=True)
class CollectorBatch:
    """collector가 반환하는 PII-safe 이벤트 배치."""

    source_name: str
    mode: CollectorMode
    events: list[ComplaintIntelligenceEvent]
    watermark: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ComplaintEventCollector(Protocol):
    """향후 외부 민원 접수 시스템으로 교체 가능한 수집기 계약."""

    def collect_since(self, watermark: datetime | None, limit: int) -> CollectorBatch:
        """watermark 이후 이벤트를 limit 범위에서 수집한다."""


class NoopComplaintEventCollector:
    """이벤트를 수집하지 않는 안전 기본 collector."""

    def __init__(self, *, source_name: str = "noop") -> None:
        self.source_name = source_name

    def collect_since(self, watermark: datetime | None, limit: int) -> CollectorBatch:
        return CollectorBatch(
            source_name=self.source_name,
            mode="realtime",
            events=[],
            watermark=watermark,
            metadata={"collector": "noop", "limit": limit},
        )


class RepositoryReplayCollector:
    """저장소 이벤트를 watermark 기준으로 순차 유입처럼 재생하는 demo/replay collector."""

    def __init__(
        self,
        repository: ComplaintIntelligenceRepository,
        *,
        source_name: str = "repository_replay",
        mode: CollectorMode = "replay",
    ) -> None:
        self.repository = repository
        self.source_name = source_name
        self.mode = mode

    def collect_since(self, watermark: datetime | None, limit: int) -> CollectorBatch:
        safe_watermark = _aware(watermark) if watermark else None
        events = [
            ComplaintIntelligenceEvent.model_validate(event.model_dump(mode="json"))
            for event in self.repository.get_events()
        ]
        selected = [
            event
            for event in sorted(events, key=lambda item: _aware(item.received_at))
            if safe_watermark is None or _aware(event.received_at) > safe_watermark
        ]
        if limit > 0:
            selected = selected[:limit]
        next_watermark = max((_aware(event.received_at) for event in selected), default=safe_watermark)
        return CollectorBatch(
            source_name=self.source_name,
            mode=self.mode,
            events=selected,
            watermark=next_watermark,
            metadata={
                "collector": "repository_replay",
                "limit": limit,
                "input_watermark": safe_watermark.isoformat() if safe_watermark else None,
            },
        )


def build_complaint_event_collector(
    collector_name: str,
    repository: ComplaintIntelligenceRepository,
    *,
    source_name: str,
) -> ComplaintEventCollector:
    """config 값에 맞는 collector를 구성한다."""

    normalized = (collector_name or "repository_replay").lower()
    if normalized == "noop":
        return NoopComplaintEventCollector(source_name=source_name or "noop")
    if normalized == "repository_replay":
        return RepositoryReplayCollector(repository, source_name=source_name or "repository_replay")
    return NoopComplaintEventCollector(source_name=source_name or normalized)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

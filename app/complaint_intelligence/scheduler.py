"""Complaint Intelligence 자동 관제 스케줄러."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, RLock, Thread
from typing import Any

from app.complaint_intelligence.collector import (
    ComplaintEventCollector,
    build_complaint_event_collector,
)
from app.complaint_intelligence.config import ComplaintIntelligenceConfig
from app.complaint_intelligence.repository import CollectorCheckpointRecord
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.service import ComplaintIntelligenceService, get_complaint_intelligence_service


@dataclass(frozen=True)
class SchedulerRunResult:
    """스케줄러 1회 분석 실행 결과."""

    ran: bool
    reason: str | None = None
    run_id: str | None = None
    event_count: int = 0
    alert_count: int = 0
    public_insight_count: int = 0
    as_of: datetime | None = None
    collector_source_name: str | None = None
    collector_mode: str | None = None
    collector_watermark: datetime | None = None


@dataclass(frozen=True)
class CollectorPollResult:
    """collector collect+save 1회 실행 결과."""

    source_name: str
    mode: str
    event_count: int
    watermark: datetime | None = None
    metadata: dict[str, Any] | None = None


class ComplaintIntelligenceScheduler:
    """collector에서 받은 민원 배치를 단일 프로세스에서 주기적으로 분석한다."""

    def __init__(
        self,
        service: ComplaintIntelligenceService,
        *,
        config: ComplaintIntelligenceConfig | None = None,
        collector: ComplaintEventCollector | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.service = service
        self.config = config or service.config
        self.collector = collector or build_complaint_event_collector(
            self.config.collector,
            self.service.repository,
            source_name=self.config.collector_source_name,
        )
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._run_lock = RLock()
        self._state_lock = RLock()
        self._run_count = 0
        self._error_count = 0
        self._started_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_watermark: datetime | None = self._restore_watermark()
        self._last_poll_watermark: datetime | None = self._restore_poll_watermark()
        self._last_poll_result: CollectorPollResult | None = None
        self._last_error: str | None = None
        self._last_result: SchedulerRunResult | None = None

    def start(self) -> bool:
        """설정이 활성화된 경우 백그라운드 스케줄러를 시작한다."""

        if not self.config.scheduler_enabled:
            return False
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._started_at = _now()
            self._thread = Thread(target=self._loop, name="complaint-intelligence-scheduler", daemon=True)
            self._thread.start()
        return True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """백그라운드 스케줄러를 안전하게 중지한다."""

        with self._state_lock:
            thread = self._thread
            self._stop_event.set()
        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)

    def run_once(self) -> SchedulerRunResult:
        """collector에서 받은 이벤트 배치를 저장한 뒤 분석을 1회 실행한다."""

        with self._run_lock:
            batch = self.collector.collect_since(self._last_watermark, self._collector_limit())
            safe_events = _safe_events(batch.events)
            if safe_events:
                self.service.repository.save_events(safe_events)
            if len(safe_events) < self.config.scheduler_min_events:
                result = SchedulerRunResult(
                    ran=False,
                    reason="not_enough_events",
                    event_count=len(safe_events),
                    as_of=_resolve_as_of(safe_events),
                    collector_source_name=batch.source_name,
                    collector_mode=batch.mode,
                    collector_watermark=batch.watermark,
                )
                if safe_events:
                    self._save_checkpoint(
                        trigger="scheduler",
                        mode=batch.mode,
                        event_count=len(safe_events),
                        watermark=batch.watermark,
                        batch_metadata=batch.metadata,
                    )
                    self._last_watermark = batch.watermark
                self._record_result(result)
                return result

            try:
                analysis = self.service.run_analysis(
                    safe_events,
                    mode=self.config.scheduler_mode,
                    source_name=self.config.scheduler_source_name,
                    as_of=_resolve_as_of(safe_events),
                    metadata={
                        "trigger": "scheduler",
                        "collector_name": self.config.collector,
                        "collector_source_name": batch.source_name,
                        "collector_mode": batch.mode,
                        "collector_event_count": len(safe_events),
                        "collector_watermark": batch.watermark.isoformat() if batch.watermark else None,
                        "scheduler_interval_seconds": self.config.scheduler_interval_seconds,
                        "scheduler_batch_size": self.config.scheduler_batch_size,
                        "scheduler_min_events": self.config.scheduler_min_events,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 백그라운드 루프 보호용 경계
                with self._state_lock:
                    self._error_count += 1
                    self._last_error = type(exc).__name__
                    self._last_run_at = _now()
                self.logger.warning("Complaint Intelligence scheduler run failed: %s", type(exc).__name__)
                result = SchedulerRunResult(
                    ran=False,
                    reason="analysis_failed",
                    event_count=len(safe_events),
                    as_of=_resolve_as_of(safe_events),
                    collector_source_name=batch.source_name,
                    collector_mode=batch.mode,
                    collector_watermark=batch.watermark,
                )
                self._record_result(result)
                return result

            result = SchedulerRunResult(
                ran=True,
                run_id=analysis.run_id,
                event_count=analysis.event_count,
                alert_count=len(analysis.alerts),
                public_insight_count=len(analysis.public_insights),
                as_of=analysis.as_of,
                collector_source_name=batch.source_name,
                collector_mode=batch.mode,
                collector_watermark=batch.watermark,
            )
            self._save_checkpoint(
                trigger="scheduler",
                mode=batch.mode,
                event_count=len(safe_events),
                watermark=batch.watermark,
                batch_metadata=batch.metadata,
            )
            self._last_watermark = batch.watermark
            self._record_result(result)
            return result

    def poll_once(self) -> CollectorPollResult:
        """collector에서 이벤트를 수집해 저장만 하고 분석은 실행하지 않는다."""

        with self._run_lock:
            batch = self.collector.collect_since(self._last_poll_watermark, self._collector_limit())
            safe_events = _safe_events(batch.events)
            if safe_events:
                self.service.repository.save_events(safe_events)
            result = CollectorPollResult(
                source_name=batch.source_name,
                mode=batch.mode,
                event_count=len(safe_events),
                watermark=batch.watermark,
                metadata=dict(batch.metadata),
            )
            if safe_events:
                self._save_checkpoint(
                    trigger="collector_poll",
                    mode=batch.mode,
                    event_count=len(safe_events),
                    watermark=batch.watermark,
                    batch_metadata=batch.metadata,
                    poll=True,
                )
                self._last_poll_watermark = batch.watermark
            with self._state_lock:
                self._last_poll_result = result
            return result

    def status(self) -> dict[str, Any]:
        """운영자가 스케줄러와 collector 상태를 확인할 수 있는 비식별 상태를 반환한다."""

        with self._state_lock:
            running = bool(self._thread and self._thread.is_alive())
            return {
                "enabled": self.config.scheduler_enabled,
                "running": running,
                "interval_seconds": self.config.scheduler_interval_seconds,
                "batch_size": self.config.scheduler_batch_size,
                "min_events": self.config.scheduler_min_events,
                "mode": self.config.scheduler_mode,
                "source_name": self.config.scheduler_source_name,
                "collector": self.config.collector,
                "collector_source_name": self.config.collector_source_name,
                "collector_limit": self._collector_limit(),
                "last_watermark": self._last_watermark.isoformat() if self._last_watermark else None,
                "last_poll_watermark": self._last_poll_watermark.isoformat() if self._last_poll_watermark else None,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
                "run_count": self._run_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "last_result": _result_payload(self._last_result),
                "last_poll_result": _poll_result_payload(self._last_poll_result),
                "checkpoint": _checkpoint_payload(self._get_checkpoint(poll=False)),
                "poll_checkpoint": _checkpoint_payload(self._get_checkpoint(poll=True)),
            }

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(max(1.0, float(self.config.scheduler_interval_seconds)))

    def _record_result(self, result: SchedulerRunResult) -> None:
        with self._state_lock:
            self._last_result = result
            self._last_run_at = _now()
            if result.ran:
                self._run_count += 1
                self._last_error = None

    def _collector_limit(self) -> int:
        return self.config.collector_limit or self.config.scheduler_batch_size

    def _restore_watermark(self) -> datetime | None:
        checkpoint = self._get_checkpoint(poll=False)
        return checkpoint.watermark if checkpoint and self.config.checkpoint_enabled else None

    def _restore_poll_watermark(self) -> datetime | None:
        checkpoint = self._get_checkpoint(poll=True)
        return checkpoint.watermark if checkpoint and self.config.checkpoint_enabled else None

    def _get_checkpoint(self, *, poll: bool) -> CollectorCheckpointRecord | None:
        if not self.config.checkpoint_enabled:
            return None
        collector_name, source_name = self._checkpoint_key(poll=poll)
        return self.service.repository.get_collector_checkpoint(collector_name, source_name)

    def _save_checkpoint(
        self,
        *,
        trigger: str,
        mode: str,
        event_count: int,
        watermark: datetime | None,
        batch_metadata: dict[str, Any] | None,
        poll: bool = False,
    ) -> None:
        if not self.config.checkpoint_enabled:
            return
        collector_name, source_name = self._checkpoint_key(poll=poll)
        metadata = {
            "trigger": trigger,
            "collector_name": self.config.collector,
            "collector_source_name": self.config.collector_source_name,
            "collector_mode": mode,
            "collector_event_count": event_count,
            "scheduler_min_events": self.config.scheduler_min_events,
            "scheduler_batch_size": self.config.scheduler_batch_size,
            "saved_by": "ComplaintIntelligenceScheduler",
        }
        if batch_metadata:
            metadata["collector_batch"] = dict(batch_metadata)
        self.service.repository.save_collector_checkpoint(
            CollectorCheckpointRecord(
                collector_name=collector_name,
                source_name=source_name,
                mode=mode,
                watermark=watermark,
                last_event_count=event_count,
                updated_at=_now(),
                metadata=metadata,
            )
        )

    def _checkpoint_key(self, *, poll: bool) -> tuple[str, str]:
        collector_name = self.config.collector or "repository_replay"
        source_name = self.config.collector_source_name or collector_name
        if poll:
            return f"{collector_name}:poll", source_name
        return collector_name, source_name


def get_complaint_intelligence_scheduler(
    service: ComplaintIntelligenceService | None = None,
) -> ComplaintIntelligenceScheduler:
    """공유 Complaint Intelligence 스케줄러 인스턴스를 반환한다."""

    global _scheduler
    resolved_service = service or get_complaint_intelligence_service()
    if _scheduler is None or _scheduler.service is not resolved_service:
        if _scheduler is not None:
            _scheduler.stop()
        _scheduler = ComplaintIntelligenceScheduler(resolved_service)
    return _scheduler


def set_complaint_intelligence_scheduler(scheduler: ComplaintIntelligenceScheduler | None) -> None:
    """테스트에서 공유 스케줄러 인스턴스를 교체한다."""

    global _scheduler
    if _scheduler is not None and _scheduler is not scheduler:
        _scheduler.stop()
    _scheduler = scheduler


def _safe_events(events: list[ComplaintIntelligenceEvent]) -> list[ComplaintIntelligenceEvent]:
    return [ComplaintIntelligenceEvent.model_validate(event.model_dump(mode="json")) for event in events]


def _resolve_as_of(events: list[ComplaintIntelligenceEvent]) -> datetime:
    if not events:
        return _now()
    return max(_aware(event.received_at) for event in events)


def _result_payload(result: SchedulerRunResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "ran": result.ran,
        "reason": result.reason,
        "run_id": result.run_id,
        "event_count": result.event_count,
        "alert_count": result.alert_count,
        "public_insight_count": result.public_insight_count,
        "as_of": result.as_of.isoformat() if result.as_of else None,
        "collector_source_name": result.collector_source_name,
        "collector_mode": result.collector_mode,
        "collector_watermark": result.collector_watermark.isoformat() if result.collector_watermark else None,
    }


def _poll_result_payload(result: CollectorPollResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "source_name": result.source_name,
        "mode": result.mode,
        "event_count": result.event_count,
        "watermark": result.watermark.isoformat() if result.watermark else None,
        "metadata": dict(result.metadata or {}),
    }


def _checkpoint_payload(checkpoint: CollectorCheckpointRecord | None) -> dict[str, Any] | None:
    if checkpoint is None:
        return None
    return {
        "collector_name": checkpoint.collector_name,
        "source_name": checkpoint.source_name,
        "mode": checkpoint.mode,
        "watermark": checkpoint.watermark.isoformat() if checkpoint.watermark else None,
        "last_event_count": checkpoint.last_event_count,
        "updated_at": checkpoint.updated_at.isoformat(),
        "metadata": dict(checkpoint.metadata),
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


_scheduler: ComplaintIntelligenceScheduler | None = None

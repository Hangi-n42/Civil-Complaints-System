"""Complaint Intelligence 영속 저장소 계약과 in-memory 구현."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.complaint_intelligence.duplicate_merger.schemas import DuplicateMergeRecord, DuplicateMergeStatus
from app.complaint_intelligence.pii import mask_strings as _mask_strings
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight


AnalysisRunMode = Literal["realtime", "replay", "manual"]
AnalysisRunStatus = Literal["running", "completed", "failed"]


class AnalysisRunRecord(BaseModel):
    """분석 실행 이력 read-model."""

    run_id: str
    mode: AnalysisRunMode
    status: AnalysisRunStatus
    source_name: str | None = None
    event_count: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    as_of: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DashboardState(BaseModel):
    """실시간 관제형 대시보드 상단 상태."""

    as_of: datetime | None = None
    latest_event_at: datetime | None = None
    event_count: int = 0
    active_alert_count: int = 0
    high_priority_insight_count: int = 0
    last_run_id: str | None = None
    last_run_mode: str | None = None
    source_name: str | None = None


class CollectorCheckpointRecord(BaseModel):
    """collector watermark 복원을 위한 비식별 checkpoint."""

    collector_name: str
    source_name: str
    mode: str
    watermark: datetime | None = None
    last_event_count: int = 0
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplaintIntelligenceRepository(ABC):
    """운영 DB 교체가 가능하도록 둔 저장소 인터페이스."""

    @abstractmethod
    def save_analysis_run(
        self,
        *,
        run_id: str,
        mode: AnalysisRunMode,
        source_name: str | None,
        event_count: int,
        started_at: datetime,
        as_of: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """분석 실행 시작 이력을 저장한다."""

    @abstractmethod
    def complete_analysis_run(
        self,
        run_id: str,
        *,
        status: AnalysisRunStatus,
        completed_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """분석 실행 종료 상태를 저장한다."""

    @abstractmethod
    def list_analysis_runs(self, *, limit: int = 20) -> list[AnalysisRunRecord]:
        """최근 분석 실행 이력을 반환한다."""

    @abstractmethod
    def save_events(self, events: list[ComplaintIntelligenceEvent]) -> None:
        """PII 마스킹된 민원 이벤트를 저장한다."""

    @abstractmethod
    def get_events(self, event_ids: list[str] | None = None) -> list[ComplaintIntelligenceEvent]:
        """저장된 민원 이벤트를 반환한다."""

    @abstractmethod
    def save_issue_alerts(self, alerts: list[IssueAlert]) -> None:
        """IssueAlert 최신 상태를 저장한다."""

    @abstractmethod
    def list_issue_alerts(self, status: str | None = None) -> list[IssueAlert]:
        """IssueAlert 목록을 반환한다."""

    @abstractmethod
    def save_public_insights(self, insights: list[PublicAgencyInsight]) -> None:
        """PublicAgencyInsight 최신 상태를 저장한다."""

    @abstractmethod
    def list_public_insights(
        self,
        *,
        status: str | None = None,
        insight_type: str | None = None,
    ) -> list[PublicAgencyInsight]:
        """PublicAgencyInsight 목록을 반환한다."""

    @abstractmethod
    def get_public_insight(self, insight_id: str) -> PublicAgencyInsight | None:
        """PublicAgencyInsight 단건을 반환한다."""

    @abstractmethod
    def save_evidence_pack(self, insight_id: str, pack: PublicInsightEvidencePack) -> None:
        """마스킹된 EvidencePack을 저장한다."""

    @abstractmethod
    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """마스킹된 EvidencePack을 반환한다."""

    @abstractmethod
    def save_duplicate_groups(self, groups: list[DuplicateMergeRecord]) -> None:
        """DuplicateMergeRecord 최신 상태를 저장한다."""

    @abstractmethod
    def list_duplicate_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        """DuplicateMergeRecord 목록을 반환한다."""

    @abstractmethod
    def get_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        """DuplicateMergeRecord 단건을 반환한다."""

    @abstractmethod
    def update_duplicate_group(self, group: DuplicateMergeRecord) -> None:
        """DuplicateMergeRecord 상태 전이를 저장한다."""

    @abstractmethod
    def get_dashboard_state(self) -> DashboardState:
        """대시보드 요약 상태를 반환한다."""

    @abstractmethod
    def save_collector_checkpoint(self, checkpoint: CollectorCheckpointRecord) -> None:
        """collector_name + source_name 단위 최신 checkpoint를 저장한다."""

    @abstractmethod
    def get_collector_checkpoint(
        self,
        collector_name: str,
        source_name: str,
    ) -> CollectorCheckpointRecord | None:
        """collector_name + source_name에 해당하는 checkpoint를 반환한다."""

    @abstractmethod
    def list_collector_checkpoints(self) -> list[CollectorCheckpointRecord]:
        """저장된 collector checkpoint 목록을 반환한다."""

    @abstractmethod
    def clear(self) -> None:
        """테스트/fallback 초기화를 위해 저장소를 비운다."""


class InMemoryComplaintIntelligenceRepository(ComplaintIntelligenceRepository):
    """SQLite 사용이 어려운 환경과 테스트를 위한 in-memory 저장소."""

    def __init__(self) -> None:
        self._runs: dict[str, AnalysisRunRecord] = {}
        self._events: dict[str, ComplaintIntelligenceEvent] = {}
        self._alerts: dict[str, IssueAlert] = {}
        self._insights: dict[str, PublicAgencyInsight] = {}
        self._evidence_packs: dict[str, PublicInsightEvidencePack] = {}
        self._duplicate_groups: dict[str, DuplicateMergeRecord] = {}
        self._collector_checkpoints: dict[tuple[str, str], CollectorCheckpointRecord] = {}
        self._lock = RLock()

    def save_analysis_run(
        self,
        *,
        run_id: str,
        mode: AnalysisRunMode,
        source_name: str | None,
        event_count: int,
        started_at: datetime,
        as_of: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._runs[run_id] = AnalysisRunRecord(
                run_id=run_id,
                mode=mode,
                status="running",
                source_name=source_name,
                event_count=event_count,
                started_at=_aware(started_at),
                as_of=_aware(as_of),
                metadata=metadata or {},
            )

    def complete_analysis_run(
        self,
        run_id: str,
        *,
        status: AnalysisRunStatus,
        completed_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            current = self._runs.get(run_id)
            if current is None:
                return
            merged_metadata = dict(current.metadata)
            if metadata:
                merged_metadata.update(metadata)
            self._runs[run_id] = current.model_copy(
                update={
                    "status": status,
                    "completed_at": _aware(completed_at),
                    "metadata": merged_metadata,
                }
            )

    def list_analysis_runs(self, *, limit: int = 20) -> list[AnalysisRunRecord]:
        with self._lock:
            runs = list(self._runs.values())
        return sorted(runs, key=lambda item: item.started_at, reverse=True)[: max(0, limit)]

    def save_events(self, events: list[ComplaintIntelligenceEvent]) -> None:
        with self._lock:
            for event in events:
                safe_event = _safe_event(event)
                self._events[safe_event.id] = safe_event

    def get_events(self, event_ids: list[str] | None = None) -> list[ComplaintIntelligenceEvent]:
        with self._lock:
            if event_ids is None:
                events = list(self._events.values())
            else:
                events = [self._events[event_id] for event_id in event_ids if event_id in self._events]
        return sorted(events, key=lambda item: item.received_at, reverse=True)

    def save_issue_alerts(self, alerts: list[IssueAlert]) -> None:
        with self._lock:
            for alert in alerts:
                self._alerts[alert.id] = alert

    def list_issue_alerts(self, status: str | None = None) -> list[IssueAlert]:
        with self._lock:
            alerts = list(self._alerts.values())
        if status:
            normalized = status.upper()
            alerts = [alert for alert in alerts if alert.status == normalized]
        return sorted(alerts, key=lambda item: (item.confidence, item.last_seen), reverse=True)

    def save_public_insights(self, insights: list[PublicAgencyInsight]) -> None:
        with self._lock:
            for insight in insights:
                self._insights[insight.insight_id] = insight

    def list_public_insights(
        self,
        *,
        status: str | None = None,
        insight_type: str | None = None,
    ) -> list[PublicAgencyInsight]:
        with self._lock:
            insights = list(self._insights.values())
        if status:
            normalized_status = status.lower()
            insights = [insight for insight in insights if insight.status == normalized_status]
        if insight_type:
            insights = [insight for insight in insights if insight.type == insight_type]
        return sorted(insights, key=lambda item: (item.confidence, item.affected_count), reverse=True)

    def get_public_insight(self, insight_id: str) -> PublicAgencyInsight | None:
        with self._lock:
            return self._insights.get(insight_id)

    def save_evidence_pack(self, insight_id: str, pack: PublicInsightEvidencePack) -> None:
        with self._lock:
            self._evidence_packs[insight_id] = pack

    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        with self._lock:
            return self._evidence_packs.get(insight_id)

    def save_duplicate_groups(self, groups: list[DuplicateMergeRecord]) -> None:
        with self._lock:
            for group in groups:
                self._duplicate_groups[group.merge_id] = group

    def list_duplicate_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        with self._lock:
            groups = list(self._duplicate_groups.values())
        if status:
            groups = [group for group in groups if group.status == status]
        return sorted(groups, key=lambda item: (item.status != "candidate", item.confidence), reverse=True)

    def get_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        with self._lock:
            return self._duplicate_groups.get(merge_id)

    def update_duplicate_group(self, group: DuplicateMergeRecord) -> None:
        with self._lock:
            self._duplicate_groups[group.merge_id] = group

    def get_dashboard_state(self) -> DashboardState:
        with self._lock:
            latest_run = _latest_run(list(self._runs.values()))
            latest_event_at = max((event.received_at for event in self._events.values()), default=None)
            active_alert_count = sum(1 for alert in self._alerts.values() if alert.status in {"ACTIVE", "UPDATED"})
            high_priority_count = sum(1 for insight in self._insights.values() if insight.priority in {"HIGH", "CRITICAL"})
            return DashboardState(
                as_of=latest_run.as_of if latest_run else None,
                latest_event_at=latest_event_at,
                event_count=len(self._events),
                active_alert_count=active_alert_count,
                high_priority_insight_count=high_priority_count,
                last_run_id=latest_run.run_id if latest_run else None,
                last_run_mode=latest_run.mode if latest_run else None,
                source_name=latest_run.source_name if latest_run else None,
            )

    def save_collector_checkpoint(self, checkpoint: CollectorCheckpointRecord) -> None:
        with self._lock:
            safe_checkpoint = checkpoint.model_copy(
                update={
                    "updated_at": _aware(checkpoint.updated_at),
                    "watermark": _aware(checkpoint.watermark) if checkpoint.watermark else None,
                    "metadata": _mask_strings(dict(checkpoint.metadata)),
                }
            )
            self._collector_checkpoints[(safe_checkpoint.collector_name, safe_checkpoint.source_name)] = safe_checkpoint

    def get_collector_checkpoint(
        self,
        collector_name: str,
        source_name: str,
    ) -> CollectorCheckpointRecord | None:
        with self._lock:
            return self._collector_checkpoints.get((collector_name, source_name))

    def list_collector_checkpoints(self) -> list[CollectorCheckpointRecord]:
        with self._lock:
            checkpoints = list(self._collector_checkpoints.values())
        return sorted(checkpoints, key=lambda item: item.updated_at, reverse=True)

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()
            self._events.clear()
            self._alerts.clear()
            self._insights.clear()
            self._evidence_packs.clear()
            self._duplicate_groups.clear()
            self._collector_checkpoints.clear()


def _safe_event(event: ComplaintIntelligenceEvent) -> ComplaintIntelligenceEvent:
    """저장 직전에도 PII 마스킹 validator를 한 번 더 통과시킨다."""

    return ComplaintIntelligenceEvent.model_validate(event.model_dump(mode="json"))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_run(runs: list[AnalysisRunRecord]) -> AnalysisRunRecord | None:
    if not runs:
        return None
    return sorted(runs, key=lambda item: item.started_at, reverse=True)[0]

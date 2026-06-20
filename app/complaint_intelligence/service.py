"""Complaint Intelligence Layer sidecar 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from app.complaint_intelligence.config import ComplaintIntelligenceConfig, get_complaint_intelligence_config
from app.complaint_intelligence.duplicate_merger.candidate_generator import actions_for_status
from app.complaint_intelligence.duplicate_merger.draft_payload import build_draft_reply_payload
from app.complaint_intelligence.duplicate_merger.merge_verifier import has_blocker
from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeService
from app.complaint_intelligence.duplicate_merger.service import DuplicateGroupNotFound, DuplicateMergeConflict
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateMergeStatus,
)
from app.complaint_intelligence.issue_detection import IssueDetectionEngine
from app.complaint_intelligence.public_insights import PublicAgencyInsightEngine
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.repository import (
    AnalysisRunMode,
    AnalysisRunRecord,
    ComplaintIntelligenceRepository,
    DashboardState,
    InMemoryComplaintIntelligenceRepository,
)
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicAgencyInsight,
)
from app.complaint_intelligence.sqlite_repository import SQLiteComplaintIntelligenceRepository


@dataclass
class ComplaintIntelligenceResult:
    """분석 실행 결과."""

    run_id: str
    mode: str
    source_name: str | None
    as_of: datetime
    event_count: int
    latest_event_at: datetime | None
    alerts: list[IssueAlert]
    public_insights: list[PublicAgencyInsight]


class ComplaintIntelligenceService:
    """기존 RAG/API 흐름과 분리된 민원 지능화 sidecar."""

    def __init__(
        self,
        issue_engine: IssueDetectionEngine | None = None,
        public_insight_engine: PublicAgencyInsightEngine | None = None,
        duplicate_merge_service: DuplicateMergeService | None = None,
        repository: ComplaintIntelligenceRepository | None = None,
        config: ComplaintIntelligenceConfig | None = None,
    ) -> None:
        self.config = config or get_complaint_intelligence_config()
        self.issue_engine = issue_engine or IssueDetectionEngine(config=self.config)
        self.public_insight_engine = public_insight_engine or PublicAgencyInsightEngine(config=self.config)
        self.duplicate_merge_service = duplicate_merge_service or DuplicateMergeService()
        self.repository = repository or _build_repository(self.config)
        self._lock = RLock()

    def run_analysis(
        self,
        events: list[ComplaintIntelligenceEvent],
        *,
        mode: str | None = None,
        source_name: str | None = None,
        as_of: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ComplaintIntelligenceResult:
        """이벤트 배치를 분석하고 경보/공공 인사이트 저장소를 갱신한다."""

        safe_events = _safe_events(events)
        run_mode = _normalize_mode(mode or self.config.default_mode)
        resolved_as_of = _resolve_as_of(safe_events, as_of)
        run_id = _new_run_id()
        started_at = _now()

        with self._lock:
            self.repository.save_analysis_run(
                run_id=run_id,
                mode=run_mode,
                source_name=source_name,
                event_count=len(safe_events),
                started_at=started_at,
                as_of=resolved_as_of,
                metadata={"analysis_type": "issue_and_public_insight", **(metadata or {})},
            )
            try:
                self.repository.save_events(safe_events)
                active_alerts = self.repository.list_issue_alerts()
                alerts = self.issue_engine.detect(safe_events, active_alerts=active_alerts)
                public_insights = self.public_insight_engine.generate(safe_events, alerts, now=resolved_as_of)
            except Exception as exc:
                self.repository.complete_analysis_run(
                    run_id,
                    status="failed",
                    completed_at=_now(),
                    metadata={"error_type": type(exc).__name__},
                )
                raise

            linked_by_alert: dict[str, list[str]] = {}

            for insight in public_insights:
                for alert_id in insight.linked_alert_ids:
                    linked_by_alert.setdefault(alert_id, []).append(insight.insight_id)
                pack = self.public_insight_engine.get_evidence_pack(insight.insight_id)
                if pack is not None:
                    self.repository.save_evidence_pack(insight.insight_id, pack)

            for alert in alerts:
                alert.linked_insight_ids = sorted(
                    set(alert.linked_insight_ids) | set(linked_by_alert.get(alert.id, []))
                )

            self.repository.save_public_insights(public_insights)
            self.repository.save_issue_alerts(alerts)
            self.repository.complete_analysis_run(
                run_id,
                status="completed",
                completed_at=_now(),
                metadata={
                    "alert_count": len(alerts),
                    "public_insight_count": len(public_insights),
                    "llm_metrics": self.public_insight_engine.get_last_generation_metrics(),
                },
            )

            return ComplaintIntelligenceResult(
                run_id=run_id,
                mode=run_mode,
                source_name=source_name,
                as_of=resolved_as_of,
                event_count=len(safe_events),
                latest_event_at=_latest_event_at(safe_events),
                alerts=alerts,
                public_insights=public_insights,
            )

    def list_issue_alerts(self, status: str | None = None) -> list[IssueAlert]:
        """저장된 이슈 경보를 반환한다."""

        return self.repository.list_issue_alerts(status=status)

    def list_public_insights(
        self,
        status: str | None = None,
        insight_type: str | None = None,
    ) -> list[PublicAgencyInsight]:
        """저장된 공공기관 행정 인사이트를 반환한다."""

        return self.repository.list_public_insights(status=status, insight_type=insight_type)

    def get_public_insight(self, insight_id: str) -> PublicAgencyInsight | None:
        """저장된 공공기관 행정 인사이트 단건을 반환한다."""

        return self.repository.get_public_insight(insight_id)

    def get_public_insight_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """저장된 공공기관 행정 인사이트의 마스킹 EvidencePack을 반환한다."""

        pack = self.repository.get_evidence_pack(insight_id)
        if pack is not None:
            return pack
        if self.repository.get_public_insight(insight_id) is None:
            return None
        return self.public_insight_engine.get_evidence_pack(insight_id)

    def run_duplicate_analysis(
        self,
        events: list[ComplaintIntelligenceEvent],
        *,
        mode: str | None = None,
        source_name: str | None = None,
        as_of: datetime | None = None,
    ) -> list[DuplicateMergeRecord]:
        """중복 병합 후보 분석을 명시적으로 실행한다."""

        safe_events = _safe_events(events)
        run_mode = _normalize_mode(mode or self.config.default_mode)
        resolved_as_of = _resolve_as_of(safe_events, as_of)
        run_id = _new_run_id()

        with self._lock:
            self.repository.save_analysis_run(
                run_id=run_id,
                mode=run_mode,
                source_name=source_name,
                event_count=len(safe_events),
                started_at=_now(),
                as_of=resolved_as_of,
                metadata={"analysis_type": "duplicate_merge"},
            )
            try:
                self.repository.save_events(safe_events)
                groups = self.duplicate_merge_service.run_analysis(
                    safe_events,
                    issue_alerts=self.repository.list_issue_alerts(),
                    public_insights=self.repository.list_public_insights(),
                )
                self.repository.save_duplicate_groups(groups)
                self.repository.complete_analysis_run(
                    run_id,
                    status="completed",
                    completed_at=_now(),
                    metadata={"duplicate_group_count": len(groups)},
                )
                return groups
            except Exception as exc:
                self.repository.complete_analysis_run(
                    run_id,
                    status="failed",
                    completed_at=_now(),
                    metadata={"error_type": type(exc).__name__},
                )
                raise

    def list_duplicate_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        """저장된 중복 병합 추천 그룹을 반환한다."""

        return self.repository.list_duplicate_groups(status=status)

    def get_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        """중복 병합 추천 그룹 단건을 반환한다."""

        return self.repository.get_duplicate_group(merge_id)

    def confirm_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 후보를 담당자 확정 상태로 전환한다."""

        return self._transition_duplicate_group(merge_id, "confirmed")

    def split_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 그룹을 분리 상태로 전환한다."""

        return self._transition_duplicate_group(merge_id, "split")

    def reject_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 후보를 기각 상태로 전환한다."""

        return self._transition_duplicate_group(merge_id, "rejected")

    def build_duplicate_draft_reply_payload(self, merge_id: str) -> DraftReplyPayload:
        """confirmed 중복 그룹의 대표 답변 payload를 생성한다."""

        record = self.repository.get_duplicate_group(merge_id)
        if record is None:
            raise DuplicateGroupNotFound(merge_id)
        if record.status != "confirmed":
            raise DuplicateMergeConflict(
                "DUPLICATE_GROUP_NOT_CONFIRMED",
                "대표 답변 초안 payload는 confirmed 그룹에서만 생성할 수 있습니다.",
                {"merge_id": merge_id, "status": record.status},
            )
        event_list = self.repository.get_events(record.member_complaint_ids)
        events = {event.id: event for event in event_list}
        missing_ids = [case_id for case_id in record.member_complaint_ids if case_id not in events]
        if missing_ids:
            raise DuplicateMergeConflict(
                "DUPLICATE_GROUP_EVENT_NOT_FOUND",
                "초안 payload 생성에 필요한 민원 이벤트를 찾을 수 없습니다.",
                {"merge_id": merge_id, "missing_case_ids": missing_ids},
            )
        return build_draft_reply_payload(record, events)

    def get_dashboard_state(self) -> DashboardState:
        """저장소의 관제 기준 시각과 누적 read-model 상태를 반환한다."""

        return self.repository.get_dashboard_state()

    def list_analysis_runs(self, *, limit: int = 20) -> list[AnalysisRunRecord]:
        """최근 분석 실행 이력과 비식별 실행 메타데이터를 반환한다."""

        return self.repository.list_analysis_runs(limit=limit)

    def clear(self) -> None:
        """테스트와 개발 초기화를 위해 저장소와 in-memory 보조 상태를 비운다."""

        self.repository.clear()
        self.duplicate_merge_service.clear()

    def _transition_duplicate_group(
        self,
        merge_id: str,
        status: DuplicateMergeStatus,
    ) -> DuplicateMergeRecord:
        with self._lock:
            record = self.repository.get_duplicate_group(merge_id)
            if record is None:
                raise DuplicateGroupNotFound(merge_id)
            if status == "confirmed":
                if record.status != "candidate":
                    raise DuplicateMergeConflict(
                        "DUPLICATE_GROUP_INVALID_STATUS",
                        "candidate 상태의 그룹만 confirmed로 전환할 수 있습니다.",
                        {"merge_id": merge_id, "status": record.status},
                    )
                if has_blocker(record.risk_flags):
                    raise DuplicateMergeConflict(
                        "DUPLICATE_GROUP_BLOCKED_BY_RISK",
                        "blocker risk가 있는 그룹은 병합 확정을 할 수 없습니다.",
                        {
                            "merge_id": merge_id,
                            "risk_flags": [
                                flag.model_dump(mode="json")
                                for flag in record.risk_flags
                                if flag.severity == "blocker"
                            ],
                        },
                    )
            elif status == "split":
                if record.status not in {"candidate", "confirmed"}:
                    raise DuplicateMergeConflict(
                        "DUPLICATE_GROUP_INVALID_STATUS",
                        "candidate 또는 confirmed 상태의 그룹만 split으로 전환할 수 있습니다.",
                        {"merge_id": merge_id, "status": record.status},
                    )
            elif status == "rejected" and record.status != "candidate":
                raise DuplicateMergeConflict(
                    "DUPLICATE_GROUP_INVALID_STATUS",
                    "candidate 상태의 그룹만 rejected로 전환할 수 있습니다.",
                    {"merge_id": merge_id, "status": record.status},
                )

            allowed_actions, blocked_actions = actions_for_status(status, record.risk_flags)
            updated = record.model_copy(
                update={
                    "status": status,
                    "allowed_actions": allowed_actions,
                    "blocked_actions": blocked_actions,
                    "updated_at": _now(),
                }
            )
            self.repository.update_duplicate_group(updated)
            return updated


def _build_repository(config: ComplaintIntelligenceConfig) -> ComplaintIntelligenceRepository:
    if config.repository == "memory":
        return InMemoryComplaintIntelligenceRepository()
    return SQLiteComplaintIntelligenceRepository(config.db_path, auto_create=config.auto_create_db)


def _safe_events(events: list[ComplaintIntelligenceEvent]) -> list[ComplaintIntelligenceEvent]:
    return [ComplaintIntelligenceEvent.model_validate(event.model_dump(mode="json")) for event in events]


def _normalize_mode(mode: str) -> AnalysisRunMode:
    value = str(mode or "realtime").lower()
    if value in {"realtime", "replay", "manual"}:
        return value  # type: ignore[return-value]
    return "manual"


def _resolve_as_of(events: list[ComplaintIntelligenceEvent], as_of: datetime | None) -> datetime:
    if as_of is not None:
        return _aware(as_of)
    latest_event_at = _latest_event_at(events)
    if latest_event_at is not None:
        return _aware(latest_event_at)
    return _now()


def _latest_event_at(events: list[ComplaintIntelligenceEvent]) -> datetime | None:
    if not events:
        return None
    return max(_aware(event.received_at) for event in events)


def _new_run_id() -> str:
    return f"ci-run-{uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_service: ComplaintIntelligenceService | None = None


def get_complaint_intelligence_service() -> ComplaintIntelligenceService:
    """API 라우터에서 공유하는 Complaint Intelligence sidecar 인스턴스."""

    global _service
    if _service is None:
        _service = ComplaintIntelligenceService()
    return _service


def set_complaint_intelligence_service(service: ComplaintIntelligenceService | None) -> None:
    """테스트에서 저장소 격리를 위해 공유 서비스 인스턴스를 교체한다."""

    global _service
    _service = service

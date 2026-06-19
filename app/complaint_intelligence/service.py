"""Complaint Intelligence Layer sidecar 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeService
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateMergeStatus,
)
from app.complaint_intelligence.issue_detection import IssueDetectionEngine
from app.complaint_intelligence.public_insights import PublicAgencyInsightEngine
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicAgencyInsight,
)


@dataclass
class ComplaintIntelligenceResult:
    """분석 실행 결과."""

    alerts: list[IssueAlert]
    public_insights: list[PublicAgencyInsight]


class ComplaintIntelligenceService:
    """기존 RAG/API 흐름과 분리된 민원 지능화 sidecar."""

    def __init__(
        self,
        issue_engine: IssueDetectionEngine | None = None,
        public_insight_engine: PublicAgencyInsightEngine | None = None,
        duplicate_merge_service: DuplicateMergeService | None = None,
    ) -> None:
        self.issue_engine = issue_engine or IssueDetectionEngine()
        self.public_insight_engine = public_insight_engine or PublicAgencyInsightEngine()
        self.duplicate_merge_service = duplicate_merge_service or DuplicateMergeService()
        self._alerts: dict[str, IssueAlert] = {}
        self._public_insights: dict[str, PublicAgencyInsight] = {}
        self._lock = RLock()

    def run_analysis(self, events: list[ComplaintIntelligenceEvent]) -> ComplaintIntelligenceResult:
        """이벤트 배치를 분석하고 경보/공공 인사이트 저장소를 갱신한다."""

        with self._lock:
            alerts = self.issue_engine.detect(events, active_alerts=list(self._alerts.values()))
            public_insights = self.public_insight_engine.generate(events, alerts)
            linked_by_alert: dict[str, list[str]] = {}

            for insight in public_insights:
                self._public_insights[insight.insight_id] = insight
                for alert_id in insight.linked_alert_ids:
                    linked_by_alert.setdefault(alert_id, []).append(insight.insight_id)

            for alert in alerts:
                alert.linked_insight_ids = sorted(
                    set(alert.linked_insight_ids) | set(linked_by_alert.get(alert.id, []))
                )
                self._alerts[alert.id] = alert

            return ComplaintIntelligenceResult(alerts=alerts, public_insights=public_insights)

    def list_issue_alerts(self, status: str | None = None) -> list[IssueAlert]:
        """저장된 이슈 경보를 반환한다."""

        with self._lock:
            alerts = list(self._alerts.values())
        if status:
            normalized = status.upper()
            alerts = [alert for alert in alerts if alert.status == normalized]
        return sorted(alerts, key=lambda item: (item.confidence, item.last_seen), reverse=True)

    def list_public_insights(
        self,
        status: str | None = None,
        insight_type: str | None = None,
    ) -> list[PublicAgencyInsight]:
        """저장된 공공기관 행정 인사이트를 반환한다."""

        with self._lock:
            insights = list(self._public_insights.values())
        if status:
            normalized_status = status.upper()
            insights = [insight for insight in insights if insight.status == normalized_status]
        if insight_type:
            insights = [insight for insight in insights if insight.type == insight_type]
        return sorted(insights, key=lambda item: (item.confidence, item.affected_count), reverse=True)

    def get_public_insight(self, insight_id: str) -> PublicAgencyInsight | None:
        """저장된 공공기관 행정 인사이트 단건을 반환한다."""

        with self._lock:
            return self._public_insights.get(insight_id)

    def get_public_insight_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """저장된 공공기관 행정 인사이트의 마스킹 EvidencePack을 반환한다."""

        with self._lock:
            if insight_id not in self._public_insights:
                return None
            return self.public_insight_engine.get_evidence_pack(insight_id)

    def run_duplicate_analysis(self, events: list[ComplaintIntelligenceEvent]) -> list[DuplicateMergeRecord]:
        """중복 병합 후보 분석을 명시적으로 실행한다."""

        with self._lock:
            alerts = list(self._alerts.values())
            public_insights = list(self._public_insights.values())
        return self.duplicate_merge_service.run_analysis(
            events,
            issue_alerts=alerts,
            public_insights=public_insights,
        )

    def list_duplicate_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        """저장된 중복 병합 추천 그룹을 반환한다."""

        return self.duplicate_merge_service.list_groups(status=status)

    def get_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        """중복 병합 추천 그룹 단건을 반환한다."""

        return self.duplicate_merge_service.get_group(merge_id)

    def confirm_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 후보를 담당자 확정 상태로 전환한다."""

        return self.duplicate_merge_service.confirm_group(merge_id)

    def split_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 그룹을 분리 상태로 전환한다."""

        return self.duplicate_merge_service.split_group(merge_id)

    def reject_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord:
        """중복 병합 후보를 기각 상태로 전환한다."""

        return self.duplicate_merge_service.reject_group(merge_id)

    def build_duplicate_draft_reply_payload(self, merge_id: str) -> DraftReplyPayload:
        """confirmed 중복 그룹의 대표 답변 payload를 생성한다."""

        return self.duplicate_merge_service.build_draft_reply_payload(merge_id)


_service = ComplaintIntelligenceService()


def get_complaint_intelligence_service() -> ComplaintIntelligenceService:
    """API 라우터에서 공유하는 in-memory sidecar 인스턴스."""

    return _service

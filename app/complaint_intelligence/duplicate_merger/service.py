"""중복 민원 병합 추천 in-memory 서비스."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any

from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight
from app.complaint_intelligence.duplicate_merger.candidate_generator import (
    DuplicateCandidateGenerator,
    actions_for_status,
)
from app.complaint_intelligence.duplicate_merger.draft_payload import build_draft_reply_payload
from app.complaint_intelligence.duplicate_merger.merge_verifier import has_blocker
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateMergeStatus,
)


class DuplicateGroupNotFound(Exception):
    """요청한 병합 그룹이 없는 경우."""


class DuplicateMergeConflict(Exception):
    """상태 전이 또는 액션이 허용되지 않는 경우."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DuplicateMergeService:
    """DB migration 없이 동작하는 중복 병합 추천 read-model 저장소."""

    def __init__(self, generator: DuplicateCandidateGenerator | None = None) -> None:
        self.generator = generator or DuplicateCandidateGenerator()
        self._records: dict[str, DuplicateMergeRecord] = {}
        self._events: dict[str, ComplaintIntelligenceEvent] = {}
        self._lock = RLock()

    def run_analysis(
        self,
        events: list[ComplaintIntelligenceEvent],
        *,
        issue_alerts: list[IssueAlert] | None = None,
        public_insights: list[PublicAgencyInsight] | None = None,
    ) -> list[DuplicateMergeRecord]:
        """이벤트 배치를 분석해 candidate 그룹을 만들고 저장소를 갱신한다."""

        candidates = self.generator.generate(events)
        with self._lock:
            for event in events:
                self._events[event.id] = event

            saved: list[DuplicateMergeRecord] = []
            for candidate in candidates:
                linked = candidate.model_copy(
                    update={
                        "linked_issue_alert_ids": _linked_issue_alert_ids(candidate, issue_alerts or []),
                        "linked_public_insight_ids": _linked_public_insight_ids(candidate, public_insights or []),
                    }
                )
                existing = self._records.get(linked.merge_id)
                if existing and existing.status != "candidate":
                    saved.append(existing)
                    continue
                self._records[linked.merge_id] = linked
                saved.append(linked)
            return sorted(saved, key=lambda item: (item.confidence, len(item.member_complaint_ids)), reverse=True)

    def list_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        """저장된 중복 병합 그룹 목록을 반환한다."""

        with self._lock:
            records = list(self._records.values())
        if status:
            records = [record for record in records if record.status == status]
        return sorted(records, key=lambda item: (item.status != "candidate", item.confidence), reverse=True)

    def get_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        """병합 그룹 단건을 반환한다."""

        with self._lock:
            return self._records.get(merge_id)

    def confirm_group(self, merge_id: str) -> DuplicateMergeRecord:
        """candidate 그룹을 담당자 승인 상태로 전환한다."""

        with self._lock:
            record = self._require_group(merge_id)
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
                        "risk_flags": [flag.model_dump(mode="json") for flag in record.risk_flags if flag.severity == "blocker"],
                    },
                )
            return self._replace_status(record, "confirmed")

    def split_group(self, merge_id: str) -> DuplicateMergeRecord:
        """candidate 또는 confirmed 그룹을 분리 상태로 전환한다."""

        with self._lock:
            record = self._require_group(merge_id)
            if record.status not in {"candidate", "confirmed"}:
                raise DuplicateMergeConflict(
                    "DUPLICATE_GROUP_INVALID_STATUS",
                    "candidate 또는 confirmed 상태의 그룹만 split으로 전환할 수 있습니다.",
                    {"merge_id": merge_id, "status": record.status},
                )
            return self._replace_status(record, "split")

    def reject_group(self, merge_id: str) -> DuplicateMergeRecord:
        """candidate 그룹을 담당자 기각 상태로 전환한다."""

        with self._lock:
            record = self._require_group(merge_id)
            if record.status != "candidate":
                raise DuplicateMergeConflict(
                    "DUPLICATE_GROUP_INVALID_STATUS",
                    "candidate 상태의 그룹만 rejected로 전환할 수 있습니다.",
                    {"merge_id": merge_id, "status": record.status},
                )
            return self._replace_status(record, "rejected")

    def build_draft_reply_payload(self, merge_id: str) -> DraftReplyPayload:
        """confirmed 그룹에 대해서만 BE3 전달 payload를 생성한다."""

        with self._lock:
            record = self._require_group(merge_id)
            if record.status != "confirmed":
                raise DuplicateMergeConflict(
                    "DUPLICATE_GROUP_NOT_CONFIRMED",
                    "대표 답변 초안 payload는 confirmed 그룹에서만 생성할 수 있습니다.",
                    {"merge_id": merge_id, "status": record.status},
                )
            missing_ids = [case_id for case_id in record.member_complaint_ids if case_id not in self._events]
            if missing_ids:
                raise DuplicateMergeConflict(
                    "DUPLICATE_GROUP_EVENT_NOT_FOUND",
                    "초안 payload 생성에 필요한 민원 이벤트를 찾을 수 없습니다.",
                    {"merge_id": merge_id, "missing_case_ids": missing_ids},
                )
            return build_draft_reply_payload(record, self._events)

    def clear(self) -> None:
        """테스트에서 in-memory 상태를 초기화한다."""

        with self._lock:
            self._records.clear()
            self._events.clear()

    def _require_group(self, merge_id: str) -> DuplicateMergeRecord:
        record = self._records.get(merge_id)
        if record is None:
            raise DuplicateGroupNotFound(merge_id)
        return record

    def _replace_status(self, record: DuplicateMergeRecord, status: DuplicateMergeStatus) -> DuplicateMergeRecord:
        allowed_actions, blocked_actions = actions_for_status(status, record.risk_flags)
        updated = record.model_copy(
            update={
                "status": status,
                "allowed_actions": allowed_actions,
                "blocked_actions": blocked_actions,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._records[record.merge_id] = updated
        return updated


def _linked_issue_alert_ids(record: DuplicateMergeRecord, alerts: list[IssueAlert]) -> list[str]:
    member_ids = set(record.member_complaint_ids)
    linked = []
    for alert in alerts:
        alert_ids = set(alert.related_ids)
        alert_ids.update(item.id for item in alert.representative_complaints)
        if member_ids & alert_ids:
            linked.append(alert.id)
    return sorted(set(linked))


def _linked_public_insight_ids(record: DuplicateMergeRecord, insights: list[PublicAgencyInsight]) -> list[str]:
    member_ids = set(record.member_complaint_ids)
    linked = []
    for insight in insights:
        evidence_ids = set(insight.representative_complaint_ids) | set(insight.representative_ids)
        evidence_ids.update(item.complaint_id for item in insight.evidence)
        if member_ids & evidence_ids:
            linked.append(insight.insight_id)
    return sorted(set(linked))

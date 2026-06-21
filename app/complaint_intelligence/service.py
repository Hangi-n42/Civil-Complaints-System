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
from app.complaint_intelligence.duplicate_merger.reply_context import build_duplicate_reply_context
from app.complaint_intelligence.duplicate_merger.reply_safety import build_reply_safety_warnings
from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeService
from app.complaint_intelligence.duplicate_merger.service import DuplicateGroupNotFound, DuplicateMergeConflict
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateReplyDraft,
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
from app.core.exceptions import GenerationError, RetrievalError
from app.generation.service import get_generation_service
from app.retrieval.service import get_retrieval_service


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

    def list_duplicate_groups(
        self,
        status: DuplicateMergeStatus | None = None,
        *,
        complaint_id: str | None = None,
        issue_alert_id: str | None = None,
        public_insight_id: str | None = None,
    ) -> list[DuplicateMergeRecord]:
        """저장된 중복 병합 추천 그룹을 반환한다."""

        groups = self.repository.list_duplicate_groups(status=status)
        return [
            group
            for group in groups
            if _matches_duplicate_group_filter(
                group,
                complaint_id=complaint_id,
                issue_alert_id=issue_alert_id,
                public_insight_id=public_insight_id,
            )
        ]

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

        record, events = self._confirmed_duplicate_group_events(merge_id)
        return build_draft_reply_payload(record, events)

    async def build_duplicate_reply_draft(self, merge_id: str) -> DuplicateReplyDraft:
        """confirmed 중복 그룹에 대해 실제 대표 답변 초안을 생성한다."""

        record, events = self._confirmed_duplicate_group_events(merge_id)
        payload = build_draft_reply_payload(record, events)
        reply_context = build_duplicate_reply_context(record, payload)
        retrieval_warning: str | None = None
        try:
            search_results = await get_retrieval_service().search(
                query=reply_context.query,
                top_k=5,
                request_segments=reply_context.request_segments,
                retrieval_policy=str(reply_context.routing_trace.get("retrieval_policy") or "general"),
                snippet_max_chars=1100,
                query_signals=reply_context.query_signals,
                exclude_case_id=record.representative_complaint_id,
            )
        except RetrievalError:
            search_results = []
            retrieval_warning = "RETRIEVAL_ERROR"
        context = _exclude_duplicate_member_results(search_results, reply_context.excluded_case_ids)
        if context:
            try:
                result = await get_generation_service().generate_qa(
                    query=reply_context.query,
                    context=context,
                    routing_trace=reply_context.routing_trace,
                    query_signals=reply_context.query_signals,
                )
                answer = str(result.get("answer") or "").strip()
                citations = result.get("citations") if isinstance(result.get("citations"), list) else []
                limitations = _limitations_to_list(result.get("limitations"))
                structured_output = (
                    result.get("structured_output")
                    if isinstance(result.get("structured_output"), dict)
                    else {}
                )
                generation_metadata = (
                    result.get("generation_metadata")
                    if isinstance(result.get("generation_metadata"), dict)
                    else {}
                )
            except GenerationError as exc:
                answer, citations, limitations, structured_output, generation_metadata = _fallback_duplicate_reply(
                    payload,
                    reason=f"{exc.__class__.__name__}:{getattr(exc, 'code', 'GENERATION_ERROR')}",
                )
        else:
            answer, citations, limitations, structured_output, generation_metadata = _fallback_duplicate_reply(
                payload,
                reason=retrieval_warning or "NO_SEARCH_CONTEXT",
            )

        safety_warnings = build_reply_safety_warnings(answer)
        if retrieval_warning:
            safety_warnings.append(retrieval_warning)
        if not context:
            safety_warnings.append("NO_SEARCH_CONTEXT")
        if record.risk_flags:
            safety_warnings.append("RISK_FLAGS_PRESENT")

        return DuplicateReplyDraft(
            merge_id=record.merge_id,
            representative_complaint_id=record.representative_complaint_id,
            member_complaint_ids=list(record.member_complaint_ids),
            answer=answer,
            citations=[dict(item) for item in citations if isinstance(item, dict)],
            limitations=limitations,
            structured_output=structured_output,
            generation_metadata={
                **generation_metadata,
                "duplicate_group_reply": True,
                "requires_human_review": True,
                "search_result_count": len(context),
                "retrieval_warning": retrieval_warning,
            },
            safety_warnings=_unique_strings(safety_warnings),
            query=reply_context.query,
            routing_hint=reply_context.routing_hint,
            routing_trace=reply_context.routing_trace,
            search_results=[_public_search_result(item) for item in context],
            draft_reply_payload=payload,
        )

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

    def _confirmed_duplicate_group_events(
        self,
        merge_id: str,
    ) -> tuple[DuplicateMergeRecord, dict[str, ComplaintIntelligenceEvent]]:
        record = self.repository.get_duplicate_group(merge_id)
        if record is None:
            raise DuplicateGroupNotFound(merge_id)
        if record.status != "confirmed":
            raise DuplicateMergeConflict(
                "DUPLICATE_GROUP_NOT_CONFIRMED",
                "대표 답변 초안은 confirmed 그룹에서만 생성할 수 있습니다.",
                {"merge_id": merge_id, "status": record.status},
            )
        event_list = self.repository.get_events(record.member_complaint_ids)
        events = {event.id: event for event in event_list}
        missing_ids = [case_id for case_id in record.member_complaint_ids if case_id not in events]
        if missing_ids:
            raise DuplicateMergeConflict(
                "DUPLICATE_GROUP_EVENT_NOT_FOUND",
                "초안 생성에 필요한 민원 이벤트를 찾을 수 없습니다.",
                {"merge_id": merge_id, "missing_case_ids": missing_ids},
            )
        return record, events

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


def _matches_duplicate_group_filter(
    group: DuplicateMergeRecord,
    *,
    complaint_id: str | None,
    issue_alert_id: str | None,
    public_insight_id: str | None,
) -> bool:
    if complaint_id and complaint_id not in group.member_complaint_ids:
        return False
    if issue_alert_id and issue_alert_id not in group.linked_issue_alert_ids:
        return False
    if public_insight_id and public_insight_id not in group.linked_public_insight_ids:
        return False
    return True


def _exclude_duplicate_member_results(
    results: list[dict[str, Any]],
    member_ids: list[str],
) -> list[dict[str, Any]]:
    excluded = {_case_key(case_id) for case_id in member_ids}
    return [
        item
        for item in results
        if not _is_duplicate_member_result(item, excluded)
    ]


def _is_duplicate_member_result(item: dict[str, Any], excluded: set[str]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    candidates = [
        item.get("case_id"),
        item.get("doc_id"),
        item.get("chunk_id"),
        metadata.get("case_id"),
        metadata.get("source_id"),
    ]
    for value in candidates:
        text = str(value or "").split("__", 1)[0]
        if _case_key(text) in excluded:
            return True
    return False


def _case_key(value: str) -> str:
    return str(value or "").strip().upper().removeprefix("CASE-")


def _limitations_to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return ["담당자 검토 후 발송 여부를 결정해야 합니다."]
    return [text]


def _fallback_duplicate_reply(
    payload: DraftReplyPayload,
    *,
    reason: str,
) -> tuple[str, list[dict[str, Any]], list[str], dict[str, Any], dict[str, Any]]:
    summary = payload.representative.pii_safe_summary or "반복 접수된 민원에 대한 공통 검토 요청"
    request_segments = payload.representative.request_segments or ["공통 민원 사항 확인 및 처리 방향 안내"]
    answer = (
        "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
        "2. 귀하의 민원 내용은 같은 사안으로 반복 접수된 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. "
        "다만 본 초안은 담당자가 확정한 중복 그룹의 공통 사항을 정리한 검토용 문안입니다.\n\n"
        f"3. 검토 의견은 다음과 같습니다. {summary[:220]} 관련 사항은 담당부서에서 접수 내용과 현장 여건, "
        "관련 기준을 함께 확인한 뒤 공통으로 안내 가능한 조치와 개별 확인이 필요한 사항을 구분해 검토하겠습니다. "
        "개별 보상 여부, 권리관계, 법정 처리기한 등은 본 공통 초안에서 판단하지 않습니다.\n\n"
        "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
    )
    structured_output = {
        "summary": summary[:240],
        "action_items": [
            "대표 민원과 구성 민원의 공통 사실관계 확인",
            "개별 권리관계 또는 보상 판단이 필요한 항목 분리 검토",
        ],
        "request_segments": list(request_segments),
        "segment_answers": [
            {
                "segment_index": index,
                "request_segment": segment,
                "answer": "유사 선례 없음 — 담당부서 확인 필요",
                "case_ids": [],
                "evidence_status": "no_evidence",
            }
            for index, segment in enumerate(request_segments)
        ],
    }
    return (
        answer,
        [],
        ["검색 근거 또는 생성 결과가 충분하지 않아 담당자 검토용 안전 초안으로 대체했습니다."],
        structured_output,
        {"fallback_used": True, "fallback_reason": reason},
    )


def _public_search_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": item.get("case_id"),
        "doc_id": item.get("doc_id"),
        "chunk_id": item.get("chunk_id"),
        "snippet": item.get("snippet"),
        "score": item.get("score", item.get("relevance_score")),
    }


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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

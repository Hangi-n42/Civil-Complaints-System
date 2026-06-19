"""병합 후보 hard gate와 risk flag 검증."""

from __future__ import annotations

from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.duplicate_merger.scoring import (
    DuplicateScoreResult,
    analysis_text,
    classify_request_type,
    structural_evidence_count,
)
from app.complaint_intelligence.duplicate_merger.schemas import DuplicateRiskFlag


class MergeVerifier:
    """중복 점수와 별개로 담당자 승인 전 확인해야 할 위험을 생성한다."""

    def verify(
        self,
        events: list[ComplaintIntelligenceEvent],
        pair_results: list[DuplicateScoreResult],
    ) -> list[DuplicateRiskFlag]:
        flags: list[DuplicateRiskFlag] = []
        flags.extend(self._pair_flags(pair_results))
        flags.extend(self._group_flags(events))
        return _dedupe_flags(flags)

    def _pair_flags(self, pair_results: list[DuplicateScoreResult]) -> list[DuplicateRiskFlag]:
        flags: list[DuplicateRiskFlag] = []
        for result in pair_results:
            case_ids = list(result.case_ids)
            if result.location_state == "conflict":
                flags.append(
                    DuplicateRiskFlag(
                        code="LOCATION_MISMATCH",
                        severity="blocker",
                        message="명확히 다른 장소 신호가 있어 병합 확정을 막습니다.",
                        affected_case_ids=case_ids,
                        evidence=[f"location_state={result.location_state}"],
                    )
                )
            elif result.location_state in {"ambiguous", "missing"}:
                flags.append(
                    DuplicateRiskFlag(
                        code="LOCATION_AMBIGUOUS",
                        severity="warning",
                        message="장소 신호가 불명확해 단독 병합 근거로 사용할 수 없습니다.",
                        affected_case_ids=case_ids,
                        evidence=[f"location_state={result.location_state}"],
                    )
                )

            request_types = set(result.request_types.values())
            if len(request_types) > 1 and "other" not in request_types:
                flags.append(
                    DuplicateRiskFlag(
                        code="REQUEST_TYPE_MISMATCH",
                        severity="warning",
                        message="동일 사건 가능성은 있으나 요청 유형이 서로 다릅니다.",
                        affected_case_ids=case_ids,
                        evidence=[f"{case_id}: {request_type}" for case_id, request_type in result.request_types.items()],
                    )
                )

            if result.time_delta_hours > 72:
                flags.append(
                    DuplicateRiskFlag(
                        code="TIME_WINDOW_TOO_WIDE",
                        severity="warning",
                        message="접수 시간 간격이 72시간을 넘어 같은 사건인지 확인이 필요합니다.",
                        affected_case_ids=case_ids,
                        evidence=[f"time_delta_hours={result.time_delta_hours:.1f}"],
                    )
                )

            if (
                result.breakdown.get("semantic_similarity", 0.0) >= 0.78
                and result.breakdown.get("entity_overlap", 0.0) == 0.0
                and result.location_state in {"ambiguous", "missing"}
                and result.breakdown.get("request_segment_similarity", 0.0) < 0.2
            ):
                flags.append(
                    DuplicateRiskFlag(
                        code="SEMANTIC_ONLY_MATCH",
                        severity="warning",
                        message="의미 유사도는 높지만 구조화 근거가 부족합니다.",
                        affected_case_ids=case_ids,
                        evidence=[
                            f"semantic_similarity={result.breakdown.get('semantic_similarity', 0.0):.2f}",
                            "entity/location/request segment 근거 부족",
                        ],
                    )
                )
        return flags

    def _group_flags(self, events: list[ComplaintIntelligenceEvent]) -> list[DuplicateRiskFlag]:
        flags: list[DuplicateRiskFlag] = []
        if not events:
            return flags

        departments = {
            _normalize_department(value)
            for event in events
            for value in _department_values(event)
            if _normalize_department(value)
        }
        if len(departments) > 1:
            flags.append(
                DuplicateRiskFlag(
                    code="DEPARTMENT_MISMATCH",
                    severity="blocker",
                    message="담당부서 신호가 충돌해 병합 확정을 막습니다.",
                    affected_case_ids=[event.id for event in events],
                    evidence=sorted(departments),
                )
            )

        request_types = {event.id: classify_request_type(event) for event in events}
        if "safety_action" in request_types.values() and {"inquiry", "guidance", "other"} & set(request_types.values()):
            flags.append(
                DuplicateRiskFlag(
                    code="SAFETY_AND_INCONVENIENCE_MIXED",
                    severity="blocker",
                    message="안전 위험 민원과 단순 문의/불편 민원이 섞여 있습니다.",
                    affected_case_ids=[event.id for event in events],
                    evidence=[f"{case_id}: {request_type}" for case_id, request_type in request_types.items()],
                )
            )

        if any(self._has_legal_or_deadline_risk(event) for event in events):
            flags.append(
                DuplicateRiskFlag(
                    code="LEGAL_RIGHTS_OR_DEADLINE_RISK",
                    severity="blocker",
                    message="민원인별 권리관계, 보상 또는 법정 처리기한 차이가 있을 수 있습니다.",
                    affected_case_ids=[event.id for event in events],
                    evidence=[
                        event.id
                        for event in events
                        if self._has_legal_or_deadline_risk(event)
                    ],
                )
            )

        pii_events = [event for event in events if event.pii_detected or event.pii_status not in {"PASSED", "MASKED"}]
        if pii_events:
            flags.append(
                DuplicateRiskFlag(
                    code="PII_RISK",
                    severity="warning",
                    message="입력에서 PII가 감지되었으므로 payload와 화면 노출 전 마스킹 상태를 확인해야 합니다.",
                    affected_case_ids=[event.id for event in pii_events],
                    evidence=sorted({label for event in pii_events for label in event.pii_labels}),
                )
            )

        multi_intent_events = [
            event for event in events
            if len(getattr(event, "request_segments", []) or []) > 1
        ]
        if multi_intent_events:
            flags.append(
                DuplicateRiskFlag(
                    code="MULTI_INTENT_SEGMENTS",
                    severity="warning",
                    message="복수 요청 segment가 있어 동일 업무 단위로 묶을 수 있는지 검토해야 합니다.",
                    affected_case_ids=[event.id for event in multi_intent_events],
                    evidence=[
                        f"{event.id}: {len(getattr(event, 'request_segments', []) or [])} segments"
                        for event in multi_intent_events
                    ],
                )
            )

        low_evidence = [event for event in events if structural_evidence_count(event) < 3]
        if low_evidence:
            flags.append(
                DuplicateRiskFlag(
                    code="LOW_EVIDENCE",
                    severity="warning",
                    message="일부 민원은 구조화 근거가 부족해 담당자 확인이 필요합니다.",
                    affected_case_ids=[event.id for event in low_evidence],
                    evidence=[
                        f"{event.id}: structural_evidence_count={structural_evidence_count(event)}"
                        for event in low_evidence
                    ],
                )
            )
        return flags

    def _has_legal_or_deadline_risk(self, event: ComplaintIntelligenceEvent) -> bool:
        text = analysis_text(event)
        return any(keyword in text for keyword in ("보상", "배상", "손해", "권리", "법정", "처리기한", "기한"))


def has_blocker(flags: list[DuplicateRiskFlag]) -> bool:
    """확정을 막아야 하는 blocker risk가 있는지 확인한다."""

    return any(flag.severity == "blocker" for flag in flags)


def _department_values(event: ComplaintIntelligenceEvent) -> list[str | None]:
    values = [event.final_department, event.predicted_department]
    values.extend(getattr(event, "responsible_unit", []) or [])
    return values


def _normalize_department(value: str | None) -> str:
    return "".join(str(value or "").split())


def _dedupe_flags(flags: list[DuplicateRiskFlag]) -> list[DuplicateRiskFlag]:
    merged: dict[str, DuplicateRiskFlag] = {}
    severity_rank = {"info": 0, "warning": 1, "blocker": 2}
    for flag in flags:
        if flag.code not in merged:
            merged[flag.code] = flag
            continue
        existing = merged[flag.code]
        severity = flag.severity
        if severity_rank[existing.severity] > severity_rank[severity]:
            severity = existing.severity
        merged[flag.code] = DuplicateRiskFlag(
            code=flag.code,
            severity=severity,
            message=existing.message,
            affected_case_ids=sorted(set(existing.affected_case_ids) | set(flag.affected_case_ids)),
            evidence=_dedupe(existing.evidence + flag.evidence),
        )
    return sorted(merged.values(), key=lambda item: (item.severity != "blocker", item.code))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

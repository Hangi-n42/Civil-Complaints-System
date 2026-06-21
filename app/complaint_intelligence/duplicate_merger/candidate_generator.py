"""중복 민원 후보 그룹 생성."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.duplicate_merger.merge_verifier import MergeVerifier, has_blocker
from app.complaint_intelligence.duplicate_merger.representative_selector import RepresentativeSelector
from app.complaint_intelligence.duplicate_merger.scoring import DuplicateScoreResult, score_duplicate_pair
from app.complaint_intelligence.duplicate_merger.schemas import (
    DuplicateAction,
    DuplicateEvidence,
    DuplicateLocationState,
    DuplicateMergeRecord,
    DuplicateRecommendationLevel,
)


class DuplicateCandidateGenerator:
    """PII-safe 이벤트 신호를 기반으로 중복 병합 후보를 만든다."""

    def __init__(
        self,
        *,
        min_candidate_score: float = 0.50,
        max_pair_window_hours: float = 24 * 7,
    ) -> None:
        self.min_candidate_score = min_candidate_score
        self.max_pair_window_hours = max_pair_window_hours
        self.verifier = MergeVerifier()
        self.representative_selector = RepresentativeSelector()

    def generate(self, events: list[ComplaintIntelligenceEvent]) -> list[DuplicateMergeRecord]:
        """분석 이벤트 목록에서 candidate 상태의 read-model을 생성한다."""

        if len(events) < 2:
            return []

        sorted_events = sorted(events, key=lambda item: (item.received_at, item.id))
        pair_results: dict[tuple[str, str], DuplicateScoreResult] = {}
        parent = {event.id: event.id for event in sorted_events}

        for index, left in enumerate(sorted_events):
            for right in sorted_events[index + 1:]:
                if _time_delta_hours(left.received_at, right.received_at) > self.max_pair_window_hours:
                    continue
                result = score_duplicate_pair(left, right)
                if result.score < self.min_candidate_score:
                    continue
                if result.location_state == "conflict":
                    continue
                if result.location_state == "ambiguous" and (left.pii_detected or right.pii_detected):
                    continue
                if result.location_state == "ambiguous" and result.score < 0.80:
                    continue
                key = tuple(sorted(result.case_ids))
                pair_results[key] = result
                self._union(parent, left.id, right.id)

        groups: dict[str, list[ComplaintIntelligenceEvent]] = {}
        for event in sorted_events:
            root = self._find(parent, event.id)
            groups.setdefault(root, []).append(event)

        records = []
        for members in groups.values():
            if len(members) < 2:
                continue
            member_ids = sorted(event.id for event in members)
            group_pairs = [
                result for key, result in pair_results.items()
                if set(key).issubset(member_ids)
            ]
            if not group_pairs:
                continue
            records.append(self._build_record(members, group_pairs))

        return sorted(records, key=lambda item: (item.confidence, len(item.member_complaint_ids)), reverse=True)

    def _build_record(
        self,
        events: list[ComplaintIntelligenceEvent],
        pair_results: list[DuplicateScoreResult],
    ) -> DuplicateMergeRecord:
        representative = self.representative_selector.select(events)
        verification_pairs = _complete_pair_results(events, pair_results)
        flags = self.verifier.verify(events, verification_pairs)
        confidence = round(sum(result.score for result in pair_results) / len(pair_results), 4)
        evidence = _dedupe_evidence([evidence for result in pair_results for evidence in result.evidence])
        location_state = _aggregate_location_state(verification_pairs)
        request_types: dict[str, str] = {}
        for result in verification_pairs:
            request_types.update(result.request_types)
        allowed_actions, blocked_actions = actions_for_status("candidate", flags)
        return DuplicateMergeRecord(
            merge_id=_merge_id(event.id for event in events),
            status="candidate",
            representative_complaint_id=representative.complaint_id,
            member_complaint_ids=sorted(event.id for event in events),
            confidence=confidence,
            recommendation_level=_recommendation_level(confidence, flags),
            evidence=evidence,
            risk_flags=flags,
            allowed_actions=allowed_actions,
            blocked_actions=blocked_actions,
            linked_issue_alert_ids=[],
            linked_public_insight_ids=[],
            representative=representative,
            score_breakdown=_average_breakdown(pair_results),
            location_state=location_state,
            request_types=request_types,
            created_at=min(event.received_at for event in events).astimezone(timezone.utc),
            updated_at=max(event.received_at for event in events).astimezone(timezone.utc),
        )

    def _find(self, parent: dict[str, str], item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def _union(self, parent: dict[str, str], left: str, right: str) -> None:
        left_root = self._find(parent, left)
        right_root = self._find(parent, right)
        if left_root != right_root:
            parent[right_root] = left_root


def actions_for_status(
    status: str,
    flags: list,
) -> tuple[list[DuplicateAction], list[DuplicateAction]]:
    """상태와 blocker risk 기준으로 FE 버튼 노출 힌트를 만든다."""

    blocker = has_blocker(flags)
    all_actions: list[DuplicateAction] = ["confirm", "split", "reject", "draft_reply"]
    if status == "candidate":
        allowed: list[DuplicateAction] = ["split", "reject"]
        if not blocker:
            allowed.insert(0, "confirm")
        return allowed, [action for action in all_actions if action not in allowed]
    if status == "confirmed":
        allowed = ["split", "draft_reply"]
        return allowed, [action for action in all_actions if action not in allowed]
    return [], all_actions


def _recommendation_level(
    confidence: float,
    flags: list,
) -> DuplicateRecommendationLevel:
    if confidence < 0.55:
        return "weak"
    if has_blocker(flags) or flags:
        return "review"
    if confidence >= 0.78:
        return "strong"
    return "review"


def _average_breakdown(pair_results: list[DuplicateScoreResult]) -> dict[str, float]:
    if not pair_results:
        return {}
    keys = sorted({key for result in pair_results for key in result.breakdown})
    return {
        key: round(sum(result.breakdown.get(key, 0.0) for result in pair_results) / len(pair_results), 4)
        for key in keys
    }


def _aggregate_location_state(pair_results: list[DuplicateScoreResult]) -> DuplicateLocationState:
    order: list[DuplicateLocationState] = ["conflict", "ambiguous", "missing", "nearby", "exact"]
    states = {result.location_state for result in pair_results}
    for state in order:
        if state in states:
            return state
    return "missing"


def _merge_id(ids) -> str:
    key = "|".join(sorted(str(item) for item in ids))
    return "dup-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _dedupe_evidence(items: list[DuplicateEvidence]) -> list[DuplicateEvidence]:
    result: list[DuplicateEvidence] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    for item in items:
        key = (item.type, tuple(sorted(item.affected_case_ids)), str(item.value))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _complete_pair_results(
    events: list[ComplaintIntelligenceEvent],
    pair_results: list[DuplicateScoreResult],
) -> list[DuplicateScoreResult]:
    results = {tuple(sorted(result.case_ids)): result for result in pair_results}
    sorted_events = sorted(events, key=lambda item: item.id)
    for index, left in enumerate(sorted_events):
        for right in sorted_events[index + 1:]:
            key = tuple(sorted((left.id, right.id)))
            if key not in results:
                results[key] = score_duplicate_pair(left, right)
    return list(results.values())


def _time_delta_hours(left: datetime, right: datetime) -> float:
    left_value = _as_aware(left)
    right_value = _as_aware(right)
    return abs((left_value - right_value).total_seconds()) / 3600


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

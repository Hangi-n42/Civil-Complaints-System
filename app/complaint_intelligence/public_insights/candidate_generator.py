"""공공기관 인사이트 후보 생성기."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.complaint_intelligence.config import (
    ComplaintIntelligenceConfig,
    get_complaint_intelligence_config,
)
from app.complaint_intelligence.embedding import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    average_vectors,
    cosine_similarity,
)
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicInsightType,
)


@dataclass(frozen=True)
class PublicInsightCandidate:
    """LLM 합성 전 단계의 결정적 후보."""

    candidate_id: str
    type_hint: PublicInsightType
    topic_label: str
    event_ids: list[str]
    complaint_ids: list[str]
    linked_alert_ids: list[str]
    region_key: str | None
    department_key: str | None
    window_start: datetime
    window_end: datetime
    trigger_metrics: dict[str, float | int | str]
    trigger_reason: str


@dataclass
class _Cluster:
    """후보 생성을 위한 의미 군집."""

    events: list[ComplaintIntelligenceEvent]
    vectors: list[list[float]]
    centroid: list[float]

    def add(self, event: ComplaintIntelligenceEvent, vector: list[float]) -> None:
        self.events.append(event)
        self.vectors.append(vector)
        self.centroid = average_vectors(self.vectors)


class PublicInsightCandidateGenerator:
    """키워드/군집/급증/운영 상태를 분석해 인사이트 후보를 만든다."""

    TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
        "도로 침하": ("싱크홀", "침하", "꺼짐", "구멍", "포트홀", "아스팔트", "도로", "움푹"),
        "대형폐기물 배출": ("대형폐기물", "배출", "스티커", "수거", "신청"),
        "불법주정차": ("불법주정차", "주정차", "불법주차", "주차", "단속", "차량"),
        "공공자전거 이용": ("공공자전거", "자전거", "예약", "대여", "앱", "결제"),
        "복지 지원": ("복지", "지원", "급여", "자격", "대상", "필요서류"),
        "가로등/보안등": ("가로등", "보안등", "조명", "고장", "점멸"),
        "악취/소음": ("악취", "냄새", "소음", "진동", "공장", "산업단지"),
    }
    SAFETY_KEYWORDS = ("싱크홀", "침하", "꺼짐", "위험", "붕괴", "침수", "감전", "화재", "사고", "구멍", "움푹", "내려앉", "아스팔트")
    FACILITY_KEYWORDS = ("도로", "가로등", "보안등", "하수", "공원", "공공시설", "파손", "고장", "침하", "구멍", "움푹", "내려앉", "아스팔트")
    ENFORCEMENT_KEYWORDS = ("불법주정차", "불법주차", "소음", "무단투기", "불법영업", "단속")
    GUIDANCE_KEYWORDS = ("문의", "방법", "신청", "서류", "필요서류", "어디", "어떻게", "기준", "안내")
    POLICY_KEYWORDS = ("제도", "기준", "요금", "지원", "완화", "확대", "절차", "개선")
    SERVICE_DESIGN_KEYWORDS = ("앱", "예약", "대여", "접수", "결제", "이용 절차", "오류", "로그인")
    ACCESSIBILITY_KEYWORDS = ("고령자", "장애인", "외국인", "접근성", "복잡", "어려움", "디지털")
    COMMUNICATION_KEYWORDS = ("진행", "상태", "담당", "부서", "기간", "언제", "왜", "연락")
    REPEAT_KEYWORDS = ("재민원", "반복", "다시", "또", "계속", "불만족", "반려", "재문의")
    OPEN_STATUSES = {"접수", "처리중", "진행중", "open", "pending", "in_progress", "delayed", "지연"}
    CLOSED_STATUSES = {"완료", "처리완료", "종결", "closed", "resolved", "done"}

    def __init__(
        self,
        config: ComplaintIntelligenceConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.config = config or get_complaint_intelligence_config()
        self.embedding_provider = embedding_provider or FakeEmbeddingProvider()

    def generate(
        self,
        events: list[ComplaintIntelligenceEvent],
        issue_alerts: list[IssueAlert] | None = None,
        now: datetime | None = None,
    ) -> list[PublicInsightCandidate]:
        """분석 이벤트와 이슈 경보에서 공공기관 인사이트 후보를 생성한다."""

        reference_time = _reference_time(events, issue_alerts or [], now)
        window_start = reference_time - timedelta(days=self.config.public_insight_analysis_window_days)
        window_events = [
            event for event in events if window_start <= _as_aware(event.received_at) <= reference_time
        ]
        candidates: list[PublicInsightCandidate] = []
        candidates.extend(self._alert_candidates(issue_alerts or [], window_start, reference_time))

        clusters = self._semantic_clusters(window_events)
        for cluster in clusters:
            candidates.extend(self._cluster_candidates(cluster.events, window_start, reference_time))
        candidates.extend(self._keyword_group_candidates(window_events, window_start, reference_time))
        candidates.extend(self._department_candidates(window_events, window_start, reference_time))
        candidates.extend(self._delay_candidates(window_events, window_start, reference_time))

        deduped: dict[str, PublicInsightCandidate] = {}
        for candidate in candidates:
            deduped[candidate.candidate_id] = candidate
        return list(deduped.values())

    def _alert_candidates(
        self,
        alerts: list[IssueAlert],
        window_start: datetime,
        window_end: datetime,
    ) -> list[PublicInsightCandidate]:
        candidates: list[PublicInsightCandidate] = []
        for alert in alerts:
            text = " ".join([alert.topic, alert.summary, " ".join(alert.keywords)])
            insight_type: PublicInsightType = "SAFETY_RISK_SIGNAL" if _contains_any(text, self.SAFETY_KEYWORDS) else "HOTSPOT_RESPONSE_REQUIRED"
            metrics = {
                "complaint_count": alert.recent_count,
                "surge_ratio": alert.surge_ratio,
                "baseline_count": alert.baseline,
                "alert_confidence": alert.confidence,
            }
            candidates.append(
                self._candidate(
                    insight_type=insight_type,
                    events=[],
                    topic_label=alert.topic,
                    region_key=alert.region,
                    department_key=None,
                    window_start=window_start,
                    window_end=window_end,
                    trigger_metrics=metrics,
                    trigger_reason="IssueAlert 기반 급증/위험 후보입니다.",
                    linked_alert_ids=[alert.id],
                    complaint_ids=sorted(alert.related_ids),
                )
            )
        return candidates

    def _cluster_candidates(
        self,
        events: list[ComplaintIntelligenceEvent],
        window_start: datetime,
        window_end: datetime,
    ) -> list[PublicInsightCandidate]:
        if len(events) < self.config.public_insight_min_candidate_complaint_count:
            return []

        text = _joined_text(events)
        topic = self._infer_topic(events)
        region = _dominant_region(events)
        candidates: list[PublicInsightCandidate] = [
            self._candidate(
                insight_type="RECURRING_COMPLAINT_PATTERN",
                events=events,
                topic_label=topic,
                region_key=region,
                department_key=None,
                window_start=window_start,
                window_end=window_end,
                trigger_metrics={"complaint_count": len(events), "distinct_days": _distinct_days(events)},
                trigger_reason="같은 주제의 민원이 분석 기간 내 반복되었습니다.",
            )
        ]

        if region:
            candidates.append(
                self._candidate(
                    insight_type="REGIONAL_SERVICE_GAP",
                    events=events,
                    topic_label=topic,
                    region_key=region,
                    department_key=None,
                    window_start=window_start,
                    window_end=window_end,
                    trigger_metrics={"complaint_count": len(events), "regional_concentration": _region_share(events, region)},
                    trigger_reason="특정 지역에서 같은 주제의 민원이 집중되었습니다.",
                )
            )
        if _contains_any(text, self.SAFETY_KEYWORDS):
            candidates.append(self._keyword_candidate("SAFETY_RISK_SIGNAL", events, topic, region, window_start, window_end, "안전 위험 표현이 반복되었습니다."))
        if _contains_any(text, self.GUIDANCE_KEYWORDS):
            candidates.append(self._keyword_candidate("PUBLIC_GUIDANCE_NEEDED", events, topic, region, window_start, window_end, "신청/방법/서류/기준 안내 요구가 반복되었습니다."))
        if _contains_any(text, self.FACILITY_KEYWORDS):
            candidates.append(self._keyword_candidate("FACILITY_MAINTENANCE_PRIORITY", events, topic, region, window_start, window_end, "시설 파손 또는 유지보수 민원이 반복되었습니다."))
        if _contains_any(text, self.ENFORCEMENT_KEYWORDS):
            candidates.append(self._keyword_candidate("ENFORCEMENT_PRIORITY", events, topic, region, window_start, window_end, "단속 또는 점검 요구가 반복되었습니다."))
        if _contains_any(text, self.POLICY_KEYWORDS):
            candidates.append(self._keyword_candidate("POLICY_IMPROVEMENT_OPPORTUNITY", events, topic, region, window_start, window_end, "제도/기준/절차 개선 요구가 반복되었습니다."))
        if _contains_any(text, self.SERVICE_DESIGN_KEYWORDS):
            candidates.append(self._keyword_candidate("SERVICE_DESIGN_IMPROVEMENT", events, topic, region, window_start, window_end, "공공 서비스 이용 절차 불편이 반복되었습니다."))
        if _contains_any(text, self.ACCESSIBILITY_KEYWORDS):
            candidates.append(self._keyword_candidate("ACCESSIBILITY_OR_USABILITY_ISSUE", events, topic, region, window_start, window_end, "접근성 또는 사용성 불편이 반복되었습니다."))
        if _contains_any(text, self.COMMUNICATION_KEYWORDS):
            candidates.append(self._keyword_candidate("CITIZEN_COMMUNICATION_GAP", events, topic, region, window_start, window_end, "처리 기준/상태/부서/기간 이해 어려움이 반복되었습니다."))
        if self._night_share(events) >= 0.6:
            candidates.append(self._keyword_candidate("SEASONAL_OR_TIME_PATTERN", events, topic, region, window_start, window_end, "특정 시간대 접수 비율이 높습니다."))

        repeat_events = [
            event for event in events
            if event.reopened or _contains_any(_analysis_text(event), self.REPEAT_KEYWORDS) or _clean(event.status) in {"재접수", "재민원", "reopened"}
        ]
        if len(repeat_events) >= self.config.repeat_risk_count:
            candidates.append(
                self._candidate(
                    insight_type="REOPEN_OR_REPEAT_RISK",
                    events=repeat_events,
                    topic_label=topic,
                    region_key=region,
                    department_key=None,
                    window_start=window_start,
                    window_end=window_end,
                    trigger_metrics={"repeat_count": len(repeat_events), "cluster_count": len(events)},
                    trigger_reason="재민원/반복/불만족 표현이 같은 주제에서 반복되었습니다.",
                )
            )
        return candidates

    def _keyword_group_candidates(
        self,
        events: list[ComplaintIntelligenceEvent],
        window_start: datetime,
        window_end: datetime,
    ) -> list[PublicInsightCandidate]:
        """의미 클러스터가 작게 갈라져도 행정 주제 반복 신호는 후보로 보강한다."""

        keyword_rules: list[tuple[PublicInsightType, tuple[str, ...], str]] = [
            ("SAFETY_RISK_SIGNAL", self.SAFETY_KEYWORDS, "안전 위험 표현이 분석 기간 안에서 반복되었습니다."),
            ("PUBLIC_GUIDANCE_NEEDED", self.GUIDANCE_KEYWORDS, "신청/방법/서류/기준 안내 요구가 반복되었습니다."),
            ("FACILITY_MAINTENANCE_PRIORITY", self.FACILITY_KEYWORDS, "시설 파손 또는 유지보수 민원이 반복되었습니다."),
            ("ENFORCEMENT_PRIORITY", self.ENFORCEMENT_KEYWORDS, "단속 또는 점검 요구가 반복되었습니다."),
            ("POLICY_IMPROVEMENT_OPPORTUNITY", self.POLICY_KEYWORDS, "제도/기준/절차 개선 요구가 반복되었습니다."),
            ("SERVICE_DESIGN_IMPROVEMENT", self.SERVICE_DESIGN_KEYWORDS, "공공 서비스 이용 절차 불편이 반복되었습니다."),
            ("ACCESSIBILITY_OR_USABILITY_ISSUE", self.ACCESSIBILITY_KEYWORDS, "접근성 또는 사용성 불편이 반복되었습니다."),
            ("CITIZEN_COMMUNICATION_GAP", self.COMMUNICATION_KEYWORDS, "처리 기준/상태/담당 부서 소통 요구가 반복되었습니다."),
        ]

        candidates: list[PublicInsightCandidate] = []
        min_count = self.config.public_insight_min_candidate_complaint_count
        for insight_type, keywords, reason in keyword_rules:
            matched = [event for event in events if _contains_any(_analysis_text(event), keywords)]
            if len(matched) < min_count:
                continue
            candidates.append(
                self._keyword_candidate(
                    insight_type=insight_type,
                    events=matched,
                    topic=self._infer_topic(matched),
                    region=_dominant_region(matched),
                    window_start=window_start,
                    window_end=window_end,
                    reason=reason,
                )
            )
        return candidates

    def _department_candidates(
        self,
        events: list[ComplaintIntelligenceEvent],
        window_start: datetime,
        window_end: datetime,
    ) -> list[PublicInsightCandidate]:
        by_department: dict[str, list[ComplaintIntelligenceEvent]] = {}
        for event in events:
            department = _clean(event.final_department)
            if department:
                by_department.setdefault(department, []).append(event)

        candidates: list[PublicInsightCandidate] = []
        for department, department_events in by_department.items():
            open_count = sum(1 for event in department_events if _is_open_status(event.status, self.OPEN_STATUSES, self.CLOSED_STATUSES))
            if len(department_events) < self.config.department_bottleneck_min_count and open_count < self.config.department_bottleneck_min_count:
                continue
            candidates.append(
                self._candidate(
                    insight_type="DEPARTMENT_WORKLOAD_BOTTLENECK",
                    events=department_events,
                    topic_label="부서 처리량",
                    region_key=_dominant_region(department_events),
                    department_key=department,
                    window_start=window_start,
                    window_end=window_end,
                    trigger_metrics={"complaint_count": len(department_events), "open_count": open_count},
                    trigger_reason="특정 부서 담당 민원과 미완료 건이 누적되었습니다.",
                )
            )
        return candidates

    def _delay_candidates(
        self,
        events: list[ComplaintIntelligenceEvent],
        window_start: datetime,
        window_end: datetime,
    ) -> list[PublicInsightCandidate]:
        delayed = [
            event for event in events
            if _is_delayed(event, window_end, self.config.public_insight_process_delay_minutes_threshold, self.OPEN_STATUSES, self.CLOSED_STATUSES)
        ]
        if len(delayed) < self.config.public_insight_min_candidate_complaint_count:
            return []
        avg_minutes = sum(_handling_minutes(event, window_end) for event in delayed) / len(delayed)
        return [
            self._candidate(
                insight_type="PROCESS_DELAY_RISK",
                events=delayed,
                topic_label="처리 지연",
                region_key=_dominant_region(delayed),
                department_key=_dominant_department(delayed),
                window_start=window_start,
                window_end=window_end,
                trigger_metrics={"delayed_count": len(delayed), "avg_handling_time_minutes": round(avg_minutes, 2)},
                trigger_reason="처리 지연 기준을 넘는 민원이 누적되었습니다.",
            )
        ]

    def _keyword_candidate(
        self,
        insight_type: PublicInsightType,
        events: list[ComplaintIntelligenceEvent],
        topic: str,
        region: str | None,
        window_start: datetime,
        window_end: datetime,
        reason: str,
    ) -> PublicInsightCandidate:
        return self._candidate(
            insight_type=insight_type,
            events=events,
            topic_label=topic,
            region_key=region,
            department_key=_dominant_department(events),
            window_start=window_start,
            window_end=window_end,
            trigger_metrics={"complaint_count": len(events), "keyword_count": _keyword_count(events)},
            trigger_reason=reason,
        )

    def _candidate(
        self,
        insight_type: PublicInsightType,
        events: list[ComplaintIntelligenceEvent],
        topic_label: str,
        region_key: str | None,
        department_key: str | None,
        window_start: datetime,
        window_end: datetime,
        trigger_metrics: dict[str, float | int | str],
        trigger_reason: str,
        linked_alert_ids: list[str] | None = None,
        complaint_ids: list[str] | None = None,
    ) -> PublicInsightCandidate:
        ids = sorted(complaint_ids or [event.id for event in events])
        seed = "|".join([insight_type, topic_label, region_key or "", department_key or "", ",".join(ids[:20]), ",".join(linked_alert_ids or [])])
        return PublicInsightCandidate(
            candidate_id="candidate-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12],
            type_hint=insight_type,
            topic_label=topic_label,
            event_ids=ids,
            complaint_ids=ids,
            linked_alert_ids=linked_alert_ids or [],
            region_key=region_key,
            department_key=department_key,
            window_start=window_start,
            window_end=window_end,
            trigger_metrics=trigger_metrics,
            trigger_reason=trigger_reason,
        )

    def _semantic_clusters(self, events: list[ComplaintIntelligenceEvent]) -> list[_Cluster]:
        vectors = self._event_vectors(events)
        clusters: list[_Cluster] = []
        for event in sorted(events, key=lambda item: _as_aware(item.received_at)):
            vector = vectors[event.id]
            best: _Cluster | None = None
            best_similarity = 0.0
            for cluster in clusters:
                similarity = cosine_similarity(vector, cluster.centroid)
                if similarity >= self.config.semantic_threshold and similarity > best_similarity:
                    best = cluster
                    best_similarity = similarity
            if best is None:
                clusters.append(_Cluster(events=[event], vectors=[vector], centroid=vector))
            else:
                best.add(event, vector)
        return clusters

    def _event_vectors(self, events: list[ComplaintIntelligenceEvent]) -> dict[str, list[float]]:
        texts = [_analysis_text(event) for event in events]
        return {event.id: vector for event, vector in zip(events, self.embedding_provider.embed(texts))}

    def _infer_topic(self, events: list[ComplaintIntelligenceEvent]) -> str:
        text = _joined_text(events)
        best_topic = "반복 민원"
        best_count = 0
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            count = sum(1 for keyword in keywords if keyword in text)
            if count > best_count:
                best_topic = topic
                best_count = count
        return best_topic

    def _night_share(self, events: list[ComplaintIntelligenceEvent]) -> float:
        if not events:
            return 0.0
        night_count = sum(1 for event in events if _is_night(_as_aware(event.received_at).hour, self.config.night_start_hour, self.config.night_end_hour))
        return night_count / len(events)


def _reference_time(events: list[ComplaintIntelligenceEvent], alerts: list[IssueAlert], now: datetime | None) -> datetime:
    if now is not None:
        return _as_aware(now)
    candidates = [_as_aware(event.received_at) for event in events]
    candidates.extend(_as_aware(alert.last_seen) for alert in alerts)
    return max(candidates) if candidates else datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _joined_text(events: list[ComplaintIntelligenceEvent]) -> str:
    return " ".join(_analysis_text(event) for event in events)


def _analysis_text(event: ComplaintIntelligenceEvent) -> str:
    texts: list[str] = []
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element is not None and element.text.strip():
            texts.append(element.text)
    if event.masked_text:
        texts.append(event.masked_text)
    return " ".join(texts)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _keyword_count(events: list[ComplaintIntelligenceEvent]) -> int:
    return len([token for event in events for token in _analysis_text(event).split() if len(token) >= 2])


def _distinct_days(events: list[ComplaintIntelligenceEvent]) -> int:
    return len({_as_aware(event.received_at).date().isoformat() for event in events})


def _dominant_region(events: list[ComplaintIntelligenceEvent]) -> str | None:
    counts: dict[str, int] = {}
    for event in events:
        region = _clean(event.region)
        if region:
            counts[region] = counts.get(region, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def _dominant_department(events: list[ComplaintIntelligenceEvent]) -> str | None:
    counts: dict[str, int] = {}
    for event in events:
        department = _clean(event.final_department)
        if department:
            counts[department] = counts.get(department, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def _region_share(events: list[ComplaintIntelligenceEvent], region: str) -> float:
    if not events:
        return 0.0
    return sum(1 for event in events if _clean(event.region) == region) / len(events)


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _is_open_status(status: str | None, open_statuses: set[str], closed_statuses: set[str]) -> bool:
    value = _clean(status).lower()
    if not value:
        return False
    if value in closed_statuses:
        return False
    return value in open_statuses or value not in closed_statuses


def _handling_minutes(event: ComplaintIntelligenceEvent, now: datetime) -> float:
    if event.handling_time_minutes is not None:
        return float(event.handling_time_minutes)
    return max(0.0, (now - _as_aware(event.received_at)).total_seconds() / 60)


def _is_delayed(
    event: ComplaintIntelligenceEvent,
    now: datetime,
    threshold_minutes: int,
    open_statuses: set[str],
    closed_statuses: set[str],
) -> bool:
    return _is_open_status(event.status, open_statuses, closed_statuses) and _handling_minutes(event, now) >= threshold_minutes


def _is_night(hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return False
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour

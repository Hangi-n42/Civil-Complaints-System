"""민원 급증 이슈를 감지하는 sidecar 엔진."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

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
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    RepresentativeComplaint,
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")
_UNKNOWN_REGIONS = {"", "미상", "unknown", "UNKNOWN", "지역미상", "N/A", "None"}


@dataclass
class _Cluster:
    """최근 민원 묶음과 중심 벡터를 보관한다."""

    events: list[ComplaintIntelligenceEvent]
    vectors: list[list[float]]
    centroid: list[float]

    def add(self, event: ComplaintIntelligenceEvent, vector: list[float]) -> None:
        self.events.append(event)
        self.vectors.append(vector)
        self.centroid = average_vectors(self.vectors)


class IssueDetectionEngine:
    """masked text 기반으로 의미/공간/기준선 급증을 결합해 경보를 만든다."""

    _CONCRETE_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("대형폐기물 배출 안내", ("대형폐기물", "스티커", "배출", "수거", "신청", "방법", "안내")),
        ("야간 하수 악취", ("악취", "냄새", "하수", "야간", "밤", "새벽")),
        ("공공자전거 예약/대여 불편", ("공공자전거", "자전거", "예약", "대여", "결제", "앱", "오류")),
        ("초등학교 앞 불법주정차", ("초등학교", "학교 앞", "불법주정차", "불법주차", "주정차", "단속")),
        ("가로등/보안등 고장", ("가로등", "보안등", "꺼짐", "고장", "조명", "어두움")),
        ("공사 소음 시간대 집중", ("공사", "소음", "새벽", "야간", "주말", "진동")),
        ("도로 침하/싱크홀 위험", ("싱크홀", "침하", "꺼짐", "구멍", "아스팔트", "도로", "움푹")),
        ("복지 지원 신청/기준 안내", ("복지", "지원", "신청", "기준", "자격", "서류")),
    )
    _TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
        "도로침하": ("싱크홀", "침하", "꺼짐", "구멍", "포트홀", "아스팔트", "도로", "움푹", "내려앉"),
        "쓰레기": ("쓰레기", "폐기물", "무단투기", "청소", "악취"),
        "주정차": ("주정차", "불법주정차", "주차", "단속", "차량"),
        "가로등": ("가로등", "보안등", "조명", "고장", "점멸"),
        "소음": ("소음", "진동", "공사", "층간"),
        "복지": ("복지", "지원", "급여", "생활비", "노인"),
    }
    _RISK_KEYWORDS = ("싱크홀", "침하", "꺼짐", "구멍", "위험", "파손", "균열", "누수", "침수", "화재", "사고", "움푹", "내려앉")
    _UX_KEYWORDS = ("공공자전거", "자전거", "앱", "예약", "대여", "결제", "오류", "로그인")
    _ACCESSIBILITY_KEYWORDS = ("고령자", "장애인", "외국인", "디지털", "취약계층", "접근성", "어려움", "복잡", "글씨")
    _REPEAT_KEYWORDS = ("재민원", "반복", "다시", "재발", "계속", "여러 번", "불만")
    _OPEN_STATUSES = {"접수", "처리중", "진행중", "open", "pending", "in_progress", "delayed", "지연"}
    _CLOSED_STATUSES = {"완료", "처리완료", "종결", "closed", "resolved", "done"}

    def __init__(
        self,
        config: ComplaintIntelligenceConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.config = config or get_complaint_intelligence_config()
        self.embedding_provider = embedding_provider or FakeEmbeddingProvider()

    def detect(
        self,
        events: list[ComplaintIntelligenceEvent],
        active_alerts: list[IssueAlert] | None = None,
    ) -> list[IssueAlert]:
        """최근 N시간 민원 중 기준선 대비 급증한 클러스터만 경보로 반환한다."""

        if not events:
            return []

        vectors = self._event_vectors(events)
        reference_time = max(_as_aware(event.received_at) for event in events)
        recent_start = reference_time - timedelta(hours=self.config.recent_hours)
        recent_events = [
            event for event in events if recent_start <= _as_aware(event.received_at) <= reference_time
        ]
        clusters = self._build_recent_clusters(recent_events, vectors)
        active_by_id = {
            alert.id: alert for alert in active_alerts or [] if alert.status in {"ACTIVE", "UPDATED"}
        }

        alerts: list[IssueAlert] = []
        for cluster in clusters:
            if len(cluster.events) < self.config.min_recent_count:
                continue

            baseline = self._baseline_average(cluster, events, vectors, reference_time, recent_start)
            surge_ratio = len(cluster.events) / max(baseline, 1.0)
            if surge_ratio < self.config.min_surge_ratio:
                continue

            confidence, parts = self._score_cluster(cluster, surge_ratio)
            severity = self._severity(confidence)
            if severity is None:
                continue

            alert = self._build_alert(cluster, baseline, surge_ratio, confidence, severity, parts)
            if alert.id in active_by_id:
                alert = self._merge_active_alert(active_by_id[alert.id], alert)
            alerts.append(alert)

        for alert in self._operational_alerts(recent_events, reference_time, recent_start):
            if alert.id in active_by_id:
                alert = self._merge_active_alert(active_by_id[alert.id], alert)
            alerts.append(alert)

        return sorted(_dedupe_alerts(alerts), key=lambda item: item.confidence, reverse=True)

    def _event_vectors(self, events: list[ComplaintIntelligenceEvent]) -> dict[str, list[float]]:
        # 외부 embedding 필드가 있어도 sidecar는 마스킹된 텍스트만 임베딩 입력으로 사용한다.
        texts = [_analysis_text(event) for event in events]
        return {
            event.id: vector
            for event, vector in zip(events, self.embedding_provider.embed(texts))
        }

    def _build_recent_clusters(
        self,
        events: list[ComplaintIntelligenceEvent],
        vectors: dict[str, list[float]],
    ) -> list[_Cluster]:
        clusters: list[_Cluster] = []
        for event in sorted(events, key=lambda item: _as_aware(item.received_at)):
            vector = vectors[event.id]
            best_cluster: _Cluster | None = None
            best_similarity = 0.0

            for cluster in clusters:
                similarity = cosine_similarity(vector, cluster.centroid)
                if similarity < self.config.semantic_threshold:
                    continue
                if not _region_compatible(event.region, _cluster_region(cluster.events)):
                    continue
                if similarity > best_similarity:
                    best_cluster = cluster
                    best_similarity = similarity

            if best_cluster is None:
                clusters.append(_Cluster(events=[event], vectors=[vector], centroid=vector))
            else:
                best_cluster.add(event, vector)
        return clusters

    def _baseline_average(
        self,
        cluster: _Cluster,
        events: list[ComplaintIntelligenceEvent],
        vectors: dict[str, list[float]],
        reference_time: datetime,
        recent_start: datetime,
    ) -> float:
        baseline_start = reference_time - timedelta(days=self.config.baseline_days)
        region = _cluster_region(cluster.events)
        older_count = 0
        for event in events:
            received_at = _as_aware(event.received_at)
            if not (baseline_start <= received_at < recent_start):
                continue
            if not _region_compatible(event.region, region):
                continue
            if cosine_similarity(vectors[event.id], cluster.centroid) >= self.config.semantic_threshold:
                older_count += 1
        return older_count / max(self.config.baseline_days, 1)

    def _score_cluster(self, cluster: _Cluster, surge_ratio: float) -> tuple[float, dict[str, float]]:
        recent_count = len(cluster.events)
        count_score = min(1.0, recent_count / max(self.config.min_recent_count, 1))
        surge_score = min(1.0, surge_ratio / max(self.config.min_surge_ratio, 1.0))
        cohesion = _average_centroid_similarity(cluster.vectors, cluster.centroid)
        spatial = _spatial_score(cluster.events)
        risk = 1.0 if any(self._contains_risk_keyword(event.masked_text) for event in cluster.events) else 0.0

        score = (
            self.config.score_weight_count * count_score
            + self.config.score_weight_surge * surge_score
            + self.config.score_weight_cohesion * cohesion
            + self.config.score_weight_spatial * spatial
            + self.config.score_weight_risk * risk
        )
        parts = {
            "count": round(count_score, 4),
            "surge": round(surge_score, 4),
            "cohesion": round(cohesion, 4),
            "spatial": round(spatial, 4),
            "risk_keyword": round(risk, 4),
        }
        return round(min(1.0, max(0.0, score)), 4), parts

    def _severity(self, score: float) -> str | None:
        if score >= self.config.critical_threshold:
            return "CRITICAL"
        if score >= self.config.warning_threshold:
            return "WARNING"
        if score >= self.config.watch_threshold:
            return "WATCH"
        return None

    def _build_alert(
        self,
        cluster: _Cluster,
        baseline: float,
        surge_ratio: float,
        confidence: float,
        severity: str,
        parts: dict[str, float],
    ) -> IssueAlert:
        topic = self._infer_topic(cluster.events)
        region = _cluster_region(cluster.events)
        related_ids = sorted(event.id for event in cluster.events)
        first_seen = min(_as_aware(event.received_at) for event in cluster.events)
        last_seen = max(_as_aware(event.received_at) for event in cluster.events)
        keywords = self._extract_keywords(cluster.events)
        alert_id = self._alert_id(topic, region)
        representative_complaints = [
            RepresentativeComplaint(
                id=event.id,
                masked_text=mask_pii(event.masked_text[:180]).text,
                region=event.region,
                received_at=_as_aware(event.received_at),
            )
            for event in sorted(cluster.events, key=lambda item: _as_aware(item.received_at), reverse=True)[:3]
        ]
        region_label = region or "지역 미상"

        return IssueAlert(
            id=alert_id,
            severity=severity,
            trigger_type="SURGE_HOTSPOT",
            title=f"{region_label} {topic} 민원 급증",
            summary=(
                f"최근 {self.config.recent_hours}시간 동안 {len(cluster.events)}건이 접수되었고 "
                f"7일 기준선 대비 {surge_ratio:.1f}배 증가했습니다."
            ),
            topic=topic,
            keywords=keywords,
            region=region,
            center=_center(cluster.events),
            radius=_radius_km(cluster.events),
            recent_count=len(cluster.events),
            baseline=round(baseline, 4),
            surge_ratio=round(surge_ratio, 4),
            first_seen=first_seen,
            last_seen=last_seen,
            representative_complaints=representative_complaints,
            related_ids=related_ids,
            confidence=confidence,
            explanation=(
                "score=.30*count+.25*surge+.20*cohesion+.15*spatial+.10*risk_keyword, "
                f"parts={parts}"
            ),
        )

    def _merge_active_alert(self, active: IssueAlert, incoming: IssueAlert) -> IssueAlert:
        related_ids = sorted(set(active.related_ids) | set(incoming.related_ids))
        representatives = {item.id: item for item in active.representative_complaints}
        representatives.update({item.id: item for item in incoming.representative_complaints})
        incoming.status = "UPDATED"
        incoming.first_seen = min(_as_aware(active.first_seen), _as_aware(incoming.first_seen))
        incoming.last_seen = max(_as_aware(active.last_seen), _as_aware(incoming.last_seen))
        incoming.related_ids = related_ids
        incoming.representative_complaints = list(representatives.values())[:3]
        incoming.linked_insight_ids = sorted(set(active.linked_insight_ids) | set(incoming.linked_insight_ids))
        return incoming

    def _infer_topic(self, events: Iterable[ComplaintIntelligenceEvent]) -> str:
        text = " ".join(_analysis_text(event) for event in events)
        concrete_topic = _best_concrete_topic(text, self._CONCRETE_TOPIC_RULES)
        if concrete_topic:
            return concrete_topic
        best_topic = "반복 민원"
        best_count = 0
        for topic, keywords in self._TOPIC_KEYWORDS.items():
            count = sum(1 for keyword in keywords if keyword in text)
            if count > best_count:
                best_topic = topic
                best_count = count
        return best_topic

    def _extract_keywords(self, events: Iterable[ComplaintIntelligenceEvent]) -> list[str]:
        text = " ".join(_analysis_text(event) for event in events)
        selected: list[str] = []
        for _topic, keywords in self._CONCRETE_TOPIC_RULES:
            for keyword in keywords:
                if keyword in text and keyword not in selected:
                    selected.append(keyword)
        for keywords in self._TOPIC_KEYWORDS.values():
            for keyword in keywords:
                if keyword in text and keyword not in selected:
                    selected.append(keyword)
        if selected:
            return selected[:8]

        tokens: dict[str, int] = {}
        for token in _TOKEN_RE.findall(text):
            if token.startswith("REDACTED") or len(token) < 2:
                continue
            tokens[token] = tokens.get(token, 0) + 1
        return [token for token, _ in sorted(tokens.items(), key=lambda item: item[1], reverse=True)[:8]]

    def _contains_risk_keyword(self, text: str) -> bool:
        return any(keyword in text for keyword in self._RISK_KEYWORDS)

    def _operational_alerts(
        self,
        recent_events: list[ComplaintIntelligenceEvent],
        reference_time: datetime,
        recent_start: datetime,
    ) -> list[IssueAlert]:
        """급증 클러스터가 약한 운영 신호를 보수적으로 alert로 승격한다."""

        alerts: list[IssueAlert] = []
        alerts.extend(self._backlog_alerts(recent_events, reference_time, recent_start))
        alerts.extend(self._repeat_alerts(recent_events, reference_time, recent_start))
        alerts.extend(
            self._keyword_operational_alerts(
                recent_events,
                reference_time,
                recent_start,
                topic="공공자전거 예약/대여 불편",
                keywords=self._UX_KEYWORDS,
                trigger_type="SERVICE_UX_PATTERN",
            )
        )
        alerts.extend(
            self._keyword_operational_alerts(
                recent_events,
                reference_time,
                recent_start,
                topic="접근성/사용성 반복 불편",
                keywords=self._ACCESSIBILITY_KEYWORDS,
                trigger_type="SERVICE_ACCESSIBILITY_PATTERN",
            )
        )
        return alerts

    def _backlog_alerts(
        self,
        recent_events: list[ComplaintIntelligenceEvent],
        reference_time: datetime,
        recent_start: datetime,
    ) -> list[IssueAlert]:
        by_department: dict[str, list[ComplaintIntelligenceEvent]] = {}
        for event in recent_events:
            if not _is_open_status(event.status, self._OPEN_STATUSES, self._CLOSED_STATUSES):
                continue
            if event.handling_time_minutes is None:
                continue
            if float(event.handling_time_minutes) < self.config.public_insight_process_delay_minutes_threshold:
                continue
            department = " ".join(str(event.final_department or "담당 부서 미상").split())
            by_department.setdefault(department, []).append(event)

        alerts: list[IssueAlert] = []
        threshold = max(self.config.min_recent_count, self.config.department_bottleneck_min_count)
        for department, events in by_department.items():
            if len(events) < threshold:
                continue
            avg_minutes = sum(float(event.handling_time_minutes or 0.0) for event in events) / len(events)
            alerts.append(
                self._build_operational_alert(
                    events,
                    topic=f"{department} 처리 지연/미처리 누적",
                    reference_time=reference_time,
                    recent_start=recent_start,
                    trigger_type="OPERATIONAL_BACKLOG",
                    confidence=0.86,
                    severity="WARNING",
                    explanation=(
                        f"open/pending 상태와 처리시간 기준 초과가 {len(events)}건 누적, "
                        f"avg_handling_time_minutes={avg_minutes:.1f}"
                    ),
                )
            )
        return alerts

    def _repeat_alerts(
        self,
        recent_events: list[ComplaintIntelligenceEvent],
        reference_time: datetime,
        recent_start: datetime,
    ) -> list[IssueAlert]:
        repeat_events = [
            event for event in recent_events
            if event.reopened
            or _contains_any(_analysis_text(event), self._REPEAT_KEYWORDS)
            or (event.user_feedback_score is not None and float(event.user_feedback_score) <= 2.0)
        ]
        if len(repeat_events) < max(self.config.min_recent_count, self.config.repeat_risk_count):
            return []
        return [
            self._build_operational_alert(
                repeat_events,
                topic="재민원/반복 민원 증가",
                reference_time=reference_time,
                recent_start=recent_start,
                trigger_type="REOPEN_REPEAT",
                confidence=0.84,
                severity="WARNING",
                explanation=f"reopened/반복/불만족 신호가 {len(repeat_events)}건 확인되었습니다.",
            )
        ]

    def _keyword_operational_alerts(
        self,
        recent_events: list[ComplaintIntelligenceEvent],
        reference_time: datetime,
        recent_start: datetime,
        *,
        topic: str,
        keywords: tuple[str, ...],
        trigger_type: str,
    ) -> list[IssueAlert]:
        matched = [event for event in recent_events if _contains_any(_analysis_text(event), keywords)]
        if len(matched) < self.config.min_recent_count:
            return []
        if _dominant_region_share(matched) < self.config.public_insight_regional_concentration_threshold:
            return []
        return [
            self._build_operational_alert(
                matched,
                topic=topic,
                reference_time=reference_time,
                recent_start=recent_start,
                trigger_type=trigger_type,
                confidence=0.82,
                severity="WARNING",
                explanation=f"{topic} 운영 신호가 {len(matched)}건 반복되었습니다.",
            )
        ]

    def _build_operational_alert(
        self,
        events: list[ComplaintIntelligenceEvent],
        *,
        topic: str,
        reference_time: datetime,
        recent_start: datetime,
        trigger_type: str,
        confidence: float,
        severity: str,
        explanation: str,
    ) -> IssueAlert:
        region = _cluster_region(events)
        first_seen = min(_as_aware(event.received_at) for event in events)
        last_seen = max(_as_aware(event.received_at) for event in events)
        baseline = _baseline_count(events, reference_time, recent_start)
        surge_ratio = len(events) / max(baseline, 1.0)
        representatives = [
            RepresentativeComplaint(
                id=event.id,
                masked_text=mask_pii(_analysis_text(event)[:180]).text,
                region=event.region,
                received_at=_as_aware(event.received_at),
            )
            for event in sorted(events, key=lambda item: _as_aware(item.received_at), reverse=True)[:3]
        ]
        region_label = region or "지역 미상"
        return IssueAlert(
            id=self._alert_id(topic, region),
            severity=severity,  # type: ignore[arg-type]
            trigger_type=trigger_type,  # type: ignore[arg-type]
            title=f"{region_label} {topic}",
            summary=f"최근 {self.config.recent_hours}시간 동안 {len(events)}건의 {topic} 신호가 관측되었습니다.",
            topic=topic,
            keywords=self._extract_keywords(events),
            region=region,
            center=_center(events),
            radius=_radius_km(events),
            recent_count=len(events),
            baseline=round(baseline, 4),
            surge_ratio=round(surge_ratio, 4),
            first_seen=first_seen,
            last_seen=last_seen,
            representative_complaints=representatives,
            related_ids=sorted(event.id for event in events),
            confidence=confidence,
            explanation=f"trigger_type={trigger_type}; {explanation}",
        )

    def _alert_id(self, topic: str, region: str | None) -> str:
        key = f"{topic}|{region or 'unknown'}"
        return "issue-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cluster_region(events: Iterable[ComplaintIntelligenceEvent]) -> str | None:
    counts: dict[str, int] = {}
    for event in events:
        region = _normalize_region(event.region)
        if region:
            counts[region] = counts.get(region, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def _normalize_region(region: str | None) -> str | None:
    value = " ".join(str(region or "").split())
    if value in _UNKNOWN_REGIONS:
        return None
    return value


def _region_compatible(left: str | None, right: str | None) -> bool:
    left_value = _normalize_region(left)
    right_value = _normalize_region(right)
    if not left_value or not right_value:
        return True
    if left_value == right_value:
        return True
    if left_value.startswith(right_value) or right_value.startswith(left_value):
        return True
    return len(left_value) >= 2 and len(right_value) >= 2 and left_value[:2] == right_value[:2]


def _analysis_text(event: ComplaintIntelligenceEvent) -> str:
    chunks: list[str] = []
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element is not None and element.text.strip():
            chunks.append(element.text)
    if event.masked_text:
        chunks.append(event.masked_text)
    return " ".join(chunks)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _best_concrete_topic(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    best_topic: str | None = None
    best_score = 0
    for topic, keywords in rules:
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_topic = topic
            best_score = score
    return best_topic if best_score >= 2 else None


def _baseline_count(
    events: list[ComplaintIntelligenceEvent],
    reference_time: datetime,
    recent_start: datetime,
) -> float:
    older = [
        event for event in events
        if _as_aware(event.received_at) < recent_start
        and _as_aware(event.received_at) >= reference_time - timedelta(days=7)
    ]
    return len(older) / 7 if older else 0.0


def _dominant_region_share(events: list[ComplaintIntelligenceEvent]) -> float:
    counts: dict[str, int] = {}
    for event in events:
        region = _normalize_region(event.region)
        if region:
            counts[region] = counts.get(region, 0) + 1
    if not counts:
        return 1.0
    return max(counts.values()) / len(events)


def _is_open_status(status: str | None, open_statuses: set[str], closed_statuses: set[str]) -> bool:
    value = " ".join(str(status or "").split()).lower()
    if not value:
        return False
    if value in closed_statuses:
        return False
    return value in open_statuses or value not in closed_statuses


def _dedupe_alerts(alerts: list[IssueAlert]) -> list[IssueAlert]:
    by_id: dict[str, IssueAlert] = {}
    for alert in alerts:
        current = by_id.get(alert.id)
        if current is None or (alert.confidence, alert.recent_count) > (current.confidence, current.recent_count):
            by_id[alert.id] = alert
    return list(by_id.values())


def _average_centroid_similarity(vectors: list[list[float]], centroid: list[float]) -> float:
    if not vectors:
        return 0.0
    return sum(cosine_similarity(vector, centroid) for vector in vectors) / len(vectors)


def _spatial_score(events: list[ComplaintIntelligenceEvent]) -> float:
    regions = [_normalize_region(event.region) for event in events]
    known = [region for region in regions if region]
    if not known:
        return 0.75
    if len(set(known)) == 1:
        return 1.0
    return 0.85


def _center(events: list[ComplaintIntelligenceEvent]) -> dict[str, float] | None:
    points = [
        (event.latitude, event.longitude)
        for event in events
        if event.latitude is not None and event.longitude is not None
    ]
    if not points:
        return None
    return {
        "latitude": round(sum(point[0] for point in points) / len(points), 6),
        "longitude": round(sum(point[1] for point in points) / len(points), 6),
    }


def _radius_km(events: list[ComplaintIntelligenceEvent]) -> float | None:
    center = _center(events)
    if center is None:
        return None
    points = [
        (event.latitude, event.longitude)
        for event in events
        if event.latitude is not None and event.longitude is not None
    ]
    if len(points) < 2:
        return 0.0
    return round(
        max(_haversine_km(center["latitude"], center["longitude"], lat, lon) for lat, lon in points),
        3,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

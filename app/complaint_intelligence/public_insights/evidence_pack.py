"""PublicAgencyInsight LLM 합성에 사용하는 근거 패키지."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.complaint_intelligence.config import (
    ComplaintIntelligenceConfig,
    get_complaint_intelligence_config,
)
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.action_catalog import allowed_actions_for
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidate
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicInsightType


class PublicInsightEvidencePack(BaseModel):
    """LLM에 전달되는 유일한 근거 입력."""

    candidate_id: str
    type_hint: Optional[PublicInsightType] = None
    topic_label: str
    region_summary: Optional[dict[str, Any]] = None
    department_summary: Optional[dict[str, Any]] = None
    window_start: datetime
    window_end: datetime
    complaint_count: int
    baseline_count: Optional[float] = None
    trend_metrics: dict[str, float | int | str] = Field(default_factory=dict)
    operational_metrics: dict[str, float | int | str] = Field(default_factory=dict)
    representative_complaints: list[dict[str, Any]] = Field(default_factory=list)
    key_phrases: list[str] = Field(default_factory=list)
    extracted_aspects: list[dict[str, Any]] = Field(default_factory=list)
    citizen_requests: list[dict[str, Any]] = Field(default_factory=list)
    linked_alert_ids: list[str] = Field(default_factory=list)
    similar_past_patterns: list[dict[str, Any]] = Field(default_factory=list)
    allowed_action_catalog: list[str] = Field(default_factory=list)


class EvidencePackBuilder:
    """후보와 민원 이벤트를 LLM 입력용 근거 패키지로 변환한다."""

    def __init__(self, config: ComplaintIntelligenceConfig | None = None) -> None:
        self.config = config or get_complaint_intelligence_config()

    def build(
        self,
        candidate: PublicInsightCandidate,
        events: list[ComplaintIntelligenceEvent],
        issue_alerts: list[IssueAlert] | None = None,
    ) -> PublicInsightEvidencePack:
        """대표 민원, 지역/부서/운영 지표, key phrase를 마스킹 근거로 구성한다."""

        event_by_id = {event.id: event for event in events}
        candidate_event_ids = candidate.event_ids or candidate.complaint_ids
        candidate_events = [event_by_id[event_id] for event_id in candidate_event_ids if event_id in event_by_id]
        alert_by_id = {alert.id: alert for alert in issue_alerts or []}
        linked_alerts = [alert_by_id[alert_id] for alert_id in candidate.linked_alert_ids if alert_id in alert_by_id]
        representative = self._representative_complaints(candidate_events, linked_alerts)
        complaint_count = len(candidate.complaint_ids) or len(candidate_events)
        region_summary = _region_summary(candidate_events, candidate.region_key)
        department_summary = _department_summary(candidate_events, candidate.department_key)
        baseline_count = linked_alerts[0].baseline if linked_alerts else None

        return PublicInsightEvidencePack(
            candidate_id=candidate.candidate_id,
            type_hint=candidate.type_hint,
            topic_label=candidate.topic_label,
            region_summary=region_summary,
            department_summary=department_summary,
            window_start=candidate.window_start,
            window_end=candidate.window_end,
            complaint_count=complaint_count,
            baseline_count=baseline_count,
            trend_metrics={**dict(candidate.trigger_metrics), **_structured_context_metrics(candidate_events)},
            operational_metrics={
                **_operational_metrics(candidate_events, candidate.window_end),
                **_structured_result_metrics(candidate_events),
            },
            representative_complaints=representative,
            key_phrases=_key_phrases(candidate_events, candidate.topic_label),
            linked_alert_ids=list(candidate.linked_alert_ids),
            similar_past_patterns=[],
            allowed_action_catalog=allowed_actions_for(candidate.type_hint),
        )

    def _representative_complaints(
        self,
        events: list[ComplaintIntelligenceEvent],
        linked_alerts: list[IssueAlert],
    ) -> list[dict[str, Any]]:
        row_by_text: dict[str, dict[str, Any]] = {}
        rows: list[dict[str, Any]] = []
        source_events = sorted(events, key=lambda item: item.received_at, reverse=True)
        for event in source_events:
            text = mask_pii(event.masked_text[: self.config.public_insight_max_evidence_chars_per_complaint]).text
            normalized = " ".join(text.split())
            if not normalized:
                continue
            if normalized in row_by_text:
                row_by_text[normalized].setdefault("source_complaint_ids", []).append(event.id)
                continue
            row = {
                "complaint_id": event.id,
                "source_complaint_ids": [event.id],
                "created_at": event.received_at.isoformat(),
                "masked_text": text,
                "region": event.region,
                "department": event.final_department,
                "status": event.status,
                "structured_elements": self._structured_elements(event),
            }
            row_by_text[normalized] = row
            rows.append(row)
            if len(rows) >= self.config.public_insight_max_representative_complaints:
                return rows

        for alert in linked_alerts:
            for item in alert.representative_complaints:
                text = mask_pii(item.masked_text[: self.config.public_insight_max_evidence_chars_per_complaint]).text
                normalized = " ".join(text.split())
                if not normalized or normalized in row_by_text:
                    continue
                row = {
                    "complaint_id": item.id,
                    "source_complaint_ids": [item.id],
                    "created_at": item.received_at.isoformat(),
                    "masked_text": text,
                    "region": item.region,
                    "department": None,
                    "status": None,
                    "structured_elements": {},
                }
                row_by_text[normalized] = row
                rows.append(row)
                if len(rows) >= self.config.public_insight_max_representative_complaints:
                    return rows
        return rows

    def _structured_elements(self, event: ComplaintIntelligenceEvent) -> dict[str, dict[str, Any]]:
        elements: dict[str, dict[str, Any]] = {}
        for field in ("observation", "result", "request", "context"):
            element = getattr(event.structured_elements, field, None)
            if element is None or not element.text.strip():
                continue
            text = mask_pii(element.text[: self.config.public_insight_max_evidence_chars_per_complaint]).text
            row: dict[str, Any] = {"text": text}
            if element.confidence is not None:
                row["confidence"] = element.confidence
            if element.evidence_span:
                row["evidence_span"] = list(element.evidence_span)
            if element.status:
                row["status"] = element.status
            elements[field] = row
        return elements


def _region_summary(events: list[ComplaintIntelligenceEvent], region_key: str | None) -> dict[str, Any] | None:
    counts: dict[str, int] = {}
    for event in events:
        if event.region:
            counts[event.region] = counts.get(event.region, 0) + 1
    if not counts and not region_key:
        return None
    return {"dominant_region": region_key, "counts": counts}


def _department_summary(events: list[ComplaintIntelligenceEvent], department_key: str | None) -> dict[str, Any] | None:
    counts: dict[str, int] = {}
    for event in events:
        if event.final_department:
            counts[event.final_department] = counts.get(event.final_department, 0) + 1
    if not counts and not department_key:
        return None
    return {"dominant_department": department_key, "counts": counts}


def _operational_metrics(events: list[ComplaintIntelligenceEvent], now: datetime) -> dict[str, float | int | str]:
    if not events:
        return {}
    open_count = sum(1 for event in events if str(event.status or "").lower() in {"접수", "처리중", "진행중", "open", "pending", "in_progress", "delayed", "지연"})
    reopened_count = sum(1 for event in events if event.reopened)
    handling_times = [
        float(event.handling_time_minutes)
        for event in events
        if event.handling_time_minutes is not None
    ]
    metrics: dict[str, float | int | str] = {
        "open_count": open_count,
        "reopened_count": reopened_count,
        "reopen_rate": round(reopened_count / len(events), 4),
    }
    if handling_times:
        metrics["avg_handling_time_minutes"] = round(sum(handling_times) / len(handling_times), 2)
    else:
        ages = [(now - event.received_at).total_seconds() / 60 for event in events]
        metrics["avg_age_minutes"] = round(sum(ages) / len(ages), 2)
    return metrics


def _structured_result_metrics(events: list[ComplaintIntelligenceEvent]) -> dict[str, float | int | str]:
    result_texts = [_structured_text(event, "result") for event in events]
    result_texts = [text for text in result_texts if text]
    if not result_texts:
        return {}

    impact_keywords = (
        "피해", "위험", "사고", "지연", "불편", "어려", "이용", "중단", "막힘", "민원",
        "문의", "반복", "안전", "침수", "감전", "악취", "소음",
    )
    impact_texts = [text for text in result_texts if any(keyword in text for keyword in impact_keywords)]
    confidences = [_structured_confidence(event, "result") for event in events]
    confidences = [value for value in confidences if value is not None]
    metrics: dict[str, float | int | str] = {
        "structured_result_count": len(result_texts),
        "structured_result_impact_count": len(impact_texts),
    }
    if confidences:
        metrics["structured_result_avg_confidence"] = round(sum(confidences) / len(confidences), 4)
    return metrics


def _structured_context_metrics(events: list[ComplaintIntelligenceEvent]) -> dict[str, float | int | str]:
    context_texts = [_structured_text(event, "context") for event in events]
    context_texts = [text for text in context_texts if text]
    if not context_texts:
        return {}

    time_keywords = (
        "출근", "퇴근", "야간", "새벽", "주말", "평일", "매일", "시간대", "오전", "오후",
        "저녁", "아침", "계절", "여름", "겨울",
    )
    repeat_keywords = ("반복", "계속", "매번", "자주", "같은", "동일")
    time_texts = [text for text in context_texts if any(keyword in text for keyword in time_keywords)]
    repeat_texts = [text for text in context_texts if any(keyword in text for keyword in repeat_keywords)]
    return {
        "structured_context_count": len(context_texts),
        "structured_context_time_pattern_count": len(time_texts),
        "structured_context_repeat_pattern_count": len(repeat_texts),
    }


def _key_phrases(events: list[ComplaintIntelligenceEvent], topic: str) -> list[str]:
    phrases: list[str] = []
    if topic and topic != "반복 민원":
        phrases.append(topic)
    for event in events:
        for token in _analysis_text(event).replace(",", " ").replace(".", " ").split():
            cleaned = token.strip()
            if len(cleaned) < 2 or cleaned.startswith("[REDACTED"):
                continue
            if cleaned not in phrases:
                phrases.append(cleaned)
            if len(phrases) >= 12:
                return phrases
    return phrases


def _analysis_text(event: ComplaintIntelligenceEvent) -> str:
    structured_texts = []
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element is not None and element.text.strip():
            structured_texts.append(element.text)
    structured_texts.append(event.masked_text)
    return " ".join(text for text in structured_texts if text)


def _structured_text(event: ComplaintIntelligenceEvent, field: str) -> str:
    element = getattr(event.structured_elements, field, None)
    if element is None:
        return ""
    return element.text.strip()


def _structured_confidence(event: ComplaintIntelligenceEvent, field: str) -> float | None:
    element = getattr(event.structured_elements, field, None)
    if element is None:
        return None
    return element.confidence

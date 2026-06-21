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
from app.complaint_intelligence.public_insights.action_rubric import action_type_rubric_for_pack
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
    valid_evidence_ids: list[str] = Field(default_factory=list)
    allowed_action_types: list[str] = Field(default_factory=list)
    preferred_action_types: list[str] = Field(default_factory=list)


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
        _append_operational_structured_signals(elements, event)
        return elements


def evidence_pack_for_llm(
    pack: PublicInsightEvidencePack,
    *,
    compact: bool = False,
    max_representative_complaints: int = 5,
    max_text_chars: int = 220,
) -> dict[str, Any]:
    """LLM 전달용 EvidencePack dict를 만든다.

    compact 모드는 로컬 LLM의 JSON 안정성을 위해 원본 EvidencePack의 긴 텍스트를 줄이되,
    deterministic metric과 evidence_id는 유지한다.
    """

    if not compact:
        rubric = action_type_rubric_for_pack(pack)
        payload = pack.model_dump(mode="json")
        payload["valid_evidence_ids"] = valid_evidence_ids_for_pack(pack)
        payload["allowed_action_types"] = rubric["allowed_action_types"]
        payload["preferred_action_types"] = rubric["preferred_action_types"]
        payload["action_type_rubric_requires_human_review"] = rubric["requires_human_review"]
        return payload

    rubric = action_type_rubric_for_pack(pack)
    representatives: list[dict[str, Any]] = []
    for item in pack.representative_complaints[:max_representative_complaints]:
        row: dict[str, Any] = {
            "complaint_id": item.get("complaint_id"),
            "masked_text": _short_masked(item.get("masked_text"), max_text_chars),
            "region": item.get("region"),
            "status": item.get("status"),
        }
        structured = item.get("structured_elements")
        if isinstance(structured, dict):
            compact_structured: dict[str, str] = {}
            for field in ("observation", "request", "context"):
                element = structured.get(field)
                if isinstance(element, dict) and element.get("text"):
                    compact_structured[field] = _short_masked(element.get("text"), 120)
            if compact_structured:
                row["structured_elements"] = compact_structured
        representatives.append(row)

    return {
        "candidate_id": pack.candidate_id,
        "type_hint": pack.type_hint,
        "topic_label": _short_masked(pack.topic_label, 80),
        "region_summary": pack.region_summary,
        "department_summary": pack.department_summary,
        "window_start": pack.window_start.isoformat(),
        "window_end": pack.window_end.isoformat(),
        "complaint_count": pack.complaint_count,
        "baseline_count": pack.baseline_count,
        "trend_metrics": _compact_metrics(pack.trend_metrics),
        "operational_metrics": _compact_metrics(pack.operational_metrics),
        "representative_complaints": representatives,
        "extracted_aspects": _compact_aspects(pack.extracted_aspects),
        "citizen_requests": _compact_requests(pack.citizen_requests),
        "linked_alert_ids": pack.linked_alert_ids,
        "allowed_action_catalog": pack.allowed_action_catalog[:8],
        "valid_evidence_ids": valid_evidence_ids_for_pack(pack, max_ids=20),
        "allowed_action_types": rubric["allowed_action_types"][:6],
        "preferred_action_types": rubric["preferred_action_types"][:3],
        "action_type_rubric_requires_human_review": rubric["requires_human_review"],
    }


def valid_evidence_ids_for_pack(pack: PublicInsightEvidencePack, max_ids: int | None = None) -> list[str]:
    """EvidencePack 내부에서 LLM이 참조할 수 있는 근거 ID를 결정적으로 계산한다."""

    ids: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)

    for item in pack.representative_complaints:
        add(item.get("complaint_id"))
        source_ids = item.get("source_complaint_ids")
        if isinstance(source_ids, list):
            for source_id in source_ids:
                add(source_id)
    for item in pack.extracted_aspects:
        for evidence_id in list(item.get("evidence_ids") or []):
            add(evidence_id)
    for item in pack.citizen_requests:
        for evidence_id in list(item.get("evidence_ids") or []):
            add(evidence_id)
    for evidence_id in pack.valid_evidence_ids:
        add(evidence_id)
    return ids[:max_ids] if max_ids is not None else ids


def _short_masked(value: Any, limit: int) -> str:
    text = mask_pii(str(value or "")).text
    return text[:limit]


def _append_operational_structured_signals(
    elements: dict[str, dict[str, Any]],
    event: ComplaintIntelligenceEvent,
) -> None:
    """운영 메타데이터를 aspect/request 추출용 마스킹 문장으로 보강한다."""

    analysis_text = " ".join(
        [
            str(event.masked_text or ""),
            str(event.reviewer_feedback or ""),
            str(event.feedback or ""),
            str(event.status or ""),
        ]
    )
    if _is_repeat_or_reopen_signal(event, analysis_text):
        _append_structured_text(
            elements,
            "context",
            "재민원/반복 접수 신호가 있으며 처리 완료 후 재문의가 확인됩니다.",
        )
        _append_structured_text(
            elements,
            "result",
            "처리 결과 불만과 재발 우려가 반복되어 현장 조치 실효성 확인이 필요합니다.",
        )
        _append_structured_text(
            elements,
            "request",
            "재발 원인 점검, 처리 완료 안내 개선, 현장 조치 검증과 소통 강화를 요청합니다.",
        )

    if _is_construction_noise_time_signal(event, analysis_text):
        _append_structured_text(
            elements,
            "context",
            "야간·새벽·퇴근 이후 시간대에 공사 소음/진동 민원이 집중됩니다.",
        )
        _append_structured_text(
            elements,
            "result",
            "특정 시간대 소음/진동으로 생활 불편과 단속 공백 인식이 반복됩니다.",
        )
        _append_structured_text(
            elements,
            "request",
            "야간 소음 현장 점검, 단속 강화, 공사 시간 안내를 요청합니다.",
        )


def _append_structured_text(
    elements: dict[str, dict[str, Any]],
    field: str,
    text: str,
) -> None:
    row = elements.setdefault(field, {"text": "", "confidence": 0.7})
    current = str(row.get("text") or "").strip()
    combined = f"{current} {text}".strip() if current else text
    row["text"] = mask_pii(combined).text
    row.setdefault("confidence", 0.72)
    if not current:
        row["operational_signal_only"] = True


def _is_repeat_or_reopen_signal(event: ComplaintIntelligenceEvent, text: str) -> bool:
    repeat_keywords = ("재민원", "반복", "재문의", "재접수", "재발", "여러 번", "처리 완료", "완료 안내", "불만")
    status = str(event.status or "").lower()
    feedback_score = float(event.user_feedback_score) if event.user_feedback_score is not None else None
    return (
        event.reopened
        or status in {"reopened", "재접수", "재민원"}
        or (feedback_score is not None and feedback_score <= 2.0)
        or any(keyword in text for keyword in repeat_keywords)
    )


def _is_construction_noise_time_signal(event: ComplaintIntelligenceEvent, text: str) -> bool:
    noise_keywords = ("공사", "소음", "진동", "공사장", "작업 소음", "차량 소음")
    time_keywords = ("야간", "새벽", "밤", "주말", "퇴근", "이른 아침", "시간대")
    hour = event.received_at.hour
    is_night_or_edge = hour >= 18 or hour <= 7
    return any(keyword in text for keyword in noise_keywords) and (
        is_night_or_edge or any(keyword in text for keyword in time_keywords)
    )


def _compact_metrics(metrics: dict[str, float | int | str]) -> dict[str, float | int | str]:
    allowed_keys = {
        "complaint_count",
        "surge_ratio",
        "recent_count",
        "baseline_count",
        "open_count",
        "reopened_count",
        "reopen_rate",
        "avg_handling_time_minutes",
        "avg_age_minutes",
        "structured_context_time_pattern_count",
        "structured_context_repeat_pattern_count",
        "structured_result_impact_count",
    }
    return {key: value for key, value in metrics.items() if key in allowed_keys}


def _compact_aspects(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items[:3]:
        rows.append(
            {
                "aspect": item.get("aspect"),
                "count": item.get("count"),
                "sentiment": item.get("sentiment", "negative"),
                "evidence_ids": list(item.get("evidence_ids") or [])[:2],
                "representative_phrases": [_short_masked(phrase, 60) for phrase in list(item.get("representative_phrases") or [])[:1]],
            }
        )
    return rows


def _compact_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items[:3]:
        rows.append(
            {
                "request": _short_masked(item.get("request"), 80),
                "count": item.get("count"),
                "evidence_ids": list(item.get("evidence_ids") or [])[:2],
                "request_type": item.get("request_type"),
            }
        )
    return rows


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

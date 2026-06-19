"""중복 그룹의 대표 민원 선정."""

from __future__ import annotations

from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.duplicate_merger.scoring import analysis_text, structural_evidence_count
from app.complaint_intelligence.duplicate_merger.schemas import DuplicateRepresentative


class RepresentativeSelector:
    """최초 접수순 대신 정보 품질 기준으로 대표 민원을 고른다."""

    def select(self, events: list[ComplaintIntelligenceEvent]) -> DuplicateRepresentative:
        """그룹 내 다른 민원을 포괄하기 좋은 대표 민원을 반환한다."""

        if not events:
            raise ValueError("대표 민원을 선정할 이벤트가 없습니다.")

        scored = [(self._quality_score(event), event) for event in events]
        scored.sort(key=lambda item: (-item[0], item[1].received_at, item[1].id))
        score, selected = scored[0]
        reasons = self._selection_reasons(selected)
        return DuplicateRepresentative(
            complaint_id=selected.id,
            selection_reason=", ".join(reasons),
            quality_score=round(score, 4),
        )

    def _quality_score(self, event: ComplaintIntelligenceEvent) -> float:
        structured_count = structural_evidence_count(event)
        text_len = min(len(analysis_text(event)), 600) / 600
        entity_count = min(len(getattr(event, "entity_texts", []) or []), 6) / 6
        segment_count = min(len(getattr(event, "request_segments", []) or []), 4) / 4
        request_specificity = self._request_specificity(event)
        pii_penalty = 0.15 if event.pii_detected or event.pii_status not in {"PASSED", "MASKED"} else 0.0
        score = (
            0.35 * min(structured_count / 8, 1.0)
            + 0.25 * text_len
            + 0.15 * entity_count
            + 0.15 * request_specificity
            + 0.10 * segment_count
            - pii_penalty
        )
        return max(0.0, min(1.0, score))

    def _request_specificity(self, event: ComplaintIntelligenceEvent) -> float:
        request = getattr(event.structured_elements, "request", None)
        text = request.text if request and request.text else ""
        if not text:
            text = " ".join(getattr(event, "request_segments", []) or [])
        markers = ("요청", "점검", "보수", "단속", "개선", "설치", "조치", "안내", "보상")
        marker_score = 1.0 if any(marker in text for marker in markers) else 0.4
        return min(1.0, (len(text) / 80) * 0.6 + marker_score * 0.4)

    def _selection_reasons(self, event: ComplaintIntelligenceEvent) -> list[str]:
        reasons = []
        if event.structured_elements.has_any_text():
            reasons.append("4요소 구조화 정보가 풍부함")
        if event.region or getattr(event, "entity_texts", None):
            reasons.append("위치/시설 신호가 명확함")
        request = getattr(event.structured_elements, "request", None)
        if request and request.text:
            reasons.append("요구사항이 구체적임")
        if not event.pii_detected:
            reasons.append("PII 노출 위험이 낮음")
        if not reasons:
            reasons.append("그룹 내에서 가장 많은 PII-safe 설명 신호를 보유함")
        return reasons

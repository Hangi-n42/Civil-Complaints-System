"""공공기관 인사이트의 priority와 confidence를 결정적으로 계산한다."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.complaint_intelligence.config import (
    ComplaintIntelligenceConfig,
    get_complaint_intelligence_config,
)
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.grounding_verifier import VerifiedInsightDraft
from app.complaint_intelligence.schemas import PublicAgencyInsight


class PublicInsightRanker:
    """LLM 초안 품질보다 deterministic metric을 우선해 순위를 산정한다."""

    def __init__(self, config: ComplaintIntelligenceConfig | None = None) -> None:
        self.config = config or get_complaint_intelligence_config()

    def rank(
        self,
        draft: VerifiedInsightDraft,
        pack: PublicInsightEvidencePack,
        now: datetime | None = None,
    ) -> PublicAgencyInsight:
        now = now or datetime.now(timezone.utc)
        priority_score = self._priority_score(pack)
        priority = self._priority(priority_score)
        priority = self._raise_priority_for_safety_or_alert(priority, pack)
        confidence = self._confidence(draft, pack)
        insight_id = "public-insight-" + hashlib.sha1(pack.candidate_id.encode("utf-8")).hexdigest()[:12]

        return PublicAgencyInsight(
            insight_id=insight_id,
            id=insight_id,
            type=pack.type_hint or "RECURRING_COMPLAINT_PATTERN",
            status="open",
            priority=priority,
            title=draft.title,
            summary=draft.summary,
            problem_diagnosis=draft.problem_diagnosis,
            topic=pack.topic_label,
            target_area=_target_area(pack.type_hint),
            affected_region=pack.region_summary,
            related_department=(pack.department_summary or {}).get("dominant_department") if pack.department_summary else None,
            affected_count=pack.complaint_count,
            window_start=pack.window_start,
            window_end=pack.window_end,
            window={"start": pack.window_start, "end": pack.window_end},
            metrics={
                **pack.trend_metrics,
                **pack.operational_metrics,
                "priority_score": round(priority_score, 4),
            },
            extracted_aspects=draft.extracted_aspects,
            citizen_requests=draft.citizen_requests,
            root_cause_hypotheses=draft.root_cause_hypotheses,
            evidence=[
                {
                    "complaint_id": item.get("complaint_id"),
                    "source_complaint_ids": item.get("source_complaint_ids") or [item.get("complaint_id")],
                    "masked_text": item.get("masked_text", ""),
                    "region": item.get("region"),
                    "received_at": item.get("created_at"),
                    "department": item.get("department"),
                    "status": item.get("status"),
                    "structured_elements": item.get("structured_elements") or {},
                }
                for item in pack.representative_complaints
            ],
            representative_complaint_ids=[str(item.get("complaint_id")) for item in pack.representative_complaints],
            representative_ids=[str(item.get("complaint_id")) for item in pack.representative_complaints],
            linked_alert_ids=pack.linked_alert_ids,
            recommended_actions=draft.recommended_actions,
            recommended_action_texts=[action.action for action in draft.recommended_actions],
            expected_impact=draft.expected_impact,
            uncertainty=draft.uncertainty,
            requires_human_review=draft.requires_human_review,
            confidence=confidence,
            grounding_score=draft.grounding_score,
            created_at=now,
            updated_at=now,
            explanation=draft.explanation,
        )

    def _priority_score(self, pack: PublicInsightEvidencePack) -> float:
        affected = min(1.0, pack.complaint_count / max(self.config.public_insight_high_repeat_count, 1))
        surge = min(1.0, float(pack.trend_metrics.get("surge_ratio", 0.0) or 0.0) / 3.0)
        safety = 1.0 if pack.type_hint in {"SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"} else 0.0
        repeat = min(1.0, float(pack.trend_metrics.get("repeat_count", 0.0) or pack.operational_metrics.get("reopened_count", 0.0) or 0.0) / max(self.config.repeat_risk_count, 1))
        regional = min(1.0, float(pack.trend_metrics.get("regional_concentration", 0.0) or 0.0) / max(self.config.public_insight_regional_concentration_threshold, 0.01))
        delay = 1.0 if pack.type_hint in {"PROCESS_DELAY_RISK", "DEPARTMENT_WORKLOAD_BOTTLENECK"} else 0.0
        return (
            0.25 * affected
            + 0.20 * surge
            + 0.20 * safety
            + 0.15 * repeat
            + 0.10 * regional
            + 0.10 * delay
        )

    def _priority(self, score: float) -> str:
        if score >= self.config.public_insight_priority_critical_threshold:
            return "CRITICAL"
        if score >= self.config.public_insight_priority_high_threshold:
            return "HIGH"
        if score >= 0.50:
            return "MEDIUM"
        return "LOW"

    def _raise_priority_for_safety_or_alert(self, priority: str, pack: PublicInsightEvidencePack) -> str:
        """안전/급증 알림이 연결된 경우 낮은 건수만으로 우선순위가 과소평가되지 않게 보정한다."""

        if pack.type_hint == "SAFETY_RISK_SIGNAL" and pack.linked_alert_ids and priority in {"LOW", "MEDIUM"}:
            return "HIGH"
        if pack.type_hint in {"SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"} and priority == "LOW":
            return "MEDIUM"
        return priority

    def _confidence(self, draft: VerifiedInsightDraft, pack: PublicInsightEvidencePack) -> float:
        semantic_cohesion = float(pack.trend_metrics.get("semantic_cohesion", 0.75) or 0.75)
        evidence_coverage = min(1.0, len(pack.representative_complaints) / max(pack.complaint_count, 1))
        metric_completeness = 1.0 if pack.trend_metrics else 0.7
        regions = {item.get("region") for item in pack.representative_complaints if item.get("region")}
        diversity = min(1.0, max(len(regions), 1) / 3)
        confidence = (
            0.35 * semantic_cohesion
            + 0.25 * evidence_coverage
            + 0.20 * draft.grounding_score
            + 0.10 * metric_completeness
            + 0.10 * diversity
        )
        if draft.grounding_score < self.config.public_insight_min_grounding_score:
            confidence *= 0.7
        return round(max(0.0, min(1.0, confidence)), 4)


def _target_area(insight_type: str | None) -> str:
    return {
        "HOTSPOT_RESPONSE_REQUIRED": "현장 대응",
        "SAFETY_RISK_SIGNAL": "시민 안전",
        "RECURRING_COMPLAINT_PATTERN": "민원 운영",
        "REGIONAL_SERVICE_GAP": "지역 서비스",
        "DEPARTMENT_WORKLOAD_BOTTLENECK": "부서 운영",
        "PROCESS_DELAY_RISK": "처리 프로세스",
        "REOPEN_OR_REPEAT_RISK": "민원 재발 관리",
        "SEASONAL_OR_TIME_PATTERN": "운영 시간 조정",
        "PUBLIC_GUIDANCE_NEEDED": "시민 안내",
        "FACILITY_MAINTENANCE_PRIORITY": "시설 유지보수",
        "ENFORCEMENT_PRIORITY": "단속/점검",
        "POLICY_IMPROVEMENT_OPPORTUNITY": "정책/서비스 개선",
        "SERVICE_DESIGN_IMPROVEMENT": "서비스 설계",
        "ACCESSIBILITY_OR_USABILITY_ISSUE": "접근성/사용성",
        "CITIZEN_COMMUNICATION_GAP": "시민 소통",
    }.get(str(insight_type), "행정 대응")

"""LLM 실패 시 사용하는 근거 기반 fallback 템플릿."""

from __future__ import annotations

from app.complaint_intelligence.public_insights.action_catalog import allowed_actions_for
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.grounding_verifier import VerifiedInsightDraft
from app.complaint_intelligence.schemas import RecommendedAction, RootCauseHypothesis


class PublicInsightFallbackGenerator:
    """EvidencePack 수치만 사용해 안전한 fallback 초안을 만든다."""

    def generate(self, pack: PublicInsightEvidencePack, reason: str = "LLM 인사이트 생성 실패") -> VerifiedInsightDraft:
        evidence_ids = [str(item.get("complaint_id")) for item in pack.representative_complaints if item.get("complaint_id")]
        selected_ids = evidence_ids[:3]
        region = (pack.region_summary or {}).get("dominant_region") or "해당 지역"
        top_aspect = (pack.extracted_aspects[0]["aspect"] if pack.extracted_aspects else "반복 민원")
        actions = allowed_actions_for(pack.type_hint) if pack.type_hint else []
        action_text = actions[0] if actions else "대표 민원을 검토하고 담당 부서 대응 계획을 수립합니다."

        return VerifiedInsightDraft(
            title=f"{region} {pack.topic_label} 관련 반복 민원 개선 검토",
            summary=f"{pack.window_start.date()}부터 {pack.window_end.date()}까지 {region}에서 {pack.topic_label} 관련 민원 {pack.complaint_count}건이 확인되었습니다.",
            problem_diagnosis=f"민원 내용상 {top_aspect} 관련 불편이 반복됩니다.",
            root_cause_hypotheses=[
                RootCauseHypothesis(
                    hypothesis=f"{top_aspect} 관련 정보나 처리 흐름이 시민에게 충분히 명확하지 않을 가능성이 있습니다.",
                    support_level="MEDIUM",
                    supporting_evidence_ids=selected_ids,
                    needs_human_validation=True,
                )
            ],
            extracted_aspects=pack.extracted_aspects,
            citizen_requests=pack.citizen_requests,
            recommended_actions=[
                RecommendedAction(
                    action=action_text,
                    horizon="SHORT_TERM",
                    action_type=_action_type_for(pack.type_hint),
                    responsible_unit_hint=(pack.department_summary or {}).get("dominant_department") if pack.department_summary else None,
                    why=f"{top_aspect} 관련 근거 민원이 반복되었습니다.",
                    supporting_evidence_ids=selected_ids,
                    expected_impact="반복 문의와 불편을 줄일 가능성이 있습니다.",
                    risk_or_dependency="담당자 검토와 현장/업무 데이터 확인이 필요합니다.",
                )
            ],
            expected_impact="반복 민원 원인을 행정 조치 단위로 정리할 수 있습니다.",
            uncertainty=[f"{reason}로 템플릿 기반 요약을 제공했습니다."],
            requires_human_review=True,
            explanation="fallback template은 EvidencePack의 마스킹 근거와 결정적 수치만 사용했습니다.",
            grounding_score=1.0,
            removed_claims=[],
        )


def _action_type_for(insight_type: str | None) -> str:
    if insight_type in {"SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"}:
        return "FIELD_INSPECTION"
    if insight_type == "FACILITY_MAINTENANCE_PRIORITY":
        return "MAINTENANCE"
    if insight_type == "ENFORCEMENT_PRIORITY":
        return "ENFORCEMENT"
    if insight_type == "POLICY_IMPROVEMENT_OPPORTUNITY":
        return "POLICY_REVIEW"
    if insight_type == "SERVICE_DESIGN_IMPROVEMENT":
        return "SERVICE_DESIGN"
    if insight_type == "DEPARTMENT_WORKLOAD_BOTTLENECK":
        return "STAFFING_OR_WORKLOAD_REVIEW"
    if insight_type in {"PROCESS_DELAY_RISK", "REOPEN_OR_REPEAT_RISK"}:
        return "PROCESS_IMPROVEMENT"
    if insight_type == "CITIZEN_COMMUNICATION_GAP":
        return "CITIZEN_COMMUNICATION"
    return "PUBLIC_GUIDANCE"

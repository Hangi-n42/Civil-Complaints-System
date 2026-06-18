"""LLM 인사이트 초안의 근거성과 PII 안전성을 검증한다."""

from __future__ import annotations

from pydantic import Field

from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicAgencyInsightDraft
from app.complaint_intelligence.schemas import RecommendedAction, RootCauseHypothesis


UNSUPPORTED_CLAIM_TERMS = ("예산", "조례", "시장 지시", "법령", "즉시 변경 가능", "3억")
POLICY_OR_SAFETY_TYPES = {
    "SAFETY_RISK_SIGNAL",
    "HOTSPOT_RESPONSE_REQUIRED",
    "PUBLIC_GUIDANCE_NEEDED",
    "POLICY_IMPROVEMENT_OPPORTUNITY",
    "SERVICE_DESIGN_IMPROVEMENT",
}


class VerifiedInsightDraft(PublicAgencyInsightDraft):
    """검증과 보정이 끝난 초안."""

    grounding_score: float = 0.0
    removed_claims: list[str] = Field(default_factory=list)


class GroundingVerifier:
    """근거 없는 claim/action을 제거하거나 uncertainty로 강등한다."""

    def verify_and_repair(
        self,
        draft: PublicAgencyInsightDraft,
        pack: PublicInsightEvidencePack,
    ) -> VerifiedInsightDraft:
        allowed_ids = _allowed_evidence_ids(pack)
        allowed_actions = set(pack.allowed_action_catalog)
        removed: list[str] = []

        title = mask_pii(draft.title).text
        summary = mask_pii(draft.summary).text
        diagnosis = mask_pii(draft.problem_diagnosis).text
        explanation = mask_pii(draft.explanation).text
        uncertainty = [mask_pii(item).text for item in draft.uncertainty]

        repaired_actions: list[RecommendedAction] = []
        for action in draft.recommended_actions:
            evidence_ids = [item for item in action.supporting_evidence_ids if item in allowed_ids]
            action_text = mask_pii(action.action).text
            why = mask_pii(action.why).text
            risk = mask_pii(action.risk_or_dependency).text if action.risk_or_dependency else None
            impact = mask_pii(action.expected_impact).text if action.expected_impact else None
            if not evidence_ids:
                removed.append(action.action)
                continue
            if _has_unsupported_claim(action_text, pack) or _has_unsupported_claim(why, pack):
                removed.append(action.action)
                uncertainty.append(f"근거가 약한 조치 문구를 제거했습니다: {action.action[:40]}")
                continue
            if action.action not in allowed_actions and action.risk_or_dependency is None:
                risk = "카탈로그 외 조치이므로 담당자 검토가 필요합니다."
            repaired_actions.append(
                action.model_copy(
                    update={
                        "action": action_text,
                        "why": why,
                        "supporting_evidence_ids": evidence_ids,
                        "expected_impact": impact,
                        "risk_or_dependency": risk,
                    }
                )
            )

        repaired_hypotheses = [
            _repair_hypothesis(item, allowed_ids)
            for item in draft.root_cause_hypotheses
            if set(item.supporting_evidence_ids).intersection(allowed_ids)
        ]
        if _has_unsupported_claim(summary + " " + diagnosis + " " + explanation, pack):
            uncertainty.append("근거 패키지에 없는 법령, 예산, 지시 관련 표현은 확정 사실로 사용하지 않았습니다.")
            summary = _remove_unsupported_terms(summary)
            diagnosis = _remove_unsupported_terms(diagnosis)
            explanation = _remove_unsupported_terms(explanation)

        requires_review = draft.requires_human_review or str(pack.type_hint) in POLICY_OR_SAFETY_TYPES
        score = _grounding_score(draft, repaired_actions, removed, allowed_ids)

        return VerifiedInsightDraft(
            title=title,
            summary=summary,
            problem_diagnosis=diagnosis,
            root_cause_hypotheses=repaired_hypotheses,
            extracted_aspects=draft.extracted_aspects,
            citizen_requests=draft.citizen_requests,
            recommended_actions=repaired_actions,
            expected_impact=mask_pii(draft.expected_impact).text if draft.expected_impact else None,
            uncertainty=uncertainty,
            requires_human_review=requires_review,
            explanation=explanation,
            grounding_score=score,
            removed_claims=removed,
        )


def _repair_hypothesis(item: RootCauseHypothesis, allowed_ids: set[str]) -> RootCauseHypothesis:
    text = mask_pii(item.hypothesis).text
    text = text.replace("원인입니다", "원인일 가능성이 있습니다")
    text = text.replace("때문입니다", "때문일 가능성이 있습니다")
    return item.model_copy(
        update={
            "hypothesis": text,
            "supporting_evidence_ids": [evidence_id for evidence_id in item.supporting_evidence_ids if evidence_id in allowed_ids],
            "needs_human_validation": True,
        }
    )


def _allowed_evidence_ids(pack: PublicInsightEvidencePack) -> set[str]:
    allowed_ids: set[str] = set()
    for item in pack.representative_complaints:
        if item.get("complaint_id"):
            allowed_ids.add(str(item.get("complaint_id")))
        source_ids = item.get("source_complaint_ids")
        if isinstance(source_ids, list):
            allowed_ids.update(str(source_id) for source_id in source_ids if source_id)
    return allowed_ids


def _has_unsupported_claim(text: str, pack: PublicInsightEvidencePack) -> bool:
    pack_text = pack.model_dump_json()
    return any(term in text and term not in pack_text for term in UNSUPPORTED_CLAIM_TERMS)


def _remove_unsupported_terms(text: str) -> str:
    cleaned = text
    for term in UNSUPPORTED_CLAIM_TERMS:
        cleaned = cleaned.replace(term, "근거 미확인 항목")
    return cleaned


def _grounding_score(
    draft: PublicAgencyInsightDraft,
    actions: list[RecommendedAction],
    removed: list[str],
    allowed_ids: set[str],
) -> float:
    score = 1.0
    if not actions:
        score -= 0.5
    if removed:
        score -= min(0.35, 0.1 * len(removed))
    action_count = max(len(draft.recommended_actions), 1)
    supported_count = sum(1 for action in actions if set(action.supporting_evidence_ids).issubset(allowed_ids))
    score -= 0.2 * (1 - supported_count / action_count)
    return round(max(0.0, min(1.0, score)), 4)

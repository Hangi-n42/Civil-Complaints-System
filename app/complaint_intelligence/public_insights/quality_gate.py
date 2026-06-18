"""PublicAgencyInsight 운영 노출 전 품질 게이트."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.schemas import PublicAgencyInsight, RecommendedAction


FORBIDDEN_AI_OPS_TERMS = (
    "RAG",
    "retrieval",
    "RETRIEVAL",
    "prompt",
    "PROMPT",
    "model",
    "MODEL",
    "answer_quality",
    "answer quality",
    "ANSWER_QUALITY",
    "검색 품질",
    "라우팅 모델",
    "프롬프트",
    "모델 개선",
    "답변 품질",
)

CONCRETE_ACTION_TERMS = (
    "추가", "보강", "점검", "확인", "정비", "보수", "공지", "안내", "배치", "공유",
    "조정", "수립", "분리", "반영", "개편", "개선", "강화", "검토", "작성", "설치",
)
ABSTRACT_ONLY_TERMS = {"검토", "개선", "강화", "관리", "추진"}
POLICY_OR_SAFETY_TYPES = {
    "SAFETY_RISK_SIGNAL",
    "HOTSPOT_RESPONSE_REQUIRED",
    "POLICY_IMPROVEMENT_OPPORTUNITY",
}
ADMIN_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("legal_or_ordinance", re.compile(r"(?:조례|법령|법률|시행령|시행규칙)\s*제?\s*\d+\s*조")),
    ("budget_amount", re.compile(r"(?:예산\s*)?\d+(?:\.\d+)?\s*(?:억\s*원|억원|억|만원|원)")),
    ("authority_instruction", re.compile(r"(?:시장|구청장|도지사|장관)\s*지시")),
)


class QualityGateFailure(BaseModel):
    """품질 게이트 실패/경고 항목."""

    code: str
    message: str
    severity: str = "error"
    details: dict[str, Any] = Field(default_factory=dict)


class QualityGateResult(BaseModel):
    """PublicAgencyInsight 품질 게이트 결과."""

    passed: bool
    score: float
    failures: list[QualityGateFailure] = Field(default_factory=list)
    warnings: list[QualityGateFailure] = Field(default_factory=list)


class ActionabilityScore(BaseModel):
    """추천 조치 실행 가능성 점수."""

    score: float
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InsightQualityGate:
    """최종 인사이트가 운영 노출 가능한지 검사한다."""

    def __init__(
        self,
        *,
        min_grounding_score: float = 0.65,
        min_confidence: float = 0.45,
        min_actionability_score: float = 0.55,
    ) -> None:
        self.min_grounding_score = min_grounding_score
        self.min_confidence = min_confidence
        self.min_actionability_score = min_actionability_score

    def evaluate(
        self,
        insight: PublicAgencyInsight,
        pack: PublicInsightEvidencePack | None = None,
    ) -> QualityGateResult:
        """인사이트 품질을 점검하고 실패 사유를 구조화해 반환한다."""

        failures: list[QualityGateFailure] = []
        warnings: list[QualityGateFailure] = []
        evidence_ids = _evidence_ids(insight, pack)

        if not insight.title or not insight.summary or not insight.problem_diagnosis:
            failures.append(_failure("SCHEMA_INVALID", "필수 설명 필드가 비어 있습니다."))
        if not insight.recommended_actions:
            failures.append(_failure("NO_ACTIONS", "recommended_actions가 비어 있습니다."))

        invalid_actions = [
            action.action
            for action in insight.recommended_actions
            if not set(action.supporting_evidence_ids).issubset(evidence_ids)
        ]
        if invalid_actions:
            failures.append(
                _failure(
                    "EVIDENCE_ID_INVALID",
                    "추천 조치가 존재하지 않는 evidence id를 참조합니다.",
                    {"actions": invalid_actions[:5]},
                )
            )

        actions_without_evidence = [
            action.action for action in insight.recommended_actions if not action.supporting_evidence_ids
        ]
        if actions_without_evidence:
            failures.append(
                _failure(
                    "ACTION_EVIDENCE_MISSING",
                    "추천 조치에 supporting_evidence_ids가 없습니다.",
                    {"actions": actions_without_evidence[:5]},
                )
            )

        if _contains_unmasked_pii(insight):
            failures.append(_failure("PII_UNSAFE", "인사이트 출력에 마스킹되지 않은 PII가 남아 있습니다."))

        forbidden_terms = _forbidden_terms(insight)
        if forbidden_terms:
            failures.append(
                _failure(
                    "FORBIDDEN_AI_OPS_TERMS",
                    "AI 운영자용 개선 용어가 public insight 출력에 포함되어 있습니다.",
                    {"terms": forbidden_terms},
                )
            )

        unsupported_numbers = _unsupported_numeric_claims(insight, pack)
        if unsupported_numbers:
            warnings.append(
                _warning(
                    "UNSUPPORTED_NUMERIC_CLAIM",
                    "EvidencePack metrics로 확인되지 않는 숫자 표현이 있습니다.",
                    {"numbers": unsupported_numbers[:10]},
                )
            )

        unsupported_admin_claims = _unsupported_admin_claims(insight, pack)
        if unsupported_admin_claims:
            failures.append(
                _failure(
                    "UNSUPPORTED_ADMIN_CLAIM",
                    "EvidencePack에 없는 법령/예산/지시사항 주장이 포함되어 있습니다.",
                    {"claims": unsupported_admin_claims[:10]},
                )
            )

        if str(insight.type) in POLICY_OR_SAFETY_TYPES and not insight.requires_human_review:
            failures.append(
                _failure(
                    "HUMAN_REVIEW_REQUIRED",
                    "정책/안전 유형 인사이트는 담당자 검토가 필요합니다.",
                )
            )

        if insight.grounding_score < self.min_grounding_score:
            failures.append(
                _failure(
                    "GROUNDING_SCORE_LOW",
                    "grounding_score가 최소 기준보다 낮습니다.",
                    {"grounding_score": insight.grounding_score, "minimum": self.min_grounding_score},
                )
            )

        if insight.confidence < self.min_confidence:
            failures.append(
                _failure(
                    "CONFIDENCE_LOW",
                    "confidence가 최소 기준보다 낮습니다.",
                    {"confidence": insight.confidence, "minimum": self.min_confidence},
                )
            )

        action_scores = [score_actionability(action) for action in insight.recommended_actions]
        min_actionability = min((item.score for item in action_scores), default=0.0)
        if min_actionability < self.min_actionability_score:
            failures.append(
                _failure(
                    "ACTIONABILITY_SCORE_LOW",
                    "추천 조치의 실행 가능성 점수가 최소 기준보다 낮습니다.",
                    {"min_actionability_score": min_actionability, "minimum": self.min_actionability_score},
                )
            )

        score = _quality_score(failures, warnings, insight, min_actionability)
        return QualityGateResult(
            passed=not failures,
            score=score,
            failures=failures,
            warnings=warnings,
        )


def attach_actionability_metrics(insight: PublicAgencyInsight) -> PublicAgencyInsight:
    """추천 조치 실행 가능성 점수를 metrics에 추가한다."""

    scores = [score_actionability(action).score for action in insight.recommended_actions]
    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    min_score = round(min(scores), 4) if scores else 0.0
    metrics = {
        **insight.metrics,
        "avg_actionability_score": avg_score,
        "min_actionability_score": min_score,
    }
    return insight.model_copy(update={"metrics": metrics})


def score_actionability(action: RecommendedAction) -> ActionabilityScore:
    """recommended_action 하나의 실행 가능성을 0~1로 계산한다."""

    score = 0.0
    failures: list[str] = []
    warnings: list[str] = []

    if any(term in action.action for term in CONCRETE_ACTION_TERMS):
        score += 0.20
    else:
        failures.append("concrete_action_verb_missing")
    if action.action_type:
        score += 0.15
    else:
        failures.append("action_type_missing")
    if action.horizon:
        score += 0.15
    else:
        failures.append("horizon_missing")
    if action.supporting_evidence_ids:
        score += 0.20
    else:
        failures.append("supporting_evidence_missing")
    if action.why:
        score += 0.15
    else:
        failures.append("why_missing")
    if action.expected_impact or action.risk_or_dependency:
        score += 0.15
    else:
        warnings.append("impact_or_dependency_missing")

    if _is_abstract_only(action.action):
        score = min(score, 0.45)
        failures.append("abstract_only_action")

    return ActionabilityScore(score=round(max(0.0, min(1.0, score)), 4), failures=failures, warnings=warnings)


def _evidence_ids(insight: PublicAgencyInsight, pack: PublicInsightEvidencePack | None) -> set[str]:
    ids: set[str] = set()
    for evidence in insight.evidence:
        ids.add(str(evidence.complaint_id))
        ids.update(str(item) for item in evidence.source_complaint_ids if item)
    if pack is not None:
        for item in pack.representative_complaints:
            if item.get("complaint_id"):
                ids.add(str(item.get("complaint_id")))
            source_ids = item.get("source_complaint_ids")
            if isinstance(source_ids, list):
                ids.update(str(source_id) for source_id in source_ids if source_id)
    return ids


def _contains_unmasked_pii(insight: PublicAgencyInsight) -> bool:
    return bool(mask_pii(_visible_text(insight)).detected_labels)


def _forbidden_terms(insight: PublicAgencyInsight) -> list[str]:
    text = _visible_text(insight)
    return sorted({term for term in FORBIDDEN_AI_OPS_TERMS if term in text})


def _unsupported_numeric_claims(
    insight: PublicAgencyInsight,
    pack: PublicInsightEvidencePack | None,
) -> list[str]:
    text = " ".join(
        [
            insight.summary,
            insight.problem_diagnosis,
            insight.expected_impact or "",
            " ".join(action.action for action in insight.recommended_actions),
            " ".join(action.why for action in insight.recommended_actions),
        ]
    )
    numbers = sorted(set(re.findall(r"\d+(?:\.\d+)?", text)))
    if not numbers:
        return []

    allowed_values: list[Any] = [
        insight.affected_count,
        insight.grounding_score,
        insight.confidence,
        *insight.metrics.values(),
        *(aspect.count for aspect in insight.extracted_aspects),
        *(request.count for request in insight.citizen_requests),
    ]
    if pack is not None:
        allowed_values.extend(
            [
                pack.complaint_count,
                pack.baseline_count,
                *pack.trend_metrics.values(),
                *pack.operational_metrics.values(),
            ]
        )
    allowed_text = " ".join(str(value) for value in allowed_values if value is not None)
    # 날짜/ID에서 나온 숫자는 과도하게 막지 않고, metrics/evidence에 전혀 없는 숫자만 경고한다.
    return [number for number in numbers if number not in allowed_text]


def _unsupported_admin_claims(
    insight: PublicAgencyInsight,
    pack: PublicInsightEvidencePack | None,
) -> list[dict[str, str]]:
    """법령/예산/지시사항처럼 근거 없으면 위험한 행정 주장을 찾는다."""

    text = _visible_text(insight)
    pack_text = _pack_text(pack)
    claims: list[dict[str, str]] = []
    for claim_type, pattern in ADMIN_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            claim = match.group(0)
            if pack_text and claim in pack_text:
                continue
            claims.append({"type": claim_type, "claim": claim})
    return claims


def _pack_text(pack: PublicInsightEvidencePack | None) -> str:
    if pack is None:
        return ""
    chunks: list[str] = [
        pack.topic_label,
        " ".join(pack.key_phrases),
        " ".join(pack.allowed_action_catalog),
    ]
    if pack.region_summary:
        chunks.append(_json_like(pack.region_summary))
    if pack.department_summary:
        chunks.append(_json_like(pack.department_summary))
    for complaint in pack.representative_complaints:
        chunks.append(str(complaint.get("masked_text") or ""))
        elements = complaint.get("structured_elements") or {}
        if isinstance(elements, dict):
            for value in elements.values():
                if isinstance(value, dict):
                    chunks.append(str(value.get("text") or ""))
    return " ".join(chunks)


def _json_like(value: dict[str, Any]) -> str:
    """간단한 dict 근거 텍스트 변환."""

    return " ".join(str(item) for item in value.values())


def _visible_text(insight: PublicAgencyInsight) -> str:
    chunks = [
        insight.title,
        insight.summary,
        insight.problem_diagnosis,
        insight.explanation,
        insight.expected_impact or "",
        " ".join(insight.uncertainty),
        " ".join(action.action for action in insight.recommended_actions),
        " ".join(action.why for action in insight.recommended_actions),
        " ".join(action.expected_impact or "" for action in insight.recommended_actions),
        " ".join(action.risk_or_dependency or "" for action in insight.recommended_actions),
        " ".join(evidence.masked_text for evidence in insight.evidence),
    ]
    return " ".join(chunks)


def _is_abstract_only(text: str) -> bool:
    tokens = [token for token in re.split(r"[\s,./]+", text) if token]
    meaningful = [token for token in tokens if len(token) >= 2]
    if not meaningful:
        return True
    abstract_hits = sum(1 for token in meaningful if token in ABSTRACT_ONLY_TERMS or token.rstrip("합니다") in ABSTRACT_ONLY_TERMS)
    return abstract_hits > 0 and len(meaningful) <= 3


def _quality_score(
    failures: list[QualityGateFailure],
    warnings: list[QualityGateFailure],
    insight: PublicAgencyInsight,
    min_actionability: float,
) -> float:
    base = min(insight.grounding_score, insight.confidence, min_actionability if insight.recommended_actions else 0.0)
    penalty = min(0.7, 0.18 * len(failures) + 0.05 * len(warnings))
    return round(max(0.0, min(1.0, base - penalty)), 4)


def _failure(code: str, message: str, details: dict[str, Any] | None = None) -> QualityGateFailure:
    return QualityGateFailure(code=code, message=message, severity="error", details=details or {})


def _warning(code: str, message: str, details: dict[str, Any] | None = None) -> QualityGateFailure:
    return QualityGateFailure(code=code, message=message, severity="warning", details=details or {})

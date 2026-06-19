"""중복 민원 병합 추천 read-model 스키마."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


DuplicateMergeStatus = Literal["candidate", "confirmed", "split", "rejected"]
DuplicateRecommendationLevel = Literal["weak", "review", "strong"]
DuplicateAction = Literal["confirm", "split", "reject", "draft_reply"]
DuplicateRiskSeverity = Literal["info", "warning", "blocker"]
DuplicateRiskCode = Literal[
    "LOCATION_MISMATCH",
    "LOCATION_AMBIGUOUS",
    "REQUEST_TYPE_MISMATCH",
    "DEPARTMENT_MISMATCH",
    "SAFETY_AND_INCONVENIENCE_MIXED",
    "LEGAL_RIGHTS_OR_DEADLINE_RISK",
    "PII_RISK",
    "MULTI_INTENT_SEGMENTS",
    "SEMANTIC_ONLY_MATCH",
    "LOW_EVIDENCE",
    "TIME_WINDOW_TOO_WIDE",
]
DuplicateLocationState = Literal["exact", "nearby", "ambiguous", "missing", "conflict"]
DuplicateRequestType = Literal[
    "enforcement",
    "compensation",
    "facility_improvement",
    "safety_action",
    "inquiry",
    "guidance",
    "other",
]


class DuplicateEvidence(BaseModel):
    """병합 후보를 설명하는 점수/규칙 근거."""

    type: str
    message: str
    affected_case_ids: list[str] = Field(default_factory=list)
    value: Optional[float | int | str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class DuplicateRiskFlag(BaseModel):
    """담당자가 병합 전 검토해야 하는 위험 신호."""

    code: DuplicateRiskCode
    severity: DuplicateRiskSeverity
    message: str
    affected_case_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DuplicateRepresentative(BaseModel):
    """대표 민원과 선정 사유."""

    complaint_id: str
    selection_reason: str
    quality_score: float


class DuplicateMergeRecord(BaseModel):
    """candidate와 confirmed가 공유하는 병합 추천 리소스."""

    merge_id: str
    status: DuplicateMergeStatus = "candidate"
    representative_complaint_id: str
    member_complaint_ids: list[str]
    confidence: float
    recommendation_level: DuplicateRecommendationLevel
    recommended_decision: Literal["REVIEW_BEFORE_MERGE"] = "REVIEW_BEFORE_MERGE"
    evidence: list[DuplicateEvidence] = Field(default_factory=list)
    risk_flags: list[DuplicateRiskFlag] = Field(default_factory=list)
    allowed_actions: list[DuplicateAction] = Field(default_factory=list)
    blocked_actions: list[DuplicateAction] = Field(default_factory=list)
    linked_issue_alert_ids: list[str] = Field(default_factory=list)
    linked_public_insight_ids: list[str] = Field(default_factory=list)
    representative: DuplicateRepresentative
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    location_state: DuplicateLocationState
    request_types: dict[str, DuplicateRequestType] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DraftReplyMemberSummary(BaseModel):
    """BE3 대표 답변 초안에 넘길 구성 민원 요약."""

    complaint_id: str
    pii_safe_summary: str
    structured_elements: dict[str, str] = Field(default_factory=dict)
    request_segments: list[str] = Field(default_factory=list)
    responsible_unit: list[str] = Field(default_factory=list)
    civil_category: Optional[str] = None
    entity_texts: list[str] = Field(default_factory=list)


class DraftReplyPayload(BaseModel):
    """confirmed 그룹에 대해서만 생성되는 BE3 전달 payload."""

    merge_id: str
    representative_complaint_id: str
    member_complaint_ids: list[str]
    representative: DraftReplyMemberSummary
    members: list[DraftReplyMemberSummary]
    merge_evidence: list[DuplicateEvidence]
    risk_flags: list[DuplicateRiskFlag]
    system_instruction: str
    common_reply_constraints: list[str]
    prohibited_content_rules: list[str]

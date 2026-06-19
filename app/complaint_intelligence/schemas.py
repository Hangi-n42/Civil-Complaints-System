"""Complaint Intelligence Layer 공통 스키마."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.complaint_intelligence.pii import mask_pii


PublicInsightType = Literal[
    "HOTSPOT_RESPONSE_REQUIRED",
    "SAFETY_RISK_SIGNAL",
    "RECURRING_COMPLAINT_PATTERN",
    "REGIONAL_SERVICE_GAP",
    "DEPARTMENT_WORKLOAD_BOTTLENECK",
    "PROCESS_DELAY_RISK",
    "REOPEN_OR_REPEAT_RISK",
    "SEASONAL_OR_TIME_PATTERN",
    "PUBLIC_GUIDANCE_NEEDED",
    "FACILITY_MAINTENANCE_PRIORITY",
    "ENFORCEMENT_PRIORITY",
    "POLICY_IMPROVEMENT_OPPORTUNITY",
    "SERVICE_DESIGN_IMPROVEMENT",
    "ACCESSIBILITY_OR_USABILITY_ISSUE",
    "CITIZEN_COMMUNICATION_GAP",
]

InsightStatus = Literal["open", "acknowledged", "resolved", "dismissed"]
InsightPriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ActionHorizon = Literal["IMMEDIATE", "SHORT_TERM", "MID_TERM", "LONG_TERM"]
ActionType = Literal[
    "FIELD_INSPECTION",
    "SAFETY_NOTICE",
    "MAINTENANCE",
    "ENFORCEMENT",
    "PUBLIC_GUIDANCE",
    "SERVICE_DESIGN",
    "PROCESS_IMPROVEMENT",
    "POLICY_REVIEW",
    "STAFFING_OR_WORKLOAD_REVIEW",
    "CITIZEN_COMMUNICATION",
]
SupportLevel = Literal["LOW", "MEDIUM", "HIGH"]
Sentiment = Literal["negative", "neutral", "mixed"]
CitizenRequestType = Literal[
    "정보 제공",
    "절차 개선",
    "현장 점검",
    "시설 보수",
    "단속 강화",
    "기준 완화",
    "지원 확대",
    "서비스 개선",
    "처리 속도 개선",
    "소통 강화",
]


class RagTrace(BaseModel):
    """기존 파이프라인 관측값을 받기 위한 호환 필드."""

    doc_ids: List[str] = Field(default_factory=list)
    scores: List[float] = Field(default_factory=list)
    query: Optional[str] = None
    retrieval_score: Optional[float] = None


class EvaluationTrace(BaseModel):
    """기존 평가 결과 호환 필드다. 공공 인사이트 판단 기준으로는 쓰지 않는다."""

    score: Optional[float] = None
    rubric: Optional[str] = None
    failure_reasons: List[str] = Field(default_factory=list)

    @field_validator("failure_reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split("|") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class StructuredComplaintElement(BaseModel):
    """기존 구조화 파이프라인의 단일 4요소 필드."""

    model_config = ConfigDict(extra="ignore")

    text: str = ""
    confidence: Optional[float] = None
    evidence_span: List[int] = Field(default_factory=list)
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_element(cls, data: Any) -> Any:
        if data is None:
            return {"text": ""}
        if isinstance(data, str):
            return {"text": mask_pii(data).text}
        if isinstance(data, dict):
            payload = dict(data)
            raw_text = payload.get("text") or payload.get("value") or ""
            masked = mask_pii(str(raw_text))
            payload["text"] = masked.text
            return payload
        return {"text": mask_pii(str(data)).text}


class StructuredComplaintElements(BaseModel):
    """observation/result/request/context 4요소의 선택 입력 컨테이너."""

    model_config = ConfigDict(extra="ignore")

    observation: Optional[StructuredComplaintElement] = None
    result: Optional[StructuredComplaintElement] = None
    request: Optional[StructuredComplaintElement] = None
    context: Optional[StructuredComplaintElement] = None

    def has_any_text(self) -> bool:
        return any(
            element is not None and bool(element.text.strip())
            for element in (self.observation, self.result, self.request, self.context)
        )


class RepresentativeComplaint(BaseModel):
    """대시보드에 노출 가능한 마스킹 민원 요약."""

    id: str
    masked_text: str
    region: Optional[str] = None
    received_at: datetime


class ComplaintIntelligenceEvent(BaseModel):
    """기존 민원 처리 흐름 옆에서 수집되는 공공 인사이트 분석 이벤트."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    title: Optional[str] = None
    body: Optional[str] = None
    masked_text: str = ""
    predicted_category: Optional[str] = None
    final_category: Optional[str] = None
    predicted_department: Optional[str] = None
    final_department: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None
    handling_time_minutes: Optional[float] = None
    reopened: bool = False
    escalated: bool = False
    user_feedback_score: Optional[float] = None
    reviewer_feedback: Optional[str] = None
    rag: RagTrace = Field(default_factory=RagTrace)
    answer: Optional[str] = None
    evaluation: EvaluationTrace = Field(default_factory=EvaluationTrace)
    feedback: Optional[str] = None
    structured_elements: StructuredComplaintElements = Field(default_factory=StructuredComplaintElements)
    embedding: Optional[List[float]] = None
    pipeline_version: Optional[str] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    pii_status: str = "PASSED"
    pii_detected: bool = False
    pii_labels: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        # legacy alias 후보가 있을 때만 채워 기본값 생성을 방해하지 않는다.
        if "id" not in payload:
            event_id = payload.get("complaint_id") or payload.get("case_id") or payload.get("source_id")
            if event_id is not None:
                payload["id"] = event_id
        if "received_at" not in payload:
            received_at = payload.get("created_at") or payload.get("submitted_at")
            if received_at is not None:
                payload["received_at"] = received_at
        if "body" not in payload:
            body = payload.get("raw_text") or payload.get("text") or payload.get("consulting_content")
            if body is not None:
                payload["body"] = body
        if "handling_time_minutes" not in payload:
            handling_time = payload.get("processing_time_minutes") or payload.get("elapsed_minutes")
            if handling_time is not None:
                payload["handling_time_minutes"] = handling_time

        structured_source = payload.get("structured_elements") or payload.get("structured_text")
        structured_elements = dict(structured_source) if isinstance(structured_source, dict) else {}
        for field in ("observation", "result", "request", "context"):
            if field in payload and payload.get(field) is not None:
                structured_elements[field] = payload.get(field)
        if structured_elements:
            payload["structured_elements"] = structured_elements

        detected: list[str] = []
        for field in ("title", "body", "masked_text", "answer", "feedback", "reviewer_feedback"):
            if field in payload and payload.get(field) is not None:
                masked = mask_pii(str(payload.get(field)))
                payload[field] = masked.text
                detected.extend(masked.detected_labels)

        if not str(payload.get("masked_text") or "").strip():
            combined = " ".join(
                str(payload.get(field) or "").strip()
                for field in ("title", "body")
                if str(payload.get(field) or "").strip()
            )
            masked = mask_pii(combined)
            payload["masked_text"] = masked.text
            detected.extend(masked.detected_labels)

        if detected:
            payload["pii_detected"] = True
            payload["pii_labels"] = sorted(set(detected))
            payload.setdefault("pii_status", "MASKED")
        return payload

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("ComplaintIntelligenceEvent.id는 필수입니다.")
        return cleaned


class IssueAlert(BaseModel):
    """민원 핫스팟 이슈 경보."""

    id: str
    status: Literal["ACTIVE", "UPDATED", "RESOLVED"] = "ACTIVE"
    severity: Literal["WATCH", "WARNING", "CRITICAL"]
    title: str
    summary: str
    topic: str
    keywords: List[str] = Field(default_factory=list)
    region: Optional[str] = None
    center: Optional[Dict[str, float]] = None
    radius: Optional[float] = None
    recent_count: int
    baseline: float
    surge_ratio: float
    first_seen: datetime
    last_seen: datetime
    representative_complaints: List[RepresentativeComplaint] = Field(default_factory=list)
    related_ids: List[str] = Field(default_factory=list)
    confidence: float
    explanation: str
    linked_insight_ids: List[str] = Field(default_factory=list)


class PublicInsightEvidence(BaseModel):
    """공공기관 인사이트의 근거 민원."""

    complaint_id: str
    source_complaint_ids: List[str] = Field(default_factory=list)
    masked_text: str
    region: Optional[str] = None
    received_at: datetime
    department: Optional[str] = None
    status: Optional[str] = None
    structured_elements: Dict[str, Any] = Field(default_factory=dict)
    metric: Optional[str] = None
    value: Optional[float | int | str] = None


class ExtractedAspect(BaseModel):
    """민원 클러스터에서 반복되는 세부 불편 측면."""

    aspect: str
    count: int
    sentiment: Sentiment = "negative"
    evidence_ids: List[str] = Field(default_factory=list)
    representative_phrases: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence_spans: List[Dict[str, Any]] = Field(default_factory=list)


class CitizenRequest(BaseModel):
    """민원에서 추출한 시민 요구."""

    request: str
    count: int
    evidence_ids: List[str] = Field(default_factory=list)
    request_type: CitizenRequestType
    confidence: Optional[float] = None
    evidence_spans: List[Dict[str, Any]] = Field(default_factory=list)


class RootCauseHypothesis(BaseModel):
    """확정 원인이 아닌 검증 필요 가설."""

    hypothesis: str
    support_level: SupportLevel
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    needs_human_validation: bool = True


class RecommendedAction(BaseModel):
    """공공기관 담당자가 실행할 수 있는 구조화된 조치."""

    action: str
    horizon: ActionHorizon
    action_type: ActionType
    responsible_unit_hint: Optional[str] = None
    why: str
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    expected_impact: Optional[str] = None
    risk_or_dependency: Optional[str] = None


class PublicAgencyInsight(BaseModel):
    """민원 데이터에서 도출한 공공기관 행정 대응 인사이트."""

    insight_id: str
    id: Optional[str] = None
    type: PublicInsightType
    status: InsightStatus = "open"
    priority: InsightPriority
    title: str
    summary: str
    problem_diagnosis: str
    topic: str
    target_area: str
    affected_region: Optional[Dict[str, Any]] = None
    related_department: Optional[str] = None
    affected_count: int
    window_start: datetime
    window_end: datetime
    window: Optional[Dict[str, datetime]] = None
    metrics: Dict[str, float | int | str] = Field(default_factory=dict)
    extracted_aspects: List[ExtractedAspect] = Field(default_factory=list)
    citizen_requests: List[CitizenRequest] = Field(default_factory=list)
    root_cause_hypotheses: List[RootCauseHypothesis] = Field(default_factory=list)
    evidence: List[PublicInsightEvidence] = Field(default_factory=list)
    representative_complaint_ids: List[str] = Field(default_factory=list)
    representative_ids: List[str] = Field(default_factory=list)
    linked_alert_ids: List[str] = Field(default_factory=list)
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)
    recommended_action_texts: List[str] = Field(default_factory=list)
    expected_impact: Optional[str] = None
    uncertainty: List[str] = Field(default_factory=list)
    requires_human_review: bool
    confidence: float
    grounding_score: float
    created_at: datetime
    updated_at: Optional[datetime] = None
    explanation: str

    @model_validator(mode="after")
    def fill_compatibility_fields(self) -> "PublicAgencyInsight":
        if not self.id:
            self.id = self.insight_id
        if self.window is None:
            self.window = {"start": self.window_start, "end": self.window_end}
        if not self.representative_ids:
            self.representative_ids = list(self.representative_complaint_ids)
        if not self.recommended_action_texts:
            self.recommended_action_texts = [action.action for action in self.recommended_actions]
        return self

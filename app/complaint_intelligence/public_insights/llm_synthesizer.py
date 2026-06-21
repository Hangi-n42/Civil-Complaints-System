"""EvidencePack을 LLM JSON 초안으로 합성한다."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.complaint_intelligence.public_insights.action_rubric import allowed_action_types_for_pack, preferred_action_types_for_pack
from app.complaint_intelligence.public_insights.evidence_pack import (
    PublicInsightEvidencePack,
    evidence_pack_for_llm,
    valid_evidence_ids_for_pack,
)
from app.complaint_intelligence.public_insights.llm_provider import PublicInsightLLMError, PublicInsightLLMProvider
from app.complaint_intelligence.schemas import (
    CitizenRequest,
    ExtractedAspect,
    RecommendedAction,
    RootCauseHypothesis,
)


class PublicAgencyInsightDraft(BaseModel):
    """LLM이 생성하는 검증 전 인사이트 초안."""

    title: str
    summary: str
    problem_diagnosis: str
    root_cause_hypotheses: list[RootCauseHypothesis] = Field(default_factory=list)
    extracted_aspects: list[ExtractedAspect] = Field(default_factory=list)
    citizen_requests: list[CitizenRequest] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    expected_impact: str | None = None
    uncertainty: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    explanation: str


class PublicInsightLLMSynthesizer:
    """엄격한 프롬프트와 schema validation으로 LLM 초안을 만든다."""

    def __init__(self, provider: PublicInsightLLMProvider, *, prompt_mode: str = "default") -> None:
        self.provider = provider
        self.prompt_mode = prompt_mode if prompt_mode in {"default", "compact"} else "default"

    def synthesize(self, pack: PublicInsightEvidencePack) -> PublicAgencyInsightDraft:
        prompt = self._build_prompt(pack)
        schema = (
            _compact_output_schema(allowed_action_types_for_pack(pack))
            if self.prompt_mode == "compact"
            else PublicAgencyInsightDraft.model_json_schema()
        )
        payload = self.provider.generate_json(prompt, schema)
        if self.prompt_mode == "compact":
            payload = _normalize_llm_payload(payload)
        try:
            return PublicAgencyInsightDraft.model_validate(payload)
        except ValidationError as exc:
            raise PublicInsightLLMError("LLM_SCHEMA_VALIDATION_FAILED", "PUBLIC_INSIGHT_DRAFT_SCHEMA_INVALID") from exc

    def synthesize_actions(
        self,
        draft: PublicAgencyInsightDraft,
        pack: PublicInsightEvidencePack,
    ) -> list[RecommendedAction]:
        """기존 초안은 유지하고 recommended_actions만 한 번 재생성한다."""

        payload = self.provider.generate_json(
            self._build_action_retry_prompt(draft, pack),
            _action_retry_schema(allowed_action_types_for_pack(pack)),
        )
        payload = _normalize_llm_payload(payload)
        try:
            return [
                RecommendedAction.model_validate(item)
                for item in list(payload.get("recommended_actions") or [])[:2]
                if isinstance(item, dict)
            ]
        except ValidationError as exc:
            raise PublicInsightLLMError("LLM_SCHEMA_VALIDATION_FAILED", "PUBLIC_INSIGHT_ACTION_SCHEMA_INVALID") from exc

    def _build_prompt(self, pack: PublicInsightEvidencePack) -> str:
        if self.prompt_mode == "compact":
            return self._build_compact_prompt(pack)

        rules = """
너는 공공기관 민원 데이터 분석가다.
아래 EVIDENCE_PACK에 포함된 정보만 사용해 행정 개선 인사이트를 생성하라.

규칙:
1. EVIDENCE_PACK에 없는 사실을 만들지 마라.
2. 수치, 건수, 비율, 기간은 EVIDENCE_PACK의 값만 사용하라.
3. 원인 분석은 확정 사실이 아니라 가설로 표현하라.
4. 모든 추천 조치는 supporting_evidence_ids를 가져야 한다.
5. 법적 판단, 예산 규모, 정책 시행 여부를 단정하지 마라.
6. 개인정보를 복원하거나 추정하지 마라.
7. 시민 표현을 행정 조치 언어로 바꾸되 근거 민원 ID를 유지하라.
8. 단기/중기/장기 조치를 구분하라.
9. 현장 조치, 안내 개선, 제도 검토, 서비스 설계 개선을 구분하라.
10. JSON schema에 맞는 JSON만 출력하라.
11. root_cause_hypotheses는 최대 2개, extracted_aspects는 최대 3개, citizen_requests는 최대 3개, recommended_actions는 최대 3개만 출력하라.
12. 각 문자열은 120자 이내로 짧게 작성하라.
13. 설명 문단을 길게 쓰지 말고, EvidencePack의 수치와 evidence_id만 간결히 사용하라.

출력 JSON 최상위 키는 반드시 아래 11개만 사용하라.
{
  "title": "문자열",
  "summary": "문자열",
  "problem_diagnosis": "문자열",
  "root_cause_hypotheses": [
    {
      "hypothesis": "단정이 아닌 가설 문장",
      "support_level": "LOW|MEDIUM|HIGH",
      "supporting_evidence_ids": ["EvidencePack에 있는 complaint_id"],
      "needs_human_validation": true
    }
  ],
  "extracted_aspects": [
    {
      "aspect": "EvidencePack의 aspect",
      "count": 1,
      "sentiment": "negative|neutral|mixed",
      "evidence_ids": ["EvidencePack에 있는 complaint_id"],
      "representative_phrases": ["근거 문구"]
    }
  ],
  "citizen_requests": [
    {
      "request": "시민 요구",
      "count": 1,
      "evidence_ids": ["EvidencePack에 있는 complaint_id"],
      "request_type": "정보 제공|절차 개선|현장 점검|시설 보수|단속 강화|기준 완화|지원 확대|서비스 개선|처리 속도 개선|소통 강화"
    }
  ],
  "recommended_actions": [
    {
      "action": "구체적 행정 조치",
      "horizon": "IMMEDIATE|SHORT_TERM|MID_TERM|LONG_TERM",
      "action_type": "FIELD_INSPECTION|SAFETY_NOTICE|MAINTENANCE|ENFORCEMENT|PUBLIC_GUIDANCE|SERVICE_DESIGN|PROCESS_IMPROVEMENT|POLICY_REVIEW|STAFFING_OR_WORKLOAD_REVIEW|CITIZEN_COMMUNICATION",
      "responsible_unit_hint": null,
      "why": "근거 기반 이유",
      "supporting_evidence_ids": ["EvidencePack에 있는 complaint_id"],
      "expected_impact": "기대 효과",
      "risk_or_dependency": "위험 또는 의존성"
    }
  ],
  "expected_impact": "문자열 또는 null",
  "uncertainty": ["불확실성"],
  "requires_human_review": true,
  "explanation": "EvidencePack의 어떤 근거를 사용했는지 설명"
}
"""
        return f"{rules}\nEVIDENCE_PACK_JSON:\n{json.dumps(evidence_pack_for_llm(pack), ensure_ascii=False, default=str)}"

    def _build_compact_prompt(self, pack: PublicInsightEvidencePack) -> str:
        compact_pack = evidence_pack_for_llm(pack, compact=True, max_representative_complaints=3, max_text_chars=120)
        rules = """
너는 공공기관 민원 데이터 분석가다. 아래 EVIDENCE_PACK_JSON만 근거로 JSON 하나만 출력하라.

절대 규칙:
- JSON 외 설명, markdown fence, 주석을 쓰지 마라.
- EVIDENCE_PACK_JSON에 없는 수치, 법령, 예산, 사업명, 사람 이름을 만들지 마라.
- evidence_ids/supporting_evidence_ids는 VALID_EVIDENCE_IDS 배열에 있는 값을 그대로 복사하라.
- 새 evidence id를 만들지 마라.
- evidence id를 요약하거나 변형하지 마라.
- 각 recommended_action은 최소 1개 supporting_evidence_ids를 가져야 한다.
- 근거 ID를 고를 수 없으면 해당 action을 만들지 마라.
- extracted_aspects와 citizen_requests는 EVIDENCE_PACK_JSON 항목을 최대 3개 재사용하라.
- root_cause_hypotheses는 최대 1개, recommended_actions는 가능하면 1개만 작성하라.
- evidence_ids와 supporting_evidence_ids는 각 항목당 최대 2개만 작성하라.
- recommended_actions[*].action_type은 반드시 ALLOWED_ACTION_TYPES 배열 중 하나만 사용하라.
- ALLOWED_ACTION_TYPES 밖의 action_type을 만들지 마라.
- action_type을 번역하거나 변형하지 마라.
- 적절한 action_type이 없으면 action을 만들지 마라.
- preferred_action_types가 있으면 우선 사용하라.
- 모든 문자열은 80자 이내로 짧게 작성하라.
- 원인은 확정하지 말고 가능성/가설로 표현하라.
- 정책/안전/서비스 변경은 requires_human_review=true로 둔다.
- horizon 값은 IMMEDIATE, SHORT_TERM, MID_TERM, LONG_TERM 중 하나만 사용하라.
- action_type 값은 FIELD_INSPECTION, SAFETY_NOTICE, MAINTENANCE, ENFORCEMENT,
  PUBLIC_GUIDANCE, SERVICE_DESIGN, PROCESS_IMPROVEMENT, POLICY_REVIEW,
  STAFFING_OR_WORKLOAD_REVIEW, CITIZEN_COMMUNICATION 중 하나만 사용하라.

출력 키:
title, summary, problem_diagnosis, root_cause_hypotheses, extracted_aspects,
citizen_requests, recommended_actions, expected_impact, uncertainty,
requires_human_review, explanation

recommended_actions 항목 형식:
action, horizon, action_type, responsible_unit_hint, why,
supporting_evidence_ids, expected_impact, risk_or_dependency
"""
        valid_ids = valid_evidence_ids_for_pack(pack, max_ids=20)
        allowed_action_types = allowed_action_types_for_pack(pack)
        preferred_action_types = [item for item in preferred_action_types_for_pack(pack) if item in allowed_action_types]
        return (
            f"{rules}\nVALID_EVIDENCE_IDS:\n{json.dumps(valid_ids, ensure_ascii=False)}"
            f"\nALLOWED_ACTION_TYPES:\n{json.dumps(allowed_action_types, ensure_ascii=False)}"
            f"\nPREFERRED_ACTION_TYPES:\n{json.dumps(preferred_action_types, ensure_ascii=False)}"
            f"\nEVIDENCE_PACK_JSON:\n{json.dumps(compact_pack, ensure_ascii=False, default=str)}"
        )

    def _build_action_retry_prompt(self, draft: PublicAgencyInsightDraft, pack: PublicInsightEvidencePack) -> str:
        compact_pack = evidence_pack_for_llm(pack, compact=True, max_representative_complaints=3, max_text_chars=120)
        allowed_action_types = allowed_action_types_for_pack(pack)
        preferred_action_types = [item for item in preferred_action_types_for_pack(pack) if item in allowed_action_types]
        context = {
            "title": draft.title[:100],
            "summary": draft.summary[:160],
            "problem_diagnosis": draft.problem_diagnosis[:180],
            "type_hint": pack.type_hint,
            "allowed_action_catalog": pack.allowed_action_catalog[:6],
            "allowed_action_types": allowed_action_types,
            "preferred_action_types": preferred_action_types,
            "valid_evidence_ids": valid_evidence_ids_for_pack(pack, max_ids=20),
            "extracted_aspects": compact_pack.get("extracted_aspects", [])[:3],
            "citizen_requests": compact_pack.get("citizen_requests", [])[:3],
            "representative_complaints": compact_pack.get("representative_complaints", [])[:4],
        }
        rules = """
추천 조치만 다시 생성하라. JSON 하나만 출력하라.

규칙:
- recommended_actions만 출력하라.
- supporting_evidence_ids는 valid_evidence_ids 배열의 값을 그대로 복사하라.
- 새 evidence id를 만들거나 변형하지 마라.
- 근거 ID를 고를 수 없으면 action을 만들지 마라.
- recommended_actions는 최대 1개만 출력하라.
- action_type은 allowed_action_types 중 하나만 사용하라.
- preferred_action_types가 있으면 우선 사용하라.
- action_type과 horizon은 schema enum만 사용하라.
- action은 공공기관 담당자가 실행할 수 있는 구체 조치여야 한다.
"""
        return f"{rules}\nACTION_RETRY_CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False, default=str)}"


def draft_to_json(draft: PublicAgencyInsightDraft) -> dict[str, Any]:
    """테스트와 디버깅용 JSON 변환."""

    return json.loads(draft.model_dump_json())


def _compact_output_schema(allowed_action_types: list[str] | None = None) -> dict[str, Any]:
    """Ollama format에 전달할 단순 JSON schema를 만든다."""

    action_types = allowed_action_types or [
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
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "summary",
            "problem_diagnosis",
            "root_cause_hypotheses",
            "extracted_aspects",
            "citizen_requests",
            "recommended_actions",
            "expected_impact",
            "uncertainty",
            "requires_human_review",
            "explanation",
        ],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "problem_diagnosis": {"type": "string"},
            "root_cause_hypotheses": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "required": ["hypothesis", "support_level", "supporting_evidence_ids", "needs_human_validation"],
                    "properties": {
                        "hypothesis": {"type": "string"},
                        "support_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                        "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "needs_human_validation": {"type": "boolean"},
                    },
                },
            },
            "extracted_aspects": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["aspect", "count", "sentiment", "evidence_ids", "representative_phrases"],
                    "properties": {
                        "aspect": {"type": "string"},
                        "count": {"type": "integer"},
                        "sentiment": {"type": "string", "enum": ["negative", "neutral", "mixed"]},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "representative_phrases": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "citizen_requests": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["request", "count", "evidence_ids", "request_type"],
                    "properties": {
                        "request": {"type": "string"},
                        "count": {"type": "integer"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "request_type": {"type": "string"},
                    },
                },
            },
            "recommended_actions": {
                "type": "array",
                "maxItems": 1,
                "items": {
                    "type": "object",
                    "required": [
                        "action",
                        "horizon",
                        "action_type",
                        "responsible_unit_hint",
                        "why",
                        "supporting_evidence_ids",
                        "expected_impact",
                        "risk_or_dependency",
                    ],
                    "properties": {
                        "action": {"type": "string"},
                        "horizon": {"type": "string", "enum": ["IMMEDIATE", "SHORT_TERM", "MID_TERM", "LONG_TERM"]},
                        "action_type": {
                            "type": "string",
                            "enum": action_types,
                        },
                        "responsible_unit_hint": {"type": ["string", "null"]},
                        "why": {"type": "string"},
                        "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "expected_impact": {"type": ["string", "null"]},
                        "risk_or_dependency": {"type": ["string", "null"]},
                    },
                },
            },
            "expected_impact": {"type": ["string", "null"]},
            "uncertainty": {"type": "array", "items": {"type": "string"}},
            "requires_human_review": {"type": "boolean"},
            "explanation": {"type": "string"},
        },
    }


def _action_retry_schema(allowed_action_types: list[str] | None = None) -> dict[str, Any]:
    """action-only retry용 단순 JSON schema."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["recommended_actions"],
        "properties": {
            "recommended_actions": _compact_output_schema(allowed_action_types)["properties"]["recommended_actions"],
        },
    }


def _normalize_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM이 한국어 enum 라벨을 낸 경우 안전한 고정 매핑만 적용한다."""

    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    requests: list[dict[str, Any]] = []
    for item in list(payload.get("citizen_requests") or [])[:3]:
        if not isinstance(item, dict):
            continue
        request = dict(item)
        request["request_type"] = _normalize_request_type(request.get("request_type"), request.get("request"))
        request["evidence_ids"] = list(request.get("evidence_ids") or [])[:3]
        requests.append(request)
    normalized["citizen_requests"] = requests
    actions: list[dict[str, Any]] = []
    for item in list(payload.get("recommended_actions") or [])[:2]:
        if not isinstance(item, dict):
            continue
        action = dict(item)
        action["horizon"] = _normalize_horizon(action.get("horizon"))
        action["action_type"] = _normalize_action_type(action.get("action_type"), action.get("action"))
        action["supporting_evidence_ids"] = list(action.get("supporting_evidence_ids") or [])[:3]
        actions.append(action)
    normalized["recommended_actions"] = actions
    return normalized


def _normalize_request_type(value: Any, request_text: Any = "") -> str:
    text = f"{value or ''} {request_text or ''}"
    raw = str(value or "").strip()
    allowed = {
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
    }
    if raw in allowed:
        return raw
    if any(keyword in text for keyword in ("신청", "절차")):
        return "절차 개선"
    if any(keyword in text for keyword in ("현장", "점검")):
        return "현장 점검"
    if any(keyword in text for keyword in ("보수", "수리", "정비")):
        return "시설 보수"
    if any(keyword in text for keyword in ("단속", "불법")):
        return "단속 강화"
    if any(keyword in text for keyword in ("완화", "기준")):
        return "정보 제공" if "안내" in text else "기준 완화"
    if any(keyword in text for keyword in ("확대", "지원")):
        return "지원 확대"
    if any(keyword in text for keyword in ("앱", "서비스", "예약", "대여")):
        return "서비스 개선"
    if any(keyword in text for keyword in ("지연", "속도")):
        return "처리 속도 개선"
    if any(keyword in text for keyword in ("소통", "연락", "진행")):
        return "소통 강화"
    return "정보 제공"


def _normalize_horizon(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "즉시": "IMMEDIATE",
        "즉시 조치": "IMMEDIATE",
        "긴급": "IMMEDIATE",
        "단기": "SHORT_TERM",
        "단기 조치": "SHORT_TERM",
        "중기": "MID_TERM",
        "중장기": "MID_TERM",
        "장기": "LONG_TERM",
    }
    if text in {"IMMEDIATE", "SHORT_TERM", "MID_TERM", "LONG_TERM"}:
        return text
    return mapping.get(text, "SHORT_TERM")


def _normalize_action_type(value: Any, action_text: Any = "") -> str:
    text = f"{value or ''} {action_text or ''}"
    raw = str(value or "").strip()
    allowed = {
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
    }
    if any(keyword in text for keyword in ("현장", "점검", "긴급")):
        return "FIELD_INSPECTION"
    if any(keyword in text for keyword in ("안전", "공지", "안내문")):
        return "SAFETY_NOTICE"
    if any(keyword in text for keyword in ("보수", "정비", "수리")):
        return "MAINTENANCE"
    if any(keyword in text for keyword in ("단속", "불법주정차")):
        return "ENFORCEMENT"
    if any(keyword in text for keyword in ("정보 제공", "안내", "FAQ", "고지")):
        return "PUBLIC_GUIDANCE"
    if any(keyword in text for keyword in ("앱", "예약", "UX", "서비스 개선", "이용 절차")):
        return "SERVICE_DESIGN"
    if any(keyword in text for keyword in ("정책", "제도", "기준", "완화")):
        return "POLICY_REVIEW"
    if any(keyword in text for keyword in ("인력", "업무", "부서")):
        return "STAFFING_OR_WORKLOAD_REVIEW"
    if any(keyword in text for keyword in ("소통", "연락", "진행 상황")):
        return "CITIZEN_COMMUNICATION"
    if raw in allowed:
        return raw
    return "PROCESS_IMPROVEMENT"

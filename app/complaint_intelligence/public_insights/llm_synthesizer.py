"""EvidencePack을 LLM JSON 초안으로 합성한다."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.llm_provider import PublicInsightLLMProvider
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

    def __init__(self, provider: PublicInsightLLMProvider) -> None:
        self.provider = provider

    def synthesize(self, pack: PublicInsightEvidencePack) -> PublicAgencyInsightDraft:
        prompt = self._build_prompt(pack)
        schema = PublicAgencyInsightDraft.model_json_schema()
        payload = self.provider.generate_json(prompt, schema)
        try:
            return PublicAgencyInsightDraft.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("PUBLIC_INSIGHT_DRAFT_SCHEMA_INVALID") from exc

    def _build_prompt(self, pack: PublicInsightEvidencePack) -> str:
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
        return f"{rules}\nEVIDENCE_PACK_JSON:\n{pack.model_dump_json()}"


def draft_to_json(draft: PublicAgencyInsightDraft) -> dict[str, Any]:
    """테스트와 디버깅용 JSON 변환."""

    return json.loads(draft.model_dump_json())

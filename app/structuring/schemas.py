"""구조화 모듈 공용 스키마"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel


class FourElementsLLMOutput(BaseModel):
    """LLM이 반환하는 4요소 추출 결과.

    None 필드는 해당 요소가 원문에 없거나 LLM이 추출하지 못했음을 의미한다.
    """

    observation: Optional[str] = None
    result: Optional[str] = None
    request: Optional[str] = None
    context: Optional[str] = None


@dataclass
class RuleBasedNERResult:
    """Stage 1 Rule-based NER 결과."""

    entities: List[Dict[str, str]] = field(default_factory=list)
    extraction_latency_ms: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Track A — 구조화 고도화 (① 스키마 제약 디코딩)
# 평탄 스키마(XGrammar/Ollama 친화). null 대신 빈 문자열, status·역할은 enum/평탄화.
# ──────────────────────────────────────────────────────────────────────────
try:  # pydantic v2
    from typing import Literal

    RESULT_STATUS = Literal["present", "pending", "insufficient"]

    class StructuredLLMOutput(BaseModel):
        """① 제약 디코딩으로 LLM이 채우는 구조화 출력.

        - 4요소(observation/result/request/context): 없으면 "" (null 회피 → XGrammar 안정).
        - result_status: 결과 상태 enum.
        - roles 평탄화: complainant(민원인) / respondent(유발자·대상) / target_object(조치객체).
        """

        observation: str = ""
        result: str = ""
        result_status: RESULT_STATUS = "insufficient"
        request: str = ""
        context: str = ""
        complainant: str = ""
        respondent: str = ""
        target_object: str = ""

        model_config = {"extra": "ignore"}


    # LLM 출력 스키마의 표준 필드 순서(프롬프트·검증 공용)
    STRUCTURED_TEXT_FIELDS = ["observation", "result", "request", "context"]
    STRUCTURED_ROLE_FIELDS = ["complainant", "respondent", "target_object"]


    def llm_output_json_schema() -> Dict:
        """Ollama `format`(XGrammar 제약 디코딩)에 넘길 JSON Schema dict.

        모든 키 required + additionalProperties=false 로 형식을 강하게 고정한다.
        """
        schema = StructuredLLMOutput.model_json_schema()
        schema["required"] = list(StructuredLLMOutput.model_fields.keys())
        schema["additionalProperties"] = False
        return schema

except Exception:  # pydantic 미가용 환경 방어
    StructuredLLMOutput = None  # type: ignore
    STRUCTURED_TEXT_FIELDS = ["observation", "result", "request", "context"]
    STRUCTURED_ROLE_FIELDS = ["complainant", "respondent", "target_object"]

    def llm_output_json_schema() -> Dict:  # type: ignore
        return {}

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

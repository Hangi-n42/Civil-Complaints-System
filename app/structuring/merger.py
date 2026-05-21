"""Stage 3: ResultMerger

Rule NER 결과(Stage 1)와 LLM 4요소(Stage 2)를 병합해
Unified Structured Record를 생성한다.

주요 역할:
  - LLM 추출 텍스트의 evidence_span 탐색 (exact → partial → inferred)
  - non-null 필드 비율 기반 confidence 산정
  - structured_by / extraction_meta 메타 필드 구성
"""

from __future__ import annotations

from typing import Dict, Tuple

from app.structuring.schemas import FourElementsLLMOutput, RuleBasedNERResult

# non-null 필드 수 → 4요소 confidence 테이블
_NON_NULL_TO_CONFIDENCE: Dict[int, float] = {
    4: 0.90,
    3: 0.82,
    2: 0.75,
    1: 0.70,
    0: 0.0,
}


def _find_span(raw_text: str, llm_text: str) -> Tuple[int, int, str]:
    """LLM 추출 텍스트를 원문에서 탐색해 (start, end, span_source) 반환.

    span_source:
      "exact"    - 원문에 그대로 존재
      "partial"  - 앞 30자 키로 근사 위치 탐색 성공
      "inferred" - 탐색 실패, span=[0, 0] 으로 설정
    """
    if not llm_text:
        return 0, 0, "inferred"

    # 1. 정확 매칭
    idx = raw_text.find(llm_text)
    if idx >= 0:
        return idx, idx + len(llm_text), "exact"

    # 2. 부분 매칭: 앞 30자를 키로 위치 탐색
    key = llm_text[:30]
    idx = raw_text.find(key)
    if idx >= 0:
        end = min(idx + len(llm_text), len(raw_text))
        return idx, end, "partial"

    return 0, 0, "inferred"


class ResultMerger:
    """Stage 1 + Stage 2 결과를 Unified Schema로 병합한다."""

    def merge(
        self,
        raw_text: str,
        ner_result: RuleBasedNERResult,
        llm_output: FourElementsLLMOutput,
        llm_latency_ms: int,
        llm_model: str,
    ) -> dict:
        """병합 결과 dict 반환.

        validate_schema() 는 StructuringService.structure() 에서 별도 호출한다.
        """
        llm_fields = {
            "observation": llm_output.observation,
            "result": llm_output.result,
            "request": llm_output.request,
            "context": llm_output.context,
        }
        non_null_count = sum(1 for v in llm_fields.values() if v is not None)
        field_confidence = _NON_NULL_TO_CONFIDENCE.get(non_null_count, 0.0)
        structured_by = "hybrid" if non_null_count > 0 else "fallback"

        built_fields: Dict[str, dict] = {}
        span_sources: Dict[str, str] = {}

        for fname, ftext in llm_fields.items():
            if ftext:
                start, end, source = _find_span(raw_text, ftext)
                conf = field_confidence
            else:
                start, end, source = 0, 0, "inferred"
                conf = 0.0

            span_sources[fname] = source

            if fname == "result":
                built_fields[fname] = {
                    "text": ftext or "",
                    "confidence": conf,
                    "evidence_span": [start, end],
                    "status": "present" if ftext else "pending",
                }
            else:
                built_fields[fname] = {
                    "text": ftext or "",
                    "confidence": conf,
                    "evidence_span": [start, end],
                }

        return {
            "observation": built_fields["observation"],
            "result": built_fields["result"],
            "request": built_fields["request"],
            "context": built_fields["context"],
            "entities": ner_result.entities,
            "structured_by": structured_by,
            "extraction_meta": {
                "llm_model": llm_model,
                "llm_latency_ms": llm_latency_ms,
                "ner_latency_ms": ner_result.extraction_latency_ms,
                "llm_non_null_count": non_null_count,
                "span_sources": span_sources,
            },
        }

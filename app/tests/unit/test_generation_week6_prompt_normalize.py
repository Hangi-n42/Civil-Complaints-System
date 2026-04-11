from __future__ import annotations

from app.generation.normalization.response_normalizer import (
    normalize_response,
    validate_unified_contract,
)
from app.generation.prompts.prompt_factory import PromptFactory


def test_prompt_factory_includes_routing_trace_guidance():
    prompt = PromptFactory.build(
        query="임대주택 보수 지연과 관리비 이의제기 관련 민원",
        context=[
            {
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "score": 0.9,
                "snippet": "관리비 이의제기 처리 절차 안내",
            }
        ],
        routing_trace={
            "topic_type": "welfare",
            "complexity_level": "high",
            "request_segments": ["보수 지연", "관리비 이의제기"],
        },
    )

    assert "복지 행정 맥락" in prompt
    assert "다중 쟁점을 분리" in prompt
    assert "섹션 1: 보수 지연" in prompt
    assert "섹션 2: 관리비 이의제기" in prompt


def test_normalize_response_enforces_week6_shape():
    payload = normalize_response(
        {
            "answer": "답변 초안",
            "citations": [{"case_id": "CASE-1", "snippet": "근거 문장"}],
            "limitations": "현장 확인 필요",
        }
    )

    assert isinstance(payload["routing_trace"], dict)
    assert set(payload["structured_output"].keys()) == {"summary", "action_items", "request_segments"}
    assert isinstance(payload["citations"], list)
    assert isinstance(payload["limitations"], list)
    assert set(payload["latency_ms"].keys()) == {"analyzer", "router", "retrieval", "generation"}
    assert set(payload["quality_signals"].keys()) == {
        "citation_coverage",
        "hallucination_flag",
        "segment_coverage",
    }


def test_validate_unified_contract_detects_missing():
    missing = validate_unified_contract({"answer": "x"})
    assert "routing_trace" in missing
    assert "structured_output" in missing
    assert "quality_signals" in missing

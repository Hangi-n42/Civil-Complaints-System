from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.core.exceptions import GenerationError
from app.generation.service import GenerationService


CONTEXT = [
    {
        "doc_id": "DOC-1",
        "chunk_id": "CASE-1__chunk-0",
        "case_id": "CASE-1",
        "snippet": "접수 후 담당부서에서 사실관계와 처리 기준을 검토합니다.",
        "score": 0.9,
    }
]


def _valid_response() -> str:
    return json.dumps(
        {
            "answer": "담당부서에서 사실관계와 처리 기준을 검토하겠습니다.",
            "citations": [
                {
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "접수 후 담당부서에서 사실관계와 처리 기준을 검토합니다.",
                    "relevance_score": 0.9,
                }
            ],
            "limitations": "현장 확인 결과에 따라 처리 방향이 달라질 수 있습니다.",
            "structured_output": {
                "summary": "처리 기준 검토 요청",
                "action_items": ["사실관계 확인", "처리 기준 검토"],
                "request_segments": ["처리 기준 검토 요청"],
            },
        },
        ensure_ascii=False,
    )


def test_generation_ollama_budget_matches_week6_benchmark_defaults():
    assert settings.GENERATION_NUM_PREDICT == 768
    assert settings.GENERATION_NUM_CTX == 2048


@pytest.mark.asyncio
async def test_generate_qa_reports_retry_then_force_json_success(monkeypatch):
    service = GenerationService()
    responses = iter(["not-json", _valid_response()])

    async def fake_build_rag_prompt(query, context, routing_trace=None, mode="default"):
        return f"mode={mode}"

    async def fake_call_ollama(prompt, temperature=0.7):
        return next(responses)

    monkeypatch.setattr(service, "build_rag_prompt", fake_build_rag_prompt)
    monkeypatch.setattr(service, "call_ollama", fake_call_ollama)

    result = await service.generate_qa("처리 기준을 알려주세요.", CONTEXT)

    assert result["generation_metadata"] == {
        "fallback_used": False,
        "parse_retry_count": 1,
        "generation_mode": "force_json",
        "legal_grounding_status": "no_candidates",
        "legal_grounding_error": "",
    }


@pytest.mark.asyncio
async def test_generate_qa_reports_fast_fallback_after_retry_exhaustion(monkeypatch):
    service = GenerationService()

    async def fake_build_rag_prompt(query, context, routing_trace=None, mode="default"):
        return f"mode={mode}"

    async def fake_call_ollama(prompt, temperature=0.7):
        return "not-json"

    monkeypatch.setattr(service, "build_rag_prompt", fake_build_rag_prompt)
    monkeypatch.setattr(service, "call_ollama", fake_call_ollama)

    result = await service.generate_qa("처리 기준을 알려주세요.", CONTEXT)

    assert result["generation_metadata"] == {
        "fallback_used": True,
        "parse_retry_count": 3,
        "generation_mode": "fast_fallback",
        "legal_grounding_status": "no_candidates",
        "legal_grounding_error": "",
    }
    assert "폴백" in result["limitations"]


@pytest.mark.asyncio
async def test_generate_qa_retries_when_answer_is_empty(monkeypatch):
    service = GenerationService()
    empty_answer = json.dumps(
        {
            "answer": "",
            "citations": [],
            "limitations": "근거 제한",
        },
        ensure_ascii=False,
    )
    responses = iter([empty_answer, _valid_response()])

    async def fake_build_rag_prompt(query, context, routing_trace=None, mode="default"):
        return f"mode={mode}"

    async def fake_call_ollama(prompt, temperature=0.7):
        return next(responses)

    monkeypatch.setattr(service, "build_rag_prompt", fake_build_rag_prompt)
    monkeypatch.setattr(service, "call_ollama", fake_call_ollama)

    result = await service.generate_qa("처리 기준을 알려주세요.", CONTEXT)

    assert result["answer"]
    assert result["generation_metadata"] == {
        "fallback_used": False,
        "parse_retry_count": 1,
        "generation_mode": "force_json",
        "legal_grounding_status": "no_candidates",
        "legal_grounding_error": "",
    }


@pytest.mark.asyncio
async def test_relaxed_parser_rejects_empty_answer_directly():
    service = GenerationService()
    payload = json.dumps(
        {
            "answer": "",
            "citations": [],
            "limitations": "근거 제한",
        },
        ensure_ascii=False,
    )

    with pytest.raises(GenerationError) as exc_info:
        await service.parse_json_response_relaxed(payload, CONTEXT)

    error = exc_info.value
    assert getattr(error, "code", "") == "PARSE_SCHEMA_MISMATCH"
    assert getattr(error, "details", {}).get("field") == "answer"

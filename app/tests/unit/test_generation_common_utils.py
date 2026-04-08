from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.generation.parsing.json_utils import parse_qa_json_response
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
)


def test_parse_qa_json_response_normalizes_values():
    raw = """
    ```json
    {
      "answer": "요약 답변",
      "citations": [{"chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거", "relevance_score": "0.77"}],
      "confidence": "high",
      "limitations": "범위 제한"
    }
    ```
    """

    parsed = parse_qa_json_response(raw)

    assert parsed["answer"] == "요약 답변"
    assert isinstance(parsed["confidence"], float)
    assert 0.0 <= parsed["confidence"] <= 1.0
    assert parsed["citations"][0]["chunk_id"] == "C1"
    assert parsed["limitations"] == "범위 제한"


def test_parse_qa_json_response_raises_on_missing_field():
    raw = '{"answer":"x","citations":[],"confidence":"medium"}'

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert exc.value.code == "PARSE_SCHEMA_MISMATCH"


def test_normalize_citations_and_tokens():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "근거 문장",
            "score": 0.9,
        }
    ]
    raw = [{"chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거 문장"}]

    citations = normalize_citations(raw, context)
    answer = ensure_citation_tokens("답변 본문", citations)

    assert len(citations) == 1
    assert citations[0]["ref_id"] == 1
    assert "[[출처 1]]" in answer


def test_build_validation_result_detects_mismatch():
    context = [{"chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-2", "snippet": "근거"}]
    answer = "본문 [[출처 1]]"

    validation = build_validation_result(
        answer=answer,
        citations=citations,
        limitations="범위 제한",
        context=context,
    )

    assert validation["is_valid"] is False
    assert any(item["code"] == "CASE_ID_MISMATCH" for item in validation["errors"])

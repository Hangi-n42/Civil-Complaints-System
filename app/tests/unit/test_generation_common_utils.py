from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.generation.parsing.json_utils import parse_qa_json_response
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    format_civil_reply_answer,
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


def test_parse_qa_json_response_allows_missing_confidence_and_defaults():
    raw = '{"answer":"x","citations":[],"limitations":"범위 제한"}'

    parsed = parse_qa_json_response(raw)

    assert parsed["answer"] == "x"
    assert isinstance(parsed["confidence"], float)
    assert 0.0 <= parsed["confidence"] <= 1.0
    assert parsed["limitations"] == "범위 제한"


def test_parse_qa_json_response_normalizes_limitations_list():
    raw = '{"answer":"x","citations":[],"limitations":["현장 확인 필요","자료 부족"]}'

    parsed = parse_qa_json_response(raw)

    assert parsed["limitations"] == "현장 확인 필요 / 자료 부족"


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


def test_format_civil_reply_moves_citations_to_final_lines():
    citations = [
        {"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거 1"},
        {"ref_id": 2, "chunk_id": "C2", "case_id": "CASE-2", "snippet": "근거 2"},
    ]

    answer = format_civil_reply_answer(
        "[[출처 1]] 현장 여건을 확인한 뒤 조치 가능 여부를 검토하겠습니다. [[출처 2]]",
        citations,
    )

    assert answer.startswith("1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.")
    assert "3. 검토 의견은 다음과 같습니다. 현장 여건을 확인한 뒤 조치 가능 여부를 검토하겠습니다." in answer
    assert "감사합니다. 끝.\n[[출처 1]]\n[[출처 2]]" in answer
    assert answer.count("[[출처 1]]") == 1
    assert answer.count("[[출처 2]]") == 1


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

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


def test_parse_qa_json_response_rejects_empty_answer():
    raw = '{"answer":"   ","citations":[],"limitations":"근거 제한"}'

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert exc.value.code == "PARSE_SCHEMA_MISMATCH"
    assert exc.value.details["field"] == "answer"


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
    assert "[[출처 1]]" not in answer
    assert answer.endswith("감사합니다. 끝.")


def test_normalize_citations_falls_back_when_model_returns_nested_list():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "근거 문장",
            "score": 0.9,
        }
    ]

    citations = normalize_citations([["not", "a", "citation", "object"]], context)

    assert len(citations) == 1
    assert citations[0]["chunk_id"] == "C1"
    assert citations[0]["case_id"] == "CASE-1"


def test_format_civil_reply_removes_citation_tokens_from_answer():
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
    assert answer.endswith("감사합니다. 끝.")
    assert "[[출처 1]]" not in answer
    assert "[[출처 2]]" not in answer


def test_format_civil_reply_converts_structured_string_to_natural_text():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "[{'section': '섹션 1', 'content': '주차 안심번호 서비스 도입을 검토할 수 있습니다.', "
        "'action_items': ['서비스 이용 안내', '홍보 강화']}]",
        citations,
    )

    assert "[{" not in answer
    assert "주차 안심번호 서비스 도입을 검토할 수 있습니다." in answer
    assert "서비스 이용 안내, 홍보 강화" in answer


def test_format_civil_reply_removes_generic_bridge_phrase():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "주차장 설치 요청 취지를 확인했습니다. 위 내용을 바탕으로 담당부서에서는 현장 여건, "
        "관련 기준, 유사 처리 사례를 확인한 뒤 필요한 조치 가능 여부를 판단할 수 있습니다.",
        citations,
    )

    assert "위 내용을 바탕으로 담당부서에서는 현장 여건" not in answer
    assert "주차장 설치 요청 취지를 확인했습니다." in answer
    assert answer.endswith("감사합니다. 끝.")


def test_format_civil_reply_trims_incomplete_tail_after_complete_sentence():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거 문장"}]

    answer = format_civil_reply_answer(
        "현장 확인 결과 통행 불편이 확인되었습니다. 위 내용을 바탕으로 담당부서에서는 현장 여건, "
        "관련 기준, 유사 처리 사례를 확인한 뒤 필요한 조치 가능 여부를 판단할 수 있습니다. 추가로 왔습",
        citations,
    )

    assert "추가로 왔습" not in answer
    assert "현장 확인 결과 통행 불편이 확인되었습니다." in answer
    assert answer.endswith("감사합니다. 끝.")


def test_format_civil_reply_replaces_fully_incomplete_body_with_fallback():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "도로 파손 민원은 현장 확인 후 보수 여부를 검토합니다."}]

    answer = format_civil_reply_answer("담당부서 검토 결과 주변", citations)

    assert "담당부서 검토 결과 주변" not in answer
    assert "도로 파손 민원은 현장 확인 후 보수 여부를 검토합니다." in answer
    assert answer.endswith("감사합니다. 끝.")


def test_format_civil_reply_strips_html_and_trims_list_fragment():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "공원 방역은 현장 확인 후 조치합니다."}]

    answer = format_civil_reply_answer(
        "<strong>1.</strong> 공원 내 바퀴벌레 문제에 대해 공감합니다. "
        "2.<strong>2.</strong> 즉시 조치로는 다음 활동을 진행하겠습니다. <ul><li>공원 내 주요",
        citations,
    )

    assert "<strong>" not in answer
    assert "<ul>" not in answer
    assert "공원 내 주요" not in answer
    assert "즉시 조치로는 다음 활동을 진행하겠습니다." in answer
    assert answer.endswith("감사합니다. 끝.")


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

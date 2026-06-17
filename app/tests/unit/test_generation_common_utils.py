from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.generation.parsing.json_utils import (
    build_qa_response_schema,
    parse_qa_json_response,
)
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    format_civil_reply_answer,
    normalize_citations,
    normalize_structured_output,
)


def test_parse_qa_json_response_normalizes_values():
    raw = """
    ```json
    {
      "answer": "요약 답변",
      "citations": [{"chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거", "relevance_score": 0.77}],
      "limitations": "범위 제한",
      "structured_output": {
        "summary": "민원 요약",
        "action_items": ["사실관계 확인", "처리 기준 안내"],
        "request_segments": ["처리 요청"]
      }
    }
    ```
    """

    parsed = parse_qa_json_response(raw)

    assert parsed["answer"] == "요약 답변"
    assert isinstance(parsed["confidence"], float)
    assert 0.0 <= parsed["confidence"] <= 1.0
    assert parsed["citations"][0]["chunk_id"] == "C1"
    assert parsed["limitations"] == "범위 제한"


def test_normalize_structured_output_removes_deadlines_and_prefers_routing_segments():
    normalized = normalize_structured_output(
        {
            "summary": "요약: 안전 조치 및 보수 일정 안내",
            "action_items": [
                "안전 표지판 및 경고 테이프 설치 (즉시)",
                "현장 조사 및 보수 계획 수립 (3일 이내)",
            ],
            "request_segments": ["모델이 다시 작성한 세그먼트 1", "모델 세그먼트 2"],
        },
        request_segments=["포트홀 임시 안전 조치 요청", "도로 보수 일정 문의"],
    )

    assert normalized["summary"] == "안전 조치 및 보수 일정 안내"
    assert normalized["request_segments"] == [
        "포트홀 임시 안전 조치 요청",
        "도로 보수 일정 문의",
    ]
    assert normalized["action_items"] == [
        "안전 표지판 및 경고 테이프 설치 필요성 및 소관 권한 검토",
        "현장 조사 및 보수 계획 수립 필요성 및 소관 권한 검토",
    ]


def test_parse_qa_json_response_raises_on_missing_field():
    raw = '{"answer":"x","citations":[],"confidence":"medium"}'

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert exc.value.code == "PARSE_SCHEMA_MISMATCH"


def test_parse_qa_json_response_rejects_empty_answer():
    raw = """
    {
      "answer":"   ",
      "citations":[{"chunk_id":"C1","case_id":"CASE-1","snippet":"근거","relevance_score":0.8}],
      "limitations":"근거 제한",
      "structured_output":{"summary":"요약","action_items":["확인","안내"],"request_segments":[]}
    }
    """

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert exc.value.code == "PARSE_SCHEMA_MISMATCH"
    assert exc.value.details["field"] == "answer"


def test_parse_qa_json_response_allows_missing_confidence_and_defaults():
    raw = """
    {
      "answer":"x",
      "citations":[{"chunk_id":"C1","case_id":"CASE-1","snippet":"근거","relevance_score":0.8}],
      "limitations":"범위 제한",
      "structured_output":{"summary":"요약","action_items":["확인","안내"],"request_segments":[]}
    }
    """

    parsed = parse_qa_json_response(raw)

    assert parsed["answer"] == "x"
    assert isinstance(parsed["confidence"], float)
    assert 0.0 <= parsed["confidence"] <= 1.0
    assert parsed["limitations"] == "범위 제한"


def test_parse_qa_json_response_normalizes_limitations_list():
    raw = """
    {
      "answer":"x",
      "citations":[{"chunk_id":"C1","case_id":"CASE-1","snippet":"근거","relevance_score":0.8}],
      "limitations":["현장 확인 필요","자료 부족"],
      "structured_output":{"summary":"요약","action_items":["확인","안내"],"request_segments":[]}
    }
    """

    parsed = parse_qa_json_response(raw)

    assert parsed["limitations"] == "현장 확인 필요 / 자료 부족"


def test_parse_qa_json_response_rejects_missing_structured_output():
    raw = """
    {
      "answer":"x",
      "citations":[{"chunk_id":"C1","case_id":"CASE-1","snippet":"근거","relevance_score":0.8}],
      "limitations":"범위 제한"
    }
    """

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert "structured_output" in exc.value.details["missing_fields"]


def test_parse_qa_json_response_rejects_unexpected_top_level_key():
    raw = """
    {
      "answer":"x",
      "citations":[{"chunk_id":"C1","case_id":"CASE-1","snippet":"근거","relevance_score":0.8}],
      "limitations":"범위 제한",
      "structured_output":{"summary":"요약","action_items":["확인","안내"],"request_segments":[]},
      "confidence":0.9
    }
    """

    with pytest.raises(GenerationError) as exc:
        parse_qa_json_response(raw)

    assert exc.value.details["unexpected_fields"] == ["confidence"]


def test_qa_response_schema_constrains_citation_to_retrieved_context():
    context = [
        {
            "chunk_id": "CASE-1__chunk-0",
            "case_id": "CASE-1",
            "snippet": "도로 폭이 좁아 현재 설치는 어렵습니다.",
        },
        {
            "chunk_id": "CASE-2__chunk-0",
            "case_id": "CASE-2",
            "snippet": "현장 확인 후 처리 방향을 안내합니다.",
        },
    ]

    schema = build_qa_response_schema(context, citations_max=1)
    citations = schema["properties"]["citations"]
    item = citations["items"]["properties"]

    assert citations["minItems"] == citations["maxItems"] == 1
    assert item["chunk_id"]["enum"] == ["CASE-1__chunk-0", "CASE-2__chunk-0"]
    assert item["case_id"]["enum"] == ["CASE-1", "CASE-2"]
    assert item["snippet"]["enum"] == [
        "도로 폭이 좁아 현재 설치는 어렵습니다.",
        "현장 확인 후 처리 방향을 안내합니다.",
    ]


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


def test_format_civil_reply_keeps_single_closing_only():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]
    raw = (
        "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
        "3. 검토 의견은 다음과 같습니다. 현장 확인 후 처리 가능 여부를 검토하겠습니다. "
        "감사합니다. 끝.\n\n"
        "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 "
        "세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
    )

    answer = format_civil_reply_answer(raw, citations)

    assert answer.count("감사합니다. 끝.") == 1
    assert "3. 검토 의견은 다음과 같습니다. 현장 확인 후 처리 가능 여부를 검토하겠습니다." in answer


def test_format_civil_reply_softens_strong_commitment():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "해당 시설을 즉시 철거하겠습니다. 새로운 안내 표지판을 설치하겠습니다.",
        citations,
    )

    assert "즉시 철거하겠습니다" not in answer
    assert "설치하겠습니다" not in answer
    assert "철거 가능 여부를 검토하겠습니다" in answer
    assert "설치 가능 여부를 검토하겠습니다" in answer


def test_format_civil_reply_removes_embedded_schema_artifact():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "현장 확인 후 처리 가능 여부를 안내하겠습니다. "
        '**structured_output**: {"summary":"잘못 노출된 구조"}',
        citations,
    )

    assert "structured_output" not in answer
    assert "잘못 노출된 구조" not in answer
    assert "현장 확인 후 처리 가능 여부를 안내하겠습니다." in answer


def test_format_civil_reply_rewrites_agency_directives_as_review_language():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "즉시 조치로는 다음과 같은 방안을 제안드립니다: "
        "승차장 이전을 검토해 주시기 바랍니다. "
        "주민 의견 수렴을 진행해 주시기 바랍니다. "
        "추가적인 조치로는: 필요한 개선 조치를 취해 주시기 바랍니다.",
        citations,
    )

    assert "제안드립니다" not in answer
    assert "주시기 바랍니다" not in answer
    assert "검토할 필요가 있습니다" in answer
    assert "진행 가능 여부를 검토하겠습니다" in answer
    assert "필요한 조치 여부를 검토하겠습니다" in answer


def test_format_civil_reply_softens_unverified_precedent_facts():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "교통 흐름에 부정적인 영향을 미치고 있음을 확인하였습니다. "
        "주변 사고 위험 증가가 보고되었습니다. "
        "현장 조치를 위해 다음과 같은 방안을 제안드립니다: 시간대별 운영 조정을 권장드립니다.",
        citations,
    )

    assert "확인하였습니다" not in answer
    assert "보고되었습니다" not in answer
    assert "제안드립니다" not in answer
    assert "권장드립니다" not in answer
    assert answer.count("현장 확인이 필요합니다") == 2
    assert "처리 방향은 다음 사항을 중심으로 검토할 필요가 있습니다." in answer


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
    assert "검색된 유사 사례는 처리 방향을 검토하기 위한 참고자료" in answer
    assert "도로 파손 민원은 현장 확인 후 보수 여부를 검토합니다." not in answer
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


def test_format_civil_reply_removes_literal_newlines_internal_labels_and_redacted_tail():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "액션 아이템 1: 현장 확인을 진행하겠습니다.\\n\\n"
        "섹션 2: 관련 기준을 검토하겠습니다. [REDACTED:",
        citations,
    )

    assert "\\n" not in answer
    assert "액션 아이템" not in answer
    assert "섹션 2" not in answer
    assert "[REDACTED:" not in answer


def test_format_civil_reply_softens_removal_move_build_and_budget_commitments():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "나무 제거 작업을 우선적으로 진행할 예정입니다. "
        "흡연구역을 이동하겠습니다. 신규 시설을 건설하겠습니다. "
        "예산 확보 계획을 수립할 예정입니다.",
        citations,
    )

    assert "진행할 예정입니다" not in answer
    assert "이동하겠습니다" not in answer
    assert "건설하겠습니다" not in answer
    assert "수립할 예정입니다" not in answer
    assert "가능 여부를 검토하겠습니다" in answer


def test_format_civil_reply_softens_precedent_schedule_as_unverified():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "현재 분당구 지역에서는 정기적인 방역 활동이 진행 중입니다. "
        "민원 지역에는 이미 예정된 방제 작업이 진행 중입니다.",
        citations,
    )

    assert "진행 중입니다" not in answer
    assert "담당부서 확인이 필요합니다" in answer


def test_format_civil_reply_preserves_private_property_and_unavailable_constraints():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "해당 수목은 사유지에 있어 소유자 관리 범위에 해당하므로 행정기관의 직접 제거는 어렵습니다. "
        "음악실은 안전 및 보안 기준상 주말 개방이 불가합니다.",
        citations,
    )

    assert "사유지" in answer
    assert "소유자 관리 범위" in answer
    assert "직접 제거는 어렵습니다" in answer
    assert "주말 개방이 불가합니다" in answer


def test_format_civil_reply_collapses_multi_action_promise_into_single_safe_sentence():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "적합한 부지를 매입하거나 신규 주차 시설을 건설하여 주차 공간을 확대하겠습니다. "
        "필요한 예산도 확보하겠습니다.",
        citations,
    )

    assert "부지를 매입하거나" not in answer
    assert "시설을 건설하여" not in answer
    assert "주차 공간을 확대하겠습니다" not in answer
    assert answer.count("관련 계획 및 예산을 확인한 뒤 추진 가능 여부를 검토하겠습니다") == 1


def test_format_civil_reply_deduplicates_unverified_schedule_replacement():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "현재 정기 방역이 진행 중입니다. 민원 지역의 추가 방역도 진행 중입니다.",
        citations,
    )

    assert answer.count("현재 진행 여부와 일정은 담당부서 확인이 필요합니다") == 1
    assert "진행 여부는 담당부서 확인이 필요합니다의" not in answer


def test_format_civil_reply_removes_inline_numbering_without_damaging_law_articles():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "현재 방역 활동이 진행 중입니다. 2. 확인·협의 사항을 검토하겠습니다. "
        "주차장법 제3조는 검증된 법령 인용인 경우에만 안내합니다.",
        citations,
    )

    assert "2. 확인·협의" not in answer
    assert "확인·협의 사항" in answer
    assert "제3조" in answer


def test_format_civil_reply_keeps_intro_when_rewriting_proposal_phrase():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "판교 지역의 주차 공간 부족 문제를 해결하기 위해 다음과 같은 방안을 제안드립니다: "
        "현장 여건과 관련 계획을 검토하겠습니다.",
        citations,
    )

    assert "판교 지역의 주차 공간 부족 문제" in answer
    assert "문제를 해결하기 위해 처리 방향은" in answer
    assert "심각처리 방향" not in answer


def test_format_civil_reply_drops_concrete_precedent_only_sentence():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]
    context = [
        {
            "snippet": (
                "독서 동아리 공간이 부족하고 특정 날짜의 시설 공사로 "
                "수업 공간을 확보하지 못했습니다."
            )
        }
    ]
    complaint = "공공도서관 단기근로 채용 면접의 공정성 문제를 확인해 주세요."

    answer = format_civil_reply_answer(
        "단기근로 채용 면접 절차의 공정성을 확인할 필요가 있습니다. "
        "현재 특정 날짜의 시설 공사로 수업 공간을 확보하지 못했습니다.",
        citations,
        complaint=complaint,
        context=context,
    )

    assert "채용 면접 절차" in answer
    assert "시설 공사" not in answer
    assert "수업 공간" not in answer


def test_build_validation_result_warns_about_semantic_safety_risks():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "다른 지역에서는 시설 공사가 예정되어 있습니다.",
        }
    ]
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": context[0]["snippet"]}]

    validation = build_validation_result(
        answer="다른 지역의 시설 공사가 이미 예정되어 있으며 즉시 건설하겠습니다.",
        citations=citations,
        limitations="현장 확인 필요",
        context=context,
        complaint="채용 면접 절차의 공정성을 확인해 주세요.",
    )
    codes = {item["code"] for item in validation["warnings"]}

    assert "UNSUPPORTED_COMMITMENT_RISK" in codes
    assert "UNVERIFIED_FACT_RISK" in codes
    assert "ANSWER_REQUEST_MISMATCH" in codes


def test_build_validation_result_does_not_flag_general_context_vocabulary_as_leakage():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "유사 사례에서는 현장 확인과 관련 기준 검토 후 시설 사용 여부를 안내했습니다.",
        }
    ]
    citations = [{"ref_id": 1, **context[0]}]

    validation = build_validation_result(
        answer="시설 사용 가능 여부는 운영 기준과 안전 여건을 확인한 뒤 안내드리겠습니다.",
        citations=citations,
        limitations="현장 확인 필요",
        context=context,
        complaint="주말에 음악실을 사용할 수 있는지 알려 주세요.",
    )
    codes = {item["code"] for item in validation["warnings"]}

    assert "PRECEDENT_FACT_LEAKAGE_RISK" not in codes


def test_build_validation_result_flags_commitment_against_context_constraint():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "해당 수목은 사유지에 있어 소유자가 직접 관리해야 하며 행정기관의 제거는 어렵습니다.",
        }
    ]
    citations = [{"ref_id": 1, **context[0]}]

    validation = build_validation_result(
        answer="현장 확인 후 해당 수목을 우선 제거할 예정입니다.",
        citations=citations,
        limitations="",
        context=context,
        complaint="건물 가까이에 있는 큰 나무를 제거해 주세요.",
    )
    codes = {item["code"] for item in validation["warnings"]}

    assert "CONTEXT_CONSTRAINT_CONFLICT" in codes


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


def test_format_civil_reply_truncates_plain_structured_output_tail():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "주차 불편 사항은 현장 여건과 관련 기준을 확인한 뒤 검토하겠습니다. "
        "structured_output.action_items: 현장 조사 실시. 공영주차장 타당성 검토.",
        citations,
    )

    assert "structured_output" not in answer
    assert "action_items" not in answer
    assert "공영주차장 타당성" not in answer
    assert "주차 불편 사항" in answer


def test_format_civil_reply_preserves_context_constraints_over_positive_actions():
    context = [
        {
            "chunk_id": "C1",
            "case_id": "CASE-1",
            "snippet": "해당 흡연구역은 관리주체 소관으로 행정기관이 직접 이동하거나 추가 지정하기 어렵습니다.",
        }
    ]
    citations = [{"ref_id": 1, **context[0]}]

    answer = format_civil_reply_answer(
        "흡연구역을 더 안전한 위치로 이동시키는 방안을 검토해 보겠습니다. "
        "정원 사이 벤치 주변으로 흡연구역을 설치하는 방안도 검토해 보겠습니다.",
        citations,
        complaint="오피스텔 앞 흡연구역 이동을 요청합니다.",
        context=context,
    )

    assert "이동시키는 방안" not in answer
    assert "설치하는 방안" not in answer
    assert "관리주체 소관" in answer
    assert "처리 가능 여부를 판단하겠습니다" in answer


def test_format_civil_reply_removes_unsupported_positive_proposals():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "불법 주정차 문제는 주차 공간 부족으로 인한 것으로 보입니다. "
        "이에 대해 다음과 같은 조치를 제안드립니다. "
        "주말이나 공휴일에도 도로변 주차를 허용하는 방안을 검토해 보겠습니다. "
        "장기적으로는 공영 주차장 확충을 위한 계획을 수립하고 있습니다. "
        "설치 요청은 현장 여건, 소관 권한 및 관련 기준을 확인한 뒤 처리 가능 여부를 검토하겠습니다.",
        citations,
    )

    assert "제안드립니다" not in answer
    assert "허용하는 방안" not in answer
    assert "계획을 수립하고 있습니다" not in answer
    assert "처리 가능 여부를 검토하겠습니다" in answer


def test_format_civil_reply_removes_unsupported_relocation_promise():
    citations = [{"ref_id": 1, "chunk_id": "C1", "case_id": "CASE-1", "snippet": "근거"}]

    answer = format_civil_reply_answer(
        "흡연 매너 구역 이동 요청에 대해 안내드립니다. "
        "보다 조용하고 안전한 위치로 재배치를 제안드립니다. "
        "관리사무소와 협의하여 주민 설명회를 개최하고 의견을 수렴하겠습니다. "
        "정원 사이 벤치 주변으로 흡연 매너 존을 설치하는 방안도 검토해 보겠습니다. "
        "이동 요청은 현장 여건, 소관 권한 및 관련 기준을 확인한 뒤 처리 가능 여부를 검토하겠습니다.",
        citations,
    )

    assert "재배치를 제안" not in answer
    assert "주민 설명회" not in answer
    assert "설치하는 방안" not in answer
    assert "처리 가능 여부를 검토하겠습니다" in answer

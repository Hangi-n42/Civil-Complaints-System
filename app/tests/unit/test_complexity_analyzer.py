from __future__ import annotations

from app.retrieval.analyzers.complexity_analyzer import (
    COMPLEXITY_LEVEL_HIGH_THRESHOLD,
    COMPLEXITY_LEVEL_MEDIUM_THRESHOLD,
    build_analyzer_output,
    analyze,
)


def test_analyze_handles_empty_text():
    result = analyze("", "welfare")

    assert result.complexity_score == 0.0
    assert result.complexity_level == "low"
    assert result.intent_count == 0
    assert result.constraint_count == 0
    assert result.entity_diversity == 0
    assert result.policy_reference_count == 0
    assert result.complexity_trace["reason"] == "empty_text"


def test_analyze_score_is_bounded_and_uses_expected_level():
    text = (
        "복지 예산과 절차 및 기한을 검토하고, 조례와 법령 근거를 확인한 뒤 "
        "담당 부서 및 기관 협의 조건을 함께 제시해 주세요."
    )
    result = analyze(text, "welfare")

    assert 0.0 <= result.complexity_score <= 1.0
    if result.complexity_score >= COMPLEXITY_LEVEL_HIGH_THRESHOLD:
        assert result.complexity_level == "high"
    elif result.complexity_score >= COMPLEXITY_LEVEL_MEDIUM_THRESHOLD:
        assert result.complexity_level == "medium"
    else:
        assert result.complexity_level == "low"


def test_analyze_is_deterministic_for_same_input():
    text = "도로 보수 절차와 예산, 담당 부서 협업 기준을 알려주세요."

    first = analyze(text, "construction")
    second = analyze(text, "construction")

    assert first == second


def test_analyze_returns_high_for_rich_constraints():
    text = (
        "복지 및 도로 민원 대응 절차를 기관, 부서, 주민, 사업자, 지자체 관점으로 구분하고, "
        "기한과 예산, 규정, 우선순위, 근거 조건을 함께 제시해 주세요. "
        "관련 법, 법령, 조례, 규칙, 고시까지 반영해 주세요."
    )

    result = analyze(text, "welfare")

    assert result.complexity_level == "high"
    assert result.policy_reference_count >= 2
    assert result.constraint_count >= 3


def test_build_analyzer_output_aligns_with_routing_contract():
    text = "복지 예산과 절차 및 기한을 검토하고, 조례와 법령 근거를 확인한 뒤 담당 부서 및 기관 협의 조건을 함께 제시해 주세요."

    output = build_analyzer_output(text, "welfare")

    assert output["topic_type"] == "welfare"
    assert output["complexity_level"] in {"low", "medium", "high"}
    assert 0.0 <= float(output["complexity_score"]) <= 1.0
    assert set(output["complexity_trace"].keys()) >= {
        "topic_type",
        "text_length",
        "intent_count",
        "constraint_count",
        "entity_diversity",
        "policy_reference_count",
        "cross_sentence_dependency",
        "weights",
    }
    assert isinstance(output["request_segments"], list)
    assert len(output["request_segments"]) >= 1
    assert output["length_bucket"] in {"short", "medium", "long"}
    assert isinstance(output["is_multi"], bool)

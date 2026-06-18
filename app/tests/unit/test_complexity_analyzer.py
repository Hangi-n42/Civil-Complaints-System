from __future__ import annotations

from app.retrieval.analyzers.complexity_analyzer import (
    COMPLEXITY_LEVEL_HIGH_THRESHOLD,
    COMPLEXITY_LEVEL_MEDIUM_THRESHOLD,
    build_analyzer_output,
    _split_sentences_with_source,
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
    assert output["intent_count"] == len(output["request_segments"])
    assert output["is_multi"] == (len(output["request_segments"]) >= 2)


def test_request_segments_keep_single_request_with_connectors():
    text = (
        "도로와 인도, 가로등 및 보안등이 파손되어 통행이 위험하니 "
        "현장 점검 및 보수를 요청드립니다."
    )

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_split_independent_requests_only():
    text = "포트홀 주변 임시 안전 조치를 해주시고, 도로 보수 일정도 알려주세요."

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == [
        "포트홀 주변 임시 안전 조치를 해주시고",
        "도로 보수 일정도 알려주세요.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_background_and_admin_action_sentences():
    text = (
        "안녕하세요. 포트홀 때문에 차량이 흔들리고 주민들이 불편을 겪고 있습니다. "
        "담당 부서에서 현장 확인 후 조치할 예정입니다. "
        "문의하신 내용은 확인 후 안내드립니다. 빠른 현장 확인을 부탁드립니다."
    )

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == ["빠른 현장 확인을 부탁드립니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_remove_duplicate_and_partial_segments():
    text = "도로 보수 요청 및 도로 보수 요청드립니다."

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == ["도로 보수 요청드립니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_sentence_splitter_uses_kss_when_available(monkeypatch):
    from app.retrieval.analyzers import complexity_analyzer

    def fake_splitter(text: str, **kwargs):
        return ["첫 번째 문장입니다.", "두 번째 문장입니다."]

    monkeypatch.setenv("COMPLEXITY_ANALYZER_USE_KSS", "true")
    monkeypatch.setattr(complexity_analyzer, "_load_kss_sentence_splitter", lambda: fake_splitter)

    sentences, source = _split_sentences_with_source("첫 번째 문장입니다. 두 번째 문장입니다.")

    assert source == "kss"
    assert sentences == ["첫 번째 문장입니다.", "두 번째 문장입니다."]


def test_sentence_splitter_falls_back_to_regex_without_kss(monkeypatch):
    from app.retrieval.analyzers import complexity_analyzer

    monkeypatch.setattr(complexity_analyzer, "_load_kss_sentence_splitter", lambda: None)

    sentences, source = _split_sentences_with_source("첫 번째 문장입니다. 두 번째 문장입니다.")

    assert source == "regex"
    assert sentences == ["첫 번째 문장입니다.", "두 번째 문장입니다."]


def test_request_segments_split_shared_predicate_for_distinct_requests():
    text = "도로 보수와 불법주정차 단속을 요청합니다."

    output = build_analyzer_output(text, "traffic")

    assert output["request_segments"] == [
        "도로 보수 요청합니다.",
        "불법주정차 단속 요청합니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True
    assert output["complexity_trace"]["shared_predicate_split_count"] >= 2


def test_request_segments_split_compact_request_list_only():
    text = "영어 가이드 투어 운영 여부, 신청 기한, 신청 경로, 잔여석 부족 시 대안 안내 요청"

    output = build_analyzer_output(text, "general")

    assert output["request_segments"] == [
        "영어 가이드 투어 운영 여부 요청",
        "신청 기한 요청",
        "신청 경로 요청",
        "잔여석 부족 시 대안 안내 요청",
    ]
    assert output["intent_count"] == 4
    assert output["is_multi"] is True


def test_generation_fallback_uses_complexity_analyzer_segments():
    from app.api.routers.generation import _derive_request_segments

    text = "도로 보수와 불법주정차 단속을 요청합니다."

    assert _derive_request_segments(text) == [
        "도로 보수 요청합니다.",
        "불법주정차 단속 요청합니다.",
    ]

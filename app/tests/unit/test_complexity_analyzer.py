from __future__ import annotations

from app.retrieval.analyzers.complexity_analyzer import (
    COMPLEXITY_LEVEL_HIGH_THRESHOLD,
    COMPLEXITY_LEVEL_MEDIUM_THRESHOLD,
    build_analyzer_output,
    is_request_segments_low_confidence,
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
    assert isinstance(output["fallback_used"], bool)
    assert isinstance(output["truncated"], bool)
    assert output["request_segments_low_confidence"] == is_request_segments_low_confidence(
        complexity_level=output["complexity_level"],
        fallback_used=output["fallback_used"],
    )
    assert output["complexity_trace"]["fallback_used"] == output["fallback_used"]
    assert output["complexity_trace"]["truncated"] == output["truncated"]
    assert output["complexity_trace"]["request_segments_low_confidence"] == output["request_segments_low_confidence"]


def test_request_segments_low_confidence_helper_uses_fallback_or_low_level():
    assert is_request_segments_low_confidence(complexity_level="low", fallback_used=False) is True
    assert is_request_segments_low_confidence(complexity_level="medium", fallback_used=True) is True
    assert is_request_segments_low_confidence(complexity_level="high", fallback_used=False) is False


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


def test_request_segments_drop_title_greeting_and_closing_only_segments():
    text = (
        "전자도서관 전자책 대여 안녕하십니까? "
        "전자책 예약 제한 이유가 궁금합니다. "
        "예약 없이 내려받을 수 있도록 지원해 주시면 감사하겠습니다. "
        "더운 날씨에 더위 조심하시길 바랍니다."
    )

    output = build_analyzer_output(text, "general")

    assert output["request_segments"] == [
        "전자책 예약 제한 이유가 궁금합니다.",
        "예약 없이 내려받을 수 있도록 지원해 주시면 감사하겠습니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_do_not_split_parallel_direction_nouns():
    text = "오류IC 교량공사 부지에 남쪽, 북쪽 구간 연결통로를 개설해 주십시오."

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_merge_repeated_same_request():
    text = (
        "사회자 교체를 요청드립니다. "
        "총회 사회자를 지정해서 공정하게 조합장을 선정할 수 있도록 요청드립니다. "
        "사회자 교체 요청을 신속히 검토해 주시길 부탁드립니다. "
        "본 요청에 대한 협조에 깊이 감사드립니다."
    )

    output = build_analyzer_output(text, "general")

    assert output["request_segments"] == [
        "사회자 교체 요청을 신속히 검토해 주시길 부탁드립니다."
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_allow_six_actionable_items():
    text = (
        "줍깅대회를 개최해 주세요. 쓰레기통을 추가 설치해 주세요. "
        "환경미화 인력을 보충해 주세요. 울타리를 높게 설치해 주세요. "
        "벌금을 부과해 주세요. 안내판을 설치해 주세요."
    )

    output = build_analyzer_output(text, "environment")

    assert output["intent_count"] == 6
    assert output["complexity_trace"]["segment_limit"] == 6
    assert output["complexity_trace"]["segment_limit_applied"] is False


def test_request_segments_restore_numbered_title_items():
    text = (
        "1.도로 침하 신고 및 2.공사 현장 주차난 해소 요청 "
        "1. 도로 침하로 싱크홀이 우려됩니다. "
        "2. 공사 현장 주차난 해소를 요청드립니다."
    )

    output = build_analyzer_output(text, "construction")

    assert output["request_segments"] == [
        "도로 침하 신고",
        "공사 현장 주차난 해소를 요청드립니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_answer_style_and_generic_closing_requests():
    text = (
        "소셜벤처 육성사업에서 경남이 제외된 이유가 무엇인지요? "
        "육성 계획이 있는지 문의드립니다. "
        "반드시 답변하여 주실 것을 요청합니다. "
        "항상 도민을 위해 살아가는 멋진 도지사님 되어주시기를 부탁드립니다."
    )

    output = build_analyzer_output(text, "general")

    assert output["request_segments"] == [
        "소셜벤처 육성사업에서 경남이 제외된 이유가 무엇인지요?",
        "육성 계획이 있는지 문의드립니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_short_summary_when_detail_segments_exist():
    text = (
        "오거리 신호등 설치 요청. "
        "오거리 보행자 안전을 위해 신호등 설치를 요청드립니다. "
        "횡단보도 설치도 요청드립니다."
    )

    output = build_analyzer_output(text, "transport")

    assert output["request_segments"] == [
        "오거리 보행자 안전을 위해 신호등 설치를 요청드립니다.",
        "횡단보도 설치도 요청드립니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_duplicate_question_title_summary():
    title = "국가기술자격증 관련 행정처분의 기준은 어떻게 되어 있나요?"
    question = "국가기술자격증 대여시 행정처분의 기준은 어떻게 되어 있나요?"

    output = build_analyzer_output(
        f"{title}\n{question}",
        "general",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [
        "국가기술자격증 대여시 행정처분의 기준은 어떻게 되어 있나요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_use_title_question_boundary_to_drop_title_summary():
    title = "공중충돌경고장치(ACAS/TCAS)가 무엇입니까?"
    question = "○ 공중충돌경고장치란 무엇인가요?\n○ 공중충돌경고장치의 원리는 무엇입니까?"

    output = build_analyzer_output(
        f"{title}\n{question}",
        "aviation",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [
        "○ 공중충돌경고장치란 무엇인가요?",
        "○ 공중충돌경고장치의 원리는 무엇입니까?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True
    assert output["complexity_trace"]["title_question_boundary_used"] is True
    assert output["complexity_trace"]["title_duplicate_dropped_count"] == 1


def test_request_segments_query_only_does_not_use_title_question_boundary():
    text = "공중충돌경고장치가 무엇인지와 원리가 무엇인지 궁금합니다."

    output = build_analyzer_output(text, "aviation")

    assert output["complexity_trace"]["title_question_boundary_used"] is False
    assert output["complexity_trace"]["title_duplicate_dropped_count"] == 0
    assert output["request_segments"]


def test_request_segments_keep_title_only_request_when_question_has_other_request():
    title = "1.도로 침하 신고 및 2.공사 현장 주차난 민원"
    question = "공사 현장 종사자 차량으로 실거주 주민 주차난이 커져 민원 해소를 요청드립니다."

    output = build_analyzer_output(
        f"{title}\n{question}",
        "construction",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [
        "도로 침하 신고",
        "공사 현장 종사자 차량으로 실거주 주민 주차난이 커져 민원 해소를 요청드립니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_question_title_with_long_shared_term():
    text = (
        "공중충돌경고장치(ACAS/TCAS)가 무엇입니까? "
        "공중충돌경고장치란 무엇인가요? "
        "공중충돌경고장치의 원리는 무엇입니까?"
    )

    output = build_analyzer_output(text, "aviation")

    assert output["request_segments"] == [
        "공중충돌경고장치(ACAS/TCAS)가 무엇입니까?",
        "공중충돌경고장치란 무엇인가요?",
        "공중충돌경고장치의 원리는 무엇입니까?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_keep_distinct_condition_questions():
    text = (
        "수하인이 포워더인 경우 합병이 가능한지? "
        "SHIPPER가 상이한 경우 합병이 가능한지? "
        "화물관리번호가 다른 경우에 합병이 가능한지?"
    )

    output = build_analyzer_output(text, "trade")

    assert output["request_segments"] == [
        "수하인이 포워더인 경우 합병이 가능한지?",
        "SHIPPER가 상이한 경우 합병이 가능한지?",
        "화물관리번호가 다른 경우에 합병이 가능한지?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_do_not_split_comma_inside_parentheses():
    text = "반려동물(개, 고양이) 동물 등록제 신청 방법과 변경 절차를 문의드립니다."

    output = build_analyzer_output(text, "animal")

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_generic_action_only_segments():
    text = (
        "무단방치 자동차 신고 방법을 알려주세요. "
        "이 경우 문의드립니다. "
        "신속한 대응 부탁드립니다."
    )

    output = build_analyzer_output(text, "transport")

    assert output["request_segments"] == ["무단방치 자동차 신고 방법을 알려주세요."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_split_comma_numbered_questions_and_drop_generic_closing():
    question = (
        "1, 제주도에서 제주관광협회에 지원되는 보조금 및 사업비 예산 금액을 알고 싶습니다. "
        "2, 전세기 보조금 예산이 협회 자체 예산인지 제주도 예산인지 궁금합니다. "
        "3, 위 지원 금액이 관광정책과 사전 승인을 얻는 것인지 궁금합니다. "
        "정확한 답변 부탁드립니다."
    )

    output = build_analyzer_output(question, "tourism", question=question)

    assert output["request_segments"] == [
        "제주도에서 제주관광협회에 지원되는 보조금 및 사업비 예산 금액을 알고 싶습니다.",
        "전세기 보조금 예산이 협회 자체 예산인지 제주도 예산인지 궁금합니다.",
        "위 지원 금액이 관광정책과 사전 승인을 얻는 것인지 궁금합니다.",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_keep_why_question_and_drop_reply_closing():
    question = "도대체 축사 문제는 언제면 해결이 되나요? 그리고 왜 이렇게 해결이 안 되나요? 회신 바랍니다."

    output = build_analyzer_output(question, "environment", question=question)

    assert output["request_segments"] == [
        "도대체 축사 문제는 언제면 해결이 되나요?",
        "왜 이렇게 해결이 안 되나요?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_keep_specific_reply_request_not_generic_closing():
    question = "방음벽 설치를 재차 요청드리며, 방음벽 설치 회신 부탁드립니다."

    output = build_analyzer_output(question, "construction", question=question)

    assert output["request_segments"]
    assert "방음벽" in output["request_segments"][-1]


def test_request_segments_drop_generic_inquiry_intro_when_specific_question_follows():
    question = (
        "제주관광협회 전세기 운영 지원사업에 대하여 문의합니다. "
        "전세기 보조금 예산이 협회 자체 예산인지 제주도 예산인지 궁금합니다."
    )

    output = build_analyzer_output(question, "tourism", question=question)

    assert output["request_segments"] == [
        "전세기 보조금 예산이 협회 자체 예산인지 제주도 예산인지 궁금합니다."
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_merge_orphan_numbered_possible_questions():
    question = (
        "1. 개인사업자등록은 제가 살고 있는 집으로 내도 되는지요? "
        "2. 인터넷 쇼핑몰도 자금을 지원받을 수 있는지요? "
        "3. 외국산 상품도 직거래 중개를 할 수 있는지요?"
    )

    sentences, splitter = _split_sentences_with_source(question)
    output = build_analyzer_output(question, "industry", question=question)

    assert splitter == "regex"
    assert sentences == [
        "1. 개인사업자등록은 제가 살고 있는 집으로 내도 되는지요?",
        "2. 인터넷 쇼핑몰도 자금을 지원받을 수 있는지요?",
        "3. 외국산 상품도 직거래 중개를 할 수 있는지요?",
    ]
    assert output["request_segments"] == [
        "개인사업자등록은 제가 살고 있는 집으로 내도 되는지요?",
        "인터넷 쇼핑몰도 자금을 지원받을 수 있는지요?",
        "외국산 상품도 직거래 중개를 할 수 있는지요?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_keep_short_nominal_question_items():
    question = (
        "1. 청주시에서 시행하는 시골마을 행복택시 사업은 무엇인가? "
        "2. 청주시 행복택시 운행대상 마을은? "
        "3. 청주시 행복택시 이용대상은? "
        "4. 청주시 행복택시 운행구간은? "
        "5. 청주시 행복택시 이용방법은?"
    )

    output = build_analyzer_output(question, "transport", question=question)

    assert output["request_segments"] == [
        "청주시에서 시행하는 시골마을 행복택시 사업은 무엇인가?",
        "청주시 행복택시 운행대상 마을은?",
        "청주시 행복택시 이용대상은?",
        "청주시 행복택시 운행구간은?",
        "청주시 행복택시 이용방법은?",
    ]
    assert output["intent_count"] == 5
    assert output["is_multi"] is True


def test_request_segments_merge_numbered_object_with_polite_tail_before_limit():
    question = (
        "이제 독립을 하고자 하는데 창업 시에 어떤 지원을 받을 수 있는지 안내받고 싶습니다. "
        "1. 개인사업자등록은 제가 살고 있는 집으로 내도 되는지요? "
        "2. 인터넷 쇼핑몰도 자금을 지원받을 수 있는지요? "
        "3. 장사가 잘되는 여러 가지의 사업장과 연결하여 소비자와 중개 거래도 할 수 있는지요? "
        "4. 외국산 상품도 직거래 중개를 할 수 있는지요? "
        "5. 창업지원을 받으려면 어떤 절차를 거쳐서 어디서, 어떤 상담 받을 수 있는지요? "
        "6. 온라인 쇼핑몰 제작 방법\n"
        "안내해 주시면 감사하겠습니다."
    )

    output = build_analyzer_output(question, "industry", question=question)

    assert output["request_segments"] == [
        "개인사업자등록은 제가 살고 있는 집으로 내도 되는지요?",
        "인터넷 쇼핑몰도 자금을 지원받을 수 있는지요?",
        "장사가 잘되는 여러 가지의 사업장과 연결하여 소비자와 중개 거래도 할 수 있는지요?",
        "외국산 상품도 직거래 중개를 할 수 있는지요?",
        "창업지원을 받으려면 어떤 절차를 거쳐서 어디서, 어떤 상담 받을 수 있는지요?",
        "온라인 쇼핑몰 제작 방법 안내해 주시면 감사하겠습니다.",
    ]
    assert output["intent_count"] == 6
    assert output["is_multi"] is True
    assert output["complexity_trace"]["segment_limit_applied"] is True


def test_request_segments_drop_generic_inquiry_heading_when_specific_question_follows():
    text = (
        "자가품질검사서유산균 수 관련 문의. "
        "온도조건을 변경하여 자가품질검사서에 생균수를 기재할 수 있는 방법이 있을까요?"
    )

    output = build_analyzer_output(text, "health", question=text)

    assert output["request_segments"] == [
        "온도조건을 변경하여 자가품질검사서에 생균수를 기재할 수 있는 방법이 있을까요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_generic_title_heading_with_specific_question_boundary():
    title = "자가품질검사서유산균 수 관련 문의"
    question = "온도조건을 변경하여 자가품질검사서에 생균수를 기재할 수 있는 방법이 있을까요?"

    output = build_analyzer_output(
        f"{title}\n{question}",
        "health",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [question]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_generic_title_when_question_is_too_short():
    title = "세르티아 마르세센스 균 관련 문의"
    question = "방법이 있을까요?"

    output = build_analyzer_output(
        f"{title}\n{question}",
        "health",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [title, question]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_compound_title_summary_when_question_is_specific():
    title = "코로나 확진시 출석인정 부탁드립니다."
    question = "코로나 확진으로 인한 불출석에 대해서는 출석을 인정하여 주실 것을 부탁드립니다."

    output = build_analyzer_output(
        f"{title}\n{question}",
        "health",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [question]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False
    assert output["complexity_trace"]["title_duplicate_dropped_count"] == 1


def test_request_segments_keep_title_when_question_lacks_title_object():
    title = "서울대공원내 유인원관 유리 청소해주세요"
    question = "정기적인 청소를 요청합니다."

    output = build_analyzer_output(
        f"{title}\n{question}",
        "environment",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [title, question]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True
    assert output["complexity_trace"]["title_duplicate_dropped_count"] == 0


def test_request_segments_drop_low_value_closing_segments():
    text = "이 부분 꼭 해결해 주세요. 정말 부탁드립니다."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == ["이 부분 꼭 해결해 주세요."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_reference_only_segments():
    text = "전기차 신규등록 대수를 알고 싶습니다. 와 같이 나오니 참고하시길 바랍니다."

    output = build_analyzer_output(text, "transport", question=text)

    assert output["request_segments"] == ["전기차 신규등록 대수를 알고 싶습니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_do_not_split_context_fragment_before_comma():
    text = "자동차 자가 정비 후, 폐 오일 처리를 위한 수거통 설치 요청"

    output = build_analyzer_output(text, "environment", question=text)

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_low_value_meta_request_segments():
    text = (
        "질의 요지. "
        "사업계획승인 대상 주택 건설사업도 지하안전평가 협의시기 특례가 적용되는지 궁금합니다. "
        "확인 답변 부탁드립니다."
    )

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [
        "사업계획승인 대상 주택 건설사업도 지하안전평가 협의시기 특례가 적용되는지 궁금합니다."
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_objected_installation_request():
    text = "신호위반 단속 카메라 설치 부탁드립니다!"

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_reference_context_only_sentence():
    text = (
        "우리 시 공원주차장을 유료로 운영해 주세요. "
        "참고로 하남시의 공원주차장은 유료로 잘 운영되고 있습니다."
    )

    output = build_analyzer_output(text, "parking", question=text)

    assert output["request_segments"] == ["우리 시 공원주차장을 유료로 운영해 주세요."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_objected_problem_action_request():
    text = "도로 침하 문제에 분명한 조치가 필요합니다."

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_merge_compound_repeated_request():
    text = (
        "코로나 확진시 출석인정 부탁드립니다. "
        "코로나 확진으로 인한 불출석에 대해서는 출석을 인정하여 주실 것을 부탁드립니다."
    )

    output = build_analyzer_output(text, "health", question=text)

    assert output["request_segments"] == [
        "코로나 확진으로 인한 불출석에 대해서는 출석을 인정하여 주실 것을 부탁드립니다."
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_do_not_merge_distinct_dialogue_questions():
    text = "고객: 신고 접수 방법을 알려주세요. 상담원: 처리 기간도 알려주세요."

    output = build_analyzer_output(text, "general", question=text)

    assert output["request_segments"] == [
        "신고 접수 방법을 알려주세요.",
        "처리 기간도 알려주세요.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_strip_meta_request_prefix_and_orphan_parenthesis():
    text = "질의 요지: 경찰에 신고하면 되나요?) 행정에 신고하면 되나요?)"

    output = build_analyzer_output(text, "general", question=text)

    assert output["request_segments"] == [
        "경찰에 신고하면 되나요?",
        "행정에 신고하면 되나요?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_inquiry_intro_and_polite_closing_noise():
    text = (
        "궁금한 것이 있어서 질의드립니다. "
        "포락지 증명은 어떤 방법으로 받을 수 있나요? "
        "친절한 답변 부탁드립니다."
    )

    output = build_analyzer_output(text, "general", question=text)

    assert output["request_segments"] == ["포락지 증명은 어떤 방법으로 받을 수 있나요?"]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_objectless_action_closing_only():
    text = "무단방치 차량 처리요청 합니다. 조속 확인해서 조치 부탁드립니다."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == ["무단방치 차량 처리요청 합니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_action_suffix_title_summary():
    title = "방역요청"
    question = "해충 방역을 요청하고 싶습니다."

    output = build_analyzer_output(
        f"{title}\n{question}",
        "health",
        title=title,
        question=question,
    )

    assert output["request_segments"] == [question]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_objected_action_closing_request():
    text = "버스정류장에 노선별 대기판 설치 부탁드립니다."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_anaphoric_action_only_closing():
    text = "광역버스 배차 간격 단축을 요청합니다. 해결 부탁드립니다. 그렇게 해주십시오."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == ["광역버스 배차 간격 단축을 요청합니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_objected_resolution_request():
    text = "노상주차장 장기 방치 차량 해결 부탁드립니다."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == [text]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_phone_dialogue_meta_and_generic_followup():
    text = (
        "뭐 좀 문의하려 그러는데요. "
        "브런치 콘서트 연간 회원 신청은 어떻게 해야 되나요? "
        "어떻게 하는 건가요?"
    )

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == [
        "브런치 콘서트 연간 회원 신청은 어떻게 해야 되나요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_admin_future_statement_in_phone_dialogue():
    text = "업체 이름과 연락처를 알려주시면 확인해 보겠습니다. 처리 기간은 언제인가요?"

    output = build_analyzer_output(text, "general", question=text)

    assert output["request_segments"] == ["처리 기간은 언제인가요?"]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_legal_basis_context_but_keep_question():
    text = (
        "관련법 제74조에 동일한 소유자에게 속하는 일단의 토지의 잔여지에 대하여 "
        "매수청구가 가능하다고 되어 있어서요. "
        "현재 토지소유자가 잔여지 매수 청구를 할 수 있는지 궁금합니다."
    )

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [
        "현재 토지소유자가 잔여지 매수 청구를 할 수 있는지 궁금합니다."
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_drop_answer_request_closing_in_legal_question():
    text = (
        "녹색건축인증 대상에서 제외가 가능한지 여부가 궁금합니다. "
        "에 대해 답변 부탁드립니다."
    )

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == ["녹색건축인증 대상에서 제외가 가능한지 여부가 궁금합니다."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_specific_short_phone_question():
    text = "1인 4매까지 가능한가요? 주차는 어디로 들어가야 돼요?"

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == [
        "1인 4매까지 가능한가요?",
        "주차는 어디로 들어가야 돼요?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_weak_phone_confirmations_after_specific_question():
    text = (
        "단체 관람 신청은 인터넷으로 하면 되는 건가요? "
        "아 가능해요? "
        "이리 전화해서 금방 그 방법을 물어보면 된다는 말이죠?"
    )

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == [
        "단체 관람 신청은 인터넷으로 하면 되는 건가요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_concrete_phone_questions_with_confirmation_style():
    text = "1인 4매까지 가능한가요? 주차는 어디로 들어가야 돼요?"

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == [
        "1인 4매까지 가능한가요?",
        "주차는 어디로 들어가야 돼요?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_list_intro_and_strip_section_prefix():
    text = (
        "그래서 다음과 같이 건의합니다. "
        "요청 내용가산세 감면 검토 요청드립니다. "
        "납부기한 연장도 요청드립니다."
    )

    output = build_analyzer_output(text, "tax", question=text)

    assert output["request_segments"] == [
        "가산세 감면 검토 요청드립니다.",
        "납부기한 연장도 요청드립니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_phone_admin_questions_and_intro():
    text = (
        "아 문의 좀 드릴게요. "
        "혹시 성함이 어떻게 되시나요? "
        "단체 관람 신청은 인터넷으로 하면 되는 건가요?"
    )

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == [
        "단체 관람 신청은 인터넷으로 하면 되는 건가요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_split_inline_numbered_support_content_questions():
    question = "1. 국내전시회 지원 내용은 뭔가요? 2. 해외전시회 지원 내용은 뭔가요?"

    output = build_analyzer_output(question, "industry", question=question)

    assert output["request_segments"] == [
        "국내전시회 지원 내용은 뭔가요?",
        "해외전시회 지원 내용은 뭔가요?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_split_inline_numbered_nominal_legal_questions():
    question = (
        "1. 개별 설비의 전기 정격용량이 100kW 미만인 설비를 기간을 두어서 설치할 때도 "
        "유해위험방지계획서를 제출해야 하는지 "
        "2. A와 B는 제출하여야 하는지? "
        "3. B사업장이 제출 대상인지?"
    )

    output = build_analyzer_output(question, "labor", question=question)

    assert output["request_segments"] == [
        "개별 설비의 전기 정격용량이 100kW 미만인 설비를 기간을 두어서 설치할 때도 유해위험방지계획서를 제출해야 하는지",
        "A와 B는 제출하여야 하는지?",
        "B사업장이 제출 대상인지?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_strip_answer_request_heading_and_keep_items():
    question = (
        "*답변요청 사항 "
        "1. 공적으로 부부였다는 것을 확인할 수 있는 서류가 무엇이 있는지 알려주시기 바랍니다. "
        "2. 공적확인 서류로 보증인을 대신할 수 있는지 답변주시기 바랍니다."
    )

    output = build_analyzer_output(question, "welfare", question=question)

    assert output["request_segments"] == [
        "공적으로 부부였다는 것을 확인할 수 있는 서류가 무엇이 있는지 알려주시기 바랍니다.",
        "공적확인 서류로 보증인을 대신할 수 있는지 답변주시기 바랍니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_split_numbered_vehicle_subsidy_nominal_items():
    question = (
        "1. 전기자동차 구매보조금 소진여부 및 추가 접수 여부(대기접수가능여부) "
        "2. 지방비 소진된 경우 국비 보조금 별도 신청 가능 여부 "
        "3. 내연전환지원금 대상 차량 요건 및 신청관련 내용"
    )

    output = build_analyzer_output(question, "environment", question=question)

    assert output["request_segments"] == [
        "전기자동차 구매보조금 소진여부",
        "추가 접수 여부(대기접수가능여부)",
        "지방비 소진된 경우 국비 보조금 별도 신청 가능 여부",
        "내연전환지원금 대상 차량 요건",
        "신청관련 내용",
    ]
    assert output["intent_count"] == 5
    assert output["is_multi"] is True


def test_request_segments_keep_direct_question_punctuation_items():
    question = (
        "1. 부당 해고인가요? "
        "2. 계약서 작성 시 연장 근로에 동의하지 않으면 해고의 사유가 될 수가 있나요? "
        "3. 근로자는 합의할 권리가 없는 것인가요?"
    )

    output = build_analyzer_output(question, "labor", question=question)

    assert output["request_segments"] == [
        "부당 해고인가요?",
        "계약서 작성 시 연장 근로에 동의하지 않으면 해고의 사유가 될 수가 있나요?",
        "근로자는 합의할 권리가 없는 것인가요?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_keep_numbered_correctness_여부_item():
    question = (
        "1. 530kgf 이상의 파단 강도를 가진 제품을 선정하는 것이 맞는지 여부. "
        "2. 연결부의 시험 하중이 낮은 이유는?"
    )

    output = build_analyzer_output(question, "labor", question=question)

    assert output["request_segments"] == [
        "530kgf 이상의 파단 강도를 가진 제품을 선정하는 것이 맞는지 여부.",
        "연결부의 시험 하중이 낮은 이유는?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_keep_specific_contact_information_request():
    text = "담당자 연락처를 알려주세요. 신청 가능 기간도 알려주세요."

    output = build_analyzer_output(text, "general", question=text)

    assert output["request_segments"] == [
        "담당자 연락처를 알려주세요.",
        "신청 가능 기간도 알려주세요.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_anaphoric_confirmation_only_segments():
    text = (
        "ACC 투어 대기 신청이 가능한지 알려주세요. "
        "어쨌든 투어 방법은 그 방법밖에 없네요. "
        "아니 일단 해주십시오."
    )

    output = build_analyzer_output(text, "culture", question=text)

    assert output["request_segments"] == ["ACC 투어 대기 신청이 가능한지 알려주세요."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_request_segments_keep_specific_plan_disclosure_request():
    text = "교회 주변 주정차 단속 의지가 있는지요? 의지가 있다면 어떤 계획인지 밝혀주시기 바랍니다."

    output = build_analyzer_output(text, "traffic", question=text)

    assert output["request_segments"] == [
        "교회 주변 주정차 단속 의지가 있는지요?",
        "의지가 있다면 어떤 계획인지 밝혀주시기 바랍니다.",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_numbered_answer_request_closing():
    text = (
        "대수선의 면적은 어떻게 산정하는지 궁금합니다. "
        "품질시험계획 대상 공사에 해당하는지 여부가 궁금합니다. "
        "품질시험계획을 수립해야 하는 것인지요? "
        "바쁘시겠지만, 1번부터 3번까지 질의에 대하여 모두 답변 부탁드립니다."
    )

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [
        "대수선의 면적은 어떻게 산정하는지 궁금합니다.",
        "품질시험계획 대상 공사에 해당하는지 여부가 궁금합니다.",
        "품질시험계획을 수립해야 하는 것인지요?",
    ]
    assert output["intent_count"] == 3
    assert output["is_multi"] is True


def test_request_segments_strip_decorative_question_prefixes():
    text = "☞ 대수선의 면적은 어떻게 산정하는지 궁금합니다. ♣계약 만료일은 언제입니까?"

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [
        "대수선의 면적은 어떻게 산정하는지 궁금합니다.",
        "계약 만료일은 언제입니까?",
    ]
    assert output["intent_count"] == 2
    assert output["is_multi"] is True


def test_request_segments_drop_query_summary_and_answer_notice():
    text = (
        "질의 요약. "
        "신규 제정되는 도면의 관리기관명을 어떻게 기재해야 하나요? "
        "귀하의 민원 내용은 관련 질의로 이해하고 검토한 결과를 안내해 드립니다."
    )

    output = build_analyzer_output(text, "industry", question=text)

    assert output["request_segments"] == [
        "신규 제정되는 도면의 관리기관명을 어떻게 기재해야 하나요?"
    ]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False


def test_generation_fallback_uses_complexity_analyzer_segments():
    from app.api.routers.generation import _derive_request_segments

    text = "도로 보수와 불법주정차 단속을 요청합니다."

    assert _derive_request_segments(text) == [
        "도로 보수 요청합니다.",
        "불법주정차 단속 요청합니다.",
    ]

def test_sentence_splitter_merges_two_digit_orphan_numbered_markers():
    sentences, _source = _split_sentences_with_source("10. 도로 보수 일정을 알려주세요. 11. 임시 안전 조치를 요청합니다.")

    assert sentences == [
        "10. 도로 보수 일정을 알려주세요.",
        "11. 임시 안전 조치를 요청합니다.",
    ]


def test_request_segments_preserve_two_digit_numbered_order():
    text = "10. 도로 보수 일정을 알려주세요. 11. 임시 안전 조치를 요청합니다."

    output = build_analyzer_output(text, "construction", question=text)

    assert output["request_segments"] == [
        "도로 보수 일정을 알려주세요.",
        "임시 안전 조치를 요청합니다.",
    ]
    assert output["intent_count"] == len(output["request_segments"])
    assert output["is_multi"] == (len(output["request_segments"]) >= 2)

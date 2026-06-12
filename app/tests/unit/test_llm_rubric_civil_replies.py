from scripts import evaluate_llm_rubric_civil_replies as rubric


REFERENCE_ANSWER = """
귀하께서 문의하신 어린이보호구역 내 보행 안전시설 개선 요청에 대하여 답변드립니다.
현장 확인 결과 해당 구간은 등하교 시간대 보행자 통행이 많고 차량 진입이 반복되는 곳으로 확인되었습니다.
이에 따라 도로교통법과 어린이보호구역 시설 기준을 검토하고, 교통안전시설 설치 가능 여부를 관계 부서와 협의하겠습니다.
우선 노면표시와 안전표지의 훼손 상태를 점검하여 보수가 필요한 부분은 6월 중 정비할 예정입니다.
추가 시설 설치는 현장 여건과 예산을 검토한 뒤 추진 여부를 안내드리겠습니다.
자세한 사항은 교통안전과 담당자에게 문의하여 주시기 바랍니다. 감사합니다.
""".strip()

OTHER_REFERENCE = """
귀하께서 신고하신 공원 내 조명 고장 사항을 확인한 결과, 해당 보안등의 전원 장치에 이상이 있는 것으로 확인되었습니다.
시설 관리 업체에 보수를 요청하였으며 7월 5일까지 정비를 완료할 예정입니다.
정비 완료 후 야간 점등 상태를 다시 확인하겠습니다. 감사합니다.
""".strip()


def _profile() -> dict:
    return rubric.build_reference_profile(
        [REFERENCE_ANSWER, OTHER_REFERENCE, REFERENCE_ANSWER, OTHER_REFERENCE]
    )


def _row(answer: str, *, strict: bool = True) -> dict:
    return {
        "case_id": "CASE-1",
        "parsed_answer_repaired": answer,
        "citations_count": 3,
        "citations_count_repaired": 3,
        "citations_count_strict": 3 if strict else 0,
        "citation_match_rate": 1.0,
        "citation_match_rate_repaired": 1.0,
        "citation_match_rate_strict": 1.0 if strict else 0.0,
        "citation_support_rate_strict": 1.0 if strict else 0.0,
        "legal_grounding_status": "grounded",
    }


def test_reference_profile_uses_consultant_answer_distribution() -> None:
    profile = _profile()

    assert profile["valid_answer_count"] == 4
    assert profile["length_chars"]["p25"] > 0
    assert profile["length_chars"]["p25"] <= profile["length_chars"]["median"]
    assert profile["length_chars"]["median"] <= profile["length_chars"]["p75"]
    assert 0.0 <= profile["feature_rates"]["action"] <= 1.0


def test_all_rubric_scores_are_on_zero_to_ten_scale() -> None:
    result = rubric.evaluate_row(
        _row(REFERENCE_ANSWER),
        {"category": "교통"},
        "parsed_answer_repaired",
        reference_answer=REFERENCE_ANSWER,
        reference_profile=_profile(),
    )

    for qid in (f"Q{index}" for index in range(9)):
        assert 0.0 <= result["rubric"][qid]["score"] <= 10.0

    assert result["reference_available"] is True
    assert result["reference_alignment"] == 1.0


def test_generated_body_scope_excludes_fixed_reply_shell_from_scores() -> None:
    body = (
        "현장 확인 결과 보행 안전시설의 훼손 여부를 우선 점검하고, "
        "관계 부서와 보수 가능 범위를 협의하겠습니다."
    )
    full_reply = (
        "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
        "2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다.\n\n"
        f"3. 검토 의견은 다음과 같습니다. {body}\n\n"
        "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 "
        "친절히 안내해 드리겠습니다. 감사합니다. 끝."
    )
    body_only = rubric.evaluate_row(
        _row(body),
        {},
        "parsed_answer_repaired",
        reference_answer=body,
        reference_profile=rubric.build_reference_profile([body]),
    )
    with_shell = rubric.evaluate_row(
        _row(full_reply),
        {},
        "parsed_answer_repaired",
        reference_answer=body,
        reference_profile=rubric.build_reference_profile([body]),
    )

    assert rubric.extract_generated_body(full_reply) == body
    assert with_shell["answer_len"] == len(body)
    assert with_shell["rubric"]["Q1"]["score"] == body_only["rubric"]["Q1"]["score"]
    assert with_shell["rubric"]["Q6"]["score"] == body_only["rubric"]["Q6"]["score"]
    assert with_shell["rubric"]["Q0"]["score"] == body_only["rubric"]["Q0"]["score"]
    assert with_shell["reply_shell_diagnostics"]["all_sections_present"] is True
    assert with_shell["reply_shell_diagnostics"]["single_closing"] is True


def test_full_reply_scope_remains_available_for_compatibility() -> None:
    full_reply = (
        "1. 안내드립니다.\n\n"
        "2. 민원 내용입니다.\n\n"
        "3. 검토 의견은 다음과 같습니다. 현장 확인이 필요합니다.\n\n"
        "4. 감사합니다. 끝."
    )
    result = rubric.evaluate_row(
        _row(full_reply),
        {},
        "parsed_answer_repaired",
        reference_answer=full_reply,
        reference_profile=rubric.build_reference_profile(
            [full_reply],
            evaluation_scope="full_reply",
        ),
        evaluation_scope="full_reply",
    )

    assert result["evaluation_scope"] == "full_reply"
    assert result["answer_len"] == len(full_reply)


def test_reference_aligned_reply_scores_higher_than_generic_repaired_reply() -> None:
    strong = rubric.evaluate_row(
        _row(REFERENCE_ANSWER),
        {},
        "parsed_answer_repaired",
        reference_answer=REFERENCE_ANSWER,
        reference_profile=_profile(),
    )
    generic_answer = (
        "귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다. "
        "위 내용을 바탕으로 담당부서에서는 현장 여건, 관련 기준, 유사 처리 사례를 확인한 뒤 "
        "필요한 조치 가능 여부를 판단할 수 있습니다. "
        "확인 결과에 따라 필요한 안내 또는 후속 조치가 이루어질 수 있습니다. 감사합니다."
    )
    weak = rubric.evaluate_row(
        _row(generic_answer, strict=False),
        {},
        "parsed_answer_repaired",
        reference_answer=REFERENCE_ANSWER,
        reference_profile=_profile(),
    )

    assert strong["rubric"]["Q0"]["score"] > weak["rubric"]["Q0"]["score"]
    assert strong["rubric"]["Q5"]["score"] > weak["rubric"]["Q5"]["score"]
    assert weak["rubric"]["Q0"]["score"] <= 5.5
    assert weak["rubric"]["Q3"]["score"] <= 6.0
    assert weak["rubric"]["Q4"]["score"] <= 5.0


def test_zero_reference_alignment_applies_strict_q0_cap() -> None:
    unrelated = (
        "귀하께서 문의하신 도서 대출 기간은 회원 등급에 따라 다릅니다. "
        "도서관 운영 규정을 확인한 뒤 안내 데스크로 문의하여 주시기 바랍니다. 감사합니다."
    )
    result = rubric.evaluate_row(
        _row(unrelated),
        {},
        "parsed_answer_repaired",
        reference_answer=REFERENCE_ANSWER,
        reference_profile=_profile(),
    )

    assert result["rubric"]["Q0"]["score"] <= 5.0
    assert any(
        "reference_alignment" in reason
        for reason in result["rubric"]["Q0"]["reasons"]
    )


def test_report_exposes_scale_and_reference_calibration() -> None:
    profile = _profile()
    score = rubric.evaluate_row(
        _row(REFERENCE_ANSWER),
        {"category": "교통"},
        "parsed_answer_repaired",
        reference_answer=REFERENCE_ANSWER,
        reference_profile=profile,
    )

    report = rubric.build_report([score], profile)

    assert report["score_scale"] == {"min": 0.0, "max": 10.0, "precision": 0.1}
    assert report["paired_reference_count"] == 1
    assert report["reference_profile"]["valid_answer_count"] == 4
    assert sum(report["q0_distribution"].values()) == 1
    assert set(report["category_summary"]["교통"]) == {
        "count",
        "Q0",
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "Q6",
        "Q7",
        "Q8",
    }


def test_reference_constraint_reversal_caps_score() -> None:
    reference = (
        "해당 구간은 도로 폭이 좁아 자전거도로 설치가 어렵습니다. "
        "향후 도로 확폭 시 설치 가능 여부를 검토하겠습니다."
    )
    generated = (
        "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다. "
        "담당부서에서 자전거도로를 즉시 설치하겠습니다. 감사합니다. 끝."
    )

    result = rubric.evaluate_row(
        _row(generated),
        {},
        "parsed_answer_repaired",
        reference_answer=reference,
        reference_profile=_profile(),
    )

    assert "disposition_reversal" in result["semantic_risk_flags"]
    assert result["rubric"]["Q0"]["score"] <= 3.5
    assert result["rubric"]["Q2"]["score"] < 8.0


def test_private_authority_mismatch_is_detected() -> None:
    reference = "해당 시설은 사유지에 있어 소유자와 관리주체가 조치할 사항입니다."
    generated = (
        "귀하의 민원을 확인했습니다. 담당부서에서 해당 시설을 철거하겠습니다. "
        "감사합니다. 끝."
    )

    result = rubric.evaluate_row(
        _row(generated),
        {},
        "parsed_answer_repaired",
        reference_answer=reference,
        reference_profile=_profile(),
    )

    assert "authority_mismatch" in result["semantic_risk_flags"]
    assert result["rubric"]["Q0"]["score"] <= 4.0


def test_unavailable_facility_reply_detects_positive_disposition_reversal() -> None:
    reference = (
        "음악실은 대관 및 개방 대상이 아니며 안전과 보안 문제로 "
        "주말 개방이 불가합니다."
    )
    generated = (
        "학기 중 특정 주말을 지정하여 음악실 사용을 협의해 보겠습니다. "
        "시민 축제 참여를 위한 사용 시간도 우선 검토하겠습니다."
    )

    result = rubric.evaluate_row(
        _row(generated),
        {},
        "parsed_answer_repaired",
        reference_answer=reference,
        reference_profile=_profile(),
    )

    assert "disposition_reversal" in result["semantic_risk_flags"]
    assert result["rubric"]["Q0"]["score"] <= 3.5


def test_unverified_current_fact_is_detected() -> None:
    reference = "현장 방제 여부와 일정은 담당부서 확인 후 안내할 사항입니다."
    generated = "해당 공원에는 이미 예정된 방제 작업이 진행 중입니다."

    result = rubric.evaluate_row(
        _row(generated),
        {},
        "parsed_answer_repaired",
        reference_answer=reference,
        reference_profile=_profile(),
    )

    assert "unverified_current_fact" in result["semantic_risk_flags"]
    assert result["rubric"]["Q0"]["score"] <= 5.5

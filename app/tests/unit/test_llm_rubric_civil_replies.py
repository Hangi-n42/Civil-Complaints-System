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

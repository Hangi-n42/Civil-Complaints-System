from __future__ import annotations

from datetime import datetime, timezone

from app.complaint_intelligence.public_insights.action_repair import repair_action_evidence_ids
from app.complaint_intelligence.public_insights.evidence_pack import (
    PublicInsightEvidencePack,
    evidence_pack_for_llm,
    valid_evidence_ids_for_pack,
)
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicAgencyInsightDraft
from app.complaint_intelligence.schemas import RecommendedAction


def _pack() -> PublicInsightEvidencePack:
    return PublicInsightEvidencePack(
        candidate_id="candidate-action-repair",
        type_hint="PUBLIC_GUIDANCE_NEEDED",
        topic_label="대형폐기물 배출 안내",
        window_start=datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        complaint_count=3,
        representative_complaints=[
            {
                "complaint_id": "complaint-1",
                "source_complaint_ids": ["source-1"],
                "masked_text": "대형폐기물 배출 방법 안내가 부족합니다.",
            },
            {
                "complaint_id": "complaint-2",
                "source_complaint_ids": ["source-2"],
                "masked_text": "스티커 신청 절차를 모르겠습니다.",
            },
        ],
        extracted_aspects=[
            {
                "aspect": "안내 부족",
                "count": 2,
                "sentiment": "negative",
                "evidence_ids": ["complaint-1", "source-1"],
            }
        ],
        citizen_requests=[
            {
                "request": "신청 방법 안내",
                "count": 2,
                "request_type": "정보 제공",
                "evidence_ids": ["complaint-2", "source-2"],
            }
        ],
        allowed_action_catalog=["FAQ/안내 페이지 보강"],
    )


def _draft(action: RecommendedAction) -> PublicAgencyInsightDraft:
    return PublicAgencyInsightDraft(
        title="대형폐기물 배출 안내 개선",
        summary="대형폐기물 안내 민원이 반복됩니다.",
        problem_diagnosis="안내 부족 관련 불편이 반복됩니다.",
        root_cause_hypotheses=[],
        extracted_aspects=[],
        citizen_requests=[],
        recommended_actions=[action],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        uncertainty=[],
        requires_human_review=True,
        explanation="EvidencePack 기반 초안입니다.",
    )


def test_valid_evidence_ids_are_deduplicated_from_representative_aspect_and_request() -> None:
    ids = valid_evidence_ids_for_pack(_pack())

    assert ids == ["complaint-1", "source-1", "complaint-2", "source-2"]


def test_compact_serializer_includes_valid_evidence_ids() -> None:
    payload = evidence_pack_for_llm(_pack(), compact=True)

    assert payload["valid_evidence_ids"] == ["complaint-1", "source-1", "complaint-2", "source-2"]


def test_invalid_evidence_id_is_removed_but_valid_action_is_kept() -> None:
    action = RecommendedAction(
        action="대형폐기물 FAQ와 신청 안내를 보강합니다.",
        horizon="SHORT_TERM",
        action_type="PUBLIC_GUIDANCE",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["complaint-1", "missing-id"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions[0].supporting_evidence_ids == ["complaint-1"]
    assert report.invalid_evidence_ids == ["missing-id"]
    assert report.repaired_action_count == 1


def test_empty_action_gets_clear_aspect_or_request_evidence() -> None:
    action = RecommendedAction(
        action="대형폐기물 안내 페이지를 보강합니다.",
        horizon="SHORT_TERM",
        action_type="PUBLIC_GUIDANCE",
        responsible_unit_hint=None,
        why="안내 부족이 반복됩니다.",
        supporting_evidence_ids=[],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions[0].supporting_evidence_ids
    assert set(repaired.recommended_actions[0].supporting_evidence_ids) <= set(valid_evidence_ids_for_pack(_pack()))
    assert report.repaired_action_count == 1


def test_unclear_empty_action_is_removed() -> None:
    action = RecommendedAction(
        action="종합 개선을 추진합니다.",
        horizon="SHORT_TERM",
        action_type="PROCESS_IMPROVEMENT",
        responsible_unit_hint=None,
        why="일반적인 개선이 필요합니다.",
        supporting_evidence_ids=[],
        expected_impact="효과가 있을 수 있습니다.",
        risk_or_dependency="담당자 검토가 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions == []
    assert report.removed_action_count == 1
    assert "근거 ID가 없거나 불명확한 일부 추천 조치를 제외했습니다." in repaired.uncertainty


def test_invalid_action_type_is_repaired_only_when_keyword_match_is_clear() -> None:
    action = RecommendedAction(
        action="대형폐기물 FAQ와 신청 안내 페이지를 보강합니다.",
        horizon="SHORT_TERM",
        action_type="FIELD_INSPECTION",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["complaint-1"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions[0].action_type == "PUBLIC_GUIDANCE"
    assert repaired.recommended_actions[0].supporting_evidence_ids == ["complaint-1"]
    assert report.invalid_action_type_count == 1
    assert report.repaired_action_type_count == 1
    assert report.removed_action_due_to_action_type_count == 0


def test_invalid_action_type_is_removed_when_match_is_unclear() -> None:
    action = RecommendedAction(
        action="종합 대응 방안을 마련합니다.",
        horizon="SHORT_TERM",
        action_type="FIELD_INSPECTION",
        responsible_unit_hint=None,
        why="반복 민원 대응이 필요합니다.",
        supporting_evidence_ids=["complaint-1"],
        expected_impact="반복 민원 감소 가능성이 있습니다.",
        risk_or_dependency="담당자 검토가 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions == []
    assert report.invalid_action_type_count == 1
    assert report.repaired_action_type_count == 0
    assert report.removed_action_due_to_action_type_count == 1


def test_allowed_but_wrong_action_type_is_repaired_by_preferred_keywords() -> None:
    action = RecommendedAction(
        action="대형폐기물 FAQ와 신청 안내 페이지를 보강합니다.",
        horizon="SHORT_TERM",
        action_type="CITIZEN_COMMUNICATION",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["complaint-1"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions[0].action_type == "PUBLIC_GUIDANCE"
    assert report.repaired_action_type_count == 1
    assert report.action_type_repairs == [{"from": "CITIZEN_COMMUNICATION", "to": "PUBLIC_GUIDANCE"}]


def test_short_abstract_action_text_is_expanded_from_rubric() -> None:
    action = RecommendedAction(
        action="안내 개선",
        horizon="SHORT_TERM",
        action_type="PUBLIC_GUIDANCE",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["complaint-1"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )

    repaired, report = repair_action_evidence_ids(_draft(action), _pack())

    assert repaired.recommended_actions[0].action != "안내 개선"
    assert "FAQ" in repaired.recommended_actions[0].action
    assert report.repaired_action_text_count == 1

from __future__ import annotations

from datetime import datetime, timezone

from app.complaint_intelligence.public_insights.action_rubric import (
    ACTION_TYPE_RUBRIC,
    ALL_ACTION_TYPES,
    TOPIC_ACTION_TYPE_RUBRIC,
    allowed_action_types_for_pack,
    preferred_action_types_for_pack,
    requires_human_review_for_pack,
)
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.quality_gate import InsightQualityGate
from app.complaint_intelligence.schemas import PublicAgencyInsight, RecommendedAction


def _pack(type_hint: str, topic_label: str) -> PublicInsightEvidencePack:
    return PublicInsightEvidencePack(
        candidate_id=f"candidate-{type_hint}",
        type_hint=type_hint,
        topic_label=topic_label,
        window_start=datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        complaint_count=5,
        representative_complaints=[
            {
                "complaint_id": "evidence-1",
                "masked_text": f"{topic_label} 관련 민원이 반복됩니다.",
            }
        ],
    )


def test_action_rubric_uses_only_schema_action_types() -> None:
    allowed = set(ALL_ACTION_TYPES)

    for rubric in ACTION_TYPE_RUBRIC.values():
        assert set(rubric["allowed_action_types"]).issubset(allowed)
        assert set(rubric["preferred_action_types"]).issubset(allowed)
    for _, action_types in TOPIC_ACTION_TYPE_RUBRIC:
        assert set(action_types).issubset(allowed)


def test_safety_topic_returns_field_inspection_safety_and_maintenance() -> None:
    allowed = allowed_action_types_for_pack(_pack("SAFETY_RISK_SIGNAL", "도로 침하/싱크홀 위험"))

    assert allowed[:3] == ["FIELD_INSPECTION", "SAFETY_NOTICE", "MAINTENANCE"]
    assert preferred_action_types_for_pack(_pack("SAFETY_RISK_SIGNAL", "도로 침하/싱크홀 위험"))[0] == "FIELD_INSPECTION"
    assert requires_human_review_for_pack(_pack("SAFETY_RISK_SIGNAL", "도로 침하/싱크홀 위험")) is True


def test_topic_based_rubric_returns_expected_candidates() -> None:
    bulky_waste = allowed_action_types_for_pack(_pack("PUBLIC_GUIDANCE_NEEDED", "대형폐기물 배출 안내"))
    bike = allowed_action_types_for_pack(_pack("SERVICE_DESIGN_IMPROVEMENT", "공공자전거 예약/대여 불편"))
    delay = allowed_action_types_for_pack(_pack("PROCESS_DELAY_RISK", "처리 지연/미처리 누적"))

    assert "PUBLIC_GUIDANCE" in bulky_waste
    assert "SERVICE_DESIGN" in bike
    assert "PROCESS_IMPROVEMENT" in delay
    assert "STAFFING_OR_WORKLOAD_REVIEW" in delay


def test_situation_expansion_topics_return_expected_action_types() -> None:
    cases = [
        ("SAFETY_RISK_SIGNAL", "침수/배수 불량 위험", {"FIELD_INSPECTION", "MAINTENANCE", "SAFETY_NOTICE"}),
        ("ENFORCEMENT_PRIORITY", "무단투기 반복", {"ENFORCEMENT", "MAINTENANCE", "PUBLIC_GUIDANCE"}),
        ("FACILITY_MAINTENANCE_PRIORITY", "공원 시설 파손", {"FIELD_INSPECTION", "MAINTENANCE"}),
        ("SERVICE_DESIGN_IMPROVEMENT", "버스 노선/배차 불편", {"SERVICE_DESIGN", "PUBLIC_GUIDANCE"}),
        ("SAFETY_RISK_SIGNAL", "CCTV/방범 안전 요청", {"FIELD_INSPECTION", "SAFETY_NOTICE", "POLICY_REVIEW"}),
        ("ENFORCEMENT_PRIORITY", "금연구역 흡연 단속 필요", {"ENFORCEMENT", "PUBLIC_GUIDANCE"}),
        ("ENFORCEMENT_PRIORITY", "불법 현수막 정비", {"ENFORCEMENT", "FIELD_INSPECTION"}),
        ("ENFORCEMENT_PRIORITY", "반려동물 배설물/목줄 민원", {"ENFORCEMENT", "PUBLIC_GUIDANCE"}),
        ("PUBLIC_GUIDANCE_NEEDED", "인허가 기준 안내 혼선", {"PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"}),
        ("ACCESSIBILITY_OR_USABILITY_ISSUE", "접근성/사용성 반복 불편", {"SERVICE_DESIGN", "PUBLIC_GUIDANCE"}),
        ("SAFETY_RISK_SIGNAL", "어린이보호구역 통학 안전", {"ENFORCEMENT", "FIELD_INSPECTION", "SAFETY_NOTICE"}),
    ]

    for insight_type, topic, expected in cases:
        allowed = set(allowed_action_types_for_pack(_pack(insight_type, topic)))
        assert expected.issubset(allowed)


def test_low_risk_public_guidance_is_not_forced_to_human_review() -> None:
    pack = _pack("PUBLIC_GUIDANCE_NEEDED", "대형폐기물 배출 안내")

    assert requires_human_review_for_pack(pack) is False


def test_policy_like_guidance_topic_requires_human_review() -> None:
    pack = _pack("PUBLIC_GUIDANCE_NEEDED", "복지 지원 기준/신청 절차")

    assert requires_human_review_for_pack(pack) is True


def test_accessibility_topic_requires_human_review_without_forcing_all_guidance() -> None:
    accessibility_guidance = _pack("PUBLIC_GUIDANCE_NEEDED", "접근성/사용성 반복 불편")
    general_guidance = _pack("PUBLIC_GUIDANCE_NEEDED", "대형폐기물 배출 안내")

    assert requires_human_review_for_pack(accessibility_guidance) is True
    assert requires_human_review_for_pack(general_guidance) is False


def test_quality_gate_rejects_action_type_outside_rubric() -> None:
    pack = _pack("PUBLIC_GUIDANCE_NEEDED", "대형폐기물 배출 안내")
    action = RecommendedAction(
        action="대형폐기물 배출 현장 점검을 실시합니다.",
        horizon="SHORT_TERM",
        action_type="FIELD_INSPECTION",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["evidence-1"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )
    insight = PublicAgencyInsight(
        insight_id="insight-invalid-action-type",
        type="PUBLIC_GUIDANCE_NEEDED",
        priority="MEDIUM",
        title="대형폐기물 배출 안내 개선",
        summary="대형폐기물 배출 안내 민원이 반복됩니다.",
        problem_diagnosis="신청 방법 안내가 부족할 가능성이 있습니다.",
        topic="대형폐기물 배출 안내",
        target_area="행정 안내",
        affected_count=5,
        window_start=pack.window_start,
        window_end=pack.window_end,
        metrics={"avg_actionability_score": 1.0, "min_actionability_score": 1.0},
        evidence=[
            {
                "complaint_id": "evidence-1",
                "masked_text": "대형폐기물 배출 안내가 부족합니다.",
                "received_at": pack.window_start,
            }
        ],
        representative_complaint_ids=["evidence-1"],
        recommended_actions=[action],
        requires_human_review=False,
        confidence=0.8,
        grounding_score=0.9,
        created_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        explanation="EvidencePack 기반 인사이트입니다.",
    )

    result = InsightQualityGate().evaluate(insight, pack)

    assert result.passed is False
    assert any(failure.code == "ACTION_TYPE_RUBRIC_INVALID" for failure in result.failures)

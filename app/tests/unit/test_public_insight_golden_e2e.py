from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.issue_detection import IssueDetectionEngine
from app.complaint_intelligence.public_insights.quality_gate import InsightQualityGate
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, PublicAgencyInsight, RecommendedAction


BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
FORBIDDEN_TERMS = (
    "RAG",
    "retrieval",
    "prompt",
    "model",
    "answer_quality",
    "검색 품질",
    "라우팅 모델",
    "프롬프트",
    "답변 품질",
)


@dataclass(frozen=True)
class GoldenScenario:
    name: str
    events: list[ComplaintIntelligenceEvent]
    expected_types: set[str]
    required_aspects: set[str]
    requires_alerts: bool = False
    expected_fallback: bool = False


def _config():
    return replace(
        get_complaint_intelligence_config(),
        min_recent_count=3,
        min_surge_ratio=2.5,
        semantic_threshold=0.78,
        public_insight_llm_enabled=True,
        public_insight_llm_provider="fake",
        public_insight_min_candidate_complaint_count=4,
        public_insight_min_grounding_score=0.65,
        public_insight_min_confidence=0.45,
    )


def _event(
    event_id: str,
    text: str,
    *,
    region: str = "중구",
    received_at: datetime | None = None,
    hours_ago: float = 1.0,
    status: str | None = None,
    final_department: str | None = None,
    handling_time_minutes: float | None = None,
    reopened: bool = False,
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=received_at or BASE_TIME - timedelta(hours=hours_ago),
        body=text,
        region=region,
        status=status,
        final_department=final_department,
        handling_time_minutes=handling_time_minutes,
        reopened=reopened,
    )


def _scenarios() -> list[GoldenScenario]:
    night = BASE_TIME - timedelta(hours=15)
    commute = BASE_TIME - timedelta(minutes=30)
    return [
        GoldenScenario(
            name="도로 침하/싱크홀 급증",
            events=[
                _event(f"sinkhole-{idx}", text, region="중구", hours_ago=idx * 0.2)
                for idx, text in enumerate(
                    [
                        "OO동 도로에 구멍이 생겼습니다.",
                        "아스팔트가 내려앉았습니다.",
                        "차도 중간이 움푹 파였습니다.",
                        "싱크홀 같은 게 생겼습니다.",
                        "도로 바닥이 꺼져 위험합니다.",
                    ]
                )
            ],
            expected_types={"SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"},
            required_aspects={"현장 안전", "시설 파손"},
            requires_alerts=True,
        ),
        GoldenScenario(
            name="복지 지원 기준·신청 절차 불편 반복",
            events=[
                _event("welfare-1", "복지 지원 기준이 불편합니다.", region="중구"),
                _event("welfare-2", "신청 절차가 너무 복잡합니다.", region="중구"),
                _event("welfare-3", "지원 기준 완화가 필요합니다.", region="중구"),
                _event("welfare-4", "제도 개선을 요청합니다.", region="중구"),
                _event("welfare-5", "필요서류가 무엇인지 모르겠습니다.", region="중구"),
            ],
            expected_types={"POLICY_IMPROVEMENT_OPPORTUNITY", "PUBLIC_GUIDANCE_NEEDED"},
            required_aspects={"신청 절차", "지원 기준"},
        ),
        GoldenScenario(
            name="공공자전거 앱 예약/대여 UX 불편",
            events=[
                _event("bike-1", "공공자전거 앱 예약 절차가 불편합니다.", region="성산동"),
                _event("bike-2", "대여 신청 단계가 너무 복잡합니다.", region="성산동"),
                _event("bike-3", "결제 오류가 자주 납니다.", region="성산동"),
                _event("bike-4", "예약 기준을 이해하기 어렵습니다.", region="성산동"),
                _event("bike-5", "앱 로그인 오류로 대여를 못 했습니다.", region="성산동"),
            ],
            expected_types={"SERVICE_DESIGN_IMPROVEMENT", "ACCESSIBILITY_OR_USABILITY_ISSUE"},
            required_aspects={"접근성/사용성", "신청 절차"},
        ),
        GoldenScenario(
            name="대형폐기물 배출 방법 문의 반복",
            events=[
                _event("waste-1", "대형폐기물 배출 신청 방법을 모르겠습니다.", region="상암동"),
                _event("waste-2", "스티커 구매 안내가 부족합니다.", region="상암동"),
                _event("waste-3", "어디에서 신청해야 하나요?", region="상암동"),
                _event("waste-4", "필요서류가 있나요?", region="상암동"),
                _event("waste-5", "수거 기준 안내가 헷갈립니다.", region="상암동"),
            ],
            expected_types={"PUBLIC_GUIDANCE_NEEDED"},
            required_aspects={"안내 부족", "신청 절차"},
        ),
        GoldenScenario(
            name="불법주정차 특정 시간대 반복",
            events=[
                _event("parking-1", "초등학교 앞 불법주정차가 많습니다.", region="연희동", received_at=commute),
                _event("parking-2", "퇴근 시간마다 불법주차 때문에 위험합니다.", region="연희동", received_at=commute),
                _event("parking-3", "주정차 단속을 강화해주세요.", region="연희동", received_at=commute),
                _event("parking-4", "같은 위치에 계속 불법주차가 반복됩니다.", region="연희동", received_at=commute),
                _event("parking-5", "퇴근 시간대 단속 안내가 필요합니다.", region="연희동", received_at=commute),
            ],
            expected_types={"ENFORCEMENT_PRIORITY", "SEASONAL_OR_TIME_PATTERN"},
            required_aspects={"단속 공백"},
        ),
        GoldenScenario(
            name="악취 민원 야간 집중",
            events=[
                _event(f"odor-{idx}", "야간마다 산업단지 악취와 냄새가 반복됩니다.", region="상암동", received_at=night)
                for idx in range(5)
            ],
            expected_types={"SEASONAL_OR_TIME_PATTERN", "RECURRING_COMPLAINT_PATTERN"},
            required_aspects={"생활환경 불편"},
        ),
        GoldenScenario(
            name="부서 처리 지연/미처리 누적",
            events=[
                _event(
                    f"delay-{idx}",
                    "도로 보수 요청이 아직 처리되지 않았습니다.",
                    region="중구",
                    status="pending",
                    final_department="도로관리과",
                    handling_time_minutes=1800,
                )
                for idx in range(5)
            ],
            expected_types={"PROCESS_DELAY_RISK", "DEPARTMENT_WORKLOAD_BOTTLENECK"},
            required_aspects={"처리 지연"},
        ),
        GoldenScenario(
            name="재민원/반복 민원 증가",
            events=[
                _event(
                    f"repeat-{idx}",
                    "같은 악취 민원이 계속 반복되어 재문의합니다.",
                    region="상암동",
                    status="재민원",
                    reopened=True,
                )
                for idx in range(5)
            ],
            expected_types={"REOPEN_OR_REPEAT_RISK"},
            required_aspects={"생활환경 불편"},
        ),
    ]


def test_public_agency_insight_golden_e2e_scenarios() -> None:
    config = _config()
    issue_engine = IssueDetectionEngine(config=config)
    service = PublicInsightService(config=config)

    for scenario in _scenarios():
        alerts = issue_engine.detect(scenario.events) if scenario.requires_alerts else []
        insights = service.generate_insights(scenario.events, alerts, now=BASE_TIME)
        selected = _select_insight(insights, scenario.expected_types)

        assert selected is not None, scenario.name
        _assert_operational_quality(selected, service.get_evidence_pack(selected.insight_id), scenario)


def test_quality_gate_catches_invalid_evidence_pii_and_ai_ops_terms() -> None:
    config = _config()
    service = PublicInsightService(config=config)
    scenario = _scenarios()[1]
    insight = _select_insight(service.generate_insights(scenario.events, now=BASE_TIME), scenario.expected_types)
    assert insight is not None
    pack = service.get_evidence_pack(insight.insight_id)

    action = insight.recommended_actions[0].model_copy(update={"supporting_evidence_ids": ["missing-id"]})
    bad = insight.model_copy(
        update={
            "summary": insight.summary + " RAG retrieval prompt 010-1234-5678 예산 9999억 조례 제12조 시장 지시",
            "recommended_actions": [action],
        }
    )

    result = InsightQualityGate().evaluate(bad, pack)
    codes = {failure.code for failure in result.failures}
    warning_codes = {warning.code for warning in result.warnings}

    assert result.passed is False
    assert {"EVIDENCE_ID_INVALID", "PII_UNSAFE", "FORBIDDEN_AI_OPS_TERMS", "UNSUPPORTED_ADMIN_CLAIM"}.issubset(codes)
    assert "UNSUPPORTED_NUMERIC_CLAIM" in warning_codes


def test_quality_gate_catches_low_actionability() -> None:
    config = _config()
    service = PublicInsightService(config=config)
    scenario = _scenarios()[3]
    insight = _select_insight(service.generate_insights(scenario.events, now=BASE_TIME), scenario.expected_types)
    assert insight is not None
    pack = service.get_evidence_pack(insight.insight_id)

    weak_action = RecommendedAction(
        action="검토",
        horizon="SHORT_TERM",
        action_type="PUBLIC_GUIDANCE",
        responsible_unit_hint=None,
        why="",
        supporting_evidence_ids=[],
        expected_impact=None,
        risk_or_dependency=None,
    )
    weak = insight.model_copy(update={"recommended_actions": [weak_action]})

    result = InsightQualityGate().evaluate(weak, pack)
    codes = {failure.code for failure in result.failures}

    assert result.passed is False
    assert "ACTIONABILITY_SCORE_LOW" in codes
    assert "ACTION_EVIDENCE_MISSING" in codes


def test_public_insight_evidence_pack_debug_endpoint_returns_masked_pack() -> None:
    client = TestClient(app)
    events = [
        {
            "id": f"debug-{idx}",
            "received_at": (BASE_TIME - timedelta(minutes=idx * 5)).isoformat(),
            "body": "010-1234-5678로 연락 주세요. 대형폐기물 배출 신청 방법 안내가 부족합니다.",
            "region": "상암동",
        }
        for idx in range(5)
    ]

    response = client.post("/complaint-intelligence/public-insights/run-analysis", json={"events": events})
    assert response.status_code == 200
    insight_id = response.json()["data"]["public_insights"][0]["insight_id"]

    pack_response = client.get(f"/complaint-intelligence/public-insights/{insight_id}/evidence-pack")

    assert pack_response.status_code == 200
    payload = pack_response.json()
    serialized = str(payload)
    assert payload["candidate_id"]
    assert payload["representative_complaints"]
    assert "010-1234-5678" not in serialized
    assert "[REDACTED:PHONE]" in serialized


def _select_insight(insights: list[PublicAgencyInsight], expected_types: set[str]) -> PublicAgencyInsight | None:
    return next((insight for insight in insights if insight.type in expected_types), None)


def _assert_operational_quality(
    insight: PublicAgencyInsight,
    pack,
    scenario: GoldenScenario,
) -> None:
    assert insight.type in scenario.expected_types
    aspects = {aspect.aspect for aspect in insight.extracted_aspects}
    assert scenario.required_aspects.intersection(aspects), scenario.name
    assert insight.recommended_actions

    evidence_ids = {
        evidence.complaint_id
        for evidence in insight.evidence
    }
    for evidence in insight.evidence:
        evidence_ids.update(evidence.source_complaint_ids)
    assert evidence_ids

    for action in insight.recommended_actions:
        assert action.supporting_evidence_ids
        assert set(action.supporting_evidence_ids).issubset(evidence_ids)

    if insight.type in {"POLICY_IMPROVEMENT_OPPORTUNITY", "SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"}:
        assert insight.requires_human_review is True

    serialized = insight.model_dump_json()
    assert "010-1234-5678" not in serialized
    assert not any(term in serialized for term in FORBIDDEN_TERMS)

    if scenario.expected_fallback:
        assert any("템플릿" in item or "fallback" in item.lower() for item in insight.uncertainty)

    gate_result = InsightQualityGate().evaluate(insight, pack)
    assert gate_result.passed, gate_result.model_dump()

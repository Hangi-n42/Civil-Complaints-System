from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence.config import ComplaintIntelligenceConfig
from app.complaint_intelligence.issue_detection import IssueDetectionEngine
from app.complaint_intelligence.public_insights import PublicAgencyInsightEngine
from app.complaint_intelligence.public_insights.aspect_extractor import AspectExtractor
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidateGenerator
from app.complaint_intelligence.public_insights.evidence_pack import EvidencePackBuilder
from app.complaint_intelligence.public_insights.grounding_verifier import GroundingVerifier
from app.complaint_intelligence.public_insights.llm_provider import LocalLLMProvider, PublicInsightLLMProvider
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicAgencyInsightDraft
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, PublicInsightType, RecommendedAction


BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def _config(*, llm_enabled: bool = True) -> ComplaintIntelligenceConfig:
    return ComplaintIntelligenceConfig(
        recent_hours=3,
        baseline_days=7,
        min_recent_count=3,
        min_surge_ratio=2.5,
        semantic_threshold=0.78,
        merge_threshold=0.84,
        watch_threshold=0.50,
        warning_threshold=0.70,
        critical_threshold=0.85,
        insight_days=30,
        min_affected_count=4,
        recurring_days=30,
        min_recurring_count=4,
        regional_gap_min_count=4,
        department_bottleneck_min_count=4,
        process_delay_hours=72,
        repeat_risk_count=3,
        night_start_hour=20,
        night_end_hour=6,
        public_insight_enabled=True,
        public_insight_llm_enabled=llm_enabled,
        public_insight_llm_provider="fake",
        public_insight_llm_base_url="",
        public_insight_llm_model="",
        public_insight_llm_timeout_seconds=30,
        public_insight_llm_temperature=0.0,
        public_insight_llm_num_ctx=4096,
        public_insight_llm_num_predict=1536,
        public_insight_llm_num_gpu=-1,
        public_insight_llm_keep_alive="10m",
        public_insight_llm_stream=False,
        public_insight_max_representative_complaints=8,
        public_insight_max_evidence_chars_per_complaint=500,
        public_insight_min_candidate_complaint_count=4,
        public_insight_min_grounding_score=0.65,
        public_insight_min_confidence=0.45,
        public_insight_analysis_window_days=30,
        public_insight_recent_window_hours=3,
        public_insight_baseline_window_days=7,
        public_insight_high_repeat_count=10,
        public_insight_process_delay_minutes_threshold=1440,
        public_insight_reopen_rate_threshold=0.20,
        public_insight_regional_concentration_threshold=0.40,
        public_insight_priority_high_threshold=0.70,
        public_insight_priority_critical_threshold=0.85,
        public_insight_fallback_on_llm_error=True,
        public_insight_require_human_review_for_policy=True,
        public_insight_require_human_review_for_safety=True,
        score_weight_count=0.30,
        score_weight_surge=0.25,
        score_weight_cohesion=0.20,
        score_weight_spatial=0.15,
        score_weight_risk=0.10,
    )


def _event(
    event_id: str,
    text: str,
    *,
    hours_ago: float = 1.0,
    days_ago: int = 0,
    received_at: datetime | None = None,
    region: str = "중구",
    status: str | None = None,
    final_department: str | None = None,
    handling_time_minutes: float | None = None,
    reopened: bool = False,
    reviewer_feedback: str | None = None,
    structured_elements: dict | None = None,
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=received_at or BASE_TIME - timedelta(days=days_ago, hours=hours_ago),
        body=text,
        region=region,
        status=status,
        final_department=final_department,
        handling_time_minutes=handling_time_minutes,
        reopened=reopened,
        reviewer_feedback=reviewer_feedback,
        structured_elements=structured_elements or {},
    )


def _public_service(
    *,
    config: ComplaintIntelligenceConfig | None = None,
    provider: PublicInsightLLMProvider | None = None,
) -> PublicInsightService:
    cfg = config or _config()
    return PublicInsightService(config=cfg, llm_provider=provider)


def _types(insights: list) -> set[str]:
    return {insight.type for insight in insights}


def test_welfare_policy_and_guidance_insight_has_aspects_actions_and_hypotheses() -> None:
    events = [
        _event("policy-1", "복지 지원 기준이 불편합니다.", region="중구"),
        _event("policy-2", "신청 절차가 너무 복잡합니다.", region="중구"),
        _event("policy-3", "지원 기준 완화가 필요합니다.", region="중구"),
        _event("policy-4", "제도 개선을 요청합니다.", region="중구"),
        _event("policy-5", "필요서류가 무엇인지 모르겠습니다.", region="중구"),
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    selected = next(
        insight for insight in insights
        if insight.type in {"POLICY_IMPROVEMENT_OPPORTUNITY", "PUBLIC_GUIDANCE_NEEDED"}
    )

    aspects = {aspect.aspect for aspect in selected.extracted_aspects}
    assert {"신청 절차", "지원 기준"}.issubset(aspects)
    assert selected.problem_diagnosis
    assert selected.recommended_actions
    assert any("체크리스트" in action.action or "FAQ" in action.action or "신청" in action.action for action in selected.recommended_actions)
    assert all(action.supporting_evidence_ids for action in selected.recommended_actions)
    assert all(hypothesis.needs_human_validation for hypothesis in selected.root_cause_hypotheses)
    assert selected.requires_human_review is True


def test_structured_four_elements_seed_aspects_requests_and_context() -> None:
    events = [
        _event(
            f"structured-bike-{index}",
            "확인 부탁드립니다.",
            region="성산동",
            structured_elements={
                "observation": {"text": "공공자전거 예약 단계가 복잡하고 결제 오류가 발생합니다."},
                "result": {"text": "출근 시간대 대여가 지연되어 이용자가 다시 문의합니다."},
                "request": {"text": "공공자전거 신청 절차 개선 요청"},
                "context": {"text": "성산동 지하철역 주변 출근 시간대 반복 민원"},
            },
        )
        for index in range(4)
    ]

    candidates = PublicInsightCandidateGenerator(config=_config()).generate(events, [], BASE_TIME)
    assert "SERVICE_DESIGN_IMPROVEMENT" in {candidate.type_hint for candidate in candidates}

    candidate = next(candidate for candidate in candidates if candidate.type_hint == "SERVICE_DESIGN_IMPROVEMENT")
    pack = AspectExtractor().enrich(EvidencePackBuilder(config=_config()).build(candidate, events, []))

    assert pack.topic_label == "공공자전거 이용"
    assert any("출근" in phrase or "성산동" in phrase for phrase in pack.key_phrases)
    assert all("structured_elements" in item for item in pack.representative_complaints)
    assert {"신청 절차", "접근성/사용성"}.intersection({aspect["aspect"] for aspect in pack.extracted_aspects})
    request = next(item for item in pack.citizen_requests if item["request_type"] == "절차 개선")
    assert set(request["evidence_ids"]) == {event.id for event in events}


def test_structured_confidence_spans_and_result_context_metrics_are_promoted() -> None:
    events = [
        _event(
            f"structured-metric-{index}",
            "확인 부탁드립니다.",
            region="성산동",
            structured_elements={
                "observation": {
                    "text": "공공자전거 예약 단계가 복잡하고 결제 오류가 발생합니다.",
                    "confidence": 0.91,
                    "evidence_span": [0, 28],
                },
                "result": {
                    "text": "출근 시간대 대여 지연으로 이용 불편이 반복됩니다.",
                    "confidence": 0.82,
                    "evidence_span": [29, 55],
                },
                "request": {
                    "text": "신청 절차 개선 요청",
                    "confidence": 0.88,
                    "evidence_span": [56, 68],
                },
                "context": {
                    "text": "성산동 지하철역 주변 출근 시간대 반복 민원",
                    "confidence": 0.79,
                    "evidence_span": [69, 93],
                },
            },
        )
        for index in range(4)
    ]

    candidate = next(
        candidate for candidate in PublicInsightCandidateGenerator(config=_config()).generate(events, [], BASE_TIME)
        if candidate.type_hint == "SERVICE_DESIGN_IMPROVEMENT"
    )
    pack = AspectExtractor().enrich(EvidencePackBuilder(config=_config()).build(candidate, events, []))

    aspect = next(item for item in pack.extracted_aspects if item["aspect"] == "접근성/사용성")
    request = next(item for item in pack.citizen_requests if item["request_type"] == "절차 개선")

    assert aspect["confidence"] == 0.937
    assert request["confidence"] == 0.916
    assert len(aspect["evidence_spans"]) == 4
    assert aspect["evidence_spans"][0]["field"] == "observation"
    assert pack.operational_metrics["structured_result_impact_count"] == 4
    assert pack.operational_metrics["structured_result_avg_confidence"] == 0.82
    assert pack.operational_metrics["avg_aspect_confidence"] >= 0.87
    assert pack.operational_metrics["avg_request_confidence"] == 0.916
    assert pack.operational_metrics["aspect_evidence_span_count"] >= 4
    assert pack.operational_metrics["request_evidence_span_count"] == 4
    assert pack.trend_metrics["structured_context_time_pattern_count"] == 4
    assert pack.trend_metrics["structured_context_repeat_pattern_count"] == 4


def test_structured_request_drives_type_when_raw_text_has_weak_keywords() -> None:
    events = [
        _event(
            f"structured-park-{index}",
            "확인 요청드립니다.",
            region="연희동",
            structured_elements={
                "observation": {"text": "초등학교 앞 불법주정차가 반복됩니다."},
                "result": {"text": "보행 안전 위험이 커졌습니다."},
                "request": {"text": "퇴근 시간대 주정차 단속 강화 요청"},
                "context": {"text": "연희동 초등학교 앞 같은 위치에서 반복"},
            },
        )
        for index in range(4)
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    enforcement = next(insight for insight in insights if insight.type == "ENFORCEMENT_PRIORITY")

    assert enforcement.representative_complaint_ids
    assert any(request.request_type == "단속 강화" for request in enforcement.citizen_requests)
    assert all(action.supporting_evidence_ids for action in enforcement.recommended_actions)


def test_public_bicycle_app_flow_creates_service_design_insight() -> None:
    events = [
        _event("bike-1", "공공자전거 앱 예약 절차가 불편합니다.", region="성산동"),
        _event("bike-2", "대여 신청 단계가 너무 복잡합니다.", region="성산동"),
        _event("bike-3", "결제 오류가 자주 납니다.", region="성산동"),
        _event("bike-4", "예약 기준을 이해하기 어렵습니다.", region="성산동"),
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    selected = next(insight for insight in insights if insight.type in {"SERVICE_DESIGN_IMPROVEMENT", "ACCESSIBILITY_OR_USABILITY_ISSUE"})

    assert "공공자전거" in selected.topic or "대여" in selected.topic or "앱" in selected.title
    assert any(action.action_type in {"SERVICE_DESIGN", "PUBLIC_GUIDANCE"} for action in selected.recommended_actions)


def test_bulky_waste_questions_create_public_guidance_needed() -> None:
    events = [
        _event("waste-1", "대형폐기물 배출 신청 방법을 모르겠습니다.", region="상암동"),
        _event("waste-2", "스티커 구매 안내가 부족합니다.", region="상암동"),
        _event("waste-3", "어디에서 신청해야 하나요?", region="상암동"),
        _event("waste-4", "필요서류가 있나요?", region="상암동"),
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    guidance = next(insight for insight in insights if insight.type == "PUBLIC_GUIDANCE_NEEDED")

    assert any("FAQ" in action.action or "안내" in action.action or "고지문" in action.action for action in guidance.recommended_actions)
    assert guidance.evidence


def test_sinkhole_surge_links_issue_alert_to_public_safety_insight() -> None:
    events = [
        _event(f"sink-{index}", text, hours_ago=index * 0.2, region="중구")
        for index, text in enumerate(
            [
                "OO동 도로에 구멍이 생겼습니다.",
                "아스팔트가 내려앉았습니다.",
                "차도 중간이 움푹 파였습니다.",
                "싱크홀 같은 게 생겼습니다.",
                "도로 바닥이 꺼져 위험합니다.",
            ]
        )
    ]
    alerts = IssueDetectionEngine(config=_config()).detect(events)

    insights = _public_service().generate_insights(events, alerts, now=BASE_TIME)

    assert alerts
    assert {"SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"}.intersection(_types(insights))
    safety = next(insight for insight in insights if insight.linked_alert_ids)
    assert safety.priority in {"HIGH", "CRITICAL", "MEDIUM"}
    assert any(action.action_type in {"FIELD_INSPECTION", "SAFETY_NOTICE", "MAINTENANCE"} for action in safety.recommended_actions)


def test_illegal_parking_repetition_creates_enforcement_priority() -> None:
    events = [
        _event("park-1", "초등학교 앞 불법주정차가 많습니다.", region="연희동"),
        _event("park-2", "퇴근 시간마다 불법주차 때문에 위험합니다.", region="연희동"),
        _event("park-3", "주정차 단속을 강화해주세요.", region="연희동"),
        _event("park-4", "같은 위치에 계속 불법주차가 반복됩니다.", region="연희동"),
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    enforcement = next(insight for insight in insights if insight.type == "ENFORCEMENT_PRIORITY")

    assert any(action.action_type == "ENFORCEMENT" for action in enforcement.recommended_actions)
    assert "단속" in enforcement.summary or any("단속" in action.action for action in enforcement.recommended_actions)


def test_process_delay_and_department_bottleneck_are_administrative_not_model_insights() -> None:
    events = [
        _event(
            f"delay-{index}",
            "도로 보수 요청이 아직 처리되지 않았습니다.",
            status="pending",
            final_department="도로관리과",
            handling_time_minutes=1800,
        )
        for index in range(5)
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)

    assert {"PROCESS_DELAY_RISK", "DEPARTMENT_WORKLOAD_BOTTLENECK"}.issubset(_types(insights))
    assert all("라우팅" not in insight.summary for insight in insights)
    assert any(action.action_type in {"PROCESS_IMPROVEMENT", "STAFFING_OR_WORKLOAD_REVIEW"} for insight in insights for action in insight.recommended_actions)


def test_reopened_complaints_create_repeat_risk() -> None:
    events = [
        _event(f"repeat-{index}", "같은 악취 민원이 계속 반복되어 재문의합니다.", reopened=True, status="재민원")
        for index in range(4)
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)

    assert "REOPEN_OR_REPEAT_RISK" in _types(insights)
    repeat = next(insight for insight in insights if insight.type == "REOPEN_OR_REPEAT_RISK")
    assert any(action.supporting_evidence_ids for action in repeat.recommended_actions)


def test_grounding_verifier_removes_unsupported_claims_and_lowers_score() -> None:
    events = [
        _event(f"policy-{index}", "복지 지원 신청 절차와 기준 안내가 어렵습니다.", region="중구")
        for index in range(4)
    ]
    candidate = PublicInsightCandidateGenerator(config=_config()).generate(events, [], BASE_TIME)[0]
    pack = AspectExtractor().enrich(EvidencePackBuilder(config=_config()).build(candidate, events, []))
    draft = PublicAgencyInsightDraft(
        title="중구 복지 지원 개선",
        summary="예산 3억 원이 필요하고 조례 제12조에 따라 즉시 변경 가능합니다.",
        problem_diagnosis="시장 지시 사항으로 확인되었습니다.",
        root_cause_hypotheses=[],
        extracted_aspects=pack.extracted_aspects,
        citizen_requests=pack.citizen_requests,
        recommended_actions=[
            RecommendedAction(
                action="예산 3억 원을 배정해 즉시 변경합니다.",
                horizon="SHORT_TERM",
                action_type="POLICY_REVIEW",
                responsible_unit_hint="복지정책과",
                why="조례 제12조에 따라 가능합니다.",
                supporting_evidence_ids=[pack.representative_complaints[0]["complaint_id"]],
                expected_impact="즉시 해결됩니다.",
                risk_or_dependency=None,
            )
        ],
        expected_impact="즉시 해결됩니다.",
        uncertainty=[],
        requires_human_review=False,
        explanation="시장 지시 사항입니다.",
    )

    verified = GroundingVerifier().verify_and_repair(draft, pack)

    assert verified.grounding_score < 1.0
    assert verified.recommended_actions == []
    assert verified.uncertainty
    assert "3억" not in verified.summary


def test_pii_input_never_reaches_public_insight_text_fields() -> None:
    events = [
        _event(
            f"pii-{index}",
            "010-1234-5678로 연락 주세요. 서울로 123 101동 202호 앞 도로가 꺼졌습니다.",
            region="중구",
        )
        for index in range(4)
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    serialized = " ".join(insight.model_dump_json() for insight in insights)

    assert "010-1234-5678" not in serialized
    assert "101동 202호" not in serialized
    assert "[REDACTED:PHONE]" in serialized


def test_structured_fields_are_masked_in_evidence_pack_and_insight() -> None:
    events = [
        _event(
            f"structured-pii-{index}",
            "확인 바랍니다.",
            region="중구",
            structured_elements={
                "observation": {"text": "서울로 123 101동 202호 앞 도로가 침하되었습니다."},
                "result": {"text": "010-1234-5678로 연락 달라는 안전 위험 문의가 반복됩니다."},
                "request": {"text": "현장 점검 요청"},
                "context": {"text": "101동 202호 주변 같은 위치 반복"},
            },
        )
        for index in range(4)
    ]

    candidate = PublicInsightCandidateGenerator(config=_config()).generate(events, [], BASE_TIME)[0]
    pack = EvidencePackBuilder(config=_config()).build(candidate, events, [])
    pack_json = pack.model_dump_json()

    assert "010-1234-5678" not in pack_json
    assert "101동 202호" not in pack_json
    assert "[REDACTED:PHONE]" in pack_json

    insights = _public_service().generate_insights(events, now=BASE_TIME)
    serialized = " ".join(insight.model_dump_json() for insight in insights)

    assert "010-1234-5678" not in serialized
    assert "101동 202호" not in serialized
    assert "[REDACTED:PHONE]" in serialized


class FailingProvider:
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise TimeoutError("timeout")


def test_llm_failure_uses_fallback_template() -> None:
    events = [
        _event(f"fallback-{index}", "대형폐기물 배출 신청 방법 안내가 부족합니다.", region="상암동")
        for index in range(4)
    ]

    insights = _public_service(provider=FailingProvider()).generate_insights(events, now=BASE_TIME)

    assert insights
    assert any("템플릿 기반" in item for insight in insights for item in insight.uncertainty)
    assert all(insight.grounding_score >= 0.65 for insight in insights)


def test_public_insight_without_structured_elements_still_uses_masked_text_rules() -> None:
    events = [
        _event(f"plain-waste-{index}", "대형폐기물 배출 신청 방법 안내가 부족합니다.", region="상암동")
        for index in range(4)
    ]

    insights = _public_service().generate_insights(events, now=BASE_TIME)

    assert "PUBLIC_GUIDANCE_NEEDED" in _types(insights)
    guidance = next(insight for insight in insights if insight.type == "PUBLIC_GUIDANCE_NEEDED")
    assert guidance.citizen_requests
    assert guidance.extracted_aspects


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_local_llm_provider_parses_ollama_generate_json_code_fence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse({"response": "```json\n{\"title\": \"ok\", \"summary\": \"done\"}\n```"})

    monkeypatch.setattr("app.complaint_intelligence.public_insights.llm_provider.urllib.request.urlopen", fake_urlopen)
    config = replace(
        _config(),
        public_insight_llm_provider="local",
        public_insight_llm_base_url="http://localhost:11434",
        public_insight_llm_model="exaone3.5:7.8b",
    )

    result = LocalLLMProvider(config).generate_json("prompt", {"type": "object"})

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["payload"]["model"] == "exaone3.5:7.8b"
    assert captured["payload"]["format"] == {"type": "object"}
    assert captured["payload"]["options"]["num_gpu"] == -1
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["num_predict"] == 1536
    assert captured["payload"]["keep_alive"] == "10m"
    assert captured["payload"]["stream"] is False
    assert result == {"title": "ok", "summary": "done"}


def test_local_llm_provider_parses_ollama_chat_message_content(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse({"message": {"content": "{\"title\": \"chat-ok\"}"}})

    monkeypatch.setattr("app.complaint_intelligence.public_insights.llm_provider.urllib.request.urlopen", fake_urlopen)
    config = replace(
        _config(),
        public_insight_llm_provider="local",
        public_insight_llm_base_url="http://localhost:11434/api/chat",
        public_insight_llm_model="exaone3.5:7.8b",
    )

    result = LocalLLMProvider(config).generate_json("prompt", {})

    assert "messages" in captured["payload"]
    assert captured["payload"]["options"]["temperature"] == 0.0
    assert result == {"title": "chat-ok"}


class _FakeStreamingResponse:
    def __init__(self, lines: list[dict]) -> None:
        self.lines = [(json.dumps(line) + "\n").encode("utf-8") for line in lines]

    def __enter__(self) -> "_FakeStreamingResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def __iter__(self):
        return iter(self.lines)


def test_local_llm_provider_parses_ollama_streaming_generate_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeStreamingResponse(
            [
                {"response": "{\"title\":", "done": False},
                {"response": "\"stream-ok\"}", "done": False},
                {"done": True},
            ]
        )

    monkeypatch.setattr("app.complaint_intelligence.public_insights.llm_provider.urllib.request.urlopen", fake_urlopen)
    config = replace(
        _config(),
        public_insight_llm_provider="local",
        public_insight_llm_base_url="http://localhost:11434",
        public_insight_llm_model="exaone3.5:7.8b",
        public_insight_llm_stream=True,
    )

    result = LocalLLMProvider(config).generate_json("prompt", {})

    assert captured["payload"]["stream"] is True
    assert result == {"title": "stream-ok"}


def test_public_insight_type_literal_matches_requested_types() -> None:
    expected = {
        "HOTSPOT_RESPONSE_REQUIRED",
        "SAFETY_RISK_SIGNAL",
        "RECURRING_COMPLAINT_PATTERN",
        "REGIONAL_SERVICE_GAP",
        "DEPARTMENT_WORKLOAD_BOTTLENECK",
        "PROCESS_DELAY_RISK",
        "REOPEN_OR_REPEAT_RISK",
        "SEASONAL_OR_TIME_PATTERN",
        "PUBLIC_GUIDANCE_NEEDED",
        "FACILITY_MAINTENANCE_PRIORITY",
        "ENFORCEMENT_PRIORITY",
        "POLICY_IMPROVEMENT_OPPORTUNITY",
        "SERVICE_DESIGN_IMPROVEMENT",
        "ACCESSIBILITY_OR_USABILITY_ISSUE",
        "CITIZEN_COMMUNICATION_GAP",
    }

    assert set(PublicInsightType.__args__) == expected


def test_public_insight_api_run_analysis_and_lookup() -> None:
    client = TestClient(app)
    events = [
        {
            "id": f"api-{index}",
            "received_at": (BASE_TIME - timedelta(minutes=index * 10)).isoformat(),
            "body": f"도로 싱크홀 침하 구멍 위험 신고 {index}",
            "region": "중구",
        }
        for index in range(5)
    ]

    response = client.post("/complaint-intelligence/public-insights/run-analysis", json={"events": events})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["public_insight_count"] >= 1
    insight_id = data["public_insights"][0]["insight_id"]
    detail = client.get(f"/complaint-intelligence/public-insights/{insight_id}")
    assert detail.status_code == 200
    assert detail.json()["insight_id"] == insight_id


def test_complaint_intelligence_dashboard_returns_fe_ready_cards() -> None:
    client = TestClient(app)
    events = [
        {
            "id": f"dashboard-{index}",
            "received_at": (BASE_TIME - timedelta(minutes=index * 5)).isoformat(),
            "body": f"OO동 도로 싱크홀 침하 구멍 위험 신고 {index}",
            "region": "중구",
        }
        for index in range(5)
    ]

    response = client.post("/complaint-intelligence/dashboard/run-analysis", json={"events": events})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tabs"] == [
        {"id": "issue_alerts", "label": "실시간 이슈"},
        {"id": "public_insights", "label": "행정 인사이트"},
    ]
    assert data["summary"]["alert_count"] >= 1
    assert data["summary"]["public_insight_count"] >= 1
    assert data["issue_alerts"][0]["color"] in {"gray", "amber", "red"}
    assert data["issue_alerts"][0]["representative_complaint_ids"]
    insight_card = data["public_insights"][0]
    assert insight_card["id"]
    assert insight_card["priority_label"]
    assert insight_card["recommended_actions"]
    assert insight_card["representative_evidence_ids"]

    list_response = client.get("/complaint-intelligence/dashboard")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["summary"]["public_insight_count"] >= 1

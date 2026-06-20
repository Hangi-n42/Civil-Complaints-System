from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.issue_detection.engine import IssueDetectionEngine
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.service import ComplaintIntelligenceService


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


def _config():
    return replace(
        get_complaint_intelligence_config(),
        repository="memory",
        min_recent_count=3,
        min_surge_ratio=1.5,
        semantic_threshold=0.78,
        public_insight_llm_enabled=True,
        public_insight_llm_provider="fake",
        public_insight_min_candidate_complaint_count=4,
        public_insight_regional_concentration_threshold=0.4,
    )


def _event(
    event_id: str,
    text: str,
    *,
    region: str = "중구",
    minutes_ago: int = 10,
    status: str = "open",
    final_department: str = "민원담당과",
    handling_time_minutes: float | None = None,
    reopened: bool = False,
    user_feedback_score: float | None = None,
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=BASE_TIME - timedelta(minutes=minutes_ago),
        body=text,
        region=region,
        status=status,
        final_department=final_department,
        handling_time_minutes=handling_time_minutes,
        reopened=reopened,
        user_feedback_score=user_feedback_score,
    )


def test_issue_alert_topic_labels_are_concrete_for_guidance_odor_and_bike() -> None:
    engine = IssueDetectionEngine(config=_config())

    waste_alerts = engine.detect(
        [
            _event(f"waste-{idx}", text, region="동구", minutes_ago=idx + 1)
            for idx, text in enumerate(
                [
                    "대형폐기물 배출 신청 방법을 모르겠습니다.",
                    "대형폐기물 스티커 구매 안내가 부족합니다.",
                    "대형폐기물 수거 신청은 어디에서 하나요?",
                    "대형폐기물 배출 기준과 방법 안내가 필요합니다.",
                    "대형폐기물 스티커와 수거 일정을 알려주세요.",
                ]
            )
        ]
    )
    odor_alerts = engine.detect(
        [
            _event(f"odor-{idx}", text, region="남구", minutes_ago=idx + 1)
            for idx, text in enumerate(
                [
                    "밤마다 하수 악취 냄새가 올라옵니다.",
                    "야간 하수 냄새가 심해서 창문을 열 수 없습니다.",
                    "새벽에 하수 악취가 반복됩니다.",
                    "하수구 냄새와 악취가 밤에 집중됩니다.",
                    "야간 악취 현장 점검을 요청합니다.",
                ]
            )
        ]
    )
    bike_alerts = engine.detect(
        [
            _event(f"bike-{idx}", text, region="성동구", minutes_ago=idx + 1)
            for idx, text in enumerate(
                [
                    "공공자전거 앱 예약 절차가 불편합니다.",
                    "자전거 대여 중 결제 오류가 반복됩니다.",
                    "공공자전거 예약과 대여 화면이 너무 복잡합니다.",
                    "앱 로그인 오류로 공공자전거를 빌리지 못했습니다.",
                    "예약 취소 후 다시 대여하는 절차가 어렵습니다.",
                ]
            )
        ]
    )

    assert any(alert.topic == "대형폐기물 배출 안내" for alert in waste_alerts)
    assert any(alert.topic == "야간 하수 악취" for alert in odor_alerts)
    assert any(alert.topic == "공공자전거 예약/대여 불편" for alert in bike_alerts)


def test_operational_backlog_reopen_and_accessibility_rules_create_alerts() -> None:
    engine = IssueDetectionEngine(config=_config())

    backlog_alerts = engine.detect(
        [
            _event(
                f"delay-{idx}",
                "처리되지 않은 도로 보수 민원입니다.",
                final_department="도로관리과",
                status="pending",
                handling_time_minutes=2400,
                minutes_ago=idx + 1,
            )
            for idx in range(5)
        ]
    )
    repeat_alerts = engine.detect(
        [
            _event(
                f"repeat-{idx}",
                "같은 악취 민원이 반복되어 다시 접수합니다.",
                final_department="환경관리과",
                reopened=True,
                user_feedback_score=1.0,
                minutes_ago=idx + 1,
            )
            for idx in range(5)
        ]
    )
    accessibility_alerts = engine.detect(
        [
            _event(
                f"access-{idx}",
                "고령자와 장애인이 앱 신청 절차를 쓰기 어렵고 접근성이 낮습니다.",
                final_department="디지털민원지원팀",
                minutes_ago=idx + 1,
            )
            for idx in range(5)
        ]
    )

    assert any(alert.trigger_type == "OPERATIONAL_BACKLOG" for alert in backlog_alerts)
    assert any(alert.trigger_type == "REOPEN_REPEAT" for alert in repeat_alerts)
    assert any(alert.trigger_type == "SERVICE_ACCESSIBILITY_PATTERN" for alert in accessibility_alerts)


def test_negative_low_count_and_dispersed_events_do_not_create_severe_alerts_or_high_priority_insights() -> None:
    service = ComplaintIntelligenceService(config=_config())
    low_count_events = [
        _event("negative-low-1", "대형폐기물 배출 스티커 문의가 있습니다.", region="중구"),
        _event("negative-low-2", "공원 벤치 위치를 알고 싶습니다.", region="마포구"),
    ]
    dispersed_events = [
        _event(f"negative-dispersed-{idx}", "도로 구멍 보수 문의입니다.", region=region, minutes_ago=9000 - idx * 1800)
        for idx, region in enumerate(["중구", "강남구", "마포구", "성동구", "관악구"])
    ]

    low_count = service.run_analysis(low_count_events, mode="replay", as_of=BASE_TIME)
    dispersed = service.run_analysis(dispersed_events, mode="replay", as_of=BASE_TIME)
    alerts = low_count.alerts + dispersed.alerts
    insights = low_count.public_insights + dispersed.public_insights

    assert not [alert for alert in alerts if alert.severity in {"WARNING", "CRITICAL"}]
    assert not [
        insight for insight in insights
        if insight.priority in {"HIGH", "CRITICAL"}
        and not insight.linked_alert_ids
    ]

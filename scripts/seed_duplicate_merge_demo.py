"""중복 민원 병합 UI 검증용 seed와 read-model을 생성한다."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeConflict
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from scripts.seed_complaint_intelligence_demo import build_service, contains_unmasked_pii, write_report


DEFAULT_SEED = Path("data/complaint_intelligence/duplicate_merge_demo_events.json")
DEFAULT_DB_PATH = Path("data/complaint_intelligence/duplicate_merge_demo.db")
DEFAULT_REPORT = Path("reports/duplicate_merge_demo_seed_report.json")
DEFAULT_AS_OF = datetime.fromisoformat("2026-06-20T09:00:00+09:00")
SOURCE_NAME = "duplicate_merge_demo"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed duplicate merge UI demo read-model.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    report = run_duplicate_merge_demo(
        seed_path=Path(args.seed),
        db_path=Path(args.db_path),
        report_path=Path(args.report),
        base_url=args.base_url,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 1


def run_duplicate_merge_demo(
    *,
    seed_path: Path = DEFAULT_SEED,
    db_path: Path = DEFAULT_DB_PATH,
    report_path: Path = DEFAULT_REPORT,
    as_of: datetime = DEFAULT_AS_OF,
    base_url: str | None = None,
) -> dict[str, Any]:
    seed = build_duplicate_merge_seed(as_of=as_of)
    events = _seed_events(seed)
    service = build_service(db_path, demo_thresholds=False)
    service.clear()

    result = service.run_analysis(
        events,
        mode=str(seed["mode"]),
        source_name=SOURCE_NAME,
        as_of=as_of,
        metadata={"trigger": "duplicate_merge_demo_seed", "seed_file": str(seed_path)},
    )
    groups = service.run_duplicate_analysis(
        events,
        mode=str(seed["mode"]),
        source_name=SOURCE_NAME,
        as_of=as_of,
    )

    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()
    draft_results = _validate_draft_contract(service, groups)
    updated_groups = service.list_duplicate_groups()
    scenario_results = _validate_duplicate_scenarios(seed, updated_groups)
    pii_result = _validate_pii(seed, alerts, insights, updated_groups, draft_results)
    http_result = _verify_http(base_url) if base_url else None

    report: dict[str, Any] = {
        "seed": str(seed_path),
        "db_path": str(db_path),
        "source_name": SOURCE_NAME,
        "mode": seed["mode"],
        "as_of": seed["as_of"],
        "run_id": result.run_id,
        "event_count": len(events),
        "scenario_count": len(seed["scenarios"]),
        "issue_alert_count": len(alerts),
        "public_insight_count": len(insights),
        "duplicate_group_count": len(updated_groups),
        "scenario_results": scenario_results,
        "draft_contract": draft_results,
        "pii": pii_result,
        "http_verification": http_result,
        "fe_check_endpoints": [
            "GET /complaint-intelligence/dashboard",
            "GET /complaint-intelligence/duplicate-groups",
            "GET /complaint-intelligence/duplicate-groups?issue_alert_id={alert_id}",
            "POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply",
        ],
    }
    report["passed"] = (
        all(item["passed"] for item in scenario_results)
        and draft_results["passed"]
        and pii_result["passed"]
    )

    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(report_path, report)
    return report


def build_duplicate_merge_seed(*, as_of: datetime = DEFAULT_AS_OF) -> dict[str, Any]:
    return {
        "mode": "replay",
        "source_name": SOURCE_NAME,
        "description": "PII-safe 중복 민원 병합 UI 검증용 replay seed",
        "as_of": as_of.isoformat(),
        "scenarios": [
            _hotspot_apartment_noise_duplicate(as_of),
            _general_duplicate_queue(as_of),
            _different_request_risk(as_of),
            _confirmed_draft_demo(as_of),
        ],
    }


def _hotspot_apartment_noise_duplicate(as_of: datetime) -> dict[str, Any]:
    events = [
        _event(
            event_id=f"dm-hotspot-noise-{index:02d}",
            received_at=as_of - timedelta(minutes=index * 18),
            title="한빛아파트 북문 공사 소음 반복 신고",
            observation="한빛아파트 북문 공사장에서 굴착 장비 소음과 진동이 반복되고 있습니다.",
            result="거주자 휴식과 통학 동선에 불편이 커지고 있습니다.",
            request="현장 점검과 공사 소음 저감 조치를 요청합니다.",
            context="최근 세 시간 안에 같은 공사장 관련 신고가 집중 접수되었습니다.",
            region="새빛동",
            department="환경관리과",
            civil_category="생활불편",
            entity_texts=["한빛아파트 북문 공사장", "공사 소음", "진동"],
            request_segments=["현장 점검과 소음 저감 조치 요청"],
            latitude=37.5665 + index * 0.00008,
            longitude=126.9780 + index * 0.00007,
        )
        for index in range(6)
    ]
    return {
        "id": "hotspot_apartment_noise_duplicate",
        "label": "핫스팟 안 반복 공사 소음 중복 후보",
        "expected_alert": True,
        "expected_duplicate": True,
        "expected_linked_issue_alert": True,
        "expected_status": "candidate",
        "events": events,
    }


def _general_duplicate_queue(as_of: datetime) -> dict[str, Any]:
    events = [
        _event(
            event_id=f"dm-general-lamp-{index:02d}",
            received_at=as_of - timedelta(hours=6, minutes=index * 20),
            title="늘봄공원 북문 가로등 고장 신고",
            observation="늘봄공원 북문 산책로 가로등이 꺼져 있습니다.",
            result="퇴근 시간 보행자가 어두운 길을 지나야 합니다.",
            request="가로등 점검과 보수를 요청합니다.",
            context="같은 지점의 시설 고장 신고가 반복 접수되었습니다.",
            region="달빛동",
            department="도로조명과",
            civil_category="시설보수",
            entity_texts=["늘봄공원 북문", "가로등"],
            request_segments=["가로등 보수 요청"],
            latitude=37.5563 + index * 0.00006,
            longitude=126.9237 + index * 0.00008,
        )
        for index in range(2)
    ]
    return {
        "id": "general_duplicate_queue",
        "label": "핫스팟과 무관한 일반 중복 후보",
        "expected_alert": False,
        "expected_duplicate": True,
        "expected_linked_issue_alert": False,
        "expected_status": "candidate",
        "events": events,
    }


def _different_request_risk(as_of: datetime) -> dict[str, Any]:
    return {
        "id": "different_request_risk",
        "label": "같은 사건이지만 요청 유형이 섞인 주의 후보",
        "expected_alert": False,
        "expected_duplicate": True,
        "expected_linked_issue_alert": False,
        "expected_status": "candidate",
        "expected_risk_flags": ["REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"],
        "events": [
            _event(
                event_id="dm-risk-parking-01",
                received_at=as_of - timedelta(hours=5, minutes=5),
                title="새빛초 후문 불법 주정차 단속 요청",
                observation="새빛초 후문 횡단보도 주변에 불법 주정차 차량이 반복 정차합니다.",
                result="등하교 시간 보행 안전이 우려됩니다.",
                request="현장 단속과 계도 조치를 요청합니다.",
                context="같은 시간대에 같은 지점에서 반복 신고가 접수되었습니다.",
                region="새빛동",
                department="교통지도과",
                civil_category="교통",
                entity_texts=["새빛초 후문", "불법 주정차"],
                request_segments=["불법 주정차 단속 요청"],
                risk_level="high",
                urgency="high",
                latitude=37.5658,
                longitude=126.9769,
            ),
            _event(
                event_id="dm-risk-parking-02",
                received_at=as_of - timedelta(hours=5, minutes=24),
                title="새빛초 후문 불법 주정차 관련 보상 상담 요청",
                observation="새빛초 후문 불법 주정차 차량 때문에 통행 중 차량 흠집 피해가 있었다고 주장합니다.",
                result="개별 보상과 책임 관계 확인이 필요한 상황입니다.",
                request="피해 보상 상담과 처리 기준 안내를 요청합니다.",
                context="같은 지점의 불법 주정차 상황과 연결될 수 있으나 요구사항은 다릅니다.",
                region="새빛동",
                department="교통지도과",
                civil_category="교통",
                entity_texts=["새빛초 후문", "불법 주정차"],
                request_segments=["피해 보상 상담 요청"],
                risk_level="medium",
                urgency="normal",
                latitude=37.5659,
                longitude=126.9770,
            ),
        ],
    }


def _confirmed_draft_demo(as_of: datetime) -> dict[str, Any]:
    events = [
        _event(
            event_id=f"dm-confirmed-library-{index:02d}",
            received_at=as_of - timedelta(hours=7, minutes=index * 12),
            title="온누리도서관 열람실 냉난방기 고장 신고",
            observation="온누리도서관 열람실 냉난방기가 작동하지 않습니다.",
            result="이용자들이 장시간 머무르기 어렵다는 불편을 호소하고 있습니다.",
            request="냉난방기 점검과 수리를 요청합니다.",
            context="같은 시설의 같은 장비 고장 신고가 반복 접수되었습니다.",
            region="온누리동",
            department="시설관리과",
            civil_category="시설보수",
            entity_texts=["온누리도서관 열람실", "냉난방기"],
            request_segments=["냉난방기 점검과 수리 요청"],
            latitude=37.5729 + index * 0.00005,
            longitude=126.9794 + index * 0.00005,
        )
        for index in range(2)
    ]
    return {
        "id": "confirmed_draft_demo",
        "label": "담당자 확정 후 draft payload 생성 확인용 후보",
        "expected_alert": False,
        "expected_duplicate": True,
        "expected_linked_issue_alert": False,
        "expected_status_after_demo": "confirmed",
        "events": events,
    }


def _event(
    *,
    event_id: str,
    received_at: datetime,
    title: str,
    observation: str,
    result: str,
    request: str,
    context: str,
    region: str,
    department: str,
    civil_category: str,
    entity_texts: list[str],
    request_segments: list[str],
    risk_level: str = "normal",
    urgency: str = "normal",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    body = " ".join([title, observation, result, request, context])
    payload = {
        "id": event_id,
        "received_at": received_at.isoformat(),
        "title": title,
        "body": body,
        "masked_text": body,
        "region": region,
        "final_department": department,
        "predicted_department": department,
        "status": "open",
        "civil_category": civil_category,
        "final_category": civil_category,
        "entity_texts": entity_texts,
        "responsible_unit": [department],
        "request_segments": request_segments,
        "urgency": urgency,
        "risk_level": risk_level,
        "latitude": latitude,
        "longitude": longitude,
        "structured_elements": {
            "observation": {"text": observation},
            "result": {"text": result},
            "request": {"text": request},
            "context": {"text": context},
        },
    }
    return ComplaintIntelligenceEvent.model_validate(payload).model_dump(mode="json")


def _seed_events(seed: dict[str, Any]) -> list[ComplaintIntelligenceEvent]:
    events: list[ComplaintIntelligenceEvent] = []
    for scenario in seed["scenarios"]:
        for event in scenario["events"]:
            events.append(ComplaintIntelligenceEvent.model_validate(event))
    return events


def _validate_duplicate_scenarios(seed: dict[str, Any], groups: list[Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for scenario in seed["scenarios"]:
        event_ids = {event["id"] for event in scenario["events"]}
        matched = [
            group
            for group in groups
            if event_ids & set(group.member_complaint_ids)
        ]
        failures: list[dict[str, str]] = []
        if scenario.get("expected_duplicate") and not matched:
            failures.append({"code": "NO_DUPLICATE_GROUP", "hint": "중복 후보 그룹이 생성되지 않았습니다."})
        if scenario.get("expected_linked_issue_alert") and not any(group.linked_issue_alert_ids for group in matched):
            failures.append({"code": "NO_LINKED_ISSUE_ALERT", "hint": "IssueAlert와 duplicate group 연결이 비어 있습니다."})
        if scenario.get("expected_linked_issue_alert") is False and any(group.linked_issue_alert_ids for group in matched):
            failures.append({"code": "UNEXPECTED_LINKED_ISSUE_ALERT", "hint": "일반 큐 시나리오가 핫스팟과 연결되었습니다."})

        expected_flags = set(scenario.get("expected_risk_flags") or [])
        matched_flags = {flag.code for group in matched for flag in group.risk_flags}
        missing_flags = sorted(expected_flags - matched_flags)
        if missing_flags:
            failures.append({"code": "MISSING_RISK_FLAG", "hint": ",".join(missing_flags)})

        expected_status = scenario.get("expected_status_after_demo") or scenario.get("expected_status")
        if expected_status and matched and not any(group.status == expected_status for group in matched):
            failures.append({"code": "STATUS_MISMATCH", "hint": f"expected={expected_status}"})

        results.append(
            {
                "scenario": scenario["id"],
                "label": scenario["label"],
                "passed": not failures,
                "event_count": len(event_ids),
                "matched_group_ids": [group.merge_id for group in matched],
                "linked_issue_alert_ids": sorted({alert_id for group in matched for alert_id in group.linked_issue_alert_ids}),
                "risk_flags": sorted(matched_flags),
                "statuses": sorted({group.status for group in matched}),
                "failures": failures,
            }
        )
    return results


def _validate_draft_contract(service: Any, groups: list[Any]) -> dict[str, Any]:
    candidate = _first_group(groups, "dm-hotspot-noise")
    confirmed_source = _first_group(groups, "dm-confirmed-library")
    failures: list[dict[str, str]] = []
    candidate_blocked = False
    candidate_error_code = None
    confirmed_payload_created = False
    confirmed_group_id = None

    if candidate is None:
        failures.append({"code": "NO_CANDIDATE_FOR_DRAFT_BLOCK", "hint": "candidate draft 차단 검증용 그룹이 없습니다."})
    else:
        try:
            service.build_duplicate_draft_reply_payload(candidate.merge_id)
        except DuplicateMergeConflict as exc:
            candidate_blocked = exc.code == "DUPLICATE_GROUP_NOT_CONFIRMED"
            candidate_error_code = exc.code
        if not candidate_blocked:
            failures.append({"code": "CANDIDATE_DRAFT_NOT_BLOCKED", "hint": "candidate draft-reply가 차단되지 않았습니다."})

    if confirmed_source is None:
        failures.append({"code": "NO_GROUP_FOR_CONFIRMED_DRAFT", "hint": "confirmed draft 검증용 그룹이 없습니다."})
    else:
        confirmed = service.confirm_duplicate_group(confirmed_source.merge_id)
        confirmed_group_id = confirmed.merge_id
        payload = service.build_duplicate_draft_reply_payload(confirmed.merge_id)
        confirmed_payload_created = bool(payload.representative_complaint_id and payload.member_complaint_ids)
        if not confirmed_payload_created:
            failures.append({"code": "CONFIRMED_DRAFT_NOT_CREATED", "hint": "confirmed draft payload가 생성되지 않았습니다."})

    return {
        "passed": not failures,
        "candidate_draft_blocked": candidate_blocked,
        "candidate_error_code": candidate_error_code,
        "confirmed_draft_payload_created": confirmed_payload_created,
        "confirmed_group_id": confirmed_group_id,
        "failures": failures,
    }


def _validate_pii(seed: dict[str, Any], alerts: list[Any], insights: list[Any], groups: list[Any], draft: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "seed": seed,
        "alerts": [alert.model_dump(mode="json") for alert in alerts],
        "insights": [insight.model_dump(mode="json") for insight in insights],
        "duplicate_groups": [group.model_dump(mode="json") for group in groups],
        "draft_contract": draft,
    }
    has_pii = contains_unmasked_pii(payload)
    return {"passed": not has_pii, "raw_pii_detected": has_pii}


def _first_group(groups: list[Any], event_id_prefix: str) -> Any | None:
    for group in groups:
        if any(case_id.startswith(event_id_prefix) for case_id in group.member_complaint_ids):
            return group
    return None


def _verify_http(base_url: str | None) -> dict[str, Any] | None:
    if not base_url:
        return None
    base = base_url.rstrip("/")
    result: dict[str, Any] = {}
    for path in (
        "/complaint-intelligence/dashboard",
        "/complaint-intelligence/duplicate-groups",
    ):
        try:
            with urllib.request.urlopen(base + path, timeout=10) as response:
                result[path] = {"status": response.status, "ok": 200 <= response.status < 300}
        except Exception as exc:  # noqa: BLE001 - 데모 보조 검증은 오류 유형만 보고한다.
            result[path] = {"status": None, "ok": False, "error_type": type(exc).__name__}
    return result


if __name__ == "__main__":
    raise SystemExit(main())

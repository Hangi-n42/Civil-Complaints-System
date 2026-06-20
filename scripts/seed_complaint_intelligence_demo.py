"""Complaint Intelligence demo seed를 실제 분석 파이프라인으로 실행한다."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, PublicAgencyInsight
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.complaint_intelligence.sqlite_repository import SQLiteComplaintIntelligenceRepository


DEFAULT_SEED = Path("data/demo/complaint_intelligence_demo_events.json")
DEFAULT_DB_PATH = Path("data/complaint_intelligence/complaint_intelligence.db")
DEFAULT_REPORT = Path("reports/complaint_intelligence_demo_seed_run_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Complaint Intelligence demo read-model.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--demo-thresholds", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    seed = load_seed(Path(args.seed), scenario_id=args.scenario)
    events = seed_events(seed)
    report: dict[str, Any] = {
        "seed": str(args.seed),
        "db_path": str(args.db_path),
        "mode": seed.get("mode", "replay"),
        "source_name": seed.get("source_name", "complaint_intelligence_demo"),
        "as_of": seed.get("as_of"),
        "scenario_count": len(seed.get("scenarios", [])),
        "event_count": len(events),
        "demo_thresholds": bool(args.demo_thresholds),
        "fe_check_endpoints": [
            "GET /complaint-intelligence/dashboard",
            "GET /complaint-intelligence/issue-alerts",
            "GET /complaint-intelligence/public-insights",
        ],
    }

    if args.validate_only:
        report["validate_only"] = True
        report["passed"] = len(events) > 0 and not contains_unmasked_pii(seed)
        write_report(Path(args.output), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1

    service = build_service(Path(args.db_path), demo_thresholds=args.demo_thresholds)
    result = service.run_analysis(
        events,
        mode=str(seed.get("mode") or "replay"),
        source_name=str(seed.get("source_name") or "complaint_intelligence_demo"),
        as_of=datetime.fromisoformat(str(seed.get("as_of"))),
        metadata={"trigger": "demo_seed", "seed_file": str(args.seed)},
    )

    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()
    dashboard_state = service.get_dashboard_state()
    scenario_results = validate_scenarios(seed, alerts, insights, service)
    dashboard_result = validate_dashboard(dashboard_state, alerts, insights)
    pii_result = validate_pii(seed, alerts, insights, service)
    http_result = verify_http(args.base_url) if args.base_url else None

    report.update(
        {
            "run_id": result.run_id,
            "latest_event_at": result.latest_event_at.isoformat() if result.latest_event_at else None,
            "dashboard": dashboard_result,
            "issue_alert_count": len(alerts),
            "public_insight_count": len(insights),
            "evidence_pack_count": sum(1 for insight in insights if service.get_public_insight_evidence_pack(insight.insight_id)),
            "scenario_results": scenario_results,
            "pii": pii_result,
            "http_verification": http_result,
        }
    )
    report["passed"] = (
        dashboard_result["passed"]
        and pii_result["passed"]
        and all(item["passed"] for item in scenario_results)
    )
    write_report(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def load_seed(path: Path, *, scenario_id: str | None = None) -> dict[str, Any]:
    seed = json.loads(path.read_text(encoding="utf-8"))
    if scenario_id:
        seed = dict(seed)
        seed["scenarios"] = [
            scenario for scenario in seed.get("scenarios", [])
            if scenario.get("id") == scenario_id
        ]
    return seed


def seed_events(seed: dict[str, Any]) -> list[ComplaintIntelligenceEvent]:
    events: list[ComplaintIntelligenceEvent] = []
    for scenario in seed.get("scenarios", []):
        for event in scenario.get("events", []):
            events.append(ComplaintIntelligenceEvent.model_validate(event))
    return events


def build_service(db_path: Path, *, demo_thresholds: bool) -> ComplaintIntelligenceService:
    config = get_complaint_intelligence_config()
    if demo_thresholds:
        config = replace(
            config,
            min_recent_count=3,
            min_surge_ratio=1.5,
            public_insight_min_candidate_complaint_count=3,
            min_affected_count=3,
        )
    config = replace(config, repository="sqlite", db_path=str(db_path))
    repository = SQLiteComplaintIntelligenceRepository(db_path)
    return ComplaintIntelligenceService(repository=repository, config=config)


def validate_dashboard(state: Any, alerts: list[Any], insights: list[PublicAgencyInsight]) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    if state.event_count <= 0:
        failures.append({"code": "NO_EVENTS", "hint": "seed event 저장 여부를 확인하세요."})
    if state.active_alert_count < 1 or len(alerts) < 1:
        failures.append({"code": "NO_ALERT_CREATED", "hint": "recent_count/min_recent_count 또는 min_surge_ratio 조건을 확인하세요."})
    if len(insights) < 1:
        failures.append({"code": "NO_PUBLIC_INSIGHT_CREATED", "hint": "public insight candidate count와 quality gate 결과를 확인하세요."})
    return {
        "passed": not failures,
        "summary": {
            "as_of": state.as_of.isoformat() if state.as_of else None,
            "latest_event_at": state.latest_event_at.isoformat() if state.latest_event_at else None,
            "event_count": state.event_count,
            "active_alert_count": state.active_alert_count,
            "high_priority_insight_count": state.high_priority_insight_count,
        },
        "failures": failures,
    }


def validate_scenarios(
    seed: dict[str, Any],
    alerts: list[Any],
    insights: list[PublicAgencyInsight],
    service: ComplaintIntelligenceService,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for scenario in seed.get("scenarios", []):
        event_ids = {event["id"] for event in scenario.get("events", [])}
        matched_alerts = [alert for alert in alerts if event_ids & set(alert.related_ids)]
        matched_insights = [insight for insight in insights if insight_matches(insight, event_ids, matched_alerts)]
        failures: list[dict[str, str]] = []
        if scenario.get("expected_alert") and not matched_alerts:
            failures.append({"code": "NO_ALERT_CREATED", "hint": "recent_count/min_recent_count 또는 min_surge_ratio 조건을 확인하세요."})
        expected_types = set(scenario.get("expected_insight_types") or [])
        if expected_types and not any(str(insight.type) in expected_types for insight in matched_insights):
            failures.append({"code": "NO_EXPECTED_INSIGHT_TYPE", "hint": "candidate keyword/type mapping을 확인하세요."})
        for insight in matched_insights:
            if not insight.recommended_actions:
                failures.append({"code": "EMPTY_ACTIONS", "hint": f"{insight.insight_id} recommended_actions가 비어 있습니다."})
            evidence_ids = {evidence.complaint_id for evidence in insight.evidence}
            pack = service.get_public_insight_evidence_pack(insight.insight_id)
            if pack is None:
                failures.append({"code": "NO_EVIDENCE_PACK", "hint": f"{insight.insight_id} EvidencePack 저장 여부를 확인하세요."})
            elif contains_unmasked_pii(pack.model_dump(mode="json")):
                failures.append({"code": "PII_IN_EVIDENCE_PACK", "hint": f"{insight.insight_id} EvidencePack 마스킹을 확인하세요."})
            for action in insight.recommended_actions:
                if not action.supporting_evidence_ids:
                    failures.append({"code": "ACTION_WITHOUT_EVIDENCE", "hint": f"{insight.insight_id} action evidence가 비어 있습니다."})
                elif not set(action.supporting_evidence_ids) <= evidence_ids:
                    failures.append({"code": "ACTION_EVIDENCE_NOT_FOUND", "hint": f"{insight.insight_id} action evidence id가 insight evidence에 없습니다."})
        results.append(
            {
                "scenario": scenario.get("id"),
                "label": scenario.get("label"),
                "passed": not failures,
                "event_count": len(event_ids),
                "matched_alert_count": len(matched_alerts),
                "matched_insight_count": len(matched_insights),
                "matched_insight_types": sorted({str(insight.type) for insight in matched_insights}),
                "failures": failures,
            }
        )
    return results


def insight_matches(insight: PublicAgencyInsight, event_ids: set[str], matched_alerts: list[Any]) -> bool:
    if event_ids & set(insight.representative_complaint_ids):
        return True
    if event_ids & {evidence.complaint_id for evidence in insight.evidence}:
        return True
    alert_ids = {alert.id for alert in matched_alerts}
    return bool(alert_ids & set(insight.linked_alert_ids))


def validate_pii(
    seed: dict[str, Any],
    alerts: list[Any],
    insights: list[PublicAgencyInsight],
    service: ComplaintIntelligenceService,
) -> dict[str, Any]:
    payload = {
        "seed": seed,
        "alerts": [alert.model_dump(mode="json") for alert in alerts],
        "insights": [insight.model_dump(mode="json") for insight in insights],
        "packs": [
            pack.model_dump(mode="json")
            for insight in insights
            if (pack := service.get_public_insight_evidence_pack(insight.insight_id)) is not None
        ],
    }
    has_pii = contains_unmasked_pii(payload)
    return {"passed": not has_pii, "raw_pii_detected": has_pii}


def contains_unmasked_pii(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return mask_pii(text).text != text


def verify_http(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    result: dict[str, Any] = {}
    for path in (
        "/complaint-intelligence/dashboard",
        "/complaint-intelligence/issue-alerts",
        "/complaint-intelligence/public-insights",
    ):
        try:
            with urllib.request.urlopen(base + path, timeout=10) as response:
                result[path] = {"status": response.status, "ok": 200 <= response.status < 300}
        except Exception as exc:  # noqa: BLE001 - 수동 검증 보조 경로
            result[path] = {"status": None, "ok": False, "error_type": type(exc).__name__}
    return result


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

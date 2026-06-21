"""프론트 개발 서버 시작 전에 real_replay 관제 read-model을 준비한다."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_complaint_intelligence_demo_seed import build_demo_seed
from scripts.seed_complaint_intelligence_demo import (
    contains_unmasked_pii,
    load_seed,
    seed_events,
    validate_dashboard,
    validate_pii,
    validate_scenarios,
    write_report,
)
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.complaint_intelligence.sqlite_repository import SQLiteComplaintIntelligenceRepository
from app.complaint_intelligence.config import get_complaint_intelligence_config
from dataclasses import replace


DEFAULT_INPUT = Path(r"C:\Projects\AI-Civil-Affairs-Systems\data\processed")
DEFAULT_SEED = PROJECT_ROOT / "data" / "complaint_intelligence" / "complaint_intelligence_real_replay_events.json"
DEFAULT_DB = PROJECT_ROOT / "data" / "complaint_intelligence" / "complaint_intelligence_real_replay.db"
DEFAULT_BUILD_REPORT = PROJECT_ROOT / "reports" / "complaint_intelligence_real_replay_seed_build_report.json"
DEFAULT_RUN_REPORT = PROJECT_ROOT / "reports" / "complaint_intelligence_real_replay_seed_run_report.json"
DEFAULT_DESCRIPTION = "실제 processed 민원 데이터에서 PII-safe 발췌 후 관제 검증용 replay timeline으로 재배치한 seed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Complaint Intelligence real replay read-model.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--seed", default=str(DEFAULT_SEED))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--build-report", default=str(DEFAULT_BUILD_REPORT))
    parser.add_argument("--run-report", default=str(DEFAULT_RUN_REPORT))
    parser.add_argument("--source-name", default="complaint_intelligence_real_replay")
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    parser.add_argument("--as-of", default="2026-06-20T09:00:00+09:00")
    parser.add_argument("--min-events-per-scenario", type=int, default=20)
    parser.add_argument("--max-events-per-scenario", type=int, default=20)
    parser.add_argument("--allow-synthetic-fill", default="false")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    seed_path = Path(args.seed)
    db_path = Path(args.db_path)
    build_report_path = Path(args.build_report)
    run_report_path = Path(args.run_report)
    allow_synthetic_fill = str(args.allow_synthetic_fill).lower() == "true"

    if not args.skip_build:
        seed, build_report = build_demo_seed(
            input_paths=[input_path],
            as_of=datetime.fromisoformat(args.as_of),
            min_events_per_scenario=args.min_events_per_scenario,
            max_events_per_scenario=args.max_events_per_scenario,
            allow_synthetic_fill=allow_synthetic_fill,
            source_name=args.source_name,
            description=args.description,
        )
        seed, should_write_seed, fallback = choose_seed_payload(seed, seed_path)
        if fallback:
            build_report["fallback_to_existing_seed"] = fallback
            print(
                "[predev] 입력 데이터에서 real_replay 이벤트를 만들지 못해 기존 seed를 유지합니다.",
                file=sys.stderr,
            )
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        build_report_path.parent.mkdir(parents=True, exist_ok=True)
        if should_write_seed:
            seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        build_report_path.write_text(json.dumps(build_report, ensure_ascii=False, indent=2), encoding="utf-8")

    seed_payload = load_seed(seed_path)
    events = seed_events(seed_payload)
    if not events:
        raise RuntimeError(
            "real_replay seed 이벤트가 0건입니다. 기존 DB를 보존하기 위해 재생성을 중단합니다."
        )
    if contains_unmasked_pii(seed_payload):
        raise RuntimeError("real_replay seed에 마스킹되지 않은 개인정보 패턴이 감지되었습니다.")

    reset_sqlite_db(db_path)
    service = build_service(db_path)
    as_of = datetime.fromisoformat(str(seed_payload.get("as_of")))
    issue_result = service.run_analysis(
        events,
        mode=str(seed_payload.get("mode") or "replay"),
        source_name=args.source_name,
        as_of=as_of,
        metadata={"trigger": "frontend_predev_real_replay", "seed_file": str(seed_path)},
    )
    duplicate_groups = service.run_duplicate_analysis(
        events,
        mode=str(seed_payload.get("mode") or "replay"),
        source_name=args.source_name,
        as_of=issue_result.latest_event_at or as_of,
    )

    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()
    state = service.get_dashboard_state()
    dashboard_result = validate_dashboard(state, alerts, insights)
    scenario_results = validate_scenarios(seed_payload, alerts, insights, service)
    pii_result = validate_pii(seed_payload, alerts, insights, service)
    run_report: dict[str, Any] = {
        "seed": str(seed_path),
        "db_path": str(db_path),
        "source_name": args.source_name,
        "mode": seed_payload.get("mode", "replay"),
        "as_of": seed_payload.get("as_of"),
        "scenario_count": len(seed_payload.get("scenarios", [])),
        "event_count": len(events),
        "issue_run_id": issue_result.run_id,
        "duplicate_group_count": len(duplicate_groups),
        "dashboard": dashboard_result,
        "issue_alert_count": len(alerts),
        "public_insight_count": len(insights),
        "scenario_results": scenario_results,
        "pii": pii_result,
    }
    run_report["passed"] = (
        dashboard_result["passed"]
        and pii_result["passed"]
        and all(item["passed"] for item in scenario_results)
    )
    write_report(run_report_path, run_report)
    print(json.dumps(summarize(run_report), ensure_ascii=False, indent=2))
    return 0 if run_report["passed"] else 1


def build_service(db_path: Path) -> ComplaintIntelligenceService:
    """real_replay DB만 바라보는 SQLite 서비스를 만든다."""

    config = replace(get_complaint_intelligence_config(), repository="sqlite", db_path=str(db_path))
    return ComplaintIntelligenceService(repository=SQLiteComplaintIntelligenceRepository(db_path), config=config)


def reset_sqlite_db(db_path: Path) -> None:
    """워크스페이스 내부 real_replay SQLite 파일만 초기화한다."""

    resolved = db_path.resolve()
    root = PROJECT_ROOT.resolve()
    if root != resolved and root not in resolved.parents:
        raise RuntimeError(f"워크스페이스 밖 DB는 초기화하지 않습니다: {resolved}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-journal", "-wal", "-shm"):
        target = Path(str(db_path) + suffix)
        if target.exists():
            target.unlink()


def choose_seed_payload(generated_seed: dict[str, Any], seed_path: Path) -> tuple[dict[str, Any], bool, dict[str, Any] | None]:
    """새 seed가 비어 있으면 기존 정상 seed를 보존한다."""

    generated_count = count_seed_events(generated_seed)
    if generated_count > 0:
        return generated_seed, True, None

    existing_seed = load_existing_seed(seed_path)
    existing_count = count_seed_events(existing_seed) if existing_seed else 0
    if existing_seed and existing_count > 0:
        return (
            existing_seed,
            False,
            {
                "reason": "generated_seed_empty",
                "generated_event_count": generated_count,
                "existing_event_count": existing_count,
                "seed_path": str(seed_path),
            },
        )

    raise RuntimeError(
        "입력 데이터에서 real_replay 이벤트를 만들지 못했고 기존 seed도 비어 있습니다. "
        "--input 또는 COMPLAINT_INTELLIGENCE_REAL_REPLAY_INPUT 경로를 확인하세요."
    )


def load_existing_seed(seed_path: Path) -> dict[str, Any] | None:
    if not seed_path.exists():
        return None
    try:
        return json.loads(seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def count_seed_events(seed: dict[str, Any] | None) -> int:
    if not seed:
        return 0
    return sum(
        len(scenario.get("events") or [])
        for scenario in seed.get("scenarios", [])
        if isinstance(scenario, dict)
    )


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    dashboard = report.get("dashboard", {}).get("summary", {})
    return {
        "passed": report.get("passed"),
        "source_name": report.get("source_name"),
        "event_count": report.get("event_count"),
        "active_alert_count": dashboard.get("active_alert_count"),
        "issue_alert_count": report.get("issue_alert_count"),
        "public_insight_count": report.get("public_insight_count"),
        "duplicate_group_count": report.get("duplicate_group_count"),
    }


if __name__ == "__main__":
    raise SystemExit(main())

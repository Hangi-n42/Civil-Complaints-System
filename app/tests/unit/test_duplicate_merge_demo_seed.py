from __future__ import annotations

import json

from scripts.seed_duplicate_merge_demo import run_duplicate_merge_demo


def test_duplicate_merge_demo_seed_builds_hotspot_and_general_queue(tmp_path) -> None:
    report = run_duplicate_merge_demo(
        seed_path=tmp_path / "duplicate_merge_demo_events.json",
        db_path=tmp_path / "duplicate_merge_demo.db",
        report_path=tmp_path / "duplicate_merge_demo_seed_report.json",
    )

    assert report["passed"] is True
    assert report["event_count"] == 12
    assert report["duplicate_group_count"] == 4

    scenarios = {item["scenario"]: item for item in report["scenario_results"]}
    hotspot = scenarios["hotspot_apartment_noise_duplicate"]
    general = scenarios["general_duplicate_queue"]
    risk = scenarios["different_request_risk"]
    confirmed = scenarios["confirmed_draft_demo"]

    assert hotspot["passed"] is True
    assert hotspot["linked_issue_alert_ids"]
    assert hotspot["statuses"] == ["candidate"]

    assert general["passed"] is True
    assert general["linked_issue_alert_ids"] == []
    assert general["statuses"] == ["candidate"]

    assert {"REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"} <= set(risk["risk_flags"])
    assert confirmed["statuses"] == ["confirmed"]

    assert report["draft_contract"]["candidate_draft_blocked"] is True
    assert report["draft_contract"]["candidate_error_code"] == "DUPLICATE_GROUP_NOT_CONFIRMED"
    assert report["draft_contract"]["confirmed_draft_payload_created"] is True
    assert report["pii"]["raw_pii_detected"] is False


def test_duplicate_merge_demo_seed_file_is_pii_safe(tmp_path) -> None:
    seed_path = tmp_path / "duplicate_merge_demo_events.json"
    run_duplicate_merge_demo(
        seed_path=seed_path,
        db_path=tmp_path / "duplicate_merge_demo.db",
        report_path=tmp_path / "duplicate_merge_demo_seed_report.json",
    )

    seed_text = seed_path.read_text(encoding="utf-8")
    assert "010-" not in seed_text
    assert "@example.com" not in seed_text
    assert json.loads(seed_text)["source_name"] == "duplicate_merge_demo"

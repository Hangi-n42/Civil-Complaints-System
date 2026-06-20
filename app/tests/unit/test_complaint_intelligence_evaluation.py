from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from scripts.evaluate_complaint_intelligence_scenarios import (
    build_summary,
    compare_reports,
    contains_unmasked_pii,
    evaluate_scenario_file,
    has_forbidden_ai_ops_terms,
    load_scenarios,
    write_default_scenarios,
)


SCENARIO_FILE = Path("data/evaluation/complaint_intelligence_eval_scenarios.json")


def test_evaluation_scenario_json_loads() -> None:
    payload = _scenario_payload()

    assert payload["scenarios"]
    assert payload["mode"] == "replay"
    assert payload["source_name"] == "complaint_intelligence_evaluation"
    assert all("scenario_id" in scenario for scenario in payload["scenarios"])


def test_evaluation_scenario_set_has_minimum_positive_and_negative_cases() -> None:
    scenarios = _scenario_payload()["scenarios"]

    assert len(scenarios) >= 10
    assert any(scenario["expected_alert"] is True for scenario in scenarios)
    assert any(scenario["expected_alert"] is False for scenario in scenarios)


def test_evaluation_events_validate_as_complaint_intelligence_events() -> None:
    for scenario in _scenario_payload()["scenarios"]:
        for event in scenario["events"]:
            validated = ComplaintIntelligenceEvent.model_validate(event)
            assert validated.id
            assert validated.masked_text


def test_fake_provider_evaluation_builds_deterministic_summary() -> None:
    first = _evaluation_report()["summary"]
    second = evaluate_scenario_file(scenario_file=SCENARIO_FILE, provider="fake")["summary"]

    assert first["issue_detection"] == second["issue_detection"]
    assert first["public_agency_insight"] == second["public_agency_insight"]


def test_issue_alert_expected_hit_rates_are_calculated() -> None:
    issue = _evaluation_report()["summary"]["issue_detection"]

    assert 0.0 <= issue["alert_recall"] <= 1.0
    assert 0.0 <= issue["alert_precision_on_negative"] <= 1.0
    assert "false_positive_count" in issue
    assert "false_negative_count" in issue


def test_expected_insight_type_hit_rate_is_calculated() -> None:
    insight = _evaluation_report()["summary"]["public_agency_insight"]

    assert 0.0 <= insight["expected_type_hit_rate"] <= 1.0
    assert "required_aspect_hit_rate" in insight
    assert "required_action_type_hit_rate" in insight
    assert 0.0 <= insight["allowed_action_type_hit_rate"] <= 1.0
    assert 0.0 <= insight["action_type_rubric_pass_rate"] <= 1.0


def test_action_evidence_coverage_is_calculated() -> None:
    insight = _evaluation_report()["summary"]["public_agency_insight"]

    assert 0.0 <= insight["action_evidence_coverage_rate"] <= 1.0
    assert 0.0 <= insight["evidence_pack_presence_rate"] <= 1.0


def test_pii_leak_checker_detects_raw_pii() -> None:
    assert contains_unmasked_pii({"text": "010-1234-5678로 연락 주세요."}) is True
    assert contains_unmasked_pii({"text": "[PHONE]로 연락 주세요."}) is False


def test_forbidden_ai_ops_term_checker_detects_internal_terms() -> None:
    assert has_forbidden_ai_ops_terms({"summary": "RAG retrieval prompt model answer_quality 개선"}) is True
    assert has_forbidden_ai_ops_terms({"summary": "현장 점검과 시민 안내를 강화합니다."}) is False


def test_negative_false_positive_is_recorded_in_summary() -> None:
    summary = build_summary(
        [
            {
                "passed": False,
                "issue_detection_passed": False,
                "public_agency_insight": {
                    "insight_count": 0,
                    "expected_type_required": False,
                    "expected_type_hit": False,
                    "required_aspect_hit": True,
                    "required_action_type_hit": True,
                    "action_evidence_coverage_rate": 0.0,
                    "evidence_pack_presence_rate": 0.0,
                    "grounding_pass": True,
                    "avg_grounding_score": 0.0,
                    "avg_confidence": 0.0,
                    "avg_actionability_score": 0.0,
                    "fallback": False,
                    "forbidden_ai_ops_terms": False,
                    "pii_leak": False,
                    "human_review_requirement_pass": True,
                },
                "issue_detection": {
                    "expected_alert": False,
                    "alert_count": 1,
                    "severe_alert_count": 1,
                    "expected_topic_hit": False,
                    "avg_alert_confidence": 0.7,
                    "avg_surge_ratio": 2.0,
                    "avg_recent_count": 3.0,
                },
            }
        ]
    )

    assert summary["issue_detection"]["false_positive_count"] == 1
    assert summary["issue_detection"]["alert_precision_on_negative"] == 0.0


def test_comparison_report_calculates_metric_deltas() -> None:
    baseline = {
        "scenario_file": "baseline.json",
        "provider": "fake",
        "summary": {
            "issue_detection": {
                "alert_recall": 0.5,
                "expected_topic_hit_rate": 0.4,
                "false_positive_count": 0,
                "false_negative_count": 4,
            },
            "public_agency_insight": {
                "expected_type_hit_rate": 0.9,
                "avg_actionability_score": 0.8,
                "pii_leak_rate": 0.0,
                "forbidden_ai_ops_term_rate": 0.0,
            },
        },
    }
    after = {
        "scenario_file": "after.json",
        "provider": "fake",
        "summary": {
            "issue_detection": {
                "alert_recall": 0.7,
                "expected_topic_hit_rate": 0.8,
                "false_positive_count": 0,
                "false_negative_count": 2,
            },
            "public_agency_insight": {
                "expected_type_hit_rate": 0.95,
                "avg_actionability_score": 0.85,
                "pii_leak_rate": 0.0,
                "forbidden_ai_ops_term_rate": 0.0,
            },
        },
    }

    comparison = compare_reports(baseline, after)

    assert comparison["deltas"]["alert_recall_delta"] == 0.2
    assert comparison["deltas"]["topic_hit_rate_delta"] == 0.4
    assert comparison["deltas"]["false_positive_delta"] == 0
    assert comparison["deltas"]["false_negative_delta"] == -2


def test_llm_evaluation_summary_contains_action_type_and_speed_metrics() -> None:
    report = evaluate_scenario_file(scenario_file=SCENARIO_FILE, provider="fake")
    llm_eval = report["llm_evaluation"]

    assert "invalid_action_type_count" in llm_eval
    assert "repaired_action_type_count" in llm_eval
    assert "removed_action_due_to_action_type_count" in llm_eval
    assert "human_review_postprocess_count" in llm_eval
    assert "speed_metrics" in llm_eval
    assert "avg_llm_duration_ms" in llm_eval["speed_metrics"]


@lru_cache(maxsize=1)
def _scenario_payload():
    if not SCENARIO_FILE.exists():
        write_default_scenarios(SCENARIO_FILE)
    return load_scenarios(SCENARIO_FILE)


@lru_cache(maxsize=1)
def _evaluation_report():
    if not SCENARIO_FILE.exists():
        write_default_scenarios(SCENARIO_FILE)
    return evaluate_scenario_file(scenario_file=SCENARIO_FILE, provider="fake")

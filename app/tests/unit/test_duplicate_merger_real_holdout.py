from __future__ import annotations

from app.complaint_intelligence.duplicate_merger.scoring import classify_location_state
from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from scripts.evaluate_duplicate_merge_real_holdout import (
    REQUIRED_PAIR_COUNTS,
    build_real_holdout_dataset,
    evaluate_pairs,
)


def test_real_holdout_dataset_schema_and_distribution() -> None:
    events, pairs = build_real_holdout_dataset()

    assert len(events) == 300
    assert len({event["id"] for event in events}) == 300
    assert len(pairs) == 200

    counts = {category: 0 for category in REQUIRED_PAIR_COUNTS}
    event_ids = {event["id"] for event in events}
    for pair in pairs:
        counts[pair["category"]] += 1
        assert pair["left_event_id"] in event_ids
        assert pair["right_event_id"] in event_ids
        assert pair["label_confidence"] in {"high", "medium", "low"}

    assert counts == REQUIRED_PAIR_COUNTS


def test_real_holdout_pair_metrics_have_no_regression() -> None:
    events, pairs = build_real_holdout_dataset()

    evaluation = evaluate_pairs(events, pairs)
    metrics = evaluation["metrics"]

    assert metrics["precision"] >= 0.99
    assert metrics["recall"] >= 0.99
    assert metrics["same_keyword_different_event_false_positive_rate"] == 0.0
    assert metrics["same_event_different_request_risk_flag_hit_rate"] == 1.0
    assert metrics["transitive_overmerge_safe_or_risk_hit_rate"] == 1.0
    assert metrics["blocker_recall"] == 1.0
    assert metrics["pii_leak_rate"] == 0.0
    assert metrics["problem_result_count"] == 0


def test_facility_keyword_does_not_make_different_places_exact() -> None:
    events, _ = build_real_holdout_dataset()
    event_map = {event["id"]: event for event in events}
    left = ComplaintIntelligenceEvent.model_validate(event_map["rh-skde-03-0"])
    right = ComplaintIntelligenceEvent.model_validate(event_map["rh-skde-03-1"])

    assert classify_location_state(left, right) == "conflict"


def test_department_alias_does_not_block_confirm() -> None:
    events, _ = build_real_holdout_dataset()
    event_map = {event["id"]: event for event in events}
    left = ComplaintIntelligenceEvent.model_validate(event_map["rh-dept-00-0"])
    right = ComplaintIntelligenceEvent.model_validate(event_map["rh-dept-00-1"])

    service = DuplicateMergeService()
    groups = service.run_analysis([left, right])

    assert len(groups) == 1
    assert "confirm" in groups[0].allowed_actions
    assert all(flag.code != "DEPARTMENT_MISMATCH" for flag in groups[0].risk_flags)

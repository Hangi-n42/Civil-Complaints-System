from __future__ import annotations

from scripts.Be3_run_week6_model_benchmark import _should_accept_prometheus_revision


def test_revision_gate_rejects_valid_revision_when_q0_is_worse():
    accepted, reasons = _should_accept_prometheus_revision(
        revision_answer="valid answer",
        revision_validation={"is_valid": True},
        old_q0=6.0,
        new_q0=5.5,
        current_quality_signals={
            "unsupported_commitment_count": 0,
            "citation_semantic_support_rate": 0.4,
            "segment_coverage_rate": 1.0,
        },
        candidate_quality_signals={
            "unsupported_commitment_count": 0,
            "citation_semantic_support_rate": 0.4,
            "segment_coverage_rate": 1.0,
        },
        current_low_score_count=2,
        candidate_low_score_count=2,
    )

    assert accepted is False
    assert any(reason.startswith("q0_worse") for reason in reasons)


def test_revision_gate_rejects_quality_regression_even_when_q0_improves():
    accepted, reasons = _should_accept_prometheus_revision(
        revision_answer="valid answer",
        revision_validation={"is_valid": True},
        old_q0=5.0,
        new_q0=5.5,
        current_quality_signals={
            "unsupported_commitment_count": 0,
            "citation_semantic_support_rate": 0.5,
            "segment_coverage_rate": 1.0,
        },
        candidate_quality_signals={
            "unsupported_commitment_count": 1,
            "citation_semantic_support_rate": 0.2,
            "segment_coverage_rate": 0.5,
        },
        current_low_score_count=2,
        candidate_low_score_count=3,
    )

    assert accepted is False
    assert "unsupported_commitment_count_worse:0->1" in reasons
    assert any(reason.startswith("citation_semantic_support_worse") for reason in reasons)
    assert any(reason.startswith("segment_coverage_worse") for reason in reasons)


def test_revision_gate_accepts_non_regressing_improvement():
    accepted, reasons = _should_accept_prometheus_revision(
        revision_answer="valid answer",
        revision_validation={"is_valid": True},
        old_q0=5.0,
        new_q0=5.2,
        current_quality_signals={
            "unsupported_commitment_count": 0,
            "citation_semantic_support_rate": 0.3,
            "segment_coverage_rate": 0.5,
        },
        candidate_quality_signals={
            "unsupported_commitment_count": 0,
            "citation_semantic_support_rate": 0.31,
            "segment_coverage_rate": 1.0,
        },
        current_low_score_count=3,
        candidate_low_score_count=2,
    )

    assert accepted is True
    assert reasons == []

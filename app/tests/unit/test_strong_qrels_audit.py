from __future__ import annotations

import json

from scripts import audit_qrels_with_strong_llm as audit


def test_normalize_judgement_extracts_score_reason_and_flags():
    raw = json.dumps(
        {
            "score": 1,
            "reason": "같은 주제지만 보상 절차가 달라 수정이 필요합니다.",
            "rubric_flags": ["needs_modification", "same_department"],
        },
        ensure_ascii=False,
    )

    score, reason, flags = audit.normalize_judgement(raw)

    assert score == 1
    assert "수정" in reason
    assert flags == ["needs_modification", "same_department"]


def test_decide_applies_strong_score_without_overwriting_failed_audit():
    assert audit.decide(2, 1) == ("rel2_downgrade_candidate", 1)
    assert audit.decide(0, 1) == ("missed_relevant_candidate", 1)
    assert audit.decide(1, 2) == ("needs_human_review", 2)
    assert audit.decide(1, 1) == ("match", 1)
    assert audit.decide(2, None) == ("audit_failed", 2)


def test_write_qrels_preserves_unaudited_pairs(tmp_path):
    qrels = [
        {"query_id": "Q-0001", "case_id": "CASE-1", "old_rel": 2},
        {"query_id": "Q-0001", "case_id": "CASE-2", "old_rel": 0},
    ]
    audit_rows = {
        "Q-0001::CASE-1": {
            "query_id": "Q-0001",
            "case_id": "CASE-1",
            "old_rel": 2,
            "strong_rel": 1,
            "final_rel": 1,
            "decision": "rel2_downgrade_candidate",
            "reason": "수정 필요",
            "rubric_flags": ["needs_modification"],
        }
    }

    out = tmp_path / "qrels.tsv"
    audit.write_qrels(out, qrels, audit_rows)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "query_id\t0\tchunk_id\trelevance"
    assert lines[1] == "Q-0001\t0\tCASE-1\t1"
    assert lines[2] == "Q-0001\t0\tCASE-2\t0"


def test_build_summary_reports_agreement_and_label_shift(tmp_path):
    qrels = [
        {"query_id": "Q-0001", "case_id": "CASE-1", "old_rel": 2},
        {"query_id": "Q-0001", "case_id": "CASE-2", "old_rel": 0},
    ]
    rows = {
        "Q-0001::CASE-1": {
            "query_id": "Q-0001",
            "case_id": "CASE-1",
            "old_rel": 2,
            "strong_rel": 1,
            "final_rel": 1,
            "decision": "rel2_downgrade_candidate",
        },
        "Q-0001::CASE-2": {
            "query_id": "Q-0001",
            "case_id": "CASE-2",
            "old_rel": 0,
            "strong_rel": 0,
            "final_rel": 0,
            "decision": "match",
        },
    }

    summary = audit.build_summary(qrels, rows, qrels_path=tmp_path / "qrels.tsv")

    assert summary["audited_pairs"] == 2
    assert summary["old_rel_distribution"] == {"0": 1, "1": 0, "2": 1}
    assert summary["final_rel_distribution"] == {"0": 1, "1": 1, "2": 0}
    assert summary["rel2_downgrade_candidates"] == 1
    assert summary["agreement"]["exact"] == 0.5

"""responsible_unit 평가 스크립트 순수 로직 테스트."""

import pytest

from scripts.eval_responsible_unit import (
    EvalCase,
    evaluate_predictions,
    load_eval_cases,
)


def test_evaluate_predictions_recall_mrr_and_none_abstention():
    cases = [
        EvalCase(query="공원 안전", gold=["공원여가정책과"], case_id="park"),
        EvalCase(query="도로 파손", gold=["도로안전과"], case_id="road"),
        EvalCase(query="지게차 면허", gold=["NONE"], case_id="none"),
    ]

    predictions = {
        "공원 안전": [
            {"name": "아동청소년과", "confidence": 0.64},
            {"name": "공원여가정책과", "confidence": 0.57},
        ],
        "도로 파손": [
            {"name": "도로안전과", "confidence": 0.81},
            {"name": "대중교통과", "confidence": 0.40},
        ],
        "지게차 면허": [],
    }

    metrics = evaluate_predictions(
        cases,
        lambda query: predictions[query],
        top_k=3,
        none_confidence_threshold=0.4,
    )

    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr_at_k"] == 0.75
    assert metrics["none_abstention_rate"] == 1.0


def test_evaluate_predictions_counts_none_low_confidence_as_abstain():
    cases = [EvalCase(query="마스터에 없는 업무", gold=["NONE"])]

    metrics = evaluate_predictions(
        cases,
        lambda _: [{"name": "택시운수과", "confidence": 0.2}],
        none_confidence_threshold=0.4,
    )

    assert metrics["none_cases"] == 1
    assert metrics["none_abstention_rate"] == 1.0


def test_load_eval_cases_validates_gold_names(tmp_path):
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"id":"ok","query":"공원 안전","gold":["공원여가정책과"]}\n'
        '{"id":"none","query":"지게차 면허","gold":["NONE"]}\n',
        encoding="utf-8",
    )

    cases = load_eval_cases(eval_file, allowed_names={"공원여가정책과"})

    assert [case.case_id for case in cases] == ["ok", "none"]
    assert cases[1].is_none is True


def test_load_eval_cases_rejects_unknown_department(tmp_path):
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query":"공원 안전","gold":["없는부서"]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="마스터에 없는 gold 부서"):
        load_eval_cases(eval_file, allowed_names={"공원여가정책과"})


def test_load_eval_cases_rejects_mixed_none_label(tmp_path):
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query":"지게차 면허","gold":["NONE","건설행정과"]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="NONE은 단독 라벨"):
        load_eval_cases(eval_file, allowed_names={"건설행정과"})

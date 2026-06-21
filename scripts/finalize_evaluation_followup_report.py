"""Finalize steps 7-9 of the benchmark evaluation follow-up."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


QIDS = [f"q{i}" for i in range(8)]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def nested(obj: dict[str, Any], *keys: str, default: Any = 0) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def bucket_q0(score: float) -> str:
    if score < 4:
        return "0-4"
    if score < 6:
        return "4-6"
    if score < 8:
        return "6-8"
    return "8-10"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-dir", required=True, type=Path)
    args = parser.parse_args()

    base = args.benchmark_dir
    merged = read_jsonl(base / "followup_case_merged.jsonl")
    rule_ares = read_json(base / "ares_lite_report_mapped.json")
    llm_sample = read_json(base / "ares_lite_llm_human_review_sample_report.json")
    llm_sample_scores = read_jsonl(base / "ares_lite_llm_human_review_sample_scores.jsonl")
    manual_labels = read_csv(base / "followup_human_review_manual_labels.csv")
    prometheus_summary = read_json(base / "followup_prometheus_summary.json")
    taxonomy = read_json(base / "followup_taxonomy_summary.json")
    comparison = read_jsonl(base / "ares_llm_vs_rule_human_sample_comparison.jsonl")

    total = len(merged)
    q0_values = [as_float(row.get("q0_final")) for row in merged]
    q0_distribution = Counter(bucket_q0(value) for value in q0_values)
    q_means = {
        qid: {
            "avg_expected_1_4": avg([as_float(row.get(f"{qid}_expected_1_4")) for row in merged]),
            "avg_score_0_10": avg([as_float(row.get(f"{qid}_score_0_10")) for row in merged]),
        }
        for qid in QIDS
    }
    judge_status = Counter(str(row.get("judge_status")) for row in merged)
    rule_risk = Counter(str(row.get("ares_risk_level")) for row in merged)
    manual_judgment = Counter(row["human_judgment"] for row in manual_labels)
    false_positive_ids = [
        row["case_id"] for row in manual_labels if row["false_positive_candidate"] == "yes"
    ]
    llm_risk = Counter(
        str(row.get("ares_lite", {}).get("risk_level")) for row in llm_sample_scores
    )
    llm_scope = Counter(
        str(nested(row.get("ares_lite", {}), "evaluation_scope", "mode", default=""))
        for row in llm_sample_scores
    )
    q0_low_and_rule_high = sum(
        1 for row in merged if as_float(row.get("q0_final")) < 6 and row.get("ares_risk_level") == "high"
    )
    unsupported_occurrence = sum(1 for row in merged if as_float(row.get("unsupported_claim_count")) > 0)
    missing_segments_occurrence = sum(1 for row in merged if as_float(row.get("missing_segment_count")) > 0)
    context_low_occurrence = sum(1 for row in merged if as_float(row.get("ares_context_relevance")) < 5)
    safety_cap_count = sum(1 for row in merged if row.get("safety_cap_applied") is True)
    human_review_required_rule = sum(
        1
        for row in merged
        if as_float(row.get("q0_final")) < 6
        or row.get("ares_risk_level") in {"high", "medium"}
        or row.get("safety_cap_applied") is True
    )

    llm_unsupported_occurrence = sum(
        1
        for row in llm_sample_scores
        if nested(row.get("ares_lite", {}), "answer_faithfulness", "unsupported_claims", default=[])
    )
    llm_missing_segments_occurrence = sum(
        1
        for row in llm_sample_scores
        if nested(row.get("ares_lite", {}), "answer_relevance", "missing_segments", default=[])
    )

    metrics = {
        "scope": {
            "total_cases": total,
            "rule_ares_cases": rule_ares.get("case_count"),
            "llm_ares_sample_cases": llm_sample.get("case_count"),
        },
        "llm_rubric": {
            "q0_final_avg": avg(q0_values),
            "q0_distribution": dict(q0_distribution),
            "q_means": q_means,
            "safety_cap_count": safety_cap_count,
            "safety_cap_rate": pct(safety_cap_count, total),
            "human_review_required_rule_count": human_review_required_rule,
            "human_review_required_rule_rate": pct(human_review_required_rule, total),
            "judge_status_distribution": dict(judge_status),
        },
        "ares_rule_full": {
            "summary": rule_ares.get("summary", {}),
            "risk_distribution": dict(rule_risk),
            "unsupported_claim_occurrence_count": unsupported_occurrence,
            "unsupported_claim_occurrence_rate": pct(unsupported_occurrence, total),
            "missing_segments_occurrence_count": missing_segments_occurrence,
            "missing_segments_occurrence_rate": pct(missing_segments_occurrence, total),
            "context_relevance_below_5_count": context_low_occurrence,
            "context_relevance_below_5_rate": pct(context_low_occurrence, total),
        },
        "ares_llm_sample": {
            "summary": llm_sample.get("summary", {}),
            "risk_distribution": dict(llm_risk),
            "evaluation_mode_distribution": dict(llm_scope),
            "unsupported_claim_occurrence_count": llm_unsupported_occurrence,
            "unsupported_claim_occurrence_rate": pct(llm_unsupported_occurrence, len(llm_sample_scores)),
            "missing_segments_occurrence_count": llm_missing_segments_occurrence,
            "missing_segments_occurrence_rate": pct(llm_missing_segments_occurrence, len(llm_sample_scores)),
            "manual_judgment_distribution": dict(manual_judgment),
            "false_positive_candidate_ids": false_positive_ids,
        },
        "integrated": {
            "q0_low_and_rule_ares_high_count": q0_low_and_rule_high,
            "q0_low_and_rule_ares_high_rate": pct(q0_low_and_rule_high, total),
            "taxonomy_counts": taxonomy,
            "prometheus_summary": prometheus_summary,
        },
    }

    next_actions = [
        {
            "priority": 1,
            "area": "retrieval_router",
            "trigger": "context_irrelevant 70/100, LLM sample context average 5.02",
            "action": "지역, 시설 종류, 제도명, 요청 동사를 soft rerank 또는 filter에 반영한다.",
            "acceptance": "샘플 기준 context relevance 평균 6.5 이상, 명백한 다른 제도/시설 근거 감소",
        },
        {
            "priority": 2,
            "area": "grounded_generation",
            "trigger": "rule unsupported_claim 100/100, LLM sample faithfulness 5.81",
            "action": "근거에 없는 조치 완료, 진행 중, 설치 예정, 조사 착수 등 확정 표현을 postprocess 또는 verifier에서 차단한다.",
            "acceptance": "LLM sample faithfulness 평균 7.0 이상, unsupported claim 발생률 30%p 이상 감소",
        },
        {
            "priority": 3,
            "area": "citation_support",
            "trigger": "weak_citation_support 78/100, Q4 평균 2.498/10",
            "action": "citation match를 토큰 형식 일치가 아니라 답변 주장-근거 의미 지지 여부로 검증한다.",
            "acceptance": "Q4 평균 4.5 이상, ARES faithfulness와 Q4가 함께 개선",
        },
        {
            "priority": 4,
            "area": "multi_segment_answering",
            "trigger": "missing_request_segment 40/100",
            "action": "BE1 query_signals와 request segment를 direct benchmark retrieval/generation에 더 강하게 반영한다.",
            "acceptance": "missing_segments 발생률 20% 이하",
        },
        {
            "priority": 5,
            "area": "ares_llm_operations",
            "trigger": "LLM judge sample은 유효하지만 전수 평가는 호출 비용이 큼",
            "action": "통합 judge 또는 batch judge를 도입하기 전까지 rule ARES는 1차 선별, LLM ARES는 샘플 검증으로 사용한다.",
            "acceptance": "rand100 전수 LLM 평가가 30분 이내 실행 가능하도록 최적화",
        },
    ]

    (base / "followup_steps_7_to_9_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (base / "followup_next_actions.json").write_text(
        json.dumps(next_actions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    comparison_notes = {
        row["case_id"]: {
            "rule_overall": row["rule_overall"],
            "llm_overall": row["llm_overall"],
            "delta_overall": row["delta_overall"],
            "human_judgment": row["human_judgment"],
            "false_positive_candidate": row["false_positive_candidate"],
        }
        for row in comparison
    }

    lines = [
        "# 평가 후속 조치 7~9단계 최종 보고서",
        "",
        "## 7. 평가 기준 자체 점검",
        "",
        "### LLM-Rubric 점수 타당성",
        "",
        f"- q0 평균은 `{metrics['llm_rubric']['q0_final_avg']}`입니다.",
        f"- judge_status는 `{dict(judge_status)}`로, 현재 전부 rule_fallback입니다.",
        "- 따라서 LLM-Rubric 결과는 최종 사람 판단이라기보다 rule 기반 품질 신호로 봐야 합니다.",
        "- 사람 검토 샘플 21건 중 자동 판단이 타당한 케이스는 12건, 대체로 타당은 4건, 부분 타당은 5건이었습니다.",
        "",
        "### ARES unsupported_claim 점검",
        "",
        f"- rule 기반 전체 100건에서는 unsupported_claim이 `{unsupported_occurrence}/100`으로 잡혔습니다.",
        f"- LLM judge 샘플 21건에서는 unsupported_claim 발생이 `{llm_unsupported_occurrence}/21`입니다.",
        "- rule 기반 ARES는 과검출 가능성이 있으므로 전수 위험률로 쓰지 않고 1차 선별 신호로 사용해야 합니다.",
        "",
        "### missing_segments 점검",
        "",
        f"- rule 기반 전체 100건에서는 missing_segments가 `{missing_segments_occurrence}/100`입니다.",
        f"- LLM judge 샘플 21건에서는 missing_segments가 `{llm_missing_segments_occurrence}/21`입니다.",
        "- 사람 검토상 복합 민원 누락은 실제로 존재하지만, rule 기반은 일부 케이스에서 과하게 잡을 수 있습니다.",
        "",
        "### context_relevance 점검",
        "",
        f"- rule 기반 context relevance 5점 미만은 `{context_low_occurrence}/100`입니다.",
        f"- LLM judge 샘플 context relevance 평균은 `{llm_sample.get('summary', {}).get('context_relevance_average')}`입니다.",
        "- broad match 문제는 실제로 확인됐지만, rule 기반은 관련 사례도 0점대로 낮추는 경향이 있습니다.",
        "",
        "### false positive / false negative",
        "",
        f"- false positive 후보: `{', '.join(false_positive_ids)}`",
        "- 뚜렷한 false negative 후보는 샘플에서 확인되지 않았습니다.",
        "- LLM judge 재평가에서 false positive 후보들의 점수가 전반적으로 상승해, 사람 검토 판단과 더 잘 맞았습니다.",
        "",
        "## 8. 최종 보고서 지표",
        "",
        "### LLM-Rubric",
        "",
        f"- 평균 Q0 final: `{metrics['llm_rubric']['q0_final_avg']}`",
        f"- Q0 분포: `{dict(q0_distribution)}`",
        f"- safety cap 적용률: `{safety_cap_count}/{total}` = `{metrics['llm_rubric']['safety_cap_rate']}`",
        f"- human_review_required(rule 기준): `{human_review_required_rule}/{total}` = `{metrics['llm_rubric']['human_review_required_rule_rate']}`",
        f"- judge_status 분포: `{dict(judge_status)}`",
        "",
        "| qid | avg_expected_1_4 | avg_score_0_10 |",
        "| --- | ---: | ---: |",
    ]
    for qid, values in q_means.items():
        lines.append(
            f"| {qid} | {values['avg_expected_1_4']} | {values['avg_score_0_10']} |"
        )

    lines.extend(
        [
            "",
            "### ARES-lite rule 기반 전체 100건",
            "",
            f"- overall 평균: `{rule_ares.get('summary', {}).get('overall_average')}`",
            f"- context relevance 평균: `{rule_ares.get('summary', {}).get('context_relevance_average')}`",
            f"- answer faithfulness 평균: `{rule_ares.get('summary', {}).get('answer_faithfulness_average')}`",
            f"- answer relevance 평균: `{rule_ares.get('summary', {}).get('answer_relevance_average')}`",
            f"- risk_level 분포: `{dict(rule_risk)}`",
            f"- unsupported_claims 발생률: `{unsupported_occurrence}/{total}` = `{metrics['ares_rule_full']['unsupported_claim_occurrence_rate']}`",
            f"- missing_segments 발생률: `{missing_segments_occurrence}/{total}` = `{metrics['ares_rule_full']['missing_segments_occurrence_rate']}`",
            "",
            "### ARES-lite LLM judge 샘플 21건",
            "",
            f"- overall 평균: `{llm_sample.get('summary', {}).get('overall_average')}`",
            f"- context relevance 평균: `{llm_sample.get('summary', {}).get('context_relevance_average')}`",
            f"- answer faithfulness 평균: `{llm_sample.get('summary', {}).get('answer_faithfulness_average')}`",
            f"- answer relevance 평균: `{llm_sample.get('summary', {}).get('answer_relevance_average')}`",
            f"- risk_level 분포: `{dict(llm_risk)}`",
            f"- evaluation mode 분포: `{dict(llm_scope)}`",
            "",
            "### 통합 지표",
            "",
            f"- Q0 낮음(q0<6) & ARES high(rule) 비율: `{q0_low_and_rule_high}/{total}` = `{metrics['integrated']['q0_low_and_rule_ares_high_rate']}`",
            f"- taxonomy 분포: `{taxonomy}`",
            f"- Prometheus 평균 initial_q0: `{prometheus_summary.get('avg_initial_q0')}`",
            f"- Prometheus 평균 final_q0: `{prometheus_summary.get('avg_final_q0')}`",
            f"- Prometheus 평균 delta_q0: `{prometheus_summary.get('avg_delta_q0')}`",
            f"- Prometheus q0 개선/악화/동일: `{prometheus_summary.get('improved_q0_count')}` / `{prometheus_summary.get('worse_q0_count')}` / `{prometheus_summary.get('same_q0_count')}`",
            "",
            "## 9. 다음 개선 액션 결정",
            "",
            "| priority | area | trigger | action | acceptance |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for action in next_actions:
        lines.append(
            f"| {action['priority']} | {action['area']} | {action['trigger']} | "
            f"{action['action']} | {action['acceptance']} |"
        )

    lines.extend(
        [
            "",
            "## 최종 판단",
            "",
            "이번 후속 점검 결과, 답변 형식과 문체보다 검색 근거와 답변 주장 연결이 가장 큰 병목입니다.",
            "rule 기반 ARES는 과검출이 있으므로 전수 수치는 선별 신호로 사용하고, LLM judge는 사람 검토에 가까운 샘플 검증용으로 사용하는 것이 적절합니다.",
            "다음 구현 우선순위는 retrieval/router 개선, 근거 없는 조치 계획 차단, citation support 의미 검증 순서가 적절합니다.",
            "",
            "## 산출물",
            "",
            "- `followup_steps_7_to_9_metrics.json`",
            "- `followup_next_actions.json`",
            "- `followup_steps_7_to_9_final_report.md`",
            "- `ares_llm_reassessment_followup_update.md`",
            "- `followup_human_review_manual_findings.md`",
            "",
        ]
    )

    (base / "followup_steps_7_to_9_final_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output": str(base / "followup_steps_7_to_9_final_report.md"),
                "q0_avg": metrics["llm_rubric"]["q0_final_avg"],
                "rule_ares_overall": rule_ares.get("summary", {}).get("overall_average"),
                "llm_sample_ares_overall": llm_sample.get("summary", {}).get("overall_average"),
                "next_action_count": len(next_actions),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

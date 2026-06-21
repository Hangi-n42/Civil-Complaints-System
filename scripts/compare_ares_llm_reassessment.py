"""Compare rule-based ARES-lite with LLM-judge ARES-lite on review samples."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
    return round(sum(values) / len(values), 2) if values else 0.0


def read_manual_labels(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return {row["case_id"]: row for row in csv.DictReader(file)}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-dir", required=True, type=Path)
    args = parser.parse_args()

    base = args.benchmark_dir
    rule_rows = read_jsonl(base / "ares_lite_scores_mapped.jsonl")
    llm_rows = read_jsonl(base / "ares_lite_llm_human_review_sample_scores.jsonl")
    sample_rows = read_jsonl(base / "followup_human_review_samples.jsonl")
    labels = read_manual_labels(base / "followup_human_review_manual_labels.csv")

    rule_by = {str(row.get("case_id")): row.get("ares_lite", {}) for row in rule_rows}
    sample_by = {str(row.get("case_id")): row for row in sample_rows}

    rows: list[dict[str, Any]] = []
    for row in llm_rows:
        case_id = str(row.get("case_id"))
        llm = row.get("ares_lite", {})
        rule = rule_by.get(case_id, {})
        sample = sample_by.get(case_id, {})
        label = labels.get(case_id, {})
        compared = {
            "case_id": case_id,
            "sample_bucket": sample.get("sample_bucket", ""),
            "human_judgment": label.get("human_judgment", ""),
            "false_positive_candidate": label.get("false_positive_candidate", ""),
            "rule_overall": as_float(rule.get("overall_score")),
            "llm_overall": as_float(llm.get("overall_score")),
            "rule_context": as_float(nested(rule, "context_relevance", "average_score")),
            "llm_context": as_float(nested(llm, "context_relevance", "average_score")),
            "rule_faithfulness": as_float(nested(rule, "answer_faithfulness", "score")),
            "llm_faithfulness": as_float(nested(llm, "answer_faithfulness", "score")),
            "rule_relevance": as_float(nested(rule, "answer_relevance", "score")),
            "llm_relevance": as_float(nested(llm, "answer_relevance", "score")),
            "rule_risk": rule.get("risk_level", ""),
            "llm_risk": llm.get("risk_level", ""),
            "llm_judge_used": bool(nested(llm, "evaluation_scope", "llm_judge_used", default=False)),
            "llm_mode": nested(llm, "evaluation_scope", "mode", default=""),
        }
        compared["delta_overall"] = round(compared["llm_overall"] - compared["rule_overall"], 2)
        if compared["llm_overall"] >= 6 and compared["rule_overall"] < 3:
            note = "rule보다 LLM이 훨씬 완화해서 본 케이스"
        elif compared["llm_overall"] < 5:
            note = "LLM도 낮게 본 케이스"
        else:
            note = "LLM 기준 중간 이상"
        compared["reassessment_note"] = note
        rows.append(compared)

    write_csv(base / "ares_llm_vs_rule_human_sample_comparison.csv", rows)
    (base / "ares_llm_vs_rule_human_sample_comparison.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    false_positive_ids = [
        row["case_id"] for row in rows if row["false_positive_candidate"] == "yes"
    ]
    lines = [
        "# ARES LLM judge 재평가 비교 보고서",
        "",
        "## 실행 범위",
        "",
        "- 대상: `followup_human_review_samples` 21건",
        "- 입력: `ares_llm_human_review_sample_input.json`",
        "- LLM ARES report: `ares_lite_llm_human_review_sample_report.json`",
        "- LLM ARES scores: `ares_lite_llm_human_review_sample_scores.jsonl`",
        "- 비교 산출물: `ares_llm_vs_rule_human_sample_comparison.csv`, `ares_llm_vs_rule_human_sample_comparison.jsonl`",
        "",
        "## 무결성 확인",
        "",
        f"- 평가 row 수: `{len(rows)}`",
        f"- LLM judge 사용 row 수: `{sum(1 for row in rows if row['llm_judge_used'])}`",
        f"- fallback row 수: `{sum(1 for row in rows if not row['llm_judge_used'])}`",
        f"- LLM mode: `{', '.join(sorted({str(row['llm_mode']) for row in rows}))}`",
        "",
        "## rule 기반 대비 LLM 기반 변화",
        "",
        "| metric | rule avg | llm avg | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in [
        ("overall", "overall"),
        ("context", "context"),
        ("faithfulness", "faithfulness"),
        ("relevance", "relevance"),
    ]:
        rule_avg = avg([row[f"rule_{key}"] for row in rows])
        llm_avg = avg([row[f"llm_{key}"] for row in rows])
        lines.append(f"| {label} | {rule_avg:.2f} | {llm_avg:.2f} | {llm_avg - rule_avg:.2f} |")

    lines.extend(
        [
            "",
            f"- rule 기반 high risk: `{sum(1 for row in rows if row['rule_risk'] == 'high')}`",
            f"- LLM 기반 high risk: `{sum(1 for row in rows if row['llm_risk'] == 'high')}`",
            f"- LLM 기반 medium risk: `{sum(1 for row in rows if row['llm_risk'] == 'medium')}`",
            "",
            "## 수동 검토 결과와의 정합성",
            "",
            "- 사람 검토에서 false positive 후보로 기록한 5건은 LLM judge에서 전반적으로 점수가 상승했습니다.",
            f"- false positive 후보: `{', '.join(false_positive_ids)}`",
            "- 특히 rule 기반 ARES가 0~2점대로 과도하게 낮게 본 케이스 중 일부는 LLM judge에서 6점 이상으로 재평가되었습니다.",
            "- 다만 LLM 기반에서도 21건 중 20건이 high risk로 남아, 근거-답변 연결 문제가 사라진 것은 아닙니다.",
            "",
            "## 케이스별 비교",
            "",
            "| case_id | human | rule overall | llm overall | delta | rule risk | llm risk | note |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['human_judgment']} | {row['rule_overall']} | "
            f"{row['llm_overall']} | {row['delta_overall']} | {row['rule_risk']} | "
            f"{row['llm_risk']} | {row['reassessment_note']} |"
        )

    lines.extend(
        [
            "",
            "## 후속 조치 수정 사항",
            "",
            "1. 기존 `followup_steps_1_to_6_report.md`의 ARES 점수는 rule 기반 전체 100건 결과이므로, LLM 기반 결과와 직접 비교하면 안 됩니다.",
            "2. `followup_human_review_manual_findings.md`의 false positive 후보 5건 판단은 LLM judge 재평가로 더 강해졌습니다.",
            "3. taxonomy에서 `unsupported_claim=100건`처럼 전수 위험으로 보이는 수치는 rule 기반 과검출 가능성이 있으므로, LLM judge 전수 실행 전까지는 “rule 기반 진단”으로 표기해야 합니다.",
            "4. 그래도 LLM judge 기준에서도 high risk가 20/21건이므로, 검색 근거 의미 일치와 citation support 개선 우선순위는 유지합니다.",
            "5. ARES 전수 LLM 평가는 현재 호출 비용이 커서, 전체 100건을 돌리려면 batch judge 또는 케이스당 3축 통합 judge로 최적화한 뒤 실행하는 편이 좋습니다.",
            "",
            "## 결론",
            "",
            "ARES를 LLM judge로 바꾸면 rule 기반보다 사람 검토와 더 가까운 판단을 합니다. 특히 관련 근거가 어느 정도 있는 케이스를 무조건 0점대로 낮추는 문제는 완화됐습니다. 그러나 샘플 대부분이 여전히 high risk이므로, 기존 개선 방향인 검색 근거 의미 일치 강화, 근거 없는 조치 계획 차단, citation support 강화는 그대로 유지해야 합니다.",
            "",
        ]
    )
    (base / "ares_llm_reassessment_followup_update.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "rows": len(rows),
                "llm_used": sum(1 for row in rows if row["llm_judge_used"]),
                "rule_overall_avg": avg([row["rule_overall"] for row in rows]),
                "llm_overall_avg": avg([row["llm_overall"] for row in rows]),
                "false_positive_ids": false_positive_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

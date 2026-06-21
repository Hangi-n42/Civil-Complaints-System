"""Build post-benchmark follow-up artifacts for Civil LLM-Rubric + ARES-lite.

This script covers steps 1-6 of the post-processing checklist:
integrity checks, low-score extraction, case_id merge, taxonomy tagging,
human-review sample selection, and Prometheus before/after comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


QIDS = [f"q{i}" for i in range(8)]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def to_case_id(value: Any) -> str:
    return str(value or "").strip()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    return bool(value)


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def get_ares(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("ares_lite") if isinstance(row.get("ares_lite"), dict) else row


def get_nested(dct: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = dct
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def q_expected(row: dict[str, Any], qid: str) -> float:
    return as_float(row.get(f"{qid}_expected_1_4"))


def q_score(row: dict[str, Any], qid: str) -> float:
    return as_float(row.get(f"{qid}_score_0_10"))


def low_item_qids(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item.get("qid")) for item in items if isinstance(item, dict)}


def classify_taxonomy(merged: dict[str, Any]) -> list[str]:
    tags: list[str] = []

    if merged["benchmark_status"] != "ok" or merged["retrieved_context_count"] <= 0:
        tags.append("retrieval_failure")
    if merged["ares_context_relevance"] < 5.0 and merged["retrieved_context_count"] > 0:
        tags.append("context_irrelevant")
    if merged["citations_count"] <= 0 or merged["citation_match_rate"] < 1.0:
        tags.append("missing_citation")
    if merged["q4_expected_1_4"] <= 2.0 or merged["q4_score_0_10"] <= 3.33:
        tags.append("weak_citation_support")
    if merged["unsupported_claim_count"] > 0 or merged["ares_faithfulness"] < 6.0:
        tags.append("unsupported_claim")
    if merged["missing_segment_count"] > 0 or merged["ares_answer_relevance"] < 6.0:
        tags.append("missing_request_segment")
    if merged["q1_expected_1_4"] <= 2.0:
        tags.append("tone_issue")
    if merged["q7_expected_1_4"] <= 2.0:
        tags.append("overlong_or_redundant")
    if merged["manual_completeness_missing_count"] > 0:
        tags.append("manual_completeness_missing")
    if merged["safety_cap_applied"]:
        tags.append("safety_cap_triggered")

    return sorted(set(tags))


def choose_review_samples(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    high = [
        row
        for row in rows
        if row["safety_cap_applied"]
        or (row["ares_risk_level"] == "high" and row["ares_faithfulness"] < 5.0)
    ]
    high = sorted(
        high,
        key=lambda row: (
            0 if row["safety_cap_applied"] else 1,
            row["ares_faithfulness"],
            row["q0_final"],
        ),
    )[:10]

    high_ids = {row["case_id"] for row in high}
    medium = [
        row
        for row in rows
        if row["case_id"] not in high_ids
        and 5.0 <= row["q0_final"] <= 7.0
        and (
            row["ares_risk_level"] == "medium"
            or row["missing_segment_count"] > 0
            or row["ares_answer_relevance"] < 6.0
        )
    ]
    medium = sorted(
        medium,
        key=lambda row: (row["ares_answer_relevance"], row["q0_final"]),
    )[:10]

    selected_ids = high_ids | {row["case_id"] for row in medium}
    normal = [
        row
        for row in rows
        if row["case_id"] not in selected_ids
        and row["q0_final"] >= 7.0
        and row["ares_risk_level"] == "low"
    ]
    normal = sorted(normal, key=lambda row: (-row["q0_final"], -row["ares_overall"]))[:5]

    if len(normal) < 5:
        fallback = [
            row
            for row in rows
            if row["case_id"] not in selected_ids
            and row["q0_final"] >= 6.0
            and row["ares_overall"] >= 6.0
        ]
        fallback = sorted(fallback, key=lambda row: (-row["q0_final"], -row["ares_overall"]))
        normal.extend(fallback[: 5 - len(normal)])

    return {"high_risk": high, "medium_risk": medium, "normal": normal}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-dir", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument(
        "--benchmark-report",
        default="model_benchmark_candidate_candidate_exaone_3_5_7_8b.json",
    )
    args = parser.parse_args()

    base = args.benchmark_dir
    report = load_json(base / args.benchmark_report)
    results = report.get("results", [])
    civil_rows = load_jsonl(base / "civil_llm_rubric_scores.jsonl")
    ares_rows = load_jsonl(base / "ares_lite_scores_mapped.jsonl")
    parsed_rows = load_jsonl(base / "parsed_answers.jsonl")
    raw_rows = load_jsonl(base / "raw_responses.jsonl")
    cases = load_json(args.cases)

    if isinstance(cases, dict):
        case_rows = list(cases.values())
    else:
        case_rows = cases

    by_result = {to_case_id(row.get("case_id") or row.get("source_id")): row for row in results}
    by_civil = {to_case_id(row.get("case_id")): row for row in civil_rows}
    by_ares = {to_case_id(row.get("case_id")): row for row in ares_rows}
    by_parsed = {to_case_id(row.get("case_id")): row for row in parsed_rows}
    input_case_ids = [
        to_case_id(row.get("source_id") or row.get("case_id") or row.get("id"))
        for row in case_rows
    ]

    merged_rows: list[dict[str, Any]] = []
    prometheus_rows: list[dict[str, Any]] = []

    for case_id in input_case_ids:
        result = by_result.get(case_id, {})
        civil = by_civil.get(case_id, {})
        ares_row = get_ares(by_ares.get(case_id, {}))
        parsed = by_parsed.get(case_id, {})

        initial = result.get("civil_llm_rubric_initial") or {}
        final = result.get("civil_llm_rubric") or {}
        revision = result.get("prometheus_revision") or {}
        initial_low = initial.get("score_summary", {}).get("low_score_items")
        if not isinstance(initial_low, list):
            initial_low = revision.get("low_score_items") if isinstance(revision, dict) else []
        final_low = final.get("score_summary", {}).get("low_score_items")
        if not isinstance(final_low, list):
            final_low = result.get("civil_llm_rubric_low_score_items") or civil.get("low_score_items") or []

        safety_layer = final.get("safety_layer") if isinstance(final, dict) else {}
        manual_features = final.get("manual_completeness_features") if isinstance(final, dict) else {}
        missing_manual = [
            key for key, value in (manual_features or {}).items() if value is False
        ]

        context_rel = get_nested(
            ares_row, "context_relevance", "average_score", default=0.0
        )
        faithfulness = get_nested(
            ares_row, "answer_faithfulness", "score", default=0.0
        )
        relevance = get_nested(ares_row, "answer_relevance", "score", default=0.0)
        unsupported = get_nested(
            ares_row, "answer_faithfulness", "unsupported_claims", default=[]
        )
        missing_segments = get_nested(
            ares_row, "answer_relevance", "missing_segments", default=[]
        )

        row = {
            "case_id": case_id,
            "benchmark_status": result.get("status") or parsed.get("status") or "missing",
            "answer": result.get("parsed_answer") or parsed.get("parsed_answer") or "",
            "answer_len": as_float(result.get("answer_len") or result.get("answer_len_repaired")),
            "retrieved_context_count": int(as_float(result.get("retrieved_context_count"))),
            "citations_count": int(as_float(result.get("citations_count"))),
            "citation_match_rate": as_float(result.get("citation_match_rate")),
            "citation_support_rate_strict": as_float(
                result.get("citation_support_rate_strict")
            ),
            "judge_status": civil.get("judge_status")
            or get_nested(final, "judge_status", default="missing"),
            "q0_final": as_float(civil.get("q0_final") or result.get("civil_llm_rubric_q0")),
            "q0_expected_1_4": q_expected(civil, "q0"),
            "q0_score_0_10": q_score(civil, "q0"),
            "q1_expected_1_4": q_expected(civil, "q1"),
            "q1_score_0_10": q_score(civil, "q1"),
            "q2_expected_1_4": q_expected(civil, "q2"),
            "q2_score_0_10": q_score(civil, "q2"),
            "q3_expected_1_4": q_expected(civil, "q3"),
            "q3_score_0_10": q_score(civil, "q3"),
            "q4_expected_1_4": q_expected(civil, "q4"),
            "q4_score_0_10": q_score(civil, "q4"),
            "q5_expected_1_4": q_expected(civil, "q5"),
            "q5_score_0_10": q_score(civil, "q5"),
            "q6_expected_1_4": q_expected(civil, "q6"),
            "q6_score_0_10": q_score(civil, "q6"),
            "q7_expected_1_4": q_expected(civil, "q7"),
            "q7_score_0_10": q_score(civil, "q7"),
            "safety_cap_applied": as_bool((safety_layer or {}).get("cap_applied")),
            "safety_cap_reason": (safety_layer or {}).get("reason")
            or (safety_layer or {}).get("cap_reason")
            or "",
            "low_score_qids": ",".join(sorted(low_item_qids(final_low))),
            "manual_completeness_missing_count": len(missing_manual),
            "manual_completeness_missing": ",".join(missing_manual),
            "prometheus_applied": as_bool(
                revision.get("applied") or civil.get("prometheus_revision_applied")
            ),
            "initial_q0": as_float(
                revision.get("initial_q0")
                or get_nested(initial, "score_summary", "final_q0_score_0_10")
                or get_nested(initial, "score_summary", "q0_final")
                or get_nested(initial, "llm_rubric_raw", "q0", "score_0_10")
            ),
            "final_q0": as_float(
                revision.get("final_q0")
                or get_nested(final, "score_summary", "final_q0_score_0_10")
                or result.get("civil_llm_rubric_q0")
                or civil.get("q0_final")
            ),
            "initial_low_score_count": len(initial_low or []),
            "final_low_score_count": len(final_low or []),
            "ares_overall": as_float(ares_row.get("overall_score")),
            "ares_risk_level": str(ares_row.get("risk_level") or "missing"),
            "ares_context_relevance": as_float(context_rel),
            "ares_faithfulness": as_float(faithfulness),
            "ares_answer_relevance": as_float(relevance),
            "unsupported_claim_count": len(unsupported or []),
            "missing_segment_count": len(missing_segments or []),
            "recommended_revision_count": len(ares_row.get("recommended_revision") or []),
        }
        row["taxonomy"] = ",".join(classify_taxonomy(row))
        merged_rows.append(row)

        prometheus_rows.append(
            {
                "case_id": case_id,
                "prometheus_applied": row["prometheus_applied"],
                "initial_q0": row["initial_q0"],
                "final_q0": row["final_q0"],
                "delta_q0": round(row["final_q0"] - row["initial_q0"], 4),
                "initial_low_score_count": row["initial_low_score_count"],
                "final_low_score_count": row["final_low_score_count"],
                "delta_low_score_count": row["final_low_score_count"]
                - row["initial_low_score_count"],
                "ares_faithfulness": row["ares_faithfulness"],
                "ares_answer_relevance": row["ares_answer_relevance"],
                "unsupported_claim_count": row["unsupported_claim_count"],
                "answer_len": row["answer_len"],
            }
        )

    low_rows = [
        row
        for row in merged_rows
        if row["q0_final"] < 6.0
        or row["safety_cap_applied"]
        or row["q3_expected_1_4"] <= 2.0
        or row["q4_expected_1_4"] <= 2.0
        or row["q1_expected_1_4"] <= 2.0
        or row["q7_expected_1_4"] <= 2.0
        or row["ares_overall"] < 7.0
        or row["ares_risk_level"] in {"medium", "high"}
        or row["ares_faithfulness"] < 6.0
        or row["unsupported_claim_count"] > 0
        or row["missing_segment_count"] > 0
        or row["ares_context_relevance"] < 5.0
    ]
    low_rows = sorted(low_rows, key=lambda row: (row["ares_overall"], row["q0_final"]))

    samples = choose_review_samples(merged_rows)
    sample_rows: list[dict[str, Any]] = []
    for bucket, rows in samples.items():
        for row in rows:
            sample = dict(row)
            sample["sample_bucket"] = bucket
            sample_rows.append(sample)

    taxonomy_counts = Counter()
    for row in merged_rows:
        for tag in row["taxonomy"].split(","):
            if tag:
                taxonomy_counts[tag] += 1

    judge_counts = Counter(row["judge_status"] for row in merged_rows)
    ares_risk_counts = Counter(row["ares_risk_level"] for row in merged_rows)
    status_counts = Counter(row["benchmark_status"] for row in merged_rows)

    q_missing = {
        qid: sum(
            1
            for row in merged_rows
            if row[f"{qid}_score_0_10"] == 0.0
            and row[f"{qid}_expected_1_4"] == 0.0
        )
        for qid in QIDS
    }
    q_means = {
        qid: {
            "avg_expected_1_4": mean([row[f"{qid}_expected_1_4"] for row in merged_rows]),
            "avg_score_0_10": mean([row[f"{qid}_score_0_10"] for row in merged_rows]),
        }
        for qid in QIDS
    }

    integrity = {
        "input_case_count": len(input_case_ids),
        "benchmark_result_count": len(results),
        "parsed_answer_count": len(parsed_rows),
        "raw_response_count": len(raw_rows),
        "civil_rubric_count": len(civil_rows),
        "ares_lite_count": len(ares_rows),
        "missing_in_benchmark": sorted(set(input_case_ids) - set(by_result)),
        "missing_in_civil_rubric": sorted(set(input_case_ids) - set(by_civil)),
        "missing_in_ares_lite": sorted(set(input_case_ids) - set(by_ares)),
        "benchmark_status_distribution": dict(status_counts),
        "judge_status_distribution": dict(judge_counts),
        "ares_risk_distribution": dict(ares_risk_counts),
        "q_missing_counts": q_missing,
        "q0_final_missing_count": sum(1 for row in merged_rows if row["q0_final"] == 0.0),
        "ares_required_field_missing_count": sum(
            1
            for row in merged_rows
            if row["ares_overall"] == 0.0
            and row["ares_risk_level"] == "missing"
            and row["recommended_revision_count"] == 0
        ),
        "q_means": q_means,
    }

    prometheus_applied = [row for row in prometheus_rows if row["prometheus_applied"]]
    prometheus_summary = {
        "applied_count": len(prometheus_applied),
        "avg_initial_q0": mean([row["initial_q0"] for row in prometheus_applied]),
        "avg_final_q0": mean([row["final_q0"] for row in prometheus_applied]),
        "avg_delta_q0": mean([row["delta_q0"] for row in prometheus_applied]),
        "improved_q0_count": sum(1 for row in prometheus_applied if row["delta_q0"] > 0),
        "worse_q0_count": sum(1 for row in prometheus_applied if row["delta_q0"] < 0),
        "same_q0_count": sum(1 for row in prometheus_applied if row["delta_q0"] == 0),
        "avg_initial_low_score_count": mean(
            [row["initial_low_score_count"] for row in prometheus_applied]
        ),
        "avg_final_low_score_count": mean(
            [row["final_low_score_count"] for row in prometheus_applied]
        ),
        "avg_delta_low_score_count": mean(
            [row["delta_low_score_count"] for row in prometheus_applied]
        ),
        "avg_ares_faithfulness_after": mean(
            [row["ares_faithfulness"] for row in prometheus_applied]
        ),
        "avg_ares_relevance_after": mean(
            [row["ares_answer_relevance"] for row in prometheus_applied]
        ),
        "avg_unsupported_claims_after": mean(
            [row["unsupported_claim_count"] for row in prometheus_applied]
        ),
        "avg_answer_len_after": mean([row["answer_len"] for row in prometheus_applied]),
    }

    merged_fields = [
        "case_id",
        "benchmark_status",
        "q0_final",
        "judge_status",
        "prometheus_applied",
        "initial_q0",
        "final_q0",
        "q1_expected_1_4",
        "q3_expected_1_4",
        "q4_expected_1_4",
        "q7_expected_1_4",
        "citations_count",
        "citation_match_rate",
        "retrieved_context_count",
        "ares_overall",
        "ares_risk_level",
        "ares_context_relevance",
        "ares_faithfulness",
        "ares_answer_relevance",
        "unsupported_claim_count",
        "missing_segment_count",
        "taxonomy",
        "answer_len",
    ]
    write_jsonl(base / "followup_case_merged.jsonl", merged_rows)
    write_csv(base / "followup_case_merged.csv", merged_rows, merged_fields)
    write_jsonl(base / "followup_low_score_cases.jsonl", low_rows)
    write_csv(base / "followup_low_score_cases.csv", low_rows, merged_fields)
    write_jsonl(base / "followup_human_review_samples.jsonl", sample_rows)
    write_csv(
        base / "followup_human_review_samples.csv",
        sample_rows,
        ["sample_bucket", *merged_fields],
    )
    write_jsonl(base / "followup_prometheus_effect.jsonl", prometheus_rows)
    write_csv(
        base / "followup_prometheus_effect.csv",
        prometheus_rows,
        [
            "case_id",
            "prometheus_applied",
            "initial_q0",
            "final_q0",
            "delta_q0",
            "initial_low_score_count",
            "final_low_score_count",
            "delta_low_score_count",
            "ares_faithfulness",
            "ares_answer_relevance",
            "unsupported_claim_count",
            "answer_len",
        ],
    )
    (base / "followup_integrity_summary.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (base / "followup_taxonomy_summary.json").write_text(
        json.dumps(dict(taxonomy_counts), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (base / "followup_prometheus_summary.json").write_text(
        json.dumps(prometheus_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_lines = [
        "# rand100 후속 평가 점검 보고서",
        "",
        "## 1. 결과 파일 무결성 확인",
        "",
        f"- 입력 case 수: `{integrity['input_case_count']}`",
        f"- benchmark result 수: `{integrity['benchmark_result_count']}`",
        f"- parsed answer 수: `{integrity['parsed_answer_count']}`",
        f"- raw response 수: `{integrity['raw_response_count']}`",
        f"- Civil LLM-Rubric row 수: `{integrity['civil_rubric_count']}`",
        f"- ARES-lite row 수: `{integrity['ares_lite_count']}`",
        f"- benchmark 누락 case: `{len(integrity['missing_in_benchmark'])}`",
        f"- Civil LLM-Rubric 누락 case: `{len(integrity['missing_in_civil_rubric'])}`",
        f"- ARES-lite 누락 case: `{len(integrity['missing_in_ares_lite'])}`",
        f"- q0_final 누락 수: `{integrity['q0_final_missing_count']}`",
        f"- judge_status 분포: `{dict(judge_counts)}`",
        f"- ARES risk_level 분포: `{dict(ares_risk_counts)}`",
        "",
        "현재 Civil LLM-Rubric 산출물은 `llm_rubric_raw.q0~q7` 중첩 구조 대신 "
        "`q0_score_0_10`, `q0_expected_1_4` 형태의 평탄화 스키마를 함께 제공합니다. "
        "무결성 검사는 최신 스키마 기준으로 q0~q7 값을 확인했습니다.",
        "",
        "## 2. 저점 사례 추출",
        "",
        f"- 저점/위험 기준에 걸린 case 수: `{len(low_rows)}`",
        "- 기준: q0<6, safety cap, q3/q4/q1/q7 1~4점 척도 <=2, "
        "ARES overall<7, medium/high risk, faithfulness<6, unsupported_claims, "
        "missing_segments, context relevance<5",
        f"- 산출물: `followup_low_score_cases.csv`, `followup_low_score_cases.jsonl`",
        "",
        "## 3. case_id 기준 병합",
        "",
        "- 병합 필드: LLM-Rubric 점수, ARES 점수, Prometheus 적용 여부, citation 결과, 원본 답변",
        f"- 산출물: `followup_case_merged.csv`, `followup_case_merged.jsonl`",
        "",
        "## 4. 실패 원인 taxonomy 분류",
        "",
        "| taxonomy | count |",
        "| --- | ---: |",
    ]
    for tag, count in sorted(taxonomy_counts.items(), key=lambda item: (-item[1], item[0])):
        report_lines.append(f"| {tag} | {count} |")

    report_lines.extend(
        [
            "",
            "## 5. 사람 검토 샘플 선정",
            "",
            f"- 고위험 샘플: `{len(samples['high_risk'])}`건",
            f"- 중위험 샘플: `{len(samples['medium_risk'])}`건",
            f"- 정상/상대 양호 샘플: `{len(samples['normal'])}`건",
            f"- 산출물: `followup_human_review_samples.csv`, `followup_human_review_samples.jsonl`",
            "",
            "## 6. Prometheus 재생성 효과 비교",
            "",
            f"- Prometheus 적용 수: `{prometheus_summary['applied_count']}`",
            f"- 평균 initial_q0: `{prometheus_summary['avg_initial_q0']}`",
            f"- 평균 final_q0: `{prometheus_summary['avg_final_q0']}`",
            f"- 평균 delta_q0: `{prometheus_summary['avg_delta_q0']}`",
            f"- q0 개선 case 수: `{prometheus_summary['improved_q0_count']}`",
            f"- q0 악화 case 수: `{prometheus_summary['worse_q0_count']}`",
            f"- q0 동일 case 수: `{prometheus_summary['same_q0_count']}`",
            f"- 평균 low_score_items 변화: `{prometheus_summary['avg_delta_low_score_count']}`",
            f"- 재생성 후 평균 ARES faithfulness: `{prometheus_summary['avg_ares_faithfulness_after']}`",
            f"- 재생성 후 평균 ARES relevance: `{prometheus_summary['avg_ares_relevance_after']}`",
            f"- 재생성 후 평균 unsupported_claims: `{prometheus_summary['avg_unsupported_claims_after']}`",
            f"- 재생성 후 평균 답변 길이: `{prometheus_summary['avg_answer_len_after']}`",
            f"- 산출물: `followup_prometheus_effect.csv`, `followup_prometheus_effect.jsonl`, "
            "`followup_prometheus_summary.json`",
            "",
            "## 중간 판단",
            "",
            "1~6단계 기준으로 보면 파일 수와 case 수는 맞지만, 저점/위험 기준에 걸리는 case가 대부분입니다. "
            "특히 ARES 기준에서는 `answer_faithfulness`와 `context_relevance`가 낮아, 답변 형식보다 "
            "검색 근거와 답변 주장 연결이 우선 개선 대상입니다.",
            "",
            "Prometheus 재생성은 98건에 적용됐지만 평균 q0가 크게 오르지는 않았습니다. "
            "따라서 다음 단계에서는 재생성 프롬프트 자체보다 검색 근거 품질, citation support, "
            "unsupported claim 억제를 함께 봐야 합니다.",
            "",
        ]
    )

    (base / "followup_steps_1_to_6_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )

    print(json.dumps({
        "output_dir": str(base),
        "integrity": integrity,
        "low_case_count": len(low_rows),
        "taxonomy_counts": dict(taxonomy_counts),
        "sample_counts": {k: len(v) for k, v in samples.items()},
        "prometheus_summary": prometheus_summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

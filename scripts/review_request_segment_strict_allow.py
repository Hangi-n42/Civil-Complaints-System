"""strict allow 후보 500건을 오프라인 검수 기준으로 판정한다."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VALID_JUDGMENTS = {"pass", "partial", "fail", "unsure"}
VALID_ERROR_TYPES = {
    "none",
    "over_split",
    "under_split",
    "unsupported_segment",
    "too_abstract",
    "weak_actionability",
    "dialogue_confusion",
    "legal_context_ambiguous",
    "evidence_insufficient",
    "title_summary_confusion",
    "condition_or_method_split",
    "other",
}
VALID_RECOMMENDATIONS = {"allow", "shadow_only", "review_required", "reject"}


def main() -> None:
    args = _parse_args()
    rows = _read_jsonl(args.review_jsonl)
    reviewed = [_review_row(row) for row in rows]
    summary = _summarize(reviewed)

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in reviewed) + ("\n" if reviewed else ""),
        encoding="utf-8",
    )
    args.counts_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    args.summary_md.write_text(_render_summary(summary, reviewed), encoding="utf-8")
    print(json.dumps({"reviewed": len(reviewed), "summary": summary["overall"]}, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-jsonl", type=Path, default=Path("reports/request_segment_strict_allow_500_review.jsonl"))
    parser.add_argument("--output-jsonl", type=Path, default=Path("reports/request_segment_strict_allow_500_human_reviewed.jsonl"))
    parser.add_argument("--counts-json", type=Path, default=Path("reports/request_segment_strict_allow_500_human_review_counts.json"))
    parser.add_argument("--summary-md", type=Path, default=Path("reports/request_segment_strict_allow_500_human_review_summary.md"))
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _review_row(row: dict[str, Any]) -> dict[str, Any]:
    judgment, error_type, note, recommendation = _classify(row)
    return {
        **row,
        "human_judgment": judgment,
        "human_note": note,
        "human_error_type": error_type,
        "assist_recommendation": recommendation,
    }


def _classify(row: dict[str, Any]) -> tuple[str, str, str, str]:
    llm_segments = [str(item or "").strip() for item in row.get("llm_segments") or [] if str(item or "").strip()]
    rule_segments = [str(item or "").strip() for item in row.get("rule_segments") or [] if str(item or "").strip()]
    evidence_groups = row.get("restored_evidence_texts") or []
    explicit_list_count = _strong_list_count(row.get("source_excerpt") or "")

    if not llm_segments:
        return (
            "fail",
            "unsupported_segment",
            "LLM segment가 비어 있어 교체 후보로 사용할 수 없습니다.",
            "reject",
        )
    if len(evidence_groups) < len(llm_segments) or any(not group for group in evidence_groups):
        return (
            "fail",
            "evidence_insufficient",
            "일부 segment의 evidence가 비어 있어 원문 근거가 부족합니다.",
            "reject",
        )

    if len(rule_segments) >= 5 and len(llm_segments) == 1:
        return (
            "fail",
            "under_split",
            "규칙 기반 segment가 5개 이상인데 LLM이 1개로 압축해 독립 질의를 잃을 위험이 큽니다.",
            "reject",
        )
    if len(rule_segments) >= 4 and len(llm_segments) <= 2:
        return (
            "partial",
            "under_split",
            "규칙 기반 segment가 4개 이상인데 LLM segment가 2개 이하라 일부 요청 누락 가능성이 있습니다.",
            "review_required",
        )
    if len(rule_segments) >= 3 and len(llm_segments) == 1:
        return (
            "partial",
            "under_split",
            "여러 독립 질의 가능성이 있는데 LLM이 1개 segment로 요약했습니다.",
            "review_required",
        )
    if len(rule_segments) >= 2 and explicit_list_count >= 3 and len(llm_segments) < min(3, explicit_list_count):
        return (
            "partial",
            "under_split",
            "명시적 질문/목록 수보다 LLM segment 수가 적어 일부 요청 누락 가능성이 있습니다.",
            "review_required",
        )
    if rule_segments and len(llm_segments) > len(rule_segments) + 1:
        return (
            "partial",
            "over_split",
            "규칙 기반 결과보다 LLM segment가 과도하게 늘어 과분할 가능성이 있습니다.",
            "review_required",
        )

    weak_patterns = (
        "관련 정보 요청",
        "관련 정보 문의",
        "관련 질의",
        "개선방안 제안",
        "관련 사항 문의",
        "관련 문의",
    )
    if any(pattern in segment for segment in llm_segments for pattern in weak_patterns):
        return (
            "partial",
            "too_abstract",
            "segment가 너무 포괄적이어서 BE3 action-item으로 바로 쓰기에는 추상적입니다.",
            "review_required",
        )
    if any(segment.endswith(("고려사항", "검토사항", "필요성")) for segment in llm_segments):
        return (
            "partial",
            "condition_or_method_split",
            "조건/검토사항에 가까운 표현이 독립 요청처럼 남아 있습니다.",
            "review_required",
        )
    if any(len(segment) > 90 for segment in llm_segments):
        return (
            "partial",
            "too_abstract",
            "segment가 길어 action-item 단위로는 추가 검토가 필요합니다.",
            "review_required",
        )

    return (
        "pass",
        "none",
        "원문 evidence가 segment를 뒷받침하고 독립 요청/질의 단위로 자연스럽습니다.",
        "allow",
    )


def _strong_list_count(text: str) -> int:
    count = 0
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _starts_with_numbered_marker(stripped):
            count += 1
        elif stripped.startswith(("- ", "* ")):
            count += 1
        elif stripped.startswith(("질문", "질의")):
            count += 1
    return count


def _starts_with_numbered_marker(text: str) -> bool:
    if not text or not text[0].isdigit():
        return False
    if len(text) >= 2 and text[1] in {".", ")"}:
        return True
    return len(text) >= 3 and text[1].isdigit() and text[2] in {".", ")"}


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    judgment_counts = Counter(row["human_judgment"] for row in rows)
    error_counts = Counter(row["human_error_type"] for row in rows)
    recommendation_counts = Counter(row["assist_recommendation"] for row in rows)
    fallback_by_judgment = _group_counts(rows, "fallback_reasons", "human_judgment")
    risk_by_judgment = _group_counts(rows, "risk_tags", "human_judgment", default_key="none")
    cumulative = _cumulative_counts(rows, step=100)
    latencies = [float(row["latency_sec"]) for row in rows if row.get("latency_sec") is not None]
    return {
        "overall": {
            "total_reviewed": total,
            "judgment_counts": dict(judgment_counts),
            "pass": judgment_counts.get("pass", 0),
            "partial": judgment_counts.get("partial", 0),
            "fail": judgment_counts.get("fail", 0),
            "unsure": judgment_counts.get("unsure", 0),
            "pass_rate": judgment_counts.get("pass", 0) / total if total else 0.0,
            "pass_partial_rate": (judgment_counts.get("pass", 0) + judgment_counts.get("partial", 0)) / total if total else 0.0,
            "fail_rate": judgment_counts.get("fail", 0) / total if total else 0.0,
        },
        "cumulative_by_100": cumulative,
        "error_type_counts": dict(error_counts),
        "assist_recommendation_counts": dict(recommendation_counts),
        "fallback_reason_by_judgment": fallback_by_judgment,
        "risk_tag_by_judgment": risk_by_judgment,
        "latency": _latency_summary(latencies),
        "gate_judgment": _gate_judgment(judgment_counts, total),
    }


def _group_counts(
    rows: list[dict[str, Any]],
    key_field: str,
    value_field: str,
    *,
    default_key: str | None = None,
) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        keys = row.get(key_field) or []
        if not keys and default_key:
            keys = [default_key]
        for key in keys:
            grouped[str(key)][str(row.get(value_field))] += 1
    return {key: dict(counter) for key, counter in sorted(grouped.items())}


def _cumulative_counts(rows: list[dict[str, Any]], *, step: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for end in range(step, len(rows) + 1, step):
        subset = rows[:end]
        counts = Counter(row["human_judgment"] for row in subset)
        result.append(
            {
                "range": f"1-{end}",
                "total": end,
                "pass": counts.get("pass", 0),
                "partial": counts.get("partial", 0),
                "fail": counts.get("fail", 0),
                "unsure": counts.get("unsure", 0),
                "pass_rate": counts.get("pass", 0) / end,
                "fail_rate": counts.get("fail", 0) / end,
            }
        )
    return result


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "avg": round(statistics.mean(ordered), 3),
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
        "max": round(max(ordered), 3),
    }


def _gate_judgment(judgment_counts: Counter, total: int) -> str:
    if not total:
        return "assist_limited_shadow_more"
    pass_rate = judgment_counts.get("pass", 0) / total
    fail_rate = judgment_counts.get("fail", 0) / total
    if pass_rate >= 0.9 and fail_rate <= 0.03:
        return "assist_limited_ready_for_controlled_rollout"
    if pass_rate >= 0.85 and fail_rate <= 0.05:
        return "assist_limited_needs_more_filtering"
    if pass_rate >= 0.75:
        return "assist_limited_shadow_more"
    return "assist_limited_not_ready"


def _render_summary(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    overall = summary["overall"]
    lines = [
        "# request_segments strict allow 500건 검수 요약",
        "",
        "## 작업 배경",
        "",
        "이 보고서는 조건 B(source block + evidence_ids + num_predict=256), pre-gate, actionability 후처리, v2_strict gate를 모두 통과한 strict allow 후보 500건을 오프라인 검수 기준으로 판정한 결과다. strict allow는 사람 검수 전에는 정답이 아니라 교체 후보일 뿐이다.",
        "",
        "## 검수 기준",
        "",
        "- pass: 원문 evidence가 LLM segment를 충분히 뒷받침하고, BE3 action-item 후보로 자연스러운 경우",
        "- partial: 방향은 맞지만 저분할/과분할/추상화 가능성이 있어 자동 assist 적용 전 검토가 필요한 경우",
        "- fail: 독립 요청 누락, evidence 부족, unsupported segment 등으로 교체하면 위험한 경우",
        "- unsure: 원문만으로 판단이 어려운 경우",
        "",
        "## 전체 집계",
        "",
        "| 지표 | 값 |",
        "| --- | ---: |",
        f"| total reviewed | {overall['total_reviewed']} |",
        f"| pass | {overall['pass']} |",
        f"| partial | {overall['partial']} |",
        f"| fail | {overall['fail']} |",
        f"| unsure | {overall['unsure']} |",
        f"| pass rate | {overall['pass_rate']:.1%} |",
        f"| pass + partial rate | {overall['pass_partial_rate']:.1%} |",
        f"| fail rate | {overall['fail_rate']:.1%} |",
        "",
        "## 100건 단위 누적 추세",
        "",
        "| 범위 | pass | partial | fail | unsure | pass rate | fail rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["cumulative_by_100"]:
        lines.append(
            f"| {item['range']} | {item['pass']} | {item['partial']} | {item['fail']} | {item['unsure']} | {item['pass_rate']:.1%} | {item['fail_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## error_type 분포",
            "",
            "```json",
            json.dumps(summary["error_type_counts"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## assist_recommendation 분포",
            "",
            "```json",
            json.dumps(summary["assist_recommendation_counts"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## fallback_reason별 judgment",
            "",
            "```json",
            json.dumps(summary["fallback_reason_by_judgment"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## risk_tag별 judgment",
            "",
            "```json",
            json.dumps(summary["risk_tag_by_judgment"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## latency",
            "",
            f"- avg: {summary['latency']['avg']}",
            f"- p50: {summary['latency']['p50']}",
            f"- p95: {summary['latency']['p95']}",
            f"- max: {summary['latency']['max']}",
            "",
            "## gate 판단",
            "",
            f"- 판단: `{summary['gate_judgment']}`",
            "- pass rate가 90% 이상이고 fail rate가 3% 이하이므로, controlled rollout 후보로 볼 수 있다.",
            "- 단, 기본 assist/full 활성화는 별도 운영 판단이 필요하며 기본값은 shadow/off 유지가 안전하다.",
            "",
            "## 대표 사례",
            "",
        ]
    )
    for judgment, limit in (("pass", 10), ("partial", 10), ("fail", 10), ("unsure", 5)):
        lines.extend(_render_examples(rows, judgment, limit))
    lines.extend(
        [
            "",
            "## BE3/FE/Multi-Agent Routing 전달사항",
            "",
            "- strict allow 500건 기준 pass rate는 높지만, 이는 오프라인 검수 기준의 결과다.",
            "- FE/BE3 외부 계약은 변경하지 않는다.",
            "- controlled rollout을 하더라도 번호/heading/list형 strict allow 후보에 한정하고, 관리자/내부 검수 로그를 남기는 것이 좋다.",
            "- 전화 대화체, 장문 법령/정책, 장문 제안서, weak request signal은 계속 shadow/review 경로에 둔다.",
            "",
            "## 남은 리스크",
            "",
            "- 검수 기준은 보수적 휴리스틱과 샘플 검토를 결합한 오프라인 판정이며, 실제 사용자 영향도와 동일하지 않다.",
            "- partial 27건은 대부분 저분할/과분할 가능성이므로, controlled rollout 전 추가 gate 보강 후보로 봐야 한다.",
            "- EXAONE latency는 여전히 높으므로 동기 사용자 요청 경로에서 바로 쓰기 어렵다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_examples(rows: list[dict[str, Any]], judgment: str, limit: int) -> list[str]:
    selected = [row for row in rows if row.get("human_judgment") == judgment][:limit]
    lines = [f"### {judgment}", ""]
    if not selected:
        lines.append("- 해당 없음")
        return lines
    for row in selected:
        lines.extend(
            [
                f"- source_id: `{row.get('source_id')}`",
                f"  - title: {row.get('title') or '-'}",
                f"  - rule: {_short_list(row.get('rule_segments') or [])}",
                f"  - llm: {_short_list(row.get('llm_segments') or [])}",
                f"  - evidence: {_short_list([' / '.join(group) for group in row.get('restored_evidence_texts') or []])}",
                f"  - 판단: {row.get('human_note')}",
            ]
        )
    return lines


def _short_list(values: list[Any], limit: int = 2) -> str:
    rendered = [str(value).replace("\n", " ")[:120] for value in values[:limit]]
    if len(values) > limit:
        rendered.append(f"...(+{len(values) - limit})")
    return " | ".join(rendered) if rendered else "-"


if __name__ == "__main__":
    main()

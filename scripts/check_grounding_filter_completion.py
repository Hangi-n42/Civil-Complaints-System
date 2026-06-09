"""BE2 grounding filter completion gate.

This script does not call an LLM. It validates the committed evaluation and E2E
summaries that already contain the expensive grounding-filter measurements.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EFFECT_JSON = ROOT / "reports/retrieval/v3/grounding_filter_effect.json"
DEFAULT_E2E_JSON = ROOT / "reports/retrieval/v3/be3_handoff_e2e_summary.json"
DEFAULT_OUT_JSON = ROOT / "reports/retrieval/v3/grounding_filter_completion_check.json"
DEFAULT_OUT_MD = ROOT / "reports/retrieval/v3/grounding_filter_completion_check.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object가 아닙니다: {path}")
    return value


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _check(name: str, passed: bool, value: Any, threshold: Any, note: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "threshold": threshold,
        "note": note,
    }


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _display_path(path: str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    effect = _load_json(Path(args.effect_json))
    e2e = _load_json(Path(args.e2e_json))

    by_k = effect.get("by_k") if isinstance(effect.get("by_k"), dict) else {}
    topk_block = by_k.get(str(args.top_k))
    if not isinstance(topk_block, dict):
        raise ValueError(f"grounding filter effect에 top-k={args.top_k} 결과가 없습니다.")

    baseline = topk_block.get(args.baseline_variant)
    filtered = topk_block.get(args.filter_variant)
    if not isinstance(baseline, dict) or not isinstance(filtered, dict):
        raise ValueError("baseline/filter variant 결과를 찾을 수 없습니다.")

    baseline_harmful = _num(baseline.get("harmful_rate"))
    filtered_harmful = _num(filtered.get("harmful_rate"))
    relative_reduction = (
        (baseline_harmful - filtered_harmful) / baseline_harmful
        if baseline_harmful > 0
        else 0.0
    )
    n_queries = int(_num(filtered.get("n_queries")))
    empty_queries = int(_num(filtered.get("queries_empty_grounding")))
    empty_pct = empty_queries / n_queries if n_queries else 0.0

    run = e2e.get("run") if isinstance(e2e.get("run"), dict) else {}
    summary = e2e.get("summary") if isinstance(e2e.get("summary"), dict) else {}
    conclusion = e2e.get("conclusion") if isinstance(e2e.get("conclusion"), dict) else {}

    checks = [
        _check(
            "filter_eval_query_count",
            n_queries >= args.min_eval_queries,
            n_queries,
            f">= {args.min_eval_queries}",
            "정량 평가는 최소 쿼리 수 이상이어야 합니다.",
        ),
        _check(
            "harmful_rate_topk",
            filtered_harmful <= args.max_harmful_rate,
            round(filtered_harmful, 4),
            f"<= {args.max_harmful_rate}",
            "필터 후 top-k rel0 비율입니다.",
        ),
        _check(
            "queries_with_harmful_topk",
            _num(filtered.get("queries_with_harmful_pct")) <= args.max_queries_with_harmful_pct,
            round(_num(filtered.get("queries_with_harmful_pct")), 4),
            f"<= {args.max_queries_with_harmful_pct}",
            "필터 후 rel0가 1개 이상 남은 쿼리 비율입니다.",
        ),
        _check(
            "useful_rate_topk",
            _num(filtered.get("useful_rate")) >= args.min_useful_rate,
            round(_num(filtered.get("useful_rate")), 4),
            f">= {args.min_useful_rate}",
            "필터 후 rel>=1 근거 비율입니다.",
        ),
        _check(
            "relative_harmful_reduction",
            relative_reduction >= args.min_relative_reduction,
            round(relative_reduction, 4),
            f">= {args.min_relative_reduction}",
            "원본 Hybrid 대비 rel0 제거율입니다.",
        ),
        _check(
            "empty_grounding_fallback_budget",
            empty_pct <= args.max_empty_grounding_pct,
            round(empty_pct, 4),
            f"<= {args.max_empty_grounding_pct}",
            "필터 결과 0건이 되는 쿼리 비율입니다. 0건은 no-evidence fallback 대상입니다.",
        ),
        _check(
            "e2e_sample_count",
            int(_num(run.get("sample_count"))) >= args.min_e2e_samples,
            int(_num(run.get("sample_count"))),
            f">= {args.min_e2e_samples}",
            "실제 BE1->BE2->BE3 연결 smoke 샘플 수입니다.",
        ),
        _check(
            "e2e_grounding_filter_enabled",
            bool(run.get("grounding_filter")) is True,
            bool(run.get("grounding_filter")),
            True,
            "최종 E2E가 grounding_filter=True로 실행됐는지 확인합니다.",
        ),
        _check(
            "e2e_grounding_errors",
            int(_num(summary.get("grounding_error_count"))) == 0,
            int(_num(summary.get("grounding_error_count"))),
            0,
            "실제 E2E에서 grounding filter 오류가 없어야 합니다.",
        ),
        _check(
            "e2e_empty_answers",
            int(_num(summary.get("generation_empty_answer_count"))) == 0,
            int(_num(summary.get("generation_empty_answer_count"))),
            0,
            "필터 적용 후 QA 생성에서 빈 답변이 없어야 합니다.",
        ),
        _check(
            "e2e_search_path",
            conclusion.get("be2_search_path") == "통과",
            conclusion.get("be2_search_path"),
            "통과",
            "BE2 검색 경로 최종 E2E 판단입니다.",
        ),
        _check(
            "e2e_grounding_path",
            conclusion.get("grounding_filter_path") == "통과",
            conclusion.get("grounding_filter_path"),
            "통과",
            "grounding filter 경로 최종 E2E 판단입니다.",
        ),
    ]

    overall_passed = all(item["passed"] for item in checks)
    return {
        "title": "BE2 grounding filter completion check",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if overall_passed else "failed",
        "inputs": {
            "effect_json": _display_path(args.effect_json),
            "e2e_json": _display_path(args.e2e_json),
            "baseline_variant": args.baseline_variant,
            "filter_variant": args.filter_variant,
            "top_k": args.top_k,
        },
        "thresholds": {
            "min_eval_queries": args.min_eval_queries,
            "max_harmful_rate": args.max_harmful_rate,
            "max_queries_with_harmful_pct": args.max_queries_with_harmful_pct,
            "min_useful_rate": args.min_useful_rate,
            "min_relative_reduction": args.min_relative_reduction,
            "max_empty_grounding_pct": args.max_empty_grounding_pct,
            "min_e2e_samples": args.min_e2e_samples,
        },
        "metrics": {
            "baseline_harmful_rate": round(baseline_harmful, 4),
            "filtered_harmful_rate": round(filtered_harmful, 4),
            "relative_harmful_reduction": round(relative_reduction, 4),
            "filtered_useful_rate": round(_num(filtered.get("useful_rate")), 4),
            "filtered_queries_with_harmful_pct": round(
                _num(filtered.get("queries_with_harmful_pct")), 4
            ),
            "filtered_empty_grounding_pct": round(empty_pct, 4),
            "filtered_empty_grounding_queries": empty_queries,
            "filtered_avg_filled_slots": filtered.get("avg_filled_slots"),
            "e2e_sample_count": int(_num(run.get("sample_count"))),
            "e2e_grounding_error_count": int(_num(summary.get("grounding_error_count"))),
            "e2e_generation_empty_answer_count": int(
                _num(summary.get("generation_empty_answer_count"))
            ),
            "e2e_generation_fallback_count": int(_num(summary.get("generation_fallback_count"))),
        },
        "checks": checks,
        "conclusion": {
            "be2_grounding_filter_completion": "완료" if overall_passed else "미완료",
            "note": (
                "엉뚱한 근거 제거 기준은 통과했습니다. 법령 grounding fast_fallback은 "
                "BE3 생성 안정성 후속 리스크로 별도 관리합니다."
                if overall_passed
                else "하나 이상의 gate가 실패했습니다. checks를 확인해야 합니다."
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    checks = report["checks"]
    status = "통과" if report["status"] == "passed" else "실패"
    lines = [
        "# BE2 엉뚱한 근거 제거 완료 체크",
        "",
        f"- 생성 시각(UTC): `{report['generated_at']}`",
        f"- 전체 결과: **{status}**",
        f"- 판정: **{report['conclusion']['be2_grounding_filter_completion']}**",
        "",
        "## 핵심 수치",
        "",
        "| 항목 | 값 |",
        "| --- | ---: |",
        f"| 원본 Hybrid rel0 비율 | {_pct(metrics['baseline_harmful_rate'])} |",
        f"| 필터 후 rel0 비율 | {_pct(metrics['filtered_harmful_rate'])} |",
        f"| rel0 상대 감소율 | {_pct(metrics['relative_harmful_reduction'])} |",
        f"| 필터 후 유효 근거 비율(rel>=1) | {_pct(metrics['filtered_useful_rate'])} |",
        f"| rel0가 남은 쿼리 비율 | {_pct(metrics['filtered_queries_with_harmful_pct'])} |",
        f"| 필터 결과 0건 쿼리 비율 | {_pct(metrics['filtered_empty_grounding_pct'])} |",
        f"| 필터 결과 0건 쿼리 수 | {metrics['filtered_empty_grounding_queries']} |",
        f"| 평균 근거 수 | {metrics['filtered_avg_filled_slots']} |",
        f"| 최종 E2E 샘플 수 | {metrics['e2e_sample_count']} |",
        f"| 최종 E2E grounding 오류 | {metrics['e2e_grounding_error_count']} |",
        f"| 최종 E2E 빈 답변 | {metrics['e2e_generation_empty_answer_count']} |",
        "",
        "## Gate",
        "",
        "| Gate | 결과 | 값 | 기준 |",
        "| --- | --- | ---: | --- |",
    ]
    for item in checks:
        result = "통과" if item["passed"] else "실패"
        lines.append(
            f"| `{item['name']}` | {result} | {item['value']} | {item['threshold']} |"
        )

    lines.extend(
        [
            "",
            "## 판단",
            "",
            report["conclusion"]["note"],
            "",
            "## 운영 해석",
            "",
            "- 필터 결과 0건은 검색 실패가 아니라 안전 fallback 대상이다.",
            "- `/qa`는 근거가 없을 때 `no_evidence_fallback`으로 가짜 근거 생성을 피해야 한다.",
            "- 법령 grounding이 붙은 케이스의 `fast_fallback`은 BE2 검색 실패가 아니라 BE3 생성 안정성 지표로 분리한다.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BE2 grounding filter completion gate")
    parser.add_argument("--effect-json", default=str(DEFAULT_EFFECT_JSON))
    parser.add_argument("--e2e-json", default=str(DEFAULT_E2E_JSON))
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--baseline-variant", default="Hybrid")
    parser.add_argument("--filter-variant", default="Hybrid+LLM-filter")
    parser.add_argument("--min-eval-queries", type=int, default=100)
    parser.add_argument("--max-harmful-rate", type=float, default=0.05)
    parser.add_argument("--max-queries-with-harmful-pct", type=float, default=0.15)
    parser.add_argument("--min-useful-rate", type=float, default=0.95)
    parser.add_argument("--min-relative-reduction", type=float, default=0.80)
    parser.add_argument("--max-empty-grounding-pct", type=float, default=0.10)
    parser.add_argument("--min-e2e-samples", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"status={report['status']}")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    if report["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()

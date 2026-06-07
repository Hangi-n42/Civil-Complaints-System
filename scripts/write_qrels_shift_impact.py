"""기존 qrels 평가와 strong-audit qrels 평가의 영향 비교 리포트를 작성한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BASE = ROOT / "reports" / "retrieval" / "v3" / "metadata_soft_rerank_eval.json"
DEFAULT_AUDITED = ROOT / "reports" / "retrieval" / "v3" / "metadata_soft_rerank_eval_strong_audit.json"
DEFAULT_OUT = ROOT / "reports" / "retrieval" / "v3" / "qrels_shift_impact.md"
METRICS = ["nDCG@5", "nDCG@10", "P@5", "R@10"]


def get_metric(metrics: dict[str, Any], key: str) -> float:
    for name, value in metrics.items():
        if name.lower() == key.lower():
            return float(value)
    return 0.0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_rows(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    systems = report["general_search"]["systems"]
    hybrid = systems["Hybrid"]
    meta = systems["Hybrid+metadata_soft_rerank"]
    return {
        key: {
            "hybrid": get_metric(hybrid, key),
            "metadata": get_metric(meta, key),
            "delta": get_metric(meta, key) - get_metric(hybrid, key),
        }
        for key in METRICS
    }


def grounding_rows(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    systems = report["grounding"]["systems"]
    out: dict[str, dict[str, float]] = {}
    for name in ["Hybrid", "Hybrid+metadata_soft_rerank", "Hybrid+metadata_soft_rerank+LLM_filter_cache_projection"]:
        row = systems[name]
        out[name] = {
            "rel0_rate": float(row["rel0_rate"]),
            "harmful_query_rate": float(row["harmful_query_rate"]),
            "empty_result_rate": float(row["empty_result_rate"]),
            "avg_filled": float(row["avg_filled"]),
        }
    return out


def stable_conclusions(base: dict[str, Any], audited: dict[str, Any]) -> tuple[list[str], list[str]]:
    base_delta = base["general_search"]["delta"]
    audited_delta = audited["general_search"]["delta"]
    kept: list[str] = []
    changed: list[str] = []

    if audited_delta.get("nDCG@10", 0) >= 0 and audited_delta.get("R@10", 0) >= 0:
        kept.append("metadata soft rerank는 strong-audit qrels에서도 일반 검색 지표를 악화시키지 않았다.")
    else:
        changed.append("metadata soft rerank의 일반 검색 개선 신호가 strong-audit qrels에서 약해지거나 뒤집혔다.")

    if audited_delta.get("P@5", 0) >= -0.001:
        kept.append("P@5는 strong-audit qrels에서도 크게 하락하지 않았다.")
    else:
        changed.append("P@5가 strong-audit qrels에서 의미 있게 하락했다.")

    base_g = base["grounding"]["systems"]
    audited_g = audited["grounding"]["systems"]
    if audited_g["Hybrid+metadata_soft_rerank"]["rel0_rate"] >= audited_g["Hybrid"]["rel0_rate"]:
        kept.append("metadata soft rerank 단독으로 grounding rel0를 줄인다는 결론은 여전히 없다.")
    else:
        changed.append("strong-audit qrels에서는 metadata soft rerank가 grounding rel0를 줄이는 신호가 생겼다.")

    if audited_g["Hybrid+metadata_soft_rerank+LLM_filter_cache_projection"]["rel0_rate"] < audited_g["Hybrid+metadata_soft_rerank"]["rel0_rate"]:
        kept.append("답변 초안 grounding에는 LLM relevance filter가 여전히 필요하다.")
    else:
        changed.append("strong-audit qrels에서 LLM filter의 rel0 감소 효과가 약해졌다.")

    if not changed:
        changed.append("현재 비교에서는 핵심 결론이 뒤집힌 항목이 없다.")
    return kept, changed


def write_report(base: dict[str, Any], audited: dict[str, Any], out_path: Path) -> None:
    base_metrics = metric_rows(base)
    audited_metrics = metric_rows(audited)
    base_grounding = grounding_rows(base)
    audited_grounding = grounding_rows(audited)
    kept, changed = stable_conclusions(base, audited)

    lines = [
        "# qrels 변화 영향 리포트",
        "",
        "## 결론",
        "",
        "기존 `v3_local_3judge` qrels와 `strong-audit` qrels 기준 평가를 나란히 비교한다.",
        "",
        "### 유지된 결론",
        "",
    ]
    lines.extend(f"- {item}" for item in kept)
    lines.extend(["", "### 바뀌었거나 재검토할 결론", ""])
    lines.extend(f"- {item}" for item in changed)

    lines.extend([
        "",
        "## 일반 검색 지표",
        "",
        "| 지표 | 기존 Hybrid | 기존 Hybrid+metadata | 기존 변화 | 감사 Hybrid | 감사 Hybrid+metadata | 감사 변화 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for key in METRICS:
        b = base_metrics[key]
        a = audited_metrics[key]
        lines.append(
            f"| {key} | {b['hybrid']:.4f} | {b['metadata']:.4f} | {b['delta']:+.4f} | "
            f"{a['hybrid']:.4f} | {a['metadata']:.4f} | {a['delta']:+.4f} |"
        )

    lines.extend([
        "",
        "## 답변 초안 grounding 지표",
        "",
        "| 방법 | 기존 rel0 | 감사 rel0 | 기존 harmful query | 감사 harmful query | 기존 빈 결과 | 감사 빈 결과 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name in ["Hybrid", "Hybrid+metadata_soft_rerank", "Hybrid+metadata_soft_rerank+LLM_filter_cache_projection"]:
        b = base_grounding[name]
        a = audited_grounding[name]
        lines.append(
            f"| {name} | {b['rel0_rate']:.4f} | {a['rel0_rate']:.4f} | "
            f"{b['harmful_query_rate']:.4f} | {a['harmful_query_rate']:.4f} | "
            f"{b['empty_result_rate']:.4f} | {a['empty_result_rate']:.4f} |"
        )

    lines.extend([
        "",
        "## 해석 원칙",
        "",
        "- 기존 지표는 `v3_local_3judge` 기준 baseline snapshot으로 보존한다.",
        "- strong-audit 지표는 강화된 rubric과 강한 LLM 감사 기준의 재평가 결과다.",
        "- 두 평가셋에서 같은 방향으로 반복되는 결론만 안정적인 결론으로 본다.",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="qrels shift impact 리포트 작성")
    parser.add_argument("--base-eval", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--audited-eval", type=Path, default=DEFAULT_AUDITED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    base_eval = args.base_eval if args.base_eval.is_absolute() else ROOT / args.base_eval
    audited_eval = args.audited_eval if args.audited_eval.is_absolute() else ROOT / args.audited_eval
    out = args.out if args.out.is_absolute() else ROOT / args.out
    write_report(load_json(base_eval), load_json(audited_eval), out)
    print(f"[report] {out}")


if __name__ == "__main__":
    main()

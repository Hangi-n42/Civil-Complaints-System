"""Evaluate BE1 metadata soft rerank on the metadata-overlay Chroma collection."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord, sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run, per_query_metric
from app.retrieval.service import RetrievalService
from scripts.e2e_be1_query_signals_search_qa import (
    build_deterministic_structuring,
    extract_query_signals,
)


DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "civil_cases_v1_be1_metadata_v1_soft_rerank_eval.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "civil_cases_v1_be1_metadata_v1_soft_rerank_eval.md"
METRIC_ORDER = ["nDCG@5", "nDCG@10", "R@5", "R@10", "RR@5", "RR@10", "AP@10", "P@5"]
SIGNAL_FIELDS = [
    "entity_texts",
    "legal_ref_names",
    "legal_ref_ids",
    "key_terms",
    "responsible_units",
]


def load_queries(path: Path, *, limit: int = 0) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            qid = str(row.get("query_id") or row.get("qid") or row.get("id") or "").strip()
            query = str(row.get("query") or row.get("text") or "").strip()
            if not qid or not query:
                raise ValueError(f"{path} {line_number}번째 줄에 query_id 또는 query가 없습니다")
            queries.append(row | {"query_id": qid, "query": query})
            if limit > 0 and len(queries) >= limit:
                break
    return queries


def load_qrels(path: Path) -> list[QrelRecord]:
    qrels: list[QrelRecord] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if line_number == 1 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) >= 4:
                qid, _, docid, relevance = parts[:4]
            elif len(parts) >= 3:
                qid, docid, relevance = parts[:3]
            else:
                raise ValueError(f"{path} {line_number}번째 줄 형식이 올바르지 않습니다: {raw!r}")
            qrels.append(QrelRecord(qid=qid, docid=docid, relevance=int(relevance)))
    return qrels


def _query_signal_payload(query: dict[str, Any]) -> dict[str, Any]:
    structured = build_deterministic_structuring(
        {
            "case_id": query["query_id"],
            "text": query["query"],
            "category": query.get("category", ""),
            "source": query.get("source", ""),
        }
    )
    return extract_query_signals(structured)


def build_query_signals(queries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {query["query_id"]: _query_signal_payload(query) for query in queries}


def signal_coverage(query_signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    field_counts: dict[str, int] = {}
    field_value_counts: dict[str, int] = {}
    any_count = 0
    for signals in query_signals.values():
        has_any = False
        for field in SIGNAL_FIELDS:
            values = signals.get(field) or []
            if values:
                has_any = True
                field_counts[field] = field_counts.get(field, 0) + 1
                field_value_counts[field] = field_value_counts.get(field, 0) + len(values)
        if has_any:
            any_count += 1
    return {
        "query_count": len(query_signals),
        "queries_with_any_signal": any_count,
        "queries_with_field": field_counts,
        "value_count_by_field": field_value_counts,
    }


def _case_id_from_result(item: dict[str, Any]) -> str:
    case_id = str(item.get("case_id") or item.get("doc_id") or "").strip()
    if case_id:
        return case_id
    chunk_id = str(item.get("chunk_id") or "").strip()
    if "__chunk-" in chunk_id:
        return chunk_id.split("__chunk-", 1)[0]
    return chunk_id


def dedup_results(items: list[dict[str, Any]], *, top_k: int) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for item in items:
        case_id = _case_id_from_result(item)
        if not case_id:
            continue
        score = float(item.get("score") or 0.0)
        if case_id not in best or score > best[case_id]:
            best[case_id] = score
    return sorted(best.items(), key=lambda row: row[1], reverse=True)[:top_k]


def build_run(qid: str, hits: list[tuple[str, float]]) -> list[RunRecord]:
    return [
        RunRecord(qid=qid, docid=case_id, score=score, rank=rank)
        for rank, (case_id, score) in enumerate(hits, start=1)
    ]


async def run_service_variant(
    *,
    service: RetrievalService,
    queries: list[dict[str, Any]],
    query_signals: dict[str, dict[str, Any]],
    collection: str,
    strategy: str,
    top_k: int,
    use_soft_rerank: bool,
) -> tuple[dict[str, list[RunRecord]], dict[str, Any]]:
    started = time.perf_counter()
    runs: dict[str, list[RunRecord]] = {}
    top1_by_query: dict[str, str] = {}
    empty_count = 0
    for index, query in enumerate(queries, start=1):
        qid = query["query_id"]
        results = await service.search(
            query=query["query"],
            top_k=top_k,
            collection_name=collection,
            strategy=strategy,
            grounding_filter=False,
            query_signals=query_signals.get(qid) if use_soft_rerank else None,
        )
        hits = dedup_results(results, top_k=top_k)
        if not hits:
            empty_count += 1
        runs[qid] = build_run(qid, hits)
        top1_by_query[qid] = hits[0][0] if hits else ""
        if index % 10 == 0:
            label = "soft" if use_soft_rerank else "base"
            print(f"[{strategy}:{label}] {index}/{len(queries)}")
    elapsed = time.perf_counter() - started
    return runs, {
        "elapsed_sec": elapsed,
        "query_per_sec": len(queries) / elapsed if elapsed > 0 else 0.0,
        "empty_count": empty_count,
        "top1_by_query": top1_by_query,
    }


def flatten_runs(runs: dict[str, list[RunRecord]]) -> list[RunRecord]:
    return [record for records in runs.values() for record in records]


def ordered_metric_keys(*metric_sets: dict[str, float]) -> list[str]:
    all_keys = {key for metric_set in metric_sets for key in metric_set}
    ordered = [key for key in METRIC_ORDER if key in all_keys]
    return ordered + sorted(all_keys - set(ordered))


def compare_per_query(
    qrels: list[QrelRecord],
    baseline_run: list[RunRecord],
    candidate_run: list[RunRecord],
) -> dict[str, Any]:
    baseline = per_query_metric(qrels, baseline_run)
    candidate = per_query_metric(qrels, candidate_run)
    rows = []
    for qid in sorted(set(baseline) | set(candidate)):
        before = baseline.get(qid, 0.0)
        after = candidate.get(qid, 0.0)
        rows.append(
            {
                "query_id": qid,
                "baseline_nDCG@10": before,
                "soft_rerank_nDCG@10": after,
                "delta_nDCG@10": after - before,
            }
        )
    epsilon = 1e-9
    return {
        "summary": {
            "total": len(rows),
            "improved": sum(1 for row in rows if row["delta_nDCG@10"] > epsilon),
            "tied": sum(1 for row in rows if abs(row["delta_nDCG@10"]) <= epsilon),
            "regressed": sum(1 for row in rows if row["delta_nDCG@10"] < -epsilon),
        },
        "top_improvements": [
            row
            for row in sorted(rows, key=lambda row: row["delta_nDCG@10"], reverse=True)
            if row["delta_nDCG@10"] > epsilon
        ][:10],
        "top_regressions": [
            row
            for row in sorted(rows, key=lambda row: row["delta_nDCG@10"])
            if row["delta_nDCG@10"] < -epsilon
        ][:10],
        "rows": rows,
    }


def _metric_deltas(base: dict[str, float], soft: dict[str, float], keys: list[str]) -> dict[str, float]:
    return {key: soft.get(key, 0.0) - base.get(key, 0.0) for key in keys}


def _top1_change(base_stat: dict[str, Any], soft_stat: dict[str, Any]) -> dict[str, int]:
    before = base_stat["top1_by_query"]
    after = soft_stat["top1_by_query"]
    qids = set(before) | set(after)
    return {
        "total": len(qids),
        "changed": sum(1 for qid in qids if before.get(qid) != after.get(qid)),
    }


def _strip_runtime_stat(stat: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in stat.items() if key != "top1_by_query"}


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# BE1 Metadata Overlay Soft Rerank 평가",
        "",
        "## 요약",
        "",
        f"- 컬렉션: `{payload['collection']}`",
        f"- 검색 실행 쿼리: {payload['query_count']}건",
        f"- qrels 보유 쿼리: {payload['judged_query_count']}건",
        f"- qrels: `{payload['qrels_path']}` (전체 {payload['qrel_count']}개 라벨, 평가 사용 {payload['evaluated_qrel_count']}개 라벨, {payload['qrels_sha256']})",
        f"- Top-K: {payload['top_k']}",
        f"- query signal 생성: `{payload['query_signal_source']}`",
        f"- query signal 보유 쿼리: {payload['query_signal_coverage']['queries_with_any_signal']}건 / {payload['query_count']}건",
        "",
    ]

    for strategy_name, result in payload["strategies"].items():
        base = result["metrics"]["baseline"]
        soft = result["metrics"]["soft_rerank"]
        deltas = result["metric_deltas"]
        lines.extend(
            [
                f"## {strategy_name.upper()} 검색",
                "",
                "| 지표 | baseline | soft rerank | 변화 |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for key in result["metric_keys"]:
            lines.append(f"| {key} | {_fmt(base.get(key, 0.0))} | {_fmt(soft.get(key, 0.0))} | {deltas[key]:+.4f} |")

        pq = result["per_query_nDCG@10"]["summary"]
        top1 = result["top1_comparison"]
        lines.extend(
            [
                "",
                "### 쿼리별 nDCG@10 변화",
                "",
                f"- 비교 대상: {pq['total']}건",
                f"- 개선: {pq['improved']}건",
                f"- 동일: {pq['tied']}건",
                f"- 하락: {pq['regressed']}건",
                f"- Top-1 결과 변경: {top1['changed']}건 / {top1['total']}건",
                "",
                "### 하락 상위",
                "",
                "| query_id | baseline | soft rerank | 변화 |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        regressions = result["per_query_nDCG@10"]["top_regressions"]
        if regressions:
            for row in regressions:
                lines.append(
                    "| {query_id} | {baseline_nDCG@10:.4f} | {soft_rerank_nDCG@10:.4f} | {delta_nDCG@10:+.4f} |".format(
                        **row
                    )
                )
        else:
            lines.append("| - | - | - | - |")
        lines.append("")

    dense_delta = payload["strategies"].get("dense", {}).get("metric_deltas", {})
    hybrid_delta = payload["strategies"].get("hybrid", {}).get("metric_deltas", {})
    lines.extend(
        [
            "## 판단",
            "",
            "- 이 평가는 BE1 metadata를 hard filter가 아니라 약한 점수 boost로만 사용한다.",
            "- 쿼리 원문과 검색 snippet은 산출물에 포함하지 않았다.",
            (
                f"- Dense `nDCG@10` 변화는 {dense_delta.get('nDCG@10', 0.0):+.4f}, "
                f"`R@10` 변화는 {dense_delta.get('R@10', 0.0):+.4f}이다."
            ),
            (
                f"- Hybrid `nDCG@10` 변화는 {hybrid_delta.get('nDCG@10', 0.0):+.4f}, "
                f"`R@10` 변화는 {hybrid_delta.get('R@10', 0.0):+.4f}이다."
            ),
            "- 따라서 현재 가중치의 metadata soft rerank는 기본 활성화하지 않는다.",
            "- `civil_cases_v1_be1_metadata_v1` 컬렉션 전환과 soft rerank 활성화는 분리해서 판단한다.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="civil_cases_v1_be1_metadata_v1")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    queries = load_queries(args.queries, limit=max(0, args.limit))
    qrels = load_qrels(args.qrels)
    query_ids = {query["query_id"] for query in queries}
    eval_qrels = [row for row in qrels if row.qid in query_ids]
    query_signals = build_query_signals(queries)
    judged_query_count = len({row.qid for row in eval_qrels})

    service = RetrievalService()
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "queries_path": args.queries.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "qrels_path": args.qrels.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "queries_sha256": sha256_file(args.queries),
        "qrels_sha256": sha256_file(args.qrels),
        "query_count": len(queries),
        "judged_query_count": judged_query_count,
        "qrel_count": len(qrels),
        "evaluated_qrel_count": len(eval_qrels),
        "top_k": args.top_k,
        "query_signal_source": "deterministic BE1 search-signal extraction from evaluation query text",
        "query_signal_coverage": signal_coverage(query_signals),
        "strategies": {},
    }

    for strategy in args.strategies:
        print(f"[{strategy}] baseline")
        baseline_runs, baseline_stat = await run_service_variant(
            service=service,
            queries=queries,
            query_signals=query_signals,
            collection=args.collection,
            strategy=strategy,
            top_k=args.top_k,
            use_soft_rerank=False,
        )
        print(f"[{strategy}] soft rerank")
        soft_runs, soft_stat = await run_service_variant(
            service=service,
            queries=queries,
            query_signals=query_signals,
            collection=args.collection,
            strategy=strategy,
            top_k=args.top_k,
            use_soft_rerank=True,
        )
        baseline_flat = flatten_runs(baseline_runs)
        soft_flat = flatten_runs(soft_runs)
        baseline_metrics = evaluate_run(eval_qrels, baseline_flat)
        soft_metrics = evaluate_run(eval_qrels, soft_flat)
        metric_keys = ordered_metric_keys(baseline_metrics, soft_metrics)
        payload["strategies"][strategy] = {
            "metric_keys": metric_keys,
            "metrics": {
                "baseline": baseline_metrics,
                "soft_rerank": soft_metrics,
            },
            "metric_deltas": _metric_deltas(baseline_metrics, soft_metrics, metric_keys),
            "per_query_nDCG@10": compare_per_query(eval_qrels, baseline_flat, soft_flat),
            "top1_comparison": _top1_change(baseline_stat, soft_stat),
            "runtime": {
                "baseline": _strip_runtime_stat(baseline_stat),
                "soft_rerank": _strip_runtime_stat(soft_stat),
            },
            "sample_run_records": {
                "baseline": [asdict(record) for record in baseline_flat[:20]],
                "soft_rerank": [asdict(record) for record in soft_flat[:20]],
            },
        }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"[WRITE] {args.out_json}")
    print(f"[WRITE] {args.out_md}")


def main() -> None:
    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()

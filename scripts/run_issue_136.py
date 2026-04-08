"""Issue #136 runner: filter/top-k combination benchmark and baseline selection.

Measures retrieval quality/latency by running a matrix of top-k values and metadata filters
against the Week3 evaluation set, then selects a recommended baseline configuration.

Usage:
  c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe scripts/run_issue_136.py \
    --eval-set docs/40_delivery/week3/model_test_assets/evaluation_set.json \
    --output logs/evaluation/week4_issue136_baseline_report.json \
    --markdown-output logs/evaluation/week4_issue136_baseline_report.md \
    --collection civil_cases_v1 --device cpu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings


@dataclass
class QueryCase:
    query_id: str
    query_text: str
    ground_truth: Set[str]


@dataclass
class ComboAggregate:
    combo_name: str
    top_k: int
    filter_name: str
    where: Optional[Dict[str, Any]]
    query_count: int
    recall_at_5: float
    recall_at_10: float
    mrr_at_5: float
    mrr_at_10: float
    precision_at_5: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #136 filter/top-k baseline runner")
    parser.add_argument("--eval-set", type=str, required=True, help="Path to evaluation_set.json")
    parser.add_argument("--output", type=str, required=True, help="Path to output json report")
    parser.add_argument("--markdown-output", type=str, default="", help="Optional markdown summary output")
    parser.add_argument("--collection", type=str, default="civil_cases_v1", help="Chroma collection name")
    parser.add_argument("--persist-dir", type=str, default=settings.CHROMA_DB_PATH, help="Chroma persist directory")
    parser.add_argument("--embed-model", type=str, default="BAAI/bge-m3", help="Embedding model name")
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda"], help="Embedding device")
    parser.add_argument("--top-k-values", type=str, default="3,5,10,15", help="Comma-separated top-k values")
    parser.add_argument("--sample-size", type=int, default=0, help="Sample query count (0 means all)")
    parser.add_argument(
        "--filter-categories",
        type=str,
        default="road_safety,facility,welfare,traffic",
        help="Comma-separated category values for category-based filters",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_eval_set(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("evaluation_set must be a list")
    return payload


def _extract_queries(cases: List[Dict[str, Any]], sample_size: int = 0) -> List[QueryCase]:
    out: List[QueryCase] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        query_id = str(case.get("case_id") or "unknown")
        query_text = str(case.get("query") or "").strip()
        if not query_text:
            continue

        ground_truth: Set[str] = set()
        for ctx in case.get("context") or []:
            if isinstance(ctx, dict):
                chunk_id = str(ctx.get("chunk_id") or "").strip()
                if chunk_id:
                    ground_truth.add(chunk_id)

        if not ground_truth:
            continue
        out.append(QueryCase(query_id=query_id, query_text=query_text, ground_truth=ground_truth))

    if sample_size > 0 and len(out) > sample_size:
        import random

        random.seed(42)
        out = random.sample(out, sample_size)

    return out


def _initialize_chroma(persist_dir: str, collection_name: str):
    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(name=collection_name)
    return client, collection


def _initialize_embedding_model(model_name: str, device: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def _calculate_recall(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    if not ground_truth:
        return 0.0
    top_k = set(retrieved_chunks[:k])
    return len(top_k & ground_truth) / len(ground_truth)


def _calculate_mrr(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    for rank, chunk_id in enumerate(retrieved_chunks[:k], start=1):
        if chunk_id in ground_truth:
            return 1.0 / rank
    return 0.0


def _calculate_precision(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    if k == 0:
        return 0.0
    top_k = set(retrieved_chunks[:k])
    return len(top_k & ground_truth) / k


def _parse_top_k_values(text: str) -> List[int]:
    values: List[int] = []
    for item in text.split(","):
        s = item.strip()
        if not s:
            continue
        value = int(s)
        if value <= 0:
            continue
        values.append(value)
    uniq = sorted(set(values))
    if not uniq:
        raise ValueError("No valid top-k values were provided")
    return uniq


def _collect_created_at_stats(collection, sample_limit: int = 5000) -> Tuple[Optional[int], Optional[int]]:
    payload = collection.get(include=["metadatas"], limit=sample_limit)
    rows = payload.get("metadatas") or []
    created_values: List[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("created_at")
        try:
            created_values.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not created_values:
        return None, None
    return min(created_values), max(created_values)


def _build_filters(
    categories: Iterable[str],
    created_min: Optional[int],
    created_max: Optional[int],
) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    filters: List[Tuple[str, Optional[Dict[str, Any]]]] = [("no_filter", None), ("region_unknown", {"region": "unknown"})]

    for category in categories:
        name = f"category_{category}"
        filters.append((name, {"category": category}))

    if created_min is not None and created_max is not None and created_max >= created_min:
        midpoint = created_min + ((created_max - created_min) // 2)
        filters.append(("date_range_full", {"$and": [{"created_at": {"$gte": created_min}}, {"created_at": {"$lte": created_max}}]}))
        filters.append(("date_from_mid", {"created_at": {"$gte": midpoint}}))

    return filters


def _score_combo(row: ComboAggregate) -> Tuple[float, float, float]:
    # Priority: quality first, then latency.
    return (row.recall_at_5, row.mrr_at_5, -row.avg_latency_ms)


def _markdown_summary(
    report: Dict[str, Any],
    combos: List[ComboAggregate],
    recommended: ComboAggregate,
) -> str:
    lines: List[str] = []
    lines.append("# Issue #136 Baseline Report")
    lines.append("")
    lines.append(f"- generated_at: {report['generated_at']}")
    lines.append(f"- eval_set: {report['input']['eval_set']}")
    lines.append(f"- collection: {report['input']['collection']}")
    lines.append(f"- query_count: {report['input']['query_count']}")
    lines.append("")
    lines.append("## Recommended Baseline")
    lines.append("")
    lines.append(f"- combo: {recommended.combo_name}")
    lines.append(f"- recall_at_5: {recommended.recall_at_5:.4f}")
    lines.append(f"- mrr_at_5: {recommended.mrr_at_5:.4f}")
    lines.append(f"- avg_latency_ms: {recommended.avg_latency_ms:.2f}")
    lines.append("")
    lines.append("## Combination Metrics")
    lines.append("")
    lines.append("| combo | recall@5 | recall@10 | mrr@5 | precision@5 | avg_latency_ms |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in sorted(combos, key=_score_combo, reverse=True):
        lines.append(
            f"| {row.combo_name} | {row.recall_at_5:.4f} | {row.recall_at_10:.4f} | {row.mrr_at_5:.4f} | {row.precision_at_5:.4f} | {row.avg_latency_ms:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = Path(args.markdown_output) if args.markdown_output else None
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)

    top_k_values = _parse_top_k_values(args.top_k_values)
    filter_categories = [x.strip() for x in args.filter_categories.split(",") if x.strip()]

    print("[*] Issue #136 filter/top-k benchmark start")

    eval_set = _load_eval_set(Path(args.eval_set))
    queries = _extract_queries(eval_set, args.sample_size)
    if not queries:
        raise RuntimeError("No valid queries extracted from evaluation set")

    print(f"[*] loaded queries={len(queries)}")
    print(f"[*] loading Chroma collection={args.collection}")
    _, collection = _initialize_chroma(args.persist_dir, args.collection)

    created_min, created_max = _collect_created_at_stats(collection)
    filters = _build_filters(filter_categories, created_min, created_max)

    print(f"[*] loading embedding model={args.embed_model} device={args.device}")
    model = _initialize_embedding_model(args.embed_model, args.device)

    query_texts = [q.query_text for q in queries]
    query_embeddings = model.encode(query_texts, batch_size=64, show_progress_bar=True)
    query_embeddings = [emb.tolist() for emb in query_embeddings]

    combos: List[ComboAggregate] = []
    total_combo_count = len(top_k_values) * len(filters)
    combo_index = 0

    for top_k in top_k_values:
        for filter_name, where in filters:
            combo_index += 1
            combo_name = f"topk{top_k}__{filter_name}"
            latencies: List[float] = []
            recall_5_sum = 0.0
            recall_10_sum = 0.0
            mrr_5_sum = 0.0
            mrr_10_sum = 0.0
            precision_5_sum = 0.0

            for idx, query in enumerate(queries):
                start = time.perf_counter()
                result = collection.query(
                    query_embeddings=[query_embeddings[idx]],
                    n_results=top_k,
                    where=where,
                    include=["metadatas"],
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)

                retrieved_chunks: List[str] = []
                metas = (result.get("metadatas") or [[]])[0]
                for meta in metas:
                    if isinstance(meta, dict):
                        retrieved_chunks.append(str(meta.get("chunk_id") or "unknown"))

                recall_5_sum += _calculate_recall(retrieved_chunks, query.ground_truth, 5)
                recall_10_sum += _calculate_recall(retrieved_chunks, query.ground_truth, 10)
                mrr_5_sum += _calculate_mrr(retrieved_chunks, query.ground_truth, 5)
                mrr_10_sum += _calculate_mrr(retrieved_chunks, query.ground_truth, 10)
                precision_5_sum += _calculate_precision(retrieved_chunks, query.ground_truth, 5)

            count = len(queries)
            combos.append(
                ComboAggregate(
                    combo_name=combo_name,
                    top_k=top_k,
                    filter_name=filter_name,
                    where=where,
                    query_count=count,
                    recall_at_5=round(recall_5_sum / count, 4),
                    recall_at_10=round(recall_10_sum / count, 4),
                    mrr_at_5=round(mrr_5_sum / count, 4),
                    mrr_at_10=round(mrr_10_sum / count, 4),
                    precision_at_5=round(precision_5_sum / count, 4),
                    avg_latency_ms=round(sum(latencies) / count, 2),
                    min_latency_ms=round(min(latencies), 2),
                    max_latency_ms=round(max(latencies), 2),
                )
            )

            print(f"[*] combo {combo_index}/{total_combo_count} complete: {combo_name}")

    recommended = sorted(combos, key=_score_combo, reverse=True)[0]

    report: Dict[str, Any] = {
        "status": "success",
        "generated_at": _now_iso(),
        "pipeline_phase": "issue_136",
        "input": {
            "eval_set": args.eval_set,
            "collection": args.collection,
            "persist_dir": args.persist_dir,
            "embed_model": args.embed_model,
            "device": args.device,
            "query_count": len(queries),
            "top_k_values": top_k_values,
            "filter_categories": filter_categories,
            "created_at_range": {"min": created_min, "max": created_max},
        },
        "baseline_policy": {
            "priority": ["max(recall_at_5)", "max(mrr_at_5)", "min(avg_latency_ms)"],
        },
        "recommended_baseline": {
            "combo_name": recommended.combo_name,
            "top_k": recommended.top_k,
            "filter_name": recommended.filter_name,
            "where": recommended.where,
            "metrics": {
                "recall_at_5": recommended.recall_at_5,
                "recall_at_10": recommended.recall_at_10,
                "mrr_at_5": recommended.mrr_at_5,
                "mrr_at_10": recommended.mrr_at_10,
                "precision_at_5": recommended.precision_at_5,
                "avg_latency_ms": recommended.avg_latency_ms,
                "min_latency_ms": recommended.min_latency_ms,
                "max_latency_ms": recommended.max_latency_ms,
            },
        },
        "matrix_results": [
            {
                "combo_name": x.combo_name,
                "top_k": x.top_k,
                "filter_name": x.filter_name,
                "where": x.where,
                "query_count": x.query_count,
                "metrics": {
                    "recall_at_5": x.recall_at_5,
                    "recall_at_10": x.recall_at_10,
                    "mrr_at_5": x.mrr_at_5,
                    "mrr_at_10": x.mrr_at_10,
                    "precision_at_5": x.precision_at_5,
                    "avg_latency_ms": x.avg_latency_ms,
                    "min_latency_ms": x.min_latency_ms,
                    "max_latency_ms": x.max_latency_ms,
                },
            }
            for x in sorted(combos, key=_score_combo, reverse=True)
        ],
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if markdown_path is not None:
        markdown_path.write_text(_markdown_summary(report, combos, recommended), encoding="utf-8")

    print("\n[OK] Issue #136 benchmark complete")
    print(f"[OK] recommended={recommended.combo_name}")
    print(f"[OK] output={output_path}")
    if markdown_path is not None:
        print(f"[OK] markdown={markdown_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

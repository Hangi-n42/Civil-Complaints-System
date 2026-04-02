"""Issue #103 runner: Retrieval performance metrics (Recall@5, MRR, latency).

Evaluates semantic search against civil_cases_v1 collection using evaluation_set queries.

Usage:
  c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe scripts/run_issue_103.py \
    --eval-set docs/40_delivery/week3/model_test_assets/evaluation_set.json \
    --output logs/evaluation/week3_retrieval_metrics.json \
    --collection civil_cases_v1 --device cpu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings


@dataclass
class QueryResult:
    """Single query evaluation result."""
    query_id: str
    query_text: str
    ground_truth_chunks: Set[str]
    retrieved_chunks: List[str]  # Ordered by rank
    latency_ms: float
    recall_at_5: float
    recall_at_10: float
    mrr_at_5: float
    mrr_at_10: float
    precision_at_5: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #103 retrieval metrics runner")
    parser.add_argument(
        "--eval-set",
        type=str,
        required=True,
        help="Path to evaluation_set.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output metrics report json",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="civil_cases_v1",
        help="Chroma collection name",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="Chroma persist directory",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device for embedding model",
    )
    parser.add_argument(
        "--embed-model",
        type=str,
        default="BAAI/bge-m3",
        help="Embedding model name",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top results to retrieve per query",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="Number of queries to sample (0=all)",
    )
    return parser.parse_args()


def _load_eval_set(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("evaluation_set must be a list")
    return payload


def _extract_queries(cases: List[Dict[str, Any]], sample_size: int = 0) -> List[Tuple[str, str, Set[str]]]:
    """
    Extract (query_id, query_text, ground_truth_chunk_ids) tuples from evaluation_set.
    
    Args:
        cases: evaluation_set list
        sample_size: If >0, randomly sample this many queries. If 0, use all.
    
    Returns:
        List of (query_id, query_text, ground_truth_chunks)
    """
    queries: List[Tuple[str, str, Set[str]]] = []
    
    for case in cases:
        if not isinstance(case, dict):
            continue
        
        query_id = str(case.get("case_id") or "unknown")
        query_text = str(case.get("query") or "").strip()
        if not query_text:
            continue
        
        # Ground truth: union of all chunk_ids from context
        ground_truth = set()
        for ctx in case.get("context") or []:
            if isinstance(ctx, dict):
                chunk_id = str(ctx.get("chunk_id") or "").strip()
                if chunk_id:
                    ground_truth.add(chunk_id)
        
        if ground_truth:
            queries.append((query_id, query_text, ground_truth))
    
    if sample_size > 0 and len(queries) > sample_size:
        import random
        queries = random.sample(queries, sample_size)
    
    return queries


def _initialize_chroma_client(persist_dir: str, collection_name: str):
    """Initialize and return Chroma client and collection."""
    import chromadb
    
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(name=collection_name)
    return client, collection


def _initialize_embedding_model(model_name: str, device: str):
    """Initialize and return embedding model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device=device)


def _calculate_recall(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    """Calculate Recall@k: |retrieved_top_k ∩ ground_truth| / |ground_truth|"""
    if not ground_truth:
        return 0.0
    top_k = set(retrieved_chunks[:k])
    return len(top_k & ground_truth) / len(ground_truth)


def _calculate_mrr(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    """Calculate MRR@k (Mean Reciprocal Rank): 1 / (rank of first relevant result)"""
    for rank, chunk_id in enumerate(retrieved_chunks[:k], start=1):
        if chunk_id in ground_truth:
            return 1.0 / rank
    return 0.0


def _calculate_precision(retrieved_chunks: List[str], ground_truth: Set[str], k: int) -> float:
    """Calculate Precision@k: |retrieved_top_k ∩ ground_truth| / k"""
    if k == 0:
        return 0.0
    top_k = set(retrieved_chunks[:k])
    return len(top_k & ground_truth) / k


def _build_case_slice_index(cases: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Build per-query slice labels for filter-wise metric aggregation."""
    index: Dict[str, Dict[str, str]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        query_id = str(case.get("case_id") or "unknown")
        index[query_id] = {
            "scenario_type": str(case.get("scenario_type") or "unknown").lower(),
            "risk_level": str(case.get("risk_level") or "unknown").lower(),
            "requires_multi_request": str(bool(case.get("requires_multi_request", False))).lower(),
            "time_sensitivity": str(case.get("time_sensitivity") or "unknown").lower(),
        }
    return index


def _aggregate_slice_metrics(
    results: List[QueryResult],
    slice_index: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Aggregate retrieval metrics by slice groups."""
    out: Dict[str, Dict[str, Dict[str, float]]] = {
        "scenario_type": {},
        "risk_level": {},
        "requires_multi_request": {},
        "time_sensitivity": {},
    }

    for row in results:
        labels = slice_index.get(row.query_id, {})
        for slice_key in out.keys():
            group = labels.get(slice_key, "unknown")
            bucket = out[slice_key].setdefault(
                group,
                {
                    "count": 0,
                    "recall_at_5_sum": 0.0,
                    "recall_at_10_sum": 0.0,
                    "mrr_at_5_sum": 0.0,
                    "latency_ms_sum": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["recall_at_5_sum"] += row.recall_at_5
            bucket["recall_at_10_sum"] += row.recall_at_10
            bucket["mrr_at_5_sum"] += row.mrr_at_5
            bucket["latency_ms_sum"] += row.latency_ms

    normalized: Dict[str, Dict[str, Dict[str, float]]] = {}
    for slice_key, groups in out.items():
        normalized[slice_key] = {}
        for group, raw in groups.items():
            count = max(1, int(raw["count"]))
            normalized[slice_key][group] = {
                "count": int(raw["count"]),
                "recall_at_5": round(raw["recall_at_5_sum"] / count, 4),
                "recall_at_10": round(raw["recall_at_10_sum"] / count, 4),
                "mrr_at_5": round(raw["mrr_at_5_sum"] / count, 4),
                "avg_latency_ms": round(raw["latency_ms_sum"] / count, 2),
            }
    return normalized


def _evaluate_single_query(
    query_id: str,
    query_text: str,
    ground_truth: Set[str],
    collection,
    model,
    top_k: int = 10,
) -> QueryResult:
    """Evaluate a single query against the collection."""
    start = time.perf_counter()
    
    # Embed query
    query_embedding = model.encode([query_text], convert_to_tensor=True)
    query_embedding = query_embedding[0].tolist()
    
    # Search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    # Extract chunk_ids from metadata
    retrieved_chunks = []
    if results and results.get("metadatas") and results["metadatas"][0]:
        for metadata in results["metadatas"][0]:
            chunk_id = metadata.get("chunk_id", "unknown")
            retrieved_chunks.append(chunk_id)
    
    # Calculate metrics
    recall_at_5 = _calculate_recall(retrieved_chunks, ground_truth, 5)
    recall_at_10 = _calculate_recall(retrieved_chunks, ground_truth, 10)
    mrr_at_5 = _calculate_mrr(retrieved_chunks, ground_truth, 5)
    mrr_at_10 = _calculate_mrr(retrieved_chunks, ground_truth, 10)
    precision_at_5 = _calculate_precision(retrieved_chunks, ground_truth, 5)
    
    return QueryResult(
        query_id=query_id,
        query_text=query_text,
        ground_truth_chunks=ground_truth,
        retrieved_chunks=retrieved_chunks,
        latency_ms=elapsed_ms,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        mrr_at_5=mrr_at_5,
        mrr_at_10=mrr_at_10,
        precision_at_5=precision_at_5,
    )


def main():
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("[*] Issue #103 검색 성능 메트릭 평가 시작")
    
    # Load evaluation set
    eval_set = _load_eval_set(Path(args.eval_set))
    queries = _extract_queries(eval_set, args.sample_size)
    slice_index = _build_case_slice_index(eval_set)
    print(f"[*] 평가 쿼리 {len(queries)}개 로드")
    
    # Initialize Chroma and model
    print(f"[*] ChromaDB 로드: {args.collection}")
    client, collection = _initialize_chroma_client(args.persist_dir, args.collection)
    print(f"[*] embedding 모델 로드: {args.embed_model}")
    model = _initialize_embedding_model(args.embed_model, args.device)
    
    # Evaluate all queries
    results: List[QueryResult] = []
    for idx, (query_id, query_text, ground_truth) in enumerate(queries, 1):
        result = _evaluate_single_query(
            query_id=query_id,
            query_text=query_text,
            ground_truth=ground_truth,
            collection=collection,
            model=model,
            top_k=args.top_k,
        )
        results.append(result)
        
        if idx % 50 == 0 or idx == len(queries):
            print(f"[*] {idx}/{len(queries)} queries evaluated")
    
    # Calculate aggregate metrics
    avg_recall_at_5 = sum(r.recall_at_5 for r in results) / len(results) if results else 0.0
    avg_recall_at_10 = sum(r.recall_at_10 for r in results) / len(results) if results else 0.0
    avg_mrr_at_5 = sum(r.mrr_at_5 for r in results) / len(results) if results else 0.0
    avg_mrr_at_10 = sum(r.mrr_at_10 for r in results) / len(results) if results else 0.0
    avg_precision_at_5 = sum(r.precision_at_5 for r in results) / len(results) if results else 0.0
    avg_latency_ms = sum(r.latency_ms for r in results) / len(results) if results else 0.0
    slice_metrics = _aggregate_slice_metrics(results, slice_index)
    
    # Count passes for gate criteria
    # Gate: Recall@5 >= 0.75, avg_latency <= 12000ms (12s)
    recall_gate = avg_recall_at_5 >= 0.75
    latency_gate = avg_latency_ms <= 12000
    all_passed = recall_gate and latency_gate
    
    report = {
        "status": "success" if all_passed else "failure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_phase": "issue_103",
        "collection": args.collection,
        "recall_5": round(avg_recall_at_5, 4),
        "recall_10": round(avg_recall_at_10, 4),
        "avg_latency_ms": round(avg_latency_ms, 2),
        "evaluation": {
            "total_queries": len(results),
            "sample_size": args.sample_size if args.sample_size > 0 else len(results),
        },
        "metrics": {
            "recall_at_5": round(avg_recall_at_5, 4),
            "recall_at_10": round(avg_recall_at_10, 4),
            "mrr_at_5": round(avg_mrr_at_5, 4),
            "mrr_at_10": round(avg_mrr_at_10, 4),
            "precision_at_5": round(avg_precision_at_5, 4),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "min_latency_ms": round(min(r.latency_ms for r in results), 2) if results else 0,
            "max_latency_ms": round(max(r.latency_ms for r in results), 2) if results else 0,
        },
        "slice_metrics": slice_metrics,
        "gate": {
            "issue": "103",
            "requirements": [
                {"metric": "recall_at_5", "threshold": 0.75, "passed": recall_gate},
                {"metric": "avg_latency_ms", "threshold": 12000, "passed": latency_gate},
            ],
            "all_passed": all_passed,
        },
        "sample_results": [
            {
                "query_id": r.query_id,
                "recall_at_5": r.recall_at_5,
                "mrr_at_5": r.mrr_at_5,
                "latency_ms": r.latency_ms,
            }
            for r in results[:10]  # First 10 for inspection
        ],
    }
    
    # Write report
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n[OK] 검색 성능 메트릭 평가 완료")
    print(f"[OK] recall_at_5: {avg_recall_at_5:.4f} (target: >= 0.75)")
    print(f"[OK] avg_latency: {avg_latency_ms:.2f}ms (target: <= 12000ms)")
    print(f"[OK] gate_passed: {all_passed}")
    print(f"[OK] report={output_path}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

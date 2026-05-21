"""V2 파이프라인: Graded Relevance 기반 검색 성능(nDCG, Recall) 측정 및 Ablation."""

from __future__ import annotations

import argparse
import json
import sys
import time
import random
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run


@dataclass
class QueryResult:
    query_id: str
    query_text: str
    ground_truth_dict: Dict[str, int]
    retrieved_chunks: List[str]  # Ordered by rank
    latency_ms: float
    recall_at_5: float
    recall_at_10: float
    ndcg_at_5: float
    ndcg_at_10: float
    mrr_at_5: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2 retrieval metrics runner (with nDCG)")
    parser.add_argument(
        "--v2-dir",
        type=str,
        default="data/evaluation/v2",
        help="Path to V2 evaluation directory (contains queries.jsonl, qrels.tsv)",
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
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="raw",
        choices=["raw", "adaptive"],
        help="Evaluation mode: 'raw' (direct Chroma query) or 'adaptive' (RetrievalService.search())",
    )
    return parser.parse_args()


def _load_v2_set(v2_dir: Path) -> List[Tuple[str, str, Dict[str, int]]]:
    """Load queries and qrels from V2 format."""
    queries = {}
    queries_path = v2_dir / "queries.jsonl"
    with queries_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            obj = json.loads(line)
            queries[obj["query_id"]] = obj["query"]

    qrels = {}
    qrels_path = v2_dir / "qrels_caseid.tsv"  # CASE-XXXXXX 기반으로 변환된 파일
    if not qrels_path.exists():
        qrels_path = v2_dir / "qrels.tsv"
    with qrels_path.open("r", encoding="utf-8") as f:
        # skip header
        next(f, None)
        for line in f:
            if not line.strip(): continue
            parts = line.split("\t")
            if len(parts) == 4:
                qid, _, case_id, score_str = parts
                score = int(score_str)
                if score > 0:  # Only relevant (1 or 2)
                    if qid not in qrels:
                        qrels[qid] = {}
                    qrels[qid][case_id] = score

    # Combine
    dataset = []
    for qid, text in queries.items():
        if qid in qrels:
            dataset.append((qid, text, qrels[qid]))
            
    return dataset


def _initialize_chroma_client(persist_dir: str, collection_name: str):
    import chromadb
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(name=collection_name)
    return client, collection


def _initialize_embedding_model(model_name: str, device: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device=device)


def _calculate_recall(retrieved_chunks: List[str], ground_truth: Dict[str, int], k: int) -> float:
    positives = {docid for docid, score in ground_truth.items() if score > 0}
    if not positives:
        return 0.0
    top_k = retrieved_chunks[:k]
    hits = len(set(top_k) & positives)
    denominator = min(len(positives), k)
    return hits / denominator if denominator > 0 else 0.0


def _evaluate_metrics_dict(query_id: str, retrieved_chunks: List[str], ground_truth: Dict[str, int]) -> Dict[str, float]:
    if not ground_truth:
        return {"nDCG@5": 0.0, "nDCG@10": 0.0, "MRR@5": 0.0}
        
    qrels = [QrelRecord(query_id, docid, score) for docid, score in ground_truth.items()]
    
    # rank is 1-indexed, score should be strictly decreasing
    run = [
        RunRecord(query_id, docid, score=float(len(retrieved_chunks) - index), rank=index + 1)
        for index, docid in enumerate(retrieved_chunks)
    ]
    
    # ir_measures evaluate_run
    from ir_measures import nDCG, MRR
    metrics = evaluate_run(qrels, run, metrics=[nDCG@5, nDCG@10, MRR@5])
    
    result = {}
    for metric_obj, val in metrics.items():
        name = str(metric_obj)
        if "nDCG@5" in name: result["nDCG@5"] = val
        if "nDCG@10" in name: result["nDCG@10"] = val
        if "RR@5" in name: result["MRR@5"] = val
        
    return {
        "nDCG@5": result.get("nDCG@5", 0.0),
        "nDCG@10": result.get("nDCG@10", 0.0),
        "MRR@5": result.get("MRR@5", 0.0),
    }


def _evaluate_single_query(
    query_id: str,
    query_text: str,
    ground_truth: Dict[str, int],
    collection,
    model,
    top_k: int = 10,
) -> QueryResult:
    start = time.perf_counter()
    query_embedding = model.encode([query_text], convert_to_tensor=True)[0].tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas"]
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    retrieved_chunks = []
    if results and results.get("metadatas") and results["metadatas"][0]:
        for metadata in results["metadatas"][0]:
            # case_id(CASE-XXXXXX) 기준으로 매칭 (chunk index 무관)
            case_id = metadata.get("case_id", metadata.get("chunk_id", "unknown"))
            retrieved_chunks.append(case_id)
            
    recall_at_5 = _calculate_recall(retrieved_chunks, ground_truth, 5)
    recall_at_10 = _calculate_recall(retrieved_chunks, ground_truth, 10)
    metrics_dict = _evaluate_metrics_dict(query_id, retrieved_chunks, ground_truth)
    
    return QueryResult(
        query_id=query_id,
        query_text=query_text,
        ground_truth_dict=ground_truth,
        retrieved_chunks=retrieved_chunks,
        latency_ms=elapsed_ms,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        ndcg_at_5=metrics_dict["nDCG@5"],
        ndcg_at_10=metrics_dict["nDCG@10"],
        mrr_at_5=metrics_dict["MRR@5"],
    )


def _evaluate_single_query_adaptive(
    query_id: str,
    query_text: str,
    ground_truth: Dict[str, int],
    service,
    top_k: int = 10,
    collection_name: str = "civil_cases_v1",
) -> QueryResult:
    start = time.perf_counter()
    search_results = asyncio.run(
        service.search(query_text, top_k=top_k, collection_name=collection_name)
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    retrieved_chunks = [
        str(item.get("case_id", item.get("chunk_id", "unknown"))) for item in search_results
    ]
    
    recall_at_5 = _calculate_recall(retrieved_chunks, ground_truth, 5)
    recall_at_10 = _calculate_recall(retrieved_chunks, ground_truth, 10)
    metrics_dict = _evaluate_metrics_dict(query_id, retrieved_chunks, ground_truth)
    
    return QueryResult(
        query_id=query_id,
        query_text=query_text,
        ground_truth_dict=ground_truth,
        retrieved_chunks=retrieved_chunks,
        latency_ms=elapsed_ms,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        ndcg_at_5=metrics_dict["nDCG@5"],
        ndcg_at_10=metrics_dict["nDCG@10"],
        mrr_at_5=metrics_dict["MRR@5"],
    )


def main():
    args = parse_args()
    random.seed(args.seed)
    try:
        import numpy as np
        np.random.seed(args.seed)
    except ImportError:
        pass

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] V2 검색 성능 메트릭 평가 시작 (mode={args.mode}, seed={args.seed})")

    queries = _load_v2_set(Path(args.v2_dir))
    print(f"[*] V2 평가 쿼리 {len(queries)}개 로드 완료 (Ground Truth 포함)")

    if args.mode == "adaptive":
        from app.retrieval.service import get_retrieval_service
        service = get_retrieval_service()
        print("[*] Adaptive 모드: RetrievalService 초기화 완료")
    else:
        print(f"[*] ChromaDB 로드: {args.collection}")
        client, collection = _initialize_chroma_client(args.persist_dir, args.collection)
        print(f"[*] embedding 모델 로드: {args.embed_model}")
        model = _initialize_embedding_model(args.embed_model, args.device)

    results: List[QueryResult] = []
    for idx, (query_id, query_text, ground_truth) in enumerate(queries, 1):
        if args.mode == "adaptive":
            result = _evaluate_single_query_adaptive(
                query_id=query_id,
                query_text=query_text,
                ground_truth=ground_truth,
                service=service,
                top_k=args.top_k,
                collection_name=args.collection,
            )
        else:
            result = _evaluate_single_query(
                query_id=query_id,
                query_text=query_text,
                ground_truth=ground_truth,
                collection=collection,
                model=model,
                top_k=args.top_k,
            )
        results.append(result)

        if idx % 10 == 0 or idx == len(queries):
            print(f"[*] {idx}/{len(queries)} queries evaluated")
            
    # Calculate aggregate metrics
    avg_recall_at_5 = sum(r.recall_at_5 for r in results) / len(results) if results else 0.0
    avg_recall_at_10 = sum(r.recall_at_10 for r in results) / len(results) if results else 0.0
    avg_ndcg_at_5 = sum(r.ndcg_at_5 for r in results) / len(results) if results else 0.0
    avg_ndcg_at_10 = sum(r.ndcg_at_10 for r in results) / len(results) if results else 0.0
    avg_mrr_at_5 = sum(r.mrr_at_5 for r in results) / len(results) if results else 0.0
    avg_latency_ms = sum(r.latency_ms for r in results) / len(results) if results else 0.0
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "mode": args.mode,
        "seed": args.seed,
        "evaluation": {
            "total_queries": len(results),
        },
        "metrics": {
            "recall_at_5": round(avg_recall_at_5, 4),
            "recall_at_10": round(avg_recall_at_10, 4),
            "ndcg_at_5": round(avg_ndcg_at_5, 4),
            "ndcg_at_10": round(avg_ndcg_at_10, 4),
            "mrr_at_5": round(avg_mrr_at_5, 4),
            "avg_latency_ms": round(avg_latency_ms, 2),
        }
    }
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] 검색 성능 메트릭 평가 완료")
    print(f" - mode={args.mode}")
    print(f" - Recall@5 : {avg_recall_at_5:.4f}")
    print(f" - nDCG@10  : {avg_ndcg_at_10:.4f}")
    print(f" - Latency  : {avg_latency_ms:.2f}ms")
    print(f"[OK] report={output_path}")

if __name__ == "__main__":
    sys.exit(main())

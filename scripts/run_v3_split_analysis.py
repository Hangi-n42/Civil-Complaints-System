"""
V3 평가셋 Split 분석: 기존 49건 vs 신규 63건

기존 쿼리(Q-0001~Q-0050)와 신규 쿼리(Q-0051+)의 성능을 분리하여
nDCG 하락 원인이 쿼리 난이도인지 라벨 품질인지 진단한다.

출력: reports/retrieval/v3/split_analysis_{run_id}.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from run_v3_evaluation import (  # noqa: E402
    load_queries,
    load_qrels,
    load_corpus,
    run_bm25,
    run_dense,
    run_adaptive,
    run_pipeline,
    compute_metrics,
    _get_metric,
)

PIPELINE_DIR = PROJECT_ROOT / "configs" / "retrieval_pipelines"
from app.evaluation.datasets import QrelRecord

DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
REPORT_DIR = PROJECT_ROOT / "reports" / "retrieval" / "v3"
TOP_K = 10
OLD_MAX_NUM = 50   # Q-0001 ~ Q-0050: 기존 쿼리
NEW_MIN_NUM = 51   # Q-0051+: 신규 쿼리


def _qid_num(qid: str) -> int:
    return int(qid.split("-")[1])


def filter_queries(queries: list[dict], is_new: bool) -> list[dict]:
    if is_new:
        return [q for q in queries if _qid_num(q["query_id"]) >= NEW_MIN_NUM]
    return [q for q in queries if _qid_num(q["query_id"]) <= OLD_MAX_NUM]


def filter_qrels(qrels: list[QrelRecord], query_ids: set[str]) -> list[QrelRecord]:
    return [r for r in qrels if r.qid in query_ids]


def filter_runs(
    runs: dict[str, list], query_ids: set[str]
) -> dict[str, list]:
    return {qid: recs for qid, recs in runs.items() if qid in query_ids}


def slice_metrics(
    runs: dict[str, list], qrels: list[QrelRecord], query_ids: set[str]
) -> dict[str, float]:
    sliced_runs = filter_runs(runs, query_ids)
    sliced_qrels = filter_qrels(qrels, query_ids)
    return compute_metrics(sliced_runs, sliced_qrels)


def print_split_table(
    method_name: str,
    all_m: dict[str, float],
    old_m: dict[str, float],
    new_m: dict[str, float],
) -> None:
    key_map = {
        "nDCG@5": "nDCG@5",
        "nDCG@10": "nDCG@10",
        "Recall@10": "R@10",
        "MRR@10": "RR@10",
    }
    print(f"\n  [{method_name}]")
    print(f"  {'지표':<12} {'전체(112)':>12} {'기존(49)':>12} {'신규(63)':>12} {'차이(신-구)':>12}")
    print(f"  {'-'*52}")
    for label, key in key_map.items():
        a = _get_metric(all_m, key)
        o = _get_metric(old_m, key)
        n = _get_metric(new_m, key)
        diff = n - o
        print(f"  {label:<12} {a:>12.4f} {o:>12.4f} {n:>12.4f} {diff:>+12.4f}")


def main() -> None:
    print("=" * 60)
    print("V3 Split 분석: 기존 49건 vs 신규 63건")
    print(f"시각: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1] 데이터 로딩...")
    queries = load_queries()
    qrels = load_qrels()
    corpus = load_corpus()

    old_queries = filter_queries(queries, is_new=False)
    new_queries = filter_queries(queries, is_new=True)
    old_qids = {q["query_id"] for q in old_queries}
    new_qids = {q["query_id"] for q in new_queries}
    all_qids = old_qids | new_qids

    print(f"  전체 {len(queries)}건 | 기존 {len(old_queries)}건 | 신규 {len(new_queries)}건")
    print(f"  qrels {len(qrels)}건, 코퍼스 {len(corpus)}건")

    all_results: dict[str, dict] = {}

    # ── BM25 ──
    print("\n[2] BM25 평가...")
    t0 = time.perf_counter()
    bm25_runs = run_bm25(queries, corpus)
    bm25_all = compute_metrics(bm25_runs, qrels)
    bm25_old = slice_metrics(bm25_runs, qrels, old_qids)
    bm25_new = slice_metrics(bm25_runs, qrels, new_qids)
    bm25_time = time.perf_counter() - t0
    all_results["BM25"] = {"all": bm25_all, "old": bm25_old, "new": bm25_new}
    print(f"  소요: {bm25_time:.1f}초")
    print_split_table("BM25", bm25_all, bm25_old, bm25_new)

    # ── BGE-m3 Dense ──
    print("\n[3] BGE-m3 Dense 평가...")
    t0 = time.perf_counter()
    dense_runs = run_dense(queries)
    dense_all = compute_metrics(dense_runs, qrels)
    dense_old = slice_metrics(dense_runs, qrels, old_qids)
    dense_new = slice_metrics(dense_runs, qrels, new_qids)
    dense_time = time.perf_counter() - t0
    all_results["BGE-m3 Dense"] = {"all": dense_all, "old": dense_old, "new": dense_new}
    print(f"  소요: {dense_time:.1f}초")
    print_split_table("BGE-m3 Dense", dense_all, dense_old, dense_new)

    # ── Adaptive ──
    print("\n[4] BGE-m3 Adaptive 평가...")
    t0 = time.perf_counter()
    adaptive_runs = run_adaptive(queries)
    adaptive_all = compute_metrics(adaptive_runs, qrels)
    adaptive_old = slice_metrics(adaptive_runs, qrels, old_qids)
    adaptive_new = slice_metrics(adaptive_runs, qrels, new_qids)
    adaptive_time = time.perf_counter() - t0
    all_results["Adaptive"] = {"all": adaptive_all, "old": adaptive_old, "new": adaptive_new}
    print(f"  소요: {adaptive_time:.1f}초")
    print_split_table("Adaptive", adaptive_all, adaptive_old, adaptive_new)

    # ── Dense + Reranker ──
    print("\n[5] BGE-m3 Dense + CrossEncoder Reranker 평가...")
    t0 = time.perf_counter()
    reranked_runs = run_pipeline(queries, PIPELINE_DIR / "dense_reranked.yaml")
    reranked_all = compute_metrics(reranked_runs, qrels)
    reranked_old = slice_metrics(reranked_runs, qrels, old_qids)
    reranked_new = slice_metrics(reranked_runs, qrels, new_qids)
    reranked_time = time.perf_counter() - t0
    all_results["Dense+Reranker"] = {"all": reranked_all, "old": reranked_old, "new": reranked_new}
    print(f"  소요: {reranked_time:.1f}초")
    print_split_table("Dense+Reranker", reranked_all, reranked_old, reranked_new)

    # ── Hybrid + Reranker ──
    print("\n[6] Hybrid BM25+Dense + CrossEncoder Reranker 평가...")
    t0 = time.perf_counter()
    hybrid_reranked_runs = run_pipeline(queries, PIPELINE_DIR / "hybrid_bm25_dense_rrf_reranked.yaml")
    hybrid_reranked_all = compute_metrics(hybrid_reranked_runs, qrels)
    hybrid_reranked_old = slice_metrics(hybrid_reranked_runs, qrels, old_qids)
    hybrid_reranked_new = slice_metrics(hybrid_reranked_runs, qrels, new_qids)
    hybrid_reranked_time = time.perf_counter() - t0
    all_results["Hybrid+Reranker"] = {"all": hybrid_reranked_all, "old": hybrid_reranked_old, "new": hybrid_reranked_new}
    print(f"  소요: {hybrid_reranked_time:.1f}초")
    print_split_table("Hybrid+Reranker", hybrid_reranked_all, hybrid_reranked_old, hybrid_reranked_new)

    # ── 진단 요약 ──
    print("\n" + "=" * 60)
    print("진단 요약")
    print("=" * 60)
    for method, slices in all_results.items():
        ndcg5_old = _get_metric(slices["old"], "nDCG@5")
        ndcg5_new = _get_metric(slices["new"], "nDCG@5")
        diff = ndcg5_new - ndcg5_old
        verdict = "신규 쿼리가 더 어렵거나 라벨 품질 미달" if diff < -0.05 else (
            "거의 동등" if abs(diff) <= 0.05 else "신규 쿼리가 더 쉬움"
        )
        print(f"  {method:<16} nDCG@5 기존={ndcg5_old:.4f} 신규={ndcg5_new:.4f}  [{verdict}]")

    # ── 저장 ──
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _round_metrics(m: dict[str, float]) -> dict[str, float]:
        return {k: round(v, 4) for k, v in m.items()}

    report = {
        "run_id": run_id,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "n_old_queries": len(old_queries),
        "n_new_queries": len(new_queries),
        "results": {
            method: {
                slice_name: _round_metrics(slices[slice_name])
                for slice_name in ("all", "old", "new")
            }
            for method, slices in all_results.items()
        },
        "latency_seconds": {
            "BM25": round(bm25_time, 2),
            "BGE-m3 Dense": round(dense_time, 2),
            "Adaptive": round(adaptive_time, 2),
            "Dense+Reranker": round(reranked_time, 2),
            "Hybrid+Reranker": round(hybrid_reranked_time, 2),
        },
    }

    out_path = REPORT_DIR / f"split_analysis_{run_id}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_DIR / "split_analysis_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[OK] 리포트 저장: {out_path}")


if __name__ == "__main__":
    main()

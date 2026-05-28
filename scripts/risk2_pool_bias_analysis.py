"""
Risk 2: 평가셋 인플레이션 검증

#262에서 추가된 201쌍(35 generation-origin + 166 cross-encoder pool)이 Dense 점수를
얼마나 끌어올렸는지 측정한다.

4가지 qrels 변형으로 Dense + BM25 + Adaptive 평가:
  V0_full       — 현재 qrels.tsv (2549쌍, baseline)
  V1_no_genorig — 35 generation-origin 제거 (2514쌍)
  V2_no_cepool  — 166 cross-encoder pool 제거 (2383쌍)
  V3_pre262     — 201쌍 모두 제거 = #262 머지 전 상태 (2348쌍)

산출물: reports/retrieval/v3/risk2_pool_bias_analysis.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries,
    load_qrels,
    load_corpus,
    run_bm25,
    run_dense,
    compute_metrics,
)
from app.evaluation.datasets import QrelRecord

V3_DIR = Path("data/evaluation/v3")
REPORT_PATH = Path("reports/retrieval/v3/risk2_pool_bias_analysis.json")


def load_added_pairs(path: Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    with open(path) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 4:
                out.add((parts[0], parts[2]))
    return out


def filter_qrels(qrels: list[QrelRecord], exclude: set[tuple[str, str]]) -> list[QrelRecord]:
    return [q for q in qrels if (q.qid, q.docid) not in exclude]


def main() -> None:
    print("=" * 60)
    print("Risk 2: Pool Bias Analysis")
    print("=" * 60)

    queries = load_queries()
    qrels_full = load_qrels()
    corpus = load_corpus()

    gen_origin = load_added_pairs(Path("/tmp/risk2/added_gen_origin.tsv"))
    ce_pool = load_added_pairs(Path("/tmp/risk2/added_ce_pool.tsv"))
    all_added = gen_origin | ce_pool

    print(f"\n[데이터]")
    print(f"  쿼리: {len(queries)}건")
    print(f"  qrels (full):  {len(qrels_full)}쌍")
    print(f"  gen_origin:    {len(gen_origin)}쌍 (모두 rel=2)")
    print(f"  ce_pool:       {len(ce_pool)}쌍")
    print(f"  all_added:     {len(all_added)}쌍")

    qrels_variants = {
        "V0_full":       qrels_full,
        "V1_no_genorig": filter_qrels(qrels_full, gen_origin),
        "V2_no_cepool":  filter_qrels(qrels_full, ce_pool),
        "V3_pre262":     filter_qrels(qrels_full, all_added),
    }
    for name, qs in qrels_variants.items():
        print(f"  {name}: {len(qs)}쌍")

    print("\n[1] BM25 검색...")
    t0 = time.perf_counter()
    bm25_runs = run_bm25(queries, corpus)
    print(f"  소요: {time.perf_counter()-t0:.1f}s")

    print("\n[2] BGE-m3 Dense 검색...")
    t0 = time.perf_counter()
    dense_runs = run_dense(queries)
    print(f"  소요: {time.perf_counter()-t0:.1f}s")

    # Adaptive 제외: Risk 3에서 Adaptive ≈ Dense로 결정. Risk 2의 pool bias 검증에는
    # BM25 vs Dense 비교가 본질적. (Adaptive 실행은 RetrievalService 내부 CUDA 의존성으로
    # 현 CPU 환경에서 실패.)
    method_runs = {
        "BM25": bm25_runs,
        "BGE-m3 Dense": dense_runs,
    }

    print("\n[4] 4-way qrels 변형 평가...")
    results: dict[str, dict[str, dict[str, float]]] = {}
    for variant_name, variant_qrels in qrels_variants.items():
        results[variant_name] = {}
        for method_name, runs in method_runs.items():
            results[variant_name][method_name] = compute_metrics(runs, variant_qrels)
        print(f"  {variant_name}: done")

    # 핵심 비교: nDCG@5, R@10
    print("\n" + "=" * 80)
    print("결과: 각 qrels 변형에서 nDCG@5 / R@10 / nDCG@10")
    print("=" * 80)
    header = f"{'variant':<16} | {'method':<14} | {'nDCG@5':>8} {'nDCG@10':>9} {'R@10':>8}"
    print(header); print("-" * len(header))
    for vname in ["V0_full", "V1_no_genorig", "V2_no_cepool", "V3_pre262"]:
        for mname in ["BM25", "BGE-m3 Dense"]:
            r = results[vname][mname]
            ndcg5 = next((v for k, v in r.items() if "nDCG@5" in k), 0.0)
            ndcg10 = next((v for k, v in r.items() if "nDCG@10" in k), 0.0)
            recall10 = next((v for k, v in r.items() if "R@10" in k), 0.0)
            print(f"{vname:<16} | {mname:<14} | {ndcg5:>8.4f} {ndcg10:>9.4f} {recall10:>8.4f}")
        print("-" * len(header))

    # Pool bias 영향
    print("\n" + "=" * 80)
    print("Pool bias 영향: V0_full vs V3_pre262 (201쌍 제거 시 점수 변화)")
    print("=" * 80)
    for mname in ["BM25", "BGE-m3 Dense"]:
        r0 = results["V0_full"][mname]
        r3 = results["V3_pre262"][mname]
        ndcg5_0 = next((v for k, v in r0.items() if "nDCG@5" in k), 0.0)
        ndcg5_3 = next((v for k, v in r3.items() if "nDCG@5" in k), 0.0)
        r10_0 = next((v for k, v in r0.items() if "R@10" in k), 0.0)
        r10_3 = next((v for k, v in r3.items() if "R@10" in k), 0.0)
        print(f"{mname:<14}: nDCG@5  {ndcg5_3:.4f} → {ndcg5_0:.4f}  (Δ={ndcg5_0-ndcg5_3:+.4f})")
        print(f"{'':<14}  R@10    {r10_3:.4f} → {r10_0:.4f}  (Δ={r10_0-r10_3:+.4f})")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "n_queries": len(queries),
            "variants": {k: len(v) for k, v in qrels_variants.items()},
            "added_pair_counts": {
                "gen_origin": len(gen_origin),
                "ce_pool": len(ce_pool),
                "all": len(all_added),
            },
            "results": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()

"""
Risk 3 / Scenario C 가설 검증 (코드 변경 없음 — 런타임 몽키패치)

가설: RetrievalService.search()에서 _hybrid_rrf(BM25 융합)만 비활성화하면
  - nDCG@5 0.897 유지
  - nDCG@10 / R@10 이 Dense 수준(0.893 / 0.592)으로 회복
  - Latency 162s → Dense 수준(~30s)

방법: service.py를 수정하지 않고, RetrievalService._hybrid_rrf를 런타임에
      'dense_results[:top_k] 그대로 반환'으로 패치한 뒤 run_adaptive 평가.
      (_apply_retrieval_policy는 retrieval_policy=None일 때 이미 boost 미적용이므로 패치 불필요)

산출물: reports/retrieval/v3/risk3c_lightweight_adaptive.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries,
    load_qrels,
    run_dense,
    run_adaptive,
    compute_metrics,
)

REPORT_PATH = Path("reports/retrieval/v3/risk3c_lightweight_adaptive.json")


def _metric(d: dict, key: str) -> float:
    # 정확 매칭 우선 (R@10이 RR@10에 부분 매칭되는 버그 방지)
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return next((v for k, v in d.items() if key.lower() in k.lower()), 0.0)


def main() -> None:
    print("=" * 60)
    print("Risk 3 / Scenario C: 경량 Adaptive 가설 검증")
    print("=" * 60)

    queries = load_queries()
    qrels = load_qrels()
    print(f"쿼리: {len(queries)} / qrels: {len(qrels)}")

    # ── (1) 현행 Adaptive (Hybrid 포함) ──
    print("\n[1] 현행 Adaptive (Hybrid RRF 포함) 측정...")
    t0 = time.perf_counter()
    cur_runs = run_adaptive(queries)
    cur_latency = time.perf_counter() - t0
    cur_metrics = compute_metrics(cur_runs, qrels)
    print(f"  소요: {cur_latency:.1f}s")

    # ── (2) 경량 Adaptive (Hybrid 비활성, 런타임 패치) ──
    print("\n[2] 경량 Adaptive (Hybrid 비활성) 측정...")
    from app.retrieval.service import RetrievalService

    original_hybrid = RetrievalService._hybrid_rrf

    def _no_hybrid(self, *, query, dense_results, top_k, collection_key, k=60):
        # Scenario C: BM25 융합 생략, Dense 결과를 top_k로 자르기만
        return dense_results[:top_k]

    RetrievalService._hybrid_rrf = _no_hybrid
    try:
        t0 = time.perf_counter()
        lite_runs = run_adaptive(queries)
        lite_latency = time.perf_counter() - t0
        lite_metrics = compute_metrics(lite_runs, qrels)
        print(f"  소요: {lite_latency:.1f}s")
    finally:
        RetrievalService._hybrid_rrf = original_hybrid

    # ── (3) 순수 Dense (대조군) ──
    print("\n[3] 순수 Dense (대조군) 측정...")
    t0 = time.perf_counter()
    dense_runs = run_dense(queries)
    dense_latency = time.perf_counter() - t0
    dense_metrics = compute_metrics(dense_runs, qrels)
    print(f"  소요: {dense_latency:.1f}s")

    # ── 결과 ──
    print("\n" + "=" * 72)
    print("결과 비교")
    print("=" * 72)
    hdr = f"{'method':<26}{'nDCG@5':>9}{'nDCG@10':>9}{'R@10':>9}{'latency(s)':>12}"
    print(hdr); print("-" * len(hdr))
    rows = [
        ("현행 Adaptive (Hybrid)", cur_metrics, cur_latency),
        ("경량 Adaptive (no Hybrid)", lite_metrics, lite_latency),
        ("순수 Dense (대조)", dense_metrics, dense_latency),
    ]
    for name, m, lat in rows:
        print(f"{name:<26}{_metric(m,'nDCG@5'):>9.4f}{_metric(m,'nDCG@10'):>9.4f}{_metric(m,'R@10'):>9.4f}{lat:>12.1f}")

    print("\n[가설 판정]")
    lite_n5, lite_n10, lite_r10 = _metric(lite_metrics,'nDCG@5'), _metric(lite_metrics,'nDCG@10'), _metric(lite_metrics,'R@10')
    den_n5, den_n10, den_r10 = _metric(dense_metrics,'nDCG@5'), _metric(dense_metrics,'nDCG@10'), _metric(dense_metrics,'R@10')
    cur_n10, cur_r10 = _metric(cur_metrics,'nDCG@10'), _metric(cur_metrics,'R@10')

    print(f"  nDCG@5 유지(≥0.85):           {lite_n5:.4f}  {'OK' if lite_n5 >= 0.85 else 'FAIL'}")
    print(f"  nDCG@10 회복(현행 {cur_n10:.4f} → ?): {lite_n10:.4f}  (Dense {den_n10:.4f}, Δ={lite_n10-cur_n10:+.4f})")
    print(f"  R@10 회복(현행 {cur_r10:.4f} → ?):    {lite_r10:.4f}  (Dense {den_r10:.4f}, Δ={lite_r10-cur_r10:+.4f})")
    print(f"  Latency 단축:                 {cur_latency:.1f}s → {lite_latency:.1f}s")
    print(f"  경량 Adaptive ≈ Dense:        {'YES' if abs(lite_n5-den_n5)<0.01 and abs(lite_r10-den_r10)<0.01 else 'NO (차이 존재)'}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_queries": len(queries),
        "results": {
            "current_adaptive_hybrid": {"metrics": cur_metrics, "latency_s": round(cur_latency, 2)},
            "lightweight_adaptive_no_hybrid": {"metrics": lite_metrics, "latency_s": round(lite_latency, 2)},
            "pure_dense": {"metrics": dense_metrics, "latency_s": round(dense_latency, 2)},
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()

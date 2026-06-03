"""
정책 부스트(policy boost) 영향 측정 — scenario C 결정용

평가 경로(run_adaptive)는 retrieval_policy=None으로 호출되어 부스트가 미측정.
프로덕션은 resolve_retrieval_policy(topic)으로 welfare→admin_policy,
traffic/env/construction→field_ops를 적용. 이 차이를 측정한다.

3가지 모드(Hybrid는 모두 비활성 — scenario C 전제):
  (A) policy=None      — 현재 평가 방식
  (B) policy=resolved  — 프로덕션 방식 (topic→policy)
  (대조) 순수 Dense

산출물: reports/retrieval/v3/risk3c_policy_boost_impact.json
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries, load_qrels, run_dense, compute_metrics,
    build_run, dedup_to_case, chunk_to_case, TOP_K, _map_topic,
)

REPORT_PATH = Path("reports/retrieval/v3/risk3c_policy_boost_impact.json")


def _metric(d: dict, key: str) -> float:
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return 0.0


def run_adaptive_policy(queries, *, resolve_policy: bool):
    """Hybrid 비활성 + policy 적용 여부 선택."""
    from app.retrieval.service import RetrievalService
    from app.retrieval.router.adaptive_router import resolve_retrieval_policy

    # Hybrid 비활성 (scenario C 전제)
    original_hybrid = RetrievalService._hybrid_rrf
    RetrievalService._hybrid_rrf = lambda self, *, query, dense_results, top_k, collection_key, k=60: dense_results[:top_k]

    svc = RetrievalService()

    async def _search_all():
        runs = {}
        for q in queries:
            qid = q["query_id"]
            topic = _map_topic(q.get("category", ""), q.get("source", ""))
            policy = resolve_retrieval_policy(topic) if resolve_policy else None
            results = await svc.search(query=q["query"], top_k=TOP_K * 3,
                                       topic_type=topic, retrieval_policy=policy)
            hits = [(r.get("case_id") or chunk_to_case(r.get("chunk_id") or ""), float(r.get("score", 0))) for r in results]
            runs[qid] = build_run(qid, dedup_to_case(hits)[:TOP_K])
        return runs

    try:
        return asyncio.run(_search_all())
    finally:
        RetrievalService._hybrid_rrf = original_hybrid


def main() -> None:
    print("=" * 60)
    print("정책 부스트 영향 측정 (Hybrid 비활성 전제)")
    print("=" * 60)
    queries = load_queries()
    qrels = load_qrels()

    print("\n[A] policy=None (현재 평가 방식)...")
    t0 = time.perf_counter()
    runs_none = run_adaptive_policy(queries, resolve_policy=False)
    lat_none = time.perf_counter() - t0
    m_none = compute_metrics(runs_none, qrels)

    print("[B] policy=resolved (프로덕션 방식)...")
    t0 = time.perf_counter()
    runs_pol = run_adaptive_policy(queries, resolve_policy=True)
    lat_pol = time.perf_counter() - t0
    m_pol = compute_metrics(runs_pol, qrels)

    print("[대조] 순수 Dense...")
    t0 = time.perf_counter()
    runs_dense = run_dense(queries)
    lat_dense = time.perf_counter() - t0
    m_dense = compute_metrics(runs_dense, qrels)

    print("\n" + "=" * 66)
    hdr = f"{'모드':<28}{'nDCG@5':>9}{'nDCG@10':>9}{'R@10':>9}{'AP@10':>9}"
    print(hdr); print("-" * len(hdr))
    for name, m in [("경량+policy=None", m_none), ("경량+policy=resolved", m_pol), ("순수 Dense", m_dense)]:
        print(f"{name:<28}{_metric(m,'nDCG@5'):>9.4f}{_metric(m,'nDCG@10'):>9.4f}{_metric(m,'R@10'):>9.4f}{_metric(m,'AP@10'):>9.4f}")

    d5 = _metric(m_pol,'nDCG@5') - _metric(m_none,'nDCG@5')
    d10 = _metric(m_pol,'nDCG@10') - _metric(m_none,'nDCG@10')
    dr = _metric(m_pol,'R@10') - _metric(m_none,'R@10')
    print(f"\n[정책 부스트 영향: resolved − None]")
    print(f"  nDCG@5  Δ={d5:+.4f}")
    print(f"  nDCG@10 Δ={d10:+.4f}")
    print(f"  R@10    Δ={dr:+.4f}")
    verdict = "부스트 무해/미미 → 제거 안전" if abs(d5) < 0.005 and d10 >= -0.005 and dr >= -0.005 else \
              ("부스트 도움 → 유지 검토" if d5 > 0.005 or d10 > 0.005 else "부스트 해로움 → 제거 권장")
    print(f"  판정: {verdict}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_queries": len(queries),
        "results": {
            "lightweight_policy_none": {"metrics": m_none, "latency_s": round(lat_none, 2)},
            "lightweight_policy_resolved": {"metrics": m_pol, "latency_s": round(lat_pol, 2)},
            "pure_dense": {"metrics": m_dense, "latency_s": round(lat_dense, 2)},
        },
        "policy_boost_delta": {"nDCG@5": d5, "nDCG@10": d10, "R@10": dr},
        "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT_PATH}")


if __name__ == "__main__":
    main()

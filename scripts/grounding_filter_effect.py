"""RAG grounding: LLM 리랭커를 '필터'로 썼을 때 해로운 선례 제거 효과 (#299).

#299 기본 측정: Hybrid top-5의 23%가 해로운(rel0) 선례, 45% 쿼리가 ≥1개 포함.
가설: LLM 리랭커가 0점이라 매긴 후보를 **빼면(filter)** grounding이 안전해진다(순서만 바꾸는 것보다 강함).

세 변형을 동일 qrels(no-self)로 비교:
  - Hybrid            : 원본 top-K
  - Hybrid+LLM-rerank : top-10을 LLM 점수로 재정렬 후 top-K (순서만)
  - Hybrid+LLM-filter : LLM 0점 후보 제거 후 남은 것 top-K (개수 < K 가능)

측정:
  - 해로움(rel0) 비율 / 유효(rel≥1) 비율 / 미판정
  - ≥1개 해로운 선례가 섞인 쿼리 비율
  - 근거 부족: 필터 후 0개/평균 채워진 슬롯 수 (필터의 부작용)

LLM 점수는 eval_llm_reranker.py --full이 만든 캐시(llm_rerank_full.json) 재사용. LLM 미호출, 로컬.
산출: reports/retrieval/v3/grounding_filter_effect.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense
from scripts.eval_hybrid_noself import rrf
from scripts.grounding_topk_breakdown import load_rel_map

CACHE = ROOT / "data" / "evaluation" / "v3" / "checkpoints" / "llm_rerank_full.json"
OUT = ROOT / "reports" / "retrieval" / "v3" / "grounding_filter_effect.json"
KS = [3, 5]
DEPTH = 50
RERANK_POOL = 10  # LLM이 점수 매긴 Hybrid 상위 후보 수


def summarize(per_query_docs: dict[str, list[str]], qid_keys, rel_map, k: int) -> dict:
    """per_query_docs: qid -> 이미 top-K로 자른 docid 리스트. true qrels로 분해."""
    slots = Counter()
    q_harmful = q_empty = 0
    filled = []
    nq = 0
    for qid in qid_keys:
        docs = per_query_docs.get(qid, [])
        nq += 1
        if not docs:
            q_empty += 1
        filled.append(len(docs))
        harmful = 0
        for d in docs:
            rel = rel_map.get((qid, d))
            slots["unjudged" if rel is None else f"rel{rel}"] += 1
            if rel == 0:
                harmful += 1
        if harmful >= 1:
            q_harmful += 1
    total = sum(slots.values())
    return {
        "k": k, "n_queries": nq, "total_slots": total,
        "slots": {kk: slots.get(kk, 0) for kk in ["rel2", "rel1", "rel0", "unjudged"]},
        "harmful_rate": round(slots.get("rel0", 0) / total, 4) if total else 0.0,
        "useful_rate": round((slots.get("rel2", 0) + slots.get("rel1", 0)) / total, 4) if total else 0.0,
        "queries_with_harmful_pct": round(q_harmful / nq, 4) if nq else 0.0,
        "queries_empty_grounding": q_empty,
        "avg_filled_slots": round(sum(filled) / nq, 3) if nq else 0.0,
    }


def main() -> None:
    if not CACHE.exists():
        sys.exit(f"LLM 리랭커 캐시 없음: {CACHE}\n먼저: python scripts/eval_llm_reranker.py --full")
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    print(f"LLM 점수 캐시 {len(cache)}건 로드")

    R.TOP_K = DEPTH
    queries = load_queries()
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    rel_map = load_rel_map()
    corpus = load_corpus()
    print("[1] BM25..."); bm25 = run_bm25(queries, corpus)
    print("[2] Dense..."); dense = run_dense(queries)
    hybrid = rrf([bm25, dense])
    qids = [q["query_id"] for q in queries]

    def score(qid, docid):
        s = cache.get(f"{qid}::{docid}")
        return 0 if s is None else s

    report = {"eval_set": "qrels_pooled_3judge, NO-self", "n_queries": len(queries),
              "rerank_pool": RERANK_POOL, "by_k": {}}
    for k in KS:
        variants = {"Hybrid": {}, "Hybrid+LLM-rerank": {}, "Hybrid+LLM-filter": {}}
        for qid in qids:
            recs = [r for r in sorted(hybrid.get(qid, []), key=lambda x: x.rank)
                    if r.docid != self_doc.get(qid)]
            pool = recs[:RERANK_POOL]
            # 1) 원본
            variants["Hybrid"][qid] = [r.docid for r in pool[:k]]
            # 2) 재정렬: LLM 점수 desc, 동점 원래순서
            rer = sorted(enumerate(pool), key=lambda t: (-score(qid, t[1].docid), t[0]))
            variants["Hybrid+LLM-rerank"][qid] = [r.docid for _, r in rer[:k]]
            # 3) 필터: 0점 제거 후 점수 desc, top-k (개수<k 가능)
            kept = [r for _, r in rer if score(qid, r.docid) >= 1]
            variants["Hybrid+LLM-filter"][qid] = [r.docid for r in kept[:k]]
        report["by_k"][str(k)] = {name: summarize(docs, qids, rel_map, k)
                                  for name, docs in variants.items()}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for k in KS:
        print(f"\n{'='*82}\n상위 {k}개 grounding — 원본 vs 재정렬 vs 필터 (NO-self)")
        print(f"{'변형':<20}{'해로움(rel0)':>13}{'유효(rel≥1)':>12}{'0점섞인쿼리':>13}{'근거0개':>9}{'평균근거':>9}")
        for name in ["Hybrid", "Hybrid+LLM-rerank", "Hybrid+LLM-filter"]:
            b = report["by_k"][str(k)][name]
            print(f"{name:<20}{b['harmful_rate']:>12.1%}{b['useful_rate']:>12.1%}"
                  f"{b['queries_with_harmful_pct']:>12.1%}{b['queries_empty_grounding']:>9}{b['avg_filled_slots']:>9.2f}")
    print(f"\n[리포트] {OUT}")
    print("필터: 해로움↓ 기대. 단 '근거0개'(전부 0점이라 비워짐)·'평균근거'↓ 부작용 확인.")


if __name__ == "__main__":
    main()

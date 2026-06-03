"""RAG grounding 정확도: 상위 K개 관련성 분해 (#299).

용도(유사 민원을 근거로 답변 초안 생성)에선 recall이 아니라 **top-K 정확도**가 핵심.
특히 rel0(주입 시 할루시네이션 유발) 문서가 top-K에 끼면 잘못된 답변 위험.

각 방법(BM25/Dense/Hybrid)의 top-K(K=3,5)를 canonical qrels(no-self)로 분해:
  - rel2/rel1/rel0/미판정 슬롯 수
  - 해로운 비율 = rel0 / 전체 슬롯
  - ≥1개 rel0가 섞인 쿼리 비율 (= 답변이 오염될 수 있는 쿼리)
  - 유효(rel≥1) 평균 개수

산출: reports/retrieval/v3/grounding_topk_breakdown.json (LLM 미사용, 로컬 수 분)
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
from scripts.eval_noself import take_top
from scripts.eval_hybrid_noself import rrf

QRELS_PATH = ROOT / "data" / "evaluation" / "v3" / "qrels_pooled_3judge.tsv"
OUT = ROOT / "reports" / "retrieval" / "v3" / "grounding_topk_breakdown.json"
KS = [3, 5]
DEPTH = 50


def load_rel_map() -> dict[tuple[str, str], int]:
    m = {}
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            p = line.strip().split("\t")
            if i == 0 and p[0].lower() in {"qid", "query_id"}:
                continue
            if len(p) == 4:
                m[(p[0], p[2])] = int(p[3])
            elif len(p) == 3:
                m[(p[0], p[1])] = int(p[2])
    return m


def breakdown(runs, self_doc, rel_map, k) -> dict:
    top = take_top(runs, self_doc, k, drop_self=True)
    slots = Counter()           # rel2/rel1/rel0/unjudged 슬롯 수
    q_with_harmful = 0          # rel0가 1개 이상인 쿼리
    q_all_useful = 0            # top-K 전부 rel>=1 인 쿼리
    useful_per_q = []
    nq = 0
    for qid, recs in top.items():
        if not recs:
            continue
        nq += 1
        labels = []
        for r in recs:
            rel = rel_map.get((qid, r.docid))
            labels.append(rel)
            slots["unjudged" if rel is None else f"rel{rel}"] += 1
        harmful = sum(1 for x in labels if x == 0)
        useful = sum(1 for x in labels if x is not None and x >= 1)
        useful_per_q.append(useful)
        if harmful >= 1:
            q_with_harmful += 1
        if useful == len(recs):
            q_all_useful += 1
    total = sum(slots.values())
    return {
        "k": k, "n_queries": nq, "total_slots": total,
        "slots": {kk: slots.get(kk, 0) for kk in ["rel2", "rel1", "rel0", "unjudged"]},
        "harmful_rate": round(slots.get("rel0", 0) / total, 4) if total else 0.0,
        "useful_rate": round((slots.get("rel2", 0) + slots.get("rel1", 0)) / total, 4) if total else 0.0,
        "queries_with_harmful": q_with_harmful,
        "queries_with_harmful_pct": round(q_with_harmful / nq, 4) if nq else 0.0,
        "queries_all_useful": q_all_useful,
        "avg_useful_per_query": round(sum(useful_per_q) / nq, 3) if nq else 0.0,
    }


def main() -> None:
    R.TOP_K = DEPTH
    queries = load_queries()
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    rel_map = load_rel_map()
    corpus = load_corpus()
    print("[1] BM25..."); bm25 = run_bm25(queries, corpus)
    print("[2] Dense..."); dense = run_dense(queries)
    hybrid = rrf([bm25, dense])
    systems = {"BM25": bm25, "Dense": dense, "Hybrid": hybrid}

    report = {"eval_set": "qrels_pooled_3judge, NO-self", "n_queries": len(queries), "by_k": {}}
    for k in KS:
        report["by_k"][str(k)] = {name: breakdown(runs, self_doc, rel_map, k)
                                  for name, runs in systems.items()}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for k in KS:
        print(f"\n{'='*72}\n상위 {k}개 grounding 분해 (NO-self, canonical qrels)")
        print(f"{'방법':<8}{'해로움(rel0)':>14}{'유효(rel≥1)':>13}{'미판정':>9}{'0점섞인쿼리':>13}{'평균유효':>9}")
        for name in systems:
            b = report["by_k"][str(k)][name]
            print(f"{name:<8}{b['harmful_rate']:>13.1%}{b['useful_rate']:>13.1%}"
                  f"{b['slots']['unjudged']:>9}{b['queries_with_harmful_pct']:>12.1%}{b['avg_useful_per_query']:>9.2f}")
    print(f"\n[리포트] {OUT}")
    print("해석: 해로움(rel0)이 낮을수록 grounding 안전. '0점섞인쿼리'=답변 오염 가능 쿼리 비율.")


if __name__ == "__main__":
    main()

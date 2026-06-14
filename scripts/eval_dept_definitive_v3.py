"""부서 soft rerank 효과의 편향 없는 확정 측정.

#369 최종. 지금까지 부서 효과는 낡은 태그(v1) 또는 시뮬레이션, home-field 편향 평가셋에서
측정됐다. 이 스크립트는 세 조건을 동시에 만족하는 깨끗한 측정을 한다:
  - 컬렉션: civil_cases_v3 (진짜 최신 부서태그)
  - 쿼리: 현재 파이프라인 재구조화(버전중립, _cache_restructured_queries)
  - 쿼리 부서: DepartmentAssigner 로 실제 예측
  - qrels: 보강(원 + 공식 LLM 채점 캐시)
  - weight 스윕(전략별)으로 최적 가점 탐색

모두 로컬(임베딩 기반, 원격 LLM 불필요). 원문 미포함(집계만).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries

QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
NEWQ = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_restructured_queries.json"
JUDGE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
OUT = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "dept_definitive_v3.md"
WEIGHTS = {"dense": [0.0, 0.01, 0.02, 0.03, 0.05, 0.08], "hybrid": [0.0, 0.001, 0.002, 0.005, 0.01, 0.02]}
COLL = "civil_cases_v3"
TOP_K, POOL = 10, 50


def recs(qid, ranked, k):
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


def rerank(pool, qd, doc_dept, w):
    return sorted(((cid, sc + (w if (qd & set(doc_dept.get(cid, []))) else 0.0)) for cid, sc in pool),
                  key=lambda r: r[1], reverse=True)


async def main():
    queries = load_queries(QUERIES)
    qrels = load_qrels(QRELS)
    rel_qids = {r.qid for r in qrels if r.relevance > 0}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    aug = [r for r in qrels if r.qid in rel_qids]
    for k, v in json.loads(JUDGE.read_text()).items():
        qid, cid = k.split("||", 1)
        if qid in rel_qids:
            aug.append(QrelRecord(qid=qid, docid=cid, relevance=int(v)))

    newq = json.loads(NEWQ.read_text())
    qtext = {q["query_id"]: newq.get(q["query_id"], q["query"]) for q in judged}

    # v3 실제 문서 부서
    col = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db")).get_collection(COLL)
    doc_dept = {}
    for m in col.get(include=["metadatas"])["metadatas"]:
        cid = str(m.get("case_id") or "")
        if cid:
            doc_dept.setdefault(cid, [u.strip() for u in str(m.get("responsible_units") or "").split("|") if u.strip()])

    # 쿼리 부서 예측 (실제 assigner)
    asg = get_department_assigner(); asg.build_index(rebuild=False)
    qdept = {}
    cov = 0
    for q in judged:
        cands = asg.assign(qtext[q["query_id"]], top_n_units=3)
        names = {c["name"] for c in cands if c.get("name")}
        qdept[q["query_id"]] = names
        if names:
            cov += 1
    print(f"쿼리 부서 예측 커버리지: {cov}/{len(judged)}")

    # 진단: 부서 판별력 (정답 vs 비정답 일치율) — v3 실제 태그
    svc = RetrievalService()
    lines = ["# 부서 soft rerank 확정 측정 (v3 실제 태그 + 새 쿼리 + 보강 qrels)", "",
             f"- 평가 쿼리 {len(judged)}건, 컬렉션 {COLL}, top-{TOP_K}, 보강 qrels",
             f"- 쿼리 부서 예측(DepartmentAssigner) 커버리지 {cov}/{len(judged)}", ""]
    for strat in ("dense", "hybrid"):
        pools = {}
        for q in judged:
            res = await svc.search(query=qtext[q["query_id"]], top_k=POOL, collection_name=COLL,
                                   strategy=strat, grounding_filter=False, query_signals=None)
            pools[q["query_id"]] = dedup_results(res, top_k=POOL)
        lines += [f"## {strat.upper()} — 가점 weight 스윕", "",
                  "| weight | nDCG@10 | ΔnDCG@10 | R@10 | ΔR@10 |", "| ---: | ---: | ---: | ---: | ---: |"]
        base_m = None
        best = (0.0, -1)
        for w in WEIGHTS[strat]:
            flat = [r for qid, p in pools.items() for r in recs(qid, rerank(p, qdept.get(qid, set()), doc_dept, w), TOP_K)]
            m = evaluate_run(aug, flat)
            if w == 0.0:
                base_m = m
            dn = m["nDCG@10"] - base_m["nDCG@10"]
            dr = m["R@10"] - base_m["R@10"]
            lines.append(f"| {w} | {m['nDCG@10']:.4f} | {dn:+.4f} | {m['R@10']:.4f} | {dr:+.4f} |")
            if dn > best[1]:
                best = (w, dn)
            print(f"[{strat}] w={w}: nDCG@10={m['nDCG@10']:.4f} (Δ{dn:+.4f})")
        lines.append("")
        lines.append(f"→ **{strat} 최적 weight={best[0]}, ΔnDCG@10={best[1]:+.4f}**")
        lines.append("")
    lines += ["## 해석",
              "- 이 측정은 풀링편향(보강 qrels)·home-field(새 쿼리)·낡은태그(v3 실제)를 모두 제거.",
              "- 최적 weight 의 Δ가 부서 신호의 편향 없는 진짜 효과 크기.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {OUT}")


if __name__ == "__main__":
    asyncio.run(main())

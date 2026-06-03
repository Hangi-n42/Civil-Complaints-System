"""Hybrid + Reranker 평가 (#278).

Hybrid(BM25+Dense RRF, #273과 동일한 정규식 BM25) top-50 후보를 cross-encoder
(보강 입력)로 재정렬한 뒤, NO-self·3채점관 qrels로 Hybrid 단독과 비교한다.
"최선 스택이 Hybrid냐 Hybrid+Reranker냐"를 확정하고 리랭커 fine-tune 가치를 가늠.
(경량 — Mac MPS 수 분)

산출: reports/retrieval/v3/eval_hybrid_reranked_noself.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense
from scripts.eval_noself import get, load_qrels_pooled, metrics, take_top
from app.core.config import settings
from app.evaluation.datasets import EvalQuery
from app.evaluation.metrics import RunRecord
from app.retrieval.pipeline.base import RetrievedDoc, StageInput
from app.retrieval.pipeline.stages.cross_encoder_rerank import CrossEncoderRerankStage

OUT = ROOT / "reports" / "retrieval" / "v3" / "eval_hybrid_reranked_noself.json"
DEPTH = 50       # BM25/Dense 후보 깊이 (RRF 융합용)
RERANK_IN = 50   # reranker에 넣을 Hybrid 후보 수
COLL = "civil_cases_v1"
RRF_K = 60


def rrf(runs_list, k=RRF_K):
    """Reciprocal Rank Fusion (eval_hybrid_noself.py와 동일)."""
    out: dict[str, list[RunRecord]] = {}
    qids: set[str] = set()
    for runs in runs_list:
        qids.update(runs.keys())
    for qid in qids:
        fused: dict[str, float] = {}
        for runs in runs_list:
            for r in runs.get(qid, []):
                fused[r.docid] = fused.get(r.docid, 0.0) + 1.0 / (k + r.rank)
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        out[qid] = [RunRecord(qid=qid, docid=d, score=s, rank=i) for i, (d, s) in enumerate(ranked, 1)]
    return out


def load_meta_map() -> dict[str, dict]:
    """case_id -> reranker 입력용 메타(snippet/summary/title/category/region)."""
    import chromadb

    col = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH).get_collection(COLL)
    got = col.get(include=["documents", "metadatas"])
    m: dict[str, dict] = {}
    for sid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        meta = meta or {}
        cid = str(meta.get("case_id") or sid)
        if cid in m:
            continue
        m[cid] = {
            "snippet": " ".join(str(doc or "").split())[:600],
            "summary": {
                "observation": str(meta.get("summary_observation") or ""),
                "request": str(meta.get("summary_request") or ""),
            },
            "title": str(meta.get("title") or ""),
            "category": str(meta.get("category") or ""),
            "region": str(meta.get("region") or ""),
        }
    return m


async def rerank_hybrid(hybrid, meta_map, qtext, top_k=10):
    stage = CrossEncoderRerankStage(top_k=top_k)
    out: dict[str, list[RunRecord]] = {}
    for i, (qid, recs) in enumerate(hybrid.items(), 1):
        cands = [
            RetrievedDoc(qid=qid, docid=r.docid, score=r.score, rank=r.rank,
                         stage="hybrid", metadata=meta_map.get(r.docid, {}))
            for r in sorted(recs, key=lambda x: x.rank)[:RERANK_IN]
        ]
        si = StageInput(query=EvalQuery(qid=qid, text=qtext[qid], metadata={}), candidates=cands)
        so = await stage.run(si)
        out[qid] = [RunRecord(qid=qid, docid=d.docid, score=d.score, rank=j)
                    for j, d in enumerate(so.candidates, 1)]
        if i % 20 == 0:
            print(f"  rerank {i}/{len(hybrid)}")
    return out


def main() -> None:
    R.TOP_K = DEPTH
    queries = load_queries()
    qtext = {q["query_id"]: q["query"] for q in queries}
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    qrels = load_qrels_pooled()
    qrels_noself = [q for q in qrels if self_doc.get(q.qid) != q.docid]

    corpus = load_corpus()
    print("[1] BM25...");  bm25 = run_bm25(queries, corpus)
    print("[2] Dense...");  dense = run_dense(queries)
    hybrid = rrf([bm25, dense])
    print("[3] meta_map 로드...");  meta_map = load_meta_map()
    print("[4] Hybrid+Reranker 재정렬...")
    hyrr = asyncio.run(rerank_hybrid(hybrid, meta_map, qtext))

    report = {"eval_set": "qrels_pooled_3judge, NO-self", "no_self": {}}
    for name, runs in {"Hybrid": hybrid, "Hybrid+Reranker": hyrr}.items():
        report["no_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=True), qrels_noself)
    # 참고: 기존 측정값(Dense, Dense+Reranker)
    ref_path = ROOT / "reports" / "retrieval" / "v3" / "eval_noself.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text(encoding="utf-8")).get("no_self", {})
        for k in ("Dense", "Dense+Reranker"):
            if k in ref:
                report["no_self"][f"{k}(ref)"] = ref[k]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    order = [o for o in ["Dense(ref)", "Hybrid", "Dense+Reranker(ref)", "Hybrid+Reranker"]
             if o in report["no_self"]]
    print("\n" + "=" * 78)
    print("NO-self · 3채점관 — Hybrid vs Hybrid+Reranker (+ 참고)")
    print("=" * 78)
    print(f"{'지표':<9}" + "".join(f"{o.replace('(ref)','*'):>18}" for o in order))
    for kk in ["nDCG@10", "AP@10", "R@10", "RR@5", "nDCG@5", "P@5"]:
        print(f"{kk:<9}" + "".join(f"{get(report['no_self'][o], kk):>18.4f}" for o in order))
    print("\n[순위]")
    for kk in ["nDCG@10", "AP@10", "RR@5"]:
        v = sorted(((o, get(report["no_self"][o], kk)) for o in order), key=lambda x: -x[1])
        print(f"  {kk:<8}: " + "  >  ".join(f"{o.replace('(ref)','*')}={x:.3f}" for o, x in v))
    print(f"\n[리포트] {OUT}")


if __name__ == "__main__":
    main()

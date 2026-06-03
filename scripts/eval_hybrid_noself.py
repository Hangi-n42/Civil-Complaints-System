"""
Hybrid(BM25+Dense RRF) 교정 평가. (#272)

평가셋 교정(공정 풀 + 자기참조 제거 + 3채점관) 후 BM25/Dense/Reranker는 비교했으나
Hybrid(RRF)는 미측정이었다. BM25 top-50과 Dense top-50을 RRF로 융합해 Hybrid 랭킹을
만들고, NO-self·3채점관 qrels로 BM25/Dense와 동일 기준 비교한다.
(경량 — cross-encoder·LLM 미사용, Mac에서 수 분)

산출: reports/retrieval/v3/eval_hybrid_noself.json
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense
from scripts.eval_noself import METRIC_KEYS, get, load_qrels_pooled, metrics, take_top
from app.evaluation.metrics import RunRecord

OUT = ROOT / "reports" / "retrieval" / "v3" / "eval_hybrid_noself.json"
RRF_K = 60
DEPTH = 50  # 융합용 후보 깊이


def rrf(runs_list: list[dict[str, list[RunRecord]]], k: int = RRF_K) -> dict[str, list[RunRecord]]:
    """여러 run을 Reciprocal Rank Fusion으로 융합. score = Σ 1/(k+rank)."""
    out: dict[str, list[RunRecord]] = {}
    qids = set()
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


def main() -> None:
    R.TOP_K = DEPTH  # run_bm25/run_dense가 case-level top-DEPTH 반환
    queries = load_queries()
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    qrels = load_qrels_pooled()
    qrels_noself = [q for q in qrels if self_doc.get(q.qid) != q.docid]
    print(f"qrels: {len(qrels)} → noself {len(qrels_noself)} | RRF k={RRF_K}, depth={DEPTH}")

    corpus = load_corpus()
    print("\n[1] BM25...");  bm25 = run_bm25(queries, corpus)
    print("[2] Dense...");    dense = run_dense(queries)
    print("[3] Hybrid RRF 융합...")
    hybrid = rrf([bm25, dense])

    systems = {"BM25": bm25, "Dense": dense, "Hybrid(RRF)": hybrid}
    report = {"eval_set": "qrels_pooled_3judge, NO-self", "rrf_k": RRF_K, "depth": DEPTH,
              "with_self": {}, "no_self": {}}
    for name, runs in systems.items():
        report["no_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=True), qrels_noself)
        report["with_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=False), qrels)

    # 참고: 기존 측정한 Dense+Reranker(보강) 끌어오기
    ref = ROOT / "reports" / "retrieval" / "v3" / "eval_noself.json"
    rer = None
    if ref.exists():
        rr = json.loads(ref.read_text(encoding="utf-8"))
        rer = rr.get("no_self", {}).get("Dense+Reranker")
        if rer:
            report["no_self"]["Dense+Reranker(ref)"] = rer

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("교정 평가셋(NO-self, 3채점관) — 전 검색방법 공정 비교")
    print("=" * 72)
    order = ["BM25", "Dense", "Hybrid(RRF)"] + (["Dense+Reranker(ref)"] if rer else [])
    print(f"{'지표':<9}" + "".join(f"{s.replace('Dense+Reranker(ref)','Reranker*'):>16}" for s in order))
    for k in ["nDCG@10", "AP@10", "R@10", "RR@5", "nDCG@5", "P@5"]:
        print(f"{k:<9}" + "".join(f"{get(report['no_self'][s], k):>16.4f}" for s in order))
    print("\n* Reranker는 보강입력 기준(eval_noself.json 참조값)")
    # 순위 요약
    print("\n[순위] (Reranker 포함)")
    for k in ["nDCG@10", "AP@10", "RR@5"]:
        vals = sorted(((s, get(report["no_self"][s], k)) for s in order), key=lambda x: -x[1])
        print(f"  {k:<8}: " + "  >  ".join(f"{s.replace('Dense+Reranker(ref)','Reranker')}={v:.3f}" for s, v in vals))
    print(f"\n[리포트] {OUT}")


if __name__ == "__main__":
    main()

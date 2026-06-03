"""스폿체크 재평가: 보강된 정답표가 결론을 바꾸는가 (#293).

2~3단계로 찾아 확정한 신규 누락 문서(verify_confirm.json, median≥1)를 정답표에 추가하고,
스폿체크한 **10쿼리에 한해** 검색 방법(BM25/Dense/Hybrid)을 두 정답표로 재평가한다.

  - OLD: 원래 정답표(qrels_pooled_3judge), 10쿼리로 한정
  - NEW: OLD + 확정 신규 양성(195개)

가설: 누락 문서는 BM25·Dense가 top-50 밖으로 밀어낸 것 → 어떤 방법도 top-10에 거의
올리지 못함 → precision계열(nDCG@10·P@5·RR@5) 순위는 유지, recall(R@10)만 하향(분모↑).

산출: reports/retrieval/v3/spotcheck_reeval.json (LLM 미사용, Mac 수 분)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense
from scripts.eval_noself import get, metrics, take_top
from scripts.eval_hybrid_noself import rrf
from scripts.spotcheck_full_scan import pick_queries
from app.evaluation.datasets import QrelRecord

QRELS_PATH = ROOT / "data" / "evaluation" / "v3" / "qrels_pooled_3judge.tsv"
CONFIRM_CKPT = ROOT / "data" / "evaluation" / "v3" / "checkpoints" / "verify_confirm.json"
OUT = ROOT / "reports" / "retrieval" / "v3" / "spotcheck_reeval.json"
METRIC_KEYS = ["nDCG@10", "AP@10", "RR@5", "nDCG@5", "P@5", "R@10"]
DEPTH = 50


def load_qrels(path: Path) -> list[QrelRecord]:
    out = []
    with path.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            p = line.strip().split("\t")
            if i == 0 and p[0].lower() in {"qid", "query_id"}:
                continue
            if len(p) == 4:
                out.append(QrelRecord(qid=p[0], docid=p[2], relevance=int(p[3])))
            elif len(p) == 3:
                out.append(QrelRecord(qid=p[0], docid=p[1], relevance=int(p[2])))
    return out


def main() -> None:
    R.TOP_K = DEPTH
    queries_all = load_queries()
    sel = pick_queries(queries_all)
    eval_qids = {q["query_id"] for q in sel}
    queries = [q for q in queries_all if q["query_id"] in eval_qids]
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in sel}

    # OLD qrels: 원본, 10쿼리 한정
    qrels_all = load_qrels(QRELS_PATH)
    qrels_old = [q for q in qrels_all if q.qid in eval_qids]
    old_keys = {(q.qid, q.docid) for q in qrels_old}

    # NEW: + 확정 신규 양성 (median>=1, 풀 밖)
    confirm = json.loads(CONFIRM_CKPT.read_text(encoding="utf-8"))
    added = []
    for key, rec in confirm.items():
        qid, docid = key.split("::", 1)
        rel = rec.get("rel", 0)
        if qid in eval_qids and rel >= 1 and (qid, docid) not in old_keys:
            added.append(QrelRecord(qid=qid, docid=docid, relevance=rel))
    qrels_new = qrels_old + added
    print(f"10쿼리 | OLD qrels {len(qrels_old)} → NEW {len(qrels_new)} (신규 양성 +{len(added)})")

    # no-self
    def noself(qrels):
        return [q for q in qrels if self_doc.get(q.qid) != q.docid]
    qrels_old_ns, qrels_new_ns = noself(qrels_old), noself(qrels_new)

    corpus = load_corpus()
    print("[1] BM25..."); bm25 = run_bm25(queries, corpus)
    print("[2] Dense..."); dense = run_dense(queries)
    hybrid = rrf([bm25, dense])
    systems = {"BM25": bm25, "Dense": dense, "Hybrid": hybrid}

    report = {"n_queries": len(queries), "query_ids": sorted(eval_qids),
              "n_added_positives": len(added), "old": {}, "new": {}}
    for name, runs in systems.items():
        top = take_top(runs, self_doc, 10, drop_self=True)
        report["old"][name] = metrics(top, qrels_old_ns)
        report["new"][name] = metrics(top, qrels_new_ns)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"재평가: OLD vs NEW(누락 보강) — 10쿼리, NO-self  (신규 양성 +{len(added)})")
    print("=" * 78)
    for key in METRIC_KEYS:
        print(f"\n[{key}]  {'방법':<10}{'OLD':>10}{'NEW':>10}{'변화':>10}")
        for name in systems:
            o = get(report["old"][name], key); n = get(report["new"][name], key)
            print(f"  {'':<10}{name:<10}{o:>10.4f}{n:>10.4f}{n-o:>+10.4f}")
    # 순위 비교 (nDCG@10 기준)
    def rank_order(tbl):
        return [n for n, _ in sorted(((nm, get(tbl[nm], "nDCG@10")) for nm in systems),
                                     key=lambda x: -x[1])]
    print(f"\n[순위 nDCG@10] OLD: {' > '.join(rank_order(report['old']))}")
    print(f"             NEW: {' > '.join(rank_order(report['new']))}")
    print(f"[리포트] {OUT}")


if __name__ == "__main__":
    main()

"""
자기참조(self-reference) 제거 평가.

현재 평가셋은 쿼리가 특정 출처 문서(CASE-source_id)에서 파생됐고 그 문서가 rel=2 정답이라
"똑같은 쌍둥이 찾기"를 측정한다(RR≈1.0). 이를 교정하기 위해, 각 쿼리의 출처 문서가
코퍼스에 없는 것처럼 취급한다:
  - 검색 결과(run)에서 self-doc 제외 후 top-10
  - qrels에서도 (qid, self-doc) 쌍 제거
→ "다른 유용한 사례 찾기"라는 실제 과제를 측정.

정답셋: qrels_pooled.tsv (공정 풀). BM25 / Dense / Dense+Reranker 3종을
  WITH-self(기존 방식) vs NO-self(교정) 로 나란히 비교한다.

산출: reports/retrieval/v3/eval_noself.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense, run_pipeline
from scripts.reranker_diagnosis import normalize_to_case
from app.evaluation.metrics import RunRecord, evaluate_run
from app.evaluation.datasets import QrelRecord

NOSELF_YAML = ROOT / "configs" / "retrieval_pipelines" / "dense_reranked_noself.yaml"
OUT = ROOT / "reports" / "retrieval" / "v3" / "eval_noself.json"
METRIC_KEYS = ["RR@5", "RR@10", "nDCG@5", "nDCG@10", "AP@10", "R@10", "P@5"]


def get(m: dict, key: str) -> float:
    for k, v in m.items():
        if k.lower() == key.lower():
            return float(v)
    return 0.0


def load_qrels_pooled() -> list[QrelRecord]:
    out = []
    fname = os.getenv("QRELS_POOLED_FILE", "qrels_pooled.tsv")
    path = ROOT / "data" / "evaluation" / "v3" / fname
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


def take_top(runs: dict[str, list[RunRecord]], self_doc: dict[str, str], k: int, drop_self: bool):
    """각 쿼리 run을 rank순 정렬 → (옵션)self 제거 → 상위 k → rank 재부여."""
    out: dict[str, list[RunRecord]] = {}
    for qid, recs in runs.items():
        s = self_doc.get(qid)
        ordered = sorted(recs, key=lambda x: x.rank)
        if drop_self:
            ordered = [r for r in ordered if r.docid != s]
        out[qid] = [RunRecord(qid=qid, docid=r.docid, score=r.score, rank=i)
                    for i, r in enumerate(ordered[:k], 1)]
    return out


def metrics(runs: dict[str, list[RunRecord]], qrels: list[QrelRecord]) -> dict:
    flat = [r for recs in runs.values() for r in recs]
    return evaluate_run(qrels, flat)


def main() -> None:
    queries = load_queries()
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    qrels_pooled = load_qrels_pooled()
    qrels_noself = [q for q in qrels_pooled if self_doc.get(q.qid) != q.docid]
    print(f"qrels: pooled {len(qrels_pooled)} → noself {len(qrels_noself)} "
          f"(self 쌍 {len(qrels_pooled)-len(qrels_noself)} 제거)")

    R.TOP_K = 20  # 버퍼 확보 (self 제거 후 top-10 보장)
    corpus = load_corpus()
    print("\n[1] BM25...");      bm25 = run_bm25(queries, corpus)
    print("[2] Dense...");        dense = run_dense(queries)
    print("[3] Dense+Reranker..."); rer = normalize_to_case(run_pipeline(queries, NOSELF_YAML))

    systems = {"BM25": bm25, "Dense": dense, "Dense+Reranker": rer}
    report = {"eval_set": "qrels_pooled (공정 풀)", "with_self": {}, "no_self": {}}
    for name, runs in systems.items():
        report["with_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=False), qrels_pooled)
        report["no_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=True), qrels_noself)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print("자기참조 제거 효과: WITH-self(기존) vs NO-self(교정)")
    print("=" * 78)
    for key in METRIC_KEYS:
        print(f"\n[{key}]")
        print(f"  {'시스템':<16}{'WITH-self':>12}{'NO-self':>12}{'변화':>10}")
        for name in systems:
            w = get(report["with_self"][name], key)
            n = get(report["no_self"][name], key)
            print(f"  {name:<16}{w:>12.4f}{n:>12.4f}{n-w:>+10.4f}")
    print(f"\n[리포트] {OUT}")


if __name__ == "__main__":
    main()

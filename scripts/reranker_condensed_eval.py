"""
reranker vs Dense 공정 재평가 (pooling-bias 제거).

reranker_diagnosis.json은 reranker top-10의 16~24%가 미판정(qrels 부재 → rel=0 처리)
이라는 점을 보였다. 표준 metric은 그 미판정 문서를 모두 오답으로 간주하므로
"reranker가 Dense에 진다"는 결론이 평가 artifact인지 실제 성능 차이인지 구분되지 않는다.

이 스크립트는 동일 run을 재생성해 그 둘을 분리한다:
  1. run을 TREC 파일로 저장 (재현성 — 기존엔 run이 디스크에 남지 않았다)
  2. 표준 metric (미판정=오답, reranker 하한)
     vs condensed-list metric (각 run에서 미판정 문서 제거 후 채점)
     → 두 격차의 차이 = pooling-bias가 만든 artifact 크기
  3. reranker top-10 미판정 문서를 worklist CSV로 추출 (재라벨 대상 목록)

해석:
  - 표준 격차 = (top-10 밖으로 밀려난 known-positive 손실) + (미판정 filler 손실)
  - condensed 격차 = known-positive 손실만 (미판정 filler 제거됨)
  - 차이 = 미판정 filler가 만든 순수 artifact
  - 단, run이 top-10 고정이라 condensed는 rank-position 지표(nDCG/AP/P) 교정에 유효하고
    Recall 깊이는 교정하지 못한다. 미판정 문서의 실제 관련성은 worklist 재라벨로만 확정된다.

산출:
  reports/retrieval/v3/runs/{dense,reranker}.trec
  reports/retrieval/v3/reranker_condensed_eval.json
  reports/retrieval/v3/reranker_unjudged_worklist.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    compute_metrics,
    load_qrels,
    load_queries,
    run_dense,
    run_pipeline,
)
from scripts.reranker_diagnosis import PIPELINE, normalize_to_case
from app.evaluation.metrics import RunRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "retrieval" / "v3"
RUNS_DIR = OUT / "runs"

METRIC_KEYS = ["nDCG@5", "nDCG@10", "AP@10", "R@10", "R@5", "P@5"]


def get(metrics: dict[str, float], key: str) -> float:
    for k, v in metrics.items():
        if key.lower() == k.lower():
            return float(v)
    return 0.0


def condense(runs: dict[str, list[RunRecord]], qrels_by_q: dict[str, dict[str, int]]) -> dict[str, list[RunRecord]]:
    """각 쿼리 run에서 qrels에 없는(미판정) 문서를 제거. 점수·상대순서는 유지."""
    out: dict[str, list[RunRecord]] = {}
    for qid, recs in runs.items():
        judged = qrels_by_q.get(qid, {})
        kept = [r for r in sorted(recs, key=lambda x: x.rank) if r.docid in judged]
        out[qid] = [
            RunRecord(qid=qid, docid=r.docid, score=r.score, rank=i)
            for i, r in enumerate(kept, 1)
        ]
    return out


def unjudged_rate(runs: dict[str, list[RunRecord]], qrels_by_q: dict[str, dict[str, int]], k: int) -> float:
    total = unj = 0
    for qid, recs in runs.items():
        for r in sorted(recs, key=lambda x: x.rank)[:k]:
            total += 1
            if r.docid not in qrels_by_q.get(qid, {}):
                unj += 1
    return unj / max(1, total)


def write_trec(runs: dict[str, list[RunRecord]], path: Path, tag: str) -> None:
    lines = []
    for qid, recs in runs.items():
        for r in sorted(recs, key=lambda x: x.rank):
            lines.append(f"{qid}\tQ0\t{r.docid}\t{r.rank}\t{r.score:.6f}\t{tag}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_worklist(
    reranker: dict[str, list[RunRecord]],
    qrels_by_q: dict[str, dict[str, int]],
    queries_by_id: dict[str, str],
    path: Path,
    k: int = 10,
) -> int:
    rows = []
    for qid, recs in reranker.items():
        judged = qrels_by_q.get(qid, {})
        for r in sorted(recs, key=lambda x: x.rank)[:k]:
            if r.docid not in judged:
                rows.append((qid, r.docid, r.rank, round(r.score, 4)))
    rows.sort(key=lambda x: (x[0], x[2]))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "docid", "reranker_rank", "reranker_score", "relevance_TODO", "query"])
        for qid, docid, rank, score in rows:
            w.writerow([qid, docid, rank, score, "", queries_by_id.get(qid, "")[:120]])
    return len(rows)


def main() -> None:
    queries = load_queries()
    qrels = load_qrels()
    queries_by_id = {q["query_id"]: q["query"] for q in queries}
    qrels_by_q: dict[str, dict[str, int]] = defaultdict(dict)
    for q in qrels:
        qrels_by_q[q.qid][q.docid] = q.relevance
    print(f"쿼리 {len(queries)} / qrels {len(qrels)}")

    print("\n[1] Dense run 생성...")
    dense = normalize_to_case(run_dense(queries))
    print("[2] Reranker run 생성 (cross-encoder)...")
    reranker = normalize_to_case(run_pipeline(queries, PIPELINE))

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    write_trec(dense, RUNS_DIR / "dense.trec", "dense")
    write_trec(reranker, RUNS_DIR / "reranker.trec", "reranker")
    print(f"[3] run 저장: {RUNS_DIR}/dense.trec, reranker.trec")

    # 표준 metric (미판정=오답)
    std = {"dense": compute_metrics(dense, qrels), "reranker": compute_metrics(reranker, qrels)}
    # condensed metric (미판정 제거)
    dense_c = condense(dense, qrels_by_q)
    reranker_c = condense(reranker, qrels_by_q)
    cond = {"dense": compute_metrics(dense_c, qrels), "reranker": compute_metrics(reranker_c, qrels)}

    worklist_n = write_worklist(reranker, qrels_by_q, queries_by_id, OUT / "reranker_unjudged_worklist.csv")

    report = {
        "eval_set": "V3 (qrels.tsv, 100쿼리)",
        "pipeline": str(PIPELINE.relative_to(ROOT)),
        "unjudged_rate": {
            "top10": {"dense": unjudged_rate(dense, qrels_by_q, 10), "reranker": unjudged_rate(reranker, qrels_by_q, 10)},
            "top5": {"dense": unjudged_rate(dense, qrels_by_q, 5), "reranker": unjudged_rate(reranker, qrels_by_q, 5)},
        },
        "standard": std,
        "condensed": cond,
        "worklist_unjudged_pairs": worklist_n,
    }
    (OUT / "reranker_condensed_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── 출력 ──
    print("\n" + "=" * 78)
    print("공정 재평가: 표준(미판정=오답) vs condensed(미판정 제거)")
    print("=" * 78)
    print(f"{'지표':<10}{'Dense':>9}{'Rerank':>9}{'Δstd':>9} │{'Dense_c':>9}{'Rerank_c':>10}{'Δcond':>9} │{'artifact':>10}")
    for key in METRIC_KEYS:
        d_s, r_s = get(std["dense"], key), get(std["reranker"], key)
        d_c, r_c = get(cond["dense"], key), get(cond["reranker"], key)
        gap_s = d_s - r_s   # +면 reranker가 짐
        gap_c = d_c - r_c
        artifact = gap_s - gap_c  # +면 그만큼이 pooling-bias artifact
        print(f"{key:<10}{d_s:>9.4f}{r_s:>9.4f}{gap_s:>+9.4f} │{d_c:>9.4f}{r_c:>10.4f}{gap_c:>+9.4f} │{artifact:>+10.4f}")
    print(f"\n[미판정율 top-10] Dense {report['unjudged_rate']['top10']['dense']:.3f} "
          f"vs Reranker {report['unjudged_rate']['top10']['reranker']:.3f}")
    print(f"[재라벨 worklist] reranker top-10 미판정 {worklist_n}건 → {OUT}/reranker_unjudged_worklist.csv")
    print(f"[리포트] {OUT}/reranker_condensed_eval.json")


if __name__ == "__main__":
    main()

"""
reranker가 Dense에 지는 원인 심화 분석

#262 결과: Dense+Reranker nDCG@5(0.824) < Dense(0.897), Recall@10도 하락.
원인이 (A) qrels가 Dense에 편향되어 reranker가 찾은 좋은 문서가 unjudged(0점) 처리되는가,
(B) reranker가 실제로 관련 문서를 더 낮게 매기는가 를 규명한다.

세 분석:
  1. unjudged rate — 각 run top-k에서 qrels 미판정 docid 비율 (A 가설)
  2. rank displacement — Dense top-5 positive(rel>=1)를 reranker가 어디로 보내는가 (B 가설)
  3. per-query win/loss — reranker가 이기는/지는 쿼리 분포

산출: reports/retrieval/v3/reranker_diagnosis.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries, load_qrels, run_dense, run_pipeline,
    chunk_to_case, build_run, compute_metrics, TOP_K,
)
from app.evaluation.metrics import RunRecord, per_query_metric
from ir_measures import nDCG, Recall

REPORT = Path(__file__).resolve().parents[1] / "reports" / "retrieval" / "v3" / "reranker_diagnosis.json"
PIPELINE = Path(__file__).resolve().parents[1] / "configs" / "retrieval_pipelines" / "dense_reranked.yaml"


def normalize_to_case(runs: dict[str, list[RunRecord]]) -> dict[str, list[RunRecord]]:
    """run의 docid를 case 레벨로 dedup (rank 순서 유지, case당 최상위)."""
    out: dict[str, list[RunRecord]] = {}
    for qid, recs in runs.items():
        seen: set = set()
        ordered: list[tuple[str, float]] = []
        for r in sorted(recs, key=lambda x: x.rank):
            cid = chunk_to_case(r.docid)
            if cid in seen:
                continue
            seen.add(cid)
            ordered.append((cid, r.score))
        out[qid] = build_run(qid, ordered)
    return out


def flatten(runs: dict[str, list[RunRecord]]) -> list[RunRecord]:
    return [r for recs in runs.values() for r in recs]


def unjudged_rate(runs, qrels_by_q, k):
    total = unj = 0
    per_q = {}
    for qid, recs in runs.items():
        q_unj = 0
        topk = recs[:k]
        for r in topk:
            total += 1
            if r.docid not in qrels_by_q.get(qid, {}):
                unj += 1
                q_unj += 1
        per_q[qid] = q_unj / max(1, len(topk))
    return unj / max(1, total), per_q


def main() -> None:
    queries = load_queries()
    qrels = load_qrels()
    qrels_by_q: dict[str, dict[str, int]] = defaultdict(dict)
    for q in qrels:
        qrels_by_q[q.qid][q.docid] = q.relevance
    print(f"쿼리 {len(queries)} / qrels {len(qrels)}")

    print("\n[1] Dense run 생성...")
    dense = normalize_to_case(run_dense(queries))
    print("[2] Reranker run 생성 (cross-encoder, 최초 모델 다운로드 가능)...")
    reranker = normalize_to_case(run_pipeline(queries, PIPELINE))

    # 집계 지표 (재현 확인용)
    dm = compute_metrics(dense, qrels)
    rm = compute_metrics(reranker, qrels)

    def g(d, k):
        return next((v for kk, v in d.items() if k.lower() in kk.lower() and "rr" not in kk.lower()[:3]), 0.0)

    # ── 분석 1: unjudged rate ──
    print("\n[3] unjudged rate 분석...")
    d_unj5, _ = unjudged_rate(dense, qrels_by_q, 5)
    r_unj5, _ = unjudged_rate(reranker, qrels_by_q, 5)
    d_unj10, _ = unjudged_rate(dense, qrels_by_q, 10)
    r_unj10, _ = unjudged_rate(reranker, qrels_by_q, 10)

    # ── 분석 2: rank displacement ──
    # Dense top-5의 positive(rel>=1) docid가 reranker run에서 몇 위인지
    print("[4] rank displacement 분석...")
    disp = {"kept_top5": 0, "demoted_in_top10": 0, "dropped_out_top10": 0, "total_positives": 0}
    examples = []
    for qid, drecs in dense.items():
        rpos = {r.docid: r.rank for r in reranker.get(qid, [])}
        for r in drecs[:5]:
            if qrels_by_q.get(qid, {}).get(r.docid, 0) >= 1:
                disp["total_positives"] += 1
                rr = rpos.get(r.docid)
                if rr is None:
                    disp["dropped_out_top10"] += 1
                    if len(examples) < 8:
                        examples.append({"qid": qid, "docid": r.docid, "dense_rank": r.rank,
                                         "rel": qrels_by_q[qid][r.docid], "reranker_rank": "dropped"})
                elif rr <= 5:
                    disp["kept_top5"] += 1
                else:
                    disp["demoted_in_top10"] += 1

    # ── 분석 3: per-query nDCG@5 win/loss ──
    print("[5] per-query win/loss 분석...")
    d_pq = per_query_metric(qrels, flatten(dense), nDCG @ 5)
    r_pq = per_query_metric(qrels, flatten(reranker), nDCG @ 5)
    wins = losses = ties = 0
    loss_examples = []
    for qid in d_pq:
        diff = r_pq.get(qid, 0.0) - d_pq.get(qid, 0.0)
        if diff > 0.01:
            wins += 1
        elif diff < -0.01:
            losses += 1
            loss_examples.append((qid, round(diff, 3), round(d_pq[qid], 3), round(r_pq.get(qid, 0.0), 3)))
        else:
            ties += 1
    loss_examples.sort(key=lambda x: x[1])

    # ── 출력 ──
    print("\n" + "=" * 64)
    print("reranker 진단 결과")
    print("=" * 64)
    print(f"{'지표':<14}{'Dense':>10}{'Reranker':>12}{'Δ':>10}")
    for k in ["nDCG@5", "nDCG@10", "R@10"]:
        print(f"{k:<14}{g(dm,k):>10.4f}{g(rm,k):>12.4f}{g(rm,k)-g(dm,k):>+10.4f}")
    print(f"\n[unjudged rate] top-5:  Dense {d_unj5:.3f} vs Reranker {r_unj5:.3f}  (Δ={r_unj5-d_unj5:+.3f})")
    print(f"[unjudged rate] top-10: Dense {d_unj10:.3f} vs Reranker {r_unj10:.3f}  (Δ={r_unj10-d_unj10:+.3f})")
    print(f"\n[rank displacement] Dense top-5의 positive {disp['total_positives']}개를 reranker가:")
    tp = max(1, disp['total_positives'])
    print(f"  top-5 유지:       {disp['kept_top5']:>4} ({disp['kept_top5']/tp:.1%})")
    print(f"  6~10위로 강등:    {disp['demoted_in_top10']:>4} ({disp['demoted_in_top10']/tp:.1%})")
    print(f"  top-10 밖 탈락:   {disp['dropped_out_top10']:>4} ({disp['dropped_out_top10']/tp:.1%})")
    print(f"\n[per-query nDCG@5] reranker 승 {wins} / 패 {losses} / 무 {ties} (총 {len(d_pq)})")
    print(f"  최대 손실 쿼리(qid, Δ, dense, reranker): {loss_examples[:5]}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "metrics": {"dense": dm, "reranker": rm},
        "unjudged_rate": {
            "top5": {"dense": d_unj5, "reranker": r_unj5},
            "top10": {"dense": d_unj10, "reranker": r_unj10},
        },
        "rank_displacement": disp,
        "displacement_examples": examples,
        "per_query": {"reranker_wins": wins, "reranker_losses": losses, "ties": ties,
                      "worst_losses": loss_examples[:10]},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT}")


if __name__ == "__main__":
    main()

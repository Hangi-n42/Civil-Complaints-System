"""부서 soft rerank 가점(weight) 스윕 — hybrid 점수 스케일 불일치 보정 검증.

#369 후속. 현재 부서 가점은 +0.03 고정인데, dense 점수(~0.7)엔 적당하지만 hybrid RRF
점수(~0.03)엔 과도해 순위를 헝클어뜨린다(LLM 보강 평가에서 hybrid 음수). 이 스크립트는
가점 weight 를 여러 값으로 스윕해, LLM 보강 qrels 기준으로 dept 가 base 대비 개선되는
weight 가 있는지 확인한다.

캐시 재활용: 부서 예측(_cache_freshdoc_dept.json), LLM 판단(_cache_llm_judge.json).
원문 미포함(집계만).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord, sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries, ordered_metric_keys

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEPT_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_freshdoc_dept.json"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge.json"
OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_boost_weight_tuning.json"
OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_boost_weight_tuning.md"
WEIGHTS = [0.0, 0.002, 0.005, 0.01, 0.02, 0.03]


def rerank_w(pool: list[tuple[str, float]], qdept: set[str], doc_dept: dict[str, list[str]], w: float) -> list[tuple[str, float]]:
    out = [(cid, sc + (w if (qdept & set(doc_dept.get(cid, []))) else 0.0)) for cid, sc in pool]
    return sorted(out, key=lambda r: r[1], reverse=True)


def records(qid: str, ranked: list[tuple[str, float]], top_k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:top_k], start=1)]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", default="civil_cases_v1")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--pool-size", type=int, default=100)
    p.add_argument("--top-n-units", type=int, default=3)
    p.add_argument("--strategies", nargs="+", default=["dense", "hybrid"])
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()
    queries = load_queries(DEFAULT_QUERIES)
    qrels = load_qrels(DEFAULT_QRELS)
    judged_by_qid: dict[str, dict[str, int]] = {}
    for row in qrels:
        judged_by_qid.setdefault(row.qid, {})[row.docid] = row.relevance
    rel_qids = {qid for qid, d in judged_by_qid.items() if any(r > 0 for r in d.values())}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    eval_qrels = [r for r in qrels if r.qid in rel_qids]

    # 보강 qrels = 원 + LLM 판단
    judge_cache = json.loads(JUDGE_CACHE.read_text()) if JUDGE_CACHE.exists() else {}
    aug_qrels = list(eval_qrels)
    for key, rel in judge_cache.items():
        qid, cid = key.split("||", 1)
        if qid in rel_qids:
            aug_qrels.append(QrelRecord(qid=qid, docid=cid, relevance=int(rel)))

    fresh_dept = json.loads(DEPT_CACHE.read_text()) if DEPT_CACHE.exists() else {}
    assigner = get_department_assigner(); assigner.build_index(rebuild=False)
    qdept = {q["query_id"]: {c["name"] for c in assigner.assign(q["query"], top_n_units=args.top_n_units) if c.get("name")} for q in judged}

    service = RetrievalService()
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection, "judged_query_count": len(judged),
        "pool_size": args.pool_size, "top_k": args.top_k, "weights": WEIGHTS,
        "qrels_sha256": sha256_file(DEFAULT_QRELS), "eval_qrels": "augmented (orig + LLM judge)",
        "strategies": {},
    }
    for strat in args.strategies:
        pools = {}
        for i, q in enumerate(judged, start=1):
            res = await service.search(query=q["query"], top_k=args.pool_size, collection_name=args.collection,
                                       strategy=strat, grounding_filter=False, query_signals=None)
            pools[q["query_id"]] = dedup_results(res, top_k=args.pool_size)
            if i % 20 == 0:
                print(f"[pool:{strat}] {i}/{len(judged)}")
        rows = []
        base_metric = None
        for w in WEIGHTS:
            runs = []
            for qid, pool in pools.items():
                runs += records(qid, rerank_w(pool, qdept.get(qid, set()), fresh_dept, w), args.top_k)
            m = evaluate_run(aug_qrels, runs)
            if w == 0.0:
                base_metric = m
            rows.append({"weight": w, "nDCG@10": m.get("nDCG@10", 0.0), "R@10": m.get("R@10", 0.0), "AP@10": m.get("AP@10", 0.0)})
        for r in rows:
            r["dNDCG@10"] = r["nDCG@10"] - base_metric.get("nDCG@10", 0.0)
        payload["strategies"][strat] = {"rows": rows}
        print(f"[{strat}] " + " | ".join(f"w={r['weight']}:{r['dNDCG@10']:+.4f}" for r in rows))

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 부서 가점 weight 스윕 (LLM 보강 qrels 기준)", "",
             f"- 평가 쿼리 {len(judged)}건, 풀 top-{args.pool_size}, 평가 top-{args.top_k}, qrels=보강(원+LLM)", "",
             "weight=0 은 base(부서 미적용). Δ는 base 대비 nDCG@10 변화.", ""]
    for strat in args.strategies:
        lines += [f"## {strat.upper()}", "", "| weight | nDCG@10 | ΔnDCG@10 | R@10 | AP@10 |", "| ---: | ---: | ---: | ---: | ---: |"]
        for r in payload["strategies"][strat]["rows"]:
            lines.append(f"| {r['weight']} | {r['nDCG@10']:.4f} | {r['dNDCG@10']:+.4f} | {r['R@10']:.4f} | {r['AP@10']:.4f} |")
        lines.append("")
    lines += ["## 해석", "- Δ가 최대인 weight 가 해당 전략 최적. hybrid 에서 0.03 보다 작은 weight 가 +면 스케일 보정 효과 확인.", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {OUT_JSON}")
    print(f"[WRITE] {OUT_MD}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

"""풀링 편향을 줄인 condensed-list 공정 비교: base vs dept(old/fresh).

#369 후속. v3 qrels 가 후보 풀의 ~20%만 채점해 부서가 끌어올린 무라벨 문서가 자동 오답
처리되는 풀링 편향이 확인됐다(audit). 이 스크립트는 각 랭킹에서 **무라벨 문서를 제거하고
채점된 문서만 남겨**(condensed list; Sakai 2007) base/dept 를 동일 조건으로 비교한다.
이는 "부서 가점이 채점된 문서들의 상대 순서를 개선하는가"를 격리 측정한다.
(부서의 무라벨 문서 발굴 효과는 별도 LLM 채점으로만 평가 가능 — 본 스크립트 범위 밖.)

개인정보: 산출물에 원문 미포함(집계·case_id 만).
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

from app.evaluation.datasets import sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries, ordered_metric_keys
from scripts.eval_responsible_unit_freshdoc_simulation import build_doc_text_map, predict_departments, rerank

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_condensed_eval.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_condensed_eval.md"
CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_freshdoc_dept.json"


def condensed_records(qid: str, ranked: list[tuple[str, float]], judged: dict[str, int], top_k: int) -> list[RunRecord]:
    kept = [(cid, sc) for cid, sc in ranked if cid in judged]
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(kept[:top_k], start=1)]


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# 부서 신호 — condensed-list 공정 비교 (풀링 편향 완화)",
        "",
        "## 방법",
        "각 랭킹에서 무라벨 문서를 제거하고 채점된 문서만으로 base/dept 를 동일 조건 비교한다.",
        "부서 가점이 **채점된 문서들의 상대 순서**를 개선하는지 격리 측정(무라벨 발굴 효과는 범위 밖).",
        "",
        f"- 컬렉션 `{payload['collection']}`, 평가 쿼리 {payload['judged_query_count']}건, 풀 top-{payload['pool_size']}, 평가 top-{payload['top_k']}",
        "",
    ]
    for strat in payload["strategies"]:
        m = payload["strategies"][strat]
        lines.extend([
            f"## {strat.upper()} (condensed)",
            "",
            "| 지표 | base | dept_old | dept_fresh | Δ(old) | Δ(fresh) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for k in m["metric_keys"]:
            b = m["metrics"]["base"].get(k, 0.0)
            o = m["metrics"]["dept_old"].get(k, 0.0)
            f = m["metrics"]["dept_fresh"].get(k, 0.0)
            lines.append(f"| {k} | {_fmt(b)} | {_fmt(o)} | {_fmt(f)} | {o-b:+.4f} | {f-b:+.4f} |")
        lines.append("")
    lines.extend([
        "## 해석",
        "- Δ(fresh) 가 양수면: 최신 부서 태그가 **채점된 문서 순서**를 실제로 개선 → 부서 신호 유효 근거.",
        "- Δ 가 ~0/음수면: 부서는 채점 문서 재정렬에는 도움 안 됨(가치가 있다면 무라벨 발굴 쪽 → LLM 채점 필요).",
        "- 이 비교는 무라벨 발굴 효과를 제외하므로 부서 가치의 **하한**에 가깝다.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", default="civil_cases_v1")
    p.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    p.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--pool-size", type=int, default=100)
    p.add_argument("--top-n-units", type=int, default=3)
    p.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    p.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()
    queries = load_queries(args.queries)
    qrels = load_qrels(args.qrels)
    judged_by_qid: dict[str, dict[str, int]] = {}
    for row in qrels:
        judged_by_qid.setdefault(row.qid, {})[row.docid] = row.relevance
    rel_qids = {qid for qid, d in judged_by_qid.items() if any(r > 0 for r in d.values())}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    eval_qrels = [r for r in qrels if r.qid in rel_qids]

    assigner = get_department_assigner()
    assigner.build_index(rebuild=False)
    qdept = {q["query_id"]: {c["name"] for c in assigner.assign(q["query"], top_n_units=args.top_n_units) if c.get("name")} for q in judged}

    service = RetrievalService()
    pools_by_strat: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for strat in args.strategies:
        pools: dict[str, list[tuple[str, float]]] = {}
        for i, q in enumerate(judged, start=1):
            results = await service.search(query=q["query"], top_k=args.pool_size, collection_name=args.collection,
                                           strategy=strat, grounding_filter=False, query_signals=None)
            pools[q["query_id"]] = dedup_results(results, top_k=args.pool_size)
            if i % 10 == 0:
                print(f"[pool:{strat}] {i}/{len(judged)}")
        pools_by_strat[strat] = pools

    candidate_ids = {cid for pools in pools_by_strat.values() for pool in pools.values() for cid, _ in pool}
    text_map, old_dept = build_doc_text_map(args.collection)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    missing = {cid: text_map.get(cid, "") for cid in candidate_ids if cid not in cache}
    if missing:
        print(f"[predict] 신규 {len(missing)}건 (캐시 {len(cache)}건)")
        cache.update(predict_departments(missing, top_n_units=args.top_n_units))
        CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    fresh_dept = {cid: cache.get(cid, []) for cid in candidate_ids}

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "qrels_sha256": sha256_file(args.qrels),
        "judged_query_count": len(judged),
        "pool_size": args.pool_size,
        "top_k": args.top_k,
        "strategies": {},
    }
    for strat in args.strategies:
        pools = pools_by_strat[strat]
        runs = {"base": [], "dept_old": [], "dept_fresh": []}
        for qid, pool in pools.items():
            judged_map = judged_by_qid.get(qid, {})
            qd = qdept.get(qid, set())
            runs["base"] += condensed_records(qid, pool, judged_map, args.top_k)
            runs["dept_old"] += condensed_records(qid, rerank(pool, qd, old_dept), judged_map, args.top_k)
            runs["dept_fresh"] += condensed_records(qid, rerank(pool, qd, fresh_dept), judged_map, args.top_k)
        metrics = {name: evaluate_run(eval_qrels, rec) for name, rec in runs.items()}
        payload["strategies"][strat] = {"metric_keys": ordered_metric_keys(*metrics.values()), "metrics": metrics}

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"[WRITE] {args.out_json}")
    print(f"[WRITE] {args.out_md}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

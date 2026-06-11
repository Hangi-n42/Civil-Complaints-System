"""부서 신호 평가가 부서를 부당하게 깎는지(특히 풀링 편향) 감사한다.

#369 후속. "부서를 쓰면 검색이 좋아져야 한다"는 직관과 평가 결과가 어긋나, 평가 파이프라인
자체를 점검한다. 가장 유력한 의심은 풀링 편향: qrels(정답 라벨)가 부서 신호 없이 만들어져,
부서가 관련 문서를 top-10 으로 끌어올려도 그 문서가 라벨에 없으면(unjudged) 자동으로
오답(rel=0)으로 처리되어 지표가 떨어진다.

측정(넓은 풀 top-N 에서 fresh 부서 가점 재랭킹):
1) 라벨 밀도: 후보 풀 중 judged 비율, 평가 쿼리당 라벨 수.
2) 승격/강등 분석: base top-10 대비 dept_fresh top-10 에서
   - 새로 진입(promoted)한 문서가 judged-relevant / judged-nonrel / UNJUDGED 중 무엇인지
   - 빠진(demoted) 문서는 무엇인지
   promoted 의 UNJUDGED 비율이 높으면 = 풀링 편향으로 부서가 부당하게 깎임.
3) 무라벨 승격을 중립 처리(평가 제외)했을 때 지표 변화 추정.

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
from app.evaluation.metrics import evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries
from scripts.eval_responsible_unit_freshdoc_simulation import (
    build_doc_text_map,
    predict_departments,
    rerank,
    run_to_records,
)

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_eval_pipeline_audit.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_eval_pipeline_audit.md"


def classify(docid: str, judged: dict[str, int]) -> str:
    if docid not in judged:
        return "unjudged"
    return "judged_rel" if judged[docid] > 0 else "judged_nonrel"


def analyze_promotion(
    pools: dict[str, list[tuple[str, float]]],
    qdept: dict[str, set[str]],
    judged_by_qid: dict[str, dict[str, int]],
    doc_dept: dict[str, list[str]],
    top_k: int,
) -> dict[str, Any]:
    promoted = {"judged_rel": 0, "judged_nonrel": 0, "unjudged": 0}
    demoted = {"judged_rel": 0, "judged_nonrel": 0, "unjudged": 0}
    pool_judged = 0
    pool_total = 0
    for qid, pool in pools.items():
        judged = judged_by_qid.get(qid, {})
        for cid, _ in pool:
            pool_total += 1
            if cid in judged:
                pool_judged += 1
        base_top = [cid for cid, _ in pool[:top_k]]
        rer = rerank(pool, qdept.get(qid, set()), doc_dept)
        dept_top = [cid for cid, _ in rer[:top_k]]
        for cid in set(dept_top) - set(base_top):
            promoted[classify(cid, judged)] += 1
        for cid in set(base_top) - set(dept_top):
            demoted[classify(cid, judged)] += 1
    prom_total = sum(promoted.values())
    demo_total = sum(demoted.values())
    return {
        "pool_total_candidates": pool_total,
        "pool_judged_candidates": pool_judged,
        "pool_judged_rate": round(pool_judged / pool_total, 4) if pool_total else 0.0,
        "promoted_total": prom_total,
        "promoted": promoted,
        "promoted_unjudged_rate": round(promoted["unjudged"] / prom_total, 4) if prom_total else 0.0,
        "promoted_judged_rel_share_of_judged": (
            round(promoted["judged_rel"] / (promoted["judged_rel"] + promoted["judged_nonrel"]), 4)
            if (promoted["judged_rel"] + promoted["judged_nonrel"]) else None
        ),
        "demoted_total": demo_total,
        "demoted": demoted,
    }


def evaluate_excluding_unjudged_promotions(
    pools: dict[str, list[tuple[str, float]]],
    qdept: dict[str, set[str]],
    judged_by_qid: dict[str, dict[str, int]],
    doc_dept: dict[str, list[str]],
    eval_qrels: list[Any],
    top_k: int,
) -> dict[str, Any]:
    """무라벨로 승격된 문서를 평가에서 제외(중립)했을 때 지표를 재계산한다.

    풀링 편향 보정의 보수적 근사: dept_fresh 가 top-k 로 올린 무라벨 문서를 결과에서 빼고
    그 자리를 다음 후보로 채워 평가한다. unjudged 가 정답일 수도 있으므로 이는 하한(보수적)이다.
    """
    base_runs, dept_runs, dept_adj_runs = [], [], []
    for qid, pool in pools.items():
        judged = judged_by_qid.get(qid, {})
        qd = qdept.get(qid, set())
        base_runs += run_to_records(qid, pool, top_k)
        rer = rerank(pool, qd, doc_dept)
        dept_runs += run_to_records(qid, rer, top_k)
        adjusted = [(cid, sc) for cid, sc in rer if cid in judged]
        dept_adj_runs += run_to_records(qid, adjusted, top_k)
    return {
        "base": evaluate_run(eval_qrels, base_runs),
        "dept_fresh": evaluate_run(eval_qrels, dept_runs),
        "dept_fresh_excl_unjudged": evaluate_run(eval_qrels, dept_adj_runs),
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# 부서 신호 평가 파이프라인 감사 (풀링 편향 점검)",
        "",
        "## 목적",
        "",
        "\"부서를 쓰면 검색이 좋아져야 한다\"는 직관과 평가 결과가 어긋나, 평가가 부서를 부당하게",
        "깎는지(특히 풀링 편향) 점검한다.",
        "",
        "## 설정",
        f"- 컬렉션 `{payload['collection']}`, 평가 쿼리 {payload['judged_query_count']}건, 후보 풀 top-{payload['pool_size']}, 평가 top-{payload['top_k']}",
        f"- fresh 부서 재예측 문서: {payload['fresh_predicted_docs']}건",
        "",
        "## 1) 라벨 밀도 & 승격/강등 분석 (dept_fresh 기준)",
        "",
        "| strategy | 풀 judged율 | 승격 문서 | 그중 무라벨 | 승격(judged중 정답비) | 강등 문서 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strat in payload["strategies"]:
        a = payload["strategies"][strat]["promotion"]
        rel_share = a["promoted_judged_rel_share_of_judged"]
        rel_share_s = f"{rel_share:.2f}" if rel_share is not None else "-"
        lines.append(
            f"| {strat} | {a['pool_judged_rate']:.3f} | {a['promoted_total']} "
            f"| {a['promoted']['unjudged']} ({a['promoted_unjudged_rate']*100:.0f}%) "
            f"| {rel_share_s} | {a['demoted_total']} |"
        )
    lines.append("")
    lines.append("승격 문서 분류: judged_rel(정답) / judged_nonrel(오답라벨) / unjudged(라벨없음)")
    lines.append("")
    for strat in payload["strategies"]:
        a = payload["strategies"][strat]["promotion"]
        lines.append(
            f"- {strat}: 승격 {a['promoted']} / 강등 {a['demoted']}"
        )
    lines.append("")
    lines.append("## 2) 무라벨 승격 제외(중립) 시 지표 변화 — 풀링 편향 보정 하한")
    lines.append("")
    for strat in payload["strategies"]:
        m = payload["strategies"][strat]["metrics_adjusted"]
        lines.extend([
            f"### {strat.upper()}",
            "",
            "| 지표 | base | dept_fresh | dept_fresh(무라벨제외) | Δ(원본) | Δ(보정) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        keys = ["nDCG@5", "nDCG@10", "R@5", "R@10", "AP@10", "P@5"]
        for k in keys:
            b = m["base"].get(k, 0.0)
            d = m["dept_fresh"].get(k, 0.0)
            adj = m["dept_fresh_excl_unjudged"].get(k, 0.0)
            lines.append(f"| {k} | {b:.4f} | {d:.4f} | {adj:.4f} | {d-b:+.4f} | {adj-b:+.4f} |")
        lines.append("")
    lines.extend([
        "## 해석 가이드",
        "",
        "- 승격 문서의 **무라벨 비율이 높으면** = 부서가 끌어올린 문서가 정답지에 없어 오답 처리됨 → 풀링 편향.",
        "- **무라벨 제외(보정) Δ 가 원본보다 크게 개선되면** = 원본 음수는 측정 착시였을 가능성.",
        "- 단 무라벨 제외는 하한 근사(무라벨이 정답일 수도 있어 실제 효과는 그 이상일 수 있음).",
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
            results = await service.search(
                query=q["query"], top_k=args.pool_size, collection_name=args.collection,
                strategy=strat, grounding_filter=False, query_signals=None,
            )
            pools[q["query_id"]] = dedup_results(results, top_k=args.pool_size)
            if i % 10 == 0:
                print(f"[pool:{strat}] {i}/{len(judged)}")
        pools_by_strat[strat] = pools

    candidate_ids = {cid for pools in pools_by_strat.values() for pool in pools.values() for cid, _ in pool}
    text_map, _ = build_doc_text_map(args.collection)
    fresh_dept = predict_departments({cid: text_map.get(cid, "") for cid in candidate_ids}, top_n_units=args.top_n_units)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "qrels_sha256": sha256_file(args.qrels),
        "judged_query_count": len(judged),
        "pool_size": args.pool_size,
        "top_k": args.top_k,
        "fresh_predicted_docs": len(candidate_ids),
        "strategies": {},
    }
    for strat in args.strategies:
        pools = pools_by_strat[strat]
        payload["strategies"][strat] = {
            "promotion": analyze_promotion(pools, qdept, judged_by_qid, fresh_dept, args.top_k),
            "metrics_adjusted": evaluate_excluding_unjudged_promotions(
                pools, qdept, judged_by_qid, fresh_dept, eval_qrels, args.top_k
            ),
        }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"[WRITE] {args.out_json}")
    print(f"[WRITE] {args.out_md}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

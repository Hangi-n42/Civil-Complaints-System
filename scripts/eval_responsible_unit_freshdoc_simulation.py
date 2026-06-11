"""문서쪽 부서를 최신 추정기로 다시 매겼을 때(=재색인 시뮬레이션) 부서 신호가
검색에 도움이 되는지 검증한다.

배경(#369): BE1은 docs metadata 가 과거 구조화 결과(Recall@3 0.49)라 부서 매칭을 운영
신호로 못 쓴다고 보고, 전체 9,132건 재구조화 + civil_cases_v1 재색인을 제안한다.
이 스크립트는 큰 재색인 전에, 후보 문서들에만 최신 DepartmentAssigner 를 즉석 적용해
"문서쪽도 최신(0.84급)이면 부서 신호가 검색에 도움이 되는가"를 싸게 선검증한다.

측정:
1) 판별력(discrimination): 후보 풀에서 부서 일치율을 relevant vs non-relevant 로 분리.
   - relevant 일치율이 non-relevant 보다 충분히 높아야 부서로 순위를 가를 수 있다.
   - old(현재 metadata) / fresh(최신 재예측) 두 버전 모두 측정.
2) 재랭킹 효과: base 점수에 부서 일치 시 +0.03 가점(서비스와 동일)을 줘 top-10 지표 비교.
   - base / dept_old / dept_fresh

주의: fresh 문서쪽 부서는 civil_cases_v1 임베딩 텍스트(민원인 원문 기반)에 최신 추정기를
적용한 결과로, 실제 재색인이 만들 부서 metadata 를 근사한다. 4요소 LLM 구조화 차이는
부서 추정(임베딩 기반)과 무관하므로 부서 신호 평가 목적에는 충분하다.
개인정보 보호: 산출물에 쿼리/문서 원문은 포함하지 않는다(집계·case_id 만).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.evaluation.datasets import sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import (
    dedup_results,
    load_qrels,
    load_queries,
    ordered_metric_keys,
)

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_freshdoc_simulation.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_freshdoc_simulation.md"
DEPT_BOOST = 0.03  # app/retrieval/service.py METADATA_SOFT_RERANK_WEIGHTS["responsible_units"]


def build_doc_text_map(collection_name: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """case_id -> 임베딩 텍스트, case_id -> 현재 metadata responsible_units(old)."""
    col = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db")).get_collection(
        collection_name
    )
    got = col.get(include=["documents", "metadatas"])
    text_map: dict[str, str] = {}
    old_dept: dict[str, list[str]] = {}
    for doc, meta in zip(got["documents"], got["metadatas"]):
        cid = str(meta.get("case_id") or "").strip()
        if not cid:
            continue
        if cid not in text_map or len(doc or "") > len(text_map[cid]):
            text_map[cid] = doc or ""
        if cid not in old_dept:
            raw = meta.get("responsible_units") or ""
            old_dept[cid] = [u.strip() for u in str(raw).split("|") if u.strip()]
    return text_map, old_dept


def predict_departments(texts: dict[str, str], *, top_n_units: int) -> dict[str, list[str]]:
    assigner = get_department_assigner()
    assigner.build_index(rebuild=False)
    out: dict[str, list[str]] = {}
    items = list(texts.items())
    started = time.perf_counter()
    for i, (key, text) in enumerate(items, start=1):
        if not text.strip():
            out[key] = []
            continue
        cands = assigner.assign(text, top_n_units=top_n_units)
        out[key] = [c["name"] for c in cands if c.get("name")]
        if i % 50 == 0:
            print(f"[predict] {i}/{len(items)} ({time.perf_counter()-started:.0f}s)")
    return out


def rerank(pool: list[tuple[str, float]], qdept: set[str], doc_dept: dict[str, list[str]]) -> list[tuple[str, float]]:
    rescored = []
    for cid, score in pool:
        boost = DEPT_BOOST if (qdept & set(doc_dept.get(cid, []))) else 0.0
        rescored.append((cid, score + boost))
    return sorted(rescored, key=lambda r: r[1], reverse=True)


def run_to_records(qid: str, ranked: list[tuple[str, float]], top_k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r)
            for r, (cid, sc) in enumerate(ranked[:top_k], start=1)]


def discrimination(
    pools: dict[str, list[tuple[str, float]]],
    qdept: dict[str, set[str]],
    rel_by_qid: dict[str, set[str]],
    doc_dept: dict[str, list[str]],
) -> dict[str, Any]:
    rel_total = rel_match = nonrel_total = nonrel_match = 0
    for qid, pool in pools.items():
        rels = rel_by_qid.get(qid, set())
        qd = qdept.get(qid, set())
        for cid, _ in pool:
            matched = bool(qd & set(doc_dept.get(cid, [])))
            if cid in rels:
                rel_total += 1
                rel_match += int(matched)
            else:
                nonrel_total += 1
                nonrel_match += int(matched)
    rel_rate = rel_match / rel_total if rel_total else 0.0
    nonrel_rate = nonrel_match / nonrel_total if nonrel_total else 0.0
    return {
        "relevant_in_pool": rel_total,
        "relevant_dept_match": rel_match,
        "relevant_match_rate": round(rel_rate, 4),
        "nonrelevant_in_pool": nonrel_total,
        "nonrelevant_dept_match": nonrel_match,
        "nonrelevant_match_rate": round(nonrel_rate, 4),
        "discrimination_lift": round(rel_rate - nonrel_rate, 4),
    }


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# 부서 신호 — 문서쪽 최신 재예측(재색인 시뮬레이션) 선검증",
        "",
        "## 목적",
        "",
        "전체 9,132건 재색인 전에, 후보 문서에만 최신 DepartmentAssigner 를 즉석 적용해",
        "\"문서쪽도 최신(0.84급)이면 부서 신호가 검색에 도움이 되는가\"를 선검증한다.",
        "",
        "## 설정",
        "",
        f"- 컬렉션: `{payload['collection']}`",
        f"- 평가 쿼리(qrels 보유): {payload['judged_query_count']}건, 후보 풀 top-{payload['pool_size']}",
        f"- 재예측 문서 수: {payload['fresh_predicted_docs']}건 ({payload['predict_sec']}s)",
        f"- 부서 가점: +{DEPT_BOOST} (서비스 동일)",
        "",
        "## 1) 판별력 — 부서 일치율 (relevant vs non-relevant)",
        "",
        "부서로 순위를 가르려면 relevant 일치율이 non-relevant 보다 충분히 높아야 한다.",
        "",
        "| 문서쪽 부서 | strategy | relevant 일치율 | non-relevant 일치율 | lift |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for tag in ("old", "fresh"):
        for strat in payload["strategies"]:
            d = payload["strategies"][strat]["discrimination"][tag]
            lines.append(
                f"| {tag} | {strat} | {d['relevant_match_rate']:.4f} "
                f"| {d['nonrelevant_match_rate']:.4f} | {d['discrimination_lift']:+.4f} |"
            )
    lines.append("")
    for strat in payload["strategies"]:
        res = payload["strategies"][strat]
        m = res["metrics"]
        lines.extend([
            f"## 2) {strat.upper()} 재랭킹 효과 (top-{payload['top_k']})",
            "",
            "| 지표 | base | dept_old | dept_fresh | Δ(old) | Δ(fresh) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for key in res["metric_keys"]:
            b = m["base"].get(key, 0.0)
            o = m["dept_old"].get(key, 0.0)
            f = m["dept_fresh"].get(key, 0.0)
            lines.append(f"| {key} | {_fmt(b)} | {_fmt(o)} | {_fmt(f)} | {o-b:+.4f} | {f-b:+.4f} |")
        lines.append("")
    lines.extend([
        "## 판단",
        "",
        "- relevant/non-relevant 일치율 lift 가 작고 dept_fresh 재랭킹 Δ 가 ~0/음수면,",
        "  문서쪽을 최신으로 재색인해도 부서 신호가 검색을 개선하지 못한다는 뜻이다.",
        "- 부서 신호는 hard filter 가 아니라 soft 신호로만 쓴다. 산출물에 원문 미포함.",
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
    p.add_argument("--pool-size", type=int, default=20)
    p.add_argument("--top-n-units", type=int, default=3)
    p.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    p.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    p.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()
    queries = load_queries(args.queries)
    qrels = load_qrels(args.qrels)
    rel_by_qid: dict[str, set[str]] = {}
    for row in qrels:
        if row.relevance > 0:
            rel_by_qid.setdefault(row.qid, set()).add(row.docid)
    judged = [q for q in queries if q["query_id"] in rel_by_qid]
    eval_qrels = [r for r in qrels if r.qid in rel_by_qid]

    # 1) 쿼리 부서 예측
    assigner = get_department_assigner()
    assigner.build_index(rebuild=False)
    qdept: dict[str, set[str]] = {}
    for q in judged:
        cands = assigner.assign(q["query"], top_n_units=args.top_n_units)
        qdept[q["query_id"]] = {c["name"] for c in cands if c.get("name")}

    # 2) base 검색으로 후보 풀 수집
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

    # 3) 후보 문서 union 의 fresh 부서 재예측
    candidate_ids = {cid for pools in pools_by_strat.values() for pool in pools.values() for cid, _ in pool}
    text_map, old_dept = build_doc_text_map(args.collection)
    cand_texts = {cid: text_map.get(cid, "") for cid in candidate_ids}
    t0 = time.perf_counter()
    fresh_dept = predict_departments(cand_texts, top_n_units=args.top_n_units)
    predict_sec = round(time.perf_counter() - t0, 1)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "qrels_path": args.qrels.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "qrels_sha256": sha256_file(args.qrels),
        "judged_query_count": len(judged),
        "pool_size": args.pool_size,
        "top_k": args.top_k,
        "fresh_predicted_docs": len(candidate_ids),
        "predict_sec": predict_sec,
        "strategies": {},
    }

    for strat in args.strategies:
        pools = pools_by_strat[strat]
        runs_base, runs_old, runs_fresh = [], [], []
        for qid, pool in pools.items():
            qd = qdept.get(qid, set())
            runs_base += run_to_records(qid, pool, args.top_k)
            runs_old += run_to_records(qid, rerank(pool, qd, old_dept), args.top_k)
            runs_fresh += run_to_records(qid, rerank(pool, qd, fresh_dept), args.top_k)
        metrics = {
            "base": evaluate_run(eval_qrels, runs_base),
            "dept_old": evaluate_run(eval_qrels, runs_old),
            "dept_fresh": evaluate_run(eval_qrels, runs_fresh),
        }
        payload["strategies"][strat] = {
            "metric_keys": ordered_metric_keys(*metrics.values()),
            "metrics": metrics,
            "discrimination": {
                "old": discrimination(pools, qdept, rel_by_qid, old_dept),
                "fresh": discrimination(pools, qdept, rel_by_qid, fresh_dept),
            },
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

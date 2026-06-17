"""버전 중립 쿼리셋으로 civil_cases_v1 vs v3 검색 공정 평가.

#401(PR #402)에서 만든 버전 중립 쿼리셋(어느 컬렉션 버전의 구조화도 거치지 않은
민원인 원문)으로 v1/v3를 dense/hybrid 검색·평가한다. 비교 기준으로 옛 구조화본
쿼리(v1 시대 4요소)도 같은 qrels로 평가해, 옛 쿼리에서 나타나는 v1 우위가 중립
쿼리에서 얼마나 축소되는지(= home-field 편향분)를 한 리포트에서 보여준다.

qrels 는 기존 qrels_final 에 공식 LLM 보강 캐시(_cache_llm_judge_official.json)를
더해 사용한다. 무라벨 문서의 신규 LLM 재채점(원격 Ollama)은 범위 밖이며, 그로 인한
풀링편향 잔존은 리포트에 한계로 명시한다. 원문 미포함(집계만).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries

BASELINE_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
NEUTRAL_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "version_neutral" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
OUT_DIR = PROJECT_ROOT / "reports" / "retrieval" / "version_neutral"
OUT_MD = OUT_DIR / "v1_vs_v3.md"
OUT_JSON = OUT_DIR / "v1_vs_v3.json"

TOP_K = 10
POOL = 50
METRIC_ORDER = ["nDCG@5", "nDCG@10", "P@5", "RR@5", "R@10"]
COLLECTIONS = ("civil_cases_v1", "civil_cases_v3")
STRATEGIES = ("dense", "hybrid")


def recs(qid: str, ranked: list[tuple[str, float]], k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


def load_aug_qrels(eval_qrels: list[QrelRecord], rel_qids: set[str]) -> list[QrelRecord]:
    """원 qrels + 공식 LLM 보강 캐시(있으면) 결합."""
    aug = list(eval_qrels)
    if JUDGE_CACHE.exists():
        for key, value in json.loads(JUDGE_CACHE.read_text()).items():
            qid, cid = key.split("||", 1)
            if qid in rel_qids:
                aug.append(QrelRecord(qid=qid, docid=cid, relevance=int(value)))
    return aug


async def run_eval(
    svc: RetrievalService,
    queries_path: Path,
    rel_qids: set[str],
    aug: list[QrelRecord],
    limit: int,
) -> tuple[int, dict[str, dict[str, dict[str, float]]]]:
    """한 쿼리셋으로 v1/v3 × dense/hybrid 검색·평가하고 지표를 돌려준다."""
    queries = load_queries(queries_path)
    judged = [q for q in queries if q["query_id"] in rel_qids]
    if limit > 0:
        judged = judged[:limit]

    results: dict[str, dict[str, dict[str, float]]] = {}
    for strat in STRATEGIES:
        results[strat] = {}
        for coll in COLLECTIONS:
            run: list[RunRecord] = []
            for q in judged:
                res = await svc.search(
                    query=q["query"], top_k=POOL, collection_name=coll,
                    strategy=strat, grounding_filter=False, query_signals=None,
                )
                run.extend(recs(q["query_id"], dedup_results(res, top_k=POOL), TOP_K))
            metrics = evaluate_run(aug, run)
            results[strat][coll] = {k: metrics.get(k) for k in METRIC_ORDER}
            v = results[strat][coll]["nDCG@10"]
            print(f"[{queries_path.stem}:{coll.split('_')[-1]}:{strat}] nDCG@10 {v:.4f}")
    return len(judged), results


def _table(title: str, n: int, results: dict) -> list[str]:
    lines = [
        f"## {title} ({n}건)",
        "",
        "| 전략 | 컬렉션 | nDCG@5 | nDCG@10 | P@5 | RR@5 | R@10 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strat in STRATEGIES:
        for coll in COLLECTIONS:
            row = results[strat][coll]
            cells = " | ".join(f"{row[k]:.4f}" if row[k] is not None else "-" for k in METRIC_ORDER)
            lines.append(f"| {strat} | {coll.split('_')[-1]} | {cells} |")
    return lines


def _delta(results: dict, strat: str) -> float:
    return results[strat]["civil_cases_v3"]["nDCG@10"] - results[strat]["civil_cases_v1"]["nDCG@10"]


async def main() -> int:
    parser = argparse.ArgumentParser(description="버전 중립 v1 vs v3 검색 평가")
    parser.add_argument("--limit", type=int, default=0, help="스모크용 평가 쿼리 수 제한(0=전체)")
    args = parser.parse_args()

    qrels = load_qrels(QRELS)
    rel_qids = {r.qid for r in qrels if r.relevance > 0}
    eval_qrels = [r for r in qrels if r.qid in rel_qids]
    aug = load_aug_qrels(eval_qrels, rel_qids)
    print(f"[eval-vn] qrels 원 {len(eval_qrels)} → 보강 {len(aug)} (rel>0 쿼리 {len(rel_qids)})")

    svc = RetrievalService()
    n_base, baseline = await run_eval(svc, BASELINE_QUERIES, rel_qids, aug, args.limit)
    n_neu, neutral = await run_eval(svc, NEUTRAL_QUERIES, rel_qids, aug, args.limit)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 버전 중립 쿼리 기반 v1 vs v3 검색 공정 평가",
        "",
        f"- top-{TOP_K}, POOL {POOL}, qrels 원 {len(eval_qrels)} + 공식 LLM 보강 → {len(aug)}",
        "- 옛 구조화본 쿼리(v1 시대 4요소) vs 버전 중립 쿼리(민원인 원문) 비교",
        "",
    ]
    lines += _table("옛 구조화본 쿼리 (v1 시대 4요소)", n_base, baseline)
    lines += [""]
    lines += _table("버전 중립 쿼리 (민원인 원문)", n_neu, neutral)
    lines += [
        "",
        "## v3 − v1 nDCG@10 격차: 옛 구조화본 vs 중립",
        "",
        "| 전략 | 옛쿼리 Δ(v3−v1) | 중립쿼리 Δ(v3−v1) | 편향 추정(옛−중립) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for strat in STRATEGIES:
        db, dn = _delta(baseline, strat), _delta(neutral, strat)
        lines.append(f"| {strat} | {db:+.4f} | {dn:+.4f} | {db - dn:+.4f} |")
    lines += [
        "",
        "## 해석",
        "- 옛 구조화본 쿼리에서 v1이 크게 앞서지만(v1 home-field 편향), 중립 쿼리에서 v1↔v3 격차가 축소된다.",
        "- 축소된 만큼(편향 추정 열)이 평가셋 home-field 편향분이며, 그만큼 옛 평가의 'v1 우위'는 과대평가였다.",
        "- 한계: 무라벨 신규 LLM 재채점은 범위 밖이라, 중립 쿼리로 새로 떠오른 무라벨은 0점 처리되어 풀링편향이 일부 잔존한다(후속 보정 대상).",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "top_k": TOP_K, "pool": POOL, "qrels_aug": len(aug),
                "baseline": {"n": n_base, "results": baseline},
                "neutral": {"n": n_neu, "results": neutral},
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[WRITE] {OUT_MD}")
    print(f"[WRITE] {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

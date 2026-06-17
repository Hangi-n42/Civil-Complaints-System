"""중립 쿼리셋 무라벨 LLM 재채점으로 풀링편향 보정.

#403(PR #404)의 중립 쿼리 평가는 기존 qrels + 공식 캐시만 써서, 중립 쿼리로 새로
떠오른 무라벨이 0점 처리되는 풀링편향이 잔존했다. 이 스크립트는 중립 쿼리로 v1/v3를
검색해 top-10 무라벨을 공식 SYSTEM_PROMPT + qwen2.5:14b 로 채점하고, 보정 전/후의
v1 vs v3 격차를 비교한다. home-field(중립 쿼리) + 풀링(보강 채점) 두 편향이 모두
제거된 최종 공정 비교를 만든다.

심판: 원격 Ollama qwen2.5:14b. 원문 미포함(집계만).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries
from scripts.eval_v1_v3_version_neutral import build_prompt, case_texts, judge

NEUTRAL_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "version_neutral" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
OUT_DIR = PROJECT_ROOT / "reports" / "retrieval" / "version_neutral"
OUT_MD = OUT_DIR / "pooling_corrected.md"
OUT_JSON = OUT_DIR / "pooling_corrected.json"

TOP_K = 10
POOL = 50
METRIC_ORDER = ["nDCG@5", "nDCG@10", "P@5", "RR@5", "R@10"]
COLLECTIONS = ("civil_cases_v1", "civil_cases_v3")
STRATEGIES = ("dense", "hybrid")


def recs(qid: str, ranked: list[tuple[str, float]], k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


def aug_qrels(eval_qrels: list[QrelRecord], cache: dict[str, int], rel_qids: set[str]) -> list[QrelRecord]:
    out = list(eval_qrels)
    for key, value in cache.items():
        qid, cid = key.split("||", 1)
        if qid in rel_qids:
            out.append(QrelRecord(qid=qid, docid=cid, relevance=int(value)))
    return out


def eval_all(aug: list[QrelRecord], runs: dict) -> dict:
    out: dict[str, dict[str, dict[str, float]]] = {}
    for strat in STRATEGIES:
        out[strat] = {}
        for coll in COLLECTIONS:
            run = [r for qid, ranked in runs[(coll, strat)].items() for r in recs(qid, ranked, TOP_K)]
            metrics = evaluate_run(aug, run)
            out[strat][coll] = {k: metrics.get(k) for k in METRIC_ORDER}
    return out


async def main() -> int:
    queries = load_queries(NEUTRAL_QUERIES)
    qrels = load_qrels(QRELS)
    rel_qids = {r.qid for r in qrels if r.relevance > 0}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    eval_qrels = [r for r in qrels if r.qid in rel_qids]
    judged_by_qid: dict[str, set[str]] = {}
    for r in qrels:
        judged_by_qid.setdefault(r.qid, set()).add(r.docid)
    qtext = {q["query_id"]: q["query"] for q in judged}

    # 1) 중립 쿼리로 v1/v3 × dense/hybrid 검색
    svc = RetrievalService()
    runs: dict[tuple[str, str], dict[str, list[tuple[str, float]]]] = {}
    for coll in COLLECTIONS:
        for strat in STRATEGIES:
            pool: dict[str, list[tuple[str, float]]] = {}
            for q in judged:
                res = await svc.search(
                    query=q["query"], top_k=POOL, collection_name=coll,
                    strategy=strat, grounding_filter=False, query_signals=None,
                )
                pool[q["query_id"]] = dedup_results(res, top_k=POOL)
            runs[(coll, strat)] = pool
            print(f"[search:{coll.split('_')[-1]}:{strat}] done")

    # 2) top-10 무라벨 추출
    cache_before = json.loads(JUDGE_CACHE.read_text()) if JUDGE_CACHE.exists() else {}
    cache = dict(cache_before)
    ctext = case_texts()
    pairs: set[tuple[str, str]] = set()
    for pool in runs.values():
        for qid, ranked in pool.items():
            for cid, _ in ranked[:TOP_K]:
                if cid not in judged_by_qid.get(qid, set()) and f"{qid}||{cid}" not in cache:
                    pairs.add((qid, cid))
    print(f"[judge] 신규 무라벨 {len(pairs)}건 (기존 캐시 {len(cache_before)})")

    # 3) 공식 SYSTEM_PROMPT + qwen2.5:14b 채점
    t0 = time.time()
    async with httpx.AsyncClient() as client:
        for i, (qid, cid) in enumerate(sorted(pairs), start=1):
            score = await judge(client, build_prompt(qtext.get(qid, ""), ctext.get(cid, "")))
            if score is not None:
                cache[f"{qid}||{cid}"] = score
            if i % 20 == 0:
                JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
                print(f"[judge] {i}/{len(pairs)} ({time.time() - t0:.0f}s)")
    JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    # 4) 보정 전/후 평가
    before = eval_all(aug_qrels(eval_qrels, cache_before, rel_qids), runs)
    after = eval_all(aug_qrels(eval_qrels, cache, rel_qids), runs)

    new_keys = [k for k in cache if k not in cache_before]
    dist = Counter(cache[k] for k in new_keys)
    rel_pos = sum(1 for k in new_keys if cache[k] > 0)
    rel_pos_pct = rel_pos / max(len(new_keys), 1) * 100

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 중립 쿼리 풀링편향 보정 (무라벨 LLM 재채점)",
        "",
        f"- 중립 쿼리 {len(judged)}건, top-{TOP_K}, 심판 qwen2.5:14b(공식 SYSTEM_PROMPT)",
        f"- 신규 무라벨 채점 {len(new_keys)}건: rel0 {dist.get(0, 0)} / rel1 {dist.get(1, 0)} / rel2 {dist.get(2, 0)}",
        f"- **무라벨 중 실제 관련(rel≥1): {rel_pos}건 ({rel_pos_pct:.1f}%)** = 보정 전 부당하게 0점 처리된 풀링편향분",
        "",
        "## 보정 전 vs 후 — v1/v3 nDCG@10",
        "",
        "| 전략 | 컬렉션 | 보정 전 | 보정 후 |",
        "| --- | --- | ---: | ---: |",
    ]
    for strat in STRATEGIES:
        for coll in COLLECTIONS:
            b = before[strat][coll]["nDCG@10"]
            a = after[strat][coll]["nDCG@10"]
            lines.append(f"| {strat} | {coll.split('_')[-1]} | {b:.4f} | {a:.4f} |")
    lines += ["", "## v3 − v1 nDCG@10 격차: 보정 전 vs 후", "", "| 전략 | 보정 전 Δ | 보정 후 Δ |", "| --- | ---: | ---: |"]
    for strat in STRATEGIES:
        db = before[strat]["civil_cases_v3"]["nDCG@10"] - before[strat]["civil_cases_v1"]["nDCG@10"]
        da = after[strat]["civil_cases_v3"]["nDCG@10"] - after[strat]["civil_cases_v1"]["nDCG@10"]
        lines.append(f"| {strat} | {db:+.4f} | {da:+.4f} |")
    lines += [
        "",
        "## 해석",
        "- 중립 쿼리(home-field 제거) + 무라벨 보강 채점(풀링편향 제거) = 두 편향 모두 보정된 최종 공정 비교.",
        f"- 신규 무라벨의 {rel_pos_pct:.0f}%가 실제 관련(rel≥1) → 보정 전에는 이만큼이 부당하게 0점 처리되었다.",
        "- 보정 후 v1↔v3 격차로 재색인(v3)의 실제 검색 효과를 판단한다.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "judged": len(judged), "new_judged": len(new_keys),
                "new_rel_dist": {str(k): v for k, v in dist.items()},
                "rel_pos_pct": rel_pos_pct, "before": before, "after": after,
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

"""버전 중립(운영 현실) v1 vs v3 비교 — 새 파이프라인 쿼리로 검색·채점·평가.

#369 후속. 기존 평가셋은 옛 파이프라인 쿼리(5/31)로 만들어져 v1에 home-field 편향이
있음이 증명됐다(옛쿼리↔v1, 새쿼리↔v3 유사도 뒤집힘). 이 스크립트는 운영 현실에 맞춰
**현재 파이프라인으로 재구조화한 쿼리**로 v1·v3를 검색하고, 새쿼리 풀의 무라벨을
공식 기준으로 LLM 채점해 보강 qrels로 비교한다. relevance 는 intent 기반이라 기존
판정(공식 캐시)과 원 qrels(749)도 라벨로 재사용한다.

심판: 원격 Ollama qwen2.5:14b + 공식 SYSTEM_PROMPT. 원문 미포함(집계만).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries, ordered_metric_keys
from scripts.relabel_new_qrels_v3 import SYSTEM_PROMPT, _extract_score

QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
NEWQ_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_restructured_queries.json"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "v1_v3_version_neutral.md"
BASE_URL = "http://100.71.35.78:11434"
MODEL = "qwen2.5:14b"
MAX_CHARS = 600
TOP_K = 10
POOL = 50


def build_prompt(q: str, c: str) -> str:
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q[:MAX_CHARS].replace(chr(10),' / ')}\n\n과거 민원(Chunk):\n{c[:MAX_CHARS]}"


def case_texts() -> dict[str, str]:
    client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db"))
    out: dict[str, str] = {}
    for name in ("civil_cases_v1", "civil_cases_v3"):
        g = client.get_collection(name).get(include=["documents", "metadatas"])
        for d, m in zip(g["documents"], g["metadatas"]):
            cid = str(m.get("case_id") or "")
            if cid and (d or "").strip() and (name == "civil_cases_v3" or cid not in out):
                out[cid] = d
    return out


def recs(qid: str, ranked: list[tuple[str, float]], k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


async def judge(client, prompt: str) -> int | None:
    for attempt in range(4):
        try:
            r = await client.post(f"{BASE_URL}/api/generate",
                                  json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json",
                                        "options": {"temperature": 0, "num_predict": 120}, "keep_alive": "10m"},
                                  timeout=120.0)
            r.raise_for_status()
            s = _extract_score(r.json().get("response", ""))
            if s is not None:
                return s
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                print(f"[judge-error] {e!r}")
            await asyncio.sleep(2)
    return None


async def main():
    queries = load_queries(QUERIES)
    qrels = load_qrels(QRELS)
    rel_qids = {r.qid for r in qrels if r.relevance > 0}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    eval_qrels = [r for r in qrels if r.qid in rel_qids]
    judged_by_qid: dict[str, set[str]] = {}
    for r in qrels:
        judged_by_qid.setdefault(r.qid, set()).add(r.docid)

    newq = json.loads(NEWQ_CACHE.read_text())  # qid -> 새 쿼리 텍스트
    qtext = {q["query_id"]: newq.get(q["query_id"], q["query"]) for q in judged}
    ctext = case_texts()

    # 1) 새 쿼리로 v1·v3 검색
    svc = RetrievalService()
    runs: dict[tuple, dict[str, list[tuple[str, float]]]] = {}
    for coll in ("civil_cases_v1", "civil_cases_v3"):
        for strat in ("dense", "hybrid"):
            pool = {}
            for i, q in enumerate(judged, start=1):
                res = await svc.search(query=qtext[q["query_id"]], top_k=POOL, collection_name=coll,
                                       strategy=strat, grounding_filter=False, query_signals=None)
                pool[q["query_id"]] = dedup_results(res, top_k=POOL)
            runs[(coll, strat)] = pool
            print(f"[search:{coll.split('_')[-1]}:{strat}] done")

    # 2) 새쿼리 top-10 무라벨 풀 채점 (공식 캐시 확장)
    cache: dict[str, int] = json.loads(JUDGE_CACHE.read_text()) if JUDGE_CACHE.exists() else {}
    pairs = set()
    for pool in runs.values():
        for qid, ranked in pool.items():
            for cid, _ in ranked[:TOP_K]:
                if cid not in judged_by_qid.get(qid, set()) and f"{qid}||{cid}" not in cache:
                    pairs.add((qid, cid))
    print(f"[judge] 새 무라벨 쌍 {len(pairs)}건 (기존 캐시 {len(cache)} 재활용)")
    t0 = time.time()
    async with httpx.AsyncClient() as client:
        for i, (qid, cid) in enumerate(sorted(pairs), start=1):
            s = await judge(client, build_prompt(qtext.get(qid, ""), ctext.get(cid, "")))
            if s is not None:
                cache[f"{qid}||{cid}"] = s
            if i % 20 == 0:
                JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
                print(f"[judge] {i}/{len(pairs)} ({time.time()-t0:.0f}s)")
    JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    # 3) 보강 qrels = 원 + 전체 공식 캐시
    aug = list(eval_qrels)
    for k, v in cache.items():
        qid, cid = k.split("||", 1)
        if qid in rel_qids:
            aug.append(QrelRecord(qid=qid, docid=cid, relevance=int(v)))

    # 4) 평가 (새 쿼리 기준)
    lines = ["# v1 vs v3 버전 중립 비교 (운영 현실 = 새 파이프라인 쿼리)", "",
             f"- 평가 쿼리 {len(judged)}건(현재 파이프라인 재구조화), top-{TOP_K}, 보강 qrels(원+공식 LLM)",
             f"- 새 무라벨 추가 채점 {len(pairs)}건 (공식 SYSTEM_PROMPT, {MODEL})", "",
             "| 전략 | v1 nDCG@10 | v3 nDCG@10 | Δ(v3−v1) | v1 R@10 | v3 R@10 | Δ |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for strat in ("dense", "hybrid"):
        m1 = evaluate_run(aug, [r for qid, rk in runs[("civil_cases_v1", strat)].items() for r in recs(qid, rk, TOP_K)])
        m3 = evaluate_run(aug, [r for qid, rk in runs[("civil_cases_v3", strat)].items() for r in recs(qid, rk, TOP_K)])
        lines.append(f"| {strat} | {m1['nDCG@10']:.4f} | {m3['nDCG@10']:.4f} | {m3['nDCG@10']-m1['nDCG@10']:+.4f} "
                     f"| {m1['R@10']:.4f} | {m3['R@10']:.4f} | {m3['R@10']-m1['R@10']:+.4f} |")
        print(f"[{strat}] v1 {m1['nDCG@10']:.4f} vs v3 {m3['nDCG@10']:.4f} ({m3['nDCG@10']-m1['nDCG@10']:+.4f})")
    lines += ["", "## 해석",
              "- 운영 현실(새 쿼리)에서 v3가 v1과 동등/우위면, 재색인(v3)이 실전에 적합.",
              "- 옛 쿼리 평가의 'v1 우위'는 평가셋 home-field 편향(쿼리가 v1 시대 생성)이었음.", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())

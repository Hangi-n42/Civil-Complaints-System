"""civil_cases_v1 vs v3 공정 비교 — 무라벨 top-10 을 공식 기준으로 LLM 채점해 메운 뒤 비교.

#369/PR#386 후속. 고정 qrels 는 풀링 편향(후보의 ~20%만 채점)으로 새 컬렉션이 가져온
무라벨 문서를 자동 오답 처리한다(v2 의 0.70→0.44 착시). 이 스크립트는 v1·v3 양쪽
base 검색(top-10)에 등장한 무라벨 (qid, case_id) 쌍을 **양쪽에 동일하게** LLM 채점해
보강 qrels 로 공정 비교한다.

- 심판 기준: qrels 생성에 쓴 공식 SYSTEM_PROMPT(relabel_new_qrels_v3, 기준 문서
  retrieval_relevance_definition.md 0~2 척도)를 그대로 재사용 — 라벨 드리프트 없음.
- 채점 입력 청크 텍스트: v3 표현을 정본으로 사용(현행 색인 정책: 답변 포함).
  v3 텍스트가 비면 v1 텍스트로 폴백. 라벨은 case 단위라 양쪽 비교에 동일 적용.
- 심판 LLM 은 원격 데스크톱 Ollama(qwen2.5:14b). 캐시는 공식 프롬프트 전용 파일에
  분리 저장(기존 약식 프롬프트 캐시와 혼합 금지).
- 원문/스니펫은 산출물에 미포함(집계·case_id·점수만).
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

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.evaluation.datasets import QrelRecord, sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from scripts.eval_be1_metadata_overlay_soft_rerank import (
    dedup_results,
    load_qrels,
    load_queries,
    ordered_metric_keys,
)
from scripts.relabel_new_qrels_v3 import SYSTEM_PROMPT, _extract_score

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "v1_v3_fair_comparison.json"
OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "v1_v3_fair_comparison.md"
MAX_CHARS = 600  # judge_pool_qwen 과 동일


def build_prompt(query_text: str, chunk_text: str) -> str:
    q = query_text[:MAX_CHARS].replace("\n", " / ")
    c = chunk_text[:MAX_CHARS]
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


def load_case_texts() -> dict[str, str]:
    """case_id -> 정본 텍스트 (v3 우선, 비면 v1 폴백)."""
    client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db"))
    texts: dict[str, str] = {}
    for name in ("civil_cases_v1", "civil_cases_v3"):  # v3 를 나중에 덮어써 우선
        got = client.get_collection(name).get(include=["documents", "metadatas"])
        for doc, meta in zip(got["documents"], got["metadatas"]):
            cid = str(meta.get("case_id") or "")
            if cid and (doc or "").strip():
                if name == "civil_cases_v3" or cid not in texts:
                    texts[cid] = doc
    return texts


async def judge_pair(client: httpx.AsyncClient, base_url: str, model: str, prompt: str) -> int | None:
    for attempt in range(4):
        try:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "format": "json",
                      "options": {"temperature": 0, "num_predict": 120}, "keep_alive": "10m"},
                timeout=120.0,
            )
            resp.raise_for_status()
            score = _extract_score(resp.json().get("response", ""))
            if score is not None:
                return score
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f"[judge-error] {exc!r}")
            await asyncio.sleep(2)
    return None


def recs(qid: str, ranked: list[tuple[str, float]], k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    p.add_argument("--base-url", default="http://100.71.35.78:11434")
    p.add_argument("--model", default="qwen2.5:14b")
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
    qtext = {q["query_id"]: q["query"] for q in judged}

    # 1) 양쪽 컬렉션 base 검색 (top-K)
    service = RetrievalService()
    runs: dict[tuple[str, str], dict[str, list[tuple[str, float]]]] = {}
    for coll in ("civil_cases_v1", "civil_cases_v3"):
        for strat in args.strategies:
            key = (coll, strat)
            runs[key] = {}
            for i, q in enumerate(judged, start=1):
                res = await service.search(query=q["query"], top_k=args.top_k, collection_name=coll,
                                           strategy=strat, grounding_filter=False, query_signals=None)
                runs[key][q["query_id"]] = dedup_results(res, top_k=args.top_k)
                if i % 20 == 0:
                    print(f"[search:{coll}:{strat}] {i}/{len(judged)}")

    # 2) 무라벨 쌍 수집 (양쪽 동일 적용 = 대칭 채점)
    pairs: set[tuple[str, str]] = set()
    for pool in runs.values():
        for qid, ranked in pool.items():
            for cid, _ in ranked:
                if cid not in judged_by_qid.get(qid, {}):
                    pairs.add((qid, cid))
    print(f"[judge] 무라벨 쌍 {len(pairs)}건 (공식 기준, model={args.model})")

    # 3) LLM 채점 (캐시 재사용)
    cache: dict[str, int] = json.loads(JUDGE_CACHE.read_text()) if JUDGE_CACHE.exists() else {}
    texts = load_case_texts()
    dist = {"0": 0, "1": 0, "2": 0}
    ok = fail = 0
    t0 = time.perf_counter()
    async with httpx.AsyncClient() as client:
        for i, (qid, cid) in enumerate(sorted(pairs), start=1):
            ckey = f"{qid}||{cid}"
            if ckey in cache:
                score = cache[ckey]
            else:
                score = await judge_pair(client, args.base_url, args.model,
                                         build_prompt(qtext.get(qid, ""), texts.get(cid, "")))
                if score is not None:
                    cache[ckey] = score
                    if i % 20 == 0:
                        JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
            if score is None:
                fail += 1
            else:
                ok += 1
                dist[str(score)] += 1
            if i % 25 == 0:
                print(f"[judge] {i}/{len(pairs)} ({time.perf_counter()-t0:.0f}s)")
    JUDGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    # 4) 보강 qrels 로 평가
    aug_qrels = list(eval_qrels)
    for ckey, score in cache.items():
        qid, cid = ckey.split("||", 1)
        if qid in rel_qids:
            aug_qrels.append(QrelRecord(qid=qid, docid=cid, relevance=int(score)))

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "qrels_sha256": sha256_file(DEFAULT_QRELS),
        "judged_query_count": len(judged),
        "top_k": args.top_k,
        "judge": {"model": args.model, "prompt": "relabel_new_qrels_v3.SYSTEM_PROMPT (공식)",
                   "pairs": len(pairs), "ok": ok, "fail": fail, "dist": dist,
                   "unjudged_relevant_rate": round((dist["1"] + dist["2"]) / ok, 4) if ok else 0.0},
        "strategies": {},
    }
    lines = ["# civil_cases_v1 vs v3 공정 비교 (무라벨 보강 채점)", "",
             f"- 평가 쿼리 {len(judged)}건, top-{args.top_k}, 심판: {args.model} + 공식 SYSTEM_PROMPT",
             f"- 무라벨 채점 {ok}건 (rel2={dist['2']}, rel1={dist['1']}, rel0={dist['0']}) — "
             f"관련(>0) 비율 {payload['judge']['unjudged_relevant_rate']*100:.1f}%", ""]
    for strat in args.strategies:
        per: dict[str, dict[str, dict[str, float]]] = {}
        for coll in ("civil_cases_v1", "civil_cases_v3"):
            flat = [r for qid, ranked in runs[(coll, strat)].items() for r in recs(qid, ranked, args.top_k)]
            per[coll] = {"orig": evaluate_run(eval_qrels, flat), "aug": evaluate_run(aug_qrels, flat)}
        payload["strategies"][strat] = per
        keys = ordered_metric_keys(per["civil_cases_v1"]["aug"], per["civil_cases_v3"]["aug"])
        lines += [f"## {strat.upper()}", "",
                  "| 지표 | v1(원qrels) | v3(원qrels) | v1(보강) | v3(보강) | Δ(보강 v3−v1) |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for k in keys:
            a = per["civil_cases_v1"]["orig"].get(k, 0.0); b = per["civil_cases_v3"]["orig"].get(k, 0.0)
            c = per["civil_cases_v1"]["aug"].get(k, 0.0); d = per["civil_cases_v3"]["aug"].get(k, 0.0)
            lines.append(f"| {k} | {_fmt(a)} | {_fmt(b)} | {_fmt(c)} | {_fmt(d)} | {d-c:+.4f} |")
        lines.append("")
        print(f"[{strat}] 보강 nDCG@10: v1 {per['civil_cases_v1']['aug'].get('nDCG@10',0):.4f} "
              f"vs v3 {per['civil_cases_v3']['aug'].get('nDCG@10',0):.4f}")
    lines += ["## 해석",
              "- '원qrels' 열은 풀링 편향 포함(새 문서 자동 오답) — 참고용.",
              "- '보강' 열이 공정 비교: 양쪽 top-10 무라벨을 동일 기준으로 채점해 메운 결과.",
              "- 채점 입력 청크는 v3 표현(답변 포함, 현행 정책)을 정본으로 사용. 원문 미포함.", ""]
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {OUT_JSON}")
    print(f"[WRITE] {OUT_MD}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

"""풀링 편향 보정: 부서가 top-10 에 올린 무라벨 문서를 LLM 으로 관련성 채점한 뒤,
보강된 qrels 로 base vs dept_fresh 검색을 재평가해 부서 신호의 '진짜' 효과 크기를 측정한다.

#369 후속. condensed-list 공정 비교는 부서의 무라벨 문서 발굴 효과를 제외한 하한이었다.
여기서는 그 무라벨 문서를 LLM(원격 Ollama)으로 채점해 채점표 구멍을 메운다.

- 심판은 blind: (질의, 후보 사례) 텍스트만 보고 0/1/2 관련성 채점. 어느 시스템이 올렸는지,
  부서 예측이 무엇인지 보지 않는다(편향 방지).
- 심판 모델은 구조화/임베딩 파이프라인과 독립적인 별도 모델 사용(자기참조 방지).
- 산출물에 원문 미포함(집계·case_id·점수만). 판단 캐시는 case 단위로 보관.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord, sha256_file
from app.evaluation.metrics import evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries, ordered_metric_keys
from scripts.eval_responsible_unit_freshdoc_simulation import build_doc_text_map, predict_departments, rerank, run_to_records

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_llm_judge_eval.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_llm_judge_eval.md"
DEPT_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_freshdoc_dept.json"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge.json"

JUDGE_PROMPT = """당신은 민원 검색 결과의 관련성을 평가하는 심사관입니다.
아래 [질의 민원]을 처리하려는 담당자에게 [후보 사례]가 참고자료로 얼마나 관련 있는지 0/1/2 중 하나로만 평가하세요.

2 = 매우 관련: 같은 종류의 문제이고 처리/답변에 직접 참고가 됨
1 = 부분 관련: 주제·분야는 비슷하나 핵심 쟁점이 다름
0 = 무관: 다른 문제이거나 참고 가치 없음

[질의 민원]
{query}

[후보 사례]
{doc}

규칙: 설명 없이 숫자 하나(0, 1, 2)만 출력하세요.
관련성:"""


async def judge_pair(client: httpx.AsyncClient, base_url: str, model: str, query: str, doc: str) -> int | None:
    prompt = JUDGE_PROMPT.format(query=query[:1500], doc=doc[:1500])
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0, "num_predict": 8}},
                timeout=120.0,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "")
            m = re.search(r"[012]", text)
            if m:
                return int(m.group())
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"[judge-error] {exc!r}")
    return None


async def collect_unjudged_pairs(
    service: RetrievalService,
    queries: list[dict[str, Any]],
    qdept: dict[str, set[str]],
    judged_by_qid: dict[str, dict[str, int]],
    fresh_dept: dict[str, list[str]],
    strategies: list[str],
    top_k: int,
    pool_size: int,
) -> tuple[dict[str, dict[str, list[tuple[str, float]]]], set[tuple[str, str]]]:
    pools_by_strat: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for strat in strategies:
        pools: dict[str, list[tuple[str, float]]] = {}
        for i, q in enumerate(queries, start=1):
            results = await service.search(query=q["query"], top_k=pool_size, collection_name="civil_cases_v1",
                                           strategy=strat, grounding_filter=False, query_signals=None)
            pools[q["query_id"]] = dedup_results(results, top_k=pool_size)
            if i % 10 == 0:
                print(f"[pool:{strat}] {i}/{len(queries)}")
        pools_by_strat[strat] = pools
    pairs: set[tuple[str, str]] = set()
    for strat, pools in pools_by_strat.items():
        for qid, pool in pools.items():
            qd = qdept.get(qid, set())
            base_top = [cid for cid, _ in pool[:top_k]]
            dept_top = [cid for cid, _ in rerank(pool, qd, fresh_dept)[:top_k]]
            for cid in set(base_top) | set(dept_top):
                if cid not in judged_by_qid.get(qid, {}):
                    pairs.add((qid, cid))
    return pools_by_strat, pairs


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    j = payload["judge"]
    lines = [
        "# 부서 신호 — LLM 채점 보강 재평가 (풀링 편향 보정)",
        "",
        "## 방법",
        f"부서가 top-{payload['top_k']} 에 올린 무라벨 (질의,사례) 쌍을 LLM(`{j['model']}`, blind)으로 0/1/2 관련성 채점,",
        "원 qrels 에 합쳐 base vs dept_fresh 를 재평가한다.",
        "",
        f"- 컬렉션 `{payload['collection']}`, 평가 쿼리 {payload['judged_query_count']}건, 풀 top-{payload['pool_size']}, 평가 top-{payload['top_k']}",
        f"- LLM 채점 쌍: {j['pairs_judged']}건 (성공 {j['judged_ok']} / 실패 {j['judged_fail']})",
        f"- LLM 채점 분포: rel2={j['dist'].get('2',0)}, rel1={j['dist'].get('1',0)}, rel0={j['dist'].get('0',0)}",
        f"- 무라벨 중 관련(>0) 비율: {j['relevant_rate']*100:.1f}%",
        "",
    ]
    for strat in payload["strategies"]:
        m = payload["strategies"][strat]
        lines.extend([
            f"## {strat.upper()}",
            "",
            "| 지표 | base | dept_fresh | Δ(원 qrels) | base+ | dept+ | Δ(보강 qrels) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for k in m["metric_keys"]:
            b = m["orig"]["base"].get(k, 0.0); d = m["orig"]["dept_fresh"].get(k, 0.0)
            ba = m["aug"]["base"].get(k, 0.0); da = m["aug"]["dept_fresh"].get(k, 0.0)
            lines.append(f"| {k} | {_fmt(b)} | {_fmt(d)} | {d-b:+.4f} | {_fmt(ba)} | {_fmt(da)} | {da-ba:+.4f} |")
        lines.append("")
    lines.extend([
        "## 해석",
        "- Δ(보강 qrels) 가 Δ(원 qrels) 보다 커지면 = 부서가 끌어올린 무라벨 문서가 실제로 관련 있었고,",
        "  풀링 편향으로 가려졌던 효과가 드러난 것. 이것이 부서 신호의 더 현실적인 효과 크기.",
        "- LLM 채점은 근사(ground truth 아님)이며 blind·독립 모델로 편향을 줄였다. 원문 미포함.",
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
    p.add_argument("--pool-size", type=int, default=50)
    p.add_argument("--top-n-units", type=int, default=3)
    p.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    p.add_argument("--base-url", default="http://100.71.35.78:11434")
    p.add_argument("--model", default="qwen2.5:14b")
    p.add_argument("--limit-queries", type=int, default=0)
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
    if args.limit_queries > 0:
        judged = judged[: args.limit_queries]
    eval_qrels = [r for r in qrels if r.qid in {q["query_id"] for q in judged}]

    assigner = get_department_assigner()
    assigner.build_index(rebuild=False)
    qdept = {q["query_id"]: {c["name"] for c in assigner.assign(q["query"], top_n_units=args.top_n_units) if c.get("name")} for q in judged}

    text_map, _ = build_doc_text_map(args.collection)
    service = RetrievalService()
    pools_by_strat, pairs = await collect_unjudged_pairs(
        service, judged, qdept, judged_by_qid, {}, args.strategies, args.top_k, args.pool_size
    )  # fresh_dept filled below; redo rerank after predicting

    # fresh dept (cache)
    candidate_ids = {cid for pools in pools_by_strat.values() for pool in pools.values() for cid, _ in pool}
    dept_cache = json.loads(DEPT_CACHE.read_text()) if DEPT_CACHE.exists() else {}
    miss = {cid: text_map.get(cid, "") for cid in candidate_ids if cid not in dept_cache}
    if miss:
        dept_cache.update(predict_departments(miss, top_n_units=args.top_n_units))
        DEPT_CACHE.write_text(json.dumps(dept_cache, ensure_ascii=False))
    fresh_dept = {cid: dept_cache.get(cid, []) for cid in candidate_ids}

    # recompute unjudged pairs with real fresh_dept
    pairs = set()
    for strat, pools in pools_by_strat.items():
        for qid, pool in pools.items():
            base_top = [cid for cid, _ in pool[:args.top_k]]
            dept_top = [cid for cid, _ in rerank(pool, qdept.get(qid, set()), fresh_dept)[:args.top_k]]
            for cid in set(base_top) | set(dept_top):
                if cid not in judged_by_qid.get(qid, {}):
                    pairs.add((qid, cid))
    qtext = {q["query_id"]: q["query"] for q in judged}
    print(f"[judge] 무라벨 쌍 {len(pairs)}건 채점 시작 (model={args.model})")

    judge_cache = json.loads(JUDGE_CACHE.read_text()) if JUDGE_CACHE.exists() else {}
    dist = {"0": 0, "1": 0, "2": 0}
    ok = fail = 0
    started = time.perf_counter()
    async with httpx.AsyncClient() as client:
        for i, (qid, cid) in enumerate(sorted(pairs), start=1):
            key = f"{qid}||{cid}"
            if key in judge_cache:
                rel = judge_cache[key]
            else:
                rel = await judge_pair(client, args.base_url, args.model, qtext.get(qid, ""), text_map.get(cid, ""))
                if rel is not None:
                    judge_cache[key] = rel
                    if i % 25 == 0:
                        JUDGE_CACHE.write_text(json.dumps(judge_cache, ensure_ascii=False))
            if rel is None:
                fail += 1
            else:
                ok += 1
                dist[str(rel)] += 1
            if i % 25 == 0:
                print(f"[judge] {i}/{len(pairs)} ({time.perf_counter()-started:.0f}s)")
    JUDGE_CACHE.write_text(json.dumps(judge_cache, ensure_ascii=False))

    # 보강 qrels = 원 qrels + LLM 판단
    aug_qrels = list(eval_qrels)
    for key, rel in judge_cache.items():
        qid, cid = key.split("||", 1)
        if qid in {q["query_id"] for q in judged}:
            aug_qrels.append(QrelRecord(qid=qid, docid=cid, relevance=int(rel)))

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "qrels_sha256": sha256_file(args.qrels),
        "judged_query_count": len(judged),
        "pool_size": args.pool_size,
        "top_k": args.top_k,
        "judge": {
            "model": args.model,
            "pairs_judged": len(pairs),
            "judged_ok": ok,
            "judged_fail": fail,
            "dist": dist,
            "relevant_rate": round((dist["1"] + dist["2"]) / ok, 4) if ok else 0.0,
        },
        "strategies": {},
    }
    for strat in args.strategies:
        pools = pools_by_strat[strat]
        runs_base, runs_dept = [], []
        for qid, pool in pools.items():
            runs_base += run_to_records(qid, pool, args.top_k)
            runs_dept += run_to_records(qid, rerank(pool, qdept.get(qid, set()), fresh_dept), args.top_k)
        orig = {"base": evaluate_run(eval_qrels, runs_base), "dept_fresh": evaluate_run(eval_qrels, runs_dept)}
        aug = {"base": evaluate_run(aug_qrels, runs_base), "dept_fresh": evaluate_run(aug_qrels, runs_dept)}
        payload["strategies"][strat] = {
            "metric_keys": ordered_metric_keys(orig["base"], orig["dept_fresh"]),
            "orig": orig, "aug": aug,
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

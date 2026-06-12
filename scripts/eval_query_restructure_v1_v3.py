"""쿼리 버전 불일치 검증: 평가 쿼리를 현재 파이프라인으로 재구조화해 v1·v3 공정 비교.

#369 후속. 보강 qrels 공정 비교에서도 v3가 낮게 나왔는데, 진단 결과 평가 쿼리가
옛 구조화 스타일이라 v1 문서와 더 닮은 것(query↔v1 0.944 > query↔v3 0.926)이 확인됐다.
이 스크립트는 쿼리를 현재 파이프라인(civil_text=민원인 원문만, 새 민원엔 답변 없음)으로
재구조화해, 4조합(v1/v3 × 옛/새 쿼리)을 동일 qrels(원+LLM보강)로 비교한다.

기대(버전 불일치가 원인이라면): v3+새쿼리 > v3+옛쿼리, v1+새쿼리 < v1+옛쿼리,
v3+새쿼리 ≈ v1+옛쿼리(각자 매칭 버전에서 동등 = 운영 현실).
원문 미포함(집계만).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.service import get_structuring_service
from app.structuring.preprocessing import civil_text, _prepared_record
from scripts.build_index import _build_api_case_record
from scripts.eval_be1_metadata_overlay_soft_rerank import dedup_results, load_qrels, load_queries

QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
JUDGE_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_llm_judge_official.json"
QTEXT_CACHE = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "_cache_restructured_queries.json"
OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "query_restructure_v1_v3.md"


def build_source_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in sorted((PROJECT_ROOT / "data" / "Public_Civil_Service_LLM_Data").rglob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            sid = str(item.get("source_id") or "")
            if sid:
                out[sid] = item
    return out


def recs(qid: str, ranked: list[tuple[str, float]], k: int) -> list[RunRecord]:
    return [RunRecord(qid=qid, docid=cid, score=sc, rank=r) for r, (cid, sc) in enumerate(ranked[:k], start=1)]


async def restructure_queries(judged: list[dict[str, Any]], source_map: dict[str, dict[str, Any]]) -> dict[str, str]:
    cache = json.loads(QTEXT_CACHE.read_text()) if QTEXT_CACHE.exists() else {}
    svc = get_structuring_service()
    for i, q in enumerate(judged, start=1):
        qid = q["query_id"]
        if qid in cache:
            continue
        raw = source_map.get(str(q.get("source_id") or ""))
        if not raw:
            cache[qid] = q["query"]  # 폴백: 원 쿼리
            continue
        citizen = civil_text(_prepared_record(raw))
        normalized = {
            "case_id": qid, "text": citizen, "raw_text": citizen,
            "category": q.get("category", ""), "source": q.get("source", ""),
            "region": "", "metadata": {},
        }
        try:
            structured = await svc.structure(normalized)
            rec = _build_api_case_record(normalized, structured)
            cache[qid] = rec.get("text") or q["query"]
        except Exception as e:  # noqa: BLE001
            print(f"[restructure-error] {qid}: {e}")
            cache[qid] = q["query"]
        if i % 10 == 0:
            QTEXT_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
            print(f"[restructure] {i}/{len(judged)}")
    QTEXT_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return cache


async def main():
    queries = load_queries(QUERIES)
    qrels = load_qrels(QRELS)
    rel_qids = {r.qid for r in qrels if r.relevance > 0}
    judged = [q for q in queries if q["query_id"] in rel_qids]
    eval_qrels = [r for r in qrels if r.qid in rel_qids]
    aug = list(eval_qrels)
    if JUDGE_CACHE.exists():
        for k, v in json.loads(JUDGE_CACHE.read_text()).items():
            qid, cid = k.split("||", 1)
            if qid in rel_qids:
                aug.append(QrelRecord(qid=qid, docid=cid, relevance=int(v)))

    old_text = {q["query_id"]: q["query"] for q in judged}
    print("쿼리 재구조화 중 (현재 파이프라인, 민원인 원문)...")
    new_text = await restructure_queries(judged, build_source_map())

    svc = RetrievalService()
    K, POOL = 10, 50
    results: dict[tuple, dict] = {}
    for coll in ("civil_cases_v1", "civil_cases_v3"):
        for ver, qtext in (("old", old_text), ("new", new_text)):
            for strat in ("dense", "hybrid"):
                flat = []
                for q in judged:
                    res = await svc.search(query=qtext[q["query_id"]], top_k=POOL, collection_name=coll,
                                           strategy=strat, grounding_filter=False, query_signals=None)
                    flat += recs(q["query_id"], dedup_results(res, top_k=POOL), K)
                results[(coll, ver, strat)] = evaluate_run(aug, flat)
                print(f"[{coll.split('_')[-1]}/{ver}/{strat}] nDCG@10={results[(coll,ver,strat)].get('nDCG@10',0):.4f}")

    lines = ["# 쿼리 재구조화 공정 비교 (v1 vs v3, 버전 불일치 보정)", "",
             f"- 평가 쿼리 {len(judged)}건, top-{K}, 보강 qrels(원+LLM 공식기준)",
             "- 쿼리를 현재 파이프라인으로 재구조화(민원인 원문)해 버전 불일치 분리", "",
             "| 컬렉션 | 쿼리버전 | dense nDCG@10 | hybrid nDCG@10 | dense R@10 | hybrid R@10 |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for coll in ("civil_cases_v1", "civil_cases_v3"):
        for ver in ("old", "new"):
            d = results[(coll, ver, "dense")]; h = results[(coll, ver, "hybrid")]
            lines.append(f"| {coll.split('_')[-1]} | {ver} | {d.get('nDCG@10',0):.4f} | {h.get('nDCG@10',0):.4f} "
                         f"| {d.get('R@10',0):.4f} | {h.get('R@10',0):.4f} |")
    # 핵심 비교
    v1o = results[("civil_cases_v1","old","dense")].get("nDCG@10",0)
    v3n = results[("civil_cases_v3","new","dense")].get("nDCG@10",0)
    v3o = results[("civil_cases_v3","old","dense")].get("nDCG@10",0)
    v1n = results[("civil_cases_v1","new","dense")].get("nDCG@10",0)
    lines += ["", "## 핵심 비교 (dense nDCG@10)",
              f"- 운영 현실: **v3+새쿼리 {v3n:.4f}** vs v1+옛쿼리 {v1o:.4f} (Δ {v3n-v1o:+.4f})",
              f"- 재구조화 효과: v3 옛쿼리 {v3o:.4f} → 새쿼리 {v3n:.4f} (Δ {v3n-v3o:+.4f})",
              f"- 대칭 확인: v1 옛쿼리 {v1o:.4f} → 새쿼리 {v1n:.4f} (Δ {v1n-v1o:+.4f})", "",
              "## 해석",
              "- v3+새쿼리가 v1+옛쿼리와 비등하면, 앞선 'v3 하락'은 쿼리 버전 불일치 인공물.",
              "- v3는 새쿼리에서, v1은 옛쿼리에서 각각 최고 = 같은 버전끼리 매칭(운영 현실).", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[WRITE] {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())

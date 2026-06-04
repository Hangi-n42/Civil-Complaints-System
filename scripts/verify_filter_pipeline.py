"""LLM 필터 파이프라인 end-to-end 검증 (#303).

#301에서 구현한 LLMRelevanceFilterStage를 **실제 파이프라인 runner**로 돌려,
오프라인 분석(#299: grounding 해로움 23%→4%)이 프로덕션 코드 경로에서 재현되는지 확인.

  - baseline: hybrid_bm25_dense_rrf.yaml (필터 없음)
  - filter  : hybrid_bm25_dense_rrf_llmfilter.yaml (LLM 필터, top_k·final을 10으로 상향)
  둘 다 RetrievalPipelineRunner로 실행 → normalize_to_case → no-self → top-5 → canonical qrels로 분해.

필터는 LLM 호출이라 per-query 체크포인트(중단 재개). LLM=원격 qwen2.5:14b(env로 지정).
산출: reports/retrieval/v3/verify_filter_pipeline.json

실행:
  OLLAMA_BASE_URL=http://100.71.35.78:11434 OLLAMA_MODEL=qwen2.5:14b \
    python scripts/verify_filter_pipeline.py [--resume] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.datasets import EvalQuery
from app.retrieval.pipeline.runner import PipelineSpec, RetrievalPipelineRunner, load_pipeline_spec
from scripts.run_v3_evaluation import load_queries
from scripts.reranker_diagnosis import chunk_to_case
from scripts.grounding_topk_breakdown import load_rel_map

CFG_DIR = ROOT / "configs" / "retrieval_pipelines"
BASE_YAML = CFG_DIR / "hybrid_bm25_dense_rrf.yaml"
FILTER_YAML = CFG_DIR / "hybrid_bm25_dense_rrf_llmfilter.yaml"
CKPT = ROOT / "data" / "evaluation" / "v3" / "checkpoints" / "verify_filter_pipeline.json"
OUT = ROOT / "reports" / "retrieval" / "v3" / "verify_filter_pipeline.json"
TOPK = 5


def bump_spec(yaml_path: Path, filter_topk: int = 10, final_topk: int = 10) -> PipelineSpec:
    """필터/최종 top_k를 상향(case 정규화 후 top-5 확보)."""
    spec = load_pipeline_spec(yaml_path)
    raw = copy.deepcopy(spec.raw)
    for st in raw.get("stages", []):
        if st.get("type") == "llm_relevance_filter":
            st.setdefault("params", {})["top_k"] = filter_topk
    raw.setdefault("final", {})["take_top_k"] = final_topk
    return PipelineSpec(pipeline_id=spec.pipeline_id, seed=spec.seed,
                        stages=list(raw.get("stages") or []), final_top_k=final_topk,
                        raw=raw, source_path=yaml_path)


def to_eval(q: dict) -> EvalQuery:
    return EvalQuery(qid=q["query_id"], text=q["query"],
                     metadata={"category": q.get("category", ""), "source": q.get("source", "")})


def case_topk(records: list[tuple[str, float]], self_case: str, k: int) -> list[str]:
    """chunk → case dedup, self 제거, 상위 k case."""
    seen, out = set(), []
    for docid, _ in records:
        cid = chunk_to_case(docid)
        if cid == self_case or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= k:
            break
    return out


def classify(per_query: dict[str, list[str]], rel_map, self_case_map) -> dict:
    slots, q_harmful, q_empty, filled = Counter(), 0, 0, []
    for qid, cases in per_query.items():
        if not cases:
            q_empty += 1
        filled.append(len(cases))
        harmful = 0
        for cid in cases:
            rel = rel_map.get((qid, cid))
            slots["unjudged" if rel is None else f"rel{rel}"] += 1
            if rel == 0:
                harmful += 1
        if harmful >= 1:
            q_harmful += 1
    total = sum(slots.values())
    nq = len(per_query)
    return {
        "n_queries": nq, "total_slots": total,
        "slots": {k: slots.get(k, 0) for k in ["rel2", "rel1", "rel0", "unjudged"]},
        "harmful_rate": round(slots.get("rel0", 0) / total, 4) if total else 0.0,
        "useful_rate": round((slots.get("rel2", 0) + slots.get("rel1", 0)) / total, 4) if total else 0.0,
        "queries_with_harmful_pct": round(q_harmful / nq, 4) if nq else 0.0,
        "queries_empty": q_empty,
        "avg_filled": round(sum(filled) / nq, 3) if nq else 0.0,
    }


async def run_filter(queries, self_case_map, resume) -> dict[str, list[str]]:
    runner = RetrievalPipelineRunner(bump_spec(FILTER_YAML))
    done = json.loads(CKPT.read_text(encoding="utf-8")) if (resume and CKPT.exists()) else {}
    todo = [q for q in queries if q["query_id"] not in done]
    print(f"[filter] runner 초기화 완료 | 완료 {len(done)} | 이번 {len(todo)}")
    for i, q in enumerate(todo, 1):
        res = await runner.run_query(to_eval(q))
        recs = [(d.docid, d.score) for d in res.final_docs]
        done[q["query_id"]] = case_topk(recs, self_case_map[q["query_id"]], TOPK)
        CKPT.parent.mkdir(parents=True, exist_ok=True)
        CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        print(f"  [{i}/{len(todo)}] {q['query_id']} → 근거 {len(done[q['query_id']])}개")
    return done


def run_baseline(queries, self_case_map) -> dict[str, list[str]]:
    runner = RetrievalPipelineRunner(bump_spec(BASE_YAML))
    results = runner.run_sync([to_eval(q) for q in queries])
    out = {}
    for r in results:
        recs = [(d.docid, d.score) for d in r.final_docs]
        out[r.query.qid] = case_topk(recs, self_case_map[r.query.qid], TOPK)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="앞 N쿼리만(스모크)")
    args = ap.parse_args()

    queries = load_queries()
    if args.limit:
        queries = queries[:args.limit]
    self_case_map = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    rel_map = load_rel_map()

    print("[baseline] hybrid (필터 없음) 실행...")
    base = run_baseline(queries, self_case_map)
    print("[filter] hybrid + LLM 필터 실행 (원격 GPU)...")
    filt = asyncio.run(run_filter(queries, self_case_map, args.resume))

    report = {"n_queries": len(queries), "topk": TOPK,
              "baseline": classify(base, rel_map, self_case_map),
              "filter": classify(filt, rel_map, self_case_map)}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    b, f = report["baseline"], report["filter"]
    print(f"\n{'='*70}\nend-to-end 검증: baseline vs LLM필터 (top-{TOPK}, no-self, 실제 파이프라인)")
    print(f"{'':<10}{'해로움(rel0)':>14}{'유효(rel≥1)':>13}{'0점섞인쿼리':>13}{'근거0개':>9}{'평균근거':>9}")
    for name, m in (("baseline", b), ("filter", f)):
        print(f"{name:<10}{m['harmful_rate']:>13.1%}{m['useful_rate']:>13.1%}"
              f"{m['queries_with_harmful_pct']:>12.1%}{m['queries_empty']:>9}{m['avg_filled']:>9.2f}")
    verdict = "통과" if f["harmful_rate"] < b["harmful_rate"] - 0.05 else "확인필요"
    print(f"\n판정: {verdict} (필터가 해로움을 {(b['harmful_rate']-f['harmful_rate'])*100:.1f}%p 감소)")
    print(f"[리포트] {OUT}")


if __name__ == "__main__":
    main()

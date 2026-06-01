"""LLM 리랭커 (A): 관련성 루브릭 기반 재정렬. (#283)

cross-encoder 리랭커는 일반 관련성 기준이라 Hybrid을 떨어뜨렸다(#280).
가설: 우리 관련성 루브릭(judge와 동일 SYSTEM_PROMPT)을 LLM에 직접 주고 재정렬하면
"기준 불일치"가 해소돼 개선될 수 있다(학습 불필요).

방법:
  - Hybrid(BM25+Dense RRF) top-10 후보 각각을 LLM으로 0~2 점수화
  - LLM 점수 desc로 재정렬, 동점은 기존 Hybrid 순서 유지(안정 정렬)
  - **held-out test 20쿼리에서만** 평가(train 누수 방지, #271 split과 동일)
  - Hybrid 단독 / Hybrid+LLM / (참고)Hybrid+CrossEncoder 비교

LLM 추론: Tailscale로 Windows GPU(qwen2.5:14b). judge_pool_qwen의 호출·프롬프트 재사용.

산출: reports/retrieval/v3/eval_llm_reranker.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense
from scripts.eval_noself import get, load_qrels_pooled, metrics, take_top
from scripts.eval_hybrid_noself import rrf
from scripts.judge_pool_qwen import call_qwen, build_prompt, QWEN_MODEL, OLLAMA_URL
from app.evaluation.metrics import RunRecord

OUT = ROOT / "reports" / "retrieval" / "v3" / "eval_llm_reranker.json"
TEST_QIDS_PATH = ROOT / "data" / "finetune" / "reranker" / "test_qids.txt"
DEPTH = 50          # BM25/Dense 후보 깊이
RERANK_TOPK = 10    # LLM이 재정렬할 Hybrid 상위 후보 수
METRIC_KEYS = ["nDCG@10", "AP@10", "RR@5", "nDCG@5", "P@5", "R@10"]


def load_test_qids() -> set[str]:
    return {ln.strip() for ln in TEST_QIDS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()}


def llm_rerank(hybrid, qtext, corpus, top_k=RERANK_TOPK):
    """Hybrid top_k 후보를 LLM 0~2 점수로 안정 재정렬. 점수 None이면 0 취급."""
    out: dict[str, list[RunRecord]] = {}
    n_calls = 0
    started = time.perf_counter()
    items = list(hybrid.items())
    for qi, (qid, recs) in enumerate(items, 1):
        cand = sorted(recs, key=lambda x: x.rank)[:top_k]
        scored = []
        for orig_rank, r in enumerate(cand, 1):
            doc = corpus.get(r.docid, "")
            s = call_qwen(build_prompt(qtext[qid], doc)) if doc else None
            n_calls += 1
            scored.append((r, s if s is not None else 0, orig_rank))
        # LLM 점수 desc, 동점은 원래 Hybrid 순서(orig_rank asc) — 안정
        scored.sort(key=lambda t: (-t[1], t[2]))
        out[qid] = [RunRecord(qid=qid, docid=r.docid, score=float(top_k - i), rank=i + 1)
                    for i, (r, s, _) in enumerate(scored)]
        rate = n_calls / (time.perf_counter() - started)
        print(f"  [{qi}/{len(items)}] {qid} rerank 완료 | {rate:.2f} calls/s")
    return out


def main() -> None:
    R.TOP_K = DEPTH
    test_qids = load_test_qids()
    queries_all = load_queries()
    queries = [q for q in queries_all if q["query_id"] in test_qids]
    qtext = {q["query_id"]: q["query"] for q in queries}
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    qrels = load_qrels_pooled()
    # test 20쿼리로 한정 (run도 test뿐 → qrels에 train 80쿼리가 섞이면 0점으로 평균돼 점수 왜곡)
    qrels_noself = [q for q in qrels if q.qid in test_qids and self_doc.get(q.qid) != q.docid]
    print(f"test 쿼리 {len(queries)} (held-out) | LLM={QWEN_MODEL} @ {OLLAMA_URL}")

    corpus_meta = load_corpus()
    # case_id -> chunk_text (LLM 입력용)
    corpus = {}
    for d in corpus_meta:
        cid = d.get("case_id", "")
        if cid and cid not in corpus:
            corpus[cid] = d.get("chunk_text", "")

    print("[1] BM25..."); bm25 = run_bm25(queries, corpus_meta)
    print("[2] Dense..."); dense = run_dense(queries)
    hybrid = rrf([bm25, dense])
    print("[3] LLM 리랭커 재정렬...")
    hy_llm = llm_rerank(hybrid, qtext, corpus)

    report = {"eval_set": "qrels_pooled_3judge, NO-self, test 20q", "llm": QWEN_MODEL, "no_self": {}}
    for name, runs in {"Hybrid": hybrid, "Hybrid+LLM": hy_llm}.items():
        report["no_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=True), qrels_noself)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    order = ["Hybrid", "Hybrid+LLM"]
    print("\n" + "=" * 64)
    print(f"LLM 리랭커 (test 20q, NO-self·3채점관)")
    print("=" * 64)
    print(f"{'지표':<9}" + "".join(f"{o:>14}" for o in order) + f"{'Δ':>10}")
    for k in METRIC_KEYS:
        hy = get(report["no_self"]["Hybrid"], k)
        hl = get(report["no_self"]["Hybrid+LLM"], k)
        print(f"{k:<9}{hy:>14.4f}{hl:>14.4f}{hl-hy:>+10.4f}")
    print(f"\n[리포트] {OUT}")
    print("판정: Hybrid+LLM이 Hybrid를 넘으면 LLM 리랭커 유효(상한 확인).")


if __name__ == "__main__":
    main()

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
CKPT_DIR = ROOT / "data" / "evaluation" / "v3" / "checkpoints"
DEPTH = 50          # BM25/Dense 후보 깊이
RERANK_TOPK = 10    # LLM이 재정렬할 Hybrid 상위 후보 수
METRIC_KEYS = ["nDCG@10", "AP@10", "RR@5", "nDCG@5", "P@5", "R@10"]


def load_test_qids() -> set[str]:
    return {ln.strip() for ln in TEST_QIDS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()}


def llm_rerank(hybrid, qtext, corpus, ckpt_path, top_k=RERANK_TOPK):
    """Hybrid top_k 후보를 LLM 0~2 점수로 안정 재정렬. 점수 None이면 0 취급.

    (qid::docid) 단위로 LLM 점수를 ckpt_path에 저장/재개 → 중단돼도 이어서 실행.
    """
    scores_ck: dict[str, int] = {}
    if ckpt_path.exists():
        scores_ck = json.loads(ckpt_path.read_text(encoding="utf-8"))
        print(f"  [체크포인트] {len(scores_ck)}개 점수 로드, 재개")

    out: dict[str, list[RunRecord]] = {}
    n_new = 0
    started = time.perf_counter()
    items = list(hybrid.items())
    for qi, (qid, recs) in enumerate(items, 1):
        cand = sorted(recs, key=lambda x: x.rank)[:top_k]
        scored = []
        for orig_rank, r in enumerate(cand, 1):
            key = f"{qid}::{r.docid}"
            if key in scores_ck:
                s = scores_ck[key]
            else:
                doc = corpus.get(r.docid, "")
                s = call_qwen(build_prompt(qtext[qid], doc)) if doc else None
                scores_ck[key] = s if s is not None else 0
                n_new += 1
                if n_new % 10 == 0:
                    ckpt_path.write_text(json.dumps(scores_ck, ensure_ascii=False), encoding="utf-8")
            scored.append((r, scores_ck[key] if scores_ck[key] is not None else 0, orig_rank))
        scored.sort(key=lambda t: (-t[1], t[2]))  # 점수 desc, 동점은 Hybrid 순서(안정)
        out[qid] = [RunRecord(qid=qid, docid=r.docid, score=float(top_k - i), rank=i + 1)
                    for i, (r, s, _) in enumerate(scored)]
        rate = n_new / (time.perf_counter() - started) if n_new else 0
        print(f"  [{qi}/{len(items)}] {qid} rerank 완료 | 신규 {n_new}건 {rate:.2f} calls/s")
    ckpt_path.write_text(json.dumps(scores_ck, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="전체 100쿼리 평가(LLM 리랭커는 학습 없어 누수 없음). 미지정 시 test 20쿼리.")
    args = ap.parse_args()

    R.TOP_K = DEPTH
    queries_all = load_queries()
    if args.full:
        eval_qids = {q["query_id"] for q in queries_all}
        out_path = OUT.with_name("eval_llm_reranker_full.json")
        scope = f"전체 {len(eval_qids)}쿼리"
    else:
        eval_qids = load_test_qids()
        out_path = OUT
        scope = f"test {len(eval_qids)}쿼리(held-out)"
    queries = [q for q in queries_all if q["query_id"] in eval_qids]
    qtext = {q["query_id"]: q["query"] for q in queries}
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    qrels = load_qrels_pooled()
    # 평가 쿼리로 qrels 한정 (run에 없는 쿼리가 qrels에 섞이면 0점으로 평균돼 점수 왜곡)
    qrels_noself = [q for q in qrels if q.qid in eval_qids and self_doc.get(q.qid) != q.docid]
    print(f"{scope} | LLM={QWEN_MODEL} @ {OLLAMA_URL}")

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
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = CKPT_DIR / ("llm_rerank_full.json" if args.full else "llm_rerank_test.json")
    hy_llm = llm_rerank(hybrid, qtext, corpus, ckpt_path)

    report = {"eval_set": f"qrels_pooled_3judge, NO-self, {scope}", "llm": QWEN_MODEL,
              "n_queries": len(queries), "no_self": {}}
    for name, runs in {"Hybrid": hybrid, "Hybrid+LLM": hy_llm}.items():
        report["no_self"][name] = metrics(take_top(runs, self_doc, 10, drop_self=True), qrels_noself)

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    order = ["Hybrid", "Hybrid+LLM"]
    print("\n" + "=" * 64)
    print(f"LLM 리랭커 (test 20q, NO-self·3채점관)")
    print("=" * 64)
    print(f"{'지표':<9}" + "".join(f"{o:>14}" for o in order) + f"{'Δ':>10}")
    for k in METRIC_KEYS:
        hy = get(report["no_self"]["Hybrid"], k)
        hl = get(report["no_self"]["Hybrid+LLM"], k)
        print(f"{k:<9}{hy:>14.4f}{hl:>14.4f}{hl-hy:>+10.4f}")
    print(f"\n[리포트] {out_path}")
    print("판정: Hybrid+LLM이 Hybrid를 넘으면 LLM 리랭커 유효(상한 확인).")


if __name__ == "__main__":
    main()

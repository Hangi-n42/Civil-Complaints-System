"""스폿체크 2단계: 전수 스캔으로 풀 불완전성 측정 (#290).

#288에서 검증된 빠른 스캐너(exaone3.5:7.8b, score-only, num_predict=24;
graded κ 0.84, rel>=1 recall 0.88)로, 10쿼리 각각에 대해 코퍼스 전체(9,132 case)를
0/1/2 채점한다.

스캐너가 rel>=1로 본 문서 중 **기존 풀(qrels_pooled_3judge)에 없던** 것
= BM25+Dense top-50 풀이 놓친 "유사문서 후보". 이 수가 풀 불완전성을 정량화한다.

- 10쿼리: seed=42로 100쿼리에서 고정 추출.
- self-doc(CASE-source_id)·이미 풀에 있는 문서는 채점하되, 신규 후보 집계에서 구분.
- (qid::docid) 체크포인트로 중단·재개. ~10h 야간(Windows GPU).

산출:
  checkpoints/full_scan.json          (qid::docid -> 0/1/2)
  full_scan_incompleteness.json       (쿼리별 신규 후보 수·불완전성 요약)

실행:
  python scripts/spotcheck_full_scan.py --smoke 1 --max-docs 100   # 스모크
  python scripts/spotcheck_full_scan.py --resume                   # 전수(야간)
  python scripts/spotcheck_full_scan.py --aggregate-only           # 집계만
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import load_corpus
from scripts.run_v3_evaluation import load_queries as load_queries_full
from scripts.spotcheck_scanner_validation import build_fast_prompt, call_scanner, SCANNER_MODEL, OLLAMA_URL

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
QRELS_PATH = DATA_DIR / "qrels_pooled_3judge.tsv"
SCAN_CKPT = DATA_DIR / "checkpoints" / "full_scan.json"
OUT_REPORT = DATA_DIR / "full_scan_incompleteness.json"
N_QUERIES = 10
SEED = 42
CHECKPOINT_EVERY = 25


def pick_queries(queries: list[dict]) -> list[dict]:
    """seed=42로 100쿼리에서 10개 고정 추출(query_id 정렬 후)."""
    ordered = sorted(queries, key=lambda q: q["query_id"])
    rng = random.Random(SEED)
    return sorted(rng.sample(ordered, N_QUERIES), key=lambda q: q["query_id"])


def load_pool_by_query() -> dict[str, dict[str, int]]:
    """qid -> {docid: rel} (기존 풀에서 이미 판정된 문서)."""
    pool: dict[str, dict[str, int]] = {}
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            p = line.rstrip("\n").split("\t")
            if i == 0 and p[0].lower() in {"qid", "query_id"}:
                continue
            if len(p) == 4:
                qid, docid, rel = p[0], p[2], int(p[3])
            elif len(p) == 3:
                qid, docid, rel = p[0], p[1], int(p[2])
            else:
                continue
            pool.setdefault(qid, {})[docid] = rel
    return pool


def aggregate(sel_queries: list[dict], corpus: dict, done: dict) -> dict:
    pool = load_pool_by_query()
    per_query = []
    tot_new = tot_pool_pos = 0
    for q in sel_queries:
        qid = q["query_id"]
        judged = pool.get(qid, {})
        pool_pos = {d for d, r in judged.items() if r >= 1}
        scanner_pos, new_cand = [], []
        scored = 0
        for docid in corpus:
            s = done.get(f"{qid}::{docid}")
            if s is None:
                continue
            scored += 1
            if s >= 1:
                scanner_pos.append(docid)
                if docid not in judged:               # 풀에 아예 없던 문서
                    new_cand.append(docid)
        n_new, n_pool_pos = len(new_cand), len(pool_pos)
        denom = n_pool_pos + n_new
        per_query.append({
            "qid": qid,
            "n_scored": scored,
            "n_scanner_pos": len(scanner_pos),
            "n_pool_judged": len(judged),
            "n_pool_pos": n_pool_pos,
            "n_new_candidates": n_new,
            "incompleteness_raw": round(n_new / denom, 4) if denom else 0.0,
            "new_candidate_docids": sorted(new_cand),
        })
        tot_new += n_new
        tot_pool_pos += n_pool_pos

    denom = tot_pool_pos + tot_new
    return {
        "scanner": SCANNER_MODEL,
        "config": "score-only, num_predict=24 (validated #288: recall 0.88)",
        "n_queries": len(sel_queries),
        "query_ids": [q["query_id"] for q in sel_queries],
        "corpus_size": len(corpus),
        "totals": {
            "pool_positive": tot_pool_pos,
            "new_candidates": tot_new,
            "incompleteness_raw": round(tot_new / denom, 4) if denom else 0.0,
            "note": "raw = 스캐너 미확정. 신규후보는 3단계(3채점관)로 확정 필요. recall 0.88이라 하한.",
        },
        "per_query": per_query,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--smoke", type=int, default=0, help="스모크: 앞 N쿼리만")
    ap.add_argument("--max-docs", type=int, default=0, help="스모크: 쿼리당 코퍼스 앞 N건만")
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--workers", type=int, default=3, help="동시 요청 수(병렬). temp=0이라 결과 동일.")
    args = ap.parse_args()

    corpus = load_corpus()
    sel = pick_queries(load_queries_full())
    if args.smoke:
        sel = sel[:args.smoke]
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in sel}
    done = json.loads(SCAN_CKPT.read_text(encoding="utf-8")) if (args.resume and SCAN_CKPT.exists()) else {}

    if not args.aggregate_only:
        doc_ids = list(corpus)
        if args.max_docs:
            doc_ids = doc_ids[:args.max_docs]
        todo = [(q["query_id"], q["query"], d)
                for q in sel for d in doc_ids
                if self_doc[q["query_id"]] != d and f"{q['query_id']}::{d}" not in done]
        print("=" * 64)
        print(f"전수 스캔 | {SCANNER_MODEL} @ {OLLAMA_URL}")
        print(f"쿼리 {len(sel)} × 코퍼스 {len(doc_ids)} | 완료 {len(done)} | 이번 {len(todo)}")
        print(f"쿼리: {[q['query_id'] for q in sel]}")
        print("=" * 64)

        workers = max(1, args.workers)
        batch = workers * 10                      # 배치마다 체크포인트(≤batch건만 손실 위험)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for start in range(0, len(todo), batch):
                chunk = todo[start:start + batch]
                scores = list(ex.map(
                    lambda t: call_scanner(build_fast_prompt(t[1], corpus[t[2]])), chunk))
                for (qid, _qt, docid), s in zip(chunk, scores):
                    done[f"{qid}::{docid}"] = s
                n = start + len(chunk)
                SCAN_CKPT.parent.mkdir(parents=True, exist_ok=True)
                SCAN_CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                rate = n / (time.perf_counter() - started)
                eta = (len(todo) - n) / rate / 60 if rate else 0
                print(f"  [{n}/{len(todo)}] {chunk[-1][0]}::{chunk[-1][2]}={scores[-1]} | {rate:.2f}쌍/s ETA {eta:.0f}분")

    report = aggregate(sel, corpus, done)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    t = report["totals"]
    print(f"\n{'='*64}\n[집계] 풀 불완전성 (raw, 스캐너 미확정)")
    print(f"  기존 풀 양성 {t['pool_positive']} | 신규 후보 {t['new_candidates']} | 불완전성 {t['incompleteness_raw']:.1%}")
    for pq in report["per_query"]:
        print(f"   {pq['qid']}: 풀양성 {pq['n_pool_pos']:>3} + 신규 {pq['n_new_candidates']:>3} "
              f"→ 불완전성 {pq['incompleteness_raw']:.1%} (채점 {pq['n_scored']})")
    print(f"\n[리포트] {OUT_REPORT}")


if __name__ == "__main__":
    main()

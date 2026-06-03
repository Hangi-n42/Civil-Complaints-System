"""스폿체크 3단계: 정식 3채점관 검증 (#290 후속).

전수 스캔(2단계, #290)을 빠른 단일 스캐너로 했으므로, 그 결과를
**canonical과 동일한 정식 3채점관(full 설정, median)**으로 검증한다.

  --mode confirm : 스캐너가 rel>=1로 본 '풀 밖' 신규 후보를 3채점관이 확정+등급.
                   → 거짓양성 제거 후 진짜 놓친 유사문서 수 = 풀 불완전성(확정).
  --mode audit   : 스캐너가 0이라 버린 '풀 밖' 문서의 무작위 표본을 3채점관이 재채점.
                   → 스캐너 false-negative(놓침) 발견 → 누락 추정 보정 + Wilson 95% CI.
                   (한계: 풀 밖 음성의 FN은 희소 → 무작위 표본은 대개 상한만 제공.)
   추가로 audit는 'in-pool recall'(이미 라벨 있는 풀 문서에서 스캐너 재현율)을 무료 계산.

집계는 canonical qrels와 동일: median(3 judges), floor on tie (agg_median).
LLM: Tailscale로 Windows GPU. exaone3.5:7.8b+gemma3:12b(call_ollama)+qwen2.5:14b(call_qwen), full num_predict=128.

실행:
  python scripts/spotcheck_3judge_verify.py --mode confirm [--resume]
  python scripts/spotcheck_3judge_verify.py --mode audit --sample 1500 [--resume]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import load_corpus
from scripts.run_v3_evaluation import load_queries as load_queries_full
from scripts.judge_fair_pool import call_ollama, build_prompt
from scripts.judge_pool_qwen import call_qwen, agg_median, QWEN_MODEL
from scripts.spotcheck_full_scan import pick_queries, load_pool_by_query, SCAN_CKPT

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
CKPT_DIR = DATA_DIR / "checkpoints"
JUDGES = ["exaone3.5:7.8b", "gemma3:12b", QWEN_MODEL]
SEED = 42
CHECKPOINT_EVERY = 10


def judge_pairs_3(pairs: list[tuple[str, str]], qtext: dict, corpus: dict, ckpt_path: Path) -> dict:
    """주어진 (qid,docid) 쌍들을 정식 3채점관(full)으로 채점. 모델별 2패스(스왑 방지), 재개."""
    done = json.loads(ckpt_path.read_text(encoding="utf-8")) if ckpt_path.exists() else {}
    for model in JUDGES:
        pending = [(q, d) for q, d in pairs if model not in done.get(f"{q}::{d}", {})]
        if not pending:
            continue
        print(f"── [{model}] {len(pending)}쌍 ──")
        started = time.perf_counter()
        for i, (qid, docid) in enumerate(pending, 1):
            key = f"{qid}::{docid}"
            rec = done.setdefault(key, {})
            q, c = qtext.get(qid, ""), corpus.get(docid, "")
            if not q or not c:
                rec[model] = None
            elif model == QWEN_MODEL:
                rec[model] = call_qwen(build_prompt(q, c))
            else:
                rec[model] = call_ollama(model, build_prompt(q, c))
            if i % CHECKPOINT_EVERY == 0 or i == len(pending):
                ckpt_path.parent.mkdir(parents=True, exist_ok=True)
                ckpt_path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                rate = i / (time.perf_counter() - started)
                eta = (len(pending) - i) / rate / 60 if rate else 0
                print(f"  [{model}] {i}/{len(pending)} {key}={rec[model]} | {rate:.2f}쌍/s ETA {eta:.0f}분")
        ckpt_path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    # median 집계
    for key in list(done):
        r = done[key]
        r["rel"] = agg_median([r.get(m) for m in JUDGES])
    ckpt_path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    return done


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """이항 비율 Wilson 95% 신뢰구간."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - rad) / d, (c + rad) / d)


def load_context():
    corpus = load_corpus()
    sel = pick_queries(load_queries_full())
    qtext = {q["query_id"]: q["query"] for q in sel}
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in sel}
    pool = load_pool_by_query()
    scan = json.loads(SCAN_CKPT.read_text(encoding="utf-8"))
    return corpus, sel, qtext, self_doc, pool, scan


def run_confirm(resume: bool) -> dict:
    corpus, sel, qtext, self_doc, pool, scan = load_context()
    # 신규 후보: 스캐너 rel>=1 & 풀 밖 & self 아님
    pairs = []
    for q in sel:
        qid = q["query_id"]; judged = pool.get(qid, {})
        for docid in corpus:
            s = scan.get(f"{qid}::{docid}")
            if s is not None and s >= 1 and docid not in judged and docid != self_doc[qid]:
                pairs.append((qid, docid))
    print(f"[confirm] 신규 후보 {len(pairs)}쌍 × 3채점관 full")
    done = judge_pairs_3(pairs, qtext, corpus, CKPT_DIR / "verify_confirm.json")

    per_q, tot_conf, tot_pool_pos = [], 0, 0
    for q in sel:
        qid = q["query_id"]
        pool_pos = sum(1 for r in pool.get(qid, {}).values() if r >= 1)
        cand = [(qid, d) for (qq, d) in pairs if qq == qid]
        conf = [(d, done[f"{qid}::{d}"]["rel"]) for (_, d) in cand if done[f"{qid}::{d}"]["rel"] >= 1]
        denom = pool_pos + len(conf)
        per_q.append({"qid": qid, "n_candidates": len(cand), "n_confirmed": len(conf),
                      "n_pool_pos": pool_pos,
                      "confirmed_rel_dist": dict(sorted(Counter(r for _, r in conf).items())),
                      "incompleteness_confirmed": round(len(conf) / denom, 4) if denom else 0.0})
        tot_conf += len(conf); tot_pool_pos += pool_pos
    n_cand = len(pairs)
    denom = tot_pool_pos + tot_conf
    return {"mode": "confirm", "judges": JUDGES, "n_candidates": n_cand, "n_confirmed": tot_conf,
            "scanner_precision_on_new": round(tot_conf / n_cand, 4) if n_cand else None,
            "totals": {"pool_positive": tot_pool_pos, "confirmed_new": tot_conf,
                       "incompleteness_confirmed": round(tot_conf / denom, 4) if denom else 0.0},
            "per_query": per_q}


def run_audit(sample_n: int, resume: bool) -> dict:
    corpus, sel, qtext, self_doc, pool, scan = load_context()
    # 무료: in-pool recall (풀에 라벨 있는 문서에서 스캐너 재현율)
    in_pool_pos = in_pool_hit = 0
    for q in sel:
        qid = q["query_id"]
        for docid, rel in pool.get(qid, {}).items():
            if rel >= 1 and f"{qid}::{docid}" in scan:
                in_pool_pos += 1
                if scan[f"{qid}::{docid}"] >= 1:
                    in_pool_hit += 1
    in_pool_recall = round(in_pool_hit / in_pool_pos, 4) if in_pool_pos else None

    # 표본: 스캐너 0 & 풀 밖 & self 아님 (전체 음성 모집단)
    negatives = []
    for q in sel:
        qid = q["query_id"]; judged = pool.get(qid, {})
        for docid in corpus:
            s = scan.get(f"{qid}::{docid}")
            if s == 0 and docid not in judged and docid != self_doc[qid]:
                negatives.append((qid, docid))
    rng = random.Random(SEED)
    sample = rng.sample(negatives, min(sample_n, len(negatives)))
    print(f"[audit] 풀밖 음성 {len(negatives)} 중 {len(sample)} 표본 × 3채점관 full | in-pool recall={in_pool_recall}")
    done = judge_pairs_3(sample, qtext, corpus, CKPT_DIR / "verify_audit.json")

    fn = [(k, done[f"{q}::{d}"]["rel"]) for (q, d) in sample
          for k in [f"{q}::{d}"] if done[k]["rel"] >= 1]
    n, k = len(sample), len(fn)
    fn_rate = k / n if n else 0.0
    lo, hi = wilson_ci(k, n)
    est_missed = fn_rate * len(negatives)
    return {"mode": "audit", "judges": JUDGES, "in_pool_recall": in_pool_recall,
            "in_pool_pos": in_pool_pos, "in_pool_hit": in_pool_hit,
            "n_negatives_total": len(negatives), "n_sampled": n, "n_false_neg": k,
            "fn_rate": round(fn_rate, 5), "fn_rate_ci95": [round(lo, 5), round(hi, 5)],
            "est_missed_in_long_tail": round(est_missed, 1),
            "est_missed_ci95": [round(lo * len(negatives), 1), round(hi * len(negatives), 1)],
            "false_neg_examples": fn[:20],
            "note": "풀밖 음성의 FN은 희소 → 표본이 0이면 상한만 의미. in_pool_recall은 top-50 근접문서 기준 별도 재현율."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["confirm", "audit"], required=True)
    ap.add_argument("--sample", type=int, default=1500, help="audit 표본 크기")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    if args.mode == "confirm":
        rep = run_confirm(args.resume)
        out = DATA_DIR / "spotcheck_confirm_report.json"
        t = rep["totals"]
        print(f"\n{'='*64}\n[confirm] 신규후보 {rep['n_candidates']} → 확정 {rep['n_confirmed']} "
              f"(스캐너 신규정밀도 {rep['scanner_precision_on_new']})")
        print(f"  풀양성 {t['pool_positive']} + 확정신규 {t['confirmed_new']} → 불완전성(확정) {t['incompleteness_confirmed']:.1%}")
        for pq in rep["per_query"]:
            print(f"   {pq['qid']}: 후보 {pq['n_candidates']:>3} → 확정 {pq['n_confirmed']:>3} "
                  f"(풀양성 {pq['n_pool_pos']:>3}) 불완전성 {pq['incompleteness_confirmed']:.1%}")
    else:
        rep = run_audit(args.sample, args.resume)
        out = DATA_DIR / "spotcheck_audit_report.json"
        print(f"\n{'='*64}\n[audit] 풀밖음성 {rep['n_negatives_total']} 중 {rep['n_sampled']} 표본")
        print(f"  false-negative {rep['n_false_neg']} → FN율 {rep['fn_rate']:.3%} "
              f"(95%CI {rep['fn_rate_ci95'][0]:.3%}~{rep['fn_rate_ci95'][1]:.3%})")
        print(f"  추정 장기꼬리 누락 {rep['est_missed_in_long_tail']} (CI {rep['est_missed_ci95']})")
        print(f"  in-pool recall(근접문서): {rep['in_pool_recall']} ({rep['in_pool_hit']}/{rep['in_pool_pos']})")

    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[리포트] {out}")


if __name__ == "__main__":
    main()

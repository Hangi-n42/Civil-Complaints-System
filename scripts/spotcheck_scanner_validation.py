"""스폿체크 1단계: 빠른 스캐너 신뢰도 검증 (#288).

풀 불완전성을 전수 스캔(쿼리당 9,132건)으로 측정하기 전에, 단일 LLM 스캐너가
3채점관 median 라벨을 얼마나 재현하는지 먼저 검증한다. "빠르게 깎은 LLM 채점이
정확한가"라는 우려에 대한 답.

모드:
  --ceiling : (무료, LLM 호출 없음) 기존 체크포인트(fair_pool.json, fair_pool_qwen.json)의
              각 채점관 점수 vs 3채점관 median 일치도. 단일 채점관 스캐너의 '상한선'.
  --scan    : (원격 LLM) 빠른 스캐너(exaone3.5, score-only, num_predict 작음)를
              이미 채점된 풀의 층화표본 N쌍에 적용해 median과 비교 → 깎은 설정의 '실제' 성능.

핵심 판정 지표: rel>=1 재현율(recall) + binary Cohen κ.
  스캐너는 "유사 후보 거르개"이므로, 진짜 유사문서(median>=1)를 놓치지 않는 recall이 가장 중요.
  거짓 양성은 3단계에서 정식 3채점관이 재확인하므로 덜 치명적.

LLM 추론: Tailscale 너머 Windows GPU(exaone3.5:7.8b).

실행:
  python scripts/spotcheck_scanner_validation.py --ceiling
  python scripts/spotcheck_scanner_validation.py --scan --sample 400 [--resume]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import SYSTEM_PROMPT, _extract_score, load_corpus, load_queries
from scripts.validate_fair_pool_3model import cohen_linear
from scripts.judge_pool_qwen import agg_median, build_prompt

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
EXGEM_CKPT = DATA_DIR / "checkpoints" / "fair_pool.json"        # exaone+gemma
QWEN_CKPT = DATA_DIR / "checkpoints" / "fair_pool_qwen.json"    # qwen
SCAN_CKPT = DATA_DIR / "checkpoints" / "scanner_validation_scan.json"
OUT_REPORT = DATA_DIR / "scanner_validation_report.json"

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.71.35.78:11434").rstrip("/") + "/api/generate"
SCANNER_MODEL = "exaone3.5:7.8b"
SEED = 42

# 빠른 스캐너 프롬프트: 루브릭은 동일, reason 제거 → 점수만(짧은 생성).
FAST_SYSTEM = SYSTEM_PROMPT.replace(
    '{"score": <0|1|2>, "reason": "<판단 사유 1~2문장>"}',
    '{"score": <0|1|2>}',
)


def build_fast_prompt(query_text: str, chunk_text: str, max_chars: int = 600) -> str:
    q = query_text[:max_chars].replace("\n", " / ")
    c = chunk_text[:max_chars]
    return f"{FAST_SYSTEM}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


def call_scanner(prompt: str, retries: int = 4, timeout: int = 60) -> int | None:
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": SCANNER_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "10m",
                "options": {"temperature": 0.0, "num_predict": 24, "num_ctx": 2048},
            }).encode("utf-8")
            req = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8")).get("response", "")
            return _extract_score(raw)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt, 8))
            else:
                print(f"    [scanner] 최종 실패: {e}")
    return None


# ── 일치도 지표 ────────────────────────────────────────────────────────────
def binary_stats(pred: list[int], gold: list[int]) -> dict:
    """rel>=1 을 양성으로 본 binary 지표 + 3x3 혼동행렬."""
    tp = sum(1 for p, g in zip(pred, gold) if p >= 1 and g >= 1)
    fp = sum(1 for p, g in zip(pred, gold) if p >= 1 and g == 0)
    fn = sum(1 for p, g in zip(pred, gold) if p == 0 and g >= 1)
    tn = sum(1 for p, g in zip(pred, gold) if p == 0 and g == 0)
    n = len(pred)
    recall = tp / (tp + fn) if (tp + fn) else float("nan")     # 진짜 유사문서를 놓치지 않는 능력(핵심)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    acc = (tp + tn) / n if n else float("nan")
    # binary Cohen κ
    po = acc
    p_pos_pred = (tp + fp) / n
    p_pos_gold = (tp + fn) / n
    pe = p_pos_pred * p_pos_gold + (1 - p_pos_pred) * (1 - p_pos_gold)
    bkappa = (po - pe) / (1 - pe) if pe != 1 else float("nan")
    confusion = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]  # rows=pred, cols=gold
    for p, g in zip(pred, gold):
        confusion[p][g] += 1
    return {
        "n": n,
        "rel>=1_recall": round(recall, 4),
        "rel>=1_precision": round(precision, 4),
        "binary_accuracy": round(acc, 4),
        "binary_cohen_kappa": round(bkappa, 4),
        "confusion_pred_x_gold": confusion,
        "tp_fp_fn_tn": [tp, fp, fn, tn],
    }


def judge_vs_median(name: str, judge: list[int], median: list[int]) -> dict:
    return {
        "judge": name,
        "graded_cohen_kappa": round(cohen_linear(judge, median), 4),
        "exact_agreement": round(sum(1 for a, b in zip(judge, median) if a == b) / len(judge), 4),
        **binary_stats(judge, median),
    }


# ── 1a: ceiling (무료) ─────────────────────────────────────────────────────
def run_ceiling() -> dict:
    exgem = json.loads(EXGEM_CKPT.read_text(encoding="utf-8"))
    qwen = json.loads(QWEN_CKPT.read_text(encoding="utf-8"))

    keys, ex, gm, qw, med = [], [], [], [], []
    for k in exgem:
        e = exgem[k].get("exaone3.5:7.8b")
        g = exgem[k].get("gemma3:12b")
        q = qwen.get(k)
        if None in (e, g, q):
            continue
        keys.append(k)
        ex.append(e); gm.append(g); qw.append(q)
        med.append(agg_median([e, g, q]))

    rep = {
        "mode": "ceiling (기존 체크포인트, LLM 호출 없음)",
        "n_pairs": len(keys),
        "median_dist": dict(sorted(Counter(med).items())),
        "note": "각 full-config 채점관이 3채점관 median을 얼마나 재현하는가 = 단일 스캐너 상한선",
        "judges": [
            judge_vs_median("exaone3.5:7.8b", ex, med),
            judge_vs_median("gemma3:12b", gm, med),
            judge_vs_median("qwen2.5:14b", qw, med),
        ],
    }
    return rep


# ── 1b: scan (원격 LLM, 깎은 설정 실제 성능) ───────────────────────────────
def stratified_sample(exgem: dict, qwen: dict, n: int) -> list[str]:
    """median 라벨로 층화표본 추출 (희소한 rel=1,2 충분 확보)."""
    by_label: dict[int, list[str]] = {0: [], 1: [], 2: []}
    for k in exgem:
        e = exgem[k].get("exaone3.5:7.8b"); g = exgem[k].get("gemma3:12b"); q = qwen.get(k)
        if None in (e, g, q):
            continue
        by_label[agg_median([e, g, q])].append(k)
    rng = random.Random(SEED)
    per = max(1, n // 3)
    out = []
    for lab in (0, 1, 2):
        pool = by_label[lab]
        rng.shuffle(pool)
        out += pool[:min(per, len(pool))]
    return out


def run_scan(sample_n: int, resume: bool) -> dict:
    exgem = json.loads(EXGEM_CKPT.read_text(encoding="utf-8"))
    qwen = json.loads(QWEN_CKPT.read_text(encoding="utf-8"))
    queries = load_queries()
    corpus = load_corpus()

    sample_keys = stratified_sample(exgem, qwen, sample_n)
    done = json.loads(SCAN_CKPT.read_text(encoding="utf-8")) if (resume and SCAN_CKPT.exists()) else {}
    todo = [k for k in sample_keys if k not in done]
    print(f"빠른 스캐너 검증 | {SCANNER_MODEL} @ {OLLAMA_URL}")
    print(f"표본 {len(sample_keys)}쌍(층화) | 완료 {len(done)} | 이번 {len(todo)}\n")

    started = time.perf_counter()
    for i, k in enumerate(todo, 1):
        qid, docid = k.split("::", 1)
        qt, ct = queries.get(qid, ""), corpus.get(docid, "")
        done[k] = None if (not qt or not ct) else call_scanner(build_fast_prompt(qt, ct))
        if i % 10 == 0 or i == len(todo):
            SCAN_CKPT.parent.mkdir(parents=True, exist_ok=True)
            SCAN_CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
            rate = i / (time.perf_counter() - started)
            eta = (len(todo) - i) / rate if rate else 0
            print(f"  [{i}/{len(todo)}] {k}={done[k]} | {rate:.2f}쌍/s ETA {eta:.0f}s")
    SCAN_CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")

    pred, med = [], []
    n_none = 0
    for k in sample_keys:
        if done.get(k) is None:
            n_none += 1
            continue
        e = exgem[k]["exaone3.5:7.8b"]; g = exgem[k]["gemma3:12b"]; q = qwen[k]
        pred.append(done[k]); med.append(agg_median([e, g, q]))

    rep = {
        "mode": f"scan (빠른 스캐너 num_predict=24, score-only, {SCANNER_MODEL})",
        "n_sample": len(sample_keys),
        "n_scored": len(pred),
        "n_abstain_or_fail": n_none,
        "median_dist": dict(sorted(Counter(med).items())),
        "fast_exaone_vs_median": judge_vs_median(f"{SCANNER_MODEL} (fast)", pred, med),
    }
    return rep


def verdict(stats: dict) -> str:
    r = stats.get("rel>=1_recall", 0) or 0
    bk = stats.get("binary_cohen_kappa", 0) or 0
    if r >= 0.85 and bk >= 0.5:
        return f"통과(양호): recall {r:.2f}, binary κ {bk:.2f} → 전수 스캐너로 신뢰 가능"
    if r >= 0.75 and bk >= 0.4:
        return f"조건부 통과: recall {r:.2f}, binary κ {bk:.2f} → 전수 가능하나 3단계 재확인 필수"
    return f"미흡: recall {r:.2f}, binary κ {bk:.2f} → 단일 스캐너 전수는 누락 위험, 방법 재고"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceiling", action="store_true", help="무료: 기존 채점관 vs median 상한선")
    ap.add_argument("--scan", action="store_true", help="원격 LLM: 빠른 스캐너 실제 성능")
    ap.add_argument("--sample", type=int, default=400, help="--scan 층화표본 크기")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    if not (args.ceiling or args.scan):
        ap.error("--ceiling 또는 --scan 중 하나 이상 지정")

    report = {}
    if args.ceiling:
        c = run_ceiling()
        report["ceiling"] = c
        print("=" * 72)
        print(f"[1a] 상한선: 각 채점관 vs 3채점관 median ({c['n_pairs']}쌍, median분포 {c['median_dist']})")
        print("=" * 72)
        print(f"{'채점관':<18}{'graded κ':>10}{'rel≥1 recall':>14}{'rel≥1 prec':>12}{'binary κ':>10}")
        for j in c["judges"]:
            print(f"{j['judge']:<18}{j['graded_cohen_kappa']:>10.3f}"
                  f"{j['rel>=1_recall']:>14.3f}{j['rel>=1_precision']:>12.3f}{j['binary_cohen_kappa']:>10.3f}")
        # exaone(스캐너 후보)에 대한 판정
        ex = next(j for j in c["judges"] if j["judge"].startswith("exaone"))
        print(f"\n  exaone(full-config) 상한 판정: {verdict(ex)}")

    if args.scan:
        s = run_scan(args.sample, args.resume)
        report["scan"] = s
        st = s["fast_exaone_vs_median"]
        print("\n" + "=" * 72)
        print(f"[1b] 빠른 스캐너 실제: {SCANNER_MODEL} num_predict=24 vs median "
              f"({s['n_scored']}쌍 채점, 기권/실패 {s['n_abstain_or_fail']})")
        print("=" * 72)
        print(f"  graded κ {st['graded_cohen_kappa']:.3f} | rel≥1 recall {st['rel>=1_recall']:.3f} "
              f"| prec {st['rel>=1_precision']:.3f} | binary κ {st['binary_cohen_kappa']:.3f}")
        print(f"  혼동행렬(행=스캐너,열=median): {st['confusion_pred_x_gold']}")
        print(f"\n  판정: {verdict(st)}")

    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[리포트] {OUT_REPORT}")


if __name__ == "__main__":
    main()

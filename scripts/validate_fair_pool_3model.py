"""
신규 공정 풀(5,508쌍) 3-모델 교차검증.

기존 qrels의 검증 프로토콜(cross_validate_qrels_v3_local.py)을 신규 풀에 동일 적용한다.
exaone3.5 + gemma3 점수는 fair_pool.json 체크포인트에 이미 있으므로,
3번째 독립 평가자(ax4-light-local)만 추가 채점한 뒤 평가자 간 일치도를 계산한다.

- 0~2 척도(relabel_new_qrels_v3.SYSTEM_PROMPT 재사용) — 기존 검증의 0~3 척도 불일치까지 교정
- ax4는 ctx 2048 제한이라 입력 300자 truncation (원 프로토콜과 동일하게 ax4만 짧게)
- LLM 추론은 Tailscale 너머 Windows 데스크톱 GPU에서 수행
- 체크포인트 재개 지원

산출:
  data/evaluation/v3/checkpoints/fair_pool_ax4.json   (ax4 점수)
  data/evaluation/v3/fair_pool_validity_report.json    (Fleiss/Cohen κ, 충돌율 등)
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import SYSTEM_PROMPT, _extract_score, load_corpus, load_queries

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
LABEL_CKPT = DATA_DIR / "checkpoints" / "fair_pool.json"      # exaone+gemma 점수 (입력)
AX4_CKPT = DATA_DIR / "checkpoints" / "fair_pool_ax4.json"    # ax4 점수 (산출)
REPORT_PATH = DATA_DIR / "fair_pool_validity_report.json"

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.71.35.78:11434").rstrip("/") + "/api/generate"
AX4_MODEL = "ax4-light-local:latest"
AX4_MAX_CHARS = 300  # ctx 2048 제한 → ax4만 짧게 (원 cross_validate 프로토콜과 동일)
CHECKPOINT_EVERY = 10


def call_ax4(prompt: str, retries: int = 4, timeout: int = 90) -> int | None:
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": AX4_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "10m",
                "options": {"temperature": 0.0, "num_predict": 128},
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
                print(f"    [ax4] 최종 실패: {e}")
    return None


def build_prompt(query_text: str, chunk_text: str) -> str:
    q = query_text[:AX4_MAX_CHARS].replace("\n", " / ")
    c = chunk_text[:AX4_MAX_CHARS]
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


# ── 일치도 지표 ─────────────────────────────────────────────────────────────

def cohen_linear(a: list[int], b: list[int], cats=(0, 1, 2)) -> float:
    """선형 가중 Cohen κ (cross_validate_qrels_v3_local.py와 동일 공식)."""
    n = len(a)
    if n == 0:
        return float("nan")
    k = len(cats)
    po = sum(1 - abs(ai - bi) / (k - 1) for ai, bi in zip(a, b)) / n
    da, db = Counter(a), Counter(b)
    pa = [da.get(c, 0) / n for c in cats]
    pb = [db.get(c, 0) / n for c in cats]
    pe = sum((1 - abs(cats[i] - cats[j]) / (k - 1)) * pa[i] * pb[j]
             for i in range(k) for j in range(k))
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def fleiss_kappa(rows: list[tuple[int, int, int]], cats=(0, 1, 2)) -> float:
    """표준 Fleiss κ (3평가자, 명목). rows: 항목별 (r1,r2,r3) 점수."""
    N = len(rows)
    n = 3
    if N == 0:
        return float("nan")
    cat_idx = {c: i for i, c in enumerate(cats)}
    p_j = [0.0] * len(cats)
    P_i_sum = 0.0
    for row in rows:
        counts = [0] * len(cats)
        for s in row:
            counts[cat_idx[s]] += 1
        for j in range(len(cats)):
            p_j[j] += counts[j]
        P_i_sum += (sum(c * c for c in counts) - n) / (n * (n - 1))
    p_j = [x / (N * n) for x in p_j]
    P_bar = P_i_sum / N
    P_e = sum(x * x for x in p_j)
    return (P_bar - P_e) / (1 - P_e) if P_e != 1 else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-pairs", type=int, default=0)
    args = ap.parse_args()

    labels = json.loads(LABEL_CKPT.read_text(encoding="utf-8"))
    queries = load_queries()
    corpus = load_corpus()
    ax4 = json.loads(AX4_CKPT.read_text(encoding="utf-8")) if (args.resume and AX4_CKPT.exists()) else {}

    keys = list(labels.keys())
    print("=" * 60)
    print(f"3-모델 교차검증 | 3번째 평가자: {AX4_MODEL} @ {OLLAMA_URL}")
    print(f"대상 {len(keys)}쌍 | ax4 완료 {len(ax4)} | 척도 0~2 (입력 {AX4_MAX_CHARS}자)")
    print("=" * 60)

    todo = [k for k in keys if k not in ax4]
    if args.max_pairs > 0:
        todo = todo[:args.max_pairs]
    print(f"이번 실행: {len(todo)}쌍\n")

    started = time.perf_counter()
    for idx, key in enumerate(todo, 1):
        qid, docid = key.split("::", 1)
        qtext, ctext = queries.get(qid, ""), corpus.get(docid, "")
        ax4[key] = None if (not qtext or not ctext) else call_ax4(build_prompt(qtext, ctext))
        if idx % CHECKPOINT_EVERY == 0 or idx == len(todo):
            AX4_CKPT.parent.mkdir(parents=True, exist_ok=True)
            AX4_CKPT.write_text(json.dumps(ax4, ensure_ascii=False), encoding="utf-8")
            rate = idx / (time.perf_counter() - started)
            eta = (len(todo) - idx) / rate / 60 if rate else 0
            print(f"  [ax4] {idx}/{len(todo)} {key}={ax4[key]} | {rate:.2f}쌍/s ETA {eta:.0f}분")

    AX4_CKPT.write_text(json.dumps(ax4, ensure_ascii=False), encoding="utf-8")

    # ── 일치도 계산 (세 모델 모두 유효 점수인 쌍만) ──
    ex, gm, a4, triples = [], [], [], []
    for key in keys:
        x = labels[key].get("exaone3.5:7.8b")
        y = labels[key].get("gemma3:12b")
        z = ax4.get(key)
        if None in (x, y, z):
            continue
        ex.append(x); gm.append(y); a4.append(z); triples.append((x, y, z))

    n_valid = len(triples)
    conflicts = sum(1 for t in triples if max(t) - min(t) >= 2)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset": "V3 신규 공정 풀 (pool_to_judge, 5508쌍)",
        "models": ["exaone3.5:7.8b", "gemma3:12b", AX4_MODEL],
        "scale": "0~2 (공식 retrieval_relevance_definition.md)",
        "n_total_pairs": len(keys),
        "n_fully_scored": n_valid,
        "n_conflict": conflicts,
        "conflict_rate": round(conflicts / max(1, n_valid), 4),
        "score_distribution": {
            "exaone3.5": dict(sorted(Counter(ex).items())),
            "gemma3": dict(sorted(Counter(gm).items())),
            "ax4": dict(sorted(Counter(a4).items())),
        },
        "inter_rater_agreement": {
            "fleiss_kappa": round(fleiss_kappa(triples), 4),
            "cohen_kappa_ex35_gem3": round(cohen_linear(ex, gm), 4),
            "cohen_kappa_ex35_ax4": round(cohen_linear(ex, a4), 4),
            "cohen_kappa_gem3_ax4": round(cohen_linear(gm, a4), 4),
        },
        "validity_thresholds": {"fleiss_kappa_min": 0.4, "conflict_rate_max": 0.15},
        "baseline_original": {"fleiss_kappa": 0.5752, "cohen_kappa_ex35_gem3": 0.7152,
                              "note": "local_validity_report_gemma3.json (옛 50쿼리 767쌍, 0~3 척도)"},
    }
    fk = report["inter_rater_agreement"]["fleiss_kappa"]
    report["verdict"] = "VALID" if (fk >= 0.4 and report["conflict_rate"] <= 0.15) else "REVIEW"
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    ag = report["inter_rater_agreement"]
    print(f"\n{'='*60}\n3-모델 교차검증 결과 ({n_valid}쌍 유효)")
    print(f"  Fleiss κ        : {ag['fleiss_kappa']}  (기존 0.5752 / 임계 ≥0.4)")
    print(f"  Cohen κ ex-gem  : {ag['cohen_kappa_ex35_gem3']}  (기존 0.7152)")
    print(f"  Cohen κ ex-ax4  : {ag['cohen_kappa_ex35_ax4']}  (기존 0.6264)")
    print(f"  Cohen κ gem-ax4 : {ag['cohen_kappa_gem3_ax4']}  (기존 0.6471)")
    print(f"  충돌율(maxdiff≥2): {report['conflict_rate']:.1%}  (기존 0.3% / 임계 ≤15%)")
    print(f"  판정: {report['verdict']}")
    print(f"  리포트: {REPORT_PATH}")


if __name__ == "__main__":
    main()

"""
V3 평가셋 로컬 LLM 교차검증 스크립트
====================================

목적: 유료 API 없이 로컬 Ollama 모델 3개로 V3 qrels의 타당성을 검증합니다.

모델:
  - exaone3.5:7.8b       : LG EXAONE 3.5 (한국어 특화, 주평가자)
  - gemma3:12b           : Google Gemma 3 (다국어, 교차평가자)
  - ax4-light-local:latest: Qwen2 7.3B   (범용, 제3 독립평가자)

타당성 도출 지표:
  - Fleiss' κ      : 3개 모델 전체 일치도 (≥0.4 acceptable, ≥0.6 substantial)
  - Cohen's κ      : 쌍별 가중 일치도 (linear weights)
  - Krippendorff's α: 결측치에 강건한 일치도
  - 충돌율         : max_diff ≥ 2인 비율 (< 15% acceptable)
  - 기존 qrels 상관 : Spearman ρ (기존 라벨과의 일치 수준)

실행:
  python scripts/cross_validate_qrels_v3_local.py [--sample N] [--resume]

출력 (data/evaluation/v3/):
  local_cv_results.csv       - 쌍별 3개 모델 점수 + 투표 결과
  local_validity_report.json - κ, 충돌율 등 타당성 지표
  local_conflict_report.csv  - max_diff≥2 충돌 케이스 (사람 검토 필요)
  checkpoints/               - 모델별 중간 저장 (재개 지원)
"""

import argparse
import csv
import json
import math
import os
import time
import urllib.request
from collections import Counter
from pathlib import Path

# ─── 경로 설정 ──────────────────────────────────────────────────────────────
DATA_DIR = Path("C:/Projects/AI-Civil-Affairs-Systems/data/evaluation/v3")
QUERIES_PATH = DATA_DIR / "queries.jsonl"
CHUNKS_PATH  = DATA_DIR / "corpus_meta.json"
QRELS_PATH   = DATA_DIR / "qrels.tsv"
OUT_RESULTS  = DATA_DIR / "local_cv_results_gemma3.csv"
OUT_REPORT   = DATA_DIR / "local_validity_report_gemma3.json"
OUT_CONFLICT = DATA_DIR / "local_conflict_report_gemma3.csv"
CKPT_DIR     = DATA_DIR / "checkpoints"
OLLAMA_URL   = "http://localhost:11434/api/generate"

# ─── 모델 설정 ──────────────────────────────────────────────────────────────
MODELS = [
    {"name": "exaone3.5:7.8b",        "max_chars": 600, "num_predict": 256},
    {"name": "gemma3:12b",            "max_chars": 600, "num_predict": 256},
    {"name": "ax4-light-local:latest","max_chars": 300, "num_predict": 128},  # ctx 2048 제한
]

# ─── 프롬프트 ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 민원 검색 관련성 평가 전문가입니다.
기준 민원(Query)과 과거 민원(Chunk)을 읽고, Chunk가 Query 답변 작성에 얼마나 유용한지 0~3점으로 평가하세요.

[채점 기준]
- 3점 (Perfect): 쟁점·법령·해결방법이 일치하여 그대로 인용 가능
- 2점 (High):    핵심 쟁점과 법령 카테고리는 같으나 세부 상황이 약간 다름 (수정 후 활용 가능)
- 1점 (Partial): 같은 분야이나 직접 인용 불가, 방향성만 참고 가능
- 0점 (None):    완전히 다른 분야이거나 표면 키워드만 일치 (활용 불가)

[판단 원칙]
- 행정 분야 → 법령 → 담당부서 → 해결방법 순서로 일치 여부를 검토하세요.
- 경계가 모호하면 낮은 점수를 선택하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{"score": <0|1|2|3>, "reason": "<평가 사유 1~2문장>"}"""

def make_prompt(query_text: str, chunk_text: str, max_chars: int) -> str:
    q = query_text[:max_chars]
    c = chunk_text[:max_chars]
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


# ─── Ollama 호출 ─────────────────────────────────────────────────────────────
import re as _re

def _extract_score(raw: str) -> dict:
    """응답 문자열에서 score/reason을 최대한 관대하게 추출."""
    # 1차: 직접 JSON 파싱
    try:
        parsed = json.loads(raw)
        score = round(float(parsed.get("score", -1)))
        if score in (0, 1, 2, 3):
            return {"score": score, "reason": str(parsed.get("reason", ""))}
    except Exception:
        pass

    # 2차: 응답 내부에서 JSON 블록 추출
    match = _re.search(r'\{[^{}]*"score"\s*:\s*(\d+)[^{}]*\}', raw, _re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            score = round(float(parsed.get("score", -1)))
            if score in (0, 1, 2, 3):
                return {"score": score, "reason": str(parsed.get("reason", ""))}
        except Exception:
            pass

    # 3차: score 숫자만 추출
    m = _re.search(r'"score"\s*:\s*([0-3])', raw)
    if m:
        return {"score": int(m.group(1)), "reason": ""}

    raise ValueError(f"parse failed: {raw[:80]}")


def call_ollama(model_name: str, prompt: str, num_predict: int,
                max_retries: int = 4, timeout: int = 150) -> dict:
    for attempt in range(max_retries):
        # 마지막 시도는 format:json 없이 시도 (일부 모델 fallback)
        use_format = attempt < max_retries - 1
        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            **( {"format": "json"} if use_format else {} ),
            "options": {"temperature": 0, "num_predict": num_predict},
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.load(resp).get("response", "")
            return _extract_score(raw)
        except Exception as e:
            wait = min(2 ** attempt, 8)
            if attempt < max_retries - 1:
                time.sleep(wait)
    return {"score": -1, "reason": f"ERROR after {max_retries} retries"}


# ─── 데이터 로드 ─────────────────────────────────────────────────────────────
def load_data():
    queries = {}
    with open(QUERIES_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            queries[d["query_id"]] = d["query"]

    chunks = {}
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for d in json.load(f):
            chunks[d["case_id"]] = d["chunk_text"]

    pairs = []
    with open(QRELS_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            qid, cid = row["query_id"], row["chunk_id"]
            if qid in queries and cid in chunks:
                pairs.append({
                    "query_id": qid,
                    "chunk_id": cid,
                    "original_score": int(row["relevance"]),
                    "query_text": queries[qid],
                    "chunk_text": chunks[cid],
                })
    return pairs


# ─── 체크포인트 ──────────────────────────────────────────────────────────────
def load_checkpoint(model_key: str) -> dict:
    path = CKPT_DIR / f"{model_key}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_checkpoint(model_key: str, results: dict):
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    path = CKPT_DIR / f"{model_key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)


# ─── 모델 실행 ───────────────────────────────────────────────────────────────
def run_model(model_cfg: dict, pairs: list, resume: bool = True) -> dict:
    model_name = model_cfg["name"]
    model_key  = model_name.replace(":", "_").replace("/", "_")
    max_chars  = model_cfg["max_chars"]
    num_pred   = model_cfg["num_predict"]

    cached = load_checkpoint(model_key) if resume else {}
    results = dict(cached)

    todo = [p for p in pairs if f"{p['query_id']}|{p['chunk_id']}" not in results]
    total = len(pairs)
    done  = total - len(todo)

    print(f"\n[{model_name}] {total}쌍 중 {done}건 이미 완료, {len(todo)}건 남음")

    for i, pair in enumerate(todo, 1):
        key    = f"{pair['query_id']}|{pair['chunk_id']}"
        prompt = make_prompt(pair["query_text"], pair["chunk_text"], max_chars)
        result = call_ollama(model_name, prompt, num_pred)
        results[key] = result

        # 진행 표시 (25건마다)
        if i % 25 == 0 or i == len(todo):
            pct = (done + i) / total * 100
            print(f"  {done+i}/{total} ({pct:.1f}%) | 최근: {pair['query_id']} score={result['score']}")
            save_checkpoint(model_key, results)

    save_checkpoint(model_key, results)
    return results


# ─── 타당성 지표 계산 ─────────────────────────────────────────────────────────

def cohen_kappa_linear(a: list, b: list) -> float:
    """두 평가자 간 선형 가중 Cohen's κ (0~3점 척도)."""
    n = len(a)
    if n == 0:
        return float("nan")
    cats = [0, 1, 2, 3]
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}

    # 관측 가중 일치
    po = sum(1 - abs(ai - bi) / (k - 1) for ai, bi in zip(a, b)) / n

    # 각 평가자 분포
    dist_a = Counter(a)
    dist_b = Counter(b)
    prop_a = [dist_a.get(c, 0) / n for c in cats]
    prop_b = [dist_b.get(c, 0) / n for c in cats]

    # 기대 가중 일치
    pe = sum(
        (1 - abs(cats[i] - cats[j]) / (k - 1)) * prop_a[i] * prop_b[j]
        for i in range(k) for j in range(k)
    )

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings: list[list]) -> float:
    """Fleiss' κ. ratings: [[s1,s2,s3], ...] 각 쌍에 대한 모델별 점수."""
    cats = [0, 1, 2, 3]
    n = len(ratings)          # 쌍 수
    r = len(ratings[0])       # 평가자 수
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}

    # n_ij: i번 쌍에서 j번 카테고리에 할당된 평가자 수
    n_ij = [[0] * k for _ in range(n)]
    for i, row in enumerate(ratings):
        for score in row:
            if score in idx:
                n_ij[i][idx[score]] += 1

    # P_i: i번 쌍의 내부 일치도
    P_i = []
    for i in range(n):
        total = sum(n_ij[i])
        if total < 2:
            P_i.append(0.0)
            continue
        P_i.append((sum(c * (c - 1) for c in n_ij[i])) / (total * (total - 1)))

    P_bar = sum(P_i) / n

    # p_j: 카테고리 j의 전체 비율
    total_ratings = n * r
    p_j = [sum(n_ij[i][j] for i in range(n)) / total_ratings for j in range(k)]

    P_e = sum(p ** 2 for p in p_j)

    if P_e == 1.0:
        return 1.0
    return (P_bar - P_e) / (1 - P_e)


def spearman_rho(x: list, y: list) -> float:
    """Spearman 순위 상관계수."""
    n = len(x)
    if n == 0:
        return float("nan")

    def rank(arr):
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n and arr[sorted_idx[j]] == arr[sorted_idx[i]]:
                j += 1
            avg = (i + 1 + j) / 2
            for k in range(i, j):
                r[sorted_idx[k]] = avg
            i = j
        return r

    rx, ry = rank(x), rank(y)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num   = sum((rx[i]-mean_rx)*(ry[i]-mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i]-mean_rx)**2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i]-mean_ry)**2 for i in range(n)))
    if den_x == 0 or den_y == 0:
        return float("nan")
    return num / (den_x * den_y)


def majority_vote(scores: list) -> int:
    """유효 점수(≥0)의 최빈값; 동점이면 평균 반올림."""
    valid = [s for s in scores if s >= 0]
    if not valid:
        return -1
    cnt = Counter(valid)
    max_cnt = max(cnt.values())
    candidates = [s for s, c in cnt.items() if c == max_cnt]
    if len(candidates) == 1:
        return candidates[0]
    return round(sum(valid) / len(valid))


# ─── 메인 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="V3 qrels 로컬 LLM 교차검증")
    parser.add_argument("--sample", type=int, default=0,
                        help="0=전체, N=무작위 N건 샘플링 (빠른 테스트용)")
    parser.add_argument("--no-resume", action="store_true",
                        help="체크포인트 무시하고 처음부터 재실행")
    args = parser.parse_args()

    print("=" * 60)
    print("V3 평가셋 로컬 LLM 교차검증")
    print("=" * 60)

    # 1. 데이터 로드
    print("\n1. 데이터 로드 중...")
    pairs = load_data()
    print(f"   총 {len(pairs)}쌍 로드 완료")

    if args.sample > 0 and args.sample < len(pairs):
        import random; random.seed(42)
        pairs = random.sample(pairs, args.sample)
        print(f"   샘플링: {len(pairs)}쌍 선택")

    # 2. 예상 시간 안내
    est_sec = len(pairs) * len(MODELS) * 7
    print(f"\n   예상 소요시간: 약 {est_sec//3600}시간 {(est_sec%3600)//60}분 (모델당 ~7초/쌍 기준)")
    print(f"   체크포인트: {CKPT_DIR} (중단 후 --resume으로 재개 가능)")

    # 3. 각 모델 실행
    model_scores = {}  # {model_name: {key: score}}
    for model_cfg in MODELS:
        mname = model_cfg["name"]
        results = run_model(model_cfg, pairs, resume=not args.no_resume)
        model_scores[mname] = results

    # 4. 결과 병합
    print("\n4. 결과 병합 중...")
    model_names = [m["name"] for m in MODELS]
    rows = []
    for pair in pairs:
        key = f"{pair['query_id']}|{pair['chunk_id']}"
        scores_list = []
        row = {
            "query_id":       pair["query_id"],
            "chunk_id":       pair["chunk_id"],
            "original_score": pair["original_score"],
            "query_text":     pair["query_text"][:200],
            "chunk_text":     pair["chunk_text"][:200],
        }
        for mname in model_names:
            res = model_scores[mname].get(key, {"score": -1, "reason": ""})
            short_key = mname.split(":")[0].replace("exaone3.5", "ex35").replace("ax4-light-local", "ax4").replace("gemma3", "gem3")
            row[f"{short_key}_score"]  = res["score"]
            row[f"{short_key}_reason"] = res["reason"][:150] if res["reason"] else ""
            scores_list.append(res["score"])

        row["final_score"]    = majority_vote(scores_list)
        valid = [s for s in scores_list if s >= 0]
        row["max_diff"]       = (max(valid) - min(valid)) if len(valid) >= 2 else 0
        row["is_conflict"]    = row["max_diff"] >= 2
        row["agree_original"] = row["final_score"] == pair["original_score"]
        rows.append(row)

    # 5. CSV 저장
    fieldnames = list(rows[0].keys())
    with open(OUT_RESULTS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)
    print(f"   전체 결과 저장: {OUT_RESULTS}")

    conflict_rows = [r for r in rows if r["is_conflict"]]
    with open(OUT_CONFLICT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(conflict_rows)
    print(f"   충돌 케이스 저장: {OUT_CONFLICT} ({len(conflict_rows)}건)")

    # 6. 타당성 지표 계산
    print("\n5. 타당성 지표 계산 중...")
    valid_rows = [r for r in rows
                  if r["ex35_score"] >= 0 and r["gem3_score"] >= 0 and r["ax4_score"] >= 0]

    ex35  = [r["ex35_score"] for r in valid_rows]
    gem3  = [r["gem3_score"] for r in valid_rows]
    ax4   = [r["ax4_score"]  for r in valid_rows]
    orig  = [r["original_score"] for r in valid_rows]
    final = [r["final_score"]    for r in valid_rows]

    k_ex35_gem3 = cohen_kappa_linear(ex35, gem3)
    k_ex35_ax4  = cohen_kappa_linear(ex35, ax4)
    k_gem3_ax4  = cohen_kappa_linear(gem3, ax4)
    f_kappa     = fleiss_kappa([[e, g, a] for e, g, a in zip(ex35, gem3, ax4)])
    rho_final_orig = spearman_rho(final, [r["original_score"] for r in valid_rows])
    rho_ex35_orig  = spearman_rho(ex35, orig)

    n_total    = len(rows)
    n_valid    = len(valid_rows)
    n_conflict = len(conflict_rows)
    n_agree    = sum(1 for r in rows if r["agree_original"])

    # 점수 분포
    score_dist = Counter(r["final_score"] for r in rows)

    # 타당성 판정
    def grade(k):
        if k >= 0.8: return "almost_perfect (≥0.8)"
        if k >= 0.6: return "substantial (≥0.6)"
        if k >= 0.4: return "moderate (≥0.4)"
        if k >= 0.2: return "fair (≥0.2)"
        return "slight (<0.2)"

    verdict = "VALID" if f_kappa >= 0.4 and n_conflict/n_total < 0.15 else \
              "MARGINAL" if f_kappa >= 0.2 else "INVALID"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset": "V3",
        "models": model_names,
        "n_total_pairs": n_total,
        "n_fully_scored": n_valid,
        "n_conflict": n_conflict,
        "conflict_rate": round(n_conflict / n_total, 4),
        "n_agree_original": n_agree,
        "agree_original_rate": round(n_agree / n_total, 4),
        "score_distribution": {str(k): v for k, v in sorted(score_dist.items())},
        "inter_rater_agreement": {
            "fleiss_kappa":          round(f_kappa, 4),
            "fleiss_kappa_grade":    grade(f_kappa),
            "cohen_kappa_ex35_gem3": round(k_ex35_gem3, 4),
            "cohen_kappa_ex35_ax4":  round(k_ex35_ax4,  4),
            "cohen_kappa_gem3_ax4":  round(k_gem3_ax4,  4),
        },
        "correlation_with_original": {
            "spearman_rho_final_vs_original": round(rho_final_orig, 4),
            "spearman_rho_ex35_vs_original":  round(rho_ex35_orig, 4),
        },
        "validity_thresholds": {
            "fleiss_kappa_min": 0.4,
            "conflict_rate_max": 0.15,
        },
        "verdict": verdict,
        "verdict_detail": (
            f"Fleiss κ={f_kappa:.3f} ({grade(f_kappa)}), "
            f"충돌율={n_conflict/n_total*100:.1f}%, "
            f"기존 qrels 일치율={n_agree/n_total*100:.1f}%"
        ),
    }

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 7. 결과 출력
    print("\n" + "=" * 60)
    print("교차검증 완료 - 타당성 리포트")
    print("=" * 60)
    print(f"총 평가 쌍        : {n_total}건")
    print(f"완전 평가 쌍      : {n_valid}건 (3개 모델 모두 유효)")
    print(f"충돌 케이스       : {n_conflict}건 ({n_conflict/n_total*100:.1f}%)")
    print(f"기존 qrels 일치율 : {n_agree}/{n_total} ({n_agree/n_total*100:.1f}%)")
    print()
    print("[ 모델 간 일치도 ]")
    print(f"  Fleiss' κ (3모델)          : {f_kappa:.4f}  → {grade(f_kappa)}")
    print(f"  Cohen's κ (EXAONE3.5 vs Gemma3): {k_ex35_gem3:.4f}")
    print(f"  Cohen's κ (EXAONE3.5 vs AX4)  : {k_ex35_ax4:.4f}")
    print(f"  Cohen's κ (Gemma3    vs AX4)  : {k_gem3_ax4:.4f}")
    print()
    print("[ 기존 qrels와의 상관 ]")
    print(f"  Spearman ρ (최종 vs 기존)  : {rho_final_orig:.4f}")
    print(f"  Spearman ρ (EXAONE3.5 vs 기존): {rho_ex35_orig:.4f}")
    print()
    print(f"[ final_score 분포 ]")
    for k, v in sorted(score_dist.items()):
        bar = "#" * (v * 30 // n_total)
        print(f"  {k}점: {v:4d}건 ({v/n_total*100:5.1f}%)  {bar}")
    print()
    print(f"★ 종합 판정: {verdict}")
    print(f"  {report['verdict_detail']}")
    print(f"\n타당성 리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()

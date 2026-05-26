"""
신규 V3 qrels (Q-0051+) inter-rater agreement 검증

기존 v3는 local_validity_report_gemma3.json 에서 Fleiss κ=0.575(moderate) 확인.
신규 63개 쿼리(2,022쌍)에 대해 3개 LLM을 재채점하여 동일 지표를 계산.

샘플링: 전체 2,022쌍 중 200쌍 무작위 추출 (95% CI 기준 충분한 표본)
모델: exaone3.5:7.8b, gemma3:12b, ax4-light-local:latest (기존 v3와 동일)
출력: data/evaluation/v3/new_queries_validity_report.json
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import ollama

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
CHECKPOINT_PATH = DATA_DIR / "new_queries_validity_checkpoint.json"

SEED = 42
SAMPLE_N = 200
LABEL_MODELS = ["exaone3.5:7.8b", "gemma3:12b", "ax4-light-local:latest"]

NEW_QID_PREFIX_NUM = 51  # Q-0051 이상이 신규


# ──────────────────────────────────────────────
# 데이터 로딩
# ──────────────────────────────────────────────

def load_new_pairs() -> list[tuple[str, str]]:
    """신규 쿼리(Q-0051+)의 (qid, case_id) 쌍 로드."""
    pairs = []
    with (DATA_DIR / "qrels.tsv").open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split("\t")
            if len(parts) != 4:
                continue
            qid, _, case_id, _ = parts
            num = int(qid.split("-")[1])
            if num >= NEW_QID_PREFIX_NUM:
                pairs.append((qid, case_id))
    return pairs


def load_query_text() -> dict[str, str]:
    qid_text = {}
    with (DATA_DIR / "queries.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                q = json.loads(line)
                qid_text[q["query_id"]] = q["query"]
    return qid_text


def load_corpus_lookup() -> dict[str, str]:
    with (DATA_DIR / "corpus_meta.json").open("r", encoding="utf-8") as f:
        corpus = json.load(f)
    lookup: dict[str, str] = {}
    for c in corpus:
        cid = c["case_id"]
        if cid not in lookup:
            lookup[cid] = c["chunk_text"]
    return lookup


# ──────────────────────────────────────────────
# LLM 라벨링
# ──────────────────────────────────────────────

_LABEL_SYSTEM = """\
너는 민원 검색 시스템의 관련성 평가 전문가야.
기준 민원(Query)과 검색된 민원 사례(Chunk)를 보고 아래 기준으로 점수를 매겨.

2점: 핵심 쟁점이 같고 적용 법령·해결책도 같아 답변에 그대로 인용 가능.
1점: 같은 카테고리·주제지만 세부 상황이 달라 부분 참고만 가능.
0점: 키워드만 겹칠 뿐 실제 쟁점·행정절차가 달라 답변 오류를 유발할 수 있음.

출력 형식: 첫 줄에 숫자(0, 1, 2)만, 둘째 줄에 한 문장 이유.
"""

_LABEL_USER_TMPL = """\
[기준 민원 Query]
{query}

[검색된 민원 Chunk]
{chunk}
"""


def _label_one(model: str, query: str, chunk: str, retries: int = 2) -> int:
    for attempt in range(retries + 1):
        try:
            resp = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": _LABEL_SYSTEM},
                    {"role": "user", "content": _LABEL_USER_TMPL.format(
                        query=query[:800], chunk=chunk[:800]
                    )},
                ],
                options={"temperature": 0.0, "num_predict": 60},
            )
            content = resp.message.content.strip()
            # 첫 줄 우선, 없으면 전체 응답에서 숫자 탐색
            first = content.splitlines()[0].strip() if content else ""
            m = re.search(r"[012]", first) or re.search(r"[012]", content)
            if m:
                return int(m.group())
        except Exception as e:
            if attempt == retries:
                print(f"    [경고] {model} 오류: {e}", flush=True)
    return -1


# ──────────────────────────────────────────────
# Fleiss κ 계산
# ──────────────────────────────────────────────

def fleiss_kappa(ratings: list[list[int]], n_categories: int = 3) -> float:
    """ratings: [[rater1_score, rater2_score, ...], ...]"""
    n_items = len(ratings)
    n_raters = len(ratings[0])
    categories = list(range(n_categories))

    # P_i: 각 항목의 관찰 일치 비율
    p_i_list = []
    for item_scores in ratings:
        cnt = Counter(item_scores)
        p_i = sum(cnt[c] * (cnt[c] - 1) for c in categories) / (n_raters * (n_raters - 1))
        p_i_list.append(p_i)
    p_bar = sum(p_i_list) / n_items

    # p_j: 각 카테고리의 전체 비율
    total = n_items * n_raters
    p_j = {c: sum(Counter(r)[c] for r in ratings) / total for c in categories}

    p_e = sum(p_j[c] ** 2 for c in categories)
    if p_e == 1.0:
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def kappa_grade(k: float) -> str:
    if k >= 0.8:
        return "almost perfect (>=0.8)"
    if k >= 0.6:
        return "substantial (>=0.6)"
    if k >= 0.4:
        return "moderate (>=0.4)"
    if k >= 0.2:
        return "fair (>=0.2)"
    return "slight (<0.2)"


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("신규 qrels inter-rater agreement 검증")
    print("=" * 60)

    # 데이터 로드
    all_pairs = load_new_pairs()
    qid_text = load_query_text()
    corpus_lookup = load_corpus_lookup()
    print(f"신규 쌍: {len(all_pairs)}건")

    # 샘플링
    rng = random.Random(SEED)
    sample = rng.sample(all_pairs, min(SAMPLE_N, len(all_pairs)))
    print(f"샘플: {len(sample)}건")

    # 체크포인트 로드 (이전 실행에서 중단된 경우 이어서 처리)
    model_scores: dict[str, list[int]] = {m: [] for m in LABEL_MODELS}
    valid_samples: list[tuple[str, str]] = []
    start_idx = 0

    if CHECKPOINT_PATH.exists():
        ckpt = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        if ckpt.get("sample_seed") == SEED and ckpt.get("n_sampled") == len(sample):
            model_scores = ckpt["model_scores"]
            valid_samples = [tuple(p) for p in ckpt["valid_samples"]]
            start_idx = ckpt["processed_count"]
            print(f"체크포인트 재개: {start_idx}/{len(sample)} 완료된 상태에서 시작")

    # 3개 모델로 개별 채점
    t0 = time.perf_counter()
    for i, (qid, case_id) in enumerate(sample, 1):
        if i <= start_idx:
            continue

        query = qid_text.get(qid, "")
        chunk = corpus_lookup.get(case_id, "")
        if not query or not chunk:
            continue

        scores = []
        for model in LABEL_MODELS:
            s = _label_one(model, query, chunk)
            scores.append(s)

        if all(s >= 0 for s in scores):
            for model, s in zip(LABEL_MODELS, scores):
                model_scores[model].append(s)
            valid_samples.append((qid, case_id))

        if i % 20 == 0 or i == len(sample):
            elapsed = time.perf_counter() - t0
            print(f"  [{i}/{len(sample)}] {elapsed:.0f}초 경과", flush=True)
            # 체크포인트 저장
            CHECKPOINT_PATH.write_text(json.dumps({
                "sample_seed": SEED,
                "n_sampled": len(sample),
                "processed_count": i,
                "model_scores": model_scores,
                "valid_samples": valid_samples,
            }, ensure_ascii=False), encoding="utf-8")

    n_valid = len(valid_samples)
    print(f"\n유효 샘플: {n_valid}건")

    # Fleiss κ
    ratings = [[model_scores[m][i] for m in LABEL_MODELS] for i in range(n_valid)]
    kappa = fleiss_kappa(ratings)
    grade = kappa_grade(kappa)

    # 충돌율 (3개 모두 다른 경우)
    conflicts = sum(1 for r in ratings if len(set(r)) == 3)
    conflict_rate = conflicts / n_valid if n_valid else 0

    # 점수 분포 (다수결 기준)
    majority_scores = []
    for r in ratings:
        cnt = Counter(r)
        max_cnt = max(cnt.values())
        majority_scores.append(max(k for k, v in cnt.items() if v == max_cnt))
    score_dist = dict(sorted(Counter(majority_scores).items()))

    # Cohen κ 쌍별
    def cohen_kappa(a: list[int], b: list[int]) -> float:
        n = len(a)
        cats = list(range(3))
        p_o = sum(1 for x, y in zip(a, b) if x == y) / n
        p_e = sum(
            (a.count(c) / n) * (b.count(c) / n) for c in cats
        )
        return (p_o - p_e) / (1 - p_e) if p_e != 1 else 1.0

    m0, m1, m2 = [model_scores[m] for m in LABEL_MODELS]
    cohen_01 = cohen_kappa(m0, m1)
    cohen_02 = cohen_kappa(m0, m2)
    cohen_12 = cohen_kappa(m1, m2)

    # 결과 출력
    print(f"\nFleiss κ = {kappa:.4f} ({grade})")
    print(f"충돌율   = {conflict_rate:.4f} ({conflicts}/{n_valid})")
    print(f"점수 분포: {score_dist}")
    print(f"Cohen κ ({LABEL_MODELS[0][:8]} / {LABEL_MODELS[1][:8]}): {cohen_01:.4f}")
    print(f"Cohen κ ({LABEL_MODELS[0][:8]} / {LABEL_MODELS[2][:8]}): {cohen_02:.4f}")
    print(f"Cohen κ ({LABEL_MODELS[1][:8]} / {LABEL_MODELS[2][:8]}): {cohen_12:.4f}")

    verdict = "VALID" if kappa >= 0.4 and conflict_rate <= 0.15 else "INVALID"
    print(f"\n판정: {verdict}")

    # 리포트 저장
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset": "V3_new_queries (Q-0051+)",
        "models": LABEL_MODELS,
        "n_total_pairs": len(all_pairs),
        "n_sampled": len(sample),
        "n_fully_scored": n_valid,
        "n_conflict": conflicts,
        "conflict_rate": round(conflict_rate, 4),
        "score_distribution": {str(k): v for k, v in score_dist.items()},
        "inter_rater_agreement": {
            "fleiss_kappa": round(kappa, 4),
            "fleiss_kappa_grade": grade,
            f"cohen_kappa_{LABEL_MODELS[0][:4]}_{LABEL_MODELS[1][:4]}": round(cohen_01, 4),
            f"cohen_kappa_{LABEL_MODELS[0][:4]}_{LABEL_MODELS[2][:4]}": round(cohen_02, 4),
            f"cohen_kappa_{LABEL_MODELS[1][:4]}_{LABEL_MODELS[2][:4]}": round(cohen_12, 4),
        },
        "validity_thresholds": {"fleiss_kappa_min": 0.4, "conflict_rate_max": 0.15},
        "verdict": verdict,
        "verdict_detail": f"Fleiss κ={kappa:.3f} ({grade}), 충돌율={conflict_rate*100:.1f}%",
        "note": f"전체 {len(all_pairs)}쌍 중 {n_valid}쌍 샘플 기반 추정치",
    }

    out_path = DATA_DIR / "new_queries_validity_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 리포트 저장: {out_path}")

    # 체크포인트 삭제
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


if __name__ == "__main__":
    main()

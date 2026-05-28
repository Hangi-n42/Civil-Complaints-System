"""
Issue #265 영향 측정 (데이터 변경 없음, in-memory)

코퍼스의 "null" placeholder 토큰이 평가 지표에 미치는 영향을 측정한다.
- BM25: corpus_meta를 in-memory로 정제(null 라인 제거) 후 동일 쿼리로 재평가
- Dense: ChromaDB 임베딩은 고정이라 직접 측정 불가 → null 토큰이 BGE-m3 임베딩에
  미치는 영향은 218자 문서 중 1토큰 수준으로 추정. BM25 영향으로 상한 가늠.

산출물: reports/retrieval/v3/risk265_null_impact.json
"""
from __future__ import annotations
import json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries, load_qrels, load_corpus, run_bm25, compute_metrics,
)

REPORT = Path("reports/retrieval/v3/risk265_null_impact.json")
PLACEHOLDERS = {"null", "none", "n/a"}


def clean_chunk_text(text: str) -> str:
    lines = [l for l in text.split("\n") if l.strip().lower() not in PLACEHOLDERS]
    return "\n".join(lines)


def _m(d, k):
    for kk, vv in d.items():
        if kk.lower() == k.lower():
            return vv
    return next((v for kk, v in d.items() if k.lower() in kk.lower()), 0.0)


def main() -> None:
    queries = load_queries()
    qrels = load_qrels()
    corpus = load_corpus()

    n_null = sum(1 for d in corpus if "null" in d["chunk_text"].lower())
    print(f"쿼리 {len(queries)} / qrels {len(qrels)} / corpus {len(corpus)} (null 포함 {n_null})")

    # (1) 현행 (null 포함)
    print("\n[1] BM25 현행 (null 포함)...")
    dirty = run_bm25(queries, corpus)
    dirty_m = compute_metrics(dirty, qrels)

    # (2) null 제거 corpus
    print("[2] BM25 null 제거...")
    clean_corpus = [
        {**d, "chunk_text": clean_chunk_text(d["chunk_text"])} for d in corpus
    ]
    clean = run_bm25(queries, clean_corpus)
    clean_m = compute_metrics(clean, qrels)

    print("\n" + "=" * 60)
    print(f"{'metric':<10}{'현행(null)':>14}{'null제거':>12}{'Δ':>10}")
    print("-" * 46)
    for k in ["nDCG@5", "nDCG@10", "R@10", "AP@10", "P@5"]:
        a, b = _m(dirty_m, k), _m(clean_m, k)
        print(f"{k:<10}{a:>14.4f}{b:>12.4f}{b-a:>+10.4f}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_queries": len(queries),
        "n_corpus": len(corpus),
        "n_null_docs": n_null,
        "bm25_with_null": dirty_m,
        "bm25_null_removed": clean_m,
        "note": "Dense는 ChromaDB 임베딩 고정으로 직접 측정 불가. BM25 영향이 상한 추정치.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT}")


if __name__ == "__main__":
    main()

"""조문 인덱스 헬스체크 (Phase B) — 로컬 실행용.

law_articles_v1(Dense)이 정상 빌드됐는지, Phase A→B(법령 필터)→Dense+BM25 하이브리드 검색·
인용 검증이 잘 도는지 한 번에 점검한다. (bge-m3/Chroma 필요 → 로컬)

  python scripts/check_law_index.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.retrieval.law_article_store import get_law_article_store  # noqa: E402
from app.structuring.legal_dictionary import get_legal_ref_matcher  # noqa: E402
from app.structuring.enrichment import (  # noqa: E402
    build_key_terms, normalize_entity_texts,
)
from app.structuring.law_corpus import validate_citations  # noqa: E402

QUERIES = [
    "무허가 가설건축물 이행강제금 부과 기준이 궁금합니다",
    "3톤 미만 지게차 조종 면허 적성검사 갱신 절차",
    "실업급여 수급 자격과 신청 방법",
    "도로에 불법 주정차 단속 기준과 과태료",
]


def main():
    store = get_law_article_store()
    matcher = get_legal_ref_matcher()

    try:
        cnt = store._get_collection().count()
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 컬렉션 접근 불가: {e}")
        return
    print(f"law_articles_v1 색인 조문 수: {cnt}")
    if cnt == 0:
        print("[FAIL] 인덱스가 비어 있음 → build_index(rebuild=True) 먼저.")
        return

    for q in QUERIES:
        et = normalize_entity_texts([], q)
        refs = matcher.match(q)
        law_ids = [r["law_id"] for r in refs if r.get("law_id")]
        kt = build_key_terms(q, et, refs)
        hits = store.search(q, law_ids=law_ids, key_terms=kt, top_k=3)
        print(f"\n■ {q}")
        print(f"   법령 필터: {[(r['name'], r.get('law_id')) for r in refs][:3]}")
        for h in hits:
            print(f"     [{h['law_name']} {h['article_no']}] score={h['score']:.4f}  {h['text'][:46]}…")

        # 인용 환각 검증 데모: 첫 조문은 valid, 가짜 조문은 invalid
        if hits:
            real = hits[0]
            res = validate_citations(
                [{"law_name": real["law_name"], "article_no": real["article_no"]},
                 {"law_name": real["law_name"], "article_no": "제999조"}],
                hits,
            )
            print(f"   인용검증 valid={len(res['valid'])} invalid(환각차단)={len(res['invalid'])}")

    print("\n[OK] 헬스체크 완료. Dense+BM25 하이브리드가 동작하면 위 순위가 BM25 단독보다 정밀합니다.")


if __name__ == "__main__":
    main()

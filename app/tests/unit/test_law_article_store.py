"""조문 검색 Hybrid(BM25+RRF) 순수 로직 + search 배선 테스트 (모델 불필요)."""

import json
import os

from app.retrieval.law_article_store import (
    BM25Index,
    LawArticleStore,
    _normalize_chroma_client_path,
    rank_articles,
    rrf_fuse,
    tokenize,
)


# ── tokenize (어절 + 한글 bigram) ─────────────────────────────────────────
def test_normalize_chroma_client_path_uses_relative_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    persist_dir = tmp_path / "한글경로" / "chroma_db"

    assert _normalize_chroma_client_path(persist_dir) == os.path.join(
        "한글경로", "chroma_db"
    )


def test_tokenize_emits_words_and_korean_bigrams():
    toks = tokenize("정기적성검사")
    assert "정기적성검사" in toks                 # 어절
    assert "적성" in toks and "검사" in toks       # bigram → 복합어 부분매칭
    # 영숫자는 bigram 분해하지 않음
    assert tokenize("A1B2") == ["A1B2"]


def test_tokenize_bigram_enables_compound_match():
    # 질의 '면허' 가 본문 '조종사면허' 와 bigram 으로 매칭
    assert "면허" in tokenize("건설기계조종사면허")


# ── BM25Index ─────────────────────────────────────────────────────────────
def test_bm25_ranks_matching_doc_higher():
    idx = BM25Index().fit(
        ["d1", "d2"],
        [tokenize("이행강제금 부과 기준"), tokenize("주차장 설치 기준")],
    )
    sc = idx.scores(tokenize("이행강제금"))
    assert sc.get("d1", 0) > sc.get("d2", 0)


def test_bm25_candidate_filter():
    idx = BM25Index().fit(["d1", "d2"], [tokenize("과태료 단속"), tokenize("과태료 부과")])
    sc = idx.scores(tokenize("과태료"), candidate_idx=[1])   # d2 만
    assert list(sc.keys()) == ["d2"]


# ── rrf_fuse ──────────────────────────────────────────────────────────────
def test_rrf_rewards_items_in_both_rankings():
    fused = dict(rrf_fuse([["a", "b", "c"], ["b", "x", "y"]]))
    assert fused["b"] > fused["a"]              # 양쪽 등장 → 상위


# ── rank_articles (Dense 측 키워드 부스트) ────────────────────────────────
def test_rank_articles_keyterm_boost():
    hits = [{"doc_id": "1", "article_no": "제3조", "text": "가설건축물 적용", "similarity": 0.70},
            {"doc_id": "2", "article_no": "제11조", "text": "건축허가", "similarity": 0.74}]
    ranked = rank_articles(hits, key_terms=["가설건축물", "적용"], top_k=5)
    assert ranked[0]["article_no"] == "제3조" and "score" in ranked[0]


# ── search (실제 코퍼스 없이 임시 코퍼스로) ───────────────────────────────
def _corpus(tmp_path):
    rows = [
        {"doc_id": "law:001823:제80조", "law_id": "001823", "law_name": "건축법",
         "doc_type": "law", "article_no": "제80조", "article_title": "이행강제금",
         "text": "제80조(이행강제금) 허가권자는 ...", "enforce_date": "", "source_url": "u80"},
        {"doc_id": "law:001823:제20조", "law_id": "001823", "law_name": "건축법",
         "doc_type": "law", "article_no": "제20조", "article_title": "가설건축물",
         "text": "제20조(가설건축물) 가설건축물 ...", "enforce_date": "", "source_url": "u20"},
        {"doc_id": "law:000239:제26조", "law_id": "000239", "law_name": "건설기계관리법",
         "doc_type": "law", "article_no": "제26조", "article_title": "면허",
         "text": "제26조 건설기계조종사면허 ...", "enforce_date": "", "source_url": "u26"},
    ]
    p = tmp_path / "law_articles.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return p


def test_search_bm25_only_respects_law_filter_and_relevance(tmp_path):
    p = _corpus(tmp_path)
    store = LawArticleStore(corpus_path=str(p), persist_directory=str(tmp_path / "cdb"))
    store._dense_ids = lambda *a, **k: []          # Dense 미가용 → BM25 단독
    out = store.search("이행강제금 부과", law_ids=["001823"], key_terms=["이행강제금"], top_k=3)
    names = [(h["law_name"], h["article_no"]) for h in out]
    assert ("건축법", "제80조") in names
    assert all(h["law_id"] == "001823" for h in out)   # 필터: 건설기계관리법 제외
    assert out[0]["article_no"] == "제80조"


def test_search_dense_passes_law_id_where_filter(tmp_path):
    p = _corpus(tmp_path)
    store = LawArticleStore(corpus_path=str(p), persist_directory=str(tmp_path / "cdb"))
    captured = {}

    class FakeColl:
        def query(self, query_embeddings, n_results, where, include):
            captured["where"] = where
            return {"ids": [["law:001823:제80조"]],
                    "metadatas": [[{"law_name": "건축법", "law_id": "001823",
                                    "article_no": "제80조", "source_url": "u80"}]],
                    "distances": [[0.2]], "documents": [["제80조(이행강제금) ..."]]}

    store._embed = lambda texts: [[0.0]]
    store._get_collection = lambda: FakeColl()
    out = store.search("이행강제금", law_ids=["001823"], top_k=3)
    assert captured["where"] == {"law_id": {"$in": ["001823"]}}
    assert any(h["article_no"] == "제80조" for h in out)


def test_corpus_uniquifies_duplicate_doc_ids(tmp_path):
    # 동일 law_id 에 같은 조번호(제21조)가 둘 → doc_id 충돌을 '#2' 로 분리(둘 다 보존)
    rows = [
        {"doc_id": "ordinance:2064510:제21조", "law_id": "2064510", "law_name": "○○조례",
         "doc_type": "ordinance", "article_no": "제21조", "article_title": "유류",
         "text": "제21조(유류 확보) ...", "source_url": "u1"},
        {"doc_id": "ordinance:2064510:제21조", "law_id": "2064510", "law_name": "○○조례",
         "doc_type": "ordinance", "article_no": "제21조", "article_title": "비치 서류",
         "text": "제21조(비치 서류) ...", "source_url": "u2"},
    ]
    p = tmp_path / "law_articles.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    store = LawArticleStore(corpus_path=str(p), persist_directory=str(tmp_path / "cdb"))
    recs = store._corpus()
    ids = [r["doc_id"] for r in recs]
    assert len(ids) == len(set(ids)) == 2                 # 유니크
    assert "ordinance:2064510:제21조#2" in ids            # 충돌분 분리


class _ResumableColl:
    """ChromaDB upsert/get/count 를 모사(영속 + 중단 시뮬레이션)."""
    def __init__(self, fail_after=None):
        self.store = set()
        self.upserts = 0
        self.fail_after = fail_after

    def get(self, include=None):
        return {"ids": list(self.store)}

    def upsert(self, ids, documents, embeddings, metadatas):
        self.upserts += 1
        if self.fail_after is not None and self.upserts > self.fail_after:
            raise RuntimeError("interrupted")
        self.store.update(ids)

    def count(self):
        return len(self.store)


def _resumable_store(tmp_path, fake):
    rows = [{"doc_id": f"law:1:제{i}조", "law_id": "1", "law_name": "L", "doc_type": "law",
             "article_no": f"제{i}조", "text": f"t{i}", "enforce_date": "", "source_url": ""}
            for i in range(5)]
    p = tmp_path / "law_articles.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    store = LawArticleStore(corpus_path=str(p), persist_directory=str(tmp_path / "c"))
    store._collection = fake
    store._get_collection = lambda: fake
    store._embed = lambda texts: [[0.0] for _ in texts]
    return store


def test_build_index_resumes_after_interruption(tmp_path):
    import pytest
    fake = _ResumableColl(fail_after=1)            # 2번째 배치에서 중단
    store = _resumable_store(tmp_path, fake)
    with pytest.raises(RuntimeError):
        store.build_index(rebuild=False, batch_size=2)
    assert fake.count() == 2                        # 첫 배치만 영속됨(체크포인트)

    fake.fail_after = None                          # 재실행
    res = store.build_index(rebuild=False, batch_size=2)
    assert fake.count() == 5                        # 끊긴 지점부터 이어서 완료
    assert res["indexed"] == 3 and res["skipped"] == 2


def test_build_index_skips_when_complete(tmp_path):
    fake = _ResumableColl()
    store = _resumable_store(tmp_path, fake)
    store.build_index(rebuild=False, batch_size=2)
    res = store.build_index(rebuild=False, batch_size=2)   # 재실행: 전부 skip
    assert res["indexed"] == 0 and res["skipped"] == 5

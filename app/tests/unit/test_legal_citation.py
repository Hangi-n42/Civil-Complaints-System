"""BE3 법령 인용 그라운딩/검증 순수 로직 테스트 (모델 불필요)."""

from app.generation.citation.legal_citation import (
    CITATION_REMOVED_MARKER,
    build_legal_context_block,
    extract_legal_citations,
    ground_legal_citations,
    retrieve_legal_context,
)

RETRIEVED = [
    {"law_name": "건축법", "article_no": "제80조", "law_id": "001823",
     "source_url": "u80", "text": "제80조(이행강제금) ..."},
    {"law_name": "건축법", "article_no": "제20조", "law_id": "001823",
     "source_url": "u20", "text": "제20조(가설건축물) ..."},
]


# ── 인용 추출 ─────────────────────────────────────────────────────────────
def test_extract_with_known_names():
    cites = extract_legal_citations("건축법 제80조에 따르면 이행강제금을 부과한다.", ["건축법"])
    assert cites[0]["law_name"] == "건축법"
    assert cites[0]["article_no"] == "제80조"


def test_extract_branch_article():
    cites = extract_legal_citations("고용보험법 제40조의2를 보라", ["고용보험법"])
    assert cites[0]["article_no"] == "제40조의2"


def test_extract_generic_lawname_without_known():
    cites = extract_legal_citations("도로교통법 제160조에 따른 과태료")
    assert cites[0]["law_name"] == "도로교통법" and cites[0]["article_no"] == "제160조"


def test_extract_multiple():
    cites = extract_legal_citations("건축법 제80조와 건축법 제20조", ["건축법"])
    assert [c["article_no"] for c in cites] == ["제80조", "제20조"]


# ── 그라운딩(환각 제거 + 플래그) ─────────────────────────────────────────
def test_ground_removes_hallucinated_citation():
    answer = "건축법 제80조에 따라 이행강제금을 부과하며, 건축법 제999조도 적용됩니다."
    out = ground_legal_citations(answer, RETRIEVED)
    assert len(out["valid"]) == 1 and out["valid"][0]["article_no"] == "제80조"
    assert "source_url" not in out["valid"][0]
    assert out["valid"][0]["public_url"].startswith("https://")
    assert len(out["invalid"]) == 1 and out["invalid"][0]["article_no"] == "제999조"
    assert CITATION_REMOVED_MARKER in out["answer"]      # 환각 인용 제거됨
    assert "제999조" not in out["answer"]
    assert "제80조" in out["answer"]                      # 검증 인용은 유지
    assert len(out["warnings"]) == 1


def test_ground_no_citations():
    out = ground_legal_citations("특별한 법령 인용이 없는 답변입니다.", RETRIEVED)
    assert out["valid"] == [] and out["invalid"] == []
    assert out["answer"] == "특별한 법령 인용이 없는 답변입니다."


def test_ground_strips_span_field():
    out = ground_legal_citations("건축법 제80조", RETRIEVED)
    assert all("_span" not in c for c in out["valid"] + out["invalid"])


# ── 프롬프트 블록 ─────────────────────────────────────────────────────────
def test_build_context_block():
    block = build_legal_context_block(RETRIEVED)
    assert "[법령 조문]" in block
    assert "건축법 제80조" in block


# ── 그라운딩 조건(legal_refs 있을 때만) ──────────────────────────────────
def test_retrieve_skips_without_law_id():
    assert retrieve_legal_context("질의", [{"name": "건축법", "law_id": ""}]) == []
    assert retrieve_legal_context("질의", []) == []


def test_retrieve_uses_law_ids_when_present():
    captured = {}

    class FakeStore:
        def search(self, query, law_ids=None, key_terms=None, top_k=5):
            captured["law_ids"] = law_ids
            return [{"law_name": "건축법", "article_no": "제80조"}]

    out = retrieve_legal_context("질의", [{"name": "건축법", "law_id": "001823"}],
                                 key_terms=["이행강제금"], store=FakeStore())
    assert captured["law_ids"] == ["001823"] and out

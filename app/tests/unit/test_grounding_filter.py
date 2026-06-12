"""grounding 필터 공유 코어 + 서비스 통합 단위 테스트 (#305). LLM 호출은 mock."""

from __future__ import annotations

import asyncio
import logging

import app.retrieval.grounding_filter as gf
from app.retrieval.grounding_filter import (
    extract_score,
    extract_scores,
    filter_by_relevance,
    filter_by_scores,
)
from app.retrieval.service import RetrievalService


def _score_fn(scores: dict[str, int | None]):
    async def fn(query_text: str, doc_text: str):  # noqa: ARG001
        for key, s in scores.items():
            if key in doc_text:
                return s
        return 0
    return fn


def _run(coro):
    return asyncio.run(coro)


# ── 공유 코어 ───────────────────────────────────────────────────────────────
def test_extract_score():
    assert extract_score('{"score": 2}') == 2
    assert extract_score("score: 0") == 0
    assert extract_score("1") == 1
    assert extract_score("없음") is None
    assert extract_score("") is None


def test_extract_scores_requires_exact_valid_array():
    assert extract_scores('{"scores": [2, 0, 1]}', 3) == [2, 0, 1]
    assert extract_scores('{"scores": [2, 0]}', 3) is None
    assert extract_scores('{"scores": [2, 3, 1]}', 3) is None
    assert extract_scores("not-json", 1) is None


def test_filter_by_scores_matches_single_item_semantics():
    kept = filter_by_scores(["D1", "D2", "D3"], [2, 0, None], top_k=5)
    assert kept == [("D1", 2.0), ("D3", 0.5)]


def test_filter_drops_rel0_and_reranks():
    items = ["D1", "D2", "D3"]
    kept = _run(filter_by_relevance(
        "q", items, get_text=lambda x: x, score_fn=_score_fn({"D1": 2, "D2": 0, "D3": 1}), top_k=5))
    assert [it for it, _ in kept] == ["D1", "D3"]


def test_filter_empty_when_all_rel0():
    kept = _run(filter_by_relevance(
        "q", ["D1", "D2"], get_text=lambda x: x, score_fn=_score_fn({"D1": 0, "D2": 0}), top_k=5))
    assert kept == []


def test_filter_top_k_and_pool():
    kept = _run(filter_by_relevance(
        "q", ["D1", "D2", "D3"], get_text=lambda x: x,
        score_fn=_score_fn({"D1": 2, "D2": 1, "D3": 2}), rerank_pool=2, top_k=1))
    # pool=2 → D3 미채점 제외, top_k=1 → 최고 점수 1개
    assert [it for it, _ in kept] == ["D1"]


def test_filter_permissive_on_none():
    kept = _run(filter_by_relevance(
        "q", ["D1", "D2"], get_text=lambda x: x, score_fn=_score_fn({"D1": None, "D2": 2}), top_k=5))
    assert [it for it, _ in kept] == ["D2", "D1"]  # 실패는 유지하되 양성 뒤


def test_filter_empty_input():
    assert _run(filter_by_relevance("q", [], get_text=lambda x: x, score_fn=_score_fn({}))) == []


# ── 서비스 통합 ─────────────────────────────────────────────────────────────
def test_grounding_text_uses_snippet_and_domain():
    item = {"snippet": "주차 분쟁 본문", "metadata": {"category": "주택", "region": "서울"}}
    assert RetrievalService._grounding_text(item) == "[주택 서울] 주차 분쟁 본문"


def test_grounding_text_fallbacks_to_summary_then_title():
    item = {"summary": {"observation": "관찰", "request": "요청"}}
    assert "관찰" in RetrievalService._grounding_text(item)
    assert RetrievalService._grounding_text({"title": "제목만"}) == "제목만"
    assert RetrievalService._grounding_text({"case_id": "CASE-1"}) == "CASE-1"


def _bare_service() -> RetrievalService:
    svc = RetrievalService.__new__(RetrievalService)  # __init__ 우회(ChromaDB 불필요)
    svc.logger = logging.getLogger("test")
    return svc


def test_apply_grounding_filter_removes_rel0(monkeypatch):
    async def fake_batch(q, texts, **kw):  # noqa: ARG001
        return [0 if "나쁨" in text else 2 for text in texts]
    monkeypatch.setattr(gf, "score_relevance_batch", fake_batch)

    results = [
        {"case_id": "A", "snippet": "좋음 본문"},
        {"case_id": "B", "snippet": "나쁨 본문"},
        {"case_id": "C", "snippet": "좋음 본문2"},
    ]
    out = _run(_bare_service()._apply_grounding_filter("q", results, top_k=5))
    assert [r["case_id"] for r in out] == ["A", "C"]


def test_apply_grounding_filter_empty_when_all_bad(monkeypatch):
    async def fake_batch(q, texts, **kw):  # noqa: ARG001
        return [0] * len(texts)
    monkeypatch.setattr(gf, "score_relevance_batch", fake_batch)
    out = _run(_bare_service()._apply_grounding_filter("q", [{"case_id": "A", "snippet": "x"}], top_k=5))
    assert out == []


def test_apply_grounding_filter_falls_back_to_single_scores(monkeypatch):
    async def broken_batch(q, texts, **kw):  # noqa: ARG001
        return None

    async def fake_score(q, text, **kw):  # noqa: ARG001
        return 0 if "나쁨" in text else 2

    monkeypatch.setattr(gf, "score_relevance_batch", broken_batch)
    monkeypatch.setattr(gf, "score_relevance", fake_score)
    results = [
        {"case_id": "A", "snippet": "좋음"},
        {"case_id": "B", "snippet": "나쁨"},
    ]
    out = _run(_bare_service()._apply_grounding_filter("q", results, top_k=5))
    assert [item["case_id"] for item in out] == ["A"]

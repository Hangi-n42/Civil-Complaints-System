from __future__ import annotations

import pytest

from app.api.schemas.retrieval import SearchRequest
from app.core.config import settings
from app.retrieval.service import RetrievalService


def _result(case_id: str, score: float, metadata: dict | None = None) -> dict:
    return {
        "rank": 1,
        "doc_id": case_id,
        "case_id": case_id,
        "chunk_id": f"{case_id}__chunk-0",
        "score": score,
        "title": case_id,
        "snippet": case_id,
        "summary": {"observation": "", "request": ""},
        "metadata": metadata or {},
    }


def test_search_query_signals_are_normalized():
    request = SearchRequest(
        query="가로등 점검",
        query_signals={
            "entity_texts": "가로등| 가로등 ",
            "legal_ref_ids": ["001706", "001706", ""],
            "key_terms": ["조명", " 점검 "],
            "responsible_units_source": " be1_structured ",
        },
    )

    assert request.query_signals is not None
    assert request.query_signals.entity_texts == ["가로등"]
    assert request.query_signals.legal_ref_ids == ["001706"]
    assert request.query_signals.key_terms == ["조명", "점검"]
    assert request.query_signals.responsible_units_source == "be1_structured"


def test_default_collection_uses_clean_collection_name():
    assert settings.DEFAULT_CHROMA_COLLECTION == "civil_cases_v1"
    assert SearchRequest(query="가로등 점검").collection_name == settings.DEFAULT_CHROMA_COLLECTION
    assert RetrievalService().default_collection_name == settings.DEFAULT_CHROMA_COLLECTION


def test_metadata_soft_rerank_without_query_signals_keeps_results_unchanged():
    service = RetrievalService()
    results = [_result("CASE-A", 0.1), _result("CASE-B", 0.09)]

    assert service._apply_metadata_soft_rerank(results, None) is results
    assert service._apply_metadata_soft_rerank(results, {}) is results


def test_metadata_soft_rerank_lifts_matching_metadata_candidate():
    service = RetrievalService()
    query_signals = service._normalize_query_signals(
        {
            "legal_ref_ids": ["001706"],
            "entity_texts": ["가로등"],
            "responsible_units": ["도로관리과"],
            "key_terms": ["가로등", "점검"],
        }
    )
    results = [
        _result("CASE-NOMATCH", 0.100, {"legal_ref_ids": ["000000"]}),
        _result(
            "CASE-MATCH",
            0.096,
            {
                "legal_ref_ids": ["001706"],
                "entity_texts": ["가로등"],
                "responsible_units": ["도로관리과"],
                "key_terms": ["가로등", "점검"],
            },
        ),
    ]

    reranked = service._apply_metadata_soft_rerank(results, query_signals)

    assert [item["case_id"] for item in reranked] == ["CASE-MATCH", "CASE-NOMATCH"]
    assert reranked[0]["rank"] == 1
    assert reranked[0]["score"] == pytest.approx(0.096 * 1.17)


def test_metadata_soft_rerank_responsible_units_only_is_soft_signal():
    service = RetrievalService()
    query_signals = service._normalize_query_signals(
        {"responsible_units": ["도로관리과"]}
    )
    results = [
        _result("CASE-NOMATCH", 0.100, {"responsible_units": ["공원관리과"]}),
        _result("CASE-MATCH", 0.098, {"responsible_units": ["도로관리과"]}),
    ]

    reranked = service._apply_metadata_soft_rerank(results, query_signals)

    assert [item["case_id"] for item in reranked] == ["CASE-MATCH", "CASE-NOMATCH"]
    assert [item["rank"] for item in reranked] == [1, 2]
    assert reranked[0]["score"] == pytest.approx(0.098 * 1.03)
    assert reranked[1]["score"] == pytest.approx(0.100)


def test_metadata_soft_rerank_boost_is_capped():
    service = RetrievalService()
    query_signals = service._normalize_query_signals(
        {
            "legal_ref_ids": ["001706"],
            "legal_ref_names": ["도로법"],
            "entity_texts": ["가로등"],
            "responsible_units": ["도로관리과"],
            "key_terms": ["가로등", "조명", "점검", "보수", "야간"],
        }
    )
    item = _result(
        "CASE-MATCH",
        1.0,
        {
            "legal_ref_ids": ["001706"],
            "legal_ref_names": ["도로법"],
            "entity_texts": ["가로등"],
            "responsible_units": ["도로관리과"],
            "key_terms": ["가로등", "조명", "점검", "보수", "야간"],
        },
    )

    assert service._metadata_soft_boost(query_signals, item) == pytest.approx(0.20)
    assert service._apply_metadata_soft_rerank([item], query_signals)[0]["score"] == pytest.approx(1.20)


@pytest.mark.asyncio
async def test_metadata_soft_rerank_runs_before_grounding_filter(monkeypatch):
    service = RetrievalService()
    seen_before_grounding: list[str] = []

    class _Store:
        def count(self, collection_name):  # noqa: ARG002
            return 1

        def query(self, **kwargs):  # noqa: ARG002
            return []

    class _Hybrid:
        def search(self, collection_name, query, top_k, dense_results, fanout=50):  # noqa: ARG002
            return [
                _result("CASE-NOMATCH", 0.100, {"legal_ref_ids": ["000000"]}),
                _result("CASE-MATCH", 0.096, {"legal_ref_ids": ["001706"]}),
            ]

    async def _fake_grounding_filter(query, results, top_k):  # noqa: ARG001
        seen_before_grounding.extend(item["case_id"] for item in results)
        return results[:top_k]

    monkeypatch.setattr(service, "_get_vectorstore", lambda: _Store())
    monkeypatch.setattr(service, "_get_hybrid", lambda: _Hybrid())
    monkeypatch.setattr(service, "_apply_grounding_filter", _fake_grounding_filter)

    results = await service.search(
        query="가로등 점검",
        top_k=1,
        collection_name="civil_cases_v1",
        strategy="hybrid",
        grounding_filter=True,
        query_signals={"legal_ref_ids": ["001706"]},
    )

    assert seen_before_grounding == ["CASE-MATCH", "CASE-NOMATCH"]
    assert [item["case_id"] for item in results] == ["CASE-MATCH"]


def test_snippet_preserves_late_decision_constraint():
    service = RetrievalService()
    text = (
        "민원인은 자전거도로 설치를 요청했습니다.\n"
        "현장 통행 불편이 확인되었습니다.\n"
        "자전거도로 설치 요청입니다.\n"
        "도로 폭이 좁아 현재 설치는 어렵고 확폭 시 재검토합니다."
    )

    snippet = service._build_snippet(text, max_length=120)

    assert "자전거도로 설치" in snippet
    assert "도로 폭이 좁아" in snippet
    assert "어렵" in snippet


@pytest.mark.asyncio
async def test_search_excludes_current_case_before_grounding(monkeypatch):
    service = RetrievalService()
    seen_before_grounding: list[str] = []

    class _Store:
        def count(self, collection_name):  # noqa: ARG002
            return 2

        def query(self, **kwargs):  # noqa: ARG002
            return [
                _result("CASE-800806", 0.99, {}),
                _result("CASE-OTHER", 0.90, {}),
            ]

    async def _fake_grounding_filter(query, results, top_k):  # noqa: ARG001
        seen_before_grounding.extend(item["case_id"] for item in results)
        return results[:top_k]

    monkeypatch.setattr(service, "_get_vectorstore", lambda: _Store())
    monkeypatch.setattr(service, "_apply_grounding_filter", _fake_grounding_filter)

    results = await service.search(
        query="버스 배차 민원",
        top_k=1,
        collection_name="civil_cases_v1",
        strategy="dense",
        grounding_filter=True,
        exclude_case_id="800806",
    )

    assert seen_before_grounding == ["CASE-OTHER"]
    assert [item["case_id"] for item in results] == ["CASE-OTHER"]


@pytest.mark.asyncio
async def test_search_limits_be3_grounding_candidate_pool(monkeypatch):
    service = RetrievalService()
    seen_count = 0

    class _Store:
        def count(self, collection_name):  # noqa: ARG002
            return 8

        def query(self, **kwargs):  # noqa: ARG002
            return [_result(f"CASE-{index}", 1.0 - index * 0.01, {}) for index in range(8)]

    async def _fake_grounding_filter(query, results, top_k):  # noqa: ARG001
        nonlocal seen_count
        seen_count = len(results)
        return results[:top_k]

    monkeypatch.setattr(service, "_get_vectorstore", lambda: _Store())
    monkeypatch.setattr(service, "_apply_grounding_filter", _fake_grounding_filter)

    await service.search(
        query="시설 개선",
        top_k=3,
        collection_name="civil_cases_v1",
        strategy="dense",
        grounding_filter=True,
        grounding_pool=5,
    )

    assert seen_count == 5

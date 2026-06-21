from __future__ import annotations

import pytest

from app.retrieval.service import RetrievalService


class _SegmentStore:
    def __init__(self):
        self.calls = []

    def count(self, collection_name):
        return 1

    def query(self, *, collection_name, query, top_k, filters=None, threshold=0.0, snippet_max_chars=140):
        self.calls.append(
            {
                "collection_name": collection_name,
                "query": query,
                "top_k": top_k,
                "filters": filters,
                "snippet_max_chars": snippet_max_chars,
            }
        )
        if query == "임대주택 보수":
            return [
                {
                    "rank": 1,
                    "doc_id": "DOC-REPAIR",
                    "score": 0.76,
                    "chunk_id": "CASE-REPAIR__chunk-0",
                    "case_id": "CASE-REPAIR",
                    "title": "임대주택 보수 절차",
                    "snippet": "임대주택 보수 절차를 안내합니다."[:snippet_max_chars],
                    "summary": {"observation": "임대주택 보수", "request": "보수 절차 안내"},
                    "metadata": {
                        "created_at": "2026-04-10T10:00:00+09:00",
                        "category": "welfare",
                        "region": "서울",
                        "entity_labels": ["FACILITY"],
                    },
                }
            ]
        if query == "관리비 기준":
            return [
                {
                    "rank": 1,
                    "doc_id": "DOC-FEE",
                    "score": 0.82,
                    "chunk_id": "CASE-FEE__chunk-0",
                    "case_id": "CASE-FEE",
                    "title": "임대주택 관리비 기준",
                    "snippet": "관리비 기준을 안내합니다."[:snippet_max_chars],
                    "summary": {"observation": "임대주택 관리비", "request": "관리비 기준 안내"},
                    "metadata": {
                        "created_at": "2026-04-10T10:00:00+09:00",
                        "category": "welfare",
                        "region": "서울",
                        "entity_labels": ["FACILITY"],
                    },
                }
            ]
        return [
            {
                "rank": 1,
                "doc_id": "DOC-BASE",
                "score": 0.9,
                "chunk_id": "CASE-BASE__chunk-0",
                "case_id": "CASE-BASE",
                "title": "임대주택 관리비 기준과 보수 절차",
                "snippet": "관리비 기준과 보수 절차를 안내합니다."[:snippet_max_chars],
                "summary": {"observation": "임대주택 보수", "request": "관리비 기준 안내"},
                "metadata": {
                    "created_at": "2026-04-10T10:00:00+09:00",
                    "category": "welfare",
                    "region": "서울",
                    "entity_labels": ["FACILITY"],
                },
            }
        ]


@pytest.mark.asyncio
async def test_request_segments_add_segment_search_and_matched_segments(monkeypatch):
    service = RetrievalService()
    store = _SegmentStore()
    monkeypatch.setattr(service, "_get_vectorstore", lambda: store)

    results = await service.search(
        query="임대주택 보수 및 관리비 기준",
        top_k=5,
        collection_name="civil_cases_v1",
        topic_type="welfare",
        request_segments=["임대주택 보수", "관리비 기준"],
        retrieval_policy="admin_policy",
        snippet_max_chars=320,
    )

    assert len(store.calls) == 3
    assert store.calls[0]["query"] == "임대주택 보수 및 관리비 기준"
    assert store.calls[1]["query"] == "임대주택 보수"
    assert store.calls[2]["query"] == "관리비 기준"
    assert all(call["snippet_max_chars"] == 320 for call in store.calls)
    assert len(results) == 3
    by_doc = {item["doc_id"]: item for item in results}
    assert by_doc["DOC-REPAIR"]["metadata"]["matched_segments"] == ["임대주택 보수"]
    assert by_doc["DOC-FEE"]["metadata"]["matched_segments"] == ["관리비 기준"]
    assert by_doc["DOC-BASE"]["metadata"].get("matched_segments") in (None, [])
    assert all(item["metadata"]["retrieval_policy"] == "admin_policy" for item in results)
    assert all(item["metadata"]["topic_type"] == "welfare" for item in results)


@pytest.mark.asyncio
async def test_single_query_uses_policy_without_segment_merge(monkeypatch):
    service = RetrievalService()
    store = _SegmentStore()
    monkeypatch.setattr(service, "_get_vectorstore", lambda: store)

    results = await service.search(
        query="도로 시설 안전 점검",
        top_k=4,
        collection_name="civil_cases_v1",
        topic_type="traffic",
        retrieval_policy="field_ops",
        snippet_max_chars=400,
    )

    assert len(store.calls) == 1
    assert store.calls[0]["query"] == "도로 시설 안전 점검"
    assert store.calls[0]["snippet_max_chars"] == 400
    assert results[0]["metadata"]["retrieval_policy"] == "field_ops"
    assert results[0]["metadata"]["topic_type"] == "traffic"

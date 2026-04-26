from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.exceptions import RetrievalError


class _StubRetrievalService:
    async def index_documents(self, documents, rebuild=False, collection_name=None, **kwargs):
        return {
            "indexed_count": len(documents),
            "chunk_count": len(documents),
            "index_name": "civil_cases",
            "rebuild": rebuild,
            "records": [
                {"case_id": "CASE-1", "chunk_ids": ["CASE-1__chunk-0"]},
            ],
        }

    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        return [
            {
                "rank": 1,
                "doc_id": "DOC-1",
                "score": 0.9,
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "title": "테스트 제목",
                "snippet": "테스트 스니펫",
                "summary": {"observation": "obs", "request": "req"},
                "metadata": {
                    "created_at": "2026-03-20T10:00:00+09:00",
                    "category": "도로안전",
                    "region": "서울",
                    "entity_labels": ["FACILITY"],
                },
            }
        ]


class _FailSearchService:
    async def index_documents(self, documents, rebuild=False, collection_name=None, **kwargs):
        return {
            "indexed_count": len(documents),
            "chunk_count": len(documents),
            "index_name": "civil_cases",
            "rebuild": rebuild,
            "records": [],
        }

    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        raise RetrievalError("index unavailable")


def test_search_response_is_wrapped(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _StubRetrievalService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"request_id": "SRCH-2026-000001", "query": "가로등", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["request_id"], str)
    assert isinstance(body["timestamp"], str)
    assert "data" in body
    assert body["request_id"] == "SRCH-2026-000001"
    assert "elapsed_ms" in body["data"]
    assert "total_found" in body["data"]
    assert isinstance(body["data"]["strategy_id"], str)
    assert isinstance(body["data"]["route_key"], str)
    assert isinstance(body["data"]["routing_hint"], dict)
    assert isinstance(body["data"]["routing_trace"], dict)
    assert "/" in body["data"]["route_key"]
    assert body["data"]["routing_trace"]["complexity_level"] in {"low", "medium", "high"}
    assert 0.0 <= float(body["data"]["routing_trace"]["complexity_score"]) <= 1.0
    assert isinstance(body["data"]["routing_trace"]["route_reason"], str)
    assert body["data"]["routing_trace"]["route_reason"]
    assert "complexity=" in body["data"]["routing_trace"]["route_reason"]
    assert "top_k=" in body["data"]["routing_trace"]["route_reason"]
    assert "chunk_policy=" in body["data"]["routing_trace"]["route_reason"]
    assert body["data"]["routing_trace"]["route_key"] == body["data"]["route_key"]
    assert body["data"]["routing_trace"]["strategy_id"] == body["data"]["strategy_id"]
    assert isinstance(body["data"]["routing_trace"]["applied_filters"], dict)
    assert isinstance(body["data"]["routing_trace"]["request_segments"], list)
    assert len(body["data"]["routing_trace"]["request_segments"]) >= 1
    assert "cross_sentence_dependency" in body["data"]["routing_trace"]["complexity_trace"]
    assert body["data"]["routing_trace"]["segment_count"] >= 1
    assert body["data"]["routing_trace"]["merge_policy"] in {"single_query", "dedupe_max_score"}
    assert body["data"]["routing_trace"]["retrieval_policy"] in {"admin_policy", "field_ops", "general"}
    assert body["data"]["routing_hint"]["top_k"] in {4, 6, 9}
    assert body["data"]["routing_hint"]["snippet_max_chars"] in {400, 700, 1100}
    assert body["data"]["routing_hint"]["chunk_policy"] in {"compact", "balanced", "expanded"}
    assert isinstance(body["data"]["retrieved_docs"], list)
    assert isinstance(body["data"]["results"], list)
    first = body["data"]["results"][0]
    assert first["rank"] == 1
    assert first["case_id"] == "CASE-1"
    assert isinstance(first["similarity_score"], float)
    assert set(first["content"].keys()) == {"observation", "result", "request", "context"}
    assert set(first["metadata"].keys()) == {
        "created_at",
        "category",
        "region",
        "entity_labels",
        "strategy_id",
        "route_key",
        "topic_type",
        "retrieval_policy",
        "matched_segments",
    }
    assert first["doc_id"] == "DOC-1"
    assert isinstance(first["score"], float)
    assert first["chunk_id"] == "CASE-1__chunk-0"
    assert isinstance(first["snippet"], str)
    assert set(first["summary"].keys()) == {"observation", "request"}
    assert isinstance(first["answers_by_admin_unit"], dict)
    assert isinstance(first["department_answers"], dict)


def test_index_response_is_wrapped(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _StubRetrievalService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/index",
        json={
            "request_id": "IDX-2026-000001",
            "action": "incremental",
            "collection_name": "civil_cases_v1",
            "cases": [{"case_id": "CASE-1", "text": "민원"}],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["request_id"] == "IDX-2026-000001"
    assert isinstance(body["timestamp"], str)
    assert "data" in body
    assert body["data"]["indexed_count"] == 1
    assert body["data"]["failed_count"] == 0
    assert body["data"]["collection_name"] == "civil_cases_v1"
    assert "elapsed_ms" in body["data"]


def test_search_bad_request_retryable_false(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _StubRetrievalService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"request_id": "SRCH-2026-000099", "query": "   ", "top_k": 5},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "BAD_REQUEST"
    assert body["error"]["retryable"] is False


def test_search_index_not_ready_retryable_true(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _FailSearchService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"request_id": "SRCH-2026-000100", "query": "가로등", "top_k": 5},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INDEX_NOT_READY"
    assert body["error"]["retryable"] is True

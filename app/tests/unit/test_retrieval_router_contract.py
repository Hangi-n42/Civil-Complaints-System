from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.exceptions import RetrievalError


class _StubRetrievalService:
    async def index_documents(self, documents, rebuild=False):
        return {
            "indexed_count": len(documents),
            "chunk_count": len(documents),
            "index_name": "civil_cases",
            "rebuild": rebuild,
            "records": [
                {"case_id": "CASE-1", "chunk_ids": ["CASE-1__chunk-0"]},
            ],
        }

    async def search(self, query, top_k=5, filters=None):
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
    async def index_documents(self, documents, rebuild=False):
        return {
            "indexed_count": len(documents),
            "chunk_count": len(documents),
            "index_name": "civil_cases",
            "rebuild": rebuild,
            "records": [],
        }

    async def search(self, query, top_k=5, filters=None):
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
    assert isinstance(body["data"]["results"], list)


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

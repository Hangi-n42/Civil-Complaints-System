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


class _CapturingRetrievalService(_StubRetrievalService):
    def __init__(self):
        self.calls = []

    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "filters": filters,
                "collection_name": collection_name,
                **kwargs,
            }
        )
        return await super().search(
            query,
            top_k=top_k,
            filters=filters,
            collection_name=collection_name,
            **kwargs,
        )


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
    assert body["data"]["routing_trace"]["complexity_trace"]["title_question_boundary_used"] is False
    assert body["data"]["routing_trace"]["segment_count"] >= 1
    assert body["data"]["routing_trace"]["merge_policy"] == "single_query"
    assert body["data"]["routing_trace"]["retrieval_policy"] in {"admin_policy", "field_ops", "general"}
    assert body["data"]["routing_hint"]["top_k"] == 5
    assert body["data"]["routing_hint"]["snippet_max_chars"] == 1100
    assert body["data"]["routing_hint"]["chunk_policy"] == "balanced"
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
        "entity_texts",
        "legal_ref_names",
        "legal_ref_ids",
        "key_terms",
        "responsible_units",
        "responsible_units_source",
        "responsible_units_confidence",
        "civil_category_primary",
        "civil_category_secondary",
        "civil_category_source",
        "urgency_level",
        "strategy_id",
        "route_key",
        "topic_type",
        "complexity_level",
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


def test_search_passes_request_segments_for_complex_query(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    service = _CapturingRetrievalService()
    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: service,
    )
    monkeypatch.setattr(
        retrieval_router,
        "_build_routing_payload",
        lambda query: {
            "strategy_id": "topic_traffic_high_v1",
            "route_key": "traffic/high",
            "retrieval_policy": "field_ops",
            "request_segments": ["도로 파손 보수 요청", "불법 주정차 단속 요청"],
            "merge_policy": "segment_aware_dedupe",
            "routing_hint": {
                "strategy_id": "topic_traffic_high_v1",
                "route_key": "traffic/high",
                "top_k": 5,
                "snippet_max_chars": 1100,
                "chunk_policy": "balanced",
            },
            "routing_trace": {
                "topic_type": "traffic",
                "complexity_level": "high",
                "complexity_score": 0.86,
                "request_segments": ["도로 파손 보수 요청", "불법 주정차 단속 요청"],
                "complexity_trace": {
                    "intent_count": 2,
                    "constraint_count": 0,
                    "entity_diversity": 2,
                    "policy_reference_count": 0,
                    "cross_sentence_dependency": False,
                },
                "route_reason": "stub",
                "route_key": "traffic/high",
                "strategy_id": "topic_traffic_high_v1",
                "applied_filters": {},
                "segment_count": 2,
                "merge_policy": "segment_aware_dedupe",
                "retrieval_policy": "field_ops",
            },
            "analyzer_output": {},
            "analyzer_latency_ms": 0,
            "router_latency_ms": 0,
            "applied_params": {
                "top_k": 5,
                "snippet_max_chars": 1100,
                "chunk_policy": "balanced",
                "retrieval_policy": "field_ops",
            },
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "request_id": "SRCH-2026-000002",
            "query": "도로 파손도 보수하고 불법 주정차도 단속해 주세요.",
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["routing_trace"]["merge_policy"] == "segment_aware_dedupe"
    assert body["data"]["routing_trace"]["route_reason"].startswith("segment_aware_search;")
    assert service.calls[0]["request_segments"] == ["도로 파손 보수 요청", "불법 주정차 단속 요청"]


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

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


class _StubGenerationService:
    async def generate_qa(self, query, context, routing_trace=None):
        return {
            "answer": "요청하신 민원 처리 절차를 안내드립니다.",
            "citations": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "relevance_score": 0.91,
                }
            ],
            "limitations": "실제 처리 기간은 지자체 상황에 따라 달라질 수 있습니다.",
            "model": "stub-model",
        }


class _StubCitationMapper:
    def validate_citations_against_context(self, citations, retrieval_context):
        return True, 0, []


def test_qa_requires_routing_hint(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0001",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "top_k": 5,
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "routing_hint is required"


def test_qa_rejects_inconsistent_strategy_and_route_key(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0002",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_traffic_low_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ROUTING_STRATEGY_INCONSISTENT"


def test_qa_rejects_malformed_route_key(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0003",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high/extra",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "exactly one slash" in body["error"]["message"]


def test_qa_week5_response_skeleton(monkeypatch):
    from app.api.routers import generation as generation_router

    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0001",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
            "use_search_results": True,
            "search_results": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "score": 0.91,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "request_id" in body
    assert "timestamp" in body

    data = body["data"]
    assert data["complaint_id"] == "CMP-2026-0001"
    assert data["strategy_id"] == "topic_welfare_high_v1"
    assert data["route_key"] == "welfare/high"
    assert isinstance(data["routing_trace"], dict)
    assert data["routing_trace"]["complexity_level"] in {"low", "medium", "high"}
    assert 0.0 <= float(data["routing_trace"]["complexity_score"]) <= 1.0
    assert isinstance(data["routing_trace"]["route_reason"], str)
    assert data["routing_trace"]["route_reason"]
    assert set(data["structured_output"].keys()) == {"summary", "action_items", "request_segments"}
    assert isinstance(data["answer"], str)
    assert isinstance(data["citations"], list)
    assert isinstance(data["limitations"], list)
    assert set(data["latency_ms"].keys()) == {"analyzer", "router", "retrieval", "generation"}
    assert set(data["quality_signals"].keys()) == {
        "citation_coverage",
        "hallucination_flag",
        "segment_coverage",
    }

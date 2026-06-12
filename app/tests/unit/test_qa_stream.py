"""SSE QA progress endpoint contract tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.main import app


class _StubGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        return {
            "answer": "민원 처리 절차를 안내합니다.",
            "citations": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원은 접수 후 담당 부서에서 검토합니다.",
                    "relevance_score": 0.91,
                }
            ],
            "limitations": "실제 처리 기간은 상황에 따라 달라질 수 있습니다.",
        }


class _StubCitationMapper:
    def validate_citations_against_context(self, citations, retrieval_context):
        return True, 0, []


class _StubRetrievalService:
    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        return [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "민원은 접수 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def _payload() -> dict:
    return {
        "request_id": "REQ-QA-STREAM-1",
        "complaint_id": "CMP-QA-STREAM-1",
        "query": "민원 처리 절차를 알려주세요.",
        "routing_hint": {
            "strategy_id": "topic_general_low_v1",
            "route_key": "general/low",
            "top_k": 1,
            "snippet_max_chars": 400,
            "chunk_policy": "compact",
        },
    }


def test_qa_stream_emits_real_stage_order_and_compatible_done(monkeypatch):
    from app.api.routers import generation as generation_router

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: _StubRetrievalService(),
    )
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
    response = client.post("/api/v1/qa/stream", json=_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-contract-version"] == "qa-v1.1"

    events = _parse_sse(response.text)
    assert [event for event, _ in events] == ["stage", "stage", "stage", "done"]
    assert [data["stage"] for event, data in events if event == "stage"] == [
        "retrieving",
        "grounding",
        "generating",
    ]

    done = events[-1][1]
    assert done["success"] is True
    assert done["request_id"] == _payload()["request_id"]
    assert done["data"]["complaint_id"] == _payload()["complaint_id"]
    assert done["data"]["answer"]
    assert done["search_trace"]["retrieval_done"] is True


def test_qa_stream_emits_existing_error_payload_as_error_event():
    payload = _payload()
    payload["routing_hint"]["strategy_id"] = "topic_general_high_v1"

    client = TestClient(app)
    response = client.post("/api/v1/qa/stream", json=payload)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert [event for event, _ in events] == ["error"]
    assert events[-1][1]["success"] is False
    assert events[-1][1]["error"]["code"] == "ROUTING_STRATEGY_INCONSISTENT"

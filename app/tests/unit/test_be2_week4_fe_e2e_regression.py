from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.generation.context_mapper import map_retrieval_to_qa_context


class _FeFlowStubRetrievalService:
    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        return [
            {
                "rank": 1,
                "doc_id": "DOC-100",
                "score": 0.93,
                "chunk_id": "CASE-100__chunk-0",
                "case_id": "CASE-100",
                "title": "도로 보수 요청",
                "snippet": "강남구 도로 파손으로 차량 통행에 위험이 있어 보수가 필요합니다.",
                "summary": {"observation": "도로 파손", "request": "긴급 보수 요청"},
                "metadata": {
                    "created_at": "2026-04-08T10:00:00+09:00",
                    "category": "road_safety",
                    "region": "서울시 강남구",
                    "entity_labels": ["FACILITY", "HAZARD"],
                },
                "answers_by_admin_unit": {
                    "도로과": "도로 상태 점검 후 보수 공사 일정을 수립합니다.",
                    "교통과": "교통 통제 및 안내 표지 설치를 병행합니다.",
                },
            }
        ]


class _FallbackStubRetrievalService:
    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        return [
            {
                "rank": 1,
                "doc_id": "DOC-200",
                "score": 0.88,
                # case_id/chunk_id/snippet/answers_by_admin_unit intentionally missing
                "summary": {"observation": "가로등 고장", "request": "야간 점검 요청"},
                "metadata": {
                    "created_at": "2026-04-08T11:00:00+09:00",
                    "category": "facility",
                    "region": "서울시 서초구",
                    "entity_labels": ["FACILITY"],
                },
            }
        ]


def _to_qa_input(search_item: dict) -> dict:
    return {
        "doc_id": search_item.get("doc_id"),
        "chunk_id": search_item.get("chunk_id"),
        "case_id": search_item.get("case_id"),
        "snippet": search_item.get("snippet"),
        "score": search_item.get("score"),
    }


def test_be2_fe_search_to_qa_context_flow(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _FeFlowStubRetrievalService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "request_id": "SRCH-2026-0408-001",
            "query": "도로 파손 보수",
            "top_k": 5,
            "filters": {"region": "서울시 강남구"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    first = body["data"]["results"][0]
    assert first["case_id"] == "CASE-100"
    assert first["chunk_id"] == "CASE-100__chunk-0"
    assert isinstance(first["answers_by_admin_unit"], dict)
    assert isinstance(first["department_answers"], dict)
    assert first["answers_by_admin_unit"] == first["department_answers"]

    mapped, trace = map_retrieval_to_qa_context(
        retrieval_results=[_to_qa_input(first)],
        top_k=5,
        policy=None,
    )

    assert len(mapped) == 1
    assert mapped[0]["case_id"] == "CASE-100"
    assert mapped[0]["chunk_id"] == "CASE-100__chunk-0"
    assert mapped[0]["doc_id"] == "DOC-100"
    assert trace["context_dropped_count"] == 0


def test_be2_fe_search_response_fallbacks_are_stable(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _FallbackStubRetrievalService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "request_id": "SRCH-2026-0408-002",
            "query": "가로등 고장",
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    first = response.json()["data"]["results"][0]

    # Fallback contract: FE-required fields still exist.
    assert first["case_id"] == "DOC-200"
    assert first["chunk_id"] == "DOC-200__chunk-0"
    assert first["snippet"] == "가로등 고장"
    assert isinstance(first["summary"], dict)
    assert isinstance(first["answers_by_admin_unit"], dict)
    assert first["answers_by_admin_unit"] == {}

    mapped, trace = map_retrieval_to_qa_context(
        retrieval_results=[_to_qa_input(first)],
        top_k=3,
        policy=None,
    )

    assert len(mapped) == 1
    assert mapped[0]["case_id"] == "DOC-200"
    assert mapped[0]["chunk_id"] == "DOC-200__chunk-0"
    assert trace["context_dropped_count"] == 0

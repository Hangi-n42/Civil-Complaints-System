"""/api/v1/qa 응답의 retrieval 완료 경계 신호(retrieval_done) 검증 (#375).

FE retrieving 단계 종료/BE3 SSE 단계 이벤트가 추정이 아닌 실제 신호를 쓰도록,
정상 경로와 유사사례 없음(no-evidence) fallback 모두 search_trace에
retrieval_done=True 와 ISO-8601 retrieval_completed_at 을 노출해야 한다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.api.main import app


class _StubGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
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
        }


class _FailIfCalledGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        raise AssertionError("no-evidence fallback에서는 generation을 호출하면 안 된다")


class _StubCitationMapper:
    def validate_citations_against_context(self, citations, retrieval_context):
        return True, 0, []


class _StubRetrievalService:
    def __init__(self, results):
        self.results = results

    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        return self.results

    async def _apply_grounding_filter(self, query, results, top_k):
        return results[:top_k]

    def _normalize_query_signals(self, query_signals):
        return query_signals or {}

    def _apply_metadata_soft_rerank(self, results, query_signals):
        return results


_DOC = {
    "doc_id": "DOC-001",
    "chunk_id": "CASE-1__chunk-0",
    "case_id": "CASE-1",
    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
    "score": 0.91,
}


def _assert_retrieval_done(search_trace):
    assert search_trace is not None
    assert search_trace["retrieval_done"] is True
    completed_at = search_trace["retrieval_completed_at"]
    assert isinstance(completed_at, str) and completed_at
    # ISO-8601 파싱이 가능해야 BE3 SSE가 단계 경계로 활용할 수 있다
    datetime.fromisoformat(completed_at)


def test_qa_success_exposes_retrieval_done_boundary(monkeypatch):
    from app.api.routers import generation as generation_router

    monkeypatch.setattr(
        generation_router, "get_retrieval_service", lambda: _StubRetrievalService([_DOC])
    )
    monkeypatch.setattr(
        generation_router, "get_generation_service", lambda: _StubGenerationService()
    )
    monkeypatch.setattr(
        generation_router, "get_citation_mapper", lambda: _StubCitationMapper()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-RETDONE-1",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 200
    _assert_retrieval_done(response.json()["search_trace"])


def test_qa_no_evidence_fallback_exposes_retrieval_done_boundary(monkeypatch):
    from app.api.routers import generation as generation_router

    monkeypatch.setattr(
        generation_router, "get_retrieval_service", lambda: _StubRetrievalService([])
    )
    monkeypatch.setattr(
        generation_router, "get_generation_service", lambda: _FailIfCalledGenerationService()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-RETDONE-2",
            "query": "가로등 고장으로 야간 보행이 불편합니다.",
            "routing_hint": {
                "strategy_id": "topic_general_low_v1",
                "route_key": "general/low",
                "top_k": 1,
                "snippet_max_chars": 400,
                "chunk_policy": "compact",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["citations"] == []
    _assert_retrieval_done(body["search_trace"])

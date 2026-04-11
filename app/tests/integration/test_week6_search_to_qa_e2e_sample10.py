from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app


class _E2EStubRetrievalService:
    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        safe_query = str(query).strip() or "민원"
        case_key = abs(hash(safe_query)) % 10000
        case_id = f"CASE-{case_key:04d}"
        doc_id = f"DOC-{case_key:04d}"
        chunk_id = f"{case_id}__chunk-0"
        return [
            {
                "rank": 1,
                "doc_id": doc_id,
                "score": 0.9,
                "chunk_id": chunk_id,
                "case_id": case_id,
                "title": f"{safe_query[:20]} 관련 사례",
                "snippet": f"{safe_query} 관련 처리 기준과 절차를 안내합니다.",
                "summary": {
                    "observation": safe_query,
                    "request": "민원 처리 안내 요청",
                },
                "metadata": {
                    "created_at": "2026-04-11T10:00:00+09:00",
                    "category": "general",
                    "region": "서울",
                    "entity_labels": ["FACILITY"],
                },
            }
        ]


class _E2EStubGenerationService:
    async def generate_qa(self, query, context, routing_trace=None):
        first = context[0]
        segments = []
        if isinstance(routing_trace, dict):
            raw_segments = routing_trace.get("request_segments") or []
            if isinstance(raw_segments, list):
                segments = [str(item).strip() for item in raw_segments if str(item).strip()]

        return {
            "answer": f"문의하신 내용({query[:30]})에 대해 검토 결과를 안내드립니다.",
            "citations": [
                {
                    "doc_id": first.get("doc_id"),
                    "chunk_id": first.get("chunk_id"),
                    "case_id": first.get("case_id"),
                    "snippet": first.get("snippet"),
                    "source": "civil_db",
                    "relevance_score": 0.91,
                }
            ],
            "limitations": ["현장 확인 전 최종 확정은 어렵습니다."],
            "structured_output": {
                "summary": f"{query[:40]} 관련 민원 요약",
                "action_items": ["담당 부서 검토", "처리 일정 회신"],
                "request_segments": segments,
            },
            "model": "stub-week6-model",
        }


class _E2EStubCitationMapper:
    def validate_citations_against_context(self, citations, retrieval_context):
        return True, 0, []


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "week6_search_qa_e2e_sample10.json"


def _to_qa_search_results(items: list[dict]) -> list[dict]:
    transformed = []
    for item in items:
        transformed.append(
            {
                "doc_id": item.get("doc_id"),
                "chunk_id": item.get("chunk_id"),
                "case_id": item.get("case_id"),
                "snippet": item.get("snippet"),
                "score": item.get("score", 0.0),
            }
        )
    return transformed


def test_week6_search_to_qa_e2e_sample10(monkeypatch):
    from app.api.routers import generation as generation_router
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_retrieval_service",
        lambda: _E2EStubRetrievalService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: _E2EStubRetrievalService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _E2EStubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _E2EStubCitationMapper(),
    )

    cases = json.loads(_fixture_path().read_text(encoding="utf-8"))
    assert len(cases) == 10

    client = TestClient(app)

    for case in cases:
        search_res = client.post(
            "/api/v1/search",
            json={
                "request_id": f"SRCH-{case['complaint_id']}",
                "complaint_id": case["complaint_id"],
                "query": case["query"],
                "top_k": case["top_k"],
            },
        )
        assert search_res.status_code == 200
        search_body = search_res.json()
        assert search_body["success"] is True

        search_data = search_body["data"]
        assert isinstance(search_data["routing_hint"], dict)
        assert isinstance(search_data["routing_trace"], dict)
        assert isinstance(search_data["retrieved_docs"], list)

        qa_res = client.post(
            "/api/v1/qa",
            json={
                "complaint_id": case["complaint_id"],
                "query": case["query"],
                "routing_hint": search_data["routing_hint"],
                "use_search_results": True,
                "search_results": _to_qa_search_results(search_data["retrieved_docs"]),
            },
        )
        assert qa_res.status_code == 200
        qa_body = qa_res.json()
        assert qa_body["success"] is True

        qa_data = qa_body["data"]
        assert qa_data["complaint_id"] == case["complaint_id"]
        assert qa_data["strategy_id"] == search_data["strategy_id"]
        assert qa_data["route_key"] == search_data["route_key"]
        assert isinstance(qa_data["routing_trace"], dict)
        assert set(qa_data["structured_output"].keys()) == {
            "summary",
            "action_items",
            "request_segments",
        }
        assert isinstance(qa_data["answer"], str)
        assert isinstance(qa_data["citations"], list)
        assert isinstance(qa_data["limitations"], list)
        assert set(qa_data["latency_ms"].keys()) == {
            "analyzer",
            "router",
            "retrieval",
            "generation",
        }
        assert set(qa_data["quality_signals"].keys()) == {
            "citation_coverage",
            "hallucination_flag",
            "segment_coverage",
        }
        assert len(qa_data["structured_output"]["request_segments"]) >= 1

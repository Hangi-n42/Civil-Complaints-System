from __future__ import annotations

import asyncio
from typing import Any

from app.generation.prompts.prompt_factory import PromptFactory
from scripts import Be3_run_week6_model_benchmark as benchmark


def test_build_case_query_signals_uses_structured_be1_fields():
    case = {
        "query": "위반건축물 조치 문의",
        "structured": {
            "entity_texts": [{"text": "위반건축물"}],
            "legal_refs": [{"name": "건축법", "law_id": "001823"}],
            "issue_type": [{"name": "단속"}],
            "key_terms": ["이행강제금"],
            "responsible_unit": [{"name": "건축과", "source": "be1_structured"}],
            "urgency": {"level": "보통"},
        },
    }

    signals = benchmark._build_case_query_signals(case)

    assert signals["entity_texts"] == ["위반건축물"]
    assert signals["legal_ref_names"] == ["건축법"]
    assert signals["legal_ref_ids"] == ["001823"]
    assert signals["key_terms"] == ["이행강제금"]
    assert signals["responsible_units"] == ["건축과"]
    assert signals["responsible_units_source"] == "be1_structured"
    assert signals["urgency_level"] == "보통"


def test_prepare_direct_legal_grounding_reuses_generation_service(monkeypatch):
    article = {
        "law_id": "001823",
        "law_name": "건축법",
        "article_no": "제80조",
        "text": "허가권자는 이행강제금을 부과한다.",
    }

    monkeypatch.setattr(
        benchmark.GenerationService,
        "_prepare_legal_context",
        lambda self, query, query_signals=None: (
            [article],
            "unused",
            {"status": "grounded", "error": ""},
        ),
    )
    monkeypatch.setattr(
        benchmark.GenerationService,
        "_build_legal_retry_context",
        lambda self, articles, mode: "\n[법령 조문]\n- 건축법 제80조",
    )

    prompt, articles, status = benchmark._prepare_direct_legal_grounding(
        query="위반건축물 문의",
        query_signals={"legal_ref_ids": ["001823"]},
        prompt="BASE PROMPT",
        mode="default",
    )

    assert "[법령 조문]" in prompt
    assert "FINAL OUTPUT CONTRACT" in prompt
    assert articles == [article]
    assert status == {"status": "grounded", "error": ""}


def test_prompt_factory_autoretrieve_passes_query_signals_to_retrieval():
    class _Retrieval:
        kwargs: dict[str, Any] = {}

        async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
            self.kwargs = kwargs
            return [
                {
                    "doc_id": "DOC-1",
                    "chunk_id": "CHUNK-1",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 근거",
                    "score": 0.9,
                }
            ]

    retrieval = _Retrieval()
    signals = {"legal_ref_ids": ["001823"], "key_terms": ["이행강제금"]}

    _, context, _ = asyncio.run(
        PromptFactory.build_from_dataset_record_autoretrieve(
            record={"query": "위반건축물 문의", "raw_text": "위반건축물 조치 문의"},
            retrieval_service=retrieval,
            query_signals=signals,
        )
    )

    assert retrieval.kwargs["query_signals"] == signals
    assert context[0]["chunk_id"] == "CHUNK-1"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    posts: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, timeout: int):
        self.timeout = timeout

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.posts.append((url, json))
        if url.endswith("/search"):
            return _FakeResponse(
                {
                    "success": True,
                    "request_id": "REQ-1",
                    "data": {
                        "routing_hint": {
                            "strategy_id": "adaptive_v1",
                            "route_key": "general/medium",
                            "top_k": 5,
                            "snippet_max_chars": 1100,
                            "chunk_policy": "balanced",
                        },
                        "retrieved_docs": [
                            {
                                "doc_id": "DOC-1",
                                "chunk_id": "CHUNK-1",
                                "case_id": "CASE-1",
                                "snippet": "검색 근거",
                                "score": 0.9,
                            }
                        ],
                    },
                }
            )
        return _FakeResponse(
            {
                "success": True,
                "data": {
                    "answer": "건축법 제80조에 따라 검토합니다.",
                    "citations": [],
                    "legal_citations": [
                        {
                            "law_name": "건축법",
                            "article_no": "제80조",
                            "verified": True,
                        }
                    ],
                    "legal_citation_warnings": [],
                    "generation_metadata": {
                        "legal_grounding_status": "grounded",
                        "legal_grounding_error": "",
                    },
                },
            }
        )


def test_api_mode_sends_query_signals_and_reads_legal_results(monkeypatch):
    _FakeClient.posts = []
    monkeypatch.setattr(benchmark.httpx, "Client", _FakeClient)
    signals = {
        "legal_ref_names": ["건축법"],
        "legal_ref_ids": ["001823"],
        "key_terms": ["이행강제금"],
    }

    parsed, _, _, context = benchmark._call_search_qa_api(
        api_base_url="http://test",
        query="위반건축물 문의",
        complaint_id="CASE-1",
        top_k=5,
        timeout_sec=10,
        query_signals=signals,
    )

    assert _FakeClient.posts[0][1]["query_signals"] == signals
    assert _FakeClient.posts[1][1]["query_signals"] == signals
    assert parsed["generation_metadata"]["legal_grounding_status"] == "grounded"
    assert parsed["legal_citations"][0]["law_name"] == "건축법"
    assert context[0]["chunk_id"] == "CHUNK-1"

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.generation.prompts.prompt_factory import PromptFactory
from scripts import Be3_run_week6_model_benchmark as benchmark


def test_partial_json_answer_recovery_preserves_current_complaint_text():
    raw = (
        '{"citations":[],"answer":"도서관 단기근로 채용 면접의 공정성을 '
        '확인할 필요가 있습니다. 향후 채용 절차'
    )

    recovered = benchmark._recover_minimal_response(raw)

    assert "도서관 단기근로 채용" in recovered["answer"]
    assert "채용 절차" in recovered["answer"]
    assert recovered["limitations"] == "response_format_recovered"


def test_partial_json_answer_recovery_decodes_escaped_newlines():
    raw = '{"answer":"첫 문장입니다.\\n두 번째 문장입니다.","citations":['

    answer = benchmark._extract_partial_json_string_field(raw, "answer")

    assert answer == "첫 문장입니다.\n두 번째 문장입니다."


def test_missing_answer_never_uses_retrieval_snippet_as_current_reply():
    context = [
        {
            "chunk_id": "CASE-OTHER__chunk-0",
            "case_id": "CASE-OTHER",
            "snippet": "독서 동아리 공간이 부족해 별도 교실을 배정했습니다.",
        }
    ]

    answer = benchmark._derive_non_empty_answer(
        parsed={"answer": ""},
        raw_response='{"citations":[],"answer":',
        context=context,
    )

    assert "독서 동아리 공간" not in answer
    assert "구체적인 검토 내용을 충분히 구성하지 못했습니다" in answer


def test_benchmark_raw_schema_and_citation_support_are_strict():
    context = [
        {
            "chunk_id": "CASE-1__chunk-0",
            "case_id": "CASE-1",
            "snippet": "도로 폭이 좁아 현재 설치는 어렵습니다.",
        }
    ]
    payload = {
        "citations": [
            {
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "도로 폭이 좁아",
                "relevance_score": 0.9,
            }
        ],
        "answer": "도로 폭이 좁아 설치가 어렵습니다.",
        "limitations": ["현장 확인 필요"],
        "structured_output": {
            "summary": "설치 제한",
            "action_items": ["현장 확인", "검토 결과 안내"],
            "request_segments": ["설치 요청"],
        },
    }

    schema_ok, errors = benchmark._inspect_raw_schema(
        json.dumps(payload, ensure_ascii=False)
    )
    support = benchmark._citation_match_rate(payload["citations"], context)

    assert schema_ok is True
    assert errors == []
    assert support == 1.0
    assert benchmark._passes_integrity_gate(
        payload["answer"],
        support,
        raw_schema_compliant=schema_ok,
    )

    payload["citations"][0]["snippet"] = "검색 근거에 없는 문장"
    assert benchmark._citation_match_rate(payload["citations"], context) == 0.0


def test_benchmark_raw_schema_rejects_repaired_only_payload():
    schema_ok, errors = benchmark._inspect_raw_schema(
        '{"answer":"답변","citations":[],"limitations":"제한"}'
    )

    assert schema_ok is False
    assert errors


def test_build_case_query_signals_uses_structured_be1_fields():
    case = {
        "query": "위반건축물 조치 문의",
        "structured": {
            "entity_texts": [{"text": "위반건축물"}],
            "legal_refs": [{"name": "건축법", "law_id": "001823"}],
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
    assert retrieval.kwargs["grounding_filter"] is True
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

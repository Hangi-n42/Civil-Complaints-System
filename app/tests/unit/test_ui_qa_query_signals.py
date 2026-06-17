from __future__ import annotations

from types import SimpleNamespace

from app.ui.services import search_service
from app.ui.services.search_service import (
    build_qa_query_signals,
    run_qa_via_api,
    search_cases_via_api_with_filters,
)
from app.ui.services.ui_case_adapter import to_ui_queue_case


def _structured_case():
    return {
        "case_id": "CASE-LEGAL-1",
        "raw_text": "무허가 가설건축물 이행강제금 문의",
        "structured": {
            "observation": {"text": "무허가 가설건축물", "confidence": 0.9},
            "result": {"text": "이행강제금 문의", "confidence": 0.9},
            "request": {"text": "처리 기준 안내", "confidence": 0.9},
            "context": {"text": "건축 행정", "confidence": 0.9},
            "entities": [{"label": "FACILITY", "text": "가설건축물"}],
            "entity_texts": [{"text": "가설건축물"}],
            "legal_refs": [{"name": "건축법", "law_id": "001823"}],
            "key_terms": ["가설건축물", "이행강제금"],
            "responsible_unit": [{"name": "건축과", "source": "be1_structured"}],
            "urgency": {"level": "높음"},
        },
    }


def test_ui_case_adapter_preserves_be1_generation_signals():
    case = to_ui_queue_case(_structured_case(), 1)
    structured = case["structured"]

    assert structured["legal_refs"] == [{"name": "건축법", "law_id": "001823"}]
    assert structured["key_terms"] == ["가설건축물", "이행강제금"]
    assert structured["responsible_unit"] == [{"name": "건축과", "source": "be1_structured"}]
    assert structured["urgency"] == {"level": "높음"}
    assert case["civil_category"]["primary"] == "도시·건축·주택"
    assert case["category_display"].startswith("도시·건축·주택 >")


def test_build_qa_query_signals_maps_be1_contract():
    signals = build_qa_query_signals(_structured_case())

    assert signals == {
        "entity_texts": ["가설건축물"],
        "legal_ref_names": ["건축법"],
        "legal_ref_ids": ["001823"],
        "key_terms": ["가설건축물", "이행강제금"],
        "responsible_units": ["건축과"],
        "responsible_units_source": "be1_structured",
        "urgency_level": "높음",
    }


def test_run_qa_via_api_sends_required_contract(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        search_service,
        "st",
        SimpleNamespace(session_state={"api_base_url": "http://test"}),
    )

    def fake_post(base_url, path, payload, timeout):
        captured.update(payload)
        return {"success": True, "data": {"answer": "답변", "citations": []}}, 200, None

    monkeypatch.setattr(search_service, "post_json", fake_post)
    result, error = run_qa_via_api(
        complaint_id="CASE-LEGAL-1",
        query="질의",
        routing_hint={
            "strategy_id": "topic_general_medium_v1",
            "route_key": "general/medium",
            "top_k": 5,
            "snippet_max_chars": 1100,
            "chunk_policy": "balanced",
        },
        top_k=5,
        use_search_results=False,
        search_results=[],
        filters=None,
        query_signals={"legal_ref_ids": ["001823"]},
    )

    assert error is None
    assert result["success"] is True
    assert captured["complaint_id"] == "CASE-LEGAL-1"
    assert captured["routing_hint"]["route_key"] == "general/medium"
    assert captured["query_signals"]["legal_ref_ids"] == ["001823"]


def test_search_api_sends_signals_and_preserves_routing_contract(monkeypatch):
    session = {
        "api_base_url": "http://test",
        "selected_case_id": "CASE-LEGAL-1",
        "mock_cases": [_structured_case()],
    }
    captured = {}
    monkeypatch.setattr(search_service, "st", SimpleNamespace(session_state=session))

    def fake_post(base_url, path, payload, timeout):
        captured.update(payload)
        return {
            "success": True,
            "data": {
                "complaint_id": "CASE-LEGAL-1",
                "routing_hint": {
                    "strategy_id": "topic_general_high_v1",
                    "route_key": "general/high",
                    "top_k": 5,
                    "snippet_max_chars": 1100,
                    "chunk_policy": "expanded",
                },
                "routing_trace": {"topic_type": "general"},
                "results": [],
            },
        }, 200, None

    monkeypatch.setattr(search_service, "post_json", fake_post)
    results, error = search_cases_via_api_with_filters(
        query="법령 문의",
        top_k=5,
        date_range=None,
        region="전체",
        category="전체",
        entity_labels=[],
    )

    assert results == []
    assert error is None
    assert captured["complaint_id"] == "CASE-LEGAL-1"
    assert captured["query_signals"]["legal_ref_ids"] == ["001823"]
    assert session["last_search_contract"]["routing_hint"]["route_key"] == "general/high"

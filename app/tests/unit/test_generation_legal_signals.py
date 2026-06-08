from __future__ import annotations

from app.generation.service import GenerationService


def test_prepare_legal_context_prefers_be1_signals(monkeypatch):
    service = GenerationService()
    captured = {}

    def fake_retrieve(query, legal_refs, key_terms=None, top_k=5, store=None):
        captured["query"] = query
        captured["legal_refs"] = legal_refs
        captured["key_terms"] = key_terms
        return [
            {
                "law_name": "건축법",
                "article_no": "제80조",
                "law_id": "001823",
                "text": "제80조(이행강제금) 허가권자는 이행강제금을 부과한다.",
            }
        ]

    monkeypatch.setattr(
        "app.generation.citation.legal_citation.retrieve_legal_context",
        fake_retrieve,
    )
    monkeypatch.setattr(
        "app.structuring.legal_dictionary.get_legal_ref_matcher",
        lambda: (_ for _ in ()).throw(AssertionError("query rematch must not run")),
    )

    articles, prompt, status = service._prepare_legal_context(
        "무허가 가설건축물 이행강제금",
        query_signals={
            "legal_ref_names": ["건축법"],
            "legal_ref_ids": ["001823"],
            "key_terms": ["가설건축물", "이행강제금"],
        },
    )

    assert len(articles) == 1
    assert captured["legal_refs"] == [
        {
            "law_id": "001823",
            "name": "건축법",
            "source": "be1_query_signals",
        }
    ]
    assert captured["key_terms"] == ["가설건축물", "이행강제금"]
    assert "[법령 조문]" in prompt
    assert status == {"status": "grounded", "error": ""}


def test_prepare_legal_context_reports_error(monkeypatch):
    service = GenerationService()
    monkeypatch.setattr(
        "app.structuring.legal_dictionary.get_legal_ref_matcher",
        lambda: (_ for _ in ()).throw(RuntimeError("law store unavailable")),
    )

    articles, prompt, status = service._prepare_legal_context("법령 문의")

    assert articles == []
    assert prompt == ""
    assert status["status"] == "error"
    assert status["error"] == "RuntimeError: legal grounding unavailable"


def test_urgency_context_only_strengthens_high_or_emergency_signals():
    service = GenerationService()

    assert service._build_urgency_context({"urgency_level": "보통"}) == ""

    prompt = service._build_urgency_context(
        {
            "urgency_level": "긴급",
            "responsible_units": ["안전총괄과"],
        }
    )

    assert "긴급도 후보: 긴급" in prompt
    assert "안전총괄과" in prompt
    assert "112/119" in prompt
    assert "즉시 위험 근거가 있을 때만" in prompt

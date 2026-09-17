"""공유 함수로 옮긴 표시·마스킹 로직의 기존 경계 동작."""

from copy import deepcopy

from app.complaint_intelligence.repository import _mask_strings as mask_memory
from app.complaint_intelligence.sqlite_repository import _mask_strings as mask_sqlite
from app.retrieval.service import RetrievalService
from app.retrieval.vectorstores.chroma_store import ChromaVectorStore
from app.ui.services.ui_case_adapter import _format_received_at, _span_to_evidence_text


def test_snippet_preserves_single_line_and_multiline_output():
    cases = [
        ("", 120, ""),
        ("  민원\t내용\n\n 확인  ", 120, "민원 내용 확인"),
        ("가" * 100 + "나" * 100, 60, "가" * 25 + " ... " + "나" * 30),
        ("가" * 100 + "\n" + "나" * 100, 60, "가" * 25 + "... | " + "나" * 25 + "..."),
        ("변경하지 않을 기존 짧은 제한값", 0, "변경하지 않을 기존 짧은 제한값 ... 변경하지 않을 기존 짧은 제한값"),
    ]
    for cls in (RetrievalService, ChromaVectorStore):
        instance = object.__new__(cls)
        for text, limit, expected in cases:
            assert instance._build_snippet(text, max_length=limit) == expected


def test_repository_masking_preserves_nested_data_and_input():
    payload = {"contact": ["010-1234-5678", {"email": "test@example.com"}], "count": 3, "active": True, "empty": None}
    original = deepcopy(payload)
    expected = {"contact": ["[REDACTED:PHONE]", {"email": "[REDACTED:EMAIL]"}], "count": 3, "active": True, "empty": None}
    assert mask_memory(payload) == mask_sqlite(payload) == expected
    assert payload == original


def test_ui_date_and_evidence_preserve_invalid_value_fallbacks():
    assert _format_received_at("2026-09-17T09:30:00Z") == "2026-09-17 09:30"
    assert _format_received_at("invalid") == "invalid"
    assert _format_received_at(None) == "-"
    for span, expected in [("직접 근거", "직접 근거"), ([0, 2], "민원"), ((-1, 2), "-1:2"), ([2, 99], "2:99"), ([0, "2"], ""), (None, "")]:
        assert _span_to_evidence_text("민원 내용", span) == expected


def test_similar_case_renderers_preserve_escaping_and_default_status():
    from app.ui.components.search_ui import (
        render_similar_cases_collapsible,
        render_similar_cases_table,
    )

    rows = [{"case_id": "<민원&\"'>", "status": "  ", "complaint": "<script>"}]
    for render in (render_similar_cases_table, render_similar_cases_collapsible):
        markup = render(rows, return_html=True)
        assert "&lt;민원&amp;\"'&gt;" in markup
        assert "PENDING" in markup
        assert "<script>" not in markup


def test_response_contract_keeps_every_type_check_and_sorted_errors():
    from app.generation.normalization.response_normalizer import (
        REQUIRED_KEYS,
        normalize_response,
        validate_unified_contract,
    )

    payload = normalize_response({})
    assert validate_unified_contract(payload) == []
    for key in REQUIRED_KEYS - {"answer"}:
        invalid = dict(payload, **{key: "wrong type"})
        assert validate_unified_contract(invalid) == [key]
    assert validate_unified_contract({}) == sorted(REQUIRED_KEYS)

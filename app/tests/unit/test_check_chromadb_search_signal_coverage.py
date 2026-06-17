from __future__ import annotations

from scripts.check_chromadb_search_signal_coverage import analyze_metadatas, render_markdown


def test_analyze_metadatas_counts_search_signal_coverage_without_sensitive_values():
    report = analyze_metadatas(
        [
            {
                "entity_texts": "가로등|가로등",
                "legal_ref_names": "도로법",
                "legal_ref_ids": "001234",
                "key_terms": "가로등|보수",
                "responsible_units": "도로관리과",
                "responsible_units_source": "be1_structured",
                "urgency_level": "보통",
            },
            {
                "entity_texts": "",
                "legal_ref_names": "도로법",
                "legal_ref_ids": "",
                "key_terms": "",
                "responsible_units": "국토교통부",
                "responsible_units_source": "category_source_fallback",
                "urgency_level": "낮음",
            },
            {},
        ],
        total_count=3,
        top_n=3,
    )

    fields = report["fields"]
    assert fields["entity_texts"]["present_count"] == 1
    assert fields["entity_texts"]["empty_count"] == 2
    assert fields["entity_texts"]["coverage_ratio"] == 0.333333
    assert "top_values" not in fields["entity_texts"]
    assert fields["entity_texts"]["top_value_hashes"][0]["count"] == 1

    assert fields["key_terms"]["present_count"] == 1
    assert "top_values" not in fields["key_terms"]
    assert fields["key_terms"]["unique_value_count"] == 2

    assert fields["legal_ref_names"]["present_count"] == 2
    assert fields["legal_ref_names"]["top_values"][0] == {"value": "도로법", "count": 2}
    assert fields["responsible_units"]["present_count"] == 2
    assert fields["responsible_units_source"]["present_count"] == 2


def test_render_markdown_includes_korean_summary_and_redaction_note():
    report = analyze_metadatas(
        [
            {
                "entity_texts": "가로등",
                "key_terms": "가로등|보수",
                "responsible_units": "도로관리과",
                "responsible_units_source": "be1_structured",
            }
        ],
        total_count=10,
        top_n=2,
    )

    markdown = render_markdown(report, collection="civil_cases_v1", persist_dir="data/chroma_db")

    assert "# ChromaDB 검색 신호 metadata 적재율 점검" in markdown
    assert "| `responsible_units` | 1 | 0 | 100.00% | 1 |" in markdown
    assert "| `responsible_units_source` | 1 | 0 | 100.00% | 1 |" in markdown
    assert "원문 값을 숨기고 해시 prefix만 표시" in markdown
    assert "`도로관리과`" in markdown
    assert "`가로등`" not in markdown

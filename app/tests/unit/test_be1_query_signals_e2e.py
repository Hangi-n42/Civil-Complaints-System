from __future__ import annotations

from scripts.e2e_be1_query_signals_search_qa import (
    build_summary,
    build_generation_warnings,
    compare_rankings,
    extract_query_signals,
    normalize_generation_metadata,
    overlap_by_field,
    render_markdown,
)


def test_extract_query_signals_from_be1_structured_output():
    structured = {
        "entity_texts": [{"text": "지게차"}, {"text": "지게차"}],
        "legal_refs": [
            {"name": "건설기계관리법", "law_id": "001234"},
            {"name": "건설기계관리법", "law_id": "001234"},
        ],
        "key_terms": ["지게차", " 면허 ", "지게차"],
        "responsible_unit": [{"name": "교통국", "source": "be1_structured"}],
        "urgency": {"level": "높음"},
    }

    signals = extract_query_signals(structured)

    assert signals == {
        "entity_texts": ["지게차"],
        "legal_ref_names": ["건설기계관리법"],
        "legal_ref_ids": ["001234"],
        "key_terms": ["지게차", "면허"],
        "responsible_units": ["교통국"],
        "responsible_units_source": "be1_structured",
        "urgency_level": "높음",
    }


def test_overlap_by_field_accepts_pipe_encoded_metadata():
    query_signals = {
        "entity_texts": ["가로등"],
        "legal_ref_names": [],
        "legal_ref_ids": ["001706"],
        "key_terms": ["조명", "점검"],
        "responsible_units": [],
    }
    metadata = {
        "entity_texts": "가로등|공원",
        "legal_ref_ids": ["001706"],
        "key_terms": "점검|야간",
    }

    overlaps = overlap_by_field(query_signals, metadata)

    assert overlaps["entity_texts"]["values"] == ["가로등"]
    assert overlaps["legal_ref_ids"]["count"] == 1
    assert overlaps["key_terms"]["values"] == ["점검"]


def test_compare_rankings_reports_top1_change_and_rank_delta():
    baseline = [
        {"chunk_id": "A", "case_id": "A"},
        {"chunk_id": "B", "case_id": "B"},
    ]
    with_signals = [
        {"chunk_id": "B", "case_id": "B"},
        {"chunk_id": "A", "case_id": "A"},
        {"chunk_id": "C", "case_id": "C"},
    ]

    comparison = compare_rankings(baseline, with_signals)

    assert comparison["top1_changed"] is True
    assert comparison["baseline_top1"] == "A"
    assert comparison["with_signals_top1"] == "B"
    assert comparison["new_in_with_signals_top_k"] == ["C"]
    assert comparison["rank_changes"][0]["rank_delta"] == 1
    assert comparison["moved_up_count"] == 1


def test_generation_metadata_defaults_and_warnings():
    metadata = normalize_generation_metadata(
        {
            "fallback_used": True,
            "parse_retry_count": "2",
            "generation_mode": "fast_fallback",
            "legal_grounding_status": "grounded",
            "legal_grounding_error": "",
        }
    )

    warnings = build_generation_warnings(
        answer_chars=0,
        generation_metadata=metadata,
    )

    assert metadata == {
        "fallback_used": True,
        "parse_retry_count": 2,
        "generation_mode": "fast_fallback",
        "legal_grounding_status": "grounded",
        "legal_grounding_error": "",
    }
    assert warnings == ["empty_answer", "fallback_used"]


def test_build_summary_and_markdown_are_korean_report_ready():
    report = {
        "generated_at": "2026-06-08T00:00:00+00:00",
        "args": {
            "structuring_mode": "deterministic",
            "strategy": "hybrid",
            "grounding_filter": False,
            "run_generation": True,
        },
        "records": [
            {
                "status": "ok",
                "case_id": "CASE-1",
                "signal_counts": {
                    "entity_texts": 1,
                    "legal_ref_names": 0,
                    "legal_ref_ids": 0,
                    "key_terms": 2,
                    "responsible_units": 0,
                },
                "with_signals_top": [{"metadata_overlap_total": 2}],
                "comparison": {
                    "top1_changed": True,
                    "baseline_empty": False,
                    "with_signals_empty": False,
                    "moved_up_count": 1,
                    "baseline_top1": "A",
                    "with_signals_top1": "B",
                },
                "generation": {
                    "status": "warning",
                    "warnings": ["empty_answer"],
                    "answer_chars": 0,
                    "citation_count": 1,
                    "generation_metadata": {
                        "fallback_used": False,
                        "parse_retry_count": 1,
                        "generation_mode": "force_json",
                        "legal_grounding_status": "no_candidates",
                        "legal_grounding_error": "",
                    },
                },
            }
        ],
    }
    report["summary"] = build_summary(report["records"])

    markdown = render_markdown(report)

    assert report["summary"]["successful_records"] == 1
    assert report["summary"]["top1_changed_count"] == 1
    assert report["summary"]["generation_warning_count"] == 1
    assert report["summary"]["generation_empty_answer_count"] == 1
    assert report["summary"]["generation_mode_counts"] == {"force_json": 1}
    assert report["summary"]["generation_legal_grounding_status_counts"] == {"no_candidates": 1}
    assert "BE1 query_signals 검색 E2E 검증 요약" in markdown
    assert "해석 주의" in markdown
    assert "답변 생성 관측" in markdown
    assert "empty_answer" in markdown
    assert "법령 grounding 상태 분포" in markdown

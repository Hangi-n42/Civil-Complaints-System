from __future__ import annotations

from scripts.build_index import _build_api_case_record


def test_build_api_case_record_preserves_be1_search_signals():
    normalized = {
        "submitted_at": "2026-06-10T09:00:00+09:00",
        "region": "부산광역시",
    }
    structured = {
        "case_id": "CASE-SIGNAL-001",
        "source": "aihub_71852",
        "created_at": "2026-06-10T09:00:00+09:00",
        "category": "교통",
        "region": "부산광역시",
        "structured_by": "constrained",
        "validation": {"is_valid": True, "errors": []},
        "observation": {"text": "버스가 자주 지연됩니다.", "confidence": 0.9},
        "result": {"text": "출근 시간이 늦어집니다.", "confidence": 0.8},
        "request": {"request": "배차 간격을 조정해 주세요.", "confidence": 0.9},
        "context": {"text": "평일 오전 출근 시간", "confidence": 0.7},
        "entities": [{"label": "FACILITY", "text": "버스"}],
        "entity_texts": [{"text": "버스", "confidence": 0.95, "evidence": ["버스"]}],
        "issue_type": [{"name": "교통/운행", "confidence": 0.82}],
        "legal_refs": [{"name": "여객자동차 운수사업법", "law_id": "001", "confidence": 0.7}],
        "key_terms": ["버스", "배차", "지연"],
        "responsible_unit": [
            {
                "name": "대중교통과",
                "confidence": 0.74,
                "evidence": ["버스", "배차"],
                "source": "be1_structured",
            }
        ],
        "urgency": {"level": "보통", "score": 0.4, "evidence": []},
    }

    record = _build_api_case_record(normalized, structured)

    assert record["entity_texts"] == structured["entity_texts"]
    assert record["issue_type"] == structured["issue_type"]
    assert record["legal_refs"] == structured["legal_refs"]
    assert record["key_terms"] == structured["key_terms"]
    assert record["responsible_unit"] == structured["responsible_unit"]
    assert record["urgency"] == structured["urgency"]
    assert record["metadata"]["structured_by"] == "constrained"


def test_build_api_case_record_falls_back_to_raw_text_when_structured_text_empty():
    normalized = {
        "text": "민원 원문 fallback",
        "submitted_at": "2026-06-10T09:00:00+09:00",
        "region": "부산광역시",
    }
    structured = {
        "case_id": "CASE-EMPTY-STRUCTURED-001",
        "source": "aihub",
        "created_at": "2026-06-10T09:00:00+09:00",
        "category": "도로",
        "region": "부산광역시",
        "raw_text": "마스킹된 원문 fallback",
        "structured_by": "fallback",
        "validation": {"is_valid": False, "errors": ["empty_field:request"]},
        "observation": {"text": ""},
        "result": {"text": ""},
        "request": {"request": ""},
        "context": {"text": ""},
        "entities": [],
    }

    record = _build_api_case_record(normalized, structured)

    assert record["text"] == "마스킹된 원문 fallback"
    assert record["structured_text"] == {}
    assert record["metadata"]["index_text_source"] == "raw_text_fallback_empty_structured"
    assert record["metadata"]["empty_structured_text_fallback"] is True

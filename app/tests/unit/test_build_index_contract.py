from __future__ import annotations

import json
import logging

from scripts.build_index import _build_api_case_record, _save_structured_outputs


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
        "civil_category": {
            "primary": "교통·물류",
            "secondary": "버스",
            "secondary_candidates": ["버스", "대중교통"],
            "confidence": 0.84,
            "evidence": ["대중교통과"],
            "source": "responsible_unit",
        },
        "urgency": {"level": "보통", "score": 0.4, "evidence": []},
    }

    record = _build_api_case_record(normalized, structured)

    assert record["entity_texts"] == structured["entity_texts"]
    assert "issue_type" not in record
    assert record["legal_refs"] == structured["legal_refs"]
    assert record["key_terms"] == structured["key_terms"]
    assert record["responsible_unit"] == structured["responsible_unit"]
    assert record["civil_category"] == structured["civil_category"]
    assert record["metadata"]["civil_category_primary"] == "교통·물류"
    assert record["metadata"]["civil_category_secondary"] == "버스"
    assert record["urgency"] == structured["urgency"]
    assert record["metadata"]["structured_by"] == "constrained"


def test_build_api_case_record_uses_answer_included_search_text_for_index_text():
    normalized = {
        "submitted_at": "2026-06-10T09:00:00+09:00",
        "region": "부산광역시",
        "search_text": "도로 파손 신고\n포트홀이 있습니다.\n담당 부서에 전달했습니다.",
    }
    structured = {
        "case_id": "CASE-SEARCH-TEXT-001",
        "source": "aihub",
        "created_at": "2026-06-10T09:00:00+09:00",
        "category": "도로",
        "region": "부산광역시",
        "structured_by": "constrained",
        "validation": {"is_valid": True, "errors": []},
        "observation": {"text": "도로에 포트홀이 있습니다.", "confidence": 0.9},
        "result": {"text": "", "confidence": 0.0},
        "request": {"request": "보수를 요청합니다.", "confidence": 0.9},
        "context": {"text": "", "confidence": 0.0},
        "entities": [],
    }

    record = _build_api_case_record(normalized, structured)

    assert record["text"] == normalized["search_text"]
    assert record["structured_text"] == {
        "observation": "도로에 포트홀이 있습니다.",
        "request": "보수를 요청합니다.",
    }
    assert record["metadata"]["index_text_source"] == "search_text_with_answer"
    assert record["metadata"]["empty_structured_text_fallback"] is False


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


def test_save_structured_outputs_writes_default_artifacts(tmp_path):
    structured_rows = [
        {
            "case_id": "CASE-STRUCTURED-001",
            "observation": {"text": "도로가 파손되었습니다."},
            "result": {"text": "통행 불편이 있습니다."},
            "request": {"text": "보수를 요청합니다."},
            "context": {"text": "출근 시간대"},
            "validation": {"is_valid": True},
        }
    ]

    paths = _save_structured_outputs(
        input_dir="data/raw_data",
        collection_name="civil_cases_v1",
        structured_rows=structured_rows,
        failures=[],
        logger=logging.getLogger("test_build_index_contract"),
        output_dir=tmp_path,
    )

    assert paths["output"].exists()
    assert paths["summary"].exists()
    assert paths["failures"].exists()
    assert json.loads(paths["output"].read_text(encoding="utf-8")) == structured_rows
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["structured_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["schema_pass_rate"] == 1.0
    assert json.loads(paths["failures"].read_text(encoding="utf-8")) == []

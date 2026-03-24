from __future__ import annotations

from app.retrieval.service import RetrievalService


def test_normalize_record_maps_legacy_aliases_to_week2_contract():
    service = RetrievalService()
    record = {
        "id": "legacy-001",
        "submitted_at": "2026-03-20",
        "metadata": {"source": "aihub_71852", "region": "서울시 강남구"},
        "observation": {"text": "가로등 점멸"},
        "result": {"text": "야간 통행 위험"},
        "request": {"text": "점검 요청"},
        "context": {"text": "최근 2주"},
        "entities": [{"label": "facility", "text": "가로등"}],
    }

    normalized = service._normalize_record(record, index=0)

    assert normalized["case_id"] == "CASE-LEGACY-001"
    assert normalized["source"] == "aihub_71852"
    assert normalized["region"] == "서울시 강남구"
    assert normalized["chunk_id"] == "CASE-LEGACY-001__chunk-0"
    assert normalized["created_at"].startswith("2026-03-20T00:00:00")
    assert normalized["created_at"].endswith("+09:00")
    assert normalized["metadata"]["pipeline_version"] == "week2"


def test_normalize_record_enforces_chunk_id_pattern_and_entity_alignment():
    service = RetrievalService()
    record = {
        "case_id": "CASE-2026-000123",
        "created_at": "2026-03-21T09:10:00+09:00",
        "source": "civil_portal",
        "chunk_id": "INVALID-CHUNK-ID",
        "chunk_index": 7,
        "text": "테스트 본문",
        "entities": [
            {"label": "FACILITY", "text": "가로등"},
            {"label": "TIME", "text": "저녁 8시"},
            {"label": "HAZARD"},
            {"text": "강남구"},
            {"label": "FACILITY", "text": "가로등"},
        ],
    }

    normalized = service._normalize_record(record, index=5)

    assert normalized["chunk_id"] == "CASE-2026-000123__chunk-7"
    assert normalized["entity_labels"] == ["FACILITY", "TIME"]
    assert normalized["entity_texts"] == ["가로등", "저녁 8시"]
    assert len(normalized["entity_labels"]) == len(normalized["entity_texts"])

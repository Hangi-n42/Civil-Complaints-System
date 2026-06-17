from __future__ import annotations

from app.retrieval.service import RetrievalService
from app.retrieval.vectorstores.chroma_store import ChromaVectorStore


def _be1_structured_record():
    return {
        "case_id": "CASE-2026-000301",
        "created_at": "2026-03-21T10:00:00+09:00",
        "source": "civil_portal",
        "category": "교통",
        "region": "부산광역시",
        "text": "3톤 미만 지게차 조종 면허 문의입니다.",
        "entities": [{"label": "FACILITY", "text": "3톤 미만 지게차"}],
        "entity_texts": [
            {"text": "지게차", "confidence": 0.92, "evidence": ["3톤 미만 지게차"]},
            {"text": "지게차", "confidence": 0.88, "evidence": ["지게차"]},
        ],
        "legal_refs": [
            {"name": "건설기계관리법", "law_id": "000239", "confidence": 0.86},
            {"name": "건설기계관리법", "law_id": "000239", "confidence": 0.8},
        ],
        "key_terms": ["지게차", "면허", "지게차"],
        "responsible_unit": [{"name": "교통국", "confidence": 0.7, "source": "be1_structured"}],
        "civil_category": {
            "primary": "교통·물류",
            "secondary": "도로시설물",
            "source": "responsible_unit",
        },
        "urgency": {"level": "보통", "confidence": 0.62},
    }


def test_normalize_record_preserves_be1_search_signal_metadata():
    service = RetrievalService()

    normalized = service._normalize_record(_be1_structured_record(), index=0)

    assert normalized["entity_texts"] == ["3톤 미만 지게차"]
    assert normalized["search_entity_texts"] == ["지게차"]
    assert normalized["legal_ref_names"] == ["건설기계관리법"]
    assert normalized["legal_ref_ids"] == ["000239"]
    assert "issue_types" not in normalized
    assert normalized["key_terms"] == ["지게차", "면허"]
    assert normalized["responsible_units"] == ["교통국"]
    assert normalized["responsible_units_source"] == "be1_structured"
    assert normalized["civil_category_primary"] == "교통·물류"
    assert normalized["civil_category_secondary"] == "도로시설물"
    assert normalized["civil_category_source"] == "responsible_unit"
    assert normalized["urgency_level"] == "보통"


def test_chroma_metadata_flattens_be1_search_signals_for_storage():
    service = RetrievalService()
    store = ChromaVectorStore(
        persist_directory="/tmp/retrieval-test-chroma",
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )
    normalized = service._normalize_record(_be1_structured_record(), index=0)

    metadata = store._build_metadata(normalized)

    assert metadata["entity_texts"] == "지게차"
    assert metadata["legal_ref_names"] == "건설기계관리법"
    assert metadata["legal_ref_ids"] == "000239"
    assert "issue_types" not in metadata
    assert metadata["key_terms"] == "지게차|면허"
    assert metadata["responsible_units"] == "교통국"
    assert metadata["responsible_units_source"] == "be1_structured"
    assert metadata["civil_category_primary"] == "교통·물류"
    assert metadata["civil_category_secondary"] == "도로시설물"
    assert metadata["civil_category_source"] == "responsible_unit"
    assert metadata["urgency_level"] == "보통"


def test_chroma_query_restores_search_signal_metadata_as_lists(monkeypatch):
    service = RetrievalService()
    store = ChromaVectorStore(
        persist_directory="/tmp/retrieval-test-chroma",
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )
    normalized = service._normalize_record(_be1_structured_record(), index=0)
    metadata = store._build_metadata(normalized)

    class _FakeCollection:
        def query(self, **kwargs):
            return {
                "ids": [["CASE-2026-000301::CASE-2026-000301__chunk-0"]],
                "documents": [[normalized["chunk_text"]]],
                "metadatas": [[metadata]],
                "distances": [[0.08]],
            }

    monkeypatch.setattr(store, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(store, "_get_collection", lambda collection_name: _FakeCollection())

    results = store.query(collection_name="civil_cases_v1", query="지게차 면허", top_k=1)

    assert len(results) == 1
    result_metadata = results[0]["metadata"]
    assert result_metadata["entity_texts"] == ["지게차"]
    assert result_metadata["legal_ref_names"] == ["건설기계관리법"]
    assert result_metadata["legal_ref_ids"] == ["000239"]
    assert "issue_types" not in result_metadata
    assert result_metadata["key_terms"] == ["지게차", "면허"]
    assert result_metadata["responsible_units"] == ["교통국"]
    assert result_metadata["responsible_units_source"] == "be1_structured"
    assert result_metadata["civil_category_primary"] == "교통·물류"
    assert result_metadata["civil_category_secondary"] == "도로시설물"
    assert result_metadata["civil_category_source"] == "responsible_unit"
    assert result_metadata["urgency_level"] == "보통"


def test_normalize_record_preserves_category_source_fallback_origin():
    service = RetrievalService()
    record = _be1_structured_record()
    record.pop("responsible_unit")
    record["responsible_units"] = ["교통국"]
    record["responsible_units_source"] = "category_source_fallback"

    normalized = service._normalize_record(record, index=0)

    assert normalized["responsible_units"] == ["교통국"]
    assert normalized["responsible_units_source"] == "category_source_fallback"

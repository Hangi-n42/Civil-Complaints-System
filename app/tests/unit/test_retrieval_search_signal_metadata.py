from __future__ import annotations

from app.retrieval.service import RetrievalService
from app.retrieval.search.hybrid import HybridRetriever
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


def test_normalize_record_uses_stable_default_chunk_id():
    service = RetrievalService()
    record = _be1_structured_record()

    first = service._normalize_record(record, index=3)
    second = service._normalize_record(record, index=17)

    assert first["chunk_id"] == "CASE-2026-000301__chunk-0"
    assert second["chunk_id"] == "CASE-2026-000301__chunk-0"


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
    assert metadata["answer"] == ""


def test_chroma_metadata_preserves_policy_qna_identity():
    service = RetrievalService()
    store = ChromaVectorStore(
        persist_directory="/tmp/retrieval-test-chroma",
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )
    record = _be1_structured_record()
    record["case_id"] = "CASE-POLICY-175436"
    record["source_id"] = "175436"
    record["content_type"] = "policy_qna"
    record["document_type"] = "policy_qna"
    record["metadata"] = {
        "index_text_source": "search_text_with_answer",
        "structured_by": "policy_qna_repair",
        "is_valid": True,
        "answer": "온라인 신청 방법을 안내합니다.",
    }
    normalized = service._normalize_record(record, index=0)

    metadata = store._build_metadata(normalized)

    assert metadata["content_type"] == "policy_qna"
    assert metadata["document_type"] == "policy_qna"
    assert metadata["source_id"] == "175436"
    assert metadata["index_text_source"] == "search_text_with_answer"
    assert metadata["structured_by"] == "policy_qna_repair"
    assert metadata["is_valid"] is True
    assert metadata["answer"] == "온라인 신청 방법을 안내합니다."


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
    assert results[0]["answer"] == ""


def test_chroma_query_does_not_infer_answer_from_document_body(monkeypatch):
    store = ChromaVectorStore(
        persist_directory="/tmp/retrieval-test-chroma",
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )
    document = "브런치 콘서트 단체 관람 예매 문의\n오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.\n전화 예매 가능 여부와 단체 할인 문의"
    metadata = {
        "doc_id": "CASE-ANSWER-1",
        "chunk_id": "CASE-ANSWER-1__chunk-0",
        "case_id": "CASE-ANSWER-1",
        "created_at": "2026-06-10T09:00:00+09:00",
        "category": "문화",
        "region": "서울",
        "entity_labels": "",
        "summary_observation": "브런치 콘서트 단체 관람 예매 문의",
        "summary_request": "전화 예매 가능 여부와 단체 할인 문의",
        "title": "브런치 콘서트 단체 관람 예매 문의",
    }

    class _FakeCollection:
        def query(self, **kwargs):
            return {
                "ids": [["CASE-ANSWER-1::CASE-ANSWER-1__chunk-0"]],
                "documents": [[document]],
                "metadatas": [[metadata]],
                "distances": [[0.1]],
            }

    monkeypatch.setattr(store, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(store, "_get_collection", lambda collection_name: _FakeCollection())

    results = store.query(collection_name="civil_cases_v1", query="브런치 콘서트 예매", top_k=1)

    assert results[0]["answer"] == ""


def test_chroma_query_preserves_answer_metadata(monkeypatch):
    store = ChromaVectorStore(
        persist_directory="/tmp/retrieval-test-chroma",
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )
    document = "브런치 콘서트 단체 관람 예매 문의\n오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.\n전화 예매 가능 여부와 단체 할인 문의"
    metadata = {
        "doc_id": "CASE-ANSWER-1",
        "chunk_id": "CASE-ANSWER-1__chunk-0",
        "case_id": "CASE-ANSWER-1",
        "created_at": "2026-06-10T09:00:00+09:00",
        "category": "문화",
        "region": "서울",
        "entity_labels": "",
        "summary_observation": "브런치 콘서트 단체 관람 예매 문의",
        "summary_request": "전화 예매 가능 여부와 단체 할인 문의",
        "title": "브런치 콘서트 단체 관람 예매 문의",
        "answer": "오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.",
    }

    class _FakeCollection:
        def query(self, **kwargs):
            return {
                "ids": [["CASE-ANSWER-1::CASE-ANSWER-1__chunk-0"]],
                "documents": [[document]],
                "metadatas": [[metadata]],
                "distances": [[0.1]],
            }

    monkeypatch.setattr(store, "embed_texts", lambda texts: [[1.0, 0.0]])
    monkeypatch.setattr(store, "_get_collection", lambda collection_name: _FakeCollection())

    results = store.query(collection_name="civil_cases_v1", query="브런치 콘서트 예매", top_k=1)

    assert results[0]["answer"] == "오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다."


def test_hybrid_search_does_not_infer_answer_from_document_body():
    document = "브런치 콘서트 단체 관람 예매 문의\n오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.\n전화 예매 가능 여부와 단체 할인 문의"
    metadata = {
        "doc_id": "CASE-ANSWER-1",
        "chunk_id": "CASE-ANSWER-1__chunk-0",
        "case_id": "CASE-ANSWER-1",
        "summary_observation": "브런치 콘서트 단체 관람 예매 문의",
        "summary_request": "전화 예매 가능 여부와 단체 할인 문의",
        "title": "브런치 콘서트 단체 관람 예매 문의",
    }

    class _FakeCollection:
        def get(self, **kwargs):
            return {
                "ids": ["CASE-ANSWER-1::CASE-ANSWER-1__chunk-0"],
                "documents": [document],
                "metadatas": [metadata],
            }

    class _FakeStore:
        def _get_collection(self, collection_name):
            return _FakeCollection()

    retriever = HybridRetriever(_FakeStore())

    results = retriever.search(
        "civil_cases_v1",
        "브런치 콘서트 예매",
        top_k=1,
        dense_results=[{"case_id": "CASE-ANSWER-1"}],
    )

    assert results[0]["answer"] == ""
    assert results[0]["metadata"]["answer"] == results[0]["answer"]


def test_hybrid_search_preserves_answer_metadata():
    document = "브런치 콘서트 단체 관람 예매 문의\n오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.\n전화 예매 가능 여부와 단체 할인 문의"
    metadata = {
        "doc_id": "CASE-ANSWER-1",
        "chunk_id": "CASE-ANSWER-1__chunk-0",
        "case_id": "CASE-ANSWER-1",
        "summary_observation": "브런치 콘서트 단체 관람 예매 문의",
        "summary_request": "전화 예매 가능 여부와 단체 할인 문의",
        "title": "브런치 콘서트 단체 관람 예매 문의",
        "answer": "오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다.",
    }

    class _FakeCollection:
        def get(self, **kwargs):
            return {
                "ids": ["CASE-ANSWER-1::CASE-ANSWER-1__chunk-0"],
                "documents": [document],
                "metadatas": [metadata],
            }

    class _FakeStore:
        def _get_collection(self, collection_name):
            return _FakeCollection()

    retriever = HybridRetriever(_FakeStore())

    results = retriever.search(
        "civil_cases_v1",
        "브런치 콘서트 예매",
        top_k=1,
        dense_results=[{"case_id": "CASE-ANSWER-1"}],
    )

    assert results[0]["answer"] == "오픈 전 단체 예매는 어렵고, 티켓 오픈 시간 이후 예매 가능합니다."
    assert results[0]["metadata"]["answer"] == results[0]["answer"]


def test_normalize_record_preserves_category_source_fallback_origin():
    service = RetrievalService()
    record = _be1_structured_record()
    record.pop("responsible_unit")
    record["responsible_units"] = ["교통국"]
    record["responsible_units_source"] = "category_source_fallback"

    normalized = service._normalize_record(record, index=0)

    assert normalized["responsible_units"] == ["교통국"]
    assert normalized["responsible_units_source"] == "category_source_fallback"

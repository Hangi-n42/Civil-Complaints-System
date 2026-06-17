from __future__ import annotations

import pytest

from app.retrieval.service import RetrievalService
from app.retrieval.vectorstores.chroma_store import ChromaVectorStore


@pytest.mark.asyncio
async def test_retrieval_service_indexes_and_searches_via_chroma(tmp_path, monkeypatch):
    service = RetrievalService()
    store = ChromaVectorStore(
        persist_directory=str(tmp_path / "chroma_db"),
        embedding_model_name="stub-model",
        embedding_device="cpu",
    )

    def _fake_embeddings(texts):
        vectors = []
        for text in texts:
            lowered = str(text).lower()
            if "가로등" in lowered or "도로" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    monkeypatch.setattr(store, "embed_texts", _fake_embeddings)
    monkeypatch.setattr(service, "_get_vectorstore", lambda: store)

    documents = [
        {
            "case_id": "CASE-2026-000101",
            "doc_id": "DOC-101",
            "chunk_id": "CASE-2026-000101__chunk-0",
            "chunk_text": "강남구 가로등 점멸로 야간 보행이 위험합니다. 조명 점검을 요청합니다.",
            "source": "aihub_71852",
            "created_at": "2026-03-19T20:10:00+09:00",
            "category": "도로안전",
            "region": "서울시 강남구",
            "entity_labels": ["FACILITY", "HAZARD"],
            "entities": [
                {"label": "FACILITY", "text": "가로등"},
                {"label": "HAZARD", "text": "야간 보행 위험"},
            ],
            "entity_texts": [{"text": "가로등", "confidence": 0.9}],
            "legal_refs": [{"name": "도로법", "law_id": "001706"}],
            "key_terms": ["가로등", "조명", "점검"],
            "responsible_unit": [{"name": "도로관리과", "source": "be1_structured"}],
            "urgency": {"level": "높음"},
            "summary": {
                "observation": "가로등 점멸",
                "request": "조명 점검 요청",
            },
            "metadata": {
                "pipeline_version": "week2",
                "structuring_confidence": 0.91,
                "content_type": "full",
            },
        },
        {
            "case_id": "CASE-2026-000102",
            "doc_id": "DOC-102",
            "chunk_id": "CASE-2026-000102__chunk-0",
            "chunk_text": "서초구 공원 화장실 누수로 시설 이용이 어렵습니다. 긴급 보수를 요청합니다.",
            "source": "aihub_71852",
            "created_at": "2026-03-20T09:00:00+09:00",
            "category": "시설관리",
            "region": "서울시 서초구",
            "entity_labels": ["FACILITY"],
            "summary": {
                "observation": "화장실 누수",
                "request": "긴급 보수 요청",
            },
            "metadata": {
                "pipeline_version": "week2",
                "structuring_confidence": 0.84,
                "content_type": "full",
            },
        },
    ]

    index_result = await service.index_documents(documents, rebuild=True, collection_name="civil_cases_v1")
    assert index_result["indexed_count"] == 2
    assert index_result["chunk_count"] == 2
    assert index_result["index_name"] == "civil_cases_v1"

    results = await service.search(
        query="가로등 점검",
        top_k=1,
        filters={"region": "서울시 강남구"},
        collection_name="civil_cases_v1",
    )

    assert len(results) == 1
    assert results[0]["case_id"] == "CASE-2026-000101"
    assert results[0]["chunk_id"] == "CASE-2026-000101__chunk-0"
    assert results[0]["summary"]["observation"] == "가로등 점멸"
    assert results[0]["metadata"]["entity_labels"] == ["FACILITY", "HAZARD"]
    assert results[0]["metadata"]["entity_texts"] == ["가로등"]
    assert results[0]["metadata"]["legal_ref_names"] == ["도로법"]
    assert results[0]["metadata"]["legal_ref_ids"] == ["001706"]
    assert "issue_types" not in results[0]["metadata"]
    assert results[0]["metadata"]["key_terms"] == ["가로등", "조명", "점검"]
    assert results[0]["metadata"]["responsible_units"] == ["도로관리과"]
    assert results[0]["metadata"]["responsible_units_source"] == "be1_structured"
    assert results[0]["metadata"]["urgency_level"] == "높음"
    assert results[0]["rank"] == 1

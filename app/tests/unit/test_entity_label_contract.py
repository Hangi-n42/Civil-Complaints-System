from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.main import app
from app.api.schemas.retrieval import SearchFilters
from app.retrieval.service import RetrievalService


def test_indexed_entity_labels_are_allowlist_only_and_aligned():
    service = RetrievalService()
    record = {
        "case_id": "CASE-TEST-001",
        "text": "민원 본문",
        "entities": [
            {"label": "facility", "text": "가로등"},
            {"label": "TYPE", "text": "잘못된태그"},
            {"label": "HAZARD", "text": "전도위험"},
            {"label": "ADMIN_UNIT", "text": "강남구"},
            {"label": "FACILITY", "text": "가로등"},
            {"label": "TIME"},
        ],
    }

    normalized = service._normalize_record(record, index=0)

    assert normalized["entity_labels"] == ["FACILITY", "HAZARD", "ADMIN_UNIT"]
    assert normalized["entity_texts"] == ["가로등", "전도위험", "강남구"]
    assert len(normalized["entity_labels"]) == len(normalized["entity_texts"])


def test_filter_entity_labels_or_matching_and_empty_array_behavior():
    service = RetrievalService()
    chunk = {
        "entity_labels": ["FACILITY", "TIME"],
        "created_at": "2026-03-20T10:00:00+09:00",
    }

    assert service._matches_filters(chunk, {"entity_labels": ["HAZARD", "FACILITY"]})
    assert service._matches_filters(chunk, {"entity_labels": []})
    assert not service._matches_filters(chunk, {"entity_labels": ["ADMIN_UNIT"]})


def test_search_filter_rejects_invalid_entity_labels():
    try:
        SearchFilters(entity_labels=["FACILITY", "TYPE"])
        assert False, "ValidationError가 발생해야 합니다."
    except ValidationError as exc:
        assert "허용되지 않은 라벨" in str(exc)


def test_search_api_returns_400_for_invalid_entity_labels():
    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "query": "가로등",
            "top_k": 5,
            "filters": {"entity_labels": ["TYPE"]},
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "FILTER_INVALID"
    assert "허용되지 않은 라벨" in str(body)


def test_search_api_returns_400_for_invalid_date_range():
    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={
            "query": "가로등",
            "top_k": 5,
            "filters": {
                "date_from": "2026-03-31T00:00:00+09:00",
                "date_to": "2026-03-01T00:00:00+09:00",
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "FILTER_INVALID"
    assert "date_from" in str(body)

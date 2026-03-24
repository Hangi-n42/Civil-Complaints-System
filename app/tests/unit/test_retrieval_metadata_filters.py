from __future__ import annotations

import pytest

from app.api.schemas.retrieval import SearchFilters
from app.retrieval.service import RetrievalService


@pytest.mark.parametrize(
    "filters, expected",
    [
        ({"category": "도로안전"}, True),
        ({"category": "치안"}, False),
        ({"region": "강남구"}, True),
        ({"region": "서초구"}, False),
        ({"created_at": "2026-03-20T10:15:00+09:00"}, True),
        ({"created_at": "2026-03-21T10:15:00+09:00"}, False),
        ({"entity_labels": ["facility"]}, True),
        ({"entity_labels": ["admin_unit"]}, False),
        ({"date_from": "2026-03-19T00:00:00+09:00", "date_to": "2026-03-21T00:00:00+09:00"}, True),
        ({"date_from": "2026-03-21T00:00:00+09:00"}, False),
    ],
)
def test_matches_filters_by_metadata_keys(filters, expected):
    service = RetrievalService()
    chunk = {
        "category": "도로안전",
        "region": "서울시 강남구",
        "created_at": "2026-03-20T10:15:00+09:00",
        "entity_labels": ["FACILITY", "TIME"],
    }

    assert service._matches_filters(chunk, filters) is expected


def test_search_filters_normalize_entity_labels():
    payload = SearchFilters(entity_labels=[" facility ", "TIME", "time", ""])

    assert payload.entity_labels == ["FACILITY", "TIME"]

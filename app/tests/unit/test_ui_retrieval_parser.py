from __future__ import annotations

import pytest

from app.ui.services.retrieval_parser import (
    ResponseContractError,
    parse_index_response,
    parse_search_response,
)


def test_parse_search_response_success():
    payload = {
        "success": True,
        "request_id": "REQ-20260320-AAAA1111",
        "timestamp": "2026-03-20T10:00:00+09:00",
        "data": {
            "results": [],
            "total_found": 0,
            "elapsed_ms": 12,
        },
    }

    data = parse_search_response(payload)
    assert data["total_found"] == 0


def test_parse_index_response_success():
    payload = {
        "success": True,
        "request_id": "REQ-20260320-BBBB2222",
        "timestamp": "2026-03-20T10:01:00+09:00",
        "data": {
            "indexed_count": 1,
            "failed_count": 0,
            "collection_name": "civil_cases_v1",
            "elapsed_ms": 123,
        },
    }

    data = parse_index_response(payload)
    assert data["indexed_count"] == 1
    assert data["collection_name"] == "civil_cases_v1"


def test_parse_search_response_missing_data_raises_error():
    payload = {
        "success": True,
        "request_id": "REQ-20260320-CCCC3333",
        "timestamp": "2026-03-20T10:02:00+09:00",
    }

    with pytest.raises(ResponseContractError):
        parse_search_response(payload)

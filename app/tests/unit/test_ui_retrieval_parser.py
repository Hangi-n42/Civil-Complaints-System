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
            "query": "가로등",
            "top_k": 5,
            "results": [],
            "count": 0,
            "took_ms": 12,
        },
    }

    data = parse_search_response(payload)
    assert data["query"] == "가로등"
    assert data["count"] == 0


def test_parse_index_response_success():
    payload = {
        "success": True,
        "request_id": "REQ-20260320-BBBB2222",
        "timestamp": "2026-03-20T10:01:00+09:00",
        "data": {
            "indexed_count": 1,
            "chunk_count": 2,
            "index_name": "civil_cases",
            "rebuild": False,
            "records": [{"case_id": "CASE-1", "chunk_ids": ["CASE-1__chunk-0"]}],
            "took_ms": 123,
        },
    }

    data = parse_index_response(payload)
    assert data["indexed_count"] == 1
    assert data["records"][0]["case_id"] == "CASE-1"


def test_parse_search_response_missing_data_raises_error():
    payload = {
        "success": True,
        "request_id": "REQ-20260320-CCCC3333",
        "timestamp": "2026-03-20T10:02:00+09:00",
    }

    with pytest.raises(ResponseContractError):
        parse_search_response(payload)

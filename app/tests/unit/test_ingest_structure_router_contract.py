from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.exceptions import StructuringError


class _StubIngestionService:
    async def process(self, documents, clean=True, mask_pii=True, deduplicate=True):
        return [
            {
                "case_id": "CASE-1",
                "text": "정제된 텍스트",
            }
        ]


class _StubStructuringService:
    async def structure(self, record):
        return {
            "case_id": "CASE-1",
            "source": "manual",
            "created_at": "2026-03-20T10:00:00+09:00",
            "category": "도로안전",
            "region": "서울",
            "raw_text": "원문",
            "observation": {"text": "관찰", "confidence": 0.9, "evidence_span": [0, 2]},
            "result": {"text": "결과", "confidence": 0.8, "evidence_span": [3, 5]},
            "request": {"text": "요청", "confidence": 0.85, "evidence_span": [6, 8]},
            "context": {"text": "맥락", "confidence": 0.7, "evidence_span": [9, 11]},
            "entities": [{"label": "FACILITY", "text": "가로등"}],
            "metadata": {"source_file": "raw_001.json"},
            "supervision": {"summary": {"task_category": "요약", "instruction": "...", "input": "...", "output": "..."}},
            "confidence_score": 0.81,
            "structured_at": "2026-03-20T10:00:00+09:00",
            "validation": {
                "is_valid": False,
                "errors": ["invalid_confidence:request"],
                "warnings": ["source_is_unknown"],
            },
        }


class _FailStructuringService:
    async def structure(self, record):
        raise StructuringError("구조화 처리 실패")


def test_ingest_response_is_wrapped(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_ingestion_service",
        lambda: _StubIngestionService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest",
        json={
            "source_type": "manual",
            "source": "demo",
            "mask_pii": True,
            "deduplicate": True,
            "records": [{"case_id": "CASE-1", "text": "원문"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["request_id"], str)
    assert isinstance(body["timestamp"], str)
    assert body["data"]["ingested_count"] == 1
    assert body["data"]["skipped_count"] == 0
    assert body["data"]["records"][0]["status"] == "accepted"


def test_ingest_validation_error_format(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_ingestion_service",
        lambda: _StubIngestionService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest",
        json={
            "records": [{"case_id": "CASE-1"}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["retryable"] is False
    assert "validation_errors" in body["error"]["details"]


def test_structure_response_has_validation_format(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_structuring_service",
        lambda: _StubStructuringService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/structure",
        json={"records": [{"case_id": "CASE-1", "text": "원문"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["request_id"], str)
    assert isinstance(body["timestamp"], str)
    assert body["data"]["structured_count"] == 1
    assert body["data"]["invalid_count"] == 1

    validation = body["data"]["results"][0]["validation"]
    assert isinstance(body["data"]["results"][0]["metadata"], dict)
    assert isinstance(body["data"]["results"][0]["confidence_score"], float)
    assert isinstance(body["data"]["results"][0]["structured_at"], str)
    assert validation["is_valid"] is False
    assert isinstance(validation["errors"], list)
    assert isinstance(validation["warnings"], list)
    assert validation["errors"][0]["field"] == "invalid.confidence"
    assert "code" in validation["errors"][0]
    assert "message" in validation["errors"][0]


def test_structure_bad_request_retryable_false(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_structuring_service",
        lambda: _StubStructuringService(),
    )

    client = TestClient(app)
    response = client.post("/api/v1/structure", json={"records": []})

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "BAD_REQUEST"
    assert body["error"]["retryable"] is False


def test_structure_processing_error_is_wrapped(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    monkeypatch.setattr(
        retrieval_router,
        "get_structuring_service",
        lambda: _FailStructuringService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/structure",
        json={"records": [{"case_id": "CASE-1", "text": "원문"}]},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PROCESSING_ERROR"
    assert body["error"]["retryable"] is True


def test_ingest_deduplicate_flag_is_forwarded(monkeypatch):
    from app.api.routers import retrieval as retrieval_router

    called = {"deduplicate": None}

    class _AssertIngestionService:
        async def process(self, documents, clean=True, mask_pii=True, deduplicate=True):
            called["deduplicate"] = deduplicate
            return [{"case_id": "CASE-1", "text": "정제된 텍스트"}]

    monkeypatch.setattr(
        retrieval_router,
        "get_ingestion_service",
        lambda: _AssertIngestionService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest",
        json={
            "records": [{"case_id": "CASE-1", "text": "원문"}],
            "deduplicate": False,
        },
    )

    assert response.status_code == 200
    assert called["deduplicate"] is False

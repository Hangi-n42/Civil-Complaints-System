from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


class _StubStructuringService:
    async def structure(self, payload):
        return {
            "case_id": payload.get("case_id") or "CASE-STRUCTURE-001",
            "source": payload.get("source") or "test",
            "raw_text": payload.get("raw_text") or payload.get("text"),
            "observation": {"text": "관찰"},
            "result": {"text": "결과"},
            "request": {"request": "요청"},
            "context": {"text": "맥락"},
            "entities": [],
            "validation": {"is_valid": True, "errors": []},
        }


def test_structure_response_is_wrapped(monkeypatch):
    from app.api.routers import structuring as structuring_router

    monkeypatch.setattr(
        structuring_router,
        "get_structuring_service",
        lambda: _StubStructuringService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/structure",
        json={
            "request_id": "STR-2026-000001",
            "case_id": "CASE-STRUCTURE-001",
            "raw_text": "도로 파손 보수 요청",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["request_id"] == "STR-2026-000001"
    assert isinstance(body["timestamp"], str)
    assert body["data"]["case_id"] == "CASE-STRUCTURE-001"
    assert body["data"]["raw_text"] == "도로 파손 보수 요청"


def test_structure_rejects_empty_body():
    client = TestClient(app)
    response = client.post("/api/v1/structure", json={"request_id": "STR-EMPTY"})

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["request_id"] == "STR-EMPTY"
    assert body["error"]["code"] == "BAD_REQUEST"

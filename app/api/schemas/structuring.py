"""BE1 구조화 API 스키마."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class StructureRequest(BaseModel):
    """단건 민원 구조화 요청."""

    model_config = ConfigDict(extra="allow")

    request_id: Optional[str] = None
    case_id: Optional[str] = None
    source_id: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None
    consulting_date: Optional[str] = None
    category: Optional[str] = None
    consulting_category: Optional[str] = None
    region: Optional[str] = None
    text: Optional[str] = None
    raw_text: Optional[str] = None
    consulting_content: Optional[str] = None
    consulting_turns: Optional[int] = None
    consulting_length: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class StructureResponse(BaseModel):
    """단건 민원 구조화 응답."""

    success: bool
    request_id: str
    timestamp: str
    data: Dict[str, Any]

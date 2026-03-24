"""Retrieval API 스키마"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.retrieval.entity_labels import ALLOWED_ENTITY_LABELS, normalize_entity_label


class SearchFilters(BaseModel):
    """검색 필터"""

    region: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    entity_labels: Optional[List[str]] = None

    @field_validator("entity_labels")
    @classmethod
    def validate_entity_labels(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None

        normalized: List[str] = []
        seen = set()
        invalid_labels: List[str] = []

        for item in value:
            label = normalize_entity_label(item)
            if not label:
                continue
            if label not in ALLOWED_ENTITY_LABELS:
                invalid_labels.append(label)
                continue
            if label in seen:
                continue
            seen.add(label)
            normalized.append(label)

        if invalid_labels:
            allowed = ", ".join(sorted(ALLOWED_ENTITY_LABELS))
            invalid = ", ".join(sorted(set(invalid_labels)))
            raise ValueError(
                f"filters.entity_labels에 허용되지 않은 라벨이 포함되었습니다: {invalid}. "
                f"허용 라벨: {allowed}"
            )
        return normalized


class IndexRecord(BaseModel):
    """인덱싱 입력 레코드"""

    model_config = ConfigDict(extra="allow")

    case_id: Optional[str] = None
    id: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    text: Optional[str] = None
    structured_text: Optional[Dict[str, str]] = None
    observation: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    request: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class IndexRequest(BaseModel):
    """인덱싱 요청"""

    rebuild: bool = False
    records: List[IndexRecord] = Field(default_factory=list)


class IndexRecordResult(BaseModel):
    """인덱싱 레코드 결과"""

    case_id: str
    chunk_ids: List[str]


class IndexResponseData(BaseModel):
    """인덱싱 응답 데이터"""

    indexed_count: int
    chunk_count: int
    index_name: str
    rebuild: bool
    records: List[IndexRecordResult]
    took_ms: int


class SearchRequest(BaseModel):
    """검색 요청"""

    query: str
    top_k: int = 5
    filters: Optional[SearchFilters] = None


class SearchSummary(BaseModel):
    """검색 요약"""

    observation: Optional[str] = None
    request: Optional[str] = None


class SearchResultMetadata(BaseModel):
    """검색 결과 메타데이터"""

    created_at: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    entity_labels: List[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    """검색 결과 항목"""

    rank: int
    doc_id: str
    score: float
    chunk_id: str
    case_id: str
    title: str
    snippet: str
    summary: Optional[SearchSummary] = None
    metadata: SearchResultMetadata


class SearchResponseData(BaseModel):
    """검색 응답 데이터"""

    query: str
    top_k: int
    results: List[SearchResultItem]
    count: int
    took_ms: int


class IndexResponse(BaseModel):
    """인덱싱 성공 응답"""

    success: bool = True
    request_id: str
    timestamp: str
    data: IndexResponseData


class SearchResponse(BaseModel):
    """검색 성공 응답"""

    success: bool = True
    request_id: str
    timestamp: str
    data: SearchResponseData

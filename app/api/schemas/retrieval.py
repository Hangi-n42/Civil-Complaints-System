"""Retrieval API 스키마"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    """검색 필터"""

    region: Optional[str] = None
    category: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    entity_labels: Optional[List[str]] = None


class IngestRecordInput(BaseModel):
    """입수 입력 레코드"""

    model_config = ConfigDict(extra="allow")

    case_id: Optional[str] = None
    created_at: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    text: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IngestRequest(BaseModel):
    """입수 요청"""

    source_type: str = "manual"
    source: str = "manual"
    mask_pii: bool = True
    deduplicate: bool = True
    records: List[IngestRecordInput] = Field(default_factory=list)


class IngestRecordResult(BaseModel):
    """입수 처리 결과 레코드"""

    case_id: str
    status: str
    normalized_text: str


class IngestResponseData(BaseModel):
    """입수 응답 데이터"""

    ingested_count: int
    skipped_count: int
    mask_pii: bool
    deduplicate: bool
    records: List[IngestRecordResult]


class IngestResponse(BaseModel):
    """입수 성공 응답"""

    success: bool = True
    request_id: str
    timestamp: str
    data: IngestResponseData


class StructureRecordInput(BaseModel):
    """구조화 입력 레코드"""

    model_config = ConfigDict(extra="allow")

    case_id: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    text: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StructureRequest(BaseModel):
    """구조화 요청"""

    records: List[StructureRecordInput] = Field(default_factory=list)


class FieldExtraction(BaseModel):
    """4요소 추출 필드"""

    text: str
    confidence: float
    evidence_span: List[int]


class EntityItem(BaseModel):
    """엔티티 항목"""

    label: str
    text: str
    start: Optional[int] = None
    end: Optional[int] = None
    confidence: Optional[float] = None


class ValidationIssueItem(BaseModel):
    """검증 이슈"""

    field: str
    code: str
    message: str


class ValidationResult(BaseModel):
    """구조화 검증 결과"""

    is_valid: bool
    errors: List[ValidationIssueItem] = Field(default_factory=list)
    warnings: List[ValidationIssueItem] = Field(default_factory=list)


class StructuredRecordResult(BaseModel):
    """구조화 처리 결과 레코드"""

    case_id: str
    source: str
    created_at: str
    category: Optional[str] = None
    region: Optional[str] = None
    raw_text: str
    observation: FieldExtraction
    result: FieldExtraction
    request: FieldExtraction
    context: FieldExtraction
    entities: List[EntityItem] = Field(default_factory=list)
    metadata: Dict[str, Any]
    supervision: Optional[Dict[str, Any]] = None
    confidence_score: float
    structured_at: str
    validation: ValidationResult


class StructureResponseData(BaseModel):
    """구조화 응답 데이터"""

    structured_count: int
    invalid_count: int
    results: List[StructuredRecordResult]


class StructureResponse(BaseModel):
    """구조화 성공 응답"""

    success: bool = True
    request_id: str
    timestamp: str
    data: StructureResponseData


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

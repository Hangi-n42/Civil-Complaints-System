"""Retrieval API 스키마"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.retrieval.entity_labels import ALLOWED_ENTITY_LABELS, normalize_entity_label


class SearchFilters(BaseModel):
    """검색 필터"""

    region: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    entity_labels: Optional[List[str]] = None

    @field_validator("created_at", "date_from", "date_to")
    @classmethod
    def validate_iso_datetime(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("날짜 필터는 ISO-8601 형식이어야 합니다.") from exc
        return value

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

    @model_validator(mode="after")
    def validate_date_range(self) -> "SearchFilters":
        if self.date_from and self.date_to:
            start = datetime.fromisoformat(self.date_from)
            end = datetime.fromisoformat(self.date_to)
            if start > end:
                raise ValueError("filters.date_from은 filters.date_to보다 이전이거나 같아야 합니다.")
        return self


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

    request_id: Optional[str] = None
    action: Literal["bulk", "incremental"] = "bulk"
    cases: List[IndexRecord] = Field(default_factory=list)
    collection_name: str = "civil_cases_v1"

    # Backward compatibility fields
    rebuild: Optional[bool] = None
    records: Optional[List[IndexRecord]] = None

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "IndexRequest":
        if not self.cases and self.records:
            self.cases = self.records

        if self.rebuild is not None:
            self.action = "bulk" if self.rebuild else "incremental"

        return self


class IndexRecordResult(BaseModel):
    """인덱싱 레코드 결과"""

    case_id: str
    chunk_ids: List[str]


class IndexResponseData(BaseModel):
    """인덱싱 응답 데이터"""

    indexed_count: int
    failed_count: int
    collection_name: str
    elapsed_ms: int

    # Backward compatibility fields
    chunk_count: Optional[int] = None
    index_name: Optional[str] = None
    rebuild: Optional[bool] = None
    records: Optional[List[IndexRecordResult]] = None
    took_ms: Optional[int] = None


class SearchRequest(BaseModel):
    """검색 요청"""

    request_id: Optional[str] = None
    complaint_id: Optional[str] = None
    query: str
    top_k: int = 5
    filters: Optional[SearchFilters] = None
    collection_name: str = "civil_cases_v1"


class RoutingHint(BaseModel):
    """search -> qa 전달용 라우팅 힌트"""

    strategy_id: str
    route_key: str
    top_k: int = Field(default=5, ge=1, le=50)
    snippet_max_chars: int = Field(default=1100, ge=120, le=4000)
    chunk_policy: Literal["compact", "balanced", "expanded"] = "balanced"


class RoutingComplexityTrace(BaseModel):
    """라우팅 복잡도 산정 근거"""

    intent_count: int = 1
    constraint_count: int = 0
    entity_diversity: int = 1
    policy_reference_count: int = 0
    cross_sentence_dependency: bool = False


class RoutingTrace(BaseModel):
    """라우팅 추적 정보"""

    topic_type: str
    complexity_level: Literal["low", "medium", "high"]
    complexity_score: float = Field(ge=0.0, le=1.0)
    request_segments: Optional[List[str]] = None
    complexity_trace: RoutingComplexityTrace
    route_reason: str
    route_key: Optional[str] = None
    strategy_id: Optional[str] = None
    applied_filters: Dict[str, Any] = Field(default_factory=dict)
    segment_count: Optional[int] = None
    merge_policy: Optional[str] = None
    retrieval_policy: Optional[str] = None


class SearchSummary(BaseModel):
    """검색 요약"""

    observation: str = ""
    request: str = ""


class SearchResultMetadata(BaseModel):
    """검색 결과 메타데이터"""

    created_at: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    entity_labels: List[str] = Field(default_factory=list)
    strategy_id: Optional[str] = None
    route_key: Optional[str] = None
    topic_type: Optional[str] = None
    retrieval_policy: Optional[str] = None
    matched_segments: List[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    """검색 결과 항목"""

    rank: int
    case_id: str
    similarity_score: float
    content: Dict[str, str]
    metadata: SearchResultMetadata
    doc_id: str
    score: float
    chunk_id: str
    snippet: str
    summary: SearchSummary
    answers_by_admin_unit: Dict[str, str] = Field(default_factory=dict)

    # Backward compatibility fields
    title: Optional[str] = None
    department_answers: Dict[str, str] = Field(default_factory=dict)


class SearchResponseData(BaseModel):
    """검색 응답 데이터"""

    complaint_id: Optional[str] = None
    strategy_id: str
    route_key: str
    routing_hint: RoutingHint
    routing_trace: RoutingTrace
    retrieved_docs: List[SearchResultItem]
    results: List[SearchResultItem] = Field(default_factory=list)
    total_found: int
    elapsed_ms: int

    # Backward compatibility fields
    query: Optional[str] = None
    top_k: Optional[int] = None
    count: Optional[int] = None
    took_ms: Optional[int] = None


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

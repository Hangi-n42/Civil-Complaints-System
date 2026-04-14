"""Generation API 스키마"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.schemas.retrieval import RoutingHint, RoutingTrace, SearchFilters


class SearchInputResult(BaseModel):
    """/qa 요청에서 재사용하는 검색 결과 입력"""

    doc_id: Optional[str] = None
    chunk_id: str
    case_id: str
    snippet: str
    score: float


class QAContextWindowPolicy(BaseModel):
    """Retrieval 청크를 QA 입력 컨텍스트로 매핑할 때 사용할 안전 예산 정책"""

    model_ctx_tokens: int = Field(default=2048, ge=512, le=32768)
    reserved_output_tokens: int = Field(default=512, ge=128, le=8192)
    reserved_system_tokens: int = Field(default=256, ge=64, le=4096)
    chars_per_token: float = Field(default=2.0, ge=1.0, le=8.0)
    max_chunks: int = Field(default=8, ge=1, le=50)
    max_chars_per_chunk: int = Field(default=320, ge=80, le=4000)


class QARequest(BaseModel):
    """QA 요청"""

    request_id: Optional[str] = None
    complaint_id: Optional[str] = None
    query: str = Field(min_length=1)
    routing_hint: Optional[RoutingHint] = None
    routing_trace: Optional[RoutingTrace] = None
    top_k: int = Field(default=5, ge=1, le=50)
    filters: Optional[SearchFilters] = None
    use_search_results: bool = False
    search_results: List[SearchInputResult] = Field(default_factory=list)
    context_window_policy: Optional[QAContextWindowPolicy] = None

    @field_validator("query")
    @classmethod
    def validate_query_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("query는 공백일 수 없습니다.")
        return value

    @model_validator(mode="after")
    def validate_search_results_when_forced(self) -> "QARequest":
        if self.use_search_results and not self.search_results:
            raise ValueError(
                "use_search_results=true인 경우 search_results를 최소 1개 이상 전달해야 합니다."
            )
        return self


class Citation(BaseModel):
    """QA citation"""

    ref_id: int
    doc_id: Optional[str] = None
    chunk_id: str
    case_id: str
    snippet: str
    relevance_score: Optional[float] = None
    start: Optional[int] = None
    end: Optional[int] = None
    source: Optional[str] = "retrieval"


class MetaInfo(BaseModel):
    """QA 메타 정보"""

    processing_time: float
    model: str
    validation_warning: str
    generated_at: Optional[str] = None
    validator_version: Optional[str] = None


class ValidationIssue(BaseModel):
    """검증 이슈"""

    code: str
    message: str


class QAValidation(BaseModel):
    """QA 검증 결과"""

    is_valid: bool
    errors: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)


class SearchTrace(BaseModel):
    """QA 검색 추적 정보"""

    used_top_k: int
    retrieved_count: int
    context_budget_chars: Optional[int] = None
    context_used_chars: Optional[int] = None
    context_truncated_count: Optional[int] = None
    context_dropped_count: Optional[int] = None


class CitationValidation(BaseModel):
    """Citation 정합성 검증 결과"""

    is_valid: bool
    mismatch_count: int = 0
    details: Optional[Dict[str, Any]] = None


class QAResponseData(BaseModel):
    """QA 응답 본체"""

    complaint_id: str
    strategy_id: str
    route_key: str
    routing_trace: RoutingTrace
    structured_output: Dict[str, Any] = Field(default_factory=dict)
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    latency_ms: Dict[str, int] = Field(default_factory=dict)
    quality_signals: Dict[str, Any] = Field(default_factory=dict)


class ErrorInfo(BaseModel):
    """에러 정보"""

    code: str
    message: str
    retryable: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class QAResponse(BaseModel):
    """QA 성공 응답 (Week 5 계약)"""

    success: Literal[True] = True
    request_id: str
    timestamp: str
    data: QAResponseData
    meta: Optional[MetaInfo] = None
    qa_validation: Optional[QAValidation] = None
    search_trace: Optional[SearchTrace] = None
    citation_validation: Optional[CitationValidation] = None


class QAErrorResponse(BaseModel):
    """QA 실패 응답"""

    success: Literal[False] = False
    request_id: str
    timestamp: str
    error: ErrorInfo

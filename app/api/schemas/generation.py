"""Generation API 스키마"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.api.schemas.retrieval import SearchFilters


class SearchInputResult(BaseModel):
    """/qa 요청에서 재사용하는 검색 결과 입력"""

    doc_id: Optional[str] = None
    chunk_id: str
    case_id: str
    snippet: str
    score: float = 0.0


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

    query: str
    top_k: int = 5
    filters: Optional[SearchFilters] = None
    use_search_results: bool = False
    search_results: List[SearchInputResult] = Field(default_factory=list)
    context_window_policy: Optional[QAContextWindowPolicy] = None


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

    answer: str
    citations: List[Citation]
    confidence: Literal["low", "medium", "high"]
    limitations: str
    latency_ms: int


class ErrorInfo(BaseModel):
    """에러 정보"""

    code: str
    message: str
    retryable: bool
    details: Optional[Dict[str, Any]] = None


class QAResponse(BaseModel):
    """QA 성공 응답 (Week 4 계약)"""

    success: Literal[True] = True
    request_id: str
    timestamp: str
    data: QAResponseData
    meta: MetaInfo
    qa_validation: QAValidation
    search_trace: SearchTrace
    citation_validation: CitationValidation


class QAErrorResponse(BaseModel):
    """QA 실패 응답"""

    success: Literal[False] = False
    request_id: str
    timestamp: str
    error: ErrorInfo

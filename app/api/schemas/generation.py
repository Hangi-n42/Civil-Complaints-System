"""Generation API 스키마"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.api.schemas.retrieval import SearchFilters


class SearchInputResult(BaseModel):
    """/qa 요청에서 재사용하는 검색 결과 입력"""

    doc_id: Optional[str] = None
    chunk_id: str
    case_id: str
    snippet: str
    score: float = 0.0


class QARequest(BaseModel):
    """QA 요청"""

    query: str
    top_k: int = 5
    filters: Optional[SearchFilters] = None
    use_search_results: bool = False
    search_results: List[SearchInputResult] = Field(default_factory=list)


class Citation(BaseModel):
    """QA citation"""

    ref_id: int
    doc_id: str
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


class QAResponse(BaseModel):
    """QA 응답"""

    status: str = "ok"
    request_id: str
    timestamp: str
    answer: str
    citations: List[Citation]
    confidence: str
    limitations: str
    meta: MetaInfo
    qa_validation: QAValidation

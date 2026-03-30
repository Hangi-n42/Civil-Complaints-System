"""
사용자 정의 예외 클래스
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AISystemException(Exception):
    """기본 애플리케이션 예외"""
    pass


class IngestionError(AISystemException):
    """데이터 입수 오류"""
    pass


class StructuringError(AISystemException):
    """구조화 오류"""
    pass


class RetrievalError(AISystemException):
    """검색 오류"""
    pass


class GenerationError(AISystemException):
    """응답 생성 오류"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PROCESSING_ERROR",
        retryable: bool = True,
        details: Optional[Dict[str, Any]] = None,
        upstream_status: Optional[int] = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}
        self.upstream_status = upstream_status


class ValidationError(AISystemException):
    """검증 오류"""
    pass


class ConfigError(AISystemException):
    """설정 오류"""
    pass

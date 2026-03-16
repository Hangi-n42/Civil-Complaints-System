"""
사용자 정의 예외 클래스
"""


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
    pass


class ValidationError(AISystemException):
    """검증 오류"""
    pass


class ConfigError(AISystemException):
    """설정 오류"""
    pass

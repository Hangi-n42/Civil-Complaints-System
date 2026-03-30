"""
로깅 설정

모든 모듈에서 일관된 로깅을 사용하도록 설정한다.
"""

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any, Dict, Optional
from app.core.config import settings


def setup_logger(name: str, log_file: str) -> logging.Logger:
    """
    로거 설정

    Args:
        name: 로거 이름
        log_file: 로그 파일 경로

    Returns:
        설정된 로거
    """
    # 로그 디렉토리 생성
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 포매터
    formatter = logging.Formatter(settings.LOG_FORMAT)

    # 파일 핸들러
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# 각 목적별 로거 생성
api_logger = setup_logger("api", settings.API_LOG_FILE)
pipeline_logger = setup_logger("pipeline", settings.PIPELINE_LOG_FILE)
evaluation_logger = setup_logger("evaluation", settings.EVALUATION_LOG_FILE)


def log_ollama_error(
    logger: logging.Logger,
    *,
    endpoint: str,
    model: str,
    ollama_base_url: str,
    timeout: int,
    stage: str,
    upstream_status: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    retryable: bool = True,
) -> None:
    """
    Ollama 호출 오류를 구조화된 필드로 기록한다.
    
    Args:
        logger: 로거 인스턴스
        endpoint: Ollama 엔드포인트 (e.g., /api/generate)
        model: 모델명
        ollama_base_url: Ollama 베이스 URL
        timeout: 타임아웃 초 단위
        stage: 오류 발생 단계 (e.g., 'connect', 'read', 'parse')
        upstream_status: 업스트림 HTTP 상태코드
        error_code: 에러코드 (e.g., 'MODEL_NOT_READY')
        error_message: 에러 메시지
        retryable: 재시도 가능 여부
    """
    log_entry: Dict[str, Any] = {
        "level": "error",
        "component": "ollama_client",
        "endpoint": endpoint,
        "model": model,
        "ollama_base_url": ollama_base_url,
        "timeout": timeout,
        "stage": stage,
        "upstream_status": upstream_status,
        "error_code": error_code,
        "error_message": error_message,
        "retryable": retryable,
    }
    logger.error(json.dumps(log_entry, ensure_ascii=False))


def log_ollama_call(
    logger: logging.Logger,
    *,
    endpoint: str,
    model: str,
    ollama_base_url: str,
    timeout: int,
    temperature: float = 0.7,
) -> None:
    """
    Ollama 호출 시작 로그를 구조화된 필드로 기록한다.
    
    Args:
        logger: 로거 인스턴스
        endpoint: Ollama 엔드포인트
        model: 모델명
        ollama_base_url: Ollama 베이스 URL
        timeout: 타임아웃 초 단위
        temperature: 온도 파라미터
    """
    log_entry: Dict[str, Any] = {
        "level": "info",
        "component": "ollama_client",
        "action": "call_start",
        "endpoint": endpoint,
        "model": model,
        "ollama_base_url": ollama_base_url,
        "timeout": timeout,
        "temperature": temperature,
    }
    logger.info(json.dumps(log_entry, ensure_ascii=False))

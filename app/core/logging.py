"""
로깅 설정

모든 모듈에서 일관된 로깅을 사용하도록 설정한다.
"""

import logging
import logging.handlers
from pathlib import Path
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

"""
프로젝트 설정 관리

환경 변수와 기본 설정값을 로드하고 관리한다.
"""

import os
from typing import Optional
from pathlib import Path

# 기본 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIGS_DIR = PROJECT_ROOT / "configs"
LOGS_DIR = PROJECT_ROOT / "logs"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"


class Settings:
    """애플리케이션 설정"""

    # API 설정
    API_TITLE: str = "AI Civil Affairs System API"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = "온디바이스 AI 기반 민원 데이터 심층 분석 및 검색 시스템"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Ollama 설정
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", 120))

    # ChromaDB 설정
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", str(DATA_DIR / "chroma_db"))
    CHROMA_PERSIST_DIRECTORY: Optional[str] = CHROMA_DB_PATH

    # 임베딩 설정
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cuda")

    # 데이터 경로
    RAW_DATA_PATH: str = str(DATA_DIR / "raw")
    INTERIM_DATA_PATH: str = str(DATA_DIR / "interim")
    PROCESSED_DATA_PATH: str = str(DATA_DIR / "processed")
    SAMPLES_DATA_PATH: str = str(DATA_DIR / "samples")

    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    API_LOG_FILE: str = str(LOGS_DIR / "api" / "app.log")
    PIPELINE_LOG_FILE: str = str(LOGS_DIR / "pipeline" / "pipeline.log")
    EVALUATION_LOG_FILE: str = str(LOGS_DIR / "evaluation" / "evaluation.log")

    # 성능 설정
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", 4))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", 60))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", 32))

    # 검증 설정
    MIN_CONFIDENCE_SCORE: float = float(os.getenv("MIN_CONFIDENCE_SCORE", 0.5))
    MAX_RETRY_COUNT: int = int(os.getenv("MAX_RETRY_COUNT", 3))


settings = Settings()

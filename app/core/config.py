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
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b-instruct")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", 120))
    GENERATION_NUM_PREDICT: int = int(os.getenv("GENERATION_NUM_PREDICT", 640))
    GENERATION_NUM_CTX: int = int(os.getenv("GENERATION_NUM_CTX", 2048))

    # ChromaDB 설정
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", str(DATA_DIR / "chroma_db"))
    CHROMA_PERSIST_DIRECTORY: Optional[str] = CHROMA_DB_PATH
    DEFAULT_CHROMA_COLLECTION: str = os.getenv("DEFAULT_CHROMA_COLLECTION", "civil_cases_v1")

    # 임베딩 설정
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # 검색 전략 (교정 평가 #273: Hybrid이 전 지표 1위 → 기본값 hybrid)
    RETRIEVAL_STRATEGY: str = os.getenv("RETRIEVAL_STRATEGY", "hybrid")  # "hybrid" | "dense"
    RRF_K: int = int(os.getenv("RRF_K", 60))
    HYBRID_FANOUT: int = int(os.getenv("HYBRID_FANOUT", 50))

    # RAG grounding LLM 관련성 필터 (#305): 답변 근거에서 해로운(rel0) 선례 차단.
    # 기본 OFF → 현재 검색 동작 불변. be3가 search(grounding_filter=True) 또는 env로 켬.
    GROUNDING_FILTER_ENABLED: bool = os.getenv("GROUNDING_FILTER_ENABLED", "false").lower() == "true"
    GROUNDING_FILTER_MODEL: str = os.getenv("GROUNDING_FILTER_MODEL", "")  # 빈값이면 OLLAMA_MODEL
    GROUNDING_FILTER_MIN_SCORE: int = int(os.getenv("GROUNDING_FILTER_MIN_SCORE", 1))
    GROUNDING_FILTER_POOL: int = int(os.getenv("GROUNDING_FILTER_POOL", 10))
    GROUNDING_FILTER_MAX_CONCURRENCY: int = int(os.getenv("GROUNDING_FILTER_MAX_CONCURRENCY", 5))

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

    # 구조화 전용 Ollama 설정 (QA 생성 모델과 분리)
    # exaone3:7.8b-instruct → Ollama 레지스트리 태그: exaone3.5:7.8b
    STRUCTURING_MODEL: str = os.getenv("STRUCTURING_MODEL", "exaone3.5:7.8b")
    STRUCTURING_TIMEOUT: float = float(os.getenv("STRUCTURING_TIMEOUT", "90.0"))
    STRUCTURING_MAX_TEXT_LEN: int = int(os.getenv("STRUCTURING_MAX_TEXT_LEN", "2000"))

    # responsible_unit 도출 (요청 #3) — bge-m3/Chroma 인덱스 필요. 기본 off.
    # 인덱스 빌드(build_index) 후 true 로 켤 것. true 라도 인프라 미가용 시 빈 리스트로 폴백.
    ENABLE_RESPONSIBLE_UNIT: bool = os.getenv("ENABLE_RESPONSIBLE_UNIT", "false").lower() == "true"
    RESPONSIBLE_UNIT_USE_LLM: bool = os.getenv("RESPONSIBLE_UNIT_USE_LLM", "false").lower() == "true"
    # Dense+BM25+RRF 하이브리드 후보 검색. 100건 평가에서 Phase 1-A dense 기본값보다
    # 낮아져 기본 OFF. 재실험/튜닝 시에만 true 로 켠다.
    RESPONSIBLE_UNIT_USE_HYBRID: bool = os.getenv("RESPONSIBLE_UNIT_USE_HYBRID", "false").lower() == "true"
    # CrossEncoder 기반 task 리랭킹. Phase 3 실험용이며, 100건 평가로 채택 여부를
    # 확인하기 전까지 기본 OFF를 유지한다.
    RESPONSIBLE_UNIT_USE_RERANKER: bool = os.getenv("RESPONSIBLE_UNIT_USE_RERANKER", "false").lower() == "true"
    RESPONSIBLE_UNIT_RERANKER_MODEL: str = os.getenv("RESPONSIBLE_UNIT_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    RESPONSIBLE_UNIT_RERANKER_DEVICE: str = os.getenv("RESPONSIBLE_UNIT_RERANKER_DEVICE", EMBEDDING_DEVICE)
    RESPONSIBLE_UNIT_RERANKER_BATCH_SIZE: int = int(os.getenv("RESPONSIBLE_UNIT_RERANKER_BATCH_SIZE", "16"))
    # responsible_unit 신뢰도 하한(soft 후보 억제). 정답셋 없어 미보정 휴리스틱.
    # 기본 0.0: bge-m3 raw cosine 이 0.5~0.65 좁은 띠에 뭉쳐 단일 하한으로 정답/오답을
    # 분리할 수 없음이 확인됨(오답 0.63 > 정답 0.57). 하한 대신 BE2 soft-rerank 에 위임.
    # (랭킹/신뢰도 개선은 별도 리팩토링 — docs/60_specs 참조). env 로 조정 가능.
    RESPONSIBLE_UNIT_MIN_CONFIDENCE: float = float(os.getenv("RESPONSIBLE_UNIT_MIN_CONFIDENCE", "0.0"))

    # 구조화 고도화(Track A): ① 제약 디코딩 / ② 자기검증 (기본 off, 점진 전환)
    # 제약 디코딩은 스키마 안정화 이득이 크고 실패 시 기존 fallback으로 내려가므로 기본으로 사용한다.
    STRUCTURING_CONSTRAINED: bool = os.getenv("STRUCTURING_CONSTRAINED", "true").lower() == "true"
    # 자기검증은 추가 LLM 호출로 지연/비용 리스크가 있어 운영자가 명시적으로 켤 때만 사용한다.
    ENABLE_SELF_VERIFY: bool = os.getenv("ENABLE_SELF_VERIFY", "false").lower() == "true"

    # BE3 법령 조문 인용 그라운딩(Phase B). 인덱스/모델 미가용 시 자동 무동작.
    ENABLE_LEGAL_CITATIONS: bool = os.getenv("ENABLE_LEGAL_CITATIONS", "true").lower() == "true"


settings = Settings()

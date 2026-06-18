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

    # Complaint Intelligence Layer 설정(sidecar). 기존 RAG/라우팅 흐름을 바꾸지 않고
    # 분석 API에서만 사용하는 임계값과 가중치다.
    CI_RECENT_HOURS: int = int(os.getenv("CI_RECENT_HOURS", "3"))
    CI_BASELINE_DAYS: int = int(os.getenv("CI_BASELINE_DAYS", "7"))
    CI_MIN_RECENT_COUNT: int = int(os.getenv("CI_MIN_RECENT_COUNT", "3"))
    CI_MIN_SURGE_RATIO: float = float(os.getenv("CI_MIN_SURGE_RATIO", "2.5"))
    CI_SEMANTIC_THRESHOLD: float = float(os.getenv("CI_SEMANTIC_THRESHOLD", "0.78"))
    CI_MERGE_THRESHOLD: float = float(os.getenv("CI_MERGE_THRESHOLD", "0.84"))
    CI_WATCH_THRESHOLD: float = float(os.getenv("CI_WATCH_THRESHOLD", "0.50"))
    CI_WARNING_THRESHOLD: float = float(os.getenv("CI_WARNING_THRESHOLD", "0.70"))
    CI_CRITICAL_THRESHOLD: float = float(os.getenv("CI_CRITICAL_THRESHOLD", "0.85"))
    CI_INSIGHT_DAYS: int = int(os.getenv("CI_INSIGHT_DAYS", "30"))
    CI_MIN_AFFECTED_COUNT: int = int(os.getenv("CI_MIN_AFFECTED_COUNT", "5"))
    CI_RECURRING_DAYS: int = int(os.getenv("CI_RECURRING_DAYS", "30"))
    CI_MIN_RECURRING_COUNT: int = int(os.getenv("CI_MIN_RECURRING_COUNT", "5"))
    CI_REGIONAL_GAP_MIN_COUNT: int = int(os.getenv("CI_REGIONAL_GAP_MIN_COUNT", "5"))
    CI_DEPARTMENT_BOTTLENECK_MIN_COUNT: int = int(os.getenv("CI_DEPARTMENT_BOTTLENECK_MIN_COUNT", "5"))
    CI_PROCESS_DELAY_HOURS: float = float(os.getenv("CI_PROCESS_DELAY_HOURS", "72"))
    CI_REPEAT_RISK_COUNT: int = int(os.getenv("CI_REPEAT_RISK_COUNT", "3"))
    CI_NIGHT_START_HOUR: int = int(os.getenv("CI_NIGHT_START_HOUR", "20"))
    CI_NIGHT_END_HOUR: int = int(os.getenv("CI_NIGHT_END_HOUR", "6"))
    PUBLIC_INSIGHT_ENABLED: bool = os.getenv("PUBLIC_INSIGHT_ENABLED", "true").lower() == "true"
    PUBLIC_INSIGHT_LLM_ENABLED: bool = os.getenv("PUBLIC_INSIGHT_LLM_ENABLED", "true").lower() == "true"
    PUBLIC_INSIGHT_LLM_PROVIDER: str = os.getenv("PUBLIC_INSIGHT_LLM_PROVIDER", "fake")
    PUBLIC_INSIGHT_LLM_BASE_URL: str = os.getenv("PUBLIC_INSIGHT_LLM_BASE_URL", "")
    PUBLIC_INSIGHT_LLM_MODEL: str = os.getenv("PUBLIC_INSIGHT_LLM_MODEL", "")
    PUBLIC_INSIGHT_LLM_TIMEOUT_SECONDS: float = float(os.getenv("PUBLIC_INSIGHT_LLM_TIMEOUT_SECONDS", "180"))
    PUBLIC_INSIGHT_LLM_TEMPERATURE: float = float(os.getenv("PUBLIC_INSIGHT_LLM_TEMPERATURE", "0"))
    PUBLIC_INSIGHT_LLM_NUM_CTX: int = int(os.getenv("PUBLIC_INSIGHT_LLM_NUM_CTX", "4096"))
    PUBLIC_INSIGHT_LLM_NUM_PREDICT: int = int(os.getenv("PUBLIC_INSIGHT_LLM_NUM_PREDICT", "1536"))
    # Ollama num_gpu=-1은 가능한 GPU 레이어 오프로딩을 요청한다. VRAM이 부족하면 Ollama가 CPU를 함께 사용한다.
    PUBLIC_INSIGHT_LLM_NUM_GPU: int = int(os.getenv("PUBLIC_INSIGHT_LLM_NUM_GPU", "-1"))
    PUBLIC_INSIGHT_LLM_KEEP_ALIVE: str = os.getenv("PUBLIC_INSIGHT_LLM_KEEP_ALIVE", "10m")
    PUBLIC_INSIGHT_LLM_STREAM: bool = os.getenv("PUBLIC_INSIGHT_LLM_STREAM", "true").lower() == "true"
    PUBLIC_INSIGHT_MAX_REPRESENTATIVE_COMPLAINTS: int = int(os.getenv("PUBLIC_INSIGHT_MAX_REPRESENTATIVE_COMPLAINTS", "8"))
    PUBLIC_INSIGHT_MAX_EVIDENCE_CHARS_PER_COMPLAINT: int = int(os.getenv("PUBLIC_INSIGHT_MAX_EVIDENCE_CHARS_PER_COMPLAINT", "500"))
    PUBLIC_INSIGHT_MIN_CANDIDATE_COMPLAINT_COUNT: int = int(os.getenv("PUBLIC_INSIGHT_MIN_CANDIDATE_COMPLAINT_COUNT", "5"))
    PUBLIC_INSIGHT_MIN_GROUNDING_SCORE: float = float(os.getenv("PUBLIC_INSIGHT_MIN_GROUNDING_SCORE", "0.65"))
    PUBLIC_INSIGHT_MIN_CONFIDENCE: float = float(os.getenv("PUBLIC_INSIGHT_MIN_CONFIDENCE", "0.45"))
    PUBLIC_INSIGHT_ANALYSIS_WINDOW_DAYS: int = int(os.getenv("PUBLIC_INSIGHT_ANALYSIS_WINDOW_DAYS", "30"))
    PUBLIC_INSIGHT_RECENT_WINDOW_HOURS: int = int(os.getenv("PUBLIC_INSIGHT_RECENT_WINDOW_HOURS", "3"))
    PUBLIC_INSIGHT_BASELINE_WINDOW_DAYS: int = int(os.getenv("PUBLIC_INSIGHT_BASELINE_WINDOW_DAYS", "7"))
    PUBLIC_INSIGHT_HIGH_REPEAT_COUNT: int = int(os.getenv("PUBLIC_INSIGHT_HIGH_REPEAT_COUNT", "10"))
    PUBLIC_INSIGHT_PROCESS_DELAY_MINUTES_THRESHOLD: int = int(os.getenv("PUBLIC_INSIGHT_PROCESS_DELAY_MINUTES_THRESHOLD", "1440"))
    PUBLIC_INSIGHT_REOPEN_RATE_THRESHOLD: float = float(os.getenv("PUBLIC_INSIGHT_REOPEN_RATE_THRESHOLD", "0.20"))
    PUBLIC_INSIGHT_REGIONAL_CONCENTRATION_THRESHOLD: float = float(os.getenv("PUBLIC_INSIGHT_REGIONAL_CONCENTRATION_THRESHOLD", "0.40"))
    PUBLIC_INSIGHT_PRIORITY_HIGH_THRESHOLD: float = float(os.getenv("PUBLIC_INSIGHT_PRIORITY_HIGH_THRESHOLD", "0.70"))
    PUBLIC_INSIGHT_PRIORITY_CRITICAL_THRESHOLD: float = float(os.getenv("PUBLIC_INSIGHT_PRIORITY_CRITICAL_THRESHOLD", "0.85"))
    PUBLIC_INSIGHT_FALLBACK_ON_LLM_ERROR: bool = os.getenv("PUBLIC_INSIGHT_FALLBACK_ON_LLM_ERROR", "true").lower() == "true"
    PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_POLICY: bool = os.getenv("PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_POLICY", "true").lower() == "true"
    PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_SAFETY: bool = os.getenv("PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_SAFETY", "true").lower() == "true"
    CI_SCORE_WEIGHT_COUNT: float = float(os.getenv("CI_SCORE_WEIGHT_COUNT", "0.30"))
    CI_SCORE_WEIGHT_SURGE: float = float(os.getenv("CI_SCORE_WEIGHT_SURGE", "0.25"))
    CI_SCORE_WEIGHT_COHESION: float = float(os.getenv("CI_SCORE_WEIGHT_COHESION", "0.20"))
    CI_SCORE_WEIGHT_SPATIAL: float = float(os.getenv("CI_SCORE_WEIGHT_SPATIAL", "0.15"))
    CI_SCORE_WEIGHT_RISK: float = float(os.getenv("CI_SCORE_WEIGHT_RISK", "0.10"))

    # Civil Complaint LLM-Rubric vNext: QA 초안 생성 직후 운영 응답에 평가 리포트를 붙인다.
    ENABLE_CIVIL_LLM_RUBRIC: bool = os.getenv("ENABLE_CIVIL_LLM_RUBRIC", "true").lower() == "true"
    CIVIL_LLM_RUBRIC_USE_LLM_JUDGE: bool = os.getenv("CIVIL_LLM_RUBRIC_USE_LLM_JUDGE", "true").lower() == "true"
    CIVIL_LLM_RUBRIC_VERSION: str = os.getenv(
        "CIVIL_LLM_RUBRIC_VERSION",
        "civil_llm_rubric_q0_q7_v1.0",
    )
    CIVIL_LLM_RUBRIC_JUDGE_PROMPT_VERSION: str = os.getenv(
        "CIVIL_LLM_RUBRIC_JUDGE_PROMPT_VERSION",
        "judge_prompt_2026_06_18",
    )
    CIVIL_LLM_RUBRIC_MAX_CONTEXTS: int = int(os.getenv("CIVIL_LLM_RUBRIC_MAX_CONTEXTS", "5"))
    CIVIL_LLM_RUBRIC_TEMPERATURE: float = float(os.getenv("CIVIL_LLM_RUBRIC_TEMPERATURE", "0.0"))
    ENABLE_PROMETHEUS_RUBRIC_FEEDBACK: bool = os.getenv(
        "ENABLE_PROMETHEUS_RUBRIC_FEEDBACK",
        "true",
    ).lower() == "true"
    PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE: float = float(
        os.getenv("PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE", "2.0")
    )
    PROMETHEUS_RUBRIC_MAX_REGENERATION_ATTEMPTS: int = int(
        os.getenv("PROMETHEUS_RUBRIC_MAX_REGENERATION_ATTEMPTS", "1")
    )
    PROMETHEUS_RUBRIC_TEMPERATURE: float = float(
        os.getenv("PROMETHEUS_RUBRIC_TEMPERATURE", "0.0")
    )


settings = Settings()

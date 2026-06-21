"""Complaint Intelligence Layer 설정 어댑터."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class ComplaintIntelligenceConfig:
    """핫스팟 감지와 공공기관 인사이트 규칙에 쓰는 설정값."""

    recent_hours: int
    baseline_days: int
    min_recent_count: int
    min_surge_ratio: float
    semantic_threshold: float
    merge_threshold: float
    watch_threshold: float
    warning_threshold: float
    critical_threshold: float
    insight_days: int
    min_affected_count: int
    recurring_days: int
    min_recurring_count: int
    regional_gap_min_count: int
    department_bottleneck_min_count: int
    process_delay_hours: float
    repeat_risk_count: int
    night_start_hour: int
    night_end_hour: int
    public_insight_enabled: bool
    public_insight_llm_enabled: bool
    public_insight_llm_provider: str
    public_insight_llm_base_url: str
    public_insight_llm_model: str
    public_insight_llm_timeout_seconds: float
    public_insight_llm_temperature: float
    public_insight_llm_num_ctx: int
    public_insight_llm_num_predict: int
    public_insight_llm_num_gpu: int
    public_insight_llm_keep_alive: str
    public_insight_llm_stream: bool
    public_insight_max_representative_complaints: int
    public_insight_max_evidence_chars_per_complaint: int
    public_insight_min_candidate_complaint_count: int
    public_insight_min_grounding_score: float
    public_insight_min_confidence: float
    public_insight_analysis_window_days: int
    public_insight_recent_window_hours: int
    public_insight_baseline_window_days: int
    public_insight_high_repeat_count: int
    public_insight_process_delay_minutes_threshold: int
    public_insight_reopen_rate_threshold: float
    public_insight_regional_concentration_threshold: float
    public_insight_priority_high_threshold: float
    public_insight_priority_critical_threshold: float
    public_insight_fallback_on_llm_error: bool
    public_insight_require_human_review_for_policy: bool
    public_insight_require_human_review_for_safety: bool
    score_weight_count: float
    score_weight_surge: float
    score_weight_cohesion: float
    score_weight_spatial: float
    score_weight_risk: float
    public_insight_llm_prompt_mode: str = "default"
    public_insight_llm_debug_raw_response: bool = False
    public_insight_llm_debug_raw_response_dir: str = "reports/llm_raw"
    public_insight_llm_debug_raw_response_max_chars: int = 4000
    public_insight_llm_action_retry_enabled: bool = False
    repository: str = "sqlite"
    db_path: str = "data/complaint_intelligence/complaint_intelligence.db"
    default_mode: str = "realtime"
    retention_days: int = 90
    auto_create_db: bool = True
    scheduler_enabled: bool = False
    scheduler_interval_seconds: float = 300.0
    scheduler_batch_size: int = 500
    scheduler_min_events: int = 1
    scheduler_source_name: str = "repository_realtime"
    scheduler_mode: str = "realtime"
    collector: str = "repository_replay"
    collector_limit: int = 500
    collector_source_name: str = "repository_replay"
    checkpoint_enabled: bool = True
    public_insight_llm_slow_ms: float = 180000.0


def get_complaint_intelligence_config() -> ComplaintIntelligenceConfig:
    """환경변수에서 읽은 설정을 sidecar 전용 객체로 변환한다."""

    return ComplaintIntelligenceConfig(
        recent_hours=settings.CI_RECENT_HOURS,
        baseline_days=settings.CI_BASELINE_DAYS,
        min_recent_count=settings.CI_MIN_RECENT_COUNT,
        min_surge_ratio=settings.CI_MIN_SURGE_RATIO,
        semantic_threshold=settings.CI_SEMANTIC_THRESHOLD,
        merge_threshold=settings.CI_MERGE_THRESHOLD,
        watch_threshold=settings.CI_WATCH_THRESHOLD,
        warning_threshold=settings.CI_WARNING_THRESHOLD,
        critical_threshold=settings.CI_CRITICAL_THRESHOLD,
        insight_days=settings.CI_INSIGHT_DAYS,
        min_affected_count=settings.CI_MIN_AFFECTED_COUNT,
        recurring_days=settings.CI_RECURRING_DAYS,
        min_recurring_count=settings.CI_MIN_RECURRING_COUNT,
        regional_gap_min_count=settings.CI_REGIONAL_GAP_MIN_COUNT,
        department_bottleneck_min_count=settings.CI_DEPARTMENT_BOTTLENECK_MIN_COUNT,
        process_delay_hours=settings.CI_PROCESS_DELAY_HOURS,
        repeat_risk_count=settings.CI_REPEAT_RISK_COUNT,
        night_start_hour=settings.CI_NIGHT_START_HOUR,
        night_end_hour=settings.CI_NIGHT_END_HOUR,
        public_insight_enabled=settings.PUBLIC_INSIGHT_ENABLED,
        public_insight_llm_enabled=settings.PUBLIC_INSIGHT_LLM_ENABLED,
        public_insight_llm_provider=settings.PUBLIC_INSIGHT_LLM_PROVIDER,
        public_insight_llm_base_url=settings.PUBLIC_INSIGHT_LLM_BASE_URL,
        public_insight_llm_model=settings.PUBLIC_INSIGHT_LLM_MODEL,
        public_insight_llm_timeout_seconds=settings.PUBLIC_INSIGHT_LLM_TIMEOUT_SECONDS,
        public_insight_llm_temperature=settings.PUBLIC_INSIGHT_LLM_TEMPERATURE,
        public_insight_llm_num_ctx=settings.PUBLIC_INSIGHT_LLM_NUM_CTX,
        public_insight_llm_num_predict=settings.PUBLIC_INSIGHT_LLM_NUM_PREDICT,
        public_insight_llm_num_gpu=settings.PUBLIC_INSIGHT_LLM_NUM_GPU,
        public_insight_llm_keep_alive=settings.PUBLIC_INSIGHT_LLM_KEEP_ALIVE,
        public_insight_llm_stream=settings.PUBLIC_INSIGHT_LLM_STREAM,
        public_insight_llm_prompt_mode=settings.PUBLIC_INSIGHT_LLM_PROMPT_MODE,
        public_insight_llm_debug_raw_response=settings.PUBLIC_INSIGHT_LLM_DEBUG_RAW_RESPONSE,
        public_insight_llm_debug_raw_response_dir=settings.PUBLIC_INSIGHT_LLM_DEBUG_RAW_RESPONSE_DIR,
        public_insight_llm_debug_raw_response_max_chars=settings.PUBLIC_INSIGHT_LLM_DEBUG_RAW_RESPONSE_MAX_CHARS,
        public_insight_llm_action_retry_enabled=settings.PUBLIC_INSIGHT_LLM_ACTION_RETRY_ENABLED,
        public_insight_max_representative_complaints=settings.PUBLIC_INSIGHT_MAX_REPRESENTATIVE_COMPLAINTS,
        public_insight_max_evidence_chars_per_complaint=settings.PUBLIC_INSIGHT_MAX_EVIDENCE_CHARS_PER_COMPLAINT,
        public_insight_min_candidate_complaint_count=settings.PUBLIC_INSIGHT_MIN_CANDIDATE_COMPLAINT_COUNT,
        public_insight_min_grounding_score=settings.PUBLIC_INSIGHT_MIN_GROUNDING_SCORE,
        public_insight_min_confidence=settings.PUBLIC_INSIGHT_MIN_CONFIDENCE,
        public_insight_analysis_window_days=settings.PUBLIC_INSIGHT_ANALYSIS_WINDOW_DAYS,
        public_insight_recent_window_hours=settings.PUBLIC_INSIGHT_RECENT_WINDOW_HOURS,
        public_insight_baseline_window_days=settings.PUBLIC_INSIGHT_BASELINE_WINDOW_DAYS,
        public_insight_high_repeat_count=settings.PUBLIC_INSIGHT_HIGH_REPEAT_COUNT,
        public_insight_process_delay_minutes_threshold=settings.PUBLIC_INSIGHT_PROCESS_DELAY_MINUTES_THRESHOLD,
        public_insight_reopen_rate_threshold=settings.PUBLIC_INSIGHT_REOPEN_RATE_THRESHOLD,
        public_insight_regional_concentration_threshold=settings.PUBLIC_INSIGHT_REGIONAL_CONCENTRATION_THRESHOLD,
        public_insight_priority_high_threshold=settings.PUBLIC_INSIGHT_PRIORITY_HIGH_THRESHOLD,
        public_insight_priority_critical_threshold=settings.PUBLIC_INSIGHT_PRIORITY_CRITICAL_THRESHOLD,
        public_insight_fallback_on_llm_error=settings.PUBLIC_INSIGHT_FALLBACK_ON_LLM_ERROR,
        public_insight_require_human_review_for_policy=settings.PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_POLICY,
        public_insight_require_human_review_for_safety=settings.PUBLIC_INSIGHT_REQUIRE_HUMAN_REVIEW_FOR_SAFETY,
        score_weight_count=settings.CI_SCORE_WEIGHT_COUNT,
        score_weight_surge=settings.CI_SCORE_WEIGHT_SURGE,
        score_weight_cohesion=settings.CI_SCORE_WEIGHT_COHESION,
        score_weight_spatial=settings.CI_SCORE_WEIGHT_SPATIAL,
        score_weight_risk=settings.CI_SCORE_WEIGHT_RISK,
        repository=settings.COMPLAINT_INTELLIGENCE_REPOSITORY,
        db_path=settings.COMPLAINT_INTELLIGENCE_DB_PATH,
        default_mode=settings.COMPLAINT_INTELLIGENCE_DEFAULT_MODE,
        retention_days=settings.COMPLAINT_INTELLIGENCE_RETENTION_DAYS,
        auto_create_db=settings.COMPLAINT_INTELLIGENCE_AUTO_CREATE_DB,
        scheduler_enabled=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_ENABLED,
        scheduler_interval_seconds=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_INTERVAL_SECONDS,
        scheduler_batch_size=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_BATCH_SIZE,
        scheduler_min_events=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_MIN_EVENTS,
        scheduler_source_name=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_SOURCE_NAME,
        scheduler_mode=settings.COMPLAINT_INTELLIGENCE_SCHEDULER_MODE,
        collector=settings.COMPLAINT_INTELLIGENCE_COLLECTOR,
        collector_limit=settings.COMPLAINT_INTELLIGENCE_COLLECTOR_LIMIT,
        collector_source_name=settings.COMPLAINT_INTELLIGENCE_COLLECTOR_SOURCE_NAME,
        checkpoint_enabled=settings.COMPLAINT_INTELLIGENCE_CHECKPOINT_ENABLED,
        public_insight_llm_slow_ms=settings.PUBLIC_INSIGHT_LLM_SLOW_MS,
    )

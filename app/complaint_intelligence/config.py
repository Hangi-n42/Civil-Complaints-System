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
    )

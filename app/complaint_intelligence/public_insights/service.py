"""PublicAgencyInsight 생성 orchestration 서비스."""

from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Any

from app.complaint_intelligence.config import (
    ComplaintIntelligenceConfig,
    get_complaint_intelligence_config,
)
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.action_repair import repair_action_evidence_ids
from app.complaint_intelligence.public_insights.action_rubric import requires_human_review_for_pack
from app.complaint_intelligence.public_insights.aspect_extractor import AspectExtractor
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidateGenerator
from app.complaint_intelligence.public_insights.evidence_pack import EvidencePackBuilder, PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.fallback_templates import PublicInsightFallbackGenerator
from app.complaint_intelligence.public_insights.grounding_verifier import GroundingVerifier
from app.complaint_intelligence.public_insights.insight_ranker import PublicInsightRanker
from app.complaint_intelligence.public_insights.llm_provider import build_llm_provider, PublicInsightLLMProvider
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicAgencyInsightDraft, PublicInsightLLMSynthesizer
from app.complaint_intelligence.public_insights.quality_gate import (
    InsightQualityGate,
    attach_actionability_metrics,
)
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight


class PublicInsightService:
    """EvidencePack 기반 공공기관 인사이트 생성 기본 경로."""

    def __init__(
        self,
        config: ComplaintIntelligenceConfig | None = None,
        candidate_generator: PublicInsightCandidateGenerator | None = None,
        evidence_pack_builder: EvidencePackBuilder | None = None,
        aspect_extractor: AspectExtractor | None = None,
        llm_provider: PublicInsightLLMProvider | None = None,
        grounding_verifier: GroundingVerifier | None = None,
        insight_ranker: PublicInsightRanker | None = None,
        fallback_generator: PublicInsightFallbackGenerator | None = None,
        quality_gate: InsightQualityGate | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or get_complaint_intelligence_config()
        self.candidate_generator = candidate_generator or PublicInsightCandidateGenerator(config=self.config)
        self.evidence_pack_builder = evidence_pack_builder or EvidencePackBuilder(config=self.config)
        self.aspect_extractor = aspect_extractor or AspectExtractor()
        provider = llm_provider or build_llm_provider(self.config)
        self.llm_synthesizer = PublicInsightLLMSynthesizer(
            provider,
            prompt_mode=self.config.public_insight_llm_prompt_mode,
        )
        self.grounding_verifier = grounding_verifier or GroundingVerifier()
        self.insight_ranker = insight_ranker or PublicInsightRanker(config=self.config)
        self.fallback_generator = fallback_generator or PublicInsightFallbackGenerator()
        self.quality_gate = quality_gate or InsightQualityGate(
            min_grounding_score=self.config.public_insight_min_grounding_score,
            min_confidence=self.config.public_insight_min_confidence,
        )
        self.logger = logger or logging.getLogger(__name__)
        self._evidence_pack_by_insight_id: dict[str, PublicInsightEvidencePack] = {}
        self._last_generation_metrics: dict[str, Any] = {}

    def generate_insights(
        self,
        events: list[ComplaintIntelligenceEvent],
        issue_alerts: list[IssueAlert] | None = None,
        now: datetime | None = None,
    ) -> list[PublicAgencyInsight]:
        """공공기관 인사이트를 생성하고 중복을 제거해 우선순위순으로 반환한다."""

        started_at = perf_counter()
        if not self.config.public_insight_enabled:
            self._last_generation_metrics = _generation_metrics(
                config=self.config,
                provider=self.llm_synthesizer.provider,
                candidate_count=0,
                insight_count=0,
                duration_ms=_elapsed_ms(started_at),
                traces=[],
                enabled=False,
            )
            return []

        candidates = self.candidate_generator.generate(events, issue_alerts or [], now)
        insights: list[PublicAgencyInsight] = []
        traces: list[dict[str, Any]] = []

        for candidate in candidates:
            pack = self.evidence_pack_builder.build(candidate, events, issue_alerts or [])
            pack = self.aspect_extractor.enrich(pack)

            insight, trace = self._generate_one(pack, now)
            traces.append(trace)
            if insight is not None:
                self._evidence_pack_by_insight_id[insight.insight_id] = pack
                insights.append(insight)

        result = _dedupe_and_sort(insights)
        self._last_generation_metrics = _generation_metrics(
            config=self.config,
            provider=self.llm_synthesizer.provider,
            candidate_count=len(candidates),
            insight_count=len(result),
            duration_ms=_elapsed_ms(started_at),
            traces=traces,
            enabled=True,
        )
        return result

    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """생성된 인사이트의 마스킹된 EvidencePack을 debug 용도로 반환한다."""

        return self._evidence_pack_by_insight_id.get(insight_id)

    def get_last_generation_metrics(self) -> dict[str, Any]:
        """최근 PublicAgencyInsight 생성 경로의 비식별 관측 메타데이터를 반환한다."""

        return dict(self._last_generation_metrics)

    def _generate_one(
        self,
        pack: PublicInsightEvidencePack,
        now: datetime | None,
    ) -> tuple[PublicAgencyInsight | None, dict[str, Any]]:
        trace = _candidate_trace(pack)
        if self.config.public_insight_llm_enabled:
            trace["llm_attempted"] = True
            llm_started_at = perf_counter()
            try:
                draft = self.llm_synthesizer.synthesize(pack)
                trace["llm_draft_summary"] = _draft_summary(draft)
                trace["llm_duration_ms"] = _elapsed_ms(llm_started_at)
                ranked, failure_reason = self._rank_after_action_repair(draft, pack, now, trace, report_key="action_repair_report")
                if ranked is not None:
                    trace["path"] = "llm"
                    trace["llm_success"] = True
                    return ranked, trace
                if failure_reason == "EMPTY_ACTIONS" and self._should_retry_actions():
                    trace["pre_retry_failure_reason"] = failure_reason
                    retry_started_at = perf_counter()
                    trace["action_retry_attempted"] = True
                    try:
                        retry_actions = self.llm_synthesizer.synthesize_actions(draft, pack)
                        trace["action_retry_duration_ms"] = _elapsed_ms(retry_started_at)
                        retry_draft = draft.model_copy(update={"recommended_actions": retry_actions})
                        trace["action_retry_draft_summary"] = {"recommended_actions": _action_summaries(retry_actions)}
                        ranked_retry, retry_failure_reason = self._rank_after_action_repair(
                            retry_draft,
                            pack,
                            now,
                            trace,
                            report_key="action_retry_repair_report",
                        )
                        if ranked_retry is not None:
                            trace["path"] = "llm_action_retry"
                            trace["llm_success"] = True
                            trace["action_retry_success"] = True
                            return ranked_retry, trace
                        trace["action_retry_failure_reason"] = retry_failure_reason
                    except Exception as retry_exc:  # noqa: BLE001 - retry 실패는 fallback으로 격리한다.
                        trace["action_retry_duration_ms"] = _elapsed_ms(retry_started_at)
                        trace["action_retry_failure_type"] = type(retry_exc).__name__
                        trace["action_retry_failure_reason"] = getattr(retry_exc, "reason", _llm_failure_reason(retry_exc))
                trace["llm_failure_reason"] = failure_reason
            except Exception as exc:  # noqa: BLE001 - fallback을 위한 안전 경계
                # 민원 원문/근거 텍스트는 로그에 남기지 않는다.
                trace["llm_duration_ms"] = _elapsed_ms(llm_started_at)
                trace["llm_failure_type"] = type(exc).__name__
                trace["llm_failure_reason"] = getattr(exc, "reason", _llm_failure_reason(exc))
                repair_steps = getattr(exc, "repair_steps", None)
                if repair_steps:
                    trace["llm_repair_steps"] = list(repair_steps)
                raw_debug_path = getattr(exc, "raw_debug_path", None)
                if raw_debug_path:
                    trace["llm_raw_debug_path"] = str(raw_debug_path)
                self.logger.warning("Public insight LLM path failed: %s", type(exc).__name__)

        if not self.config.public_insight_fallback_on_llm_error:
            trace["path"] = "discarded"
            trace["discard_reason"] = "fallback_disabled"
            return None, trace
        fallback_started_at = perf_counter()
        fallback = self.fallback_generator.generate(pack, reason="LLM 경로 실패 또는 품질 게이트 실패")
        ranked_fallback = attach_actionability_metrics(self.insight_ranker.rank(fallback, pack, now))
        trace["fallback_used"] = True
        trace["fallback_duration_ms"] = _elapsed_ms(fallback_started_at)
        trace["grounding_score"] = ranked_fallback.grounding_score
        trace["confidence"] = ranked_fallback.confidence
        trace["avg_actionability_score"] = ranked_fallback.metrics.get("avg_actionability_score", 0.0)
        trace["min_actionability_score"] = ranked_fallback.metrics.get("min_actionability_score", 0.0)
        gate_result = self.quality_gate.evaluate(ranked_fallback, pack)
        trace["quality_gate_score"] = gate_result.score
        trace["quality_gate_failures"] = [failure.model_dump(mode="json") for failure in gate_result.failures]
        trace["quality_gate_warnings"] = [warning.model_dump(mode="json") for warning in gate_result.warnings]
        if gate_result.passed:
            trace["path"] = "fallback"
            return ranked_fallback, trace
        self.logger.warning(
            "Public insight fallback discarded by quality gate: codes=%s",
            [failure.code for failure in gate_result.failures],
        )
        trace["path"] = "discarded"
        trace["discard_reason"] = "fallback_quality_gate_failed"
        return None, trace

    def _rank_after_action_repair(
        self,
        draft: PublicAgencyInsightDraft,
        pack: PublicInsightEvidencePack,
        now: datetime | None,
        trace: dict[str, Any],
        *,
        report_key: str,
    ) -> tuple[PublicAgencyInsight | None, str | None]:
        repaired_draft, repair_report = repair_action_evidence_ids(draft, pack)
        trace[report_key] = repair_report.model_dump(mode="json")
        verified = self.grounding_verifier.verify_and_repair(repaired_draft, pack)
        ranked = attach_actionability_metrics(self.insight_ranker.rank(verified, pack, now))
        ranked, human_review_report = _apply_human_review_policy(ranked, pack)
        trace["human_review_postprocess"] = human_review_report
        trace["grounding_score"] = ranked.grounding_score
        trace["confidence"] = ranked.confidence
        trace["avg_actionability_score"] = ranked.metrics.get("avg_actionability_score", 0.0)
        trace["min_actionability_score"] = ranked.metrics.get("min_actionability_score", 0.0)
        if (
            ranked.grounding_score >= self.config.public_insight_min_grounding_score
            and ranked.confidence >= self.config.public_insight_min_confidence
            and ranked.recommended_actions
        ):
            gate_result = self.quality_gate.evaluate(ranked, pack)
            trace["quality_gate_score"] = gate_result.score
            trace["quality_gate_failures"] = [failure.model_dump(mode="json") for failure in gate_result.failures]
            trace["quality_gate_warnings"] = [warning.model_dump(mode="json") for warning in gate_result.warnings]
            if gate_result.passed:
                return ranked, None
            self.logger.warning(
                "Public insight quality gate failed: codes=%s",
                [failure.code for failure in gate_result.failures],
            )
            return None, "QUALITY_GATE_FAILED"
        return None, _ranked_failure_reason(ranked, self.config)

    def _should_retry_actions(self) -> bool:
        return (
            str(self.config.public_insight_llm_provider).lower() == "local"
            or self.config.public_insight_llm_action_retry_enabled
        )


def _candidate_trace(pack: PublicInsightEvidencePack) -> dict[str, Any]:
    """후보별 LLM/품질 게이트 경로를 PII 없이 추적한다."""

    return {
        "candidate_id": pack.candidate_id,
        "type_hint": str(pack.type_hint or ""),
        "topic_label": mask_pii(pack.topic_label).text,
        "complaint_count": pack.complaint_count,
        "linked_alert_count": len(pack.linked_alert_ids),
        "llm_attempted": False,
        "llm_success": False,
        "fallback_used": False,
        "path": "pending",
    }


def _llm_failure_reason(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "LLM_TIMEOUT"
    text = str(exc)
    if "PUBLIC_INSIGHT_DRAFT_SCHEMA_INVALID" in text:
        return "LLM_SCHEMA_VALIDATION_FAILED"
    if "QUALITY_GATE_FAILED" in text:
        return "QUALITY_GATE_FAILED"
    if "GROUNDING" in text:
        return "GROUNDING_FAILED"
    if "JSON" in type(exc).__name__.upper() or "JSON" in text.upper():
        return "LLM_JSON_PARSE_FAILED"
    if "REQUEST_FAILED" in text or "URL" in type(exc).__name__.upper():
        return "LLM_REQUEST_FAILED"
    return "LLM_REQUEST_FAILED"


def _ranked_failure_reason(insight: PublicAgencyInsight, config: ComplaintIntelligenceConfig) -> str:
    if not insight.recommended_actions:
        return "EMPTY_ACTIONS"
    if insight.grounding_score < config.public_insight_min_grounding_score:
        return "LOW_GROUNDING_SCORE"
    if insight.confidence < config.public_insight_min_confidence:
        return "CONFIDENCE_LOW"
    return "QUALITY_GATE_FAILED"


def _generation_metrics(
    *,
    config: ComplaintIntelligenceConfig,
    provider: Any,
    candidate_count: int,
    insight_count: int,
    duration_ms: float,
    traces: list[dict[str, Any]],
    enabled: bool,
) -> dict[str, Any]:
    """PublicAgencyInsight 생성 실행 단위의 관측 메타데이터를 구성한다."""

    llm_durations = [
        float(trace["llm_duration_ms"])
        for trace in traces
        if isinstance(trace.get("llm_duration_ms"), (int, float))
    ]
    retry_durations = [
        float(trace["action_retry_duration_ms"])
        for trace in traces
        if isinstance(trace.get("action_retry_duration_ms"), (int, float))
    ]
    error_types: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    for trace in traces:
        error_type = trace.get("llm_failure_type")
        if isinstance(error_type, str) and error_type:
            error_types[error_type] = error_types.get(error_type, 0) + 1
        failure_reason = trace.get("llm_failure_reason")
        if isinstance(failure_reason, str) and failure_reason:
            failure_reasons[failure_reason] = failure_reasons.get(failure_reason, 0) + 1

    slow_threshold_ms = config.public_insight_llm_slow_ms
    action_repair_reports = [
        report
        for trace in traces
        for report in (trace.get("action_repair_report"), trace.get("action_retry_repair_report"))
        if isinstance(report, dict)
    ]
    human_review_reports = [
        trace.get("human_review_postprocess")
        for trace in traces
        if isinstance(trace.get("human_review_postprocess"), dict)
    ]
    return {
        "enabled": enabled,
        "llm_enabled": config.public_insight_llm_enabled,
        "llm_provider": config.public_insight_llm_provider,
        "llm_provider_class": provider.__class__.__name__,
        "llm_model": getattr(provider, "model", config.public_insight_llm_model),
        "llm_prompt_mode": config.public_insight_llm_prompt_mode,
        "llm_timeout_seconds": config.public_insight_llm_timeout_seconds,
        "llm_num_predict": config.public_insight_llm_num_predict,
        "raw_response_debug_enabled": config.public_insight_llm_debug_raw_response,
        "action_retry_enabled": config.public_insight_llm_action_retry_enabled
        or str(config.public_insight_llm_provider).lower() == "local",
        "llm_slow_threshold_ms": slow_threshold_ms,
        "duration_ms": round(duration_ms, 3),
        "candidate_count": candidate_count,
        "insight_count": insight_count,
        "llm_attempt_count": sum(1 for trace in traces if trace.get("llm_attempted")),
        "llm_success_count": sum(1 for trace in traces if trace.get("llm_success")),
        "llm_failure_count": sum(1 for trace in traces if trace.get("llm_failure_type") or trace.get("llm_failure_reason")),
        "fallback_count": sum(1 for trace in traces if trace.get("fallback_used")),
        "fallback_due_to_empty_actions_count": sum(
            1
            for trace in traces
            if trace.get("fallback_used") and trace.get("llm_failure_reason") == "EMPTY_ACTIONS"
        ),
        "discarded_count": sum(1 for trace in traces if trace.get("path") == "discarded"),
        "quality_gate_failure_count": sum(1 for trace in traces if trace.get("quality_gate_failures")),
        "slow_llm_count": sum(1 for duration in llm_durations if duration > slow_threshold_ms),
        "avg_llm_duration_ms": round(sum(llm_durations) / len(llm_durations), 3) if llm_durations else 0.0,
        "avg_retry_duration_ms": round(sum(retry_durations) / len(retry_durations), 3) if retry_durations else 0.0,
        "invalid_evidence_id_count": sum(len(report.get("invalid_evidence_ids") or []) for report in action_repair_reports),
        "action_repair_attempt_count": len(action_repair_reports),
        "action_repair_success_count": sum(
            1 for report in action_repair_reports if int(report.get("repaired_action_count") or 0) > 0
        ),
        "action_retry_attempt_count": sum(1 for trace in traces if trace.get("action_retry_attempted")),
        "action_retry_success_count": sum(1 for trace in traces if trace.get("action_retry_success")),
        "empty_actions_after_repair_count": sum(
            1
            for trace in traces
            if trace.get("pre_retry_failure_reason") == "EMPTY_ACTIONS"
            or trace.get("llm_failure_reason") == "EMPTY_ACTIONS"
        ),
        "invalid_action_type_count": sum(int(report.get("invalid_action_type_count") or 0) for report in action_repair_reports),
        "repaired_action_type_count": sum(int(report.get("repaired_action_type_count") or 0) for report in action_repair_reports),
        "repaired_action_text_count": sum(int(report.get("repaired_action_text_count") or 0) for report in action_repair_reports),
        "removed_action_due_to_action_type_count": sum(
            int(report.get("removed_action_due_to_action_type_count") or 0) for report in action_repair_reports
        ),
        "human_review_postprocess_count": sum(1 for report in human_review_reports if report.get("reasons")),
        "action_type_rubric_pass_count": sum(
            1
            for trace in traces
            if isinstance(trace.get("quality_gate_failures"), list)
            and not any(failure.get("code") == "ACTION_TYPE_RUBRIC_INVALID" for failure in trace["quality_gate_failures"])
        ),
        "error_types": error_types,
        "failure_reasons": failure_reasons,
        "json_parse_failure_count": failure_reasons.get("LLM_JSON_PARSE_FAILED", 0),
        "schema_validation_failure_count": failure_reasons.get("LLM_SCHEMA_VALIDATION_FAILED", 0),
        "grounding_failure_count": failure_reasons.get("GROUNDING_FAILED", 0),
        "candidate_trace_count": len(traces),
        "candidate_trace_truncated": len(traces) > 50,
        "candidate_traces": traces[:50],
    }


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _apply_human_review_policy(
    insight: PublicAgencyInsight,
    pack: PublicInsightEvidencePack,
) -> tuple[PublicAgencyInsight, dict[str, Any]]:
    """위험 기반 human review 요구를 deterministic하게 후처리한다."""

    reasons: list[str] = []
    if requires_human_review_for_pack(pack):
        reasons.append("risk_type")
    if insight.priority in {"HIGH", "CRITICAL"}:
        reasons.append("high_priority")
    if insight.grounding_score < 0.8:
        reasons.append("grounding_below_0.8")
    if not reasons:
        return insight, {"changed": False, "reasons": []}
    if insight.requires_human_review:
        metrics = {**insight.metrics, "human_review_policy_applied": 1, "human_review_reasons": ",".join(reasons)}
        return insight.model_copy(update={"metrics": metrics}), {"changed": False, "reasons": reasons}

    uncertainty = [*insight.uncertainty, "위험도/우선순위 기준에 따라 담당자 검토가 필요합니다."]
    metrics = {**insight.metrics, "human_review_policy_applied": 1, "human_review_reasons": ",".join(reasons)}
    return (
        insight.model_copy(
            update={
                "requires_human_review": True,
                "uncertainty": uncertainty,
                "metrics": metrics,
            }
        ),
        {"changed": True, "reasons": reasons},
    )


def _draft_summary(draft: PublicAgencyInsightDraft) -> dict[str, Any]:
    """샘플 리뷰에 필요한 LLM 초안만 PII-safe로 축약한다."""

    return {
        "title": mask_pii(draft.title[:160]).text,
        "summary": mask_pii(draft.summary[:240]).text,
        "problem_diagnosis": mask_pii(draft.problem_diagnosis[:240]).text,
        "root_cause_hypotheses": [
            {
                "hypothesis": mask_pii(item.hypothesis[:180]).text,
                "supporting_evidence_ids": [mask_pii(evidence_id).text for evidence_id in item.supporting_evidence_ids[:3]],
            }
            for item in draft.root_cause_hypotheses[:2]
        ],
        "recommended_actions": _action_summaries(draft.recommended_actions),
        "uncertainty": [mask_pii(item[:160]).text for item in draft.uncertainty[:3]],
    }


def _action_summaries(actions: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "action": mask_pii(str(action.action)[:180]).text,
            "action_type": str(action.action_type),
            "supporting_evidence_ids": [mask_pii(evidence_id).text for evidence_id in action.supporting_evidence_ids[:3]],
        }
        for action in actions[:3]
    ]


def _dedupe_and_sort(insights: list[PublicAgencyInsight]) -> list[PublicAgencyInsight]:
    deduped: dict[str, PublicAgencyInsight] = {}
    for insight in insights:
        overlap_key = (
            insight.type,
            insight.topic,
            (insight.affected_region or {}).get("dominant_region"),
            ",".join(sorted(insight.representative_complaint_ids[:5])),
        )
        key = "|".join(str(item or "") for item in overlap_key)
        current = deduped.get(key)
        if current is None or _rank_tuple(insight) > _rank_tuple(current):
            deduped[key] = insight
    return sorted(deduped.values(), key=_rank_tuple, reverse=True)


def _rank_tuple(insight: PublicAgencyInsight) -> tuple[int, float, int]:
    priority_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(insight.priority, 0)
    return (priority_rank, insight.confidence, insight.affected_count)

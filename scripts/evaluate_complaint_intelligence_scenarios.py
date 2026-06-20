"""Complaint Intelligence 평가 시나리오를 실제 파이프라인으로 검증한다."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.action_rubric import allowed_action_types_for_pack
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidateGenerator
from app.complaint_intelligence.public_insights.engine import PublicAgencyInsightEngine
from app.complaint_intelligence.public_insights.quality_gate import (
    InsightQualityGate,
    score_actionability,
)
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.repository import InMemoryComplaintIntelligenceRepository
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicAgencyInsight,
)
from app.complaint_intelligence.service import ComplaintIntelligenceService


DEFAULT_SCENARIO_FILE = Path("data/evaluation/complaint_intelligence_eval_scenarios.json")
DEFAULT_DEMO_SEED = Path("data/demo/complaint_intelligence_demo_events.json")
DEFAULT_OUTPUT = Path("reports/complaint_intelligence_eval_report.json")
DEFAULT_AS_OF = datetime.fromisoformat("2026-06-20T09:00:00+09:00")

FORBIDDEN_AI_OPS_TERMS = (
    "RAG",
    "retrieval",
    "prompt",
    "model",
    "answer_quality",
    "검색 품질",
    "프롬프트",
    "모델 개선",
    "AI 라우팅",
)
POLICY_OR_SAFETY_TYPES = {
    "SAFETY_RISK_SIGNAL",
    "POLICY_IMPROVEMENT_OPPORTUNITY",
}
SEVERE_ALERTS = {"WARNING", "CRITICAL"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Complaint Intelligence scenarios.")
    parser.add_argument("--scenario-file", default=str(DEFAULT_SCENARIO_FILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--provider", choices=["fake", "local"], default="fake")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--scenario-limit", type=int, default=None)
    parser.add_argument("--scenario-id", default=None)
    parser.add_argument("--llm-timeout-seconds", type=float, default=None)
    parser.add_argument("--llm-num-predict", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--num-predict", type=int, default=None)
    parser.add_argument("--prompt-mode", choices=["default", "compact"], default=None)
    parser.add_argument("--debug-raw-response", action="store_true")
    parser.add_argument("--raw-response-dir", default=None)
    parser.add_argument("--max-candidates-per-scenario", type=int, default=None)
    parser.add_argument("--demo-thresholds", action="store_true")
    parser.add_argument("--include-negative", action="store_true", default=True)
    parser.add_argument("--save-dashboard-snapshots", action="store_true")
    parser.add_argument("--write-default-scenarios", action="store_true")
    parser.add_argument("--baseline-report", default=None)
    args = parser.parse_args()

    scenario_file = Path(args.scenario_file)
    if args.write_default_scenarios or not scenario_file.exists():
        write_default_scenarios(scenario_file)

    max_candidates_per_scenario = args.max_candidates_per_scenario
    if args.provider == "local" and max_candidates_per_scenario is None:
        max_candidates_per_scenario = 1

    report = evaluate_scenario_file(
        scenario_file=scenario_file,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        scenario_limit=args.scenario_limit,
        scenario_id=args.scenario_id,
        include_negative=args.include_negative,
        demo_thresholds=args.demo_thresholds,
        save_dashboard_snapshots=args.save_dashboard_snapshots,
        llm_timeout_seconds=args.timeout_seconds if args.timeout_seconds is not None else args.llm_timeout_seconds,
        llm_num_predict=args.num_predict if args.num_predict is not None else args.llm_num_predict,
        prompt_mode=args.prompt_mode,
        debug_raw_response=args.debug_raw_response,
        raw_response_dir=args.raw_response_dir,
        max_candidates_per_scenario=max_candidates_per_scenario,
    )
    output = Path(args.output)
    if args.baseline_report:
        baseline_report_path = Path(args.baseline_report)
        baseline = json.loads(baseline_report_path.read_text(encoding="utf-8"))
        comparison = compare_reports(baseline, report)
        comparison["baseline_report"] = str(baseline_report_path)
        comparison["after_report"] = str(output)
        report["baseline_comparison"] = comparison
        comparison_path = comparison_output_path(output)
        write_json(comparison_path, comparison)
        write_comparison_markdown(comparison_path.with_suffix(".md"), comparison)
    write_json(output, report)
    write_markdown(output.with_suffix(".md"), report)
    if args.provider == "local":
        sample_json = Path("reports/complaint_intelligence_local_llm_insight_samples.json")
        sample_md = Path("reports/complaint_intelligence_local_llm_insight_samples.md")
        write_local_llm_insight_samples(
            sample_json,
            sample_md,
            report,
        )
        if "action_rubric" in output.stem:
            write_local_llm_insight_samples(
                Path("reports/complaint_intelligence_local_llm_action_rubric_samples.json"),
                Path("reports/complaint_intelligence_local_llm_action_rubric_samples.md"),
                report,
            )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def evaluate_scenario_file(
    *,
    scenario_file: Path,
    provider: str = "fake",
    model: str | None = None,
    base_url: str | None = None,
    scenario_limit: int | None = None,
    scenario_id: str | None = None,
    include_negative: bool = True,
    demo_thresholds: bool = False,
    save_dashboard_snapshots: bool = False,
    llm_timeout_seconds: float | None = None,
    llm_num_predict: int | None = None,
    prompt_mode: str | None = None,
    debug_raw_response: bool = False,
    raw_response_dir: str | None = None,
    max_candidates_per_scenario: int | None = None,
) -> dict[str, Any]:
    """시나리오 파일을 읽어 IssueAlert와 PublicAgencyInsight 품질을 평가한다."""

    started_at = perf_counter()
    scenario_payload = load_scenarios(scenario_file)
    scenarios = list(scenario_payload.get("scenarios") or [])
    requested_count = len(scenarios)
    if scenario_id:
        scenarios = [item for item in scenarios if item.get("scenario_id") == scenario_id]
    if not include_negative:
        scenarios = [item for item in scenarios if item.get("expected_alert") is not False]
    if scenario_limit is not None:
        scenarios = scenarios[: max(0, scenario_limit)]

    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        results.append(
            evaluate_one_scenario(
                scenario,
                as_of=_parse_datetime(scenario_payload.get("as_of")) or DEFAULT_AS_OF,
                provider=provider,
                model=model,
                base_url=base_url,
                demo_thresholds=demo_thresholds,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_num_predict=llm_num_predict,
                prompt_mode=prompt_mode,
                debug_raw_response=debug_raw_response,
                raw_response_dir=raw_response_dir,
                max_candidates_per_scenario=max_candidates_per_scenario,
                save_dashboard_snapshot=save_dashboard_snapshots,
            )
        )

    summary = build_summary(results)
    llm_summary = build_llm_evaluation_summary(results)
    targets = build_target_results(summary, llm_summary)
    return {
        "evaluation_name": "complaint_intelligence_issue_and_public_insight_quality",
        "scenario_file": str(scenario_file),
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "demo_thresholds": demo_thresholds,
        "max_candidates_per_scenario": max_candidates_per_scenario,
        "scenario_count_requested": requested_count,
        "scenario_count_evaluated": len(results),
        "limited_reason": _limited_reason(
            requested_count=requested_count,
            evaluated_count=len(results),
            scenario_limit=scenario_limit,
            scenario_id=scenario_id,
        ),
        "scenario_count": len(results),
        "total_duration_seconds": round(perf_counter() - started_at, 3),
        "targets": targets["targets"],
        "target_results": targets["target_results"],
        "summary": summary,
        "llm_evaluation": llm_summary,
        "scenarios": results,
        "overall_assessment": build_overall_assessment(summary, results, provider),
        "local_llm_manual_command": (
            "civil\\Scripts\\python.exe scripts\\evaluate_complaint_intelligence_scenarios.py "
            "--provider local --model exaone3.5:7.8b --base-url http://localhost:11434 --prompt-mode compact "
            "--output reports\\complaint_intelligence_eval_report_local.json"
        ),
    }


def evaluate_one_scenario(
    scenario: dict[str, Any],
    *,
    as_of: datetime,
    provider: str,
    model: str | None,
    base_url: str | None,
    demo_thresholds: bool,
    llm_timeout_seconds: float | None,
    llm_num_predict: int | None,
    prompt_mode: str | None,
    debug_raw_response: bool,
    raw_response_dir: str | None,
    max_candidates_per_scenario: int | None,
    save_dashboard_snapshot: bool,
) -> dict[str, Any]:
    """단일 시나리오를 격리된 in-memory 저장소에서 실행한다."""

    events = [ComplaintIntelligenceEvent.model_validate(item) for item in scenario.get("events", [])]
    service = build_service(
        provider=provider,
        model=model,
        base_url=base_url,
        demo_thresholds=demo_thresholds,
        llm_timeout_seconds=llm_timeout_seconds,
        llm_num_predict=llm_num_predict,
        prompt_mode=prompt_mode,
        debug_raw_response=debug_raw_response,
        raw_response_dir=raw_response_dir,
        max_candidates_per_scenario=max_candidates_per_scenario,
        preferred_insight_types=[str(item) for item in scenario.get("expected_insight_types") or []],
    )
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    result = service.run_analysis(
        events,
        mode="replay",
        source_name=f"complaint_intelligence_eval:{scenario.get('scenario_id')}",
        as_of=as_of,
        metadata={"trigger": "evaluation", "scenario_id": scenario.get("scenario_id")},
    )
    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()
    event_ids = {event.id for event in events}
    matched_alerts = [alert for alert in alerts if event_ids & set(alert.related_ids)]
    matched_insights = [insight for insight in insights if insight_matches(insight, event_ids, matched_alerts)]

    issue_result = evaluate_issue_detection(scenario, matched_alerts, failures, warnings)
    insight_result = evaluate_public_insights(scenario, matched_insights, service, failures, warnings)
    llm_metrics = latest_llm_metrics(service)
    compact_metrics = compact_llm_metrics(llm_metrics)
    insight_samples = build_insight_samples(
        scenario=scenario,
        provider=provider,
        model=model,
        prompt_mode=prompt_mode,
        insights=matched_insights,
        service=service,
        llm_metrics=llm_metrics,
    )
    dashboard_snapshot = None
    if save_dashboard_snapshot:
        dashboard = service.get_dashboard_state()
        dashboard_snapshot = dashboard.model_dump(mode="json")

    passed = issue_result["passed"] and insight_result["passed"] and not _has_error_failures(failures)
    return {
        "scenario_id": scenario.get("scenario_id"),
        "label": scenario.get("label"),
        "scenario_type": scenario.get("scenario_type"),
        "source_policy": scenario.get("source_policy"),
        "real_event_count": scenario.get("real_event_count", 0),
        "synthetic_event_count": scenario.get("synthetic_event_count", 0),
        "event_count": len(events),
        "run_id": result.run_id,
        "passed": passed,
        "issue_detection_passed": issue_result["passed"],
        "insight_passed": insight_result["passed"],
        "quality_gate_passed": insight_result["quality_gate_passed"],
        "failures": failures,
        "warnings": warnings,
        "issue_detection": issue_result,
        "public_agency_insight": insight_result,
        "generated_alerts": summarize_alerts(matched_alerts),
        "generated_insights": summarize_insights(matched_insights),
        "representative_evidence_ids": insight_result["representative_evidence_ids"],
        "llm_metrics": compact_metrics,
        "direct_llm_success": bool(compact_metrics.get("direct_llm_success_count")),
        "fallback_used": bool(compact_metrics.get("fallback_count")),
        "fallback_reason": compact_metrics.get("failure_reasons"),
        "invalid_evidence_ids": compact_metrics.get("invalid_evidence_ids", []),
        "action_repair_report": compact_metrics.get("action_repair_report"),
        "action_retry_report": compact_metrics.get("action_retry_report"),
        "llm_duration_ms": compact_metrics.get("avg_llm_duration_ms"),
        "retry_duration_ms": compact_metrics.get("avg_retry_duration_ms"),
        "insight_samples": insight_samples,
        "dashboard_snapshot": dashboard_snapshot,
        "objective_assessment": objective_assessment(
            scenario=scenario,
            issue_result=issue_result,
            insight_result=insight_result,
            failures=failures,
            warnings=warnings,
        ),
    }


def build_service(
    *,
    provider: str,
    model: str | None,
    base_url: str | None,
    demo_thresholds: bool,
    llm_timeout_seconds: float | None = None,
    llm_num_predict: int | None = None,
    prompt_mode: str | None = None,
    debug_raw_response: bool = False,
    raw_response_dir: str | None = None,
    max_candidates_per_scenario: int | None = None,
    preferred_insight_types: list[str] | None = None,
) -> ComplaintIntelligenceService:
    """평가용 service를 외부 DB 영향 없이 구성한다."""

    config = replace(
        get_complaint_intelligence_config(),
        repository="memory",
        public_insight_llm_enabled=True,
        public_insight_llm_provider=provider,
    )
    if model:
        config = replace(config, public_insight_llm_model=model)
    if base_url:
        config = replace(config, public_insight_llm_base_url=base_url)
    if llm_timeout_seconds is not None:
        config = replace(config, public_insight_llm_timeout_seconds=llm_timeout_seconds)
    if llm_num_predict is not None:
        config = replace(config, public_insight_llm_num_predict=llm_num_predict)
    if prompt_mode is not None:
        config = replace(config, public_insight_llm_prompt_mode=prompt_mode)
    if debug_raw_response:
        config = replace(config, public_insight_llm_debug_raw_response=True)
    if raw_response_dir:
        config = replace(config, public_insight_llm_debug_raw_response_dir=raw_response_dir)
    if demo_thresholds:
        config = replace(
            config,
            min_recent_count=3,
            min_surge_ratio=1.5,
            public_insight_min_candidate_complaint_count=3,
            min_affected_count=3,
        )
    candidate_generator = None
    if max_candidates_per_scenario is not None:
        candidate_generator = _CappedCandidateGenerator(
            PublicInsightCandidateGenerator(config=config),
            max_candidates=max_candidates_per_scenario,
            preferred_types=set(preferred_insight_types or []),
        )
    public_insight_engine = None
    if candidate_generator is not None:
        public_insight_engine = PublicAgencyInsightEngine(
            config=config,
            service=PublicInsightService(config=config, candidate_generator=candidate_generator),
        )
    return ComplaintIntelligenceService(
        repository=InMemoryComplaintIntelligenceRepository(),
        config=config,
        public_insight_engine=public_insight_engine,
    )


class _CappedCandidateGenerator:
    """수동 Local LLM 평가에서 후보 수를 제한해 실행 시간을 통제한다."""

    def __init__(self, wrapped: PublicInsightCandidateGenerator, *, max_candidates: int, preferred_types: set[str]) -> None:
        self.wrapped = wrapped
        self.max_candidates = max(0, max_candidates)
        self.preferred_types = preferred_types

    def generate(self, events: list[ComplaintIntelligenceEvent], issue_alerts: list[IssueAlert] | None = None, now: datetime | None = None) -> list[Any]:
        candidates = self.wrapped.generate(events, issue_alerts or [], now)
        if self.preferred_types:
            candidates = sorted(candidates, key=lambda item: str(item.type_hint) not in self.preferred_types)
        return candidates[: self.max_candidates]


def evaluate_issue_detection(
    scenario: dict[str, Any],
    alerts: list[IssueAlert],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """IssueAlert 기대치를 평가한다."""

    expected_alert = bool(scenario.get("expected_alert"))
    expected_topics = [str(item) for item in scenario.get("expected_issue_topics") or []]
    severe_alert_count = sum(1 for alert in alerts if alert.severity in SEVERE_ALERTS)
    topic_hit = any(topic_matches(alert, expected_topics) for alert in alerts) if expected_topics else bool(alerts)

    if expected_alert and not alerts:
        failures.append(_failure("ISSUE_ALERT_MISSING", "기대된 IssueAlert가 생성되지 않았습니다."))
    if expected_alert and alerts and not topic_hit:
        failures.append(_failure("ISSUE_TOPIC_MISMATCH", "생성된 alert topic이 기대 topic과 맞지 않습니다."))
    if not expected_alert and severe_alert_count:
        failures.append(_failure("NEGATIVE_FALSE_POSITIVE_ALERT", "negative scenario에서 WARNING 이상 alert가 생성되었습니다."))
    elif not expected_alert and alerts:
        warnings.append(_warning("NEGATIVE_WATCH_ALERT", "negative scenario에서 WATCH 수준 alert가 생성되었습니다."))

    passed = (bool(alerts) and topic_hit) if expected_alert else severe_alert_count == 0
    return {
        "passed": passed,
        "expected_alert": expected_alert,
        "alert_count": len(alerts),
        "severe_alert_count": severe_alert_count,
        "expected_topic_hit": topic_hit,
        "avg_alert_confidence": _avg(alert.confidence for alert in alerts),
        "avg_surge_ratio": _avg(alert.surge_ratio for alert in alerts),
        "avg_recent_count": _avg(alert.recent_count for alert in alerts),
    }


def evaluate_public_insights(
    scenario: dict[str, Any],
    insights: list[PublicAgencyInsight],
    service: ComplaintIntelligenceService,
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """PublicAgencyInsight 기대 타입, action, 근거, 품질 게이트를 평가한다."""

    expected_types = {str(item) for item in scenario.get("expected_insight_types") or []}
    required_aspects = [str(item) for item in scenario.get("required_aspects") or []]
    required_action_types = {str(item) for item in scenario.get("required_action_types") or []}
    selected = select_expected_insights(insights, expected_types)
    quality_gate = InsightQualityGate()
    gate_results = []
    action_scores: list[float] = []
    representative_evidence_ids: set[str] = set()
    evidence_pack_count = 0

    if expected_types and not selected:
        failures.append(_failure("EXPECTED_INSIGHT_TYPE_MISSING", "기대 PublicAgencyInsight type이 생성되지 않았습니다."))
    if scenario.get("expected_alert") and not insights:
        failures.append(_failure("PUBLIC_INSIGHT_MISSING", "PublicAgencyInsight가 생성되지 않았습니다."))

    type_hit = any(str(insight.type) in expected_types for insight in insights) if expected_types else bool(insights)
    aspect_hit = False if required_aspects else True
    action_type_hit = False if required_action_types else True
    allowed_action_type_values: list[bool] = []
    evidence_coverage_values: list[float] = []
    pii_leak = False
    forbidden_terms = False
    human_review_pass = True
    grounding_pass = True
    fallback = False

    for insight in selected or insights:
        pack = service.get_public_insight_evidence_pack(insight.insight_id)
        if pack is not None:
            evidence_pack_count += 1
            allowed_types = set(allowed_action_types_for_pack(pack))
            allowed_action_type_values.extend(str(action.action_type) in allowed_types for action in insight.recommended_actions)
        gate_result = quality_gate.evaluate(insight, pack)
        gate_results.append(gate_result)
        evidence_ids = insight_evidence_ids(insight)
        representative_evidence_ids.update(evidence_ids)
        action_scores.extend(score_actionability(action).score for action in insight.recommended_actions)
        evidence_coverage_values.extend(action_evidence_coverage(insight))
        aspect_hit = aspect_hit or has_required_aspect(insight, required_aspects)
        action_type_hit = action_type_hit or any(
            str(action.action_type) in required_action_types for action in insight.recommended_actions
        )
        pii_leak = pii_leak or contains_unmasked_pii(visible_insight_payload(insight, pack))
        forbidden_terms = forbidden_terms or has_forbidden_ai_ops_terms(visible_insight_payload(insight, pack))
        grounding_pass = grounding_pass and insight.grounding_score >= 0.65
        fallback = fallback or is_fallback_insight(insight)
        if str(insight.type) in POLICY_OR_SAFETY_TYPES:
            human_review_pass = human_review_pass and insight.requires_human_review

    if scenario.get("requires_human_review"):
        review_required = [insight for insight in selected if str(insight.type) in POLICY_OR_SAFETY_TYPES]
        if not review_required:
            review_required = selected
        human_review_pass = human_review_pass and bool(review_required) and all(
            insight.requires_human_review for insight in review_required
        )
    if not expected_types and insights:
        warnings.append(_warning("NEGATIVE_PUBLIC_INSIGHT_CREATED", "negative scenario에서 PublicAgencyInsight가 생성되었습니다."))

    if required_aspects and not aspect_hit:
        failures.append(_failure("REQUIRED_ASPECT_MISSING", "필수 aspect가 추출되지 않았습니다."))
    if required_action_types and not action_type_hit:
        failures.append(_failure("REQUIRED_ACTION_TYPE_MISSING", "필수 action_type이 추천 조치에 없습니다."))
    if selected and not all(insight.recommended_actions for insight in selected):
        failures.append(_failure("RECOMMENDED_ACTION_EMPTY", "추천 조치가 비어 있는 insight가 있습니다."))
    if selected and any(value < 1.0 for value in evidence_coverage_values):
        failures.append(_failure("ACTION_EVIDENCE_COVERAGE_LOW", "추천 조치의 evidence id가 근거에 모두 연결되지 않았습니다."))
    if selected and evidence_pack_count == 0:
        failures.append(_failure("EVIDENCE_PACK_MISSING", "선택된 insight의 EvidencePack을 조회할 수 없습니다."))
    if pii_leak:
        failures.append(_failure("PII_LEAK", "insight 또는 EvidencePack에 원문 PII가 남아 있습니다."))
    if forbidden_terms:
        failures.append(_failure("FORBIDDEN_AI_OPS_TERM", "AI 운영자용 개선 용어가 public insight 출력에 포함되었습니다."))
    if not human_review_pass:
        failures.append(_failure("HUMAN_REVIEW_REQUIREMENT_FAILED", "정책/안전 유형에서 human review 요구가 지켜지지 않았습니다."))
    if not grounding_pass:
        failures.append(_failure("GROUNDING_SCORE_LOW", "grounding_score 기준을 넘지 못했습니다."))

    quality_gate_passed = all(result.passed for result in gate_results) if gate_results else not expected_types
    if gate_results and not quality_gate_passed:
        warnings.append(
            _warning(
                "QUALITY_GATE_WARNING",
                "일부 insight가 QualityGate를 통과하지 못했습니다.",
                {"failures": [failure.code for result in gate_results for failure in result.failures]},
            )
        )

    insight_passed = (
        (type_hit if expected_types else True)
        and aspect_hit
        and action_type_hit
        and bool(selected or not expected_types)
        and not pii_leak
        and not forbidden_terms
        and human_review_pass
        and grounding_pass
    )
    return {
        "passed": insight_passed,
        "insight_count": len(insights),
        "matched_expected_insight_count": len(selected),
        "expected_type_required": bool(expected_types),
        "expected_type_hit": type_hit,
        "required_aspect_hit": aspect_hit,
        "required_action_type_hit": action_type_hit,
        "allowed_action_type_hit_rate": _avg(allowed_action_type_values),
        "action_evidence_coverage_rate": _avg(evidence_coverage_values),
        "evidence_pack_presence_rate": evidence_pack_count / max(1, len(selected or insights)),
        "quality_gate_passed": quality_gate_passed,
        "grounding_pass": grounding_pass,
        "avg_grounding_score": _avg(insight.grounding_score for insight in selected or insights),
        "avg_confidence": _avg(insight.confidence for insight in selected or insights),
        "avg_actionability_score": _avg(action_scores),
        "fallback": fallback,
        "forbidden_ai_ops_terms": forbidden_terms,
        "pii_leak": pii_leak,
        "human_review_requirement_pass": human_review_pass,
        "action_type_rubric_pass": all(allowed_action_type_values) if allowed_action_type_values else True,
        "representative_evidence_ids": sorted(representative_evidence_ids)[:10],
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """scenario 결과에서 전체 지표를 계산한다."""

    positive = [item for item in results if item["issue_detection"]["expected_alert"]]
    negative = [item for item in results if not item["issue_detection"]["expected_alert"]]
    issue = {
        "scenario_count": len(results),
        "positive_scenario_count": len(positive),
        "negative_scenario_count": len(negative),
        "alert_recall": _rate(item["issue_detection"]["alert_count"] > 0 for item in positive),
        "alert_precision_on_negative": _rate(item["issue_detection"]["severe_alert_count"] == 0 for item in negative),
        "expected_alert_hit_rate": _rate(item["issue_detection_passed"] for item in positive),
        "expected_topic_hit_rate": _rate(item["issue_detection"]["expected_topic_hit"] for item in positive),
        "false_positive_count": sum(1 for item in negative if item["issue_detection"]["severe_alert_count"] > 0),
        "false_negative_count": sum(1 for item in positive if item["issue_detection"]["alert_count"] == 0),
        "avg_alert_confidence": _avg(item["issue_detection"]["avg_alert_confidence"] for item in results),
        "avg_surge_ratio": _avg(item["issue_detection"]["avg_surge_ratio"] for item in results),
        "avg_recent_count": _avg(item["issue_detection"]["avg_recent_count"] for item in results),
    }
    insight = {
        "insight_presence_rate": _rate(item["public_agency_insight"]["insight_count"] > 0 for item in results),
        "expected_type_hit_rate": _rate(item["public_agency_insight"]["expected_type_hit"] for item in results if item["public_agency_insight"]["expected_type_required"]),
        "required_aspect_hit_rate": _rate(item["public_agency_insight"]["required_aspect_hit"] for item in results),
        "required_action_type_hit_rate": _rate(item["public_agency_insight"]["required_action_type_hit"] for item in results),
        "allowed_action_type_hit_rate": _avg(
            item["public_agency_insight"].get("allowed_action_type_hit_rate", 1.0) for item in results
        ),
        "action_type_rubric_pass_rate": _rate(
            item["public_agency_insight"].get("action_type_rubric_pass", True) for item in results
        ),
        "action_evidence_coverage_rate": _avg(item["public_agency_insight"]["action_evidence_coverage_rate"] for item in results),
        "evidence_pack_presence_rate": _avg(item["public_agency_insight"]["evidence_pack_presence_rate"] for item in results),
        "grounding_pass_rate": _rate(item["public_agency_insight"]["grounding_pass"] for item in results),
        "avg_grounding_score": _avg(item["public_agency_insight"]["avg_grounding_score"] for item in results),
        "avg_confidence": _avg(item["public_agency_insight"]["avg_confidence"] for item in results),
        "avg_actionability_score": _avg(item["public_agency_insight"]["avg_actionability_score"] for item in results),
        "fallback_rate": _rate(item["public_agency_insight"]["fallback"] for item in results),
        "forbidden_ai_ops_term_rate": _rate(item["public_agency_insight"]["forbidden_ai_ops_terms"] for item in results),
        "pii_leak_rate": _rate(item["public_agency_insight"]["pii_leak"] for item in results),
        "human_review_requirement_pass_rate": _rate(item["public_agency_insight"]["human_review_requirement_pass"] for item in results),
    }
    return {
        "overall_pass_rate": _rate(item["passed"] for item in results),
        "issue_detection": issue,
        "public_agency_insight": insight,
    }


def build_llm_evaluation_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """scenario별 llm_metrics에서 Local LLM 안정성 지표를 집계한다."""

    metrics = [item.get("llm_metrics") or {} for item in results]
    candidate_count = sum(int(item.get("candidate_count") or 0) for item in metrics)
    direct_success_count = sum(int(item.get("direct_llm_success_count") or 0) for item in metrics)
    fallback_count = sum(int(item.get("fallback_count") or 0) for item in metrics)
    failure_count = sum(int(item.get("llm_failure_count") or 0) for item in metrics)
    durations = [
        float(duration)
        for item in metrics
        for duration in item.get("llm_durations_ms", [])
        if isinstance(duration, (int, float))
    ]
    retry_durations = [
        float(duration)
        for item in metrics
        for duration in item.get("retry_durations_ms", [])
        if isinstance(duration, (int, float))
    ]
    providers = sorted({str(item.get("provider")) for item in metrics if item.get("provider")})
    models = sorted({str(item.get("model")) for item in metrics if item.get("model")})
    prompt_modes = sorted({str(item.get("prompt_mode")) for item in metrics if item.get("prompt_mode")})
    return {
        "providers": providers,
        "models": models,
        "prompt_modes": prompt_modes,
        "scenario_count": len(results),
        "candidate_count": candidate_count,
        "direct_llm_success_count": direct_success_count,
        "fallback_count": fallback_count,
        "llm_failure_count": failure_count,
        "fallback_rate": round(fallback_count / max(1, candidate_count), 4),
        "direct_llm_success_rate": round(direct_success_count / max(1, candidate_count), 4),
        "json_parse_failure_count": sum(int(item.get("json_parse_failure_count") or 0) for item in metrics),
        "schema_validation_failure_count": sum(int(item.get("schema_validation_failure_count") or 0) for item in metrics),
        "grounding_failure_count": sum(int(item.get("grounding_failure_count") or 0) for item in metrics),
        "quality_gate_failure_count": sum(int(item.get("quality_gate_failure_count") or 0) for item in metrics),
        "fallback_due_to_empty_actions_count": sum(int(item.get("fallback_due_to_empty_actions_count") or 0) for item in metrics),
        "invalid_evidence_id_count": sum(int(item.get("invalid_evidence_id_count") or 0) for item in metrics),
        "action_repair_attempt_count": sum(int(item.get("action_repair_attempt_count") or 0) for item in metrics),
        "action_repair_success_count": sum(int(item.get("action_repair_success_count") or 0) for item in metrics),
        "invalid_action_type_count": sum(int(item.get("invalid_action_type_count") or 0) for item in metrics),
        "repaired_action_type_count": sum(int(item.get("repaired_action_type_count") or 0) for item in metrics),
        "repaired_action_text_count": sum(int(item.get("repaired_action_text_count") or 0) for item in metrics),
        "removed_action_due_to_action_type_count": sum(
            int(item.get("removed_action_due_to_action_type_count") or 0) for item in metrics
        ),
        "action_retry_attempt_count": sum(int(item.get("action_retry_attempt_count") or 0) for item in metrics),
        "action_retry_success_count": sum(int(item.get("action_retry_success_count") or 0) for item in metrics),
        "empty_actions_after_repair_count": sum(int(item.get("empty_actions_after_repair_count") or 0) for item in metrics),
        "human_review_postprocess_count": sum(int(item.get("human_review_postprocess_count") or 0) for item in metrics),
        "action_type_rubric_pass_count": sum(int(item.get("action_type_rubric_pass_count") or 0) for item in metrics),
        "avg_llm_duration_ms": round(sum(durations) / len(durations), 3) if durations else 0.0,
        "avg_retry_duration_ms": round(sum(retry_durations) / len(retry_durations), 3) if retry_durations else 0.0,
        "p95_llm_duration_ms": _percentile(durations, 0.95),
        "raw_response_debug_enabled": any(bool(item.get("raw_response_debug_enabled")) for item in metrics),
        "speed_metrics": {
            "avg_llm_duration_ms": round(sum(durations) / len(durations), 3) if durations else 0.0,
            "p95_llm_duration_ms": _percentile(durations, 0.95),
            "avg_retry_duration_ms": round(sum(retry_durations) / len(retry_durations), 3) if retry_durations else 0.0,
        },
    }


def build_target_results(summary: dict[str, Any], llm_summary: dict[str, Any]) -> dict[str, Any]:
    """운영 준비 목표와 실제 달성 여부를 함께 기록한다."""

    insight = summary["public_agency_insight"]
    targets = {
        "fallback_rate": "<=0.25",
        "direct_llm_success_rate": ">=0.75",
        "json_parse_failure_count": "0",
        "schema_validation_failure_count": "0",
        "pii_leak_rate": "0",
        "forbidden_ai_ops_term_rate": "0",
    }
    return {
        "targets": targets,
        "target_results": {
            "fallback_rate_met": float(llm_summary.get("fallback_rate", 0.0)) <= 0.25,
            "direct_llm_success_rate_met": float(llm_summary.get("direct_llm_success_rate", 0.0)) >= 0.75,
            "json_parse_failure_count_met": int(llm_summary.get("json_parse_failure_count", 0)) == 0,
            "schema_validation_failure_count_met": int(llm_summary.get("schema_validation_failure_count", 0)) == 0,
            "pii_leak_rate_met": float(insight.get("pii_leak_rate", 0.0)) == 0.0,
            "forbidden_ai_ops_term_rate_met": float(insight.get("forbidden_ai_ops_term_rate", 0.0)) == 0.0,
        },
    }


def compare_reports(baseline: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """baseline/개선 후 평가 리포트의 핵심 지표 delta를 계산한다."""

    baseline_issue = baseline["summary"]["issue_detection"]
    after_issue = after["summary"]["issue_detection"]
    baseline_insight = baseline["summary"]["public_agency_insight"]
    after_insight = after["summary"]["public_agency_insight"]
    deltas = {
        "alert_recall_delta": _delta(after_issue["alert_recall"], baseline_issue["alert_recall"]),
        "topic_hit_rate_delta": _delta(after_issue["expected_topic_hit_rate"], baseline_issue["expected_topic_hit_rate"]),
        "false_positive_delta": after_issue["false_positive_count"] - baseline_issue["false_positive_count"],
        "false_negative_delta": after_issue["false_negative_count"] - baseline_issue["false_negative_count"],
        "expected_type_hit_rate_delta": _delta(after_insight["expected_type_hit_rate"], baseline_insight["expected_type_hit_rate"]),
        "avg_actionability_score_delta": _delta(after_insight["avg_actionability_score"], baseline_insight["avg_actionability_score"]),
        "pii_leak_rate_delta": _delta(after_insight["pii_leak_rate"], baseline_insight["pii_leak_rate"]),
        "forbidden_ai_ops_term_rate_delta": _delta(
            after_insight["forbidden_ai_ops_term_rate"],
            baseline_insight["forbidden_ai_ops_term_rate"],
        ),
    }
    return {
        "baseline_report": baseline.get("scenario_file"),
        "after_report": after.get("scenario_file"),
        "provider": after.get("provider"),
        "baseline": {
            "issue_detection": baseline_issue,
            "public_agency_insight": baseline_insight,
        },
        "after": {
            "issue_detection": after_issue,
            "public_agency_insight": after_insight,
        },
        "deltas": deltas,
        "assessment": _comparison_assessment(deltas),
    }


def _comparison_assessment(deltas: dict[str, float | int]) -> dict[str, list[str]]:
    strengths: list[str] = []
    regressions: list[str] = []
    if deltas["alert_recall_delta"] > 0:
        strengths.append("IssueAlert recall이 baseline보다 개선되었습니다.")
    if deltas["topic_hit_rate_delta"] > 0:
        strengths.append("IssueAlert topic hit rate가 baseline보다 개선되었습니다.")
    if deltas["false_positive_delta"] == 0:
        strengths.append("negative scenario의 false positive count를 유지했습니다.")
    elif deltas["false_positive_delta"] > 0:
        regressions.append("false positive count가 증가했습니다.")
    if deltas["false_negative_delta"] < 0:
        strengths.append("false negative count가 감소했습니다.")
    elif deltas["false_negative_delta"] > 0:
        regressions.append("false negative count가 증가했습니다.")
    for key in ("pii_leak_rate_delta", "forbidden_ai_ops_term_rate_delta"):
        if deltas[key] > 0:
            regressions.append(f"{key}가 증가했습니다.")
    return {"strengths": strengths, "regressions": regressions}


def build_overall_assessment(summary: dict[str, Any], results: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    """제3자 관점의 전체 평가를 과장 없이 구성한다."""

    issue = summary["issue_detection"]
    insight = summary["public_agency_insight"]
    weaknesses = []
    priorities = []
    if issue["false_negative_count"]:
        weaknesses.append("기대된 hotspot scenario 일부에서 IssueAlert가 생성되지 않았습니다.")
        priorities.append("IssueDetection의 의미 군집/지역·시간 기준을 scenario별로 재점검해야 합니다.")
    if issue["false_positive_count"]:
        weaknesses.append("negative scenario에서 WARNING 이상 alert가 생성되어 false positive 위험이 있습니다.")
        priorities.append("낮은 건수와 분산 지역에 대한 alert 억제 조건을 강화해야 합니다.")
    if insight["required_aspect_hit_rate"] < 0.8:
        weaknesses.append("필수 aspect 재현율이 낮아 인사이트 설명력이 제한됩니다.")
        priorities.append("structured_elements와 aspect catalog 매핑을 보강해야 합니다.")
    if insight["avg_actionability_score"] < 0.8:
        weaknesses.append("일부 추천 조치가 실행 단위로 충분히 구체화되지 않았습니다.")
        priorities.append("action catalog와 QualityGate의 actionability 기준을 운영 예시로 보정해야 합니다.")

    return {
        "scope_note": "local provider 결과가 없으면 fake provider 기반 구조 평가이며, 실제 LLM 성능 단정은 아닙니다.",
        "provider_basis": provider,
        "strengths": [
            "실제 run_analysis 경로에서 IssueAlert, PublicAgencyInsight, EvidencePack을 함께 평가했습니다.",
            "추천 조치의 evidence id 연결, PII, 금지 AI 운영 용어를 scenario별로 검사했습니다.",
            "positive/negative scenario를 함께 두어 recall과 false positive 위험을 분리했습니다.",
        ],
        "weaknesses": weaknesses or ["현재 평가 세트에서는 치명적 품질 실패가 두드러지지 않았습니다."],
        "improvement_priorities": priorities
        or ["실제 운영 로그와 local LLM 결과를 누적해 scenario 난이도를 단계적으로 높이는 것이 좋습니다."],
        "fe_demo_fit": (
            "IssueAlert와 PublicAgencyInsight가 모두 생성되고 PII/금지 용어 검사에 통과하면 FE 데모에는 적합합니다. "
            "단, fake provider 기반 수치는 운영 LLM 품질을 보증하지 않습니다."
        ),
    }


def objective_assessment(
    *,
    scenario: dict[str, Any],
    issue_result: dict[str, Any],
    insight_result: dict[str, Any],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """scenario별 제3자 관점 코멘트를 규칙 기반으로 작성한다."""

    strengths: list[str] = []
    weaknesses: list[str] = []
    risks: list[str] = []
    expected_types = set(scenario.get("expected_insight_types") or [])
    if issue_result["alert_count"] > 0:
        strengths.append("유사 민원 묶음에서 IssueAlert를 생성해 관제 화면에 올릴 신호를 만들었습니다.")
    elif scenario.get("expected_alert"):
        weaknesses.append("기대된 hotspot 신호가 alert로 승격되지 않았습니다.")
    if expected_types and insight_result["expected_type_hit"]:
        strengths.append("기대 행정 인사이트 type 중 하나를 생성했습니다.")
    elif not expected_types and insight_result["insight_count"] == 0:
        strengths.append("negative scenario에서 PublicAgencyInsight를 생성하지 않아 과잉 조치를 억제했습니다.")
    else:
        weaknesses.append("시나리오 의도와 다른 PublicAgencyInsight type이 생성되었습니다.")
    if insight_result["action_evidence_coverage_rate"] >= 1.0:
        strengths.append("추천 조치가 근거 민원 ID와 연결되어 추적 가능합니다.")
    elif insight_result["insight_count"] == 0:
        strengths.append("생성된 추천 조치가 없어 evidence 없는 조치도 노출되지 않았습니다.")
    else:
        weaknesses.append("추천 조치 일부가 evidence id와 충분히 연결되지 않았습니다.")
    if insight_result["pii_leak"]:
        risks.append("PII 마스킹 실패가 있어 운영 노출 전 차단이 필요합니다.")
    if insight_result["forbidden_ai_ops_terms"]:
        risks.append("AI 운영자용 개선 용어가 섞여 공공기관 담당자용 표현 정리가 필요합니다.")
    if warnings:
        risks.append("경고 항목은 운영 threshold 보정 시 우선 확인해야 합니다.")
    return {
        "strengths": strengths,
        "weaknesses": weaknesses or ["자동 평가 기준에서 주요 약점은 확인되지 않았습니다."],
        "risk": " ".join(risks) if risks else "실제 운영에서는 위치 정규화와 접수 채널 편차를 추가 검증해야 합니다.",
        "failure_codes": [item["code"] for item in failures],
        "warning_codes": [item["code"] for item in warnings],
    }


def select_expected_insights(
    insights: list[PublicAgencyInsight],
    expected_types: set[str],
) -> list[PublicAgencyInsight]:
    if not expected_types:
        return list(insights)
    return [insight for insight in insights if str(insight.type) in expected_types]


def insight_matches(insight: PublicAgencyInsight, event_ids: set[str], matched_alerts: list[IssueAlert]) -> bool:
    if event_ids & set(insight.representative_complaint_ids):
        return True
    if event_ids & insight_evidence_ids(insight):
        return True
    alert_ids = {alert.id for alert in matched_alerts}
    return bool(alert_ids & set(insight.linked_alert_ids))


def has_required_aspect(insight: PublicAgencyInsight, required_aspects: list[str]) -> bool:
    text = " ".join(
        [
            *(aspect.aspect for aspect in insight.extracted_aspects),
            *(phrase for aspect in insight.extracted_aspects for phrase in aspect.representative_phrases),
        ]
    )
    return any(required in text for required in required_aspects)


def action_evidence_coverage(insight: PublicAgencyInsight) -> list[float]:
    evidence_ids = insight_evidence_ids(insight)
    values: list[float] = []
    for action in insight.recommended_actions:
        if not action.supporting_evidence_ids:
            values.append(0.0)
            continue
        supported = sum(1 for evidence_id in action.supporting_evidence_ids if evidence_id in evidence_ids)
        values.append(supported / len(action.supporting_evidence_ids))
    return values


def insight_evidence_ids(insight: PublicAgencyInsight) -> set[str]:
    ids: set[str] = set()
    for evidence in insight.evidence:
        ids.add(str(evidence.complaint_id))
        ids.update(str(item) for item in evidence.source_complaint_ids)
    return ids


def topic_matches(alert: IssueAlert, expected_topics: list[str]) -> bool:
    if not expected_topics:
        return True
    text = " ".join([alert.topic, alert.title, alert.summary, " ".join(alert.keywords)]).replace(" ", "")
    return any(topic.replace(" ", "") in text for topic in expected_topics)


def visible_insight_payload(insight: PublicAgencyInsight, pack: Any | None) -> dict[str, Any]:
    return {
        "title": insight.title,
        "summary": insight.summary,
        "problem_diagnosis": insight.problem_diagnosis,
        "explanation": insight.explanation,
        "recommended_actions": [action.model_dump(mode="json") for action in insight.recommended_actions],
        "evidence": [item.model_dump(mode="json") for item in insight.evidence],
        "evidence_pack": pack.model_dump(mode="json") if pack is not None else None,
    }


def contains_unmasked_pii(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return bool(mask_pii(text).detected_labels)


def has_forbidden_ai_ops_terms(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return any(term in text for term in FORBIDDEN_AI_OPS_TERMS)


def is_fallback_insight(insight: PublicAgencyInsight) -> bool:
    text = " ".join([insight.explanation, " ".join(insight.uncertainty)])
    return "fallback" in text.lower() or "템플릿" in text or "LLM 인사이트 생성 실패" in text


def latest_llm_metrics(service: ComplaintIntelligenceService) -> dict[str, Any]:
    runs = service.repository.list_analysis_runs(limit=1)
    if not runs:
        return {}
    return dict(runs[0].metadata.get("llm_metrics") or {})


def compact_llm_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    traces = list(metrics.get("candidate_traces") or [])
    durations = [
        float(trace["llm_duration_ms"])
        for trace in traces
        if isinstance(trace.get("llm_duration_ms"), (int, float))
    ]
    retry_durations = [
        float(trace["action_retry_duration_ms"])
        for trace in traces
        if isinstance(trace.get("action_retry_duration_ms"), (int, float))
    ]
    reports = [
        report
        for trace in traces
        for report in (trace.get("action_repair_report"), trace.get("action_retry_repair_report"))
        if isinstance(report, dict)
    ]
    invalid_ids = sorted(
        {
            str(evidence_id)
            for report in reports
            for evidence_id in list(report.get("invalid_evidence_ids") or [])
            if evidence_id
        }
    )
    invalid_action_types = sorted(
        {
            str(action_type)
            for report in reports
            for action_type in list(report.get("invalid_action_types") or [])
            if action_type
        }
    )
    return {
        "provider": metrics.get("llm_provider") or metrics.get("provider"),
        "model": metrics.get("llm_model") or metrics.get("model"),
        "prompt_mode": metrics.get("llm_prompt_mode"),
        "timeout_seconds": metrics.get("llm_timeout_seconds"),
        "num_predict": metrics.get("llm_num_predict"),
        "candidate_count": metrics.get("candidate_count"),
        "insight_count": metrics.get("insight_count"),
        "direct_llm_success_count": metrics.get("llm_success_count"),
        "llm_failure_count": metrics.get("llm_failure_count"),
        "fallback_count": metrics.get("fallback_count"),
        "fallback_due_to_empty_actions_count": metrics.get("fallback_due_to_empty_actions_count", 0),
        "discarded_count": metrics.get("discarded_count"),
        "avg_llm_duration_ms": metrics.get("avg_llm_duration_ms"),
        "avg_retry_duration_ms": metrics.get("avg_retry_duration_ms", 0.0),
        "llm_durations_ms": durations,
        "retry_durations_ms": retry_durations,
        "json_parse_failure_count": metrics.get("json_parse_failure_count", 0),
        "schema_validation_failure_count": metrics.get("schema_validation_failure_count", 0),
        "grounding_failure_count": metrics.get("grounding_failure_count", 0),
        "quality_gate_failure_count": metrics.get("quality_gate_failure_count", 0),
        "invalid_evidence_id_count": metrics.get("invalid_evidence_id_count", 0),
        "invalid_evidence_ids": invalid_ids[:20],
        "action_repair_attempt_count": metrics.get("action_repair_attempt_count", 0),
        "action_repair_success_count": metrics.get("action_repair_success_count", 0),
        "invalid_action_type_count": metrics.get("invalid_action_type_count", 0),
        "invalid_action_types": invalid_action_types[:20],
        "repaired_action_type_count": metrics.get("repaired_action_type_count", 0),
        "repaired_action_text_count": metrics.get("repaired_action_text_count", 0),
        "removed_action_due_to_action_type_count": metrics.get("removed_action_due_to_action_type_count", 0),
        "action_retry_attempt_count": metrics.get("action_retry_attempt_count", 0),
        "action_retry_success_count": metrics.get("action_retry_success_count", 0),
        "empty_actions_after_repair_count": metrics.get("empty_actions_after_repair_count", 0),
        "human_review_postprocess_count": metrics.get("human_review_postprocess_count", 0),
        "action_type_rubric_pass_count": metrics.get("action_type_rubric_pass_count", 0),
        "action_repair_report": reports[0] if reports else None,
        "action_retry_report": next(
            (trace.get("action_retry_repair_report") for trace in traces if isinstance(trace.get("action_retry_repair_report"), dict)),
            None,
        ),
        "failure_reasons": metrics.get("failure_reasons", {}),
        "raw_response_debug_enabled": metrics.get("raw_response_debug_enabled", False),
    }


def build_insight_samples(
    *,
    scenario: dict[str, Any],
    provider: str,
    model: str | None,
    prompt_mode: str | None,
    insights: list[PublicAgencyInsight],
    service: ComplaintIntelligenceService,
    llm_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Local LLM 샘플 리뷰용으로 draft/repair/final을 PII-safe로 축약한다."""

    traces = [trace for trace in list(llm_metrics.get("candidate_traces") or []) if isinstance(trace, dict)]
    trace = traces[0] if traces else {}
    samples: list[dict[str, Any]] = []
    for insight in insights[:2]:
        pack = service.get_public_insight_evidence_pack(insight.insight_id)
        samples.append(
            {
                "scenario_id": scenario.get("scenario_id"),
                "scenario_label": scenario.get("label"),
                "provider": provider,
                "model": model,
                "prompt_mode": prompt_mode,
                "direct_llm_success": bool(trace.get("llm_success")),
                "fallback_used": bool(trace.get("fallback_used")),
                "fallback_reason": trace.get("llm_failure_reason") or trace.get("action_retry_failure_reason"),
                "llm_draft_summary": trace.get("llm_draft_summary") or {},
                "repair_diff": {
                    "invalid_evidence_ids": _masked_list(
                        list((trace.get("action_repair_report") or {}).get("invalid_evidence_ids") or [])
                    ),
                    "invalid_action_types": _masked_list(
                        list((trace.get("action_repair_report") or {}).get("invalid_action_types") or [])
                    ),
                    "removed_actions": int((trace.get("action_repair_report") or {}).get("removed_action_count") or 0),
                    "repaired_actions": int((trace.get("action_repair_report") or {}).get("repaired_action_count") or 0),
                    "repaired_action_types": int(
                        (trace.get("action_repair_report") or {}).get("repaired_action_type_count") or 0
                    ),
                    "repaired_action_texts": int(
                        (trace.get("action_repair_report") or {}).get("repaired_action_text_count") or 0
                    ),
                    "retry_used": bool(trace.get("action_retry_attempted")),
                    "retry_success": bool(trace.get("action_retry_success")),
                    "retry_failure_reason": trace.get("action_retry_failure_reason"),
                },
                "final_insight_summary": _final_insight_summary(insight, pack, trace),
                "evidence_preview": _evidence_preview(pack),
                "objective_review": _sample_objective_review(insight, trace),
            }
        )
    return samples


def _final_insight_summary(insight: PublicAgencyInsight, pack: Any | None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    allowed_types = allowed_action_types_for_pack(pack) if pack is not None else []
    repairs = list(((trace or {}).get("action_repair_report") or {}).get("action_type_repairs") or [])
    return {
        "insight_id": insight.insight_id,
        "type": str(insight.type),
        "priority": insight.priority,
        "confidence": insight.confidence,
        "grounding_score": insight.grounding_score,
        "avg_actionability_score": insight.metrics.get("avg_actionability_score", 0.0),
        "title": mask_pii(insight.title[:160]).text,
        "summary": mask_pii(insight.summary[:240]).text,
        "problem_diagnosis": mask_pii(insight.problem_diagnosis[:240]).text,
        "recommended_actions": [
            {
                "action": mask_pii(action.action[:180]).text,
                "original_action_type": _original_action_type_for(action, repairs),
                "final_action_type": str(action.action_type),
                "action_type_repaired": _original_action_type_for(action, repairs) != str(action.action_type),
                "allowed_action_types": allowed_types,
                "actionability_score": score_actionability(action).score,
                "supporting_evidence_ids": _masked_list(action.supporting_evidence_ids),
            }
            for action in insight.recommended_actions[:3]
        ],
        "evidence_ids": sorted(insight_evidence_ids(insight))[:10],
    }


def _original_action_type_for(action: Any, repairs: list[Any]) -> str:
    final_type = str(getattr(action, "action_type", ""))
    for repair in repairs:
        if isinstance(repair, dict) and str(repair.get("to")) == final_type:
            return str(repair.get("from") or final_type)
    return final_type


def _evidence_preview(pack: Any | None) -> list[dict[str, Any]]:
    if pack is None:
        return []
    previews: list[dict[str, Any]] = []
    for item in list(pack.representative_complaints or [])[:5]:
        previews.append(
            {
                "evidence_id": mask_pii(str(item.get("complaint_id") or "")).text,
                "masked_text": mask_pii(str(item.get("masked_text") or "")[:120]).text,
            }
        )
    return previews


def _sample_objective_review(insight: PublicAgencyInsight, trace: dict[str, Any]) -> dict[str, Any]:
    fallback_used = bool(trace.get("fallback_used"))
    return {
        "strengths": [
            "최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.",
            "추천 조치가 evidence id와 연결되어 추적 가능합니다.",
        ],
        "weaknesses": (
            ["fallback template 기반 결과이므로 Local LLM draft 품질 판단에는 제한이 있습니다."]
            if fallback_used
            else ["자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다."]
        ),
        "actionability_judgment": "recommended_actions가 있고 action_type/evidence id를 포함합니다.",
        "grounding_judgment": "근거 ID는 EvidencePack valid_evidence_ids 기준으로 검증되었습니다.",
        "public_official_readiness": "데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.",
    }


def _masked_list(values: list[str]) -> list[str]:
    return [mask_pii(str(value)).text for value in values[:20]]


def summarize_alerts(alerts: list[IssueAlert]) -> list[dict[str, Any]]:
    return [
        {
            "id": alert.id,
            "severity": alert.severity,
            "topic": alert.topic,
            "region": alert.region,
            "recent_count": alert.recent_count,
            "surge_ratio": alert.surge_ratio,
            "confidence": alert.confidence,
        }
        for alert in alerts
    ]


def summarize_insights(insights: list[PublicAgencyInsight]) -> list[dict[str, Any]]:
    return [
        {
            "insight_id": insight.insight_id,
            "type": str(insight.type),
            "priority": insight.priority,
            "topic": insight.topic,
            "affected_count": insight.affected_count,
            "confidence": insight.confidence,
            "grounding_score": insight.grounding_score,
            "requires_human_review": insight.requires_human_review,
            "action_types": sorted({str(action.action_type) for action in insight.recommended_actions}),
            "aspects": [aspect.aspect for aspect in insight.extracted_aspects],
        }
        for insight in insights
    ]


def write_default_scenarios(path: Path) -> None:
    """기본 평가 scenario 파일을 생성한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, build_default_scenarios())


def build_default_scenarios() -> dict[str, Any]:
    """기존 demo seed와 보강 scenario를 합쳐 최소 10개 평가 세트를 만든다."""

    demo_scenarios = load_demo_scenarios()
    synthetic_scenarios = build_synthetic_scenarios(DEFAULT_AS_OF)
    return {
        "mode": "replay",
        "source_name": "complaint_intelligence_evaluation",
        "as_of": DEFAULT_AS_OF.isoformat(),
        "description": "IssueAlert와 PublicAgencyInsight 품질을 객관 평가하기 위한 replay scenario 세트",
        "provenance_note": "앞 5개 scenario는 demo seed의 실제 데이터 기반 replay를 재사용하고, 나머지는 부족한 평가 상황을 synthetic으로 보강했습니다.",
        "scenarios": demo_scenarios + synthetic_scenarios,
    }


def load_demo_scenarios() -> list[dict[str, Any]]:
    if not DEFAULT_DEMO_SEED.exists():
        return build_demo_fallback_scenarios(DEFAULT_AS_OF)
    payload = json.loads(DEFAULT_DEMO_SEED.read_text(encoding="utf-8"))
    expectations = {
        "sinkhole_hotspot": {
            "expected_issue_topics": ["도로 침하", "싱크홀"],
            "required_aspects": ["현장 안전", "시설 파손"],
            "required_action_types": ["FIELD_INSPECTION"],
            "requires_human_review": True,
        },
        "illegal_parking_enforcement": {
            "expected_issue_topics": ["주정차", "불법주차"],
            "required_aspects": ["단속 공백"],
            "required_action_types": ["ENFORCEMENT"],
            "requires_human_review": False,
        },
        "bulky_waste_guidance": {
            "expected_issue_topics": ["대형폐기물", "배출"],
            "required_aspects": ["안내 부족", "신청 절차"],
            "required_action_types": ["PUBLIC_GUIDANCE"],
            "requires_human_review": False,
        },
        "welfare_support_process": {
            "expected_issue_topics": ["복지", "지원"],
            "required_aspects": ["신청 절차", "지원 기준"],
            "required_action_types": ["POLICY_REVIEW", "PUBLIC_GUIDANCE"],
            "requires_human_review": True,
        },
        "odor_night_hotspot": {
            "expected_issue_topics": ["악취", "냄새"],
            "required_aspects": ["생활환경 불편"],
            "required_action_types": ["PROCESS_IMPROVEMENT"],
            "requires_human_review": False,
        },
    }
    scenarios = []
    for scenario in payload.get("scenarios", []):
        scenario_id = str(scenario.get("id") or scenario.get("scenario_id"))
        if scenario_id not in expectations:
            continue
        expected = expectations[scenario_id]
        events = list(scenario.get("events") or [])
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "label": scenario.get("label"),
                "scenario_type": "positive_alert",
                "expected_alert": True,
                "expected_insight_types": scenario.get("expected_insight_types") or [],
                "min_event_count": 5,
                "source_policy": scenario.get("source_policy", "real_text_replayed_time"),
                "real_event_count": len(events),
                "synthetic_event_count": 0,
                "source_ids": _source_ids(events),
                "events": events,
                **expected,
            }
        )
    return scenarios


def build_synthetic_scenarios(as_of: datetime) -> list[dict[str, Any]]:
    """실제 데이터가 부족한 평가 축을 synthetic으로 보강한다."""

    return [
        scenario(
            "public_bike_app_ux",
            "공공자전거/앱 예약·대여 UX 불편",
            "positive_alert",
            True,
            ["공공자전거", "예약"],
            ["SERVICE_DESIGN_IMPROVEMENT", "ACCESSIBILITY_OR_USABILITY_ISSUE"],
            ["접근성/사용성", "신청 절차"],
            ["SERVICE_DESIGN"],
            False,
            [
                "공공자전거 앱 예약 절차가 불편하고 대여 단계가 너무 복잡합니다.",
                "대여 신청 중 결제 오류가 반복되어 자전거를 빌리지 못했습니다.",
                "앱 로그인 후 예약 기준을 이해하기 어려워 현장에서 계속 문의합니다.",
                "공공자전거 대여 화면 안내가 부족해서 결제와 예약을 다시 해야 합니다.",
                "예약 취소와 재대여 절차가 복잡해 이용이 중단됩니다.",
            ],
            as_of,
            "성동구",
            "교통서비스과",
            "서비스 개선",
            request="앱 예약·대여 절차 단순화와 오류 단계 확인을 요청합니다.",
            result="앱 오류와 복잡한 단계 때문에 대여 실패와 현장 문의가 반복됩니다.",
            context="최근 3시간 동안 같은 대여소 주변에서 앱 이용 불편이 반복되었습니다.",
        ),
        scenario(
            "department_delay_backlog",
            "부서 처리 지연/미처리 누적",
            "positive_operational",
            True,
            ["처리 지연", "미처리"],
            ["PROCESS_DELAY_RISK", "DEPARTMENT_WORKLOAD_BOTTLENECK"],
            ["처리 지연", "소통 부족"],
            ["PROCESS_IMPROVEMENT"],
            False,
            [
                "도로 보수 요청이 접수된 지 오래됐는데 처리되지 않았습니다.",
                "같은 부서 담당 민원이 계속 pending 상태로 남아 있습니다.",
                "처리 기간 안내 없이 미처리 상태가 길어져 불편합니다.",
                "보수 요청 답변이 없어 진행 상황을 확인하고 싶습니다.",
                "담당 부서에서 아직 조치 일정을 알려주지 않았습니다.",
            ],
            as_of,
            "중구",
            "도로관리과",
            "업무 병목",
            request="처리 지연 원인 점검과 진행 상태 안내를 요청합니다.",
            result="미처리 누적과 답변 지연으로 시민이 처리 상태를 알기 어렵습니다.",
            context="동일 부서의 open/pending 민원이 최근 관측 기준으로 누적되어 있습니다.",
            status="pending",
            handling_time_minutes=2400,
        ),
        scenario(
            "repeat_reopen_growth",
            "재민원/반복 민원 증가",
            "positive_operational",
            True,
            ["재민원", "반복"],
            ["REOPEN_OR_REPEAT_RISK"],
            ["재민원/반복 민원", "처리 결과 불만", "소통 부족"],
            ["PROCESS_IMPROVEMENT", "CITIZEN_COMMUNICATION"],
            False,
            [
                "악취 민원을 처리했다고 했지만 같은 냄새가 다시 납니다.",
                "하수 냄새 신고를 여러 번 했는데 재발해서 다시 접수합니다.",
                "반복 민원인데 완료 안내 후에도 현장 상태가 바뀌지 않았습니다.",
                "같은 위치 악취가 계속 반복되어 재점검이 필요합니다.",
                "처리 완료라고 안내받았지만 냄새 문제가 다시 발생했습니다.",
            ],
            as_of,
            "관악구",
            "환경관리과",
            "재민원",
            request="재발 원인 점검과 처리 완료 후 현장 확인을 요청합니다.",
            result="완료 안내 이후에도 같은 불편이 반복되어 시민 불만이 커지고 있습니다.",
            context="동일 위치와 동일 주제 민원이 반복 접수되고 재민원으로 표시되었습니다.",
            status="reopened",
            reopened=True,
            user_feedback_score=1.0,
        ),
        scenario(
            "construction_noise_time_pattern",
            "소음/공사 민원 특정 시간대 집중",
            "positive_alert",
            True,
            ["소음", "공사"],
            ["SEASONAL_OR_TIME_PATTERN", "ENFORCEMENT_PRIORITY", "RECURRING_COMPLAINT_PATTERN"],
            ["소음/진동", "시간대 집중", "단속 공백"],
            ["ENFORCEMENT", "FIELD_INSPECTION"],
            False,
            [
                "새벽 공사 소음과 진동 때문에 잠을 잘 수 없습니다.",
                "밤마다 공사장 소음이 반복되어 단속이 필요합니다.",
                "야간 작업 소음 기준 안내와 현장 점검을 요청합니다.",
                "같은 시간대 공사 차량 소음이 계속 발생합니다.",
                "퇴근 이후 공사 소음이 집중되어 생활 불편이 큽니다.",
            ],
            as_of,
            "마포구",
            "환경관리과",
            "소음 단속",
            request="야간 소음 현장 점검과 기준 안내, 단속 강화를 요청합니다.",
            result="특정 시간대 소음과 진동으로 생활 불편이 반복됩니다.",
            context="야간과 퇴근 이후 시간대에 공사 소음 민원이 집중됩니다.",
            received_offsets=[150, 145, 140, 135, 130],
        ),
        scenario(
            "accessibility_usage_barrier",
            "접근성/고령자·장애인 이용 어려움",
            "positive_alert",
            True,
            ["접근성", "사용성"],
            ["ACCESSIBILITY_OR_USABILITY_ISSUE", "SERVICE_DESIGN_IMPROVEMENT"],
            ["접근성/사용성", "안내 부족"],
            ["PROCESS_IMPROVEMENT", "SERVICE_DESIGN"],
            False,
            [
                "고령자가 복지 신청 앱을 쓰기 어렵고 글씨와 단계 안내가 부족합니다.",
                "장애인 이용자가 예약 화면에서 필요한 버튼을 찾기 어렵습니다.",
                "외국인 안내 문구가 부족해 신청 절차를 이해하기 어렵습니다.",
                "디지털 취약계층이 로그인과 본인 확인 단계에서 계속 막힙니다.",
                "앱 화면 접근성이 낮아 상담창구 문의가 반복됩니다.",
            ],
            as_of,
            "중구",
            "디지털민원지원팀",
            "접근성 개선",
            request="고령자와 장애인을 위한 쉬운 안내와 대체 신청 경로를 요청합니다.",
            result="접근성 부족으로 신청 중단과 반복 문의가 발생합니다.",
            context="디지털 취약계층 관련 이용 어려움이 같은 기간 반복되었습니다.",
        ),
        scenario(
            "streetlight_failure_recurring",
            "가로등/보안등 고장 반복",
            "positive_alert",
            True,
            ["가로등", "보안등"],
            ["FACILITY_MAINTENANCE_PRIORITY", "RECURRING_COMPLAINT_PATTERN"],
            ["시설 파손", "현장 안전"],
            ["FIELD_INSPECTION", "MAINTENANCE"],
            False,
            [
                "공원 입구 가로등이 며칠째 꺼져 있어 밤길이 위험합니다.",
                "보안등 고장으로 골목이 어둡고 안전이 걱정됩니다.",
                "같은 위치 가로등이 반복적으로 고장 납니다.",
                "가로등 수리를 요청했지만 다시 꺼졌습니다.",
                "야간 보행 안전을 위해 조명 점검이 필요합니다.",
            ],
            as_of,
            "중구",
            "시설관리과",
            "시설 보수",
            request="가로등 현장 점검과 반복 고장 원인 확인을 요청합니다.",
            result="조명 고장으로 야간 보행 안전 우려가 반복됩니다.",
            context="같은 골목과 공원 입구 주변에서 조명 고장 신고가 집중되었습니다.",
        ),
        scenario(
            "flood_drainage_risk",
            "침수/배수 불량 위험",
            "positive_alert",
            True,
            ["침수", "배수"],
            ["SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED", "FACILITY_MAINTENANCE_PRIORITY"],
            ["침수 위험", "배수 불량", "현장 안전"],
            ["FIELD_INSPECTION", "MAINTENANCE", "SAFETY_NOTICE"],
            True,
            [
                "비가 오면 맨홀 주변 물이 역류해 보도 침수 위험이 큽니다.",
                "우수관 배수 불량으로 빗물받이가 막혀 도로에 물이 고입니다.",
                "하수도 역류 냄새와 침수 우려가 반복되어 사전 점검이 필요합니다.",
                "집중호우 전에 배수로와 맨홀을 정비해 주세요.",
                "저지대 골목 배수가 안 돼 차량과 보행자 안전이 걱정됩니다.",
            ],
            as_of,
            "영등포구",
            "치수과",
            "침수/배수",
            request="배수로 점검, 맨홀/하수도 정비, 우천 전 사전 조치를 요청합니다.",
            result="배수 불량과 역류로 침수 위험과 현장 안전 우려가 반복됩니다.",
            context="최근 관측 기준 같은 저지대 구간에서 우천 전 배수 민원이 집중되었습니다.",
        ),
        scenario(
            "illegal_dumping_recurring",
            "무단투기/쓰레기 적치 반복",
            "positive_alert",
            True,
            ["무단투기", "쓰레기"],
            ["ENFORCEMENT_PRIORITY", "FACILITY_MAINTENANCE_PRIORITY", "PUBLIC_GUIDANCE_NEEDED"],
            ["무단투기", "쓰레기 적치", "안내 부족"],
            ["ENFORCEMENT", "MAINTENANCE", "PUBLIC_GUIDANCE"],
            True,
            [
                "골목 입구에 쓰레기 무단투기가 반복되어 악취가 납니다.",
                "생활폐기물이 계속 적치되어 정기 청소와 단속이 필요합니다.",
                "무단투기 금지 안내문이 부족하고 같은 위치에 쓰레기가 쌓입니다.",
                "밤마다 폐기물을 몰래 버려 주변이 지저분합니다.",
                "쓰레기 방치로 보행이 불편하니 청소와 단속을 강화해 주세요.",
            ],
            as_of,
            "동작구",
            "청소행정과",
            "무단투기",
            request="무단투기 단속 강화, 정기 청소 확대, 금지 안내 보강을 요청합니다.",
            result="쓰레기 적치와 악취로 생활환경 불편이 반복됩니다.",
            context="같은 골목 입구에서 야간 무단투기 민원이 최근 집중되었습니다.",
        ),
        scenario(
            "park_playground_facility_safety",
            "공원/놀이터 시설 파손 및 이용 안전",
            "positive_alert",
            True,
            ["공원", "놀이터"],
            ["FACILITY_MAINTENANCE_PRIORITY", "SAFETY_RISK_SIGNAL"],
            ["시설 파손", "이용 안전", "유지보수 지연"],
            ["FIELD_INSPECTION", "MAINTENANCE", "CITIZEN_COMMUNICATION"],
            True,
            [
                "놀이터 미끄럼틀이 파손되어 아이들이 다칠 위험이 있습니다.",
                "공원 벤치가 깨져 있고 보수 일정 안내가 없습니다.",
                "산책로 바닥이 들떠 야간 이용 시 넘어질까 불안합니다.",
                "공원 시설 고장이 반복되는데 임시 안전 조치가 필요합니다.",
                "놀이터 시설 점검과 보수 일정을 알려 주세요.",
            ],
            as_of,
            "서초구",
            "공원녹지과",
            "공원 시설",
            request="시설 점검, 보수 일정 안내, 임시 안전 조치를 요청합니다.",
            result="시설 파손과 유지보수 지연으로 이용 안전 우려가 반복됩니다.",
            context="같은 공원과 놀이터 주변 시설 파손 신고가 최근 집중되었습니다.",
        ),
        scenario(
            "security_light_dark_walkway",
            "가로등/보안등 고장 반복 확장",
            "positive_alert",
            True,
            ["가로등", "보안등"],
            ["FACILITY_MAINTENANCE_PRIORITY", "SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"],
            ["조명 고장", "야간 보행 불안", "안전 위험"],
            ["FIELD_INSPECTION", "MAINTENANCE", "SAFETY_NOTICE"],
            True,
            [
                "골목 보안등이 계속 꺼져 밤길 보행이 불안합니다.",
                "가로등 고장이 반복되어 야간에 시야 확보가 어렵습니다.",
                "어두운 보행 구간에 임시 조명이나 안전 안내가 필요합니다.",
                "같은 위치 조명 고장 신고를 여러 번 했습니다.",
                "야간 보행 안전을 위해 보안등 교체와 현장 점검을 요청합니다.",
            ],
            as_of,
            "도봉구",
            "도로조명과",
            "조명 안전",
            request="조명 교체, 현장 점검, 임시 조명 또는 안전 안내를 요청합니다.",
            result="조명 고장으로 야간 보행 불안과 안전 위험이 반복됩니다.",
            context="같은 골목 보행 구간에서 가로등/보안등 고장 신고가 집중되었습니다.",
        ),
        scenario(
            "bus_route_headway_discomfort",
            "버스 정류장/노선·배차 불편",
            "positive_alert",
            True,
            ["버스", "배차"],
            ["REGIONAL_SERVICE_GAP", "SERVICE_DESIGN_IMPROVEMENT", "CITIZEN_COMMUNICATION_GAP"],
            ["배차 간격", "정류장 접근성", "노선 안내 부족"],
            ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"],
            True,
            [
                "버스 배차 간격이 길어 출근 시간마다 정류장에서 오래 기다립니다.",
                "정류장 위치가 멀고 노선 안내가 부족해 환승이 어렵습니다.",
                "버스 도착 안내가 맞지 않아 이용 불편이 반복됩니다.",
                "이 지역 노선 조정 검토와 배차 안내 개선이 필요합니다.",
                "정류장 접근성이 낮아 대중교통 이용이 어렵습니다.",
            ],
            as_of,
            "강서구",
            "교통행정과",
            "대중교통",
            request="노선 조정 검토, 배차 안내 개선, 정류장 시설 개선을 요청합니다.",
            result="배차 간격과 노선 안내 부족으로 지역 서비스 격차가 의심됩니다.",
            context="같은 생활권 정류장 주변에서 버스 이용 불편 민원이 반복되었습니다.",
        ),
        scenario(
            "cctv_security_request",
            "CCTV/방범 안전 설치 요청",
            "positive_alert",
            True,
            ["CCTV", "방범"],
            ["SAFETY_RISK_SIGNAL", "REGIONAL_SERVICE_GAP", "POLICY_IMPROVEMENT_OPPORTUNITY"],
            ["방범 취약", "야간 안전 불안", "사각지대"],
            ["FIELD_INSPECTION", "SAFETY_NOTICE", "POLICY_REVIEW"],
            True,
            [
                "골목이 밤에 너무 어두워 CCTV 설치와 방범 순찰이 필요합니다.",
                "사각지대가 있어 야간 안전이 불안하니 현장 확인 바랍니다.",
                "방범 취약 구간인데 안내와 순찰이 부족합니다.",
                "CCTV 설치 검토와 조명 보강을 요청합니다.",
                "늦은 시간 보행자가 불안해하는 구간을 점검해 주세요.",
            ],
            as_of,
            "구로구",
            "안전관리과",
            "방범 안전",
            request="CCTV 설치 검토, 방범 순찰 강화, 조명/안내 개선을 요청합니다.",
            result="야간 안전 불안과 방범 사각지대 우려가 반복됩니다.",
            context="같은 골목과 사각지대 주변에서 방범 안전 민원이 집중되었습니다.",
        ),
        scenario(
            "smoking_enforcement_recurring",
            "흡연/금연구역 단속 반복",
            "positive_alert",
            True,
            ["흡연", "금연구역"],
            ["ENFORCEMENT_PRIORITY", "PUBLIC_GUIDANCE_NEEDED", "CITIZEN_COMMUNICATION_GAP"],
            ["흡연 반복", "단속 공백", "안내 부족"],
            ["ENFORCEMENT", "PUBLIC_GUIDANCE", "MAINTENANCE"],
            True,
            [
                "금연구역에서 흡연이 반복되어 간접흡연 피해가 큽니다.",
                "담배꽁초가 계속 쌓여 청소와 단속이 필요합니다.",
                "금연 안내 표지가 부족해 같은 장소에서 흡연이 계속됩니다.",
                "점심시간마다 흡연 단속을 강화해 주세요.",
                "간접흡연 민원이 반복되니 안내문과 현장 점검이 필요합니다.",
            ],
            as_of,
            "종로구",
            "보건위생과",
            "금연 단속",
            request="금연구역 단속, 안내문/표지 보강, 담배꽁초 청소를 요청합니다.",
            result="흡연 반복과 단속 공백 인식으로 생활환경 불편이 반복됩니다.",
            context="같은 상가 앞 금연구역에서 점심·퇴근 시간대 민원이 집중되었습니다.",
        ),
        scenario(
            "illegal_banner_cleanup",
            "불법 광고물/현수막 정비",
            "positive_alert",
            True,
            ["현수막", "광고물"],
            ["ENFORCEMENT_PRIORITY", "FACILITY_MAINTENANCE_PRIORITY", "REGIONAL_SERVICE_GAP"],
            ["불법 광고물", "보행/시야 방해", "반복 위치"],
            ["ENFORCEMENT", "FIELD_INSPECTION", "MAINTENANCE"],
            True,
            [
                "불법 현수막이 횡단보도 시야를 가려 보행이 위험합니다.",
                "같은 사거리 광고물이 반복 설치되어 도시 미관을 해칩니다.",
                "보행로에 불법 광고물이 많아 현장 정비가 필요합니다.",
                "현수막 단속과 반복 위치 관리를 요청합니다.",
                "도로 시야를 방해하는 광고물을 정비해 주세요.",
            ],
            as_of,
            "송파구",
            "도시경관과",
            "불법 광고물",
            request="현장 정비, 단속 강화, 반복 위치 관리를 요청합니다.",
            result="불법 광고물과 현수막이 보행/시야 방해와 도시 미관 저해를 일으킵니다.",
            context="같은 사거리와 보행로 주변에서 불법 광고물 신고가 집중되었습니다.",
        ),
        scenario(
            "pet_waste_leash_complaints",
            "반려동물 배설물/목줄/유기동물 민원",
            "positive_alert",
            True,
            ["반려동물", "배설물"],
            ["ENFORCEMENT_PRIORITY", "PUBLIC_GUIDANCE_NEEDED", "REGIONAL_SERVICE_GAP"],
            ["반려동물 관리", "배설물 방치", "목줄 미착용"],
            ["ENFORCEMENT", "PUBLIC_GUIDANCE", "FIELD_INSPECTION"],
            True,
            [
                "공원 산책로에 반려동물 배설물이 방치되어 위생이 걱정됩니다.",
                "목줄 미착용 개 때문에 아이들이 무서워합니다.",
                "반려동물 배설물 안내문과 단속이 부족합니다.",
                "같은 시간대 목줄 없이 산책하는 사례가 반복됩니다.",
                "유기동물 신고와 현장 순찰을 요청합니다.",
            ],
            as_of,
            "노원구",
            "동물보호과",
            "반려동물 관리",
            request="단속, 안내문 보강, 현장 순찰을 요청합니다.",
            result="반려동물 관리 미흡으로 생활 안전과 위생 불편이 반복됩니다.",
            context="같은 공원 산책로 주변에서 배설물과 목줄 민원이 집중되었습니다.",
        ),
        scenario(
            "licensing_docs_guidance_confusion",
            "인허가/자격·서류 기준 안내 혼선",
            "positive_alert",
            True,
            ["인허가", "서류"],
            ["PUBLIC_GUIDANCE_NEEDED", "CITIZEN_COMMUNICATION_GAP", "POLICY_IMPROVEMENT_OPPORTUNITY"],
            ["기준 이해 어려움", "신청 절차", "제출 서류"],
            ["PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "PROCESS_IMPROVEMENT"],
            True,
            [
                "인허가 신청 기준과 제출 서류가 헷갈려 상담이 필요합니다.",
                "자격 요건 안내가 어려워 어느 부서에 문의해야 할지 모르겠습니다.",
                "면허 기준과 필요서류 체크리스트를 제공해 주세요.",
                "담당 부서 안내가 부족해 신청 절차를 반복해서 문의합니다.",
                "인허가 기준 설명이 서로 달라 시민이 혼란스럽습니다.",
            ],
            as_of,
            "중랑구",
            "민원여권과",
            "인허가 안내",
            request="기준 안내 보강, 체크리스트 제공, 담당 부서 상담 경로 안내를 요청합니다.",
            result="기준과 제출 서류 안내 혼선으로 반복 문의가 발생합니다.",
            context="최근 관측 기준 인허가·자격·서류 관련 문의가 같은 창구에 집중되었습니다.",
        ),
        scenario(
            "accessibility_vulnerable_groups",
            "장애인·고령자·외국인 접근성/이용 어려움",
            "positive_alert",
            True,
            ["접근성", "고령자"],
            ["ACCESSIBILITY_OR_USABILITY_ISSUE", "SERVICE_DESIGN_IMPROVEMENT", "PUBLIC_GUIDANCE_NEEDED"],
            ["접근성/사용성", "취약계층 이용 불편", "안내 부족"],
            ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"],
            True,
            [
                "고령자가 온라인 신청 절차를 이해하기 어려워 도움을 요청합니다.",
                "장애인 이용자가 예약 화면에서 접근성 버튼을 찾기 어렵습니다.",
                "외국어 안내가 부족해 외국인이 신청 방법을 이해하지 못합니다.",
                "휠체어 이용자가 현장 안내 동선을 알기 어렵습니다.",
                "취약계층을 위한 쉬운 안내와 대체 신청 경로가 필요합니다.",
            ],
            as_of,
            "은평구",
            "디지털민원지원팀",
            "접근성",
            request="쉬운 안내, 외국어/고령자 친화 안내, 신청 절차 단순화를 요청합니다.",
            result="취약계층 이용 불편과 신청 중단 가능성이 반복됩니다.",
            context="고령자·장애인·외국인 이용 어려움이 같은 기간 반복되었습니다.",
        ),
        scenario(
            "school_zone_commute_safety",
            "어린이보호구역/통학 안전",
            "positive_alert",
            True,
            ["어린이보호구역", "통학"],
            ["SAFETY_RISK_SIGNAL", "ENFORCEMENT_PRIORITY", "HOTSPOT_RESPONSE_REQUIRED"],
            ["통학 안전", "등하교 시간 집중", "교통 위험"],
            ["ENFORCEMENT", "FIELD_INSPECTION", "SAFETY_NOTICE"],
            True,
            [
                "어린이보호구역에 등교 시간 불법주정차가 많아 통학 안전이 걱정됩니다.",
                "학교 앞 차량 속도가 빠르고 교통 위험이 반복됩니다.",
                "하교 시간대 단속과 안전 안내 표지를 보강해 주세요.",
                "통학로 주변 현장 점검과 교통지도 요청합니다.",
                "등하교 시간마다 차량 혼잡으로 아이들이 위험합니다.",
            ],
            as_of,
            "양천구",
            "교통지도과",
            "통학 안전",
            request="등하교 시간 단속, 안내 표지 보강, 현장 점검을 요청합니다.",
            result="어린이보호구역 통학 안전과 교통 위험 우려가 반복됩니다.",
            context="학교 앞 같은 구간에서 등하교 시간대 민원이 집중되었습니다.",
        ),
        scenario(
            "low_count_negative",
            "낮은 건수라 alert가 뜨면 안 되는 상황",
            "negative_low_count",
            False,
            [],
            [],
            [],
            [],
            False,
            [
                "대형폐기물 배출 스티커 문의가 있습니다.",
                "공원 벤치 위치를 알고 싶습니다.",
            ],
            as_of,
            "중구",
            "민원상담과",
            "negative",
            source_policy="synthetic_negative_control",
        ),
        scenario(
            "dispersed_keyword_negative",
            "같은 키워드지만 지역·시간이 분산된 non-hotspot",
            "negative_dispersed",
            False,
            [],
            [],
            [],
            [],
            False,
            [
                "도로에 작은 구멍이 있어 보수 문의합니다.",
                "도로 포장 상태가 좋지 않아 점검이 필요합니다.",
                "아스팔트 균열이 보여 확인 요청합니다.",
                "도로 보수 일정이 궁금합니다.",
                "길 가장자리 구멍을 메워 주세요.",
            ],
            as_of,
            "분산",
            "도로관리과",
            "negative",
            source_policy="synthetic_negative_control",
            regions=["중구", "강남구", "마포구", "성동구", "관악구"],
            received_offsets=[9000, 7200, 5400, 3600, 120],
        ),
    ]


def build_demo_fallback_scenarios(as_of: datetime) -> list[dict[str, Any]]:
    return [
        scenario(
            "sinkhole_hotspot",
            "도로 침하/싱크홀 급증",
            "positive_alert",
            True,
            ["도로 침하", "싱크홀"],
            ["SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED"],
            ["현장 안전", "시설 파손"],
            ["FIELD_INSPECTION"],
            True,
            [
                "OO동 도로에 구멍이 생겼습니다.",
                "아스팔트가 내려앉았습니다.",
                "차도 중간이 움푹 파였습니다.",
                "싱크홀 같은 게 생겼습니다.",
                "도로 바닥이 꺼져 위험합니다.",
            ],
            as_of,
            "중구",
            "도로관리과",
            "도로 침하",
            request="긴급 현장 점검과 안전 안내를 요청합니다.",
            result="도로 침하로 차량과 보행자 안전 위험이 있습니다.",
            context="같은 지역에서 최근 3시간 안에 신고가 집중되었습니다.",
        )
    ]


def scenario(
    scenario_id: str,
    label: str,
    scenario_type: str,
    expected_alert: bool,
    expected_issue_topics: list[str],
    expected_insight_types: list[str],
    required_aspects: list[str],
    required_action_types: list[str],
    requires_human_review: bool,
    texts: list[str],
    as_of: datetime,
    region: str,
    department: str,
    category: str,
    *,
    request: str = "관련 조치와 안내 개선을 요청합니다.",
    result: str = "반복 불편으로 시민 문의와 불만이 발생합니다.",
    context: str = "최근 관측 기준으로 같은 주제 민원이 반복되었습니다.",
    status: str = "open",
    handling_time_minutes: float | None = None,
    reopened: bool = False,
    user_feedback_score: float | None = None,
    source_policy: str = "synthetic_evaluation_control",
    regions: list[str] | None = None,
    received_offsets: list[int] | None = None,
) -> dict[str, Any]:
    events = []
    offsets = received_offsets or [10 + index * 9 for index in range(len(texts))]
    for index, text in enumerate(texts):
        event_region = (regions[index] if regions and index < len(regions) else region)
        received_at = as_of - timedelta(minutes=offsets[index])
        events.append(
            {
                "id": f"eval-{scenario_id}-{index + 1:03d}",
                "received_at": received_at.isoformat(),
                "title": text,
                "body": text,
                "region": event_region,
                "final_department": department,
                "status": status,
                "handling_time_minutes": handling_time_minutes,
                "reopened": reopened,
                "user_feedback_score": user_feedback_score,
                "civil_category": category,
                "structured_elements": {
                    "observation": {"text": text, "confidence": 0.82},
                    "result": {"text": result, "confidence": 0.78},
                    "request": {"text": request, "confidence": 0.8},
                    "context": {"text": context, "confidence": 0.76},
                },
            }
        )
    return {
        "scenario_id": scenario_id,
        "label": label,
        "scenario_type": scenario_type,
        "expected_alert": expected_alert,
        "expected_issue_topics": expected_issue_topics,
        "expected_insight_types": expected_insight_types,
        "required_aspects": required_aspects,
        "required_action_types": required_action_types,
        "requires_human_review": requires_human_review,
        "min_event_count": min(5, len(texts)),
        "source_policy": source_policy,
        "real_event_count": 0,
        "synthetic_event_count": len(events),
        "source_ids": [],
        "events": events,
    }


def load_scenarios(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    issue = summary["issue_detection"]
    insight = summary["public_agency_insight"]
    llm_eval = report.get("llm_evaluation") or {}
    lines = [
        "# Complaint Intelligence 평가 보고서",
        "",
        f"- Provider: `{report['provider']}`",
        f"- Scenario count: `{report['scenario_count']}`",
        f"- Overall pass rate: `{summary['overall_pass_rate']:.3f}`",
        "",
        "## 전체 지표",
        "",
        "| 축 | 지표 | 값 |",
        "| --- | --- | ---: |",
        f"| IssueAlert | alert_recall | {issue['alert_recall']:.3f} |",
        f"| IssueAlert | alert_precision_on_negative | {issue['alert_precision_on_negative']:.3f} |",
        f"| IssueAlert | false_positive_count | {issue['false_positive_count']} |",
        f"| IssueAlert | false_negative_count | {issue['false_negative_count']} |",
        f"| PublicAgencyInsight | expected_type_hit_rate | {insight['expected_type_hit_rate']:.3f} |",
        f"| PublicAgencyInsight | required_aspect_hit_rate | {insight['required_aspect_hit_rate']:.3f} |",
        f"| PublicAgencyInsight | required_action_type_hit_rate | {insight['required_action_type_hit_rate']:.3f} |",
        f"| PublicAgencyInsight | allowed_action_type_hit_rate | {insight.get('allowed_action_type_hit_rate', 0.0):.3f} |",
        f"| PublicAgencyInsight | action_type_rubric_pass_rate | {insight.get('action_type_rubric_pass_rate', 0.0):.3f} |",
        f"| PublicAgencyInsight | action_evidence_coverage_rate | {insight['action_evidence_coverage_rate']:.3f} |",
        f"| PublicAgencyInsight | avg_grounding_score | {insight['avg_grounding_score']:.3f} |",
        f"| PublicAgencyInsight | avg_confidence | {insight['avg_confidence']:.3f} |",
        f"| PublicAgencyInsight | avg_actionability_score | {insight['avg_actionability_score']:.3f} |",
        f"| PublicAgencyInsight | pii_leak_rate | {insight['pii_leak_rate']:.3f} |",
        f"| PublicAgencyInsight | forbidden_ai_ops_term_rate | {insight['forbidden_ai_ops_term_rate']:.3f} |",
        f"| PublicAgencyInsight | human_review_requirement_pass_rate | {insight['human_review_requirement_pass_rate']:.3f} |",
        f"| LLM | direct_llm_success_count | {llm_eval.get('direct_llm_success_count', 0)} |",
        f"| LLM | fallback_count | {llm_eval.get('fallback_count', 0)} |",
        f"| LLM | fallback_rate | {float(llm_eval.get('fallback_rate', 0.0)):.3f} |",
        f"| LLM | direct_llm_success_rate | {float(llm_eval.get('direct_llm_success_rate', 0.0)):.3f} |",
        f"| LLM | fallback_due_to_empty_actions_count | {llm_eval.get('fallback_due_to_empty_actions_count', 0)} |",
        f"| LLM | invalid_evidence_id_count | {llm_eval.get('invalid_evidence_id_count', 0)} |",
        f"| LLM | invalid_action_type_count | {llm_eval.get('invalid_action_type_count', 0)} |",
        f"| LLM | repaired_action_type_count | {llm_eval.get('repaired_action_type_count', 0)} |",
        f"| LLM | repaired_action_text_count | {llm_eval.get('repaired_action_text_count', 0)} |",
        f"| LLM | removed_action_due_to_action_type_count | {llm_eval.get('removed_action_due_to_action_type_count', 0)} |",
        f"| LLM | action_repair_success_count | {llm_eval.get('action_repair_success_count', 0)} |",
        f"| LLM | human_review_postprocess_count | {llm_eval.get('human_review_postprocess_count', 0)} |",
        f"| LLM | action_retry_attempt_count | {llm_eval.get('action_retry_attempt_count', 0)} |",
        f"| LLM | action_retry_success_count | {llm_eval.get('action_retry_success_count', 0)} |",
        f"| LLM | json_parse_failure_count | {llm_eval.get('json_parse_failure_count', 0)} |",
        f"| LLM | schema_validation_failure_count | {llm_eval.get('schema_validation_failure_count', 0)} |",
        f"| LLM | avg_llm_duration_ms | {float(llm_eval.get('avg_llm_duration_ms', 0.0)):.1f} |",
        f"| LLM | avg_retry_duration_ms | {float(llm_eval.get('avg_retry_duration_ms', 0.0)):.1f} |",
        "",
        "## 목표 기준",
        "",
        "| 목표 | 기준 | 달성 |",
        "| --- | --- | --- |",
        *[
            f"| {key} | {value} | {report.get('target_results', {}).get(key + '_met', '-')} |"
            for key, value in (report.get("targets") or {}).items()
        ],
        "",
        "## Scenario별 결과",
        "",
        "| Scenario | Pass | Alert | Insight Type | 주요 실패 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for item in report["scenarios"]:
        failure_codes = ", ".join(failure["code"] for failure in item["failures"]) or "-"
        type_values = ", ".join(insight_item["type"] for insight_item in item["generated_insights"][:3]) or "-"
        lines.append(
            f"| {item['label']} | {item['passed']} | {item['issue_detection']['alert_count']} | {type_values} | {failure_codes} |"
        )

    assessment = report["overall_assessment"]
    lines.extend(
        [
            "",
            "## 잘된 점",
            *[f"- {item}" for item in assessment["strengths"]],
            "",
            "## 미흡한 점",
            *[f"- {item}" for item in assessment["weaknesses"]],
            "",
            "## 개선 제안",
            *[f"- {item}" for item in assessment["improvement_priorities"]],
            "",
            "## Local LLM manual 평가",
            "",
            f"```powershell\n{report['local_llm_manual_command']}\n```",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_local_llm_insight_samples(json_path: Path, markdown_path: Path, report: dict[str, Any]) -> None:
    """Local LLM 샘플 리뷰 리포트를 JSON/Markdown으로 생성한다."""

    samples = [
        sample
        for scenario in report.get("scenarios", [])
        for sample in list(scenario.get("insight_samples") or [])
    ]
    payload = {
        "provider": report.get("provider"),
        "model": report.get("model"),
        "prompt_mode": (report.get("llm_evaluation") or {}).get("prompt_modes", []),
        "scenario_count": report.get("scenario_count"),
        "sample_count": len(samples),
        "samples": samples,
    }
    write_json(json_path, payload)

    lines = [
        "# Local LLM PublicAgencyInsight 샘플 리뷰",
        "",
        f"- Provider: `{payload['provider']}`",
        f"- Model: `{payload['model']}`",
        f"- Sample count: `{payload['sample_count']}`",
        "",
    ]
    for sample in samples:
        final = sample.get("final_insight_summary") or {}
        repair = sample.get("repair_diff") or {}
        lines.extend(
            [
                f"## {sample.get('scenario_label')}",
                "",
                f"- scenario_id: `{sample.get('scenario_id')}`",
                f"- direct_llm_success: `{sample.get('direct_llm_success')}`",
                f"- fallback_used: `{sample.get('fallback_used')}`",
                f"- fallback_reason: `{sample.get('fallback_reason')}`",
                f"- invalid_evidence_ids: `{', '.join(repair.get('invalid_evidence_ids') or []) or '-'}`",
                f"- removed_actions: `{repair.get('removed_actions', 0)}`",
                f"- repaired_actions: `{repair.get('repaired_actions', 0)}`",
                f"- retry_used/retry_success: `{repair.get('retry_used')}` / `{repair.get('retry_success')}`",
                "",
                "### Final Insight",
                "",
                f"- type: `{final.get('type')}`",
                f"- priority: `{final.get('priority')}`",
                f"- confidence/grounding/actionability: `{final.get('confidence')}` / `{final.get('grounding_score')}` / `{final.get('avg_actionability_score')}`",
                f"- title: {final.get('title')}",
                f"- summary: {final.get('summary')}",
                f"- problem: {final.get('problem_diagnosis')}",
                "",
                "### Recommended Actions",
                "",
            ]
        )
        for action in final.get("recommended_actions") or []:
            lines.append(
                f"- [{action.get('action_type')}] {action.get('action')} "
                f"(evidence: {', '.join(action.get('supporting_evidence_ids') or [])})"
            )
        lines.extend(["", "### Evidence Preview", ""])
        for evidence in sample.get("evidence_preview") or []:
            lines.append(f"- `{evidence.get('evidence_id')}`: {evidence.get('masked_text')}")
        review = sample.get("objective_review") or {}
        lines.extend(
            [
                "",
                "### Objective Review",
                "",
                *[f"- Strength: {item}" for item in review.get("strengths", [])],
                *[f"- Weakness: {item}" for item in review.get("weaknesses", [])],
                f"- Readiness: {review.get('public_official_readiness', '')}",
                "",
            ]
        )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_comparison_markdown(path: Path, comparison: dict[str, Any]) -> None:
    deltas = comparison["deltas"]
    lines = [
        "# Complaint Intelligence 개선 전후 비교",
        "",
        "| 지표 | Delta |",
        "| --- | ---: |",
        f"| alert_recall_delta | {deltas['alert_recall_delta']:.4f} |",
        f"| topic_hit_rate_delta | {deltas['topic_hit_rate_delta']:.4f} |",
        f"| false_positive_delta | {deltas['false_positive_delta']} |",
        f"| false_negative_delta | {deltas['false_negative_delta']} |",
        f"| expected_type_hit_rate_delta | {deltas['expected_type_hit_rate_delta']:.4f} |",
        f"| avg_actionability_score_delta | {deltas['avg_actionability_score_delta']:.4f} |",
        f"| pii_leak_rate_delta | {deltas['pii_leak_rate_delta']:.4f} |",
        f"| forbidden_ai_ops_term_rate_delta | {deltas['forbidden_ai_ops_term_rate_delta']:.4f} |",
        "",
        "## 좋아진 점",
        *[f"- {item}" for item in comparison["assessment"]["strengths"]],
        "",
        "## 악화/주의",
        *[f"- {item}" for item in comparison["assessment"]["regressions"] or ["확인된 regression은 없습니다."]],
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def comparison_output_path(output: Path) -> Path:
    name = output.name
    if name == "complaint_intelligence_eval_report_after_fake.json":
        return output.with_name("complaint_intelligence_eval_comparison_fake.json")
    if name == "complaint_intelligence_eval_report_local.json":
        return output.with_name("complaint_intelligence_eval_comparison_local.json")
    return output.with_name(f"{output.stem}_comparison{output.suffix}")


def _source_ids(events: list[dict[str, Any]]) -> list[str]:
    ids = []
    for event in events:
        source_id = event.get("source_id") or event.get("source_record_id") or event.get("id")
        if source_id:
            ids.append(str(source_id))
    return ids


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _limited_reason(
    *,
    requested_count: int,
    evaluated_count: int,
    scenario_limit: int | None,
    scenario_id: str | None,
) -> str | None:
    if evaluated_count >= requested_count:
        return None
    reasons: list[str] = []
    if scenario_id:
        reasons.append("scenario_id")
    if scenario_limit is not None:
        reasons.append("scenario_limit")
    return "+".join(reasons) if reasons else "filtered"


def _avg(values: Any) -> float:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return 0.0
    return round(mean(filtered), 4)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
    return round(ordered[index], 3)


def _rate(values: Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(1 for item in items if item) / len(items), 4)


def _delta(after: float | int, before: float | int) -> float:
    return round(float(after) - float(before), 4)


def _failure(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "severity": "error", "details": details or {}}


def _warning(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "severity": "warning", "details": details or {}}


def _has_error_failures(failures: list[dict[str, Any]]) -> bool:
    return any(item.get("severity") == "error" for item in failures)


if __name__ == "__main__":
    raise SystemExit(main())

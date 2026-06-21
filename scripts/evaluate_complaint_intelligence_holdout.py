"""Complaint Intelligence holdout 50건을 실제 분석 파이프라인으로 평가한다."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.repository import InMemoryComplaintIntelligenceRepository
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, PublicAgencyInsight
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.complaint_intelligence.public_insights.quality_gate import score_actionability
from scripts.evaluate_complaint_intelligence_scenarios import (
    contains_unmasked_pii,
    has_forbidden_ai_ops_terms,
    visible_insight_payload,
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate open-world Complaint Intelligence holdout.")
    parser.add_argument("--holdout", default="data/evaluation/complaint_intelligence_holdout_50.json")
    parser.add_argument("--output", default="reports/complaint_intelligence_holdout_eval_report.json")
    parser.add_argument("--provider", choices=["fake", "local", "disabled"], default="fake")
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--prompt-mode", default="compact")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--num-predict", type=int, default=1024)
    parser.add_argument("--no-print-report", action="store_true")
    args = parser.parse_args()

    report = evaluate_holdout(
        holdout_path=Path(args.holdout),
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        prompt_mode=args.prompt_mode,
        timeout_seconds=args.timeout_seconds,
        num_predict=args.num_predict,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    if not args.no_print_report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def evaluate_holdout(
    *,
    holdout_path: Path,
    provider: str,
    model: str,
    base_url: str,
    prompt_mode: str,
    timeout_seconds: float,
    num_predict: int,
) -> dict[str, Any]:
    started = perf_counter()
    payload = json.loads(holdout_path.read_text(encoding="utf-8"))
    events = [ComplaintIntelligenceEvent.model_validate(item) for item in payload.get("events", [])]
    config = build_config(
        provider=provider,
        model=model,
        base_url=base_url,
        prompt_mode=prompt_mode,
        timeout_seconds=timeout_seconds,
        num_predict=num_predict,
    )
    service = ComplaintIntelligenceService(
        repository=InMemoryComplaintIntelligenceRepository(),
        config=config,
    )
    result = service.run_analysis(
        events,
        mode=str(payload.get("mode") or "replay"),
        source_name=str(payload.get("source_name") or "complaint_intelligence_holdout_50"),
        as_of=datetime.fromisoformat(str(payload.get("as_of"))),
        metadata={"trigger": "holdout_eval", "provider": provider, "model": model},
    )
    alerts = service.list_issue_alerts()
    insights = service.list_public_insights()
    llm_metrics = service.public_insight_engine.get_last_generation_metrics()
    insight_metrics = summarize_insights(insights, service)
    visible_payload = {
        "alerts": [alert.model_dump(mode="json") for alert in alerts],
        "insights": [
            visible_insight_payload(insight, service.get_public_insight_evidence_pack(insight.insight_id))
            for insight in insights
        ],
    }
    pii_leak = contains_unmasked_pii(visible_payload)
    forbidden_terms = has_forbidden_ai_ops_terms(visible_payload)
    candidate_count = int(llm_metrics.get("candidate_count") or 0)
    direct_success_count = int(llm_metrics.get("direct_llm_success_count") or llm_metrics.get("llm_success_count") or 0)
    fallback_count = int(llm_metrics.get("fallback_count") or 0)
    report = {
        "evaluation_name": "complaint_intelligence_holdout_50",
        "holdout_file": str(holdout_path),
        "provider": provider,
        "model": model if provider == "local" else None,
        "prompt_mode": prompt_mode,
        "input_event_count": len(events),
        "run_id": result.run_id,
        "generated_alert_count": len(alerts),
        "generated_insight_count": len(insights),
        "high_priority_insight_count": sum(1 for item in insights if item.priority in {"HIGH", "CRITICAL"}),
        "fallback_rate": _safe_rate(fallback_count, candidate_count),
        "direct_llm_success_rate": _safe_rate(direct_success_count, candidate_count),
        "candidate_count": candidate_count,
        "grounding_pass_rate": insight_metrics["grounding_pass_rate"],
        "avg_grounding_score": insight_metrics["avg_grounding_score"],
        "avg_confidence": insight_metrics["avg_confidence"],
        "avg_actionability_score": insight_metrics["avg_actionability_score"],
        "evidence_pack_presence_rate": insight_metrics["evidence_pack_presence_rate"],
        "pii_leak_rate": 1.0 if pii_leak else 0.0,
        "forbidden_ai_ops_term_rate": 1.0 if forbidden_terms else 0.0,
        "llm_metrics": llm_metrics,
        "alert_summaries": [
            {
                "id": alert.id,
                "topic": alert.topic,
                "region": alert.region,
                "severity": alert.severity,
                "confidence": alert.confidence,
                "related_count": len(alert.related_ids),
            }
            for alert in alerts[:20]
        ],
        "insight_summaries": [
            {
                "insight_id": insight.insight_id,
                "type": insight.type,
                "priority": insight.priority,
                "topic": insight.topic,
                "confidence": insight.confidence,
                "grounding_score": insight.grounding_score,
                "avg_actionability_score": insight.metrics.get("avg_actionability_score"),
                "recommended_action_types": [action.action_type for action in insight.recommended_actions],
                "requires_human_review": insight.requires_human_review,
            }
            for insight in insights[:20]
        ],
        "failure_categories": failure_categories(insights, service, pii_leak, forbidden_terms),
        "qualitative_notes": [
            "holdout은 정답 label이 없는 open-world robustness 평가이므로 pass rate를 성능 주장으로 해석하지 않습니다.",
            "생성된 insight는 EvidencePack, GroundingVerifier, QualityGate 경로를 통과한 최종 read-model 기준입니다.",
            "raw PII와 prompt 원문은 리포트에 저장하지 않았습니다.",
        ],
        "duration_seconds": round(perf_counter() - started, 3),
    }
    return report


def build_config(
    *,
    provider: str,
    model: str,
    base_url: str,
    prompt_mode: str,
    timeout_seconds: float,
    num_predict: int,
):
    config = get_complaint_intelligence_config()
    llm_enabled = provider != "disabled"
    return replace(
        config,
        repository="memory",
        public_insight_llm_enabled=llm_enabled,
        public_insight_llm_provider=provider,
        public_insight_llm_model=model,
        public_insight_llm_base_url=base_url,
        public_insight_llm_prompt_mode=prompt_mode,
        public_insight_llm_timeout_seconds=timeout_seconds,
        public_insight_llm_num_predict=num_predict,
        public_insight_llm_action_retry_enabled=True,
        public_insight_min_candidate_complaint_count=3,
        min_affected_count=3,
    )


def summarize_insights(insights: list[PublicAgencyInsight], service: ComplaintIntelligenceService) -> dict[str, float]:
    if not insights:
        return {
            "grounding_pass_rate": 0.0,
            "avg_grounding_score": 0.0,
            "avg_confidence": 0.0,
            "avg_actionability_score": 0.0,
            "evidence_pack_presence_rate": 0.0,
        }
    actionability_scores = [
        score_actionability(action).score
        for insight in insights
        for action in insight.recommended_actions
    ]
    evidence_pack_count = sum(1 for insight in insights if service.get_public_insight_evidence_pack(insight.insight_id))
    return {
        "grounding_pass_rate": _safe_rate(sum(1 for insight in insights if insight.grounding_score >= 0.65), len(insights)),
        "avg_grounding_score": _avg(insight.grounding_score for insight in insights),
        "avg_confidence": _avg(insight.confidence for insight in insights),
        "avg_actionability_score": _avg(actionability_scores),
        "evidence_pack_presence_rate": _safe_rate(evidence_pack_count, len(insights)),
    }


def failure_categories(
    insights: list[PublicAgencyInsight],
    service: ComplaintIntelligenceService,
    pii_leak: bool,
    forbidden_terms: bool,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if pii_leak:
        failures.append({"code": "PII_LEAK", "severity": "critical"})
    if forbidden_terms:
        failures.append({"code": "FORBIDDEN_AI_OPS_TERM", "severity": "critical"})
    if not insights:
        failures.append({"code": "NO_PUBLIC_INSIGHT_CREATED", "severity": "warning"})
    for insight in insights:
        if not service.get_public_insight_evidence_pack(insight.insight_id):
            failures.append({"code": "MISSING_EVIDENCE_PACK", "insight_id": insight.insight_id, "severity": "error"})
        if not insight.recommended_actions:
            failures.append({"code": "EMPTY_RECOMMENDED_ACTIONS", "insight_id": insight.insight_id, "severity": "error"})
        if insight.grounding_score < 0.65:
            failures.append({"code": "LOW_GROUNDING_SCORE", "insight_id": insight.insight_id, "severity": "warning"})
    return failures


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Complaint Intelligence Holdout 50 평가 리포트",
        "",
        "## 평가 개요",
        "",
        f"- provider: `{report.get('provider')}`",
        f"- model: `{report.get('model') or '-'}`",
        f"- input_event_count: `{report.get('input_event_count')}`",
        f"- generated_alert_count: `{report.get('generated_alert_count')}`",
        f"- generated_insight_count: `{report.get('generated_insight_count')}`",
        f"- candidate_count: `{report.get('candidate_count')}`",
        f"- duration_seconds: `{report.get('duration_seconds')}`",
        "",
        "## 품질 지표",
        "",
        "| 지표 | 값 |",
        "| --- | ---: |",
        f"| fallback_rate | {report.get('fallback_rate', 0.0):.4f} |",
        f"| direct_llm_success_rate | {report.get('direct_llm_success_rate', 0.0):.4f} |",
        f"| grounding_pass_rate | {report.get('grounding_pass_rate', 0.0):.4f} |",
        f"| avg_grounding_score | {report.get('avg_grounding_score', 0.0):.4f} |",
        f"| avg_confidence | {report.get('avg_confidence', 0.0):.4f} |",
        f"| avg_actionability_score | {report.get('avg_actionability_score', 0.0):.4f} |",
        f"| evidence_pack_presence_rate | {report.get('evidence_pack_presence_rate', 0.0):.4f} |",
        f"| pii_leak_rate | {report.get('pii_leak_rate', 0.0):.4f} |",
        f"| forbidden_ai_ops_term_rate | {report.get('forbidden_ai_ops_term_rate', 0.0):.4f} |",
        "",
        "## 주요 alert",
        "",
    ]
    for alert in report.get("alert_summaries", [])[:10]:
        lines.append(f"- `{alert.get('topic')}` / `{alert.get('region')}` / severity `{alert.get('severity')}` / related `{alert.get('related_count')}`")
    lines.extend(["", "## 주요 insight", ""])
    for insight in report.get("insight_summaries", [])[:10]:
        lines.append(
            f"- `{insight.get('type')}` / `{insight.get('topic')}` / priority `{insight.get('priority')}` / actions `{', '.join(insight.get('recommended_action_types') or [])}`"
        )
    lines.extend(["", "## 실패/주의 항목", ""])
    failures = report.get("failure_categories") or []
    if not failures:
        lines.append("- 치명적 실패는 확인되지 않았습니다.")
    else:
        for failure in failures:
            lines.append(f"- `{failure.get('code')}` severity `{failure.get('severity')}` insight `{failure.get('insight_id', '-')}`")
    lines.extend(["", "## 해석 주의", ""])
    for note in report.get("qualitative_notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def _safe_rate(numerator: Any, denominator: Any) -> float:
    try:
        numerator_value = float(numerator or 0)
        denominator_value = float(denominator or 0)
    except Exception:
        return 0.0
    if denominator_value <= 0:
        return 0.0
    return round(numerator_value / denominator_value, 4)


def _avg(values: Any) -> float:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 4)


if __name__ == "__main__":
    raise SystemExit(main())

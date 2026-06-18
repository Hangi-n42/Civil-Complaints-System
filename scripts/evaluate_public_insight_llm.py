"""PublicAgencyInsight LLM provider 수동 평가 스크립트.

기본값은 fake provider이며, 로컬 Ollama 평가는 명시적으로 실행한다.

예:
  python scripts/evaluate_public_insight_llm.py --provider local --model exaone3.5:7.8b
  python scripts/evaluate_public_insight_llm.py --provider local --model exaone3.5:7.8b --scenario-limit 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.issue_detection import IssueDetectionEngine
from app.complaint_intelligence.public_insights.candidate_generator import (
    PublicInsightCandidate,
    PublicInsightCandidateGenerator,
)
from app.complaint_intelligence.public_insights.llm_provider import LocalLLMProvider
from app.complaint_intelligence.public_insights.quality_gate import InsightQualityGate
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PublicAgencyInsight LLM provider on golden scenarios.")
    parser.add_argument("--provider", choices=["fake", "local", "disabled"], default="fake")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--num-gpu", type=int, default=-1)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--num-predict", type=int, default=1536)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--keep-alive", default="10m")
    parser.set_defaults(stream=True)
    parser.add_argument("--stream", dest="stream", action="store_true")
    parser.add_argument("--no-stream", dest="stream", action="store_false")
    parser.add_argument("--max-candidates-per-scenario", type=int, default=1)
    parser.add_argument("--scenario-limit", type=int, default=0)
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument("--input-json", default="")
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    config = replace(
        get_complaint_intelligence_config(),
        public_insight_llm_enabled=args.provider != "disabled",
        public_insight_llm_provider=args.provider,
        public_insight_llm_model=args.model,
        public_insight_llm_base_url=args.base_url if args.provider == "local" else "",
        public_insight_llm_timeout_seconds=args.timeout_seconds,
        public_insight_llm_temperature=args.temperature,
        public_insight_llm_num_ctx=args.num_ctx,
        public_insight_llm_num_predict=args.num_predict,
        public_insight_llm_num_gpu=args.num_gpu,
        public_insight_llm_keep_alive=args.keep_alive,
        public_insight_llm_stream=args.stream,
        public_insight_min_candidate_complaint_count=4,
        public_insight_analysis_window_days=3650 if args.input_json else get_complaint_intelligence_config().public_insight_analysis_window_days,
    )
    issue_engine = IssueDetectionEngine(config=config)
    candidate_generator = PublicInsightCandidateGenerator(config=config)
    quality_gate = InsightQualityGate(
        min_grounding_score=config.public_insight_min_grounding_score,
        min_confidence=config.public_insight_min_confidence,
    )
    warmup_result = None
    if args.provider == "local" and not args.skip_warmup:
        warmup_result = _warm_up_local_llm(config)

    scenario_results: list[dict[str, Any]] = []
    scenarios = _load_shadow_scenarios(args.input_json, args.sample_limit) if args.input_json else _golden_scenarios()
    if args.scenario_limit > 0:
        scenarios = scenarios[: args.scenario_limit]
    for scenario in scenarios:
        started_at = time.perf_counter()
        scenario_now = scenario.get("now") or BASE_TIME
        alerts = issue_engine.detect(scenario["events"])
        candidates = candidate_generator.generate(scenario["events"], alerts, scenario_now)
        selected_candidates = _select_candidates(
            candidates,
            scenario.get("expected_types", []),
            args.max_candidates_per_scenario,
        )
        service = PublicInsightService(
            config=config,
            candidate_generator=_FixedCandidateGenerator(selected_candidates),
        )
        insights = service.generate_insights(scenario["events"], alerts, now=scenario_now)
        best = insights[0] if insights else None
        duration_seconds = round(time.perf_counter() - started_at, 3)
        if best is None:
            scenario_results.append(
                {
                    "scenario": scenario["name"],
                    "schema_valid": False,
                    "grounding_pass": False,
                    "actionability_score": 0.0,
                    "forbidden_terms": False,
                    "fallback": False,
                    "insight_type": None,
                    "candidate_count": len(candidates),
                    "evaluated_candidate_count": len(selected_candidates),
                    "duration_seconds": duration_seconds,
                    "failure": "no_insight",
                }
            )
            continue

        pack = service.get_evidence_pack(best.insight_id)
        gate = quality_gate.evaluate(best, pack)
        scenario_results.append(
            {
                "scenario": scenario["name"],
                "schema_valid": True,
                "grounding_pass": gate.passed,
                "actionability_score": float(best.metrics.get("avg_actionability_score", 0.0) or 0.0),
                "forbidden_terms": any(failure.code == "FORBIDDEN_AI_OPS_TERMS" for failure in gate.failures),
                "fallback": any("템플릿" in item or "fallback" in item.lower() for item in best.uncertainty),
                "insight_type": best.type,
                "candidate_count": len(candidates),
                "evaluated_candidate_count": len(selected_candidates),
                "duration_seconds": duration_seconds,
                "quality_failures": [failure.model_dump() for failure in gate.failures],
                "quality_warnings": [warning.model_dump() for warning in gate.warnings],
                "insight_excerpt": _insight_excerpt(best),
            }
        )

    report = _summary(args, scenario_results, warmup_result)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


def _summary(
    args: argparse.Namespace,
    scenario_results: list[dict[str, Any]],
    warmup_result: dict[str, Any] | None,
) -> dict[str, Any]:
    total = len(scenario_results)
    if total == 0:
        total = 1
    schema_valid_count = sum(1 for item in scenario_results if item["schema_valid"])
    grounding_pass_count = sum(1 for item in scenario_results if item["grounding_pass"])
    forbidden_count = sum(1 for item in scenario_results if item["forbidden_terms"])
    fallback_count = sum(1 for item in scenario_results if item["fallback"])
    actionability_scores = [float(item["actionability_score"]) for item in scenario_results]
    return {
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url if args.provider == "local" else "",
        "timeout_seconds": args.timeout_seconds,
        "max_candidates_per_scenario": args.max_candidates_per_scenario,
        "llm_options": {
            "temperature": args.temperature,
            "num_ctx": args.num_ctx,
            "num_predict": args.num_predict,
            "num_gpu": args.num_gpu,
            "keep_alive": args.keep_alive,
            "stream": args.stream,
        },
        "warmup": warmup_result,
        "scenario_count": len(scenario_results),
        "evaluation_mode": "shadow" if args.input_json else "golden",
        "input_json": args.input_json,
        "schema_valid_rate": round(schema_valid_count / total, 4),
        "grounding_pass_rate": round(grounding_pass_count / total, 4),
        "avg_actionability_score": round(sum(actionability_scores) / total, 4),
        "forbidden_term_rate": round(forbidden_count / total, 4),
        "fallback_rate": round(fallback_count / total, 4),
        "scenarios": scenario_results,
    }


def _golden_scenarios() -> list[dict[str, Any]]:
    night = BASE_TIME - timedelta(hours=15)
    commute = BASE_TIME - timedelta(minutes=30)
    return [
        {
            "name": "도로 침하/싱크홀 급증",
            "expected_types": ["SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED", "FACILITY_MAINTENANCE_PRIORITY"],
            "events": [
                _event("manual-sink-1", "도로에 구멍이 생겼습니다.", "중구"),
                _event("manual-sink-2", "아스팔트가 내려앉았습니다.", "중구"),
                _event("manual-sink-3", "차도 중간이 움푹 파였습니다.", "중구"),
                _event("manual-sink-4", "싱크홀 같은 게 생겼습니다.", "중구"),
                _event("manual-sink-5", "도로 바닥이 꺼져 위험합니다.", "중구"),
            ],
        },
        {
            "name": "복지 지원 기준/신청 절차",
            "expected_types": ["POLICY_IMPROVEMENT_OPPORTUNITY", "PUBLIC_GUIDANCE_NEEDED"],
            "events": [
                _event("manual-welfare-1", "복지 지원 기준이 불편합니다.", "중구"),
                _event("manual-welfare-2", "신청 절차가 너무 복잡합니다.", "중구"),
                _event("manual-welfare-3", "지원 기준 완화가 필요합니다.", "중구"),
                _event("manual-welfare-4", "제도 개선을 요청합니다.", "중구"),
                _event("manual-welfare-5", "필요서류가 무엇인지 모르겠습니다.", "중구"),
            ],
        },
        {
            "name": "대형폐기물 배출 안내",
            "expected_types": ["PUBLIC_GUIDANCE_NEEDED"],
            "events": [
                _event("manual-waste-1", "대형폐기물 배출 신청 방법을 모르겠습니다.", "상암동"),
                _event("manual-waste-2", "스티커 구매 안내가 부족합니다.", "상암동"),
                _event("manual-waste-3", "어디에서 신청해야 하나요?", "상암동"),
                _event("manual-waste-4", "필요서류가 있나요?", "상암동"),
                _event("manual-waste-5", "수거 기준 안내가 헷갈립니다.", "상암동"),
            ],
        },
        {
            "name": "공공자전거 앱 예약/대여 UX 불편",
            "expected_types": ["SERVICE_DESIGN_IMPROVEMENT", "ACCESSIBILITY_OR_USABILITY_ISSUE"],
            "events": [
                _event("manual-bike-1", "공공자전거 앱 예약 절차가 불편합니다.", "성산동"),
                _event("manual-bike-2", "대여 신청 단계가 너무 복잡합니다.", "성산동"),
                _event("manual-bike-3", "결제 오류가 자주 납니다.", "성산동"),
                _event("manual-bike-4", "예약 기준을 이해하기 어렵습니다.", "성산동"),
                _event("manual-bike-5", "앱 로그인 오류로 대여를 못 했습니다.", "성산동"),
            ],
        },
        {
            "name": "불법주정차 특정 시간대 반복",
            "expected_types": ["ENFORCEMENT_PRIORITY", "SEASONAL_OR_TIME_PATTERN"],
            "events": [
                _event("manual-parking-1", "초등학교 앞 불법주정차가 많습니다.", "연희동", received_at=commute),
                _event("manual-parking-2", "퇴근 시간마다 불법주차 때문에 위험합니다.", "연희동", received_at=commute),
                _event("manual-parking-3", "주정차 단속을 강화해주세요.", "연희동", received_at=commute),
                _event("manual-parking-4", "같은 위치에 계속 불법주차가 반복됩니다.", "연희동", received_at=commute),
                _event("manual-parking-5", "퇴근 시간대 단속 안내가 필요합니다.", "연희동", received_at=commute),
            ],
        },
        {
            "name": "악취 민원 야간 집중",
            "expected_types": ["SEASONAL_OR_TIME_PATTERN", "RECURRING_COMPLAINT_PATTERN"],
            "events": [
                _event(f"manual-odor-{index}", "야간마다 산업단지 악취와 냄새가 반복됩니다.", "상암동", received_at=night)
                for index in range(5)
            ],
        },
        {
            "name": "부서 처리 지연/미처리 누적",
            "expected_types": ["PROCESS_DELAY_RISK", "DEPARTMENT_WORKLOAD_BOTTLENECK"],
            "events": [
                _event(
                    f"manual-delay-{index}",
                    "도로 보수 요청이 아직 처리되지 않았습니다.",
                    "중구",
                    status="pending",
                    final_department="도로관리과",
                    handling_time_minutes=1800,
                )
                for index in range(5)
            ],
        },
        {
            "name": "재민원/반복 민원 증가",
            "expected_types": ["REOPEN_OR_REPEAT_RISK"],
            "events": [
                _event(
                    f"manual-repeat-{index}",
                    "같은 악취 민원이 계속 반복되어 재문의합니다.",
                    "상암동",
                    status="재민원",
                    reopened=True,
                )
                for index in range(5)
            ],
        },
    ]


@dataclass(frozen=True)
class _FixedCandidateGenerator:
    """평가 대상 후보를 고정해 로컬 LLM 반복 호출을 제한한다."""

    candidates: list[PublicInsightCandidate]

    def generate(self, events, issue_alerts=None, now=None):  # noqa: ANN001 - 서비스 주입용 최소 인터페이스
        return self.candidates


def _select_candidates(
    candidates: list[PublicInsightCandidate],
    expected_types: list[str],
    max_candidates: int,
) -> list[PublicInsightCandidate]:
    """시나리오 기대 유형을 우선해 평가할 후보를 고른다."""

    if max_candidates <= 0:
        return candidates
    expected_order = {insight_type: index for index, insight_type in enumerate(expected_types)}

    def sort_key(candidate: PublicInsightCandidate) -> tuple[int, int, int]:
        expected_rank = expected_order.get(str(candidate.type_hint), len(expected_order) + 1)
        count = int(candidate.trigger_metrics.get("complaint_count") or len(candidate.complaint_ids))
        return (expected_rank, -count, len(candidate.linked_alert_ids) * -1)

    return sorted(candidates, key=sort_key)[:max_candidates]


def _warm_up_local_llm(config) -> dict[str, Any]:  # noqa: ANN001 - dataclass replace 결과를 그대로 받는다.
    """작은 JSON 요청으로 Ollama 모델을 미리 로드한다."""

    started_at = time.perf_counter()
    # warm-up은 모델 로드와 GPU 오프로딩 확인만 목적이므로 짧은 생성으로 제한한다.
    warmup_config = replace(config, public_insight_llm_num_predict=32)
    try:
        result = LocalLLMProvider(warmup_config).generate_json('JSON만 반환하세요: {"ok": true}', {})
        return {
            "ok": True,
            "duration_seconds": round(time.perf_counter() - started_at, 3),
            "num_predict": warmup_config.public_insight_llm_num_predict,
            "response": result,
            "ollama_ps": _ollama_ps(config.public_insight_llm_base_url),
        }
    except Exception as exc:  # noqa: BLE001 - 수동 평가 리포트에 실패 원인만 남긴다.
        return {
            "ok": False,
            "duration_seconds": round(time.perf_counter() - started_at, 3),
            "num_predict": warmup_config.public_insight_llm_num_predict,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "ollama_ps": _ollama_ps(config.public_insight_llm_base_url),
        }


def _ollama_ps(base_url: str) -> dict[str, Any] | None:
    """Ollama 로드 모델과 CPU/GPU 배치를 리포트에 포함한다."""

    url = base_url.rstrip("/") + "/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _insight_excerpt(insight) -> dict[str, Any]:  # noqa: ANN001 - report serializer
    """리포트에서 사람이 바로 검토할 최소 인사이트 본문을 반환한다."""

    return {
        "title": insight.title,
        "summary": insight.summary,
        "problem_diagnosis": insight.problem_diagnosis,
        "recommended_actions": [action.model_dump(mode="json") for action in insight.recommended_actions],
        "uncertainty": list(insight.uncertainty),
        "representative_evidence_ids": list(insight.representative_complaint_ids),
        "extracted_aspects": [aspect.model_dump(mode="json") for aspect in insight.extracted_aspects],
        "citizen_requests": [request.model_dump(mode="json") for request in insight.citizen_requests],
    }


def _load_shadow_scenarios(path: str, sample_limit: int) -> list[dict[str, Any]]:
    """실제 JSON 데이터 일부를 shadow evaluation 시나리오로 변환한다."""

    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("input-json은 JSON 배열이어야 합니다.")
    events = [_event_from_record(record, index) for index, record in enumerate(records[: max(1, sample_limit)])]
    events = [event for event in events if event.body or event.masked_text]
    return [
        {
            "name": f"shadow:{Path(path).name}",
            "expected_types": [],
            "events": events,
            "now": max((event.received_at for event in events), default=BASE_TIME),
        }
    ]


def _event_from_record(record: dict[str, Any], index: int) -> ComplaintIntelligenceEvent:
    """처리된 실제 데이터 레코드를 평가용 이벤트로 변환한다."""

    text = _first_text(record, ("client_question", "body", "question", "content", "text", "title"))
    title = str(record.get("title") or "")
    if title and title not in text:
        text = f"{title}\n{text}".strip()
    event_id = str(record.get("source_id") or record.get("id") or _stable_record_id(record, index))
    received_at = _parse_date(record.get("consulting_date") or record.get("received_at"), index)
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=received_at,
        body=text,
        region=str(record.get("source") or "") or None,
        final_department=str(record.get("consulting_category") or "") or None,
        status=str(record.get("status") or "") or None,
    )


def _first_text(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return ""


def _stable_record_id(record: dict[str, Any], index: int) -> str:
    digest = hashlib.sha1(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    return f"shadow-{index}-{digest}"


def _parse_date(value: Any, index: int) -> datetime:
    if value:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return BASE_TIME - timedelta(minutes=index)


def _event(
    event_id: str,
    text: str,
    region: str,
    *,
    received_at: datetime | None = None,
    status: str | None = None,
    final_department: str | None = None,
    handling_time_minutes: float | None = None,
    reopened: bool = False,
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent(
        id=event_id,
        received_at=received_at or BASE_TIME - timedelta(minutes=5),
        body=text,
        region=region,
        status=status,
        final_department=final_department,
        handling_time_minutes=handling_time_minutes,
        reopened=reopened,
    )


if __name__ == "__main__":
    main()

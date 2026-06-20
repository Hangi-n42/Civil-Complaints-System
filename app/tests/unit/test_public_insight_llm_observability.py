from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import (
    set_complaint_intelligence_scheduler,
    set_complaint_intelligence_service,
)
from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.public_insights.llm_observability import (
    build_llm_observability_report,
)
from app.complaint_intelligence.repository import (
    AnalysisRunRecord,
    InMemoryComplaintIntelligenceRepository,
)
from app.complaint_intelligence.service import ComplaintIntelligenceService


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """공유 서비스와 스케줄러가 다른 테스트에 영향을 주지 않도록 격리한다."""

    yield
    set_complaint_intelligence_scheduler(None)
    set_complaint_intelligence_service(None)


def test_llm_observability_report_aggregates_run_metadata_only() -> None:
    runs = [
        _run("run-without-llm", minutes=30, metadata={"trigger": "scheduler"}),
        _run("run-local-1", minutes=20, metadata={"llm_metrics": _metrics_one()}),
        _run("run-local-2", minutes=10, metadata={"llm_metrics": _metrics_two()}),
    ]

    report = build_llm_observability_report(runs)

    assert report["run_count"] == 3
    assert report["llm_run_count"] == 2
    assert report["provider_counts"] == {"local": 2}
    assert report["model_counts"] == {"exaone3.5:7.8b-instruct": 2}
    assert report["quality_gate_pass_rate"] == 0.5
    assert report["grounding_pass_rate"] == 0.5
    assert report["fallback_rate"] == 0.5
    assert report["timeout_rate"] == 0.25
    assert report["error_type_counts"] == {"TimeoutError": 1, "ValueError": 1}
    assert report["avg_llm_duration_ms"] == 250.0
    assert report["p95_llm_duration_ms"] == 400.0
    assert report["slow_llm_rate"] == 0.5
    assert report["avg_actionability_score"] == 0.7
    assert report["avg_grounding_score"] == 0.6
    assert report["avg_confidence"] == 0.5
    assert report["discarded_count"] == 1
    assert report["period_start"] == (BASE_TIME - timedelta(minutes=30)).isoformat()
    assert report["period_end"] == (BASE_TIME - timedelta(minutes=5)).isoformat()


def test_llm_observability_api_filters_provider_and_model_without_pii() -> None:
    repository = InMemoryComplaintIntelligenceRepository()
    service = ComplaintIntelligenceService(
        repository=repository,
        config=get_complaint_intelligence_config(),
    )
    _save_run(repository, "local-run", _metrics_one())
    _save_run(
        repository,
        "fake-run",
        {
            **_metrics_two(),
            "llm_provider": "fake",
            "llm_model": "fake-public-insight",
        },
    )
    set_complaint_intelligence_service(service)
    client = TestClient(app)

    response = client.get(
        "/complaint-intelligence/public-insights/llm-observability",
        params={"provider": "local", "model": "exaone3.5:7.8b-instruct"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["runs_analyzed"] == 1
    assert payload["report"]["provider_counts"] == {"local": 1}
    assert payload["report"]["model_counts"] == {"exaone3.5:7.8b-instruct": 1}
    assert "010-1234-5678" not in response.text
    assert "prompt" not in response.text.lower()


def _run(run_id: str, *, minutes: int, metadata: dict[str, Any]) -> AnalysisRunRecord:
    started_at = BASE_TIME - timedelta(minutes=minutes)
    return AnalysisRunRecord(
        run_id=run_id,
        mode="replay",
        status="completed",
        source_name="unit",
        event_count=0,
        started_at=started_at,
        completed_at=started_at + timedelta(minutes=5),
        as_of=started_at,
        metadata=metadata,
    )


def _save_run(
    repository: InMemoryComplaintIntelligenceRepository,
    run_id: str,
    metrics: dict[str, Any],
) -> None:
    repository.save_analysis_run(
        run_id=run_id,
        mode="manual",
        source_name="unit",
        event_count=0,
        started_at=BASE_TIME,
        as_of=BASE_TIME,
        metadata={"trigger": "unit"},
    )
    repository.complete_analysis_run(
        run_id,
        status="completed",
        completed_at=BASE_TIME + timedelta(seconds=1),
        metadata={"llm_metrics": metrics},
    )


def _metrics_one() -> dict[str, Any]:
    return {
        "llm_provider": "local",
        "llm_model": "exaone3.5:7.8b-instruct",
        "candidate_trace_count": 2,
        "candidate_count": 2,
        "llm_attempt_count": 2,
        "fallback_count": 1,
        "slow_llm_count": 1,
        "discarded_count": 0,
        "error_types": {"TimeoutError": 1},
        "candidate_traces": [
            {
                "path": "llm",
                "llm_duration_ms": 100.0,
                "avg_actionability_score": 1.0,
                "grounding_score": 0.9,
                "confidence": 0.8,
                "quality_gate_failures": [],
            },
            {
                "path": "fallback",
                "llm_duration_ms": 300.0,
                "avg_actionability_score": 0.8,
                "grounding_score": 0.7,
                "confidence": 0.6,
                "quality_gate_failures": [],
            },
        ],
    }


def _metrics_two() -> dict[str, Any]:
    return {
        "llm_provider": "local",
        "llm_model": "exaone3.5:7.8b-instruct",
        "candidate_trace_count": 2,
        "candidate_count": 2,
        "llm_attempt_count": 2,
        "fallback_count": 1,
        "slow_llm_count": 1,
        "discarded_count": 1,
        "error_types": {"ValueError": 1},
        "candidate_traces": [
            {
                "path": "llm",
                "llm_duration_ms": 200.0,
                "avg_actionability_score": 0.6,
                "grounding_score": 0.5,
                "confidence": 0.4,
                "quality_gate_failures": [{"code": "grounding_low"}],
            },
            {
                "path": "discarded",
                "llm_duration_ms": 400.0,
                "avg_actionability_score": 0.4,
                "grounding_score": 0.3,
                "confidence": 0.2,
                "quality_gate_failures": [{"code": "schema_invalid"}],
            },
        ],
    }

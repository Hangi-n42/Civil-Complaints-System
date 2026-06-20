from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.complaint_intelligence.config import get_complaint_intelligence_config
from app.complaint_intelligence.public_insights.evidence_pack import (
    PublicInsightEvidencePack,
    evidence_pack_for_llm,
    valid_evidence_ids_for_pack,
)
from app.complaint_intelligence.public_insights.llm_provider import (
    LocalLLMProvider,
    PublicInsightLLMError,
    _parse_json_object_with_repair,
)
from app.complaint_intelligence.public_insights.llm_synthesizer import (
    PublicAgencyInsightDraft,
    PublicInsightLLMSynthesizer,
)
from app.complaint_intelligence.public_insights.service import PublicInsightService, _apply_human_review_policy
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, PublicAgencyInsight, RecommendedAction


def _pack() -> PublicInsightEvidencePack:
    return PublicInsightEvidencePack(
        candidate_id="candidate-1",
        type_hint="PUBLIC_GUIDANCE_NEEDED",
        topic_label="대형폐기물 배출 안내",
        region_summary={"dominant_region": "중구", "counts": {"중구": 5}},
        department_summary={"dominant_department": "청소행정과"},
        window_start=datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        complaint_count=5,
        baseline_count=0.0,
        trend_metrics={"complaint_count": 5, "surge_ratio": 5.0, "unused_verbose_metric": "drop"},
        operational_metrics={"open_count": 3, "reopened_count": 0},
        representative_complaints=[
            {
                "complaint_id": f"e-{idx}",
                "masked_text": "대형폐기물 배출 신청 방법을 모르겠습니다. 010-1234-5678 연락 주세요." * 4,
                "region": "중구",
                "status": "open",
                "structured_elements": {
                    "observation": {"text": "대형폐기물 배출 방법 문의가 반복됩니다."},
                    "request": {"text": "신청 방법 안내를 요청합니다."},
                    "context": {"text": "최근 같은 지역에서 반복 접수되었습니다."},
                },
            }
            for idx in range(6)
        ],
        extracted_aspects=[
            {"aspect": "안내 부족", "count": 5, "sentiment": "negative", "evidence_ids": ["e-1"]},
            {"aspect": "신청 절차", "count": 3, "sentiment": "negative", "evidence_ids": ["e-2"]},
            {"aspect": "지원 기준", "count": 1, "sentiment": "negative", "evidence_ids": ["e-3"]},
            {"aspect": "초과 항목", "count": 1, "sentiment": "negative", "evidence_ids": ["e-4"]},
        ],
        citizen_requests=[
            {"request": "신청 방법 안내", "count": 5, "request_type": "정보 제공", "evidence_ids": ["e-1"]},
            {"request": "절차 개선", "count": 2, "request_type": "절차 개선", "evidence_ids": ["e-2"]},
            {"request": "FAQ 보강", "count": 1, "request_type": "정보 제공", "evidence_ids": ["e-3"]},
            {"request": "초과 요청", "count": 1, "request_type": "정보 제공", "evidence_ids": ["e-4"]},
        ],
        linked_alert_ids=["issue-1"],
        allowed_action_catalog=["FAQ/안내 페이지 보강", "신청 절차 체크리스트 추가"],
    )


def test_compact_evidence_pack_serializer_masks_pii_and_reduces_payload() -> None:
    compact = evidence_pack_for_llm(_pack(), compact=True, max_representative_complaints=3, max_text_chars=80)
    rendered = json.dumps(compact, ensure_ascii=False)

    assert len(compact["representative_complaints"]) == 3
    assert len(compact["extracted_aspects"]) == 3
    assert len(compact["citizen_requests"]) == 3
    assert compact["valid_evidence_ids"] == valid_evidence_ids_for_pack(_pack(), max_ids=20)
    assert compact["allowed_action_types"][:2] == ["PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"]
    assert compact["preferred_action_types"][0] == "PUBLIC_GUIDANCE"
    assert "010-1234-5678" not in rendered
    assert "unused_verbose_metric" not in rendered


def test_compact_prompt_contains_json_only_rules() -> None:
    synthesizer = PublicInsightLLMSynthesizer(_SchemaEchoProvider(), prompt_mode="compact")
    prompt = synthesizer._build_prompt(_pack())

    assert "JSON 외 설명" in prompt
    assert "markdown fence" in prompt
    assert "recommended_actions는 가능하면 1개" in prompt
    assert "VALID_EVIDENCE_IDS" in prompt
    assert "ALLOWED_ACTION_TYPES" in prompt
    assert "preferred_action_types" in prompt
    assert "새 evidence id를 만들지 마라" in prompt
    assert "ALLOWED_ACTION_TYPES 밖의 action_type을 만들지 마라" in prompt


def test_human_review_policy_forces_required_risk_types_only() -> None:
    safety_pack = _pack().model_copy(update={"type_hint": "SAFETY_RISK_SIGNAL", "topic_label": "도로 침하/싱크홀 위험"})
    safety_insight = _insight("SAFETY_RISK_SIGNAL", "MEDIUM", requires_human_review=False)
    guidance_insight = _insight("PUBLIC_GUIDANCE_NEEDED", "LOW", requires_human_review=False)

    reviewed, safety_report = _apply_human_review_policy(safety_insight, safety_pack)
    unchanged, guidance_report = _apply_human_review_policy(guidance_insight, _pack())

    assert reviewed.requires_human_review is True
    assert safety_report["changed"] is True
    assert "risk_type" in safety_report["reasons"]
    assert unchanged.requires_human_review is False
    assert guidance_report == {"changed": False, "reasons": []}


def test_json_parser_repairs_fence_prefix_trailing_comma_and_python_literals() -> None:
    raw = """
설명입니다.
```json
{
  "requires_human_review": True,
  "expected_impact": None,
}
```
"""
    result = _parse_json_object_with_repair(raw)

    assert result.payload["requires_human_review"] is True
    assert result.payload["expected_impact"] is None
    assert "strip_markdown_fence" in result.repair_steps
    assert "remove_trailing_commas" in result.repair_steps
    assert "replace_python_literals" in result.repair_steps


def test_schema_validation_failure_is_not_silently_repaired() -> None:
    synthesizer = PublicInsightLLMSynthesizer(_InvalidDraftProvider(), prompt_mode="compact")

    with pytest.raises(PublicInsightLLMError) as exc:
        synthesizer.synthesize(_pack())

    assert exc.value.reason == "LLM_SCHEMA_VALIDATION_FAILED"


def test_raw_response_debug_is_disabled_by_default() -> None:
    provider = LocalLLMProvider(get_complaint_intelligence_config())

    assert provider.debug_raw_response is False


def test_raw_response_debug_masks_pii(tmp_path) -> None:
    config = replace(
        get_complaint_intelligence_config(),
        public_insight_llm_model="exaone3.5:7.8b",
        public_insight_llm_debug_raw_response=True,
        public_insight_llm_debug_raw_response_dir=str(tmp_path),
        public_insight_llm_debug_raw_response_max_chars=200,
    )
    provider = LocalLLMProvider(config)
    prompt = 'EVIDENCE_PACK_JSON:\n{"candidate_id":"candidate-pii"}'

    path = provider._write_raw_debug(prompt, '{"summary":"010-1234-5678로 연락"}')
    assert path is not None
    saved = json.loads(Path(path).read_text(encoding="utf-8"))

    assert saved["candidate_id"] == "candidate-pii"
    assert "010-1234-5678" not in saved["raw_response"]


def test_public_insight_service_records_specific_fallback_reason() -> None:
    config = replace(
        get_complaint_intelligence_config(),
        public_insight_llm_enabled=True,
        public_insight_min_candidate_complaint_count=3,
    )
    service = PublicInsightService(config=config, llm_provider=_BrokenProvider())
    events = [
        ComplaintIntelligenceEvent(
            id=f"fallback-reason-{idx}",
            received_at=datetime(2026, 6, 20, 8, idx, tzinfo=timezone.utc),
            body="대형폐기물 배출 신청 방법 안내가 필요합니다.",
            region="중구",
        )
        for idx in range(5)
    ]

    insights = service.generate_insights(events, now=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc))
    metrics = service.get_last_generation_metrics()

    assert insights
    assert metrics["failure_reasons"]["LLM_JSON_PARSE_FAILED"] >= 1
    assert metrics["json_parse_failure_count"] >= 1
    assert metrics["fallback_count"] >= 1


def test_action_retry_recovers_empty_actions_once() -> None:
    config = replace(
        get_complaint_intelligence_config(),
        public_insight_llm_enabled=True,
        public_insight_llm_provider="local",
        public_insight_min_candidate_complaint_count=3,
    )
    service = PublicInsightService(config=config, llm_provider=_ActionRetryProvider())

    insights = service.generate_insights(_retry_events(), now=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc))
    metrics = service.get_last_generation_metrics()

    assert insights
    assert metrics["action_retry_attempt_count"] >= 1
    assert metrics["action_retry_success_count"] >= 1
    assert metrics["fallback_count"] == 0
    assert insights[0].recommended_actions[0].supporting_evidence_ids


def test_action_retry_failure_keeps_fallback() -> None:
    config = replace(
        get_complaint_intelligence_config(),
        public_insight_llm_enabled=True,
        public_insight_llm_provider="local",
        public_insight_min_candidate_complaint_count=3,
    )
    service = PublicInsightService(config=config, llm_provider=_ActionRetryFailureProvider())

    insights = service.generate_insights(_retry_events(), now=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc))
    metrics = service.get_last_generation_metrics()

    assert insights
    assert metrics["action_retry_attempt_count"] >= 1
    assert metrics["action_retry_success_count"] == 0
    assert metrics["fallback_count"] >= 1
    assert metrics["fallback_due_to_empty_actions_count"] >= 1


class _SchemaEchoProvider:
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise AssertionError("이 테스트는 prompt만 확인합니다.")


class _InvalidDraftProvider:
    def generate_json(self, prompt: str, schema: dict) -> dict:
        return {"title": "불완전한 JSON"}


class _BrokenProvider:
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise PublicInsightLLMError(
            "LLM_JSON_PARSE_FAILED",
            "broken json",
            repair_steps=["strip_markdown_fence"],
        )


class _ActionRetryProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.calls += 1
        if schema.get("required") != ["recommended_actions"]:
            return _draft_payload("missing-id")
        return {
            "recommended_actions": [
                {
                    "action": "대형폐기물 안내 페이지와 FAQ를 보강합니다.",
                    "horizon": "SHORT_TERM",
                    "action_type": "PUBLIC_GUIDANCE",
                    "responsible_unit_hint": None,
                    "why": "안내 부족 민원이 반복되었습니다.",
                    "supporting_evidence_ids": ["retry-event-0"],
                    "expected_impact": "반복 문의를 줄일 가능성이 있습니다.",
                    "risk_or_dependency": "정확한 배출 기준은 담당 부서 확인이 필요합니다.",
                }
            ]
        }


class _ActionRetryFailureProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.calls += 1
        if schema.get("required") != ["recommended_actions"]:
            return _draft_payload("missing-id")
        raise PublicInsightLLMError("LLM_JSON_PARSE_FAILED", "retry failed")


def _draft_payload(evidence_id: str) -> dict:
    return {
        "title": "대형폐기물 배출 안내 개선",
        "summary": "대형폐기물 배출 방법 문의가 반복됩니다.",
        "problem_diagnosis": "시민이 배출 신청 절차를 이해하기 어려울 가능성이 있습니다.",
        "root_cause_hypotheses": [],
        "extracted_aspects": [],
        "citizen_requests": [],
        "recommended_actions": [
            {
                "action": "운영 개선 과제를 정리합니다.",
                "horizon": "SHORT_TERM",
                "action_type": "PROCESS_IMPROVEMENT",
                "responsible_unit_hint": None,
                "why": "일반적인 개선이 필요합니다.",
                "supporting_evidence_ids": [evidence_id],
                "expected_impact": "반복 문의 감소 가능성이 있습니다.",
                "risk_or_dependency": "담당자 검토가 필요합니다.",
            }
        ],
        "expected_impact": "반복 문의 감소 가능성이 있습니다.",
        "uncertainty": [],
        "requires_human_review": True,
        "explanation": "EvidencePack 기반 초안입니다.",
    }


def _retry_events() -> list[ComplaintIntelligenceEvent]:
    return [
        ComplaintIntelligenceEvent(
            id=f"retry-event-{idx}",
            received_at=datetime(2026, 6, 20, 8, idx, tzinfo=timezone.utc),
            body="대형폐기물 배출 신청 방법과 스티커 구매 안내가 부족합니다.",
            region="중구",
            final_department="청소행정과",
        )
        for idx in range(5)
    ]


def _insight(insight_type: str, priority: str, *, requires_human_review: bool) -> PublicAgencyInsight:
    action = RecommendedAction(
        action="대형폐기물 FAQ와 안내 페이지를 보강합니다.",
        horizon="SHORT_TERM",
        action_type="PUBLIC_GUIDANCE",
        responsible_unit_hint=None,
        why="안내 부족 민원이 반복되었습니다.",
        supporting_evidence_ids=["e-1"],
        expected_impact="반복 문의 감소 가능성이 있습니다.",
        risk_or_dependency="담당 부서 확인이 필요합니다.",
    )
    return PublicAgencyInsight(
        insight_id=f"insight-{insight_type}",
        type=insight_type,
        priority=priority,
        title="대형폐기물 배출 안내 개선",
        summary="대형폐기물 배출 방법 문의가 반복됩니다.",
        problem_diagnosis="시민이 배출 신청 절차를 이해하기 어려울 가능성이 있습니다.",
        topic="대형폐기물 배출 안내",
        target_area="행정 안내",
        affected_count=5,
        window_start=datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        metrics={"avg_actionability_score": 1.0},
        evidence=[
            {
                "complaint_id": "e-1",
                "masked_text": "대형폐기물 배출 안내가 부족합니다.",
                "received_at": datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
            }
        ],
        representative_complaint_ids=["e-1"],
        recommended_actions=[action],
        requires_human_review=requires_human_review,
        confidence=0.82,
        grounding_score=0.9,
        created_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        explanation="EvidencePack 기반 인사이트입니다.",
    )

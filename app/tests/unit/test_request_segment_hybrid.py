"""request_segments LLM hybrid fallback 검증."""

from __future__ import annotations

import json

import app.retrieval.analyzers.request_segment_hybrid as hybrid
from app.retrieval.analyzers.request_segment_hybrid import (
    FallbackDecision,
    assess_segment_actionability,
    assess_fallback_need,
    assess_llm_pre_gate,
    build_block_prompt,
    build_analyzer_output_hybrid,
    build_source_blocks,
    evaluate_assist_limited_v2_strict_gate,
    LLMValidationResult,
    parse_llm_json_response,
    validate_block_llm_segments,
    validate_llm_segments,
)


def _patch_hybrid_rule_and_decision(monkeypatch, *, rule_segments=None, reasons=None, trace=None):
    rule_segments = rule_segments or ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    reasons = reasons or ["numbered_under_split"]
    trace = trace or {}

    def fake_rule_output(**kwargs):
        return {
            "request_segments": rule_segments,
            "intent_count": len(rule_segments),
            "is_multi": len(rule_segments) >= 2,
            "complexity_trace": trace,
        }

    monkeypatch.setattr(hybrid, "build_analyzer_output", fake_rule_output)
    monkeypatch.setattr(
        hybrid,
        "assess_fallback_need",
        lambda source_text, rule_output: FallbackDecision(True, reasons, len(rule_segments), 0),
    )


def _block_llm_response(segment_texts=None, evidence_ids=None):
    segment_texts = segment_texts or ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    evidence_ids = evidence_ids or [["S1"], ["S2"]]
    return json.dumps(
        {
            "decision": "replace",
            "segments": [
                {"text": text, "evidence_ids": ids}
                for text, ids in zip(segment_texts, evidence_ids)
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )


def _accepted_validation(segment_texts=None):
    return LLMValidationResult(
        True,
        segment_texts or ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."],
        None,
        confidence=0.9,
        decision="replace",
    )


def test_hybrid_off_returns_rule_output_without_llm_call():
    called = False

    def fake_call(prompt: str) -> str:
        nonlocal called
        called = True
        return "{}"

    text = "1. 국내전시회 지원 내용은 뭔가요? 2. 해외전시회 지원 내용은 뭔가요?"

    output = build_analyzer_output_hybrid(text, "industry", question=text, mode="off", llm_call=fake_call)

    assert called is False
    assert output["request_segments"] == [
        "국내전시회 지원 내용은 뭔가요?",
        "해외전시회 지원 내용은 뭔가요?",
    ]


def test_assess_fallback_need_detects_single_segment_with_numbered_candidates():
    text = "1. 첫 번째 요청을 알려주세요. 2. 두 번째 요청도 알려주세요."
    rule_output = {
        "request_segments": [text],
        "complexity_trace": {"fallback_segment_used": True},
    }

    decision = assess_fallback_need(text, rule_output)

    assert decision.should_call is True
    assert "fallback_single_segment" in decision.reasons
    assert "numbered_under_split" in decision.reasons


def test_assess_fallback_need_ignores_duplicate_title_question_candidates():
    text = "도로 보수 일정은 언제인가요?\n도로 보수 일정은 언제인가요?"
    rule_output = {
        "request_segments": ["도로 보수 일정은 언제인가요?"],
        "complexity_trace": {},
    }

    decision = assess_fallback_need(text, rule_output)

    assert decision.should_call is False
    assert decision.reasons == []


def test_pre_gate_allows_clear_numbered_list_candidate():
    rule_output = {
        "request_segments": ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."],
        "complexity_trace": {},
    }

    gate = assess_llm_pre_gate(
        policy="v2_strict",
        fallback_reasons=["numbered_under_split"],
        source_text="1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        rule_output=rule_output,
        prompt_style="block",
    )

    assert gate.decision == "allow_call"
    assert gate.reason is None


def test_pre_gate_skips_non_list_fallback_candidate():
    gate = assess_llm_pre_gate(
        policy="v2_strict",
        fallback_reasons=["fallback_single_segment"],
        source_text="도로 보수 일정을 알려주세요.",
        rule_output={"request_segments": ["도로 보수 일정을 알려주세요."], "complexity_trace": {}},
        prompt_style="block",
    )

    assert gate.decision == "skip_shadow_only"
    assert gate.reason == "not_list_trigger_candidate"


def test_pre_gate_reviews_phone_dialogue_candidate():
    gate = assess_llm_pre_gate(
        policy="v2_strict",
        fallback_reasons=["numbered_under_split"],
        source_text="여보세요.\n1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        rule_output={"request_segments": ["도로 보수 일정을 알려주세요."], "complexity_trace": {}},
        prompt_style="block",
    )

    assert gate.decision == "review_required"
    assert gate.reason == "excluded_risk_tag:phone_dialogue"
    assert "phone_dialogue" in gate.risk_tags


def test_pre_gate_reviews_weak_request_signal_candidate():
    gate = assess_llm_pre_gate(
        policy="v2_strict",
        fallback_reasons=["numbered_under_split", "weak_request_signal"],
        source_text="1. 도로 주변 내용\n2. 공원 주변 내용",
        rule_output={"request_segments": ["도로 주변 내용", "공원 주변 내용"], "complexity_trace": {}},
        prompt_style="block",
    )

    assert gate.decision == "review_required"
    assert gate.reason.startswith("excluded_risk_tag:weak_request_signal")


def test_pre_gate_reviews_segment_limit_case():
    gate = assess_llm_pre_gate(
        policy="v2_strict",
        fallback_reasons=["numbered_under_split"],
        source_text="1. 도로 보수 일정을 알려주세요.",
        rule_output={
            "request_segments": ["도로 보수 일정을 알려주세요."] * 6,
            "complexity_trace": {"segment_limit_applied": True},
        },
        prompt_style="block",
    )

    assert gate.decision == "review_required"
    assert gate.reason == "excluded_risk_tag:segment_limit_case"


def test_hybrid_shadow_records_accepted_llm_segments_without_replacing():
    text = "1. 첫 번째 요청을 알려주세요. 2. 두 번째 요청도 알려주세요."

    def fake_call(prompt: str) -> str:
        return json.dumps(
            {
                "request_segments": [
                    {
                        "text": "첫 번째 요청을 알려주세요.",
                        "evidence": "첫 번째 요청을 알려주세요.",
                        "reason": "독립 질의",
                    },
                    {
                        "text": "두 번째 요청도 알려주세요.",
                        "evidence": "두 번째 요청도 알려주세요.",
                        "reason": "독립 질의",
                    },
                ],
                "is_multi": True,
                "confidence": 0.88,
            },
            ensure_ascii=False,
        )

    rule_only = build_analyzer_output_hybrid(text, "industry", question=text, mode="off")
    output = build_analyzer_output_hybrid(text, "industry", question=text, mode="shadow", llm_call=fake_call)

    assert output["request_segments"] == rule_only["request_segments"]
    trace = output["complexity_trace"]
    assert trace["llm_fallback_triggered"] is True
    assert trace["llm_segments_accepted"] is True
    assert trace["request_segments_source"] == "rule"


def test_hybrid_assist_policy_none_keeps_rule_after_validation():
    text = "1. 첫 번째 요청을 알려주세요. 2. 두 번째 요청도 알려주세요."

    def fake_call(prompt: str) -> str:
        return json.dumps(
            {
                "request_segments": [
                    {
                        "text": "첫 번째 요청을 알려주세요.",
                        "evidence": "첫 번째 요청을 알려주세요.",
                        "reason": "독립 질의",
                    },
                    {
                        "text": "두 번째 요청도 알려주세요.",
                        "evidence": "두 번째 요청도 알려주세요.",
                        "reason": "독립 질의",
                    },
                ],
                "is_multi": True,
                "confidence": 0.9,
            },
            ensure_ascii=False,
        )

    rule_only = build_analyzer_output_hybrid(
        "지원 전시회 문의",
        "industry",
        question=text,
        mode="off",
    )
    output = build_analyzer_output_hybrid(
        "지원 전시회 문의",
        "industry",
        question=text,
        mode="assist",
        llm_call=fake_call,
    )

    trace = output["complexity_trace"]
    assert output["request_segments"] == rule_only["request_segments"]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_segments_accepted"] is True
    assert trace["llm_assist_policy"] == "none"
    assert trace["llm_assist_gate"] == "shadow_only"
    assert trace["llm_assist_gate_rejected_reason"] == "policy_none"


def test_hybrid_assist_unknown_policy_keeps_rule(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch)
    monkeypatch.setattr(hybrid, "validate_block_llm_segments", lambda *args, **kwargs: _accepted_validation())

    output = build_analyzer_output_hybrid(
        "1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        "construction",
        question="1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        mode="assist",
        prompt_style="block",
        assist_policy="unexpected_policy",
        llm_call=lambda prompt: _block_llm_response(),
    )

    trace = output["complexity_trace"]
    assert output["request_segments"] == ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_assist_policy"] == "none"
    assert trace["llm_assist_gate"] == "shadow_only"
    assert trace["llm_assist_gate_rejected_reason"] == "policy_none"


def test_hybrid_rejects_hallucinated_evidence_and_keeps_rule_segments():
    text = "1. 첫 번째 요청을 알려주세요. 2. 두 번째 요청도 알려주세요."

    def fake_call(prompt: str) -> str:
        return json.dumps(
            {
                "request_segments": [
                    {
                        "text": "주차장 증설을 요청합니다.",
                        "evidence": "주차장 증설",
                        "reason": "원문에 없는 요청",
                    }
                ],
                "is_multi": False,
                "confidence": 0.95,
            },
            ensure_ascii=False,
        )

    output = build_analyzer_output_hybrid(
        text,
        "construction",
        question=text,
        mode="assist",
        llm_call=fake_call,
    )

    assert output["request_segments"] == ["첫 번째 요청을 알려주세요."]
    trace = output["complexity_trace"]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_segments_accepted"] is False
    assert trace["llm_hallucination_suspected"] is True


def test_hybrid_shadow_v2_strict_records_gate_without_replacing(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch)
    monkeypatch.setattr(hybrid, "validate_block_llm_segments", lambda *args, **kwargs: _accepted_validation())

    output = build_analyzer_output_hybrid(
        "1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        "construction",
        question="1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        mode="shadow",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(),
    )

    assert output["request_segments"] == ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    trace = output["complexity_trace"]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_assist_policy"] == "v2_strict"
    assert trace["llm_assist_gate"] == "allow_assist"
    assert trace["llm_assist_gate_rejected_reason"] is None


def test_hybrid_assist_v2_strict_replaces_only_when_gate_allows(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, rule_segments=["규칙 기반 단일 요청입니다."])
    monkeypatch.setattr(
        hybrid,
        "validate_block_llm_segments",
        lambda *args, **kwargs: _accepted_validation(["도로 보수 일정을 알려주세요."]),
    )

    output = build_analyzer_output_hybrid(
        "1. 도로 보수 일정을 알려주세요.",
        "construction",
        question="1. 도로 보수 일정을 알려주세요.",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(["도로 보수 일정을 알려주세요."], [["S1"]]),
    )

    assert output["request_segments"] == ["도로 보수 일정을 알려주세요."]
    assert output["intent_count"] == 1
    assert output["is_multi"] is False
    trace = output["complexity_trace"]
    assert trace["request_segments_source"] == "llm_fallback"
    for key in (
        "llm_fallback_mode",
        "llm_assist_policy",
        "llm_assist_gate",
        "llm_assist_gate_reason",
        "llm_assist_gate_rejected_reason",
        "llm_pre_gate",
        "llm_segments_accepted",
    ):
        assert key in trace
    assert trace["llm_fallback_mode"] == "assist"
    assert trace["llm_assist_policy"] == "v2_strict"
    assert trace["llm_pre_gate"] == "allow_call"
    assert trace["llm_assist_gate"] == "allow_assist"


def test_hybrid_assist_v2_strict_keeps_rule_when_gate_rejects(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, reasons=["numbered_under_split", "weak_request_signal"])
    monkeypatch.setattr(hybrid, "validate_block_llm_segments", lambda *args, **kwargs: _accepted_validation())

    output = build_analyzer_output_hybrid(
        "1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        "construction",
        question="1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(),
    )

    trace = output["complexity_trace"]
    assert output["request_segments"] == ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_pre_gate"] == "review_required"
    assert trace["llm_pre_gate_rejected_reason"].startswith("excluded_risk_tag:weak_request_signal")
    assert trace["llm_assist_gate"] == "not_evaluated"


def test_hybrid_shadow_v2_strict_pre_gate_skip_does_not_call_llm(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, reasons=["fallback_single_segment"])
    called = False

    def fake_call(prompt: str) -> str:
        nonlocal called
        called = True
        return _block_llm_response()

    output = build_analyzer_output_hybrid(
        "도로 보수 일정을 알려주세요.",
        "construction",
        question="도로 보수 일정을 알려주세요.",
        mode="shadow",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=fake_call,
    )

    trace = output["complexity_trace"]
    assert called is False
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_pre_gate"] == "skip_shadow_only"
    assert trace["llm_pre_gate_rejected_reason"] == "not_list_trigger_candidate"
    assert trace["llm_segments_accepted"] is False


def test_hybrid_assist_v2_strict_pre_gate_review_keeps_rule(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, reasons=["numbered_under_split", "weak_request_signal"])
    called = False

    def fake_call(prompt: str) -> str:
        nonlocal called
        called = True
        return _block_llm_response()

    output = build_analyzer_output_hybrid(
        "1. 도로 주변 내용\n2. 공원 주변 내용",
        "construction",
        question="1. 도로 주변 내용\n2. 공원 주변 내용",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=fake_call,
    )

    trace = output["complexity_trace"]
    assert called is False
    assert output["request_segments"] == ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    assert trace["llm_pre_gate"] == "review_required"
    assert trace["llm_pre_gate_rejected_reason"].startswith("excluded_risk_tag:weak_request_signal")


def test_hybrid_assist_v2_strict_keeps_rule_for_phone_dialogue_risk(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch)
    monkeypatch.setattr(hybrid, "validate_block_llm_segments", lambda *args, **kwargs: _accepted_validation())

    output = build_analyzer_output_hybrid(
        "여보세요.\n1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        "construction",
        question="여보세요.\n1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(),
    )

    trace = output["complexity_trace"]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_pre_gate"] == "review_required"
    assert "phone_dialogue" in trace["llm_pre_gate_risk_tags"]
    assert trace["llm_assist_gate"] == "not_evaluated"


def test_hybrid_assist_v2_strict_keeps_rule_for_segment_limit_case(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, trace={"segment_limit_applied": True})
    monkeypatch.setattr(hybrid, "validate_block_llm_segments", lambda *args, **kwargs: _accepted_validation())

    output = build_analyzer_output_hybrid(
        "1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        "construction",
        question="1. 도로 보수 일정을 알려주세요.\n2. 임시 안전 조치를 요청합니다.",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(),
    )

    trace = output["complexity_trace"]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_pre_gate"] == "review_required"
    assert "segment_limit_case" in trace["llm_pre_gate_risk_tags"]
    assert trace["llm_assist_gate"] == "not_evaluated"


def test_hybrid_assist_v2_strict_keeps_rule_when_evidence_validation_fails(monkeypatch):
    _patch_hybrid_rule_and_decision(monkeypatch, rule_segments=["도로 보수 일정을 알려주세요."])

    output = build_analyzer_output_hybrid(
        "도로 보수 일정을 알려주세요.",
        "construction",
        question="도로 보수 일정을 알려주세요.",
        mode="assist",
        prompt_style="block",
        assist_policy="v2_strict",
        llm_call=lambda prompt: _block_llm_response(["도로 보수 일정을 알려주세요."], [["S99"]]),
    )

    trace = output["complexity_trace"]
    assert output["request_segments"] == ["도로 보수 일정을 알려주세요."]
    assert trace["request_segments_source"] == "rule"
    assert trace["llm_assist_gate"] == "reject"
    assert trace["llm_assist_gate_rejected_reason"] == "unknown_evidence_id:0"


def test_segment_actionability_rejects_generic_segments():
    assert assess_segment_actionability("\uc870\uce58 \uc694\uccad") == "generic_weak_actionability"
    assert assess_segment_actionability("\uc774\uc6a9 \ubc29\ubc95 \ubb38\uc758") == "generic_weak_actionability"
    assert assess_segment_actionability("\uc548\uc804 \uace0\ub824 \uc694\uccad") == "generic_weak_actionability"


def test_segment_actionability_rejects_method_or_condition_only_segment():
    segment = "\ub178\uba74 \ubc30\uc218 \uacbd\uc0ac \uace0\ub824\uc0ac\ud56d"

    assert assess_segment_actionability(segment) == "method_or_condition_only_segment"


def test_segment_actionability_keeps_actionable_requests():
    assert assess_segment_actionability("\ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694.") is None
    assert assess_segment_actionability("\uc784\uc2dc \uc548\uc804 \uc870\uce58\ub97c \uc694\uccad\ud569\ub2c8\ub2e4.") is None


def test_v2_strict_gate_reviews_generic_actionability_segment():
    validation = LLMValidationResult(
        True,
        ["\uc870\uce58 \uc694\uccad"],
        None,
        confidence=0.9,
        decision="replace",
    )
    raw_response = json.dumps(
        {
            "decision": "replace",
            "segments": [{"text": "\uc870\uce58 \uc694\uccad", "evidence_ids": ["S1"]}],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    gate = evaluate_assist_limited_v2_strict_gate(
        validation=validation,
        rule_output={"request_segments": ["\ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694."], "complexity_trace": {}},
        fallback_reasons=["numbered_under_split"],
        source_text="1. \ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694.\n2. \uc784\uc2dc \uc548\uc804 \uc870\uce58\ub97c \uc694\uccad\ud569\ub2c8\ub2e4.",
        prompt_style="block",
        raw_response=raw_response,
    )

    assert gate.decision == "review_required"
    assert gate.reason == "generic_weak_actionability"


def test_v2_strict_gate_keeps_clear_numbered_actionable_segments_allowed():
    validation = LLMValidationResult(
        True,
        [
            "\ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694.",
            "\uc784\uc2dc \uc548\uc804 \uc870\uce58\ub97c \uc694\uccad\ud569\ub2c8\ub2e4.",
        ],
        None,
        confidence=0.9,
        decision="replace",
    )
    raw_response = json.dumps(
        {
            "decision": "replace",
            "segments": [
                {"text": "\ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694.", "evidence_ids": ["S1"]},
                {"text": "\uc784\uc2dc \uc548\uc804 \uc870\uce58\ub97c \uc694\uccad\ud569\ub2c8\ub2e4.", "evidence_ids": ["S2"]},
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    gate = evaluate_assist_limited_v2_strict_gate(
        validation=validation,
        rule_output={"request_segments": ["\ub3c4\ub85c \ubcf4\uc218 \ubc0f \uc548\uc804 \uc870\uce58 \ubb38\uc758"], "complexity_trace": {}},
        fallback_reasons=["numbered_under_split"],
        source_text="1. \ub3c4\ub85c \ubcf4\uc218 \uc77c\uc815\uc744 \uc54c\ub824\uc8fc\uc138\uc694.\n2. \uc784\uc2dc \uc548\uc804 \uc870\uce58\ub97c \uc694\uccad\ud569\ub2c8\ub2e4.",
        prompt_style="block",
        raw_response=raw_response,
    )

    assert gate.decision == "allow_assist"
    assert gate.reason is None


def test_validate_llm_segments_rejects_admin_action_segment():
    raw = json.dumps(
        {
            "request_segments": [
                {
                    "text": "담당 부서에서 현장 확인 후 조치하겠습니다.",
                    "evidence": "담당 부서에서 현장 확인 후 조치하겠습니다.",
                    "reason": "행정기관 조치",
                }
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_llm_segments(raw, source_text="담당 부서에서 현장 확인 후 조치하겠습니다.")

    assert result.accepted is False
    assert result.reject_reason == "low_value_or_admin_segment:0"


def test_validate_llm_segments_rejects_overlong_segment():
    segment = "도로 보수 요청 " + ("상세 설명 " * 40)
    raw = json.dumps(
        {
            "request_segments": [
                {
                    "text": segment,
                    "evidence": segment,
                    "reason": "장문 후보",
                }
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_llm_segments(raw, source_text=segment)

    assert result.accepted is False
    assert result.reject_reason == "segment_too_long:0"


def test_build_source_blocks_prioritizes_request_blocks():
    text = "\n".join(
        [
            "안녕하세요.",
            "도로 보수 일정을 알려주세요.",
            "감사합니다.",
            "임시 안전 조치를 요청합니다.",
        ]
    )

    blocks = build_source_blocks(text, max_blocks=2)

    assert len(blocks) == 2
    assert [block.id for block in blocks] == ["S1", "S2"]
    assert "도로 보수" in blocks[0].text
    assert "임시 안전" in blocks[1].text


def test_build_block_prompt_uses_evidence_ids_schema():
    blocks = build_source_blocks("도로 보수 일정을 알려주세요.", max_blocks=3)
    prompt = build_block_prompt(blocks, {"request_segments": ["도로 보수 일정을 알려주세요."]})

    assert "evidence_ids" in prompt
    assert "decision" in prompt
    assert "S1:" in prompt


def test_validate_block_llm_segments_accepts_existing_evidence_ids():
    blocks = build_source_blocks("도로 보수 일정을 알려주세요.\n임시 안전 조치를 요청합니다.", max_blocks=3)
    raw = json.dumps(
        {
            "decision": "replace",
            "segments": [
                {"text": "도로 보수 일정을 알려주세요.", "evidence_ids": ["S1"]},
                {"text": "임시 안전 조치를 요청합니다.", "evidence_ids": ["S2"]},
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_block_llm_segments(raw, source_blocks=blocks, rule_output={"request_segments": []})

    assert result.accepted is True
    assert result.segments == ["도로 보수 일정을 알려주세요.", "임시 안전 조치를 요청합니다."]
    assert result.decision == "replace"


def test_validate_block_llm_segments_rejects_unknown_evidence_id():
    blocks = build_source_blocks("도로 보수 일정을 알려주세요.", max_blocks=3)
    raw = json.dumps(
        {
            "decision": "replace",
            "segments": [{"text": "도로 보수 일정을 알려주세요.", "evidence_ids": ["S99"]}],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_block_llm_segments(raw, source_blocks=blocks, rule_output={"request_segments": []})

    assert result.accepted is False
    assert result.reject_reason == "unknown_evidence_id:0"
    assert result.hallucination_suspected is True


def test_validate_block_llm_segments_rejects_schema_error():
    blocks = build_source_blocks("도로 보수 일정을 알려주세요.", max_blocks=3)
    raw = json.dumps({"decision": "replace", "segments": [{"text": "도로 보수 일정을 알려주세요."}]})

    result = validate_block_llm_segments(raw, source_blocks=blocks, rule_output={"request_segments": []})

    assert result.accepted is False
    assert result.reject_reason == "missing_text_or_evidence_ids:0"


def test_validate_block_llm_segments_keep_rule_and_abstain_do_not_replace():
    blocks = build_source_blocks("도로 보수 일정을 알려주세요.", max_blocks=3)

    keep = validate_block_llm_segments(
        '{"decision":"keep_rule","segments":[],"confidence":0.0}',
        source_blocks=blocks,
        rule_output={"request_segments": ["도로 보수 일정을 알려주세요."]},
    )
    abstain = validate_block_llm_segments(
        '{"decision":"abstain","segments":[],"confidence":0.0}',
        source_blocks=blocks,
        rule_output={"request_segments": ["도로 보수 일정을 알려주세요."]},
    )

    assert keep.accepted is False
    assert keep.reject_reason == "keep_rule"
    assert abstain.accepted is False
    assert abstain.reject_reason == "abstain"


def test_validate_block_llm_segments_rejects_phone_dialogue_over_split():
    text = "\n".join(
        [
            "여보세요?",
            "네 잠시만요.",
            "이용 방법을 알려주세요?",
            "주차 위치는 어디인가요?",
            "현장 접수 가능한가요?",
            "현장 예매 가능한가요?",
        ]
    )
    blocks = build_source_blocks(text, max_blocks=10)
    raw = json.dumps(
        {
            "decision": "replace",
            "segments": [
                {"text": "이용 방법을 알려주세요?", "evidence_ids": ["S3"]},
                {"text": "주차 위치는 어디인가요?", "evidence_ids": ["S4"]},
                {"text": "현장 접수 가능한가요?", "evidence_ids": ["S5"]},
                {"text": "현장 예매 가능한가요?", "evidence_ids": ["S6"]},
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_block_llm_segments(raw, source_blocks=blocks, rule_output={"request_segments": []})

    assert result.accepted is False
    assert result.reject_reason == "phone_dialogue_over_split"


def test_validate_block_llm_segments_rejects_long_proposal_over_split():
    text = "\n".join(
        [
            "재개발 구역 확대 건의",
            "1. 특정 지역을 재개발 구역에 추가 검토 요청합니다. " + ("배경 설명 " * 30),
            "2. 개발 불균형 해소 방안을 검토 요청합니다. " + ("배경 설명 " * 30),
            "3. 상가 밀집 지역 개발 어려움을 고려해 주세요. " + ("배경 설명 " * 30),
            "4. 철도 인근 개발 연계성을 검토 요청합니다. " + ("배경 설명 " * 30),
        ]
    )
    blocks = build_source_blocks(text, max_blocks=10)
    raw = json.dumps(
        {
            "decision": "replace",
            "segments": [
                {"text": "특정 지역을 재개발 구역에 추가 검토 요청합니다.", "evidence_ids": ["S2"]},
                {"text": "개발 불균형 해소 방안을 검토 요청합니다.", "evidence_ids": ["S3"]},
                {"text": "상가 밀집 지역 개발 어려움을 고려해 주세요.", "evidence_ids": ["S4"]},
                {"text": "철도 인근 개발 연계성을 검토 요청합니다.", "evidence_ids": ["S5"]},
            ],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )

    result = validate_block_llm_segments(raw, source_blocks=blocks, rule_output={"request_segments": ["재개발 구역 확대 건의"]})

    assert result.accepted is False
    assert result.reject_reason == "long_legal_or_proposal_over_split"


def test_parse_llm_json_response_handles_fence_and_trailing_comma():
    raw = '설명\n```json\n{"decision":"keep_rule","segments":[],"confidence":0.0,}\n```'

    parsed = parse_llm_json_response(raw)

    assert parsed == {"decision": "keep_rule", "segments": [], "confidence": 0.0}

"""request_segments LLM hybrid fallback wrapper.

규칙 기반 `complexity_analyzer`는 1차 판정기로 유지하고, 이 모듈은 불확실한
케이스에서만 선택적으로 LLM 후보를 검증한다. 기본 설정은 off라 기존 동작을
바꾸지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

import httpx

from app.core.config import settings
from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output

HybridMode = Literal["off", "shadow", "assist"]
PromptStyle = Literal["text", "block"]
AssistPolicy = Literal["none", "v2_strict"]
AssistGateDecision = Literal["allow_assist", "shadow_only", "review_required", "reject"]
PreGateDecision = Literal["allow_call", "skip_shadow_only", "review_required"]
LLMCall = Callable[[str], str]

MAX_SEGMENTS = 6
MIN_SEGMENTS = 1
MAX_LLM_SEGMENT_CHARS = 240
MAX_LLM_EVIDENCE_CHARS = 320
MAX_SOURCE_BLOCK_CHARS = 320
_SUPPORT_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_SUPPORT_STOPWORDS = {
    "요청",
    "문의",
    "문의합니다",
    "질의",
    "확인",
    "가능",
    "여부",
    "방법",
    "절차",
    "일정",
    "관련",
    "대한",
    "대해",
    "알려",
    "알려주세요",
    "해주세요",
    "해주시기",
    "바랍니다",
    "합니다",
    "주세요",
    "검토",
    "처리",
    "조치",
    "개선",
}
ASSIST_TRIGGER_ALLOWLIST = {"numbered_under_split", "heading_list_under_split"}
STRICT_ASSIST_EXCLUDED_REASONS = {
    "weak_request_signal",
    "possible_over_split",
    "phone_dialogue_uncertain",
    "segment_too_long",
}
STRICT_ASSIST_EXCLUDED_RISK_TAGS = {
    "phone_dialogue",
    "long_legal_or_policy",
    "long_proposal",
    "segment_limit_case",
    "weak_request_signal",
}
STRICT_ASSIST_DIALOGUE_MARKERS = (
    "여보세요",
    "아 네",
    "아 그럼",
    "아 그러면",
    "아 홈페이지",
    "네,",
    "네. 여보세요",
    "예,",
    "수고하세요",
)
STRICT_ASSIST_REQUEST_CUES = (
    "문의",
    "요청",
    "확인",
    "알려",
    "궁금",
    "가능",
    "여부",
    "부탁",
    "해 주세요",
    "해주세요",
    "알고 싶",
)

_NUMBERED_ITEM_RE = re.compile(
    r"(?:^|\s|\n)(?:[1-9][0-9]?[.),]|[①②③④⑤⑥⑦⑧⑨⑩]|[가-하][.),]|[-•∙])\s*"
)
_HEADING_RE = re.compile(
    r"(?:답변\s*요청\s*사항|요청\s*사항|요청\s*내용|제안\s*내용|의문\s*및\s*요청\s*사항|"
    r"문의\s*사항|질의\s*사항|질문\s*사항|확인\s*사항)"
)
_REQUEST_CUE_RE = re.compile(
    r"(?:요청|문의|질의|궁금|알려|확인|조치|개선|설치|보수|수리|철거|단속|점검|"
    r"신청|가능|여부|언제|어떻게|왜|무엇|어디|뭔가요|인지|\?)"
)
_WEAK_PHONE_RE = re.compile(r"^(?:아|네|예|음|어|그럼|그러면).{0,36}(?:맞죠|그\s*말이죠|가능해요)[?？.!。！？]*$")
_ADMIN_ACTION_RE = re.compile(
    r"(?:귀하의\s*민원|검토\s*결과|처리\s*결과|현장\s*확인\s*후|담당\s*부서에서|"
    r"조치하겠습니다|안내드립니다|답변드립니다)"
)
_LOW_VALUE_RE = re.compile(
    r"^(?:안녕하세요|수고하십니다|감사합니다|답변\s*부탁드립니다|빠른\s*답변\s*부탁드립니다)[.!?。！？]*$"
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_BLOCK_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_LEGAL_REFERENCE_RE = re.compile(r"(?:제\s*\d+\s*조|시행령|시행규칙|법률|조례|고시|훈령)")


@dataclass(frozen=True)
class FallbackDecision:
    """LLM fallback 호출 여부와 사유."""

    should_call: bool
    reasons: list[str]
    numbered_candidate_count: int
    weak_segment_count: int


@dataclass(frozen=True)
class LLMValidationResult:
    """LLM 응답 검증 결과."""

    accepted: bool
    segments: list[str]
    reject_reason: str | None
    hallucination_suspected: bool = False
    confidence: float | None = None
    decision: str | None = None


@dataclass(frozen=True)
class SourceBlock:
    """조건 B prompt에 전달하는 원문 근거 블록."""

    id: str
    text: str
    score: int
    index: int


@dataclass(frozen=True)
class AssistGateResult:
    """LLM assist 결과를 실제 교체에 사용할지 판단한 결과."""

    decision: AssistGateDecision
    reason: str | None
    risk_tags: list[str]
    evidence_reference_count: int


@dataclass(frozen=True)
class LLMPreGateResult:
    """LLM 호출 전에 비용이 큰 후보를 거를지 판단한 결과."""

    decision: PreGateDecision
    reason: str | None
    risk_tags: list[str]


def build_analyzer_output_hybrid(
    text: str,
    topic_type: str = "general",
    *,
    title: str | None = None,
    question: str | None = None,
    mode: str | None = None,
    prompt_style: str | None = None,
    assist_policy: str | None = None,
    llm_call: LLMCall | None = None,
) -> dict:
    """규칙 기반 analyzer 결과에 선택적 LLM fallback을 얹는다.

    - off: 기존 규칙 기반 결과를 그대로 반환한다.
    - shadow: LLM 후보를 검증하고 trace에만 기록한다.
    - assist: 검증 통과 시 `request_segments`/`intent_count`/`is_multi`를 교체한다.
    """
    rule_output = build_analyzer_output(text=text, topic_type=topic_type, title=title, question=question)
    normalized_mode = _normalize_mode(mode or settings.REQUEST_SEGMENT_LLM_MODE)
    normalized_assist_policy = _normalize_assist_policy(
        assist_policy or settings.REQUEST_SEGMENT_LLM_ASSIST_POLICY
    )
    if normalized_mode == "off":
        return rule_output

    source_text = _source_text(text=text, title=title, question=question)
    decision = assess_fallback_need(source_text, rule_output)
    trace = dict(rule_output.get("complexity_trace") or {})
    trace.update(
        {
            "request_segments_source": "rule",
            "llm_fallback_mode": normalized_mode,
            "llm_fallback_triggered": decision.should_call,
            "llm_fallback_reason": ",".join(decision.reasons) if decision.reasons else None,
            "llm_segments_accepted": False,
            "llm_segments_rejected_reason": None,
            "llm_hallucination_suspected": False,
            "llm_assist_policy": normalized_assist_policy,
            "llm_assist_gate": "not_evaluated",
            "llm_assist_gate_reason": None,
            "llm_assist_gate_rejected_reason": None,
            "llm_assist_gate_risk_tags": None,
            "llm_assist_gate_evidence_count": 0,
            "llm_pre_gate": "not_evaluated",
            "llm_pre_gate_reason": None,
            "llm_pre_gate_rejected_reason": None,
            "llm_pre_gate_risk_tags": None,
        }
    )
    rule_output = {**rule_output, "complexity_trace": trace}
    if not decision.should_call:
        return rule_output

    normalized_prompt_style = _normalize_prompt_style(prompt_style or settings.REQUEST_SEGMENT_LLM_PROMPT_STYLE)
    trace["llm_prompt_style"] = normalized_prompt_style
    pre_gate = assess_llm_pre_gate(
        policy=normalized_assist_policy,
        fallback_reasons=decision.reasons,
        source_text=source_text,
        rule_output=rule_output,
        prompt_style=normalized_prompt_style,
    )
    _record_pre_gate_trace(trace, pre_gate)
    if pre_gate.decision != "allow_call":
        return {**rule_output, "complexity_trace": trace}

    if normalized_prompt_style == "block":
        source_blocks = build_source_blocks(
            source_text,
            max_blocks=max(1, settings.REQUEST_SEGMENT_LLM_SOURCE_BLOCK_LIMIT),
        )
        trace["llm_source_block_count"] = len(source_blocks)
        raw_response = _call_llm(
            prompt=build_block_prompt(source_blocks, rule_output),
            llm_call=llm_call,
            num_predict=settings.REQUEST_SEGMENT_LLM_BLOCK_NUM_PREDICT,
        )
    else:
        source_blocks = []
        raw_response = _call_llm(
            prompt=build_llm_prompt(source_text, rule_output),
            llm_call=llm_call,
            num_predict=settings.REQUEST_SEGMENT_LLM_NUM_PREDICT,
        )
    if raw_response is None:
        trace["llm_segments_rejected_reason"] = _provider_unavailable_reason()
        return {**rule_output, "complexity_trace": trace}

    if normalized_prompt_style == "block":
        validation = validate_block_llm_segments(
            raw_response,
            source_blocks=source_blocks,
            rule_output=rule_output,
            fallback_reasons=decision.reasons,
        )
    else:
        validation = validate_llm_segments(raw_response, source_text=source_text)
    trace["llm_segments_accepted"] = validation.accepted
    trace["llm_segments_rejected_reason"] = validation.reject_reason
    trace["llm_hallucination_suspected"] = validation.hallucination_suspected
    trace["llm_fallback_confidence"] = validation.confidence
    trace["llm_segment_count"] = len(validation.segments)
    trace["llm_decision"] = validation.decision
    gate = _evaluate_assist_gate(
        policy=normalized_assist_policy,
        validation=validation,
        rule_output=rule_output,
        fallback_reasons=decision.reasons,
        source_text=source_text,
        prompt_style=normalized_prompt_style,
        raw_response=raw_response,
    )
    _record_assist_gate_trace(trace, gate)

    if normalized_mode == "shadow" or not validation.accepted:
        return {**rule_output, "complexity_trace": trace}
    if gate.decision != "allow_assist":
        return {**rule_output, "complexity_trace": trace}
    if normalized_prompt_style == "block" and not _assist_replace_allowed(decision.reasons):
        trace["llm_segments_rejected_reason"] = "assist_trigger_not_allowed"
        trace["llm_segments_accepted"] = False
        return {**rule_output, "complexity_trace": trace}

    trace["request_segments_source"] = "llm_fallback"
    updated = {
        **rule_output,
        "request_segments": validation.segments,
        "intent_count": len(validation.segments),
        "is_multi": len(validation.segments) >= 2,
        "complexity_trace": {**trace, "intent_count": len(validation.segments), "segment_count": len(validation.segments)},
    }
    return updated


def assess_fallback_need(source_text: str, rule_output: dict) -> FallbackDecision:
    """규칙 기반 결과가 LLM fallback 후보인지 보수적으로 판정한다."""
    trace = rule_output.get("complexity_trace") if isinstance(rule_output.get("complexity_trace"), dict) else {}
    segments = [str(item or "").strip() for item in rule_output.get("request_segments") or [] if str(item or "").strip()]
    numbered_count = len(_NUMBERED_ITEM_RE.findall(source_text or ""))
    strong_candidate_count = _strong_request_candidate_count(source_text)
    weak_count = sum(1 for segment in segments if not _REQUEST_CUE_RE.search(segment))
    reasons: list[str] = []

    if trace.get("fallback_segment_used"):
        reasons.append("fallback_single_segment")
    if len(segments) == 1 and strong_candidate_count >= 2:
        reasons.append("strong_candidate_single_segment")
    if numbered_count >= 2 and len(segments) < min(numbered_count, MAX_SEGMENTS):
        reasons.append("numbered_under_split")
    if _HEADING_RE.search(source_text or "") and len(segments) < 2:
        reasons.append("heading_list_under_split")
    if len(segments) >= 5 and weak_count >= 1:
        reasons.append("possible_over_split")
    if any(len(segment) > 260 for segment in segments):
        reasons.append("segment_too_long")
    if weak_count >= 2:
        reasons.append("weak_request_signal")
    if _looks_like_phone_dialogue(source_text) and (len(segments) <= 1 or len(segments) >= 5):
        reasons.append("phone_dialogue_uncertain")

    return FallbackDecision(
        should_call=bool(reasons),
        reasons=reasons,
        numbered_candidate_count=numbered_count,
        weak_segment_count=weak_count,
    )


def assess_llm_pre_gate(
    *,
    policy: AssistPolicy,
    fallback_reasons: list[str],
    source_text: str,
    rule_output: dict,
    prompt_style: PromptStyle,
) -> LLMPreGateResult:
    """LLM 호출 전 cheap gate. v2_strict 내부 실험 경로에서만 호출을 줄인다."""
    if policy == "none":
        return LLMPreGateResult("allow_call", "policy_none", [])
    if policy != "v2_strict":
        return LLMPreGateResult("review_required", "unknown_policy", [])
    if prompt_style != "block":
        return LLMPreGateResult("review_required", "non_block_prompt_style", [])
    if not ASSIST_TRIGGER_ALLOWLIST.intersection(fallback_reasons):
        return LLMPreGateResult("skip_shadow_only", "not_list_trigger_candidate", [])

    risk_tags = _strict_assist_risk_tags(source_text, rule_output, fallback_reasons)
    excluded_risks = sorted(set(risk_tags).intersection(STRICT_ASSIST_EXCLUDED_RISK_TAGS))
    if excluded_risks:
        return LLMPreGateResult("review_required", f"excluded_risk_tag:{','.join(excluded_risks)}", risk_tags)

    excluded_reasons = sorted(set(fallback_reasons).intersection(STRICT_ASSIST_EXCLUDED_REASONS))
    if excluded_reasons:
        return LLMPreGateResult(
            "review_required",
            f"excluded_fallback_reason:{','.join(excluded_reasons)}",
            risk_tags,
        )

    rule_segments = [str(item or "").strip() for item in rule_output.get("request_segments") or [] if str(item or "").strip()]
    if len(rule_segments) >= MAX_SEGMENTS:
        return LLMPreGateResult("review_required", "segment_limit_case", risk_tags)

    if len(str(source_text or "")) > 1800:
        return LLMPreGateResult("review_required", "source_too_long_for_pregate", risk_tags)

    source_blocks = build_source_blocks(source_text, max_blocks=8)
    cue_block_count = sum(1 for block in source_blocks if _has_strict_assist_request_cue(block.text))
    if cue_block_count == 0:
        return LLMPreGateResult("review_required", "weak_source_block_request_cue", risk_tags)

    return LLMPreGateResult("allow_call", None, risk_tags)


def build_llm_prompt(source_text: str, rule_output: dict) -> str:
    """원문 근거 기반 request_segments 추출용 JSON-only prompt."""
    rule_segments = json.dumps(rule_output.get("request_segments") or [], ensure_ascii=False)
    return (
        "당신은 한국어 민원 request_segments 검수기입니다.\n"
        "원문에서 시민이 실제로 요구하거나 묻는 독립 처리 요청만 추출하세요.\n"
        "배경 설명, 인사말, 피해 서술만 있는 문장, 상담사/행정기관 조치 예상 문구는 제외하세요.\n"
        "원문에 없는 요청을 만들면 안 됩니다. 각 항목의 evidence는 원문에 그대로 존재하는 짧은 구절이어야 합니다.\n"
        f"segment 수는 {MIN_SEGMENTS}~{MAX_SEGMENTS}개입니다.\n"
        "반드시 JSON만 출력하세요.\n\n"
        f"[원문]\n{source_text[:3500]}\n\n"
        f"[규칙 기반 후보]\n{rule_segments}\n\n"
        "[출력 형식]\n"
        '{"request_segments":[{"text":"도로 보수 일정을 알려주세요.","evidence":"도로 보수 일정은 언제인가요?","reason":"독립 질의"}],"is_multi":true,"confidence":0.82}'
    )


def build_source_blocks(source_text: str, *, max_blocks: int = 30) -> list[SourceBlock]:
    """조건 B용 원문 block을 만들고 요청 가능성이 높은 block을 우선 선택한다."""
    raw_chunks = _split_source_blocks(source_text)
    candidates: list[SourceBlock] = []
    seen: set[str] = set()
    for index, chunk in enumerate(raw_chunks):
        text = _normalize_text(chunk)
        if not text:
            continue
        if len(text) > MAX_SOURCE_BLOCK_CHARS:
            text = text[:MAX_SOURCE_BLOCK_CHARS].rstrip()
        key = _compact(text)
        if key in seen:
            continue
        seen.add(key)
        score = _score_source_block(text, index)
        candidates.append(SourceBlock(id="", text=text, score=score, index=index))

    selected = sorted(candidates, key=lambda item: (-item.score, item.index))[:max_blocks]
    ordered = sorted(selected, key=lambda item: item.index)
    return [
        SourceBlock(id=f"S{block_index}", text=block.text, score=block.score, index=block.index)
        for block_index, block in enumerate(ordered, start=1)
    ]


def build_block_prompt(source_blocks: list[SourceBlock], rule_output: dict) -> str:
    """source block ID 기반 request_segments 추출 prompt."""
    rule_segments = json.dumps(rule_output.get("request_segments") or [], ensure_ascii=False)
    block_text = "\n".join(f"{block.id}: {block.text}" for block in source_blocks)
    return (
        "당신은 한국어 민원 request_segments 검수기입니다.\n"
        "아래 source block에서 시민이 실제로 요구하거나 묻는 독립 처리 요청만 추출하세요.\n"
        "배경 설명, 인사말, 감사/마무리, 상담사/행정기관의 조치 예상 문구는 요청으로 만들지 마세요.\n"
        "증거 문장을 직접 쓰지 말고 반드시 source block ID만 evidence_ids에 넣으세요.\n"
        "원문 block에 없는 요청을 만들면 안 됩니다. 애매하면 keep_rule 또는 abstain을 선택하세요.\n"
        "전화 대화체나 긴 법령/제안서에서 독립 요청이 확실하지 않으면 keep_rule을 선택하세요.\n"
        f"replace일 때 segment 수는 {MIN_SEGMENTS}~{MAX_SEGMENTS}개입니다.\n"
        "반드시 JSON만 출력하세요.\n\n"
        "[source blocks]\n"
        f"{block_text}\n\n"
        f"[규칙 기반 후보]\n{rule_segments}\n\n"
        "[출력 형식]\n"
        '{"decision":"replace","segments":[{"text":"도로 보수 일정을 알려주세요.","evidence_ids":["S3"]}],"confidence":0.82}\n'
        '{"decision":"keep_rule","segments":[],"confidence":0.0}'
    )


def validate_llm_segments(raw_response: str, *, source_text: str) -> LLMValidationResult:
    """LLM JSON 응답을 원문 근거 기반으로 검증한다."""
    parsed = parse_llm_json_response(raw_response)
    if not isinstance(parsed, dict):
        return LLMValidationResult(False, [], "invalid_json", hallucination_suspected=True)

    raw_confidence = parsed.get("confidence")
    confidence = _safe_float(raw_confidence)
    if raw_confidence is None:
        return LLMValidationResult(False, [], "missing_confidence")
    if confidence is None:
        return LLMValidationResult(False, [], "invalid_confidence")
    if confidence < settings.REQUEST_SEGMENT_LLM_MIN_CONFIDENCE:
        return LLMValidationResult(False, [], "low_confidence", confidence=confidence)

    raw_segments = parsed.get("request_segments")
    if not isinstance(raw_segments, list) or not (MIN_SEGMENTS <= len(raw_segments) <= MAX_SEGMENTS):
        return LLMValidationResult(False, [], "invalid_segment_count", confidence=confidence)

    accepted: list[str] = []
    seen: set[str] = set()
    normalized_source = _compact(source_text)
    for index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            return LLMValidationResult(False, [], f"invalid_segment_item:{index}", confidence=confidence)
        text = _normalize_text(item.get("text"))
        evidence = _normalize_text(item.get("evidence"))
        if not text or not evidence:
            return LLMValidationResult(False, [], f"missing_text_or_evidence:{index}", confidence=confidence)
        if len(text) > MAX_LLM_SEGMENT_CHARS or len(evidence) > MAX_LLM_EVIDENCE_CHARS:
            return LLMValidationResult(False, [], f"segment_too_long:{index}", confidence=confidence)
        if _is_invalid_segment(text) or _is_invalid_segment(evidence):
            return LLMValidationResult(False, [], f"low_value_or_admin_segment:{index}", confidence=confidence)
        if _compact(evidence) not in normalized_source:
            return LLMValidationResult(
                False,
                [],
                f"evidence_not_in_source:{index}",
                hallucination_suspected=True,
                confidence=confidence,
            )
        if not _REQUEST_CUE_RE.search(text) and not _REQUEST_CUE_RE.search(evidence):
            return LLMValidationResult(False, [], f"weak_request_signal:{index}", confidence=confidence)
        key = _compact(text)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(text)

    accepted = _dedupe_near_duplicate_texts(accepted)
    if not accepted:
        return LLMValidationResult(False, [], "empty_after_dedup", confidence=confidence)
    return LLMValidationResult(True, accepted, None, confidence=confidence)


def validate_block_llm_segments(
    raw_response: str,
    *,
    source_blocks: list[SourceBlock],
    rule_output: dict,
    fallback_reasons: list[str] | None = None,
) -> LLMValidationResult:
    """조건 B의 evidence_ids 기반 LLM 응답을 검증한다."""
    parsed = parse_llm_json_response(raw_response)
    if not isinstance(parsed, dict):
        return LLMValidationResult(False, [], "invalid_json", hallucination_suspected=True)

    decision = _normalize_decision(parsed.get("decision"))
    if decision in {"keep_rule", "abstain"}:
        return LLMValidationResult(False, [], decision, decision=decision)
    if decision != "replace":
        return LLMValidationResult(False, [], "invalid_decision", decision=decision)

    raw_confidence = parsed.get("confidence")
    confidence = _safe_float(raw_confidence)
    if raw_confidence is None:
        return LLMValidationResult(False, [], "missing_confidence", decision=decision)
    if confidence is None:
        return LLMValidationResult(False, [], "invalid_confidence", decision=decision)
    if confidence < settings.REQUEST_SEGMENT_LLM_MIN_CONFIDENCE:
        return LLMValidationResult(False, [], "low_confidence", confidence=confidence, decision=decision)

    raw_segments = parsed.get("segments")
    if not isinstance(raw_segments, list) or not (MIN_SEGMENTS <= len(raw_segments) <= MAX_SEGMENTS):
        return LLMValidationResult(False, [], "invalid_segment_count", confidence=confidence, decision=decision)

    block_map = {block.id: block for block in source_blocks}
    source_text = "\n".join(block.text for block in source_blocks)
    rule_segments = [str(item or "").strip() for item in rule_output.get("request_segments") or [] if str(item or "").strip()]
    if _looks_like_phone_dialogue(source_text) and len(raw_segments) >= 4:
        return LLMValidationResult(False, [], "phone_dialogue_over_split", confidence=confidence, decision=decision)
    if _looks_like_long_legal_or_proposal(source_text) and len(raw_segments) >= 4:
        return LLMValidationResult(False, [], "long_legal_or_proposal_over_split", confidence=confidence, decision=decision)
    if rule_segments and len(raw_segments) > max(len(rule_segments) + 2, len(rule_segments) * 2):
        return LLMValidationResult(False, [], "segment_count_expanded_too_much", confidence=confidence, decision=decision)

    accepted: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            return LLMValidationResult(False, [], f"invalid_segment_item:{index}", confidence=confidence, decision=decision)
        text = _normalize_text(item.get("text"))
        evidence_ids = item.get("evidence_ids")
        if not text or not isinstance(evidence_ids, list) or not evidence_ids:
            return LLMValidationResult(False, [], f"missing_text_or_evidence_ids:{index}", confidence=confidence, decision=decision)
        if len(text) > MAX_LLM_SEGMENT_CHARS:
            return LLMValidationResult(False, [], f"segment_too_long:{index}", confidence=confidence, decision=decision)
        evidence_blocks: list[SourceBlock] = []
        for raw_id in evidence_ids:
            evidence_id = str(raw_id or "").strip()
            if evidence_id not in block_map:
                return LLMValidationResult(
                    False,
                    [],
                    f"unknown_evidence_id:{index}",
                    hallucination_suspected=True,
                    confidence=confidence,
                    decision=decision,
                )
            evidence_blocks.append(block_map[evidence_id])
        evidence_text = " ".join(block.text for block in evidence_blocks)
        if _is_invalid_segment(text) or _is_invalid_segment(evidence_text):
            return LLMValidationResult(False, [], f"low_value_or_admin_segment:{index}", confidence=confidence, decision=decision)
        if not _REQUEST_CUE_RE.search(text) and not _REQUEST_CUE_RE.search(evidence_text):
            return LLMValidationResult(False, [], f"weak_request_signal:{index}", confidence=confidence, decision=decision)
        if not _segment_supported_by_evidence(text, evidence_text):
            return LLMValidationResult(
                False,
                [],
                f"segment_not_supported_by_evidence:{index}",
                hallucination_suspected=True,
                confidence=confidence,
                decision=decision,
            )
        key = _compact(text)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(text)

    accepted = _dedupe_near_duplicate_texts(accepted)
    if not accepted:
        return LLMValidationResult(False, [], "empty_after_dedup", confidence=confidence, decision=decision)
    return LLMValidationResult(True, accepted, None, confidence=confidence, decision=decision)


def _evaluate_assist_gate(
    *,
    policy: AssistPolicy,
    validation: LLMValidationResult,
    rule_output: dict,
    fallback_reasons: list[str],
    source_text: str,
    prompt_style: PromptStyle,
    raw_response: str,
) -> AssistGateResult:
    """assist 정책별로 LLM 결과의 실제 교체 가능 여부를 판단한다."""
    if policy == "none":
        return AssistGateResult("shadow_only", "policy_none", [], 0)
    if policy == "v2_strict":
        return evaluate_assist_limited_v2_strict_gate(
            validation=validation,
            rule_output=rule_output,
            fallback_reasons=fallback_reasons,
            source_text=source_text,
            prompt_style=prompt_style,
            raw_response=raw_response,
        )
    return AssistGateResult("shadow_only", "unknown_policy", [], 0)


def evaluate_assist_limited_v2_strict_gate(
    *,
    validation: LLMValidationResult,
    rule_output: dict,
    fallback_reasons: list[str],
    source_text: str,
    prompt_style: PromptStyle,
    raw_response: str,
) -> AssistGateResult:
    """조건 B + strict replay 기준을 runtime에서 관측 가능한 신호로 재현한다."""
    risk_tags = _strict_assist_risk_tags(source_text, rule_output, fallback_reasons)
    evidence_reference_count = _block_evidence_reference_count(raw_response)

    if not validation.accepted:
        return AssistGateResult("reject", validation.reject_reason or "validation_rejected", risk_tags, evidence_reference_count)
    if prompt_style != "block":
        return AssistGateResult("review_required", "non_block_prompt_style", risk_tags, evidence_reference_count)
    if not ASSIST_TRIGGER_ALLOWLIST.intersection(fallback_reasons):
        return AssistGateResult("shadow_only", "not_list_trigger_candidate", risk_tags, evidence_reference_count)

    excluded_risks = sorted(set(risk_tags).intersection(STRICT_ASSIST_EXCLUDED_RISK_TAGS))
    if excluded_risks:
        return AssistGateResult("review_required", f"excluded_risk_tag:{','.join(excluded_risks)}", risk_tags, evidence_reference_count)

    excluded_reasons = sorted(set(fallback_reasons).intersection(STRICT_ASSIST_EXCLUDED_REASONS))
    if excluded_reasons:
        return AssistGateResult(
            "review_required",
            f"excluded_fallback_reason:{','.join(excluded_reasons)}",
            risk_tags,
            evidence_reference_count,
        )

    if _looks_like_strict_assist_dialogue(source_text):
        return AssistGateResult("review_required", "dialogue_like_text", risk_tags, evidence_reference_count)

    segment_count = len(validation.segments)
    if not (1 <= segment_count <= 3):
        return AssistGateResult("review_required", "invalid_llm_segment_count", risk_tags, evidence_reference_count)

    rule_segments = [str(item or "").strip() for item in rule_output.get("request_segments") or [] if str(item or "").strip()]
    if rule_segments and len(rule_segments) <= 4 and segment_count < len(rule_segments):
        return AssistGateResult("review_required", "llm_under_rule_segments", risk_tags, evidence_reference_count)

    if evidence_reference_count > segment_count:
        return AssistGateResult("review_required", "too_many_evidence_blocks", risk_tags, evidence_reference_count)

    if any(len(segment) > 70 for segment in validation.segments):
        return AssistGateResult("review_required", "segment_too_long_for_assist", risk_tags, evidence_reference_count)

    if any(not _has_strict_assist_request_cue(segment) for segment in validation.segments):
        return AssistGateResult("review_required", "weak_request_cue", risk_tags, evidence_reference_count)

    if any(_has_multi_request_single_segment(segment) for segment in validation.segments):
        return AssistGateResult("review_required", "multi_request_single_segment", risk_tags, evidence_reference_count)

    for segment in validation.segments:
        quality_issue = assess_segment_actionability(segment)
        if quality_issue:
            return AssistGateResult("review_required", quality_issue, risk_tags, evidence_reference_count)

    return AssistGateResult("allow_assist", None, risk_tags, evidence_reference_count)


def _record_assist_gate_trace(trace: dict, gate: AssistGateResult) -> None:
    trace["llm_assist_gate"] = gate.decision
    trace["llm_assist_gate_reason"] = gate.reason
    trace["llm_assist_gate_rejected_reason"] = None if gate.decision == "allow_assist" else gate.reason
    trace["llm_assist_gate_risk_tags"] = ",".join(gate.risk_tags) if gate.risk_tags else None
    trace["llm_assist_gate_evidence_count"] = gate.evidence_reference_count


def assess_segment_actionability(segment: str) -> str | None:
    """BE3 action-item으로 쓰기 약한 LLM segment를 보수적으로 걸러낸다."""
    text = _normalize_text(segment)
    compact = _compact(text)
    generic_compacts = {
        "이용방법문의",
        "신청방법문의",
        "지원방법문의",
        "관련질의",
        "관련문의",
        "확인요청",
        "조치요청",
        "개선요청",
        "안전고려요청",
    }
    if compact in generic_compacts:
        return "generic_weak_actionability"
    if re.search(r"(?:필요성|고려사항|검토사항)[.!?。]*$", text) and not re.search(r"(?:문의|요청|알려|궁금|가능|여부)", text):
        return "method_or_condition_only_segment"
    if len(compact) <= 8 and not re.search(r"(?:가능|여부|\?)", text):
        return "segment_too_short_for_action"
    return None


def _record_pre_gate_trace(trace: dict, pre_gate: LLMPreGateResult) -> None:
    trace["llm_pre_gate"] = pre_gate.decision
    trace["llm_pre_gate_reason"] = pre_gate.reason
    trace["llm_pre_gate_rejected_reason"] = None if pre_gate.decision == "allow_call" else pre_gate.reason
    trace["llm_pre_gate_risk_tags"] = ",".join(pre_gate.risk_tags) if pre_gate.risk_tags else None


def _strict_assist_risk_tags(source_text: str, rule_output: dict, fallback_reasons: list[str]) -> list[str]:
    tags: list[str] = []
    if ASSIST_TRIGGER_ALLOWLIST.intersection(fallback_reasons):
        tags.append("numbered_or_heading_list")
    if _looks_like_strict_assist_dialogue(source_text):
        tags.append("phone_dialogue")
    if len(str(source_text or "")) > 1000 and _looks_like_long_legal_or_proposal(source_text):
        tags.append("long_legal_or_policy")
    trace = rule_output.get("complexity_trace") if isinstance(rule_output.get("complexity_trace"), dict) else {}
    rule_segments = [str(item or "").strip() for item in rule_output.get("request_segments") or [] if str(item or "").strip()]
    if trace.get("segment_limit_applied") or len(rule_segments) >= MAX_SEGMENTS:
        tags.append("segment_limit_case")
    if "weak_request_signal" in fallback_reasons:
        tags.append("weak_request_signal")
    return list(dict.fromkeys(tags))


def _block_evidence_reference_count(raw_response: str) -> int:
    parsed = parse_llm_json_response(raw_response)
    if not isinstance(parsed, dict):
        return 0
    segments = parsed.get("segments")
    if not isinstance(segments, list):
        return 0
    count = 0
    for item in segments:
        if not isinstance(item, dict):
            continue
        evidence_ids = item.get("evidence_ids")
        if isinstance(evidence_ids, list):
            count += len([value for value in evidence_ids if str(value or "").strip()])
    return count


def _looks_like_strict_assist_dialogue(source_text: str) -> bool:
    text = str(source_text or "")[:900]
    return any(marker in text for marker in STRICT_ASSIST_DIALOGUE_MARKERS)


def _has_strict_assist_request_cue(segment: str) -> bool:
    text = str(segment or "")
    return any(cue in text for cue in STRICT_ASSIST_REQUEST_CUES) or bool(_REQUEST_CUE_RE.search(text))


def _has_multi_request_single_segment(segment: str) -> bool:
    text = str(segment or "")
    cue_count = sum(1 for cue in STRICT_ASSIST_REQUEST_CUES if cue in text)
    has_sentence_join = ". " in text or "다. " in text or "요. " in text
    return cue_count >= 2 and has_sentence_join


def _call_llm(*, prompt: str, llm_call: LLMCall | None, num_predict: int | None = None) -> str | None:
    if callable(llm_call):
        try:
            return str(llm_call(prompt) or "")
        except Exception:
            return None
    if settings.REQUEST_SEGMENT_LLM_PROVIDER != "ollama":
        return None

    payload = {
        "model": settings.REQUEST_SEGMENT_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": num_predict or settings.REQUEST_SEGMENT_LLM_NUM_PREDICT, "num_ctx": 4096},
    }
    url = f"{settings.REQUEST_SEGMENT_LLM_BASE_URL.rstrip('/')}/api/generate"
    try:
        with httpx.Client(timeout=settings.REQUEST_SEGMENT_LLM_TIMEOUT) as client:
            response = client.post(url, json=payload)
            if response.status_code != 200:
                return None
            return str(response.json().get("response") or "")
    except (httpx.HTTPError, ValueError):
        return None


def _provider_unavailable_reason() -> str:
    if settings.REQUEST_SEGMENT_LLM_PROVIDER != "ollama":
        return "llm_provider_unavailable"
    return "llm_call_failed"


def parse_llm_json_response(raw: str) -> dict[str, Any] | None:
    """LLM 응답에서 JSON object만 보수적으로 추출한다."""
    text = str(raw or "").strip()
    if not text:
        return None
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    return parse_llm_json_response(raw)


def _source_text(*, text: str, title: str | None, question: str | None) -> str:
    parts = [str(part or "").strip() for part in (title, question) if str(part or "").strip()]
    if parts:
        return "\n".join(parts)
    return str(text or "").strip()


def _split_source_blocks(source_text: str) -> list[str]:
    chunks: list[str] = []
    for raw_line in str(source_text or "").splitlines():
        line = _normalize_text(raw_line)
        if not line:
            continue
        if len(line) <= MAX_SOURCE_BLOCK_CHARS:
            chunks.append(line)
            continue
        for part in _BLOCK_SPLIT_RE.split(line):
            cleaned = _normalize_text(part)
            if cleaned:
                chunks.append(cleaned)
    if chunks:
        return chunks
    return [_normalize_text(part) for part in _BLOCK_SPLIT_RE.split(str(source_text or "")) if _normalize_text(part)]


def _score_source_block(text: str, index: int) -> int:
    score = 0
    if _NUMBERED_ITEM_RE.search(text):
        score += 6
    if _REQUEST_CUE_RE.search(text):
        score += 5
    if "?" in text or "？" in text:
        score += 4
    if _HEADING_RE.search(text):
        score += 4
    if index <= 2:
        score += 3
    elif index <= 8:
        score += 1
    if _LOW_VALUE_RE.match(text):
        score -= 6
    if _ADMIN_ACTION_RE.search(text):
        score -= 5
    if _LEGAL_REFERENCE_RE.search(text) and not _REQUEST_CUE_RE.search(text):
        score -= 3
    if len(text) > 260 and not _REQUEST_CUE_RE.search(text):
        score -= 2
    return score


def _strong_request_candidate_count(text: str) -> int:
    chunks = re.split(r"[.!?。！？\n]+|(?<=요)\s+|(?<=다)\s+", str(text or ""))
    candidates: list[str] = []
    for chunk in chunks:
        cleaned = _normalize_text(chunk)
        if len(cleaned) >= 8 and _REQUEST_CUE_RE.search(cleaned):
            candidates.append(cleaned)
    return len(_dedupe_near_duplicate_texts(candidates))


def _looks_like_phone_dialogue(text: str) -> bool:
    cleaned = str(text or "")
    filler_count = sum(cleaned.count(token) for token in ("네", "예", "아", "어", "음", "잠시만", "여보세요"))
    question_count = cleaned.count("?") + cleaned.count("？")
    return filler_count >= 5 and question_count >= 2


def _looks_like_long_legal_or_proposal(text: str) -> bool:
    cleaned = str(text or "")
    legal_count = len(_LEGAL_REFERENCE_RE.findall(cleaned))
    numbered_count = len(_NUMBERED_ITEM_RE.findall(cleaned))
    proposal_like = any(token in cleaned for token in ("건의", "제안", "청원", "검토 요청"))
    return len(cleaned) > 700 and (legal_count >= 4 or numbered_count >= 4 or proposal_like)


def _is_invalid_segment(text: str) -> bool:
    cleaned = _normalize_text(text)
    return bool(
        not cleaned
        or _LOW_VALUE_RE.match(cleaned)
        or _ADMIN_ACTION_RE.search(cleaned)
        or _WEAK_PHONE_RE.match(cleaned)
    )


def _normalize_mode(mode: str) -> HybridMode:
    normalized = str(mode or "off").strip().lower()
    if normalized in {"shadow", "assist"}:
        return normalized  # type: ignore[return-value]
    return "off"


def _normalize_prompt_style(value: str) -> PromptStyle:
    normalized = str(value or "text").strip().lower()
    if normalized == "block":
        return "block"
    return "text"


def _normalize_assist_policy(value: str) -> AssistPolicy:
    normalized = str(value or "none").strip().lower()
    if normalized == "v2_strict":
        return "v2_strict"
    return "none"


def _normalize_decision(value: Any) -> str:
    decision = str(value or "").strip().lower()
    if decision in {"keep_rule", "replace", "abstain"}:
        return decision
    return ""


def _assist_replace_allowed(reasons: list[str]) -> bool:
    return bool(ASSIST_TRIGGER_ALLOWLIST.intersection(reasons))


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _segment_supported_by_evidence(segment: str, evidence_text: str) -> bool:
    segment_tokens = _support_tokens(segment)
    if not segment_tokens:
        return False

    evidence_compact = _compact(evidence_text).lower()
    evidence_tokens = _support_tokens(evidence_text)
    evidence_token_set = set(evidence_tokens)

    numeric_tokens = [token for token in segment_tokens if any(char.isdigit() for char in token)]
    if any(token not in evidence_compact for token in numeric_tokens):
        return False

    supported = 0
    for token in segment_tokens:
        if (
            token in evidence_compact
            or token in evidence_token_set
            or any(token in evidence_token or evidence_token in token for evidence_token in evidence_tokens if len(evidence_token) >= 3)
        ):
            supported += 1

    required = 1 if len(segment_tokens) <= 2 else 2
    return supported >= required and supported / max(len(segment_tokens), 1) >= 0.4


def _support_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in _SUPPORT_TOKEN_RE.findall(str(value or "").lower()):
        token = raw_token.strip()
        if len(token) < 2 or token in _SUPPORT_STOPWORDS:
            continue
        if token.endswith(("은", "는", "이", "가", "을", "를", "의", "에", "로", "과", "와", "도")) and len(token) > 2:
            token = token[:-1]
        if token and token not in _SUPPORT_STOPWORDS:
            tokens.append(token)
    return list(dict.fromkeys(tokens))


def _dedupe_near_duplicate_texts(values: list[str]) -> list[str]:
    """제목/본문 반복처럼 한쪽이 다른 쪽에 포함되는 후보를 보수적으로 병합한다."""
    unique: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        key = _compact(text)
        replaced = False
        skip = False
        for index, existing in enumerate(unique):
            existing_key = _compact(existing)
            if key == existing_key:
                skip = True
                break
            if key in existing_key or existing_key in key:
                if len(text) > len(existing):
                    unique[index] = text
                replaced = True
                break
        if not skip and not replaced:
            unique.append(text)
    return unique


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

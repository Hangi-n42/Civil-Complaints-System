from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ComplexityLevel = Literal["low", "medium", "high"]

# Score -> level thresholds are split as constants for stable tuning.
COMPLEXITY_LEVEL_MEDIUM_THRESHOLD = 0.45
COMPLEXITY_LEVEL_HIGH_THRESHOLD = 0.75

_CONSTRAINT_TOKENS = (
    "기한",
    "예산",
    "규정",
    "절차",
    "우선순위",
    "근거",
    "조건",
)
_POLICY_TOKENS = ("법", "법령", "시행령", "조례", "규칙", "고시")
_ENTITY_TOKENS = (
    "기관",
    "부서",
    "주민",
    "사업자",
    "지자체",
    "담당자",
    "시설",
    "도로",
)
_INTENT_SPLIT_TOKENS = (" 및 ", " 그리고 ", " 또는 ", ",", ";", "/")


@dataclass(frozen=True)
class ComplexityAnalysis:
    complexity_score: float
    complexity_level: ComplexityLevel
    intent_count: int
    constraint_count: int
    entity_diversity: int
    policy_reference_count: int
    complexity_trace: dict


def build_analyzer_output(text: str, topic_type: str = "general") -> dict:
    analysis = _DEFAULT_ANALYZER.analyze(text=text, topic_type=topic_type)
    cleaned = str(text or "").strip()
    request_segments = _build_request_segments(cleaned)

    return {
        "topic_type": analysis.complexity_trace.get("topic_type", _normalize_topic_type(topic_type)),
        "complexity_level": analysis.complexity_level,
        "complexity_score": analysis.complexity_score,
        "intent_count": analysis.intent_count,
        "constraint_count": analysis.constraint_count,
        "entity_diversity": analysis.entity_diversity,
        "policy_reference_count": analysis.policy_reference_count,
        "cross_sentence_dependency": _detect_cross_sentence_dependency(cleaned),
        "complexity_trace": analysis.complexity_trace,
        "request_segments": request_segments,
        "length_bucket": _build_length_bucket(len(cleaned)),
        "is_multi": len(request_segments) > 1,
    }


class ComplexityAnalyzer:
    def analyze(self, text: str, topic_type: str) -> ComplexityAnalysis:
        cleaned = str(text or "").strip()
        normalized_topic = str(topic_type or "general").strip().lower() or "general"

        if not cleaned:
            return ComplexityAnalysis(
                complexity_score=0.0,
                complexity_level="low",
                intent_count=0,
                constraint_count=0,
                entity_diversity=0,
                policy_reference_count=0,
                complexity_trace={
                    "topic_type": normalized_topic,
                    "text_length": 0,
                    "reason": "empty_text",
                },
            )

        text_length = len(cleaned)
        intent_count = _count_intents(cleaned)
        constraint_count = _count_tokens(cleaned, _CONSTRAINT_TOKENS)
        entity_diversity = _count_entity_diversity(cleaned)
        policy_reference_count = _count_tokens(cleaned, _POLICY_TOKENS)
        cross_sentence_dependency = _detect_cross_sentence_dependency(cleaned)

        score = _build_score(
            text_length=text_length,
            intent_count=intent_count,
            constraint_count=constraint_count,
            entity_diversity=entity_diversity,
            policy_reference_count=policy_reference_count,
        )
        level = _score_to_level(score)

        return ComplexityAnalysis(
            complexity_score=score,
            complexity_level=level,
            intent_count=intent_count,
            constraint_count=constraint_count,
            entity_diversity=entity_diversity,
            policy_reference_count=policy_reference_count,
            complexity_trace={
                "topic_type": normalized_topic,
                "text_length": text_length,
                "intent_count": intent_count,
                "constraint_count": constraint_count,
                "entity_diversity": entity_diversity,
                "policy_reference_count": policy_reference_count,
                "cross_sentence_dependency": cross_sentence_dependency,
                "weights": {
                    "length": min(0.25, text_length / 400.0),
                    "intent": min(0.20, max(0, intent_count - 1) * 0.08),
                    "constraint": min(0.20, constraint_count * 0.07),
                    "entity": min(0.15, entity_diversity * 0.05),
                    "policy": min(0.20, policy_reference_count * 0.10),
                },
            },
        )


def analyze(text: str, topic_type: str) -> ComplexityAnalysis:
    return _DEFAULT_ANALYZER.analyze(text=text, topic_type=topic_type)


def _count_tokens(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token in text)


def _count_entity_diversity(text: str) -> int:
    return sum(1 for token in _ENTITY_TOKENS if token in text)


def _normalize_topic_type(topic_type: str) -> str:
    cleaned = str(topic_type or "").strip().lower()
    return cleaned or "general"


def _build_request_segments(text: str) -> list[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    segments = [cleaned]
    for token in _INTENT_SPLIT_TOKENS:
        next_segments: list[str] = []
        for segment in segments:
            next_segments.extend(segment.split(token))
        segments = next_segments

    normalized = [" ".join(segment.split()) for segment in segments if segment.strip()]
    return normalized if normalized else [cleaned]


def _detect_cross_sentence_dependency(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    return any(token in cleaned for token in ("또한", "한편", "다만", "그리고"))


def _build_length_bucket(text_length: int) -> Literal["short", "medium", "long"]:
    if text_length < 40:
        return "short"
    if text_length < 120:
        return "medium"
    return "long"


def _count_intents(text: str) -> int:
    parts = [text]
    for token in _INTENT_SPLIT_TOKENS:
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(part.split(token))
        parts = next_parts
    return max(1, len([part.strip() for part in parts if part.strip()]))


def _build_score(
    *,
    text_length: int,
    intent_count: int,
    constraint_count: int,
    entity_diversity: int,
    policy_reference_count: int,
) -> float:
    score = (
        0.10
        + min(0.25, text_length / 400.0)
        + min(0.20, max(0, intent_count - 1) * 0.08)
        + min(0.20, constraint_count * 0.07)
        + min(0.15, entity_diversity * 0.05)
        + min(0.20, policy_reference_count * 0.10)
    )
    return max(0.0, min(1.0, round(score, 3)))


def _score_to_level(score: float) -> ComplexityLevel:
    if score >= COMPLEXITY_LEVEL_HIGH_THRESHOLD:
        return "high"
    if score >= COMPLEXITY_LEVEL_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


_DEFAULT_ANALYZER = ComplexityAnalyzer()

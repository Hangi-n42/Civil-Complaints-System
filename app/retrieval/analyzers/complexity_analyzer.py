from __future__ import annotations

import re
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

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|[\r\n]+")
_SEMANTIC_SPLIT_PATTERNS = (
    re.compile(r"\s*(?:그리고|또한|아울러|동시에)\s*"),
    re.compile(r"\s*,\s*"),
    re.compile(r"\s*;\s*"),
    re.compile(r"\s*/\s*"),
    re.compile(r"\s+및\s+"),
    re.compile(r"(?<=(?:요청|문의|신고|건의))(?:과|와)\s+"),
)
_ADMIN_ACTION_RE = re.compile(
    r"(?:접수|전달|배정|검토|확인|조치|처리|안내|답변).{0,16}"
    r"(?:했습니다|하겠습니다|드립니다|드렸습니다|예정입니다|예정|완료|되었습니다)"
)
_REQUEST_INTENT_PATTERNS = (
    re.compile(
        r"(?:요청|문의|질의|신고|건의)"
        r"(?:합니다|드립니다|드려요|드리고|하고|하니|입니다|$)"
    ),
    re.compile(
        r"(?:부탁드립니다|바랍니다|해\s*주세요|해\s*주십시오|해\s*주시기 바랍니다|해\s*주시고)"
    ),
    re.compile(
        r"(?:조치|점검|보수|수리|설치|교체|제거|단속|개선|확인|검토|처리|조사|복구|시정|안내|답변|공개|제공|연장|확대|감면|지원)"
        r".{0,24}(?:부탁|바랍니다|요청|해\s*주세요|해\s*주십시오|해\s*주시|필요합니다)"
    ),
    re.compile(r"(?:알려\s*주세요|알려\s*주시|답변.{0,12}(?:주세요|바랍니다|부탁)|궁금합니다)"),
    re.compile(
        r"(?:언제|어떻게|어디(?:서|에)?|무엇|가능한지|여부|일정|절차|방법)"
        r".{0,32}(?:\?|인가요|나요|습니까|문의|궁금|알려)"
    ),
)


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
    intent_count = len(request_segments) if request_segments else 0
    complexity_trace = dict(analysis.complexity_trace)
    complexity_trace["intent_count"] = intent_count

    return {
        "topic_type": analysis.complexity_trace.get("topic_type", _normalize_topic_type(topic_type)),
        "complexity_level": analysis.complexity_level,
        "complexity_score": analysis.complexity_score,
        "intent_count": intent_count,
        "constraint_count": analysis.constraint_count,
        "entity_diversity": analysis.entity_diversity,
        "policy_reference_count": analysis.policy_reference_count,
        "cross_sentence_dependency": _detect_cross_sentence_dependency(cleaned),
        "complexity_trace": complexity_trace,
        "request_segments": request_segments,
        "length_bucket": _build_length_bucket(len(cleaned)),
        "is_multi": len(request_segments) >= 2,
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

    request_segments: list[str] = []
    for sentence in _split_sentences(cleaned):
        for segment in _split_semantic_request_units(sentence):
            if _has_request_intent(segment):
                request_segments.append(_normalize_segment(segment))

    deduped = _dedupe_request_segments(request_segments)
    if deduped:
        return deduped

    fallback = _normalize_segment(cleaned)
    return [fallback] if fallback else []


def _split_sentences(text: str) -> list[str]:
    return [
        _normalize_segment(part)
        for part in _SENTENCE_SPLIT_RE.split(text)
        if part.strip()
    ]


def _split_semantic_request_units(segment: str) -> list[str]:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return []

    for splitter in _SEMANTIC_SPLIT_PATTERNS:
        parts = [_normalize_segment(part) for part in splitter.split(cleaned) if part.strip()]
        if len(parts) >= 2 and all(_has_request_intent(part) for part in parts):
            split_parts: list[str] = []
            for part in parts:
                split_parts.extend(_split_semantic_request_units(part))
            return split_parts
    return [cleaned]


def _has_request_intent(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return False

    explicit_request_signal = any(
        token in cleaned
        for token in (
            "요청",
            "문의",
            "질의",
            "신고",
            "건의",
            "부탁",
            "바랍니다",
            "해주세요",
            "해 주세요",
            "궁금",
            "?",
        )
    )
    if _ADMIN_ACTION_RE.search(cleaned) and not explicit_request_signal:
        return False

    return any(pattern.search(cleaned) for pattern in _REQUEST_INTENT_PATTERNS)


def _dedupe_request_segments(segments: list[str]) -> list[str]:
    normalized = [
        _normalize_segment(segment)
        for segment in segments
        if _normalize_segment(segment)
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for segment in normalized:
        key = _segment_key(segment)
        if key in seen:
            continue
        seen.add(key)
        unique.append(segment)

    deduped: list[str] = []
    keys = [_segment_key(segment) for segment in unique]
    for index, segment in enumerate(unique):
        key = keys[index]
        if any(
            index != other_index and key in other_key and len(key) < len(other_key)
            for other_index, other_key in enumerate(keys)
        ):
            continue
        deduped.append(segment)
    return deduped


def _normalize_segment(segment: str) -> str:
    return " ".join(str(segment or "").split())


def _segment_key(segment: str) -> str:
    return re.sub(r"[\s.!?。！？,;:/]+", "", segment)


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
    segments = _build_request_segments(text)
    return len(segments) if segments else 0


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

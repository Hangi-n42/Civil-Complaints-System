from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Literal

ComplexityLevel = Literal["low", "medium", "high"]

# Score -> level thresholds are split as constants for stable tuning.
COMPLEXITY_LEVEL_MEDIUM_THRESHOLD = 0.45
COMPLEXITY_LEVEL_HIGH_THRESHOLD = 0.75
MAX_REQUEST_SEGMENTS = 4
_KSS_SPLITTER_UNSET = object()
_KSS_SENTENCE_SPLITTER: Callable[..., object] | None | object = _KSS_SPLITTER_UNSET

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
_REQUEST_ACTION_TOKENS = (
    "조치",
    "점검",
    "보수",
    "수리",
    "설치",
    "교체",
    "제거",
    "단속",
    "개선",
    "확인",
    "검토",
    "처리",
    "조사",
    "복구",
    "시정",
    "안내",
    "답변",
    "공개",
    "제공",
    "연장",
    "확대",
    "감면",
    "지원",
)
_REQUEST_OBJECT_TOKENS = (
    "도로",
    "보도",
    "인도",
    "포트홀",
    "불법주정차",
    "주정차",
    "주차",
    "가로등",
    "보안등",
    "공원",
    "하천",
    "하수",
    "악취",
    "쓰레기",
    "폐기물",
    "버스",
    "정류장",
    "노선",
    "어린이집",
    "장애인",
    "임대주택",
    "공동주택",
)
_SHARED_REQUEST_PREDICATE_RE = re.compile(
    r"^(?P<body>.+?)(?:을|를)?\s*"
    r"(?P<predicate>(?:요청|문의|질의|신고|건의)(?:합니다|드립니다|드려요|드리고|하고|하니|입니다)?"
    r"|(?:해\s*주세요|해\s*주십시오|바랍니다))(?P<suffix>[.!?。！？]*)$"
)
_SHARED_REQUEST_SPLIT_RE = re.compile(r"\s*(?:그리고|및|과|와)\s*")
_COMPACT_REQUEST_LIST_SPLIT_RE = re.compile(r"\s*,\s*")
_BACKGROUND_GUARD_TOKENS = (
    "때문",
    "위험",
    "불편",
    "피해",
    "파손",
    "고장",
    "발생",
    "심합니다",
    "쌓이고",
    "꺼져",
    "넘어질",
)
_BACKGROUND_ONLY_RE = re.compile(
    r"(?:불편|위험|피해|문제|파손|고장|막히|흔들리|어렵|힘듭|많습니다|있습니다|발생)"
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


@dataclass(frozen=True)
class RequestSegmentAnalysis:
    segments: list[str]
    sentence_splitter: str
    sentence_count: int
    candidate_count: int
    dropped_background_count: int
    dropped_admin_action_count: int
    shared_predicate_split_count: int
    fallback_used: bool
    truncated: bool

    def trace(self) -> dict:
        return {
            "segment_count": len(self.segments),
            "sentence_splitter": self.sentence_splitter,
            "sentence_count": self.sentence_count,
            "segment_candidate_count": self.candidate_count,
            "dropped_background_count": self.dropped_background_count,
            "dropped_admin_action_count": self.dropped_admin_action_count,
            "shared_predicate_split_count": self.shared_predicate_split_count,
            "fallback_segment_used": self.fallback_used,
            "segment_limit": MAX_REQUEST_SEGMENTS,
            "segment_limit_applied": self.truncated,
        }


def build_analyzer_output(text: str, topic_type: str = "general") -> dict:
    analysis = _DEFAULT_ANALYZER.analyze(text=text, topic_type=topic_type)
    cleaned = str(text or "").strip()
    segment_analysis = _analyze_request_segments(cleaned)
    request_segments = segment_analysis.segments
    intent_count = len(request_segments) if request_segments else 0
    complexity_trace = dict(analysis.complexity_trace)
    complexity_trace["intent_count"] = intent_count
    complexity_trace.update(segment_analysis.trace())

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
    return _analyze_request_segments(text).segments


def _analyze_request_segments(text: str) -> RequestSegmentAnalysis:
    cleaned = str(text or "").strip()
    if not cleaned:
        return RequestSegmentAnalysis(
            segments=[],
            sentence_splitter="none",
            sentence_count=0,
            candidate_count=0,
            dropped_background_count=0,
            dropped_admin_action_count=0,
            shared_predicate_split_count=0,
            fallback_used=False,
            truncated=False,
        )

    request_segments: list[str] = []
    candidate_count = 0
    dropped_background_count = 0
    dropped_admin_action_count = 0
    shared_predicate_split_count = 0
    sentences, sentence_splitter = _split_sentences_with_source(cleaned)
    for sentence in sentences:
        for segment in _split_semantic_request_units(sentence):
            candidate_count += 1
            if _is_admin_action_without_request(segment):
                dropped_admin_action_count += 1
                continue
            if _is_background_only_segment(segment):
                dropped_background_count += 1
                continue
            shared_predicate_split_count += int(_is_shared_predicate_segment(segment))
            if _has_request_intent(segment):
                request_segments.append(_normalize_segment(segment))

    deduped = _dedupe_request_segments(request_segments)
    truncated = len(deduped) > MAX_REQUEST_SEGMENTS
    if truncated:
        deduped = deduped[:MAX_REQUEST_SEGMENTS]
    if deduped:
        return RequestSegmentAnalysis(
            segments=deduped,
            sentence_splitter=sentence_splitter,
            sentence_count=len(sentences),
            candidate_count=candidate_count,
            dropped_background_count=dropped_background_count,
            dropped_admin_action_count=dropped_admin_action_count,
            shared_predicate_split_count=shared_predicate_split_count,
            fallback_used=False,
            truncated=truncated,
        )

    fallback = _normalize_segment(cleaned)
    return RequestSegmentAnalysis(
        segments=[fallback] if fallback else [],
        sentence_splitter=sentence_splitter,
        sentence_count=len(sentences),
        candidate_count=candidate_count,
        dropped_background_count=dropped_background_count,
        dropped_admin_action_count=dropped_admin_action_count,
        shared_predicate_split_count=shared_predicate_split_count,
        fallback_used=bool(fallback),
        truncated=False,
    )


def _split_sentences(text: str) -> list[str]:
    sentences, _ = _split_sentences_with_source(text)
    return sentences


def _split_sentences_with_source(text: str) -> tuple[list[str], str]:
    if _should_use_kss_sentence_splitter():
        kss_sentences = _split_sentences_with_kss(text)
        if kss_sentences:
            return kss_sentences, "kss"

    regex_sentences = [
        _normalize_segment(part)
        for part in _SENTENCE_SPLIT_RE.split(text)
        if part.strip()
    ]
    return regex_sentences, "regex"


def _should_use_kss_sentence_splitter() -> bool:
    flag = os.getenv("COMPLEXITY_ANALYZER_USE_KSS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"} or "kss" in sys.modules


def _split_sentences_with_kss(text: str) -> list[str]:
    splitter = _load_kss_sentence_splitter()
    if splitter is None:
        return []
    try:
        raw_sentences = splitter(text, backend="fast", num_workers=1)
    except TypeError:
        raw_sentences = splitter(text)
    except Exception:
        return []

    if isinstance(raw_sentences, str):
        raw_sentences = [raw_sentences]
    return [
        _normalize_segment(part)
        for part in raw_sentences
        if str(part or "").strip()
    ]


def _load_kss_sentence_splitter() -> Callable[..., object] | None:
    global _KSS_SENTENCE_SPLITTER

    if _KSS_SENTENCE_SPLITTER is not _KSS_SPLITTER_UNSET:
        return _KSS_SENTENCE_SPLITTER  # type: ignore[return-value]

    # kss는 한국어 문장 경계만 담당하고, 요청 단위 판단은 의미 기반 규칙에서 수행한다.
    try:
        from kss import split_sentences  # type: ignore
    except Exception:
        _KSS_SENTENCE_SPLITTER = None
        return None
    _KSS_SENTENCE_SPLITTER = split_sentences
    return split_sentences


def _split_semantic_request_units(segment: str) -> list[str]:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return []

    shared_predicate_parts = _split_shared_predicate_request_units(cleaned)
    if len(shared_predicate_parts) >= 2:
        return shared_predicate_parts

    compact_list_parts = _split_compact_request_list_units(cleaned)
    if len(compact_list_parts) >= 2:
        return compact_list_parts

    for splitter in _SEMANTIC_SPLIT_PATTERNS:
        parts = [_normalize_segment(part) for part in splitter.split(cleaned) if part.strip()]
        if len(parts) >= 2 and all(_has_request_intent(part) for part in parts):
            split_parts: list[str] = []
            for part in parts:
                split_parts.extend(_split_semantic_request_units(part))
            return split_parts
    return [cleaned]


def _split_shared_predicate_request_units(segment: str) -> list[str]:
    match = _SHARED_REQUEST_PREDICATE_RE.match(segment)
    if not match:
        return []

    body = _normalize_segment(match.group("body"))
    predicate = _normalize_segment(match.group("predicate"))
    suffix = match.group("suffix") or ""
    parts = [_normalize_segment(part) for part in _SHARED_REQUEST_SPLIT_RE.split(body) if part.strip()]
    if len(parts) < 2:
        return []
    if not all(_can_share_request_predicate(part) for part in parts):
        return []

    return [
        _normalize_segment(f"{part} {predicate}{suffix}")
        for part in parts
    ]


def _split_compact_request_list_units(segment: str) -> list[str]:
    match = _SHARED_REQUEST_PREDICATE_RE.match(segment)
    if not match:
        return []

    body = _normalize_segment(match.group("body"))
    predicate = _normalize_segment(match.group("predicate"))
    suffix = match.group("suffix") or ""
    if len(body) > 90 or any(token in body for token in _BACKGROUND_GUARD_TOKENS):
        return []

    parts = [_normalize_segment(part) for part in _COMPACT_REQUEST_LIST_SPLIT_RE.split(body) if part.strip()]
    if not 2 <= len(parts) <= MAX_REQUEST_SEGMENTS:
        return []
    if any(_has_explicit_request_signal(part) or len(part) < 3 for part in parts):
        return []

    return [
        _normalize_segment(f"{part} {predicate}{suffix}")
        for part in parts
    ]


def _can_share_request_predicate(part: str) -> bool:
    cleaned = _normalize_segment(part)
    if _has_explicit_request_signal(cleaned):
        return False
    return any(token in cleaned for token in _REQUEST_ACTION_TOKENS) and any(
        token in cleaned for token in _REQUEST_OBJECT_TOKENS
    )


def _has_request_intent(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return False

    if _is_admin_action_without_request(cleaned):
        return False

    return any(pattern.search(cleaned) for pattern in _REQUEST_INTENT_PATTERNS)


def _has_explicit_request_signal(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    return any(
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


def _is_admin_action_without_request(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    return bool(_ADMIN_ACTION_RE.search(cleaned) and not _has_explicit_request_signal(cleaned))


def _is_background_only_segment(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned or _has_explicit_request_signal(cleaned):
        return False
    return bool(_BACKGROUND_ONLY_RE.search(cleaned) and not any(token in cleaned for token in _REQUEST_ACTION_TOKENS))


def _is_shared_predicate_segment(segment: str) -> bool:
    return bool(_SHARED_REQUEST_PREDICATE_RE.match(_normalize_segment(segment)))


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

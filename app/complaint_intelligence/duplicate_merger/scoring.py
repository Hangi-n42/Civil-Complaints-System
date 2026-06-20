"""중복 민원 후보 점수 산정."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.complaint_intelligence.embedding import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    cosine_similarity,
)
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.duplicate_merger.schemas import (
    DuplicateEvidence,
    DuplicateLocationState,
    DuplicateRequestType,
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")
_REDACTION_PLACEHOLDER_RE = re.compile(r"\[REDACTED:[^\]]*\]")
_UNKNOWN = {"", "미상", "unknown", "UNKNOWN", "N/A", "None", "지역미상"}


@dataclass(frozen=True)
class DuplicateScoreResult:
    """두 민원 간 중복 점수와 설명 신호."""

    case_ids: tuple[str, str]
    score: float
    breakdown: dict[str, float]
    location_state: DuplicateLocationState
    request_types: dict[str, DuplicateRequestType]
    time_delta_hours: float
    evidence: list[DuplicateEvidence]


def score_duplicate_pair(
    left: ComplaintIntelligenceEvent,
    right: ComplaintIntelligenceEvent,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> DuplicateScoreResult:
    """PRD 가중치를 적용해 pair 단위 중복 점수를 계산한다."""

    provider = embedding_provider or FakeEmbeddingProvider()
    left_text = analysis_text(left)
    right_text = analysis_text(right)
    vectors = provider.embed([left_text, right_text])
    semantic_similarity = cosine_similarity(vectors[0], vectors[1])

    location_state = classify_location_state(left, right)
    location_score = _location_score(location_state)
    entity_overlap = _entity_overlap(left, right)
    left_request = classify_request_type(left)
    right_request = classify_request_type(right)
    request_type_match = 1.0 if left_request == right_request else 0.0
    responsible_unit_match = _responsible_unit_match(left, right)
    time_delta_hours = abs((_as_aware(left.received_at) - _as_aware(right.received_at)).total_seconds()) / 3600
    time_window_score = _time_window_score(time_delta_hours)
    request_segment_similarity = _request_segment_similarity(left, right)

    breakdown = {
        "semantic_similarity": round(semantic_similarity, 4),
        "location_score": round(location_score, 4),
        "entity_overlap": round(entity_overlap, 4),
        "request_type_match": round(request_type_match, 4),
        "responsible_unit_match": round(responsible_unit_match, 4),
        "time_window_score": round(time_window_score, 4),
        "request_segment_similarity": round(request_segment_similarity, 4),
    }
    score = (
        0.30 * semantic_similarity
        + 0.20 * location_score
        + 0.15 * entity_overlap
        + 0.15 * request_type_match
        + 0.10 * responsible_unit_match
        + 0.05 * time_window_score
        + 0.05 * request_segment_similarity
    )
    evidence = [
        DuplicateEvidence(
            type="semantic_similarity",
            message="PII-safe 분석 텍스트 간 의미 유사도입니다.",
            affected_case_ids=[left.id, right.id],
            value=round(semantic_similarity, 4),
        ),
        DuplicateEvidence(
            type="location",
            message=f"장소 신호는 {location_state} 상태입니다.",
            affected_case_ids=[left.id, right.id],
            value=location_state,
        ),
        DuplicateEvidence(
            type="request_type",
            message=f"요청 유형은 {left.id}:{left_request}, {right.id}:{right_request}입니다.",
            affected_case_ids=[left.id, right.id],
            value=request_type_match,
        ),
        DuplicateEvidence(
            type="duplicate_score",
            message="중복 후보 정렬용 종합 점수입니다.",
            affected_case_ids=[left.id, right.id],
            value=round(score, 4),
            details=breakdown,
        ),
    ]
    return DuplicateScoreResult(
        case_ids=(left.id, right.id),
        score=round(max(0.0, min(1.0, score)), 4),
        breakdown=breakdown,
        location_state=location_state,
        request_types={left.id: left_request, right.id: right_request},
        time_delta_hours=round(time_delta_hours, 4),
        evidence=evidence,
    )


def analysis_text(event: ComplaintIntelligenceEvent) -> str:
    """원문보다 PII-safe 구조화/요약 신호를 우선해 분석 텍스트를 만든다."""

    parts: list[str] = []
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element and element.text:
            _append_scoring_part(parts, element.text)
    for item in getattr(event, "request_segments", []) or []:
        _append_scoring_part(parts, item)
    for item in getattr(event, "entity_texts", []) or []:
        _append_scoring_part(parts, item)
    if event.civil_category:
        _append_scoring_part(parts, event.civil_category)
    if event.final_department:
        _append_scoring_part(parts, event.final_department)
    elif event.predicted_department:
        _append_scoring_part(parts, event.predicted_department)
    if event.region:
        parts.append(event.region)
    if event.masked_text:
        _append_scoring_part(parts, event.masked_text)
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def classify_location_state(
    left: ComplaintIntelligenceEvent,
    right: ComplaintIntelligenceEvent,
) -> DuplicateLocationState:
    """지역/장소 신호를 exact, nearby, ambiguous, missing, conflict로 분류한다."""

    left_locations = _location_tokens(left)
    right_locations = _location_tokens(right)
    if not left_locations and not right_locations:
        return "missing"
    if not left_locations or not right_locations:
        return "ambiguous"
    if set(left_locations) & set(right_locations):
        return "exact"
    for left_item in left_locations:
        for right_item in right_locations:
            if left_item.startswith(right_item) or right_item.startswith(left_item):
                return "nearby"
            if len(left_item) >= 2 and len(right_item) >= 2 and left_item[:2] == right_item[:2]:
                return "nearby"
    return "conflict"


def classify_request_type(event: ComplaintIntelligenceEvent) -> DuplicateRequestType:
    """구조화 request와 요약 텍스트에서 최소 요청 유형을 분류한다."""

    text = analysis_text(event)
    if any(keyword in text for keyword in ("보상", "배상", "손해", "피해보상", "환불")):
        return "compensation"
    if any(keyword in text for keyword in ("단속", "과태료", "불법주정차", "처벌", "계도")):
        return "enforcement"
    if any(keyword in text for keyword in ("위험", "안전", "사고", "긴급", "침하", "싱크홀", "점검")):
        return "safety_action"
    if any(keyword in text for keyword in ("개선", "보수", "정비", "설치", "교체", "시설", "수리")):
        return "facility_improvement"
    if any(keyword in text for keyword in ("안내", "공지", "홍보", "방법", "절차")):
        return "guidance"
    if any(keyword in text for keyword in ("문의", "궁금", "확인", "가능", "어떻게")):
        return "inquiry"
    return "other"


def structural_evidence_count(event: ComplaintIntelligenceEvent) -> int:
    """병합 설명에 쓸 수 있는 구조화 신호 개수를 센다."""

    count = 0
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element and element.text.strip():
            count += 1
    if getattr(event, "request_segments", None):
        count += 1
    if getattr(event, "entity_texts", None):
        count += 1
    if event.region:
        count += 1
    if event.final_department or event.predicted_department or getattr(event, "responsible_unit", None):
        count += 1
    return count


def _location_tokens(event: ComplaintIntelligenceEvent) -> list[str]:
    tokens = []
    region = _normalize_location(event.region)
    if region:
        tokens.append(region)
    for value in getattr(event, "entity_texts", []) or []:
        normalized = _normalize_location(value)
        if normalized and _looks_like_location(str(value)):
            tokens.append(normalized)
    return _dedupe(tokens)


def _looks_like_location(value: str) -> bool:
    text = str(value or "")
    if not text.strip():
        return False
    return bool(
        any(marker in text for marker in ("동", "로", "길", "아파트", "공원", "초등학교", "교차로", "역", "구", "군", "시"))
    )


def _normalize_location(value: str | None) -> str | None:
    cleaned = re.sub(r"\s+", "", str(value or ""))
    cleaned = re.sub(r"[^A-Za-z0-9가-힣]", "", cleaned)
    if cleaned in _UNKNOWN:
        return None
    return cleaned or None


def _location_score(state: DuplicateLocationState) -> float:
    return {
        "exact": 1.0,
        "nearby": 0.75,
        "ambiguous": 0.35,
        "missing": 0.25,
        "conflict": 0.0,
    }[state]


def _entity_overlap(left: ComplaintIntelligenceEvent, right: ComplaintIntelligenceEvent) -> float:
    left_items = set(_normalize_tokens(getattr(left, "entity_texts", []) or []))
    right_items = set(_normalize_tokens(getattr(right, "entity_texts", []) or []))
    if not left_items or not right_items:
        return 0.0
    return len(left_items & right_items) / len(left_items | right_items)


def _responsible_unit_match(left: ComplaintIntelligenceEvent, right: ComplaintIntelligenceEvent) -> float:
    left_units = set(_department_tokens(left))
    right_units = set(_department_tokens(right))
    if not left_units or not right_units:
        return 0.5
    return 1.0 if left_units & right_units else 0.0


def _department_tokens(event: ComplaintIntelligenceEvent) -> list[str]:
    values = []
    values.extend(getattr(event, "responsible_unit", []) or [])
    values.extend([event.final_department, event.predicted_department])
    return _normalize_tokens(values)


def _time_window_score(hours: float) -> float:
    if hours <= 24:
        return 1.0
    if hours <= 72:
        return 0.8
    if hours <= 24 * 7:
        return 0.4
    return 0.0


def _request_segment_similarity(left: ComplaintIntelligenceEvent, right: ComplaintIntelligenceEvent) -> float:
    left_segments = getattr(left, "request_segments", []) or []
    right_segments = getattr(right, "request_segments", []) or []
    if not left_segments or not right_segments:
        return _jaccard_tokens(analysis_text(left), analysis_text(right))
    return max(_jaccard_tokens(a, b) for a in left_segments for b in right_segments)


def _jaccard_tokens(left: str, right: str) -> float:
    left = _strip_redaction_placeholders(left)
    right = _strip_redaction_placeholders(right)
    left_tokens = {token for token in _TOKEN_RE.findall(str(left or "").lower()) if len(token) >= 2}
    right_tokens = {token for token in _TOKEN_RE.findall(str(right or "").lower()) if len(token) >= 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalize_tokens(values: Iterable[str | None]) -> list[str]:
    return _dedupe(
        re.sub(r"\s+", "", _strip_redaction_placeholders(value)).strip()
        for value in values
        if str(value or "").strip()
    )


def _append_scoring_part(parts: list[str], value: str | None) -> None:
    cleaned = _strip_redaction_placeholders(value).strip()
    if cleaned:
        parts.append(cleaned)


def _strip_redaction_placeholders(value: str | None) -> str:
    return _REDACTION_PLACEHOLDER_RE.sub(" ", str(value or ""))


def _dedupe(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

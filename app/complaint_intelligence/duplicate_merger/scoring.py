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
_BROAD_REGION_SUFFIXES = ("특별자치도", "특별자치시", "광역시", "특별시", "자치구", "시", "군", "구", "도")
_DETAIL_LOCATION_MARKERS = (
    "아파트",
    "공원",
    "초등학교",
    "중학교",
    "고등학교",
    "대학교",
    "교차로",
    "사거리",
    "삼거리",
    "구청",
    "시청",
    "군청",
    "정류장",
    "터미널",
    "역",
    "시장",
    "센터",
    "주민센터",
    "도서관",
    "병원",
    "상가",
    "빌딩",
    "공사장",
    "놀이터",
    "도로",
    "보도",
    "하천",
    "배수로",
    "로",
    "길",
    "동",
)
_GENERIC_LOCATION_DETAILS = {"공사장", "도로", "보도", "하천", "배수로", "놀이터", "상가", "건물", "시설", "길", "로", "동"}
_ADDITIONAL_DETAIL_LOCATION_MARKERS = ("마을", "단지", "구역", "구간")
_NON_LOCATION_ENTITY_TERMS = {
    "가로등",
    "보안등",
    "배수로",
    "포트홀",
    "무단투기",
    "공사소음",
    "복지급여",
    "현장민원",
    "도로파손",
}


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

    left_region, left_details = _location_signals(left)
    right_region, right_details = _location_signals(right)
    if not any((left_region, left_details, right_region, right_details)):
        return "missing"
    if not (left_region or left_details) or not (right_region or right_details):
        return "ambiguous"

    if left_details and right_details:
        if set(left_details) & set(right_details):
            return "exact"
        if any(_is_conservative_nearby(left_item, right_item) for left_item in left_details for right_item in right_details):
            return "nearby"
        return "conflict"

    if left_region and right_region and left_region == right_region:
        return "ambiguous" if _is_broad_region(left_region) else "exact"
    if left_region and right_region and left_region != right_region:
        return "conflict"
    return "conflict"


def classify_request_type(event: ComplaintIntelligenceEvent) -> DuplicateRequestType:
    """구조화 request와 요약 텍스트에서 최소 요청 유형을 분류한다."""

    text = _request_intent_text(event)
    if any(keyword in text for keyword in ("보상", "배상", "손해", "피해보상", "환불", "수리비", "치료비", "금전", "변상")):
        return "compensation"
    if any(keyword in text for keyword in ("문의", "궁금", "확인", "가능", "어떻게", "언제", "여부", "조회")):
        return "inquiry"
    if any(keyword in text for keyword in ("안내", "공지", "홍보", "방법", "절차", "알림", "공고", "신청 방법", "처리 절차")):
        return "guidance"
    if any(keyword in text for keyword in ("단속", "과태료", "불법주정차", "처벌", "계도", "시정명령", "행정조치", "현장단속", "불법 적치", "불법주차")):
        return "enforcement"
    if any(keyword in text for keyword in ("위험", "안전", "사고", "긴급", "침하", "싱크홀", "점검", "붕괴", "균열", "낙상", "파손 위험")):
        return "safety_action"
    if any(keyword in text for keyword in ("개선", "보수", "정비", "설치", "교체", "시설", "수리", "확충", "신설", "보강", "복구", "배수로", "가로등")):
        return "facility_improvement"
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
    region, details = _location_signals(event)
    tokens = []
    if region:
        tokens.append(region)
    tokens.extend(details)
    return _dedupe(tokens)


def _location_signals(event: ComplaintIntelligenceEvent) -> tuple[str | None, list[str]]:
    region = _normalize_location(event.region)
    details = []
    for value in getattr(event, "entity_texts", []) or []:
        normalized = _normalize_location(value)
        if not normalized or normalized == region:
            continue
        if _looks_like_detail_location(str(value), normalized):
            details.append(normalized)
    return region, _dedupe(details)


def _looks_like_detail_location(value: str, normalized: str) -> bool:
    text = str(value or "")
    if not text.strip():
        return False
    if normalized in _GENERIC_LOCATION_DETAILS or normalized in _NON_LOCATION_ENTITY_TERMS:
        return False
    if _is_broad_region(normalized):
        return False
    markers = _DETAIL_LOCATION_MARKERS + _ADDITIONAL_DETAIL_LOCATION_MARKERS
    return bool(any(marker in text for marker in markers))


def _is_broad_region(value: str | None) -> bool:
    text = str(value or "")
    if len(text) <= 3 and text.endswith(("시", "군", "구", "도")):
        return True
    return text.endswith(_BROAD_REGION_SUFFIXES) and not any(marker in text for marker in ("아파트", "공원", "학교", "센터", "시장", "역"))


def _is_conservative_nearby(left: str, right: str) -> bool:
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) < 4 or _is_broad_region(shorter):
        return False
    return longer.startswith(shorter)


def _normalize_location(value: str | None) -> str | None:
    cleaned = re.sub(r"\s+", "", _strip_redaction_placeholders(value))
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


def _request_intent_text(event: ComplaintIntelligenceEvent) -> str:
    parts = []
    request = getattr(event.structured_elements, "request", None)
    if request and request.text:
        parts.append(request.text)
    parts.extend(getattr(event, "request_segments", []) or [])
    if parts:
        return " ".join(_strip_redaction_placeholders(part).strip() for part in parts if str(part or "").strip())
    return analysis_text(event)


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

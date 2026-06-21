"""confirmed 중복 그룹을 BE2/BE3 답변 생성 입력으로 변환한다."""

from __future__ import annotations

from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyMemberSummary,
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateReplyContext,
)


def build_duplicate_reply_context(
    record: DuplicateMergeRecord,
    payload: DraftReplyPayload,
) -> DuplicateReplyContext:
    """대표 민원 중심의 검색/생성 입력을 만들고 구성 민원 원문은 노출하지 않는다."""

    representative = payload.representative
    request_segments = _unique_texts(
        representative.request_segments
        + [segment for member in payload.members for segment in member.request_segments]
    )[:6]
    query = _build_query(representative, request_segments)
    risk_messages = [
        f"{flag.code}: {flag.message}"
        for flag in record.risk_flags
        if str(flag.message).strip()
    ]
    evidence_messages = [
        item.message
        for item in record.evidence
        if str(item.message).strip()
    ][:5]

    routing_hint = {
        "strategy_id": "topic_general_medium_duplicate_group_v1",
        "route_key": "general/medium",
        "top_k": 5,
        "snippet_max_chars": 1100,
        "chunk_policy": "balanced",
    }
    routing_trace = {
        "topic_type": "general",
        "complexity_level": "medium",
        "complexity_score": 0.68,
        "request_segments": request_segments,
        "complexity_trace": {
            "intent_count": max(1, len(request_segments)),
            "constraint_count": 2 + len(record.risk_flags),
            "entity_diversity": len(_unique_texts(representative.entity_texts)),
            "policy_reference_count": 0,
            "cross_sentence_dependency": len(payload.members) > 0,
        },
        "route_reason": "confirmed 중복 그룹의 대표 민원과 공통 요청을 기반으로 답변 생성을 준비했습니다.",
        "route_key": routing_hint["route_key"],
        "strategy_id": routing_hint["strategy_id"],
        "retrieval_policy": "general",
        "prompt_mode": "duplicate_group",
        "duplicate_group": {
            "merge_id": record.merge_id,
            "representative_complaint_id": record.representative_complaint_id,
            "member_complaint_ids": list(record.member_complaint_ids),
            "status": record.status,
            "risk_flags": risk_messages,
            "evidence": evidence_messages,
            "constraints": payload.common_reply_constraints + payload.prohibited_content_rules,
            "member_summaries": _member_summaries(payload.members),
        },
    }
    query_signals = {
        "entity_texts": _unique_texts(representative.entity_texts + [item for member in payload.members for item in member.entity_texts]),
        "key_terms": _unique_texts([payload.representative.civil_category or "", *request_segments, *evidence_messages])[:12],
        "responsible_units": _unique_texts(
            representative.responsible_unit
            + [unit for member in payload.members for unit in member.responsible_unit]
        ),
        "responsible_units_source": "duplicate_merge_confirmed_group",
    }
    return DuplicateReplyContext(
        merge_id=record.merge_id,
        query=query,
        routing_hint=routing_hint,
        routing_trace=routing_trace,
        query_signals=query_signals,
        request_segments=request_segments,
        excluded_case_ids=list(record.member_complaint_ids),
    )


def _build_query(representative: DraftReplyMemberSummary, request_segments: list[str]) -> str:
    structured = representative.structured_elements
    parts = [
        structured.get("observation", ""),
        structured.get("result", ""),
        structured.get("request", ""),
        structured.get("context", ""),
        " / ".join(request_segments),
    ]
    query = " ".join(part.strip() for part in parts if part and part.strip())
    return query or representative.pii_safe_summary or "중복 민원 대표 답변 초안 생성"


def _member_summaries(members: list[DraftReplyMemberSummary]) -> list[str]:
    return [
        f"{member.complaint_id}: {member.pii_safe_summary[:180]}"
        for member in members
        if member.pii_safe_summary.strip()
    ][:8]


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = " ".join(str(value or "").split())
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

"""confirmed 중복 그룹의 대표 답변 초안 입력 payload 생성."""

from __future__ import annotations

from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyMemberSummary,
    DraftReplyPayload,
    DuplicateMergeRecord,
)


SYSTEM_INSTRUCTION = (
    "병합 확정된 반복 민원 그룹에 대해 공통 적용 가능한 대표 답변 초안만 작성하세요. "
    "개별 민원인의 권리관계, 개인정보, 보상 판단, 자동 일괄 발송을 전제로 한 문구는 작성하지 마세요."
)

COMMON_REPLY_CONSTRAINTS = [
    "대표 민원의 PII-safe 구조화 결과를 중심으로 답변합니다.",
    "구성 민원 전체에 공통으로 적용 가능한 사실과 조치만 포함합니다.",
    "병합 근거와 risk_flags를 참고하되 risk를 숨기지 않습니다.",
    "담당자 검토와 개별 사안 확인이 필요하다는 조건을 유지합니다.",
]

PROHIBITED_CONTENT_RULES = [
    "개별 보상, 배상, 민원인별 권리관계 판단 금지",
    "법정 처리기한 변경 또는 자동 연장 암시 금지",
    "개인정보 또는 원문 전체 재노출 금지",
    "담당자 승인 없는 자동 발송 또는 일괄 처리 확정 표현 금지",
]


def build_draft_reply_payload(
    record: DuplicateMergeRecord,
    events_by_id: dict[str, ComplaintIntelligenceEvent],
) -> DraftReplyPayload:
    """confirmed 그룹에 대해 BE3 전달용 PII-safe payload를 만든다."""

    representative_event = events_by_id[record.representative_complaint_id]
    members = [
        _member_summary(events_by_id[case_id])
        for case_id in record.member_complaint_ids
        if case_id in events_by_id and case_id != record.representative_complaint_id
    ]
    return DraftReplyPayload(
        merge_id=record.merge_id,
        representative_complaint_id=record.representative_complaint_id,
        member_complaint_ids=list(record.member_complaint_ids),
        representative=_member_summary(representative_event),
        members=members,
        merge_evidence=list(record.evidence),
        risk_flags=list(record.risk_flags),
        system_instruction=SYSTEM_INSTRUCTION,
        common_reply_constraints=list(COMMON_REPLY_CONSTRAINTS),
        prohibited_content_rules=list(PROHIBITED_CONTENT_RULES),
    )


def _member_summary(event: ComplaintIntelligenceEvent) -> DraftReplyMemberSummary:
    structured = _structured_elements(event)
    summary_source = " ".join(structured.values()) or event.masked_text
    return DraftReplyMemberSummary(
        complaint_id=event.id,
        pii_safe_summary=mask_pii(summary_source[:500]).text,
        structured_elements=structured,
        request_segments=[mask_pii(item).text for item in (getattr(event, "request_segments", []) or [])],
        responsible_unit=[mask_pii(item).text for item in (getattr(event, "responsible_unit", []) or [])],
        civil_category=mask_pii(event.civil_category).text if event.civil_category else None,
        entity_texts=[mask_pii(item).text for item in (getattr(event, "entity_texts", []) or [])],
    )


def _structured_elements(event: ComplaintIntelligenceEvent) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in ("observation", "result", "request", "context"):
        element = getattr(event.structured_elements, field, None)
        if element and element.text.strip():
            result[field] = mask_pii(element.text).text
    return result

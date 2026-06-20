"""추천 조치의 evidence id를 보수적으로 보정한다."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.public_insights.action_rubric import (
    allowed_action_types_for_pack,
    preferred_action_types_for_pack,
)
from app.complaint_intelligence.public_insights.evidence_pack import (
    PublicInsightEvidencePack,
    valid_evidence_ids_for_pack,
)
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicAgencyInsightDraft
from app.complaint_intelligence.schemas import RecommendedAction


class ActionRepairReport(BaseModel):
    """추천 조치 evidence id 보정 결과."""

    repaired_action_count: int = 0
    removed_action_count: int = 0
    invalid_evidence_ids: list[str] = Field(default_factory=list)
    empty_action_count: int = 0
    invalid_action_type_count: int = 0
    repaired_action_type_count: int = 0
    repaired_action_text_count: int = 0
    removed_action_due_to_action_type_count: int = 0
    invalid_action_types: list[str] = Field(default_factory=list)
    action_type_repairs: list[dict[str, str]] = Field(default_factory=list)
    repair_strategy: list[str] = Field(default_factory=list)


ACTION_EVIDENCE_HINTS: dict[str, tuple[str, ...]] = {
    "FIELD_INSPECTION": ("현장 안전", "시설 파손", "현장 점검"),
    "SAFETY_NOTICE": ("현장 안전", "시민 안내", "정보 제공"),
    "MAINTENANCE": ("시설 파손", "시설 보수"),
    "ENFORCEMENT": ("단속 공백", "단속 강화"),
    "PUBLIC_GUIDANCE": ("안내 부족", "정보 제공", "소통 부족"),
    "SERVICE_DESIGN": ("접근성/사용성", "서비스 개선", "신청 절차"),
    "PROCESS_IMPROVEMENT": ("처리 지연", "처리 속도 개선", "소통 부족"),
    "POLICY_REVIEW": ("지원 기준", "기준 완화", "지원 확대", "신청 절차"),
    "STAFFING_OR_WORKLOAD_REVIEW": ("처리 지연", "처리 속도 개선"),
    "CITIZEN_COMMUNICATION": ("소통 부족", "소통 강화", "정보 제공"),
}

ACTION_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FIELD_INSPECTION": ("현장", "점검", "확인", "조사", "순찰"),
    "SAFETY_NOTICE": ("안전", "위험", "주의", "공지", "안내"),
    "MAINTENANCE": ("보수", "정비", "수리", "교체", "고장", "시설"),
    "ENFORCEMENT": ("단속", "불법", "주정차", "순찰", "위반"),
    "PUBLIC_GUIDANCE": ("안내", "FAQ", "고지", "체크리스트", "상담", "설명"),
    "SERVICE_DESIGN": ("앱", "예약", "대여", "결제", "화면", "UX", "절차 단순화"),
    "PROCESS_IMPROVEMENT": ("처리", "프로세스", "절차", "재발", "원인", "계획", "개선"),
    "POLICY_REVIEW": ("제도", "정책", "기준", "완화", "지원", "검토"),
    "STAFFING_OR_WORKLOAD_REVIEW": ("부서", "인력", "업무", "병목", "미처리", "누적"),
    "CITIZEN_COMMUNICATION": ("소통", "연락", "진행", "상태", "예정일", "알림"),
}


def repair_action_evidence_ids(
    draft: PublicAgencyInsightDraft,
    pack: PublicInsightEvidencePack,
) -> tuple[PublicAgencyInsightDraft, ActionRepairReport]:
    """invalid evidence id를 제거하고, 명확한 aspect/request 근거가 있을 때만 보강한다."""

    valid_ids = set(valid_evidence_ids_for_pack(pack))
    allowed_action_types = set(allowed_action_types_for_pack(pack))
    preferred_action_types = set(preferred_action_types_for_pack(pack))
    report = ActionRepairReport()
    repaired_actions: list[RecommendedAction] = []

    for action in draft.recommended_actions:
        action = _repair_action_type(action, allowed_action_types, preferred_action_types, report)
        if action is None:
            continue
        original_ids = [str(item) for item in action.supporting_evidence_ids if str(item or "").strip()]
        valid_action_ids = [item for item in original_ids if item in valid_ids]
        invalid_ids = [item for item in original_ids if item not in valid_ids]
        if invalid_ids:
            report.invalid_evidence_ids.extend(_masked_unique(invalid_ids))
            report.repair_strategy.append("removed_invalid_evidence_ids")

        repaired_ids = _dedupe(valid_action_ids)
        if not repaired_ids:
            report.empty_action_count += 1
            repaired_ids = _evidence_ids_from_clear_aspect_or_request(action, pack, valid_ids)
            if repaired_ids:
                report.repair_strategy.append("filled_from_matching_aspect_or_request")
            else:
                report.removed_action_count += 1
                report.repair_strategy.append("removed_action_without_clear_evidence")
                continue

        if repaired_ids != original_ids:
            report.repaired_action_count += 1
        action = _repair_short_action_text(action, pack, report)
        repaired_actions.append(action.model_copy(update={"supporting_evidence_ids": repaired_ids[:3]}))

    uncertainty = list(draft.uncertainty)
    if report.removed_action_count:
        uncertainty.append("근거 ID가 없거나 불명확한 일부 추천 조치를 제외했습니다.")
    return draft.model_copy(update={"recommended_actions": repaired_actions, "uncertainty": uncertainty}), report


def _repair_action_type(
    action: RecommendedAction,
    allowed_action_types: set[str],
    preferred_action_types: set[str],
    report: ActionRepairReport,
) -> RecommendedAction | None:
    action_type = str(action.action_type)
    if action_type in allowed_action_types:
        preferred_match = _clear_action_type_match(action, preferred_action_types)
        if preferred_match and preferred_match != action_type:
            report.repaired_action_type_count += 1
            report.action_type_repairs.append({"from": action_type, "to": preferred_match})
            report.repair_strategy.append("repaired_allowed_action_type_by_preferred_keywords")
            return action.model_copy(update={"action_type": preferred_match})
        return action
    report.invalid_action_type_count += 1
    report.invalid_action_types = _masked_unique([*report.invalid_action_types, action_type])

    repaired_type = _clear_action_type_match(action, allowed_action_types)
    if repaired_type:
        report.repaired_action_type_count += 1
        report.action_type_repairs.append({"from": action_type, "to": repaired_type})
        report.repair_strategy.append("repaired_invalid_action_type_by_clear_keywords")
        return action.model_copy(update={"action_type": repaired_type})

    report.removed_action_count += 1
    report.removed_action_due_to_action_type_count += 1
    report.repair_strategy.append("removed_action_with_unclear_action_type")
    return None


def _clear_action_type_match(action: RecommendedAction, allowed_action_types: set[str]) -> str | None:
    text = " ".join(
        [
            str(action.action or ""),
            str(action.why or ""),
            str(action.expected_impact or ""),
            str(action.risk_or_dependency or ""),
        ]
    )
    scores: dict[str, int] = {}
    for action_type in allowed_action_types:
        score = sum(1 for keyword in ACTION_TYPE_KEYWORDS.get(action_type, ()) if keyword in text)
        if action_type == "ENFORCEMENT" and any(keyword in text for keyword in ("단속", "주정차", "불법주차")):
            score += 2
        if action_type == "PROCESS_IMPROVEMENT" and any(keyword in text for keyword in ("절차", "프로세스", "검토", "개선")):
            score += 1
        if action_type == "SERVICE_DESIGN" and any(keyword in text for keyword in ("앱", "UX", "예약", "결제")):
            score += 1
        if score > 0:
            scores[action_type] = score
    if not scores:
        return None
    best_score = max(scores.values())
    matches = [action_type for action_type, score in scores.items() if score == best_score]
    if len(matches) == 1:
        return matches[0]
    return None


def _repair_short_action_text(
    action: RecommendedAction,
    pack: PublicInsightEvidencePack,
    report: ActionRepairReport,
) -> RecommendedAction:
    action_text = str(action.action or "").strip()
    if not _needs_concrete_action_text(action_text):
        return action
    replacement = _concrete_action_text(str(action.action_type), pack.topic_label)
    if not replacement:
        return action
    report.repaired_action_text_count += 1
    report.repair_strategy.append("expanded_short_action_text_from_rubric")
    return action.model_copy(update={"action": replacement})


def _needs_concrete_action_text(action_text: str) -> bool:
    compact = action_text.replace(" ", "")
    abstract_terms = ("검토", "개선", "강화", "관리", "추진")
    if len(action_text) <= 12 and any(term in action_text for term in abstract_terms):
        return True
    meaningful = [token.strip(".,!?") for token in action_text.split() if token.strip(".,!?")]
    return len(meaningful) <= 4 and any(term in compact for term in abstract_terms)


def _concrete_action_text(action_type: str, topic_label: str) -> str | None:
    topic = topic_label or "해당 민원"
    templates = {
        "FIELD_INSPECTION": f"{topic} 관련 민원 집중 위치를 현장 확인하고 조치 필요 여부를 기록합니다.",
        "SAFETY_NOTICE": f"{topic} 관련 위험 가능 구간에 임시 안전 안내를 게시하고 담당 부서에 공유합니다.",
        "MAINTENANCE": f"{topic} 관련 반복 위치의 시설 상태를 점검하고 보수 우선순위에 반영합니다.",
        "ENFORCEMENT": f"{topic} 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다.",
        "PUBLIC_GUIDANCE": f"{topic} FAQ와 신청 절차 안내를 보강하고 문의 응대 기준을 정리합니다.",
        "SERVICE_DESIGN": f"{topic} 이용 절차의 오류·복잡 단계를 확인하고 안내 문구를 보강합니다.",
        "PROCESS_IMPROVEMENT": f"{topic} 처리 흐름을 점검하고 반복 민원 원인별 개선 과제를 정리합니다.",
        "POLICY_REVIEW": f"{topic} 관련 기준·절차 개선 요구를 정책 검토 과제로 분리해 정리합니다.",
        "STAFFING_OR_WORKLOAD_REVIEW": f"{topic} 담당 부서의 미처리 누적과 처리 기준을 점검합니다.",
        "CITIZEN_COMMUNICATION": f"{topic} 처리 기준과 예상 일정을 시민 안내 문구로 정리합니다.",
    }
    return templates.get(action_type)


def _evidence_ids_from_clear_aspect_or_request(
    action: RecommendedAction,
    pack: PublicInsightEvidencePack,
    valid_ids: set[str],
) -> list[str]:
    hints = ACTION_EVIDENCE_HINTS.get(str(action.action_type), ())
    action_text = " ".join(
        [
            str(action.action or ""),
            str(action.why or ""),
            str(action.expected_impact or ""),
            str(action.risk_or_dependency or ""),
        ]
    )
    matches: list[str] = []
    for item in pack.extracted_aspects:
        label = str(item.get("aspect") or "")
        if _clearly_matches(label, action_text, hints):
            matches.extend(str(evidence_id) for evidence_id in list(item.get("evidence_ids") or []))
    for item in pack.citizen_requests:
        label = " ".join([str(item.get("request_type") or ""), str(item.get("request") or "")])
        if _clearly_matches(label, action_text, hints):
            matches.extend(str(evidence_id) for evidence_id in list(item.get("evidence_ids") or []))
    return [evidence_id for evidence_id in _dedupe(matches) if evidence_id in valid_ids][:3]


def _clearly_matches(label: str, action_text: str, hints: tuple[str, ...]) -> bool:
    if not label:
        return False
    compact_label = label.replace(" ", "")
    compact_action = action_text.replace(" ", "")
    if compact_label and compact_label in compact_action:
        return True
    return any(hint and hint.replace(" ", "") in compact_label for hint in hints)


def _dedupe(values: list[str]) -> list[str]:
    rows: list[str] = []
    for value in values:
        if value and value not in rows:
            rows.append(value)
    return rows


def _masked_unique(values: list[str]) -> list[str]:
    return _dedupe([mask_pii(value).text for value in values])

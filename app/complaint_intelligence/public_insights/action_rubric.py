"""PublicAgencyInsight 추천 조치 action_type 운영 rubric."""

from __future__ import annotations

from typing import Any

from app.complaint_intelligence.schemas import ActionType, PublicInsightType


ALL_ACTION_TYPES: tuple[ActionType, ...] = (
    "FIELD_INSPECTION",
    "SAFETY_NOTICE",
    "MAINTENANCE",
    "ENFORCEMENT",
    "PUBLIC_GUIDANCE",
    "SERVICE_DESIGN",
    "PROCESS_IMPROVEMENT",
    "POLICY_REVIEW",
    "STAFFING_OR_WORKLOAD_REVIEW",
    "CITIZEN_COMMUNICATION",
)


ACTION_TYPE_RUBRIC: dict[PublicInsightType, dict[str, Any]] = {
    "HOTSPOT_RESPONSE_REQUIRED": {
        "allowed_action_types": ["FIELD_INSPECTION", "SAFETY_NOTICE", "MAINTENANCE", "PUBLIC_GUIDANCE"],
        "preferred_action_types": ["FIELD_INSPECTION", "SAFETY_NOTICE"],
        "requires_human_review": True,
    },
    "SAFETY_RISK_SIGNAL": {
        "allowed_action_types": ["FIELD_INSPECTION", "SAFETY_NOTICE", "MAINTENANCE"],
        "preferred_action_types": ["FIELD_INSPECTION", "SAFETY_NOTICE"],
        "requires_human_review": True,
    },
    "RECURRING_COMPLAINT_PATTERN": {
        "allowed_action_types": ["PROCESS_IMPROVEMENT", "FIELD_INSPECTION", "PUBLIC_GUIDANCE", "MAINTENANCE"],
        "preferred_action_types": ["PROCESS_IMPROVEMENT"],
        "requires_human_review": False,
    },
    "REGIONAL_SERVICE_GAP": {
        "allowed_action_types": ["PROCESS_IMPROVEMENT", "PUBLIC_GUIDANCE", "FIELD_INSPECTION"],
        "preferred_action_types": ["PROCESS_IMPROVEMENT"],
        "requires_human_review": False,
    },
    "DEPARTMENT_WORKLOAD_BOTTLENECK": {
        "allowed_action_types": ["STAFFING_OR_WORKLOAD_REVIEW", "PROCESS_IMPROVEMENT", "CITIZEN_COMMUNICATION"],
        "preferred_action_types": ["STAFFING_OR_WORKLOAD_REVIEW", "PROCESS_IMPROVEMENT"],
        "requires_human_review": True,
    },
    "PROCESS_DELAY_RISK": {
        "allowed_action_types": ["PROCESS_IMPROVEMENT", "STAFFING_OR_WORKLOAD_REVIEW", "CITIZEN_COMMUNICATION"],
        "preferred_action_types": ["PROCESS_IMPROVEMENT"],
        "requires_human_review": True,
    },
    "REOPEN_OR_REPEAT_RISK": {
        "allowed_action_types": ["PROCESS_IMPROVEMENT", "CITIZEN_COMMUNICATION", "FIELD_INSPECTION"],
        "preferred_action_types": ["PROCESS_IMPROVEMENT", "CITIZEN_COMMUNICATION"],
        "requires_human_review": True,
    },
    "SEASONAL_OR_TIME_PATTERN": {
        "allowed_action_types": ["PROCESS_IMPROVEMENT", "ENFORCEMENT", "FIELD_INSPECTION", "PUBLIC_GUIDANCE"],
        "preferred_action_types": ["PROCESS_IMPROVEMENT"],
        "requires_human_review": False,
    },
    "PUBLIC_GUIDANCE_NEEDED": {
        "allowed_action_types": ["PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "SERVICE_DESIGN"],
        "preferred_action_types": ["PUBLIC_GUIDANCE"],
        "requires_human_review": False,
    },
    "FACILITY_MAINTENANCE_PRIORITY": {
        "allowed_action_types": ["MAINTENANCE", "FIELD_INSPECTION", "PROCESS_IMPROVEMENT", "SAFETY_NOTICE"],
        "preferred_action_types": ["MAINTENANCE", "FIELD_INSPECTION"],
        "requires_human_review": False,
    },
    "ENFORCEMENT_PRIORITY": {
        "allowed_action_types": ["ENFORCEMENT", "PUBLIC_GUIDANCE", "FIELD_INSPECTION", "PROCESS_IMPROVEMENT"],
        "preferred_action_types": ["ENFORCEMENT"],
        "requires_human_review": True,
    },
    "POLICY_IMPROVEMENT_OPPORTUNITY": {
        "allowed_action_types": ["POLICY_REVIEW", "PUBLIC_GUIDANCE", "PROCESS_IMPROVEMENT"],
        "preferred_action_types": ["POLICY_REVIEW", "PUBLIC_GUIDANCE"],
        "requires_human_review": True,
    },
    "SERVICE_DESIGN_IMPROVEMENT": {
        "allowed_action_types": ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "PROCESS_IMPROVEMENT"],
        "preferred_action_types": ["SERVICE_DESIGN"],
        "requires_human_review": False,
    },
    "ACCESSIBILITY_OR_USABILITY_ISSUE": {
        "allowed_action_types": ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "PROCESS_IMPROVEMENT"],
        "preferred_action_types": ["SERVICE_DESIGN", "PUBLIC_GUIDANCE"],
        "requires_human_review": False,
    },
    "CITIZEN_COMMUNICATION_GAP": {
        "allowed_action_types": ["CITIZEN_COMMUNICATION", "PUBLIC_GUIDANCE", "PROCESS_IMPROVEMENT"],
        "preferred_action_types": ["CITIZEN_COMMUNICATION"],
        "requires_human_review": False,
    },
}


TOPIC_ACTION_TYPE_RUBRIC: tuple[tuple[tuple[str, ...], list[ActionType]], ...] = (
    (("도로 침하", "싱크홀", "땅꺼짐"), ["FIELD_INSPECTION", "SAFETY_NOTICE", "MAINTENANCE"]),
    (("불법주정차", "불법주차", "주정차", "단속", "학교 앞"), ["ENFORCEMENT", "PUBLIC_GUIDANCE", "FIELD_INSPECTION"]),
    (("대형폐기물", "배출 안내", "스티커"), ["PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "SERVICE_DESIGN"]),
    (("하수 악취", "악취", "냄새"), ["PROCESS_IMPROVEMENT", "FIELD_INSPECTION", "MAINTENANCE", "PUBLIC_GUIDANCE"]),
    (("공공자전거", "예약", "대여", "앱"), ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"]),
    (("처리 지연", "미처리", "부서"), ["PROCESS_IMPROVEMENT", "STAFFING_OR_WORKLOAD_REVIEW", "CITIZEN_COMMUNICATION"]),
    (("재민원", "반복 민원"), ["PROCESS_IMPROVEMENT", "CITIZEN_COMMUNICATION", "FIELD_INSPECTION"]),
    (("가로등", "보안등", "조명"), ["FIELD_INSPECTION", "MAINTENANCE", "SAFETY_NOTICE"]),
    (("공사 소음", "소음", "진동"), ["ENFORCEMENT", "PROCESS_IMPROVEMENT", "FIELD_INSPECTION", "PUBLIC_GUIDANCE"]),
    (("접근성", "사용성", "고령자", "장애인"), ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"]),
    (("침수", "배수", "맨홀", "우수관"), ["FIELD_INSPECTION", "MAINTENANCE", "SAFETY_NOTICE"]),
    (("무단투기", "쓰레기 적치", "생활폐기물"), ["ENFORCEMENT", "MAINTENANCE", "PUBLIC_GUIDANCE"]),
    (("공원 시설", "놀이터", "산책로", "벤치"), ["FIELD_INSPECTION", "MAINTENANCE", "CITIZEN_COMMUNICATION"]),
    (("버스", "정류장", "노선", "배차"), ["SERVICE_DESIGN", "PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION"]),
    (("CCTV", "방범", "사각지대", "야간 안전"), ["FIELD_INSPECTION", "SAFETY_NOTICE", "POLICY_REVIEW"]),
    (("금연구역", "흡연", "담배", "담배꽁초"), ["ENFORCEMENT", "PUBLIC_GUIDANCE", "MAINTENANCE"]),
    (("현수막", "광고물", "불법 광고물"), ["ENFORCEMENT", "FIELD_INSPECTION", "MAINTENANCE"]),
    (("반려동물", "배설물", "목줄", "유기동물"), ["ENFORCEMENT", "PUBLIC_GUIDANCE", "FIELD_INSPECTION"]),
    (("인허가", "자격", "면허", "제출 서류"), ["PUBLIC_GUIDANCE", "CITIZEN_COMMUNICATION", "PROCESS_IMPROVEMENT"]),
    (("어린이보호구역", "통학", "등하교"), ["ENFORCEMENT", "FIELD_INSPECTION", "SAFETY_NOTICE"]),
)


HUMAN_REVIEW_REQUIRED_TYPES: set[str] = {
    "SAFETY_RISK_SIGNAL",
    "HOTSPOT_RESPONSE_REQUIRED",
    "POLICY_IMPROVEMENT_OPPORTUNITY",
    "DEPARTMENT_WORKLOAD_BOTTLENECK",
    "PROCESS_DELAY_RISK",
    "REOPEN_OR_REPEAT_RISK",
    "ENFORCEMENT_PRIORITY",
    "ACCESSIBILITY_OR_USABILITY_ISSUE",
}

HUMAN_REVIEW_TOPIC_KEYWORDS: tuple[str, ...] = (
    "정책",
    "제도",
    "지원 기준",
    "기준 완화",
    "지원 확대",
    "복지 지원",
    "안전",
    "위험",
    "단속",
    "침수",
    "방범",
    "CCTV",
    "금연구역",
    "현수막",
    "반려동물",
    "어린이보호구역",
    "통학 안전",
    "접근성",
    "고령자",
    "장애인",
    "외국인",
    "취약계층",
)


def allowed_action_types_for_pack(pack: Any) -> list[ActionType]:
    """EvidencePack의 type/topic을 기준으로 허용 action_type 후보를 반환한다."""

    type_values = _type_allowed(str(getattr(pack, "type_hint", "") or ""))
    topic_values = _topic_allowed(str(getattr(pack, "topic_label", "") or ""))
    return _dedupe([*topic_values, *type_values]) or list(ALL_ACTION_TYPES)


def preferred_action_types_for_pack(pack: Any) -> list[ActionType]:
    """EvidencePack의 type/topic을 기준으로 우선 action_type 후보를 반환한다."""

    topic_values = _topic_allowed(str(getattr(pack, "topic_label", "") or ""))
    type_hint = str(getattr(pack, "type_hint", "") or "")
    type_values = list(ACTION_TYPE_RUBRIC.get(type_hint, {}).get("preferred_action_types") or [])
    return _dedupe([*topic_values[:2], *type_values])[:3]


def requires_human_review_for_pack(pack: Any) -> bool:
    type_hint = str(getattr(pack, "type_hint", "") or "")
    if type_hint in HUMAN_REVIEW_REQUIRED_TYPES:
        return True
    topic_label = str(getattr(pack, "topic_label", "") or "")
    if any(keyword in topic_label for keyword in HUMAN_REVIEW_TOPIC_KEYWORDS):
        return True
    return bool(ACTION_TYPE_RUBRIC.get(type_hint, {}).get("requires_human_review"))


def action_type_rubric_for_pack(pack: Any) -> dict[str, Any]:
    """LLM prompt/report에 넣을 compact rubric payload."""

    allowed = allowed_action_types_for_pack(pack)
    preferred = [item for item in preferred_action_types_for_pack(pack) if item in allowed]
    return {
        "allowed_action_types": allowed,
        "preferred_action_types": preferred or allowed[:1],
        "requires_human_review": requires_human_review_for_pack(pack),
    }


def _type_allowed(type_hint: str) -> list[ActionType]:
    return list(ACTION_TYPE_RUBRIC.get(type_hint, {}).get("allowed_action_types") or [])


def _topic_allowed(topic_label: str) -> list[ActionType]:
    compact_topic = topic_label.replace(" ", "")
    for keywords, action_types in TOPIC_ACTION_TYPE_RUBRIC:
        if any(keyword.replace(" ", "") in compact_topic for keyword in keywords):
            return list(action_types)
    return []


def _dedupe(values: list[str]) -> list[ActionType]:
    rows: list[ActionType] = []
    for value in values:
        if value in ALL_ACTION_TYPES and value not in rows:
            rows.append(value)  # type: ignore[arg-type]
    return rows

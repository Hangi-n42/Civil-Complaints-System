"""공공기관 인사이트별 허용 행정 조치 카탈로그."""

from __future__ import annotations

from app.complaint_intelligence.schemas import PublicInsightType


ACTION_CATALOG: dict[PublicInsightType, list[str]] = {
    "HOTSPOT_RESPONSE_REQUIRED": [
        "관련 부서 즉시 공유",
        "현장 확인 일정 수립",
        "시민 안내 또는 공지 검토",
    ],
    "SAFETY_RISK_SIGNAL": [
        "긴급 현장 점검",
        "위험 구역 임시 안전 조치",
        "시민 안전 안내",
        "관련 부서 즉시 공유",
    ],
    "RECURRING_COMPLAINT_PATTERN": [
        "반복 민원 원인 항목 정리",
        "담당 부서별 처리 계획 수립",
        "반복 위치 또는 절차 점검",
    ],
    "REGIONAL_SERVICE_GAP": [
        "지역별 서비스 제공 현황 점검",
        "반복 지역 현장 확인",
        "지역 안내 또는 자원 배분 검토",
    ],
    "DEPARTMENT_WORKLOAD_BOTTLENECK": [
        "부서별 미처리 건 점검",
        "업무 병목 원인 확인",
        "인력 또는 처리 우선순위 조정 검토",
    ],
    "PROCESS_DELAY_RISK": [
        "장기 미처리 건 우선 검토",
        "처리 기준과 지연 사유 점검",
        "처리 예정일 시민 안내 강화",
    ],
    "REOPEN_OR_REPEAT_RISK": [
        "재민원 원인 점검",
        "처리 완료 안내 개선",
        "현장 조치 실효성 확인",
    ],
    "SEASONAL_OR_TIME_PATTERN": [
        "민원 집중 시간대 점검 강화",
        "운영 시간 또는 단속 시간 조정",
        "행사/계절성 안내 사전 공지",
    ],
    "PUBLIC_GUIDANCE_NEEDED": [
        "FAQ/안내 페이지 보강",
        "신청 절차 체크리스트 추가",
        "현장 안내문/고지문 개선",
        "상담 스크립트 보강",
    ],
    "FACILITY_MAINTENANCE_PRIORITY": [
        "시설 상태 현장 확인",
        "보수 우선순위 상향",
        "반복 위치 유지보수 계획 반영",
    ],
    "ENFORCEMENT_PRIORITY": [
        "민원 집중 시간대 단속 강화",
        "단속 안내 현수막/표지 검토",
        "반복 위치 순찰 동선 반영",
    ],
    "POLICY_IMPROVEMENT_OPPORTUNITY": [
        "반복 개선 요구 항목 정리",
        "제도/기준/요금 검토 과제화",
        "시민 설명자료 보강",
        "관련 부서 협의 필요사항 정리",
    ],
    "SERVICE_DESIGN_IMPROVEMENT": [
        "신청/예약/이용 절차 단순화 검토",
        "앱/웹 UX 문구 개선",
        "오류 발생 단계 확인",
        "사용자 안내 흐름 재설계",
    ],
    "ACCESSIBILITY_OR_USABILITY_ISSUE": [
        "취약계층 이용 단계 점검",
        "쉬운 안내 문구와 대체 신청 경로 검토",
        "접근성 테스트와 상담 지원 보강",
    ],
    "CITIZEN_COMMUNICATION_GAP": [
        "처리 기준과 진행 상태 안내 강화",
        "책임 부서와 예상 처리 기간 명확화",
        "민원 접수/처리 알림 문구 개선",
    ],
}


def allowed_actions_for(insight_type: PublicInsightType) -> list[str]:
    """인사이트 타입에 허용된 조치 후보를 반환한다."""

    return list(ACTION_CATALOG.get(insight_type, []))

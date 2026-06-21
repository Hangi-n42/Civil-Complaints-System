import type { DuplicateEvidence, DuplicateMergeRecord, DuplicateRiskFlag } from "@/lib/api";

export function duplicateStatusLabel(status: DuplicateMergeRecord["status"]): string {
  switch (status) {
    case "candidate":
      return "추천 후보";
    case "confirmed":
      return "담당자 확정 그룹";
    case "split":
      return "분리됨";
    case "rejected":
      return "추천 기각";
    default:
      return "상태 확인 필요";
  }
}

export function duplicateStatusTone(status: DuplicateMergeRecord["status"]): string {
  switch (status) {
    case "candidate":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "confirmed":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "split":
      return "border-slate-200 bg-slate-50 text-slate-600";
    case "rejected":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-600";
  }
}

export function duplicateGroupTitle(group: DuplicateMergeRecord): string {
  const ids = group.member_complaint_ids.join(" ");
  if (ids.includes("dm-hotspot-noise")) return "한빛아파트 북문 공사 소음 반복 민원";
  if (ids.includes("dm-general-lamp")) return "늘봄공원 북문 가로등 고장 민원";
  if (ids.includes("dm-risk-parking")) return "새빛초 후문 불법 주정차 관련 민원";
  if (ids.includes("dm-confirmed-library")) return "온누리도서관 어린이실 냉난방기 고장 민원";
  if (ids.includes("demo-sinkhole_hotspot")) return "을지로 보행로 도로 침하 반복 민원";
  if (ids.includes("demo-illegal_parking_enforcement")) return "가정초등학교 후문 불법 주정차 반복 민원";
  if (ids.includes("demo-bulky_waste_guidance")) return "덕진동 대형폐기물 배출 안내 반복 문의";
  if (ids.includes("demo-welfare_support_process")) return "중촌동 복지 지원 신청 절차 반복 문의";
  if (ids.includes("demo-odor_night_hotspot")) return "삼산동 하수 악취 야간 반복 민원";

  const locationState = group.location_state;
  if (locationState === "conflict") return "장소 확인이 필요한 중복 민원 후보";
  if (group.risk_flags.length > 0) return "주의 사유가 있는 중복 민원 후보";
  return "반복 접수된 민원 후보";
}

export function representativeReasonLabel(group: DuplicateMergeRecord): string {
  const reason = group.representative.selection_reason || "";
  if (reason.includes("위치") || reason.includes("시설") || reason.includes("요구")) {
    return "장소와 요청 내용이 가장 구체적으로 정리되어 대표로 검토하기 좋습니다.";
  }
  if (reason.includes("PII") || reason.includes("개인정보")) {
    return "개인정보 노출 요소가 적고 공통 사건 설명이 충분한 민원입니다.";
  }
  if (reason.trim()) {
    return "공통 사건을 설명하는 정보가 가장 충분한 민원입니다.";
  }
  return "대표 검토에 필요한 장소, 상황, 요청 정보가 비교적 충분한 민원입니다.";
}

export function evidenceLabel(evidence: DuplicateEvidence): string {
  const message = evidence.message || "";
  const type = evidence.type || "";

  if (message.includes("PII-safe") || message.includes("semantic") || type.includes("semantic")) {
    return "민원 요약과 요청 내용이 서로 유사합니다.";
  }
  if (message.includes("exact") || message.includes("nearby") || type.includes("location")) {
    return locationEvidenceLabel(message, evidence.value);
  }
  if (type.includes("request") || message.includes("request")) {
    return "요청 유형과 처리 방향을 함께 확인해야 합니다.";
  }
  if (type.includes("department") || message.includes("department")) {
    return "담당 부서 신호가 서로 가깝습니다.";
  }
  if (typeof evidence.value === "number") {
    return `중복 가능성 판단 점수 ${(evidence.value * 100).toFixed(0)}점`;
  }

  return sanitizeInternalTerms(message) || "중복 후보로 볼 수 있는 근거가 있습니다.";
}

export function riskFlagLabel(flag: DuplicateRiskFlag): string {
  const labels: Record<string, string> = {
    LOCATION_MISMATCH: "장소가 서로 다름",
    LOCATION_AMBIGUOUS: "장소 근거 부족",
    REQUEST_TYPE_MISMATCH: "요청 유형 혼합",
    DEPARTMENT_MISMATCH: "담당 부서 충돌",
    SAFETY_AND_INCONVENIENCE_MIXED: "안전 위험과 단순 불편 혼합",
    LEGAL_RIGHTS_OR_DEADLINE_RISK: "권리관계·처리기한 주의",
    PII_RISK: "개인정보 확인 필요",
    MULTI_INTENT_SEGMENTS: "복수 요구 포함",
    SEMANTIC_ONLY_MATCH: "요약 유사도 중심 근거",
    LOW_EVIDENCE: "구조화 근거 부족",
    TIME_WINDOW_TOO_WIDE: "접수 시간 간격 큼",
  };
  return labels[flag.code] ?? flag.code;
}

export function riskFlagTone(flag: DuplicateRiskFlag): string {
  if (flag.severity === "blocker") return "border-red-200 bg-red-50 text-red-700";
  if (flag.severity === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

export function canCreateDraftReply(group: DuplicateMergeRecord): boolean {
  return group.status === "confirmed" && group.allowed_actions.includes("draft_reply");
}

export function duplicateQueueContextLabel(group: DuplicateMergeRecord): {
  label: string;
  className: string;
  title: string;
} {
  const alertCount = group.linked_issue_alert_ids.length;
  if (alertCount > 0) {
    return {
      label: `핫스팟 연결 ${alertCount}건`,
      className: "border-blue-200 bg-blue-50 text-blue-700",
      title: "핫스팟 안에서 같은 장소·같은 사건 반복 민원으로 이어진 중복 후보입니다.",
    };
  }
  return {
    label: "일반 검토",
    className: "border-slate-200 bg-slate-50 text-slate-600",
    title: "핫스팟과 직접 연결되지 않은 일반 중복 병합 검토 후보입니다.",
  };
}

export function duplicateBadgeForCase(caseId: string, groups: DuplicateMergeRecord[]): {
  label: string;
  className: string;
  title: string;
} | null {
  const related = groups.filter((group) => group.member_complaint_ids.includes(caseId));
  if (related.length === 0) return null;
  if (related.some((group) => group.status === "confirmed")) {
    return {
      label: "확정 그룹",
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      title: "담당자가 확정한 중복 민원 그룹에 포함되어 있습니다.",
    };
  }
  if (related.some((group) => group.risk_flags.some((flag) => flag.severity === "blocker"))) {
    return {
      label: "주의 필요",
      className: "border-red-200 bg-red-50 text-red-700",
      title: "중복 후보가 있으나 확정 전 반드시 확인해야 할 차단 위험이 있습니다.",
    };
  }
  return {
    label: "중복 후보 있음",
    className: "border-amber-200 bg-amber-50 text-amber-700",
    title: "검토 가능한 중복 민원 추천 후보가 있습니다.",
  };
}

export function countGroupsLinkedToAlert(alertId: string, groups: DuplicateMergeRecord[]): number {
  return groups.filter((group) => group.linked_issue_alert_ids.includes(alertId)).length;
}

export function countGroupsLinkedToInsight(insightId: string, groups: DuplicateMergeRecord[]): number {
  return groups.filter((group) => group.linked_public_insight_ids.includes(insightId)).length;
}

function locationEvidenceLabel(message: string, value?: DuplicateEvidence["value"]): string {
  const signal = String(value ?? message).toLowerCase();
  if (signal.includes("conflict")) return "장소 신호가 달라 별도 확인이 필요합니다.";
  if (signal.includes("ambiguous") || signal.includes("missing")) return "장소 정보가 충분하지 않아 확인이 필요합니다.";
  if (signal.includes("nearby")) return "장소가 가까운 것으로 보이나 세부 위치 확인이 필요합니다.";
  return "장소와 시설 신호가 일치합니다.";
}

function sanitizeInternalTerms(message: string): string {
  return message
    .replaceAll("PII-safe", "민감정보를 제외한")
    .replaceAll("PII", "개인정보")
    .replaceAll("payload", "자료")
    .replaceAll("semantic similarity", "요약 유사도")
    .replaceAll("exact", "일치")
    .trim();
}

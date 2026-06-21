import type { DuplicateEvidence, DuplicateMergeRecord, DuplicateRiskFlag } from "@/lib/api";

export type DuplicateReviewTone = "ok" | "review" | "blocker";

export type DuplicateReviewChecklistItem = {
  label: string;
  value: string;
  detail: string;
  tone: DuplicateReviewTone;
};

export type DuplicateCaseReviewRow = {
  complaintId: string;
  requestType: string;
  role: "대표" | "구성";
  attention: string;
  tone: DuplicateReviewTone;
};

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

export function duplicateCandidateGrade(group: DuplicateMergeRecord): {
  label: string;
  description: string;
  className: string;
} {
  if (group.risk_flags.some((flag) => flag.severity === "blocker")) {
    return {
      label: "차단 위험",
      description: "확정 전 차이점을 먼저 해소해야 합니다.",
      className: "border-red-200 bg-red-50 text-red-700",
    };
  }
  if (group.recommendation_level === "strong") {
    return {
      label: "강한 후보",
      description: "공통점이 뚜렷하지만 담당자 확인은 필요합니다.",
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }
  if (group.recommendation_level === "weak") {
    return {
      label: "약한 후보",
      description: "비슷한 점은 있으나 분리 가능성을 먼저 봐야 합니다.",
      className: "border-slate-200 bg-slate-50 text-slate-600",
    };
  }
  return {
    label: "검토 후보",
    description: "병합 가능성과 분리 필요성을 함께 확인하세요.",
    className: "border-amber-200 bg-amber-50 text-amber-800",
  };
}

export function duplicateReviewPriorityLabel(group: DuplicateMergeRecord): string {
  if (group.risk_flags.some((flag) => flag.severity === "blocker")) return "검토 우선도 주의";
  if (group.confidence >= 0.78) return "검토 우선도 높음";
  if (group.confidence >= 0.55) return "검토 우선도 보통";
  return "검토 우선도 낮음";
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

export function duplicateCommonPoints(group: DuplicateMergeRecord): string[] {
  const points = uniqueStrings([
    ...group.evidence.slice(0, 3).map(evidenceLabel),
    group.linked_issue_alert_ids.length > 0 ? `같은 핫스팟 경보 ${group.linked_issue_alert_ids.length}건과 연결되어 있습니다.` : "",
    group.linked_public_insight_ids.length > 0 ? `같은 행정 인사이트 ${group.linked_public_insight_ids.length}건과 연결되어 있습니다.` : "",
    requestTypeValues(group).length === 1 ? `요청 유형이 모두 ${duplicateRequestTypeLabel(requestTypeValues(group)[0])} 계열입니다.` : "",
  ]);
  return points.length > 0 ? points : ["같은 사건으로 볼 수 있는 구조화 근거를 확인해야 합니다."];
}

export function duplicateDifferencePoints(group: DuplicateMergeRecord): string[] {
  const requestTypes = requestTypeValues(group);
  const points = uniqueStrings([
    ...group.risk_flags.map((flag) => riskFlagLabel(flag)),
    locationStateDifferenceLabel(group.location_state),
    requestTypes.length > 1 ? `요청 유형이 ${requestTypes.map(duplicateRequestTypeLabel).join(", ")}로 섞여 있습니다.` : "",
    group.blocked_actions.length > 0 ? `${group.blocked_actions.length}개 작업이 차단되어 있습니다.` : "",
  ]);
  return points.length > 0
    ? points
    : ["뚜렷한 차단 신호는 없지만 대표 답변으로 모든 요구를 다룰 수 있는지 확인하세요."];
}

export function duplicatePreMergeChecklist(group: DuplicateMergeRecord): DuplicateReviewChecklistItem[] {
  const requestTypes = requestTypeValues(group);
  const blockerCodes = new Set(group.risk_flags.filter((flag) => flag.severity === "blocker").map((flag) => flag.code));
  const warningCodes = new Set(group.risk_flags.filter((flag) => flag.severity === "warning").map((flag) => flag.code));

  return [
    {
      label: "장소·시설",
      value: duplicateLocationStateLabel(group.location_state),
      detail: locationChecklistDetail(group.location_state),
      tone: locationChecklistTone(group.location_state),
    },
    {
      label: "요청 유형",
      value: requestTypes.length === 1 ? duplicateRequestTypeLabel(requestTypes[0]) : requestTypes.length > 1 ? "혼합" : "확인 필요",
      detail:
        requestTypes.length === 1
          ? "같은 처리 방향으로 묶을 수 있는지 확인하세요."
          : "단속, 보상, 안전, 안내가 섞이면 분리 처리해야 할 수 있습니다.",
      tone:
        blockerCodes.has("REQUEST_TYPE_MISMATCH") || blockerCodes.has("MULTI_INTENT_SEGMENTS")
          ? "blocker"
          : requestTypes.length === 1
            ? "ok"
            : "review",
    },
    {
      label: "권리·기한",
      value: blockerCodes.has("LEGAL_RIGHTS_OR_DEADLINE_RISK") ? "차단" : warningCodes.has("LEGAL_RIGHTS_OR_DEADLINE_RISK") ? "주의" : "신호 없음",
      detail: "보상, 이의제기, 처리기한 변경 요구가 섞였는지 확인하세요.",
      tone: riskToneForCode(group, "LEGAL_RIGHTS_OR_DEADLINE_RISK"),
    },
    {
      label: "안전 위험",
      value: hasRiskCode(group, "SAFETY_AND_INCONVENIENCE_MIXED") ? "혼합 주의" : "분리 신호 없음",
      detail: "긴급 안전 신고와 단순 문의가 함께 있으면 답변을 분리하세요.",
      tone: riskToneForCode(group, "SAFETY_AND_INCONVENIENCE_MIXED"),
    },
    {
      label: "대표 답변",
      value: group.risk_flags.some((flag) => flag.severity === "blocker") ? "생성 차단" : "검토 후 가능",
      detail: "대표 민원 하나로 모든 민원의 요구가 누락 없이 답변되는지 확인하세요.",
      tone: group.risk_flags.some((flag) => flag.severity === "blocker") ? "blocker" : "review",
    },
  ];
}

export function duplicateCaseReviewRows(group: DuplicateMergeRecord): DuplicateCaseReviewRow[] {
  return group.member_complaint_ids.map((complaintId) => {
    const riskCount = group.risk_flags.filter((flag) => flag.affected_case_ids.includes(complaintId)).length;
    return {
      complaintId,
      requestType: duplicateRequestTypeLabel(group.request_types[complaintId] ?? "other"),
      role: complaintId === group.representative_complaint_id ? "대표" : "구성",
      attention: riskCount > 0 ? `주의 사유 ${riskCount}건` : "공통 답변 적용 여부 확인",
      tone: riskCount > 0 ? "review" : "ok",
    };
  });
}

export function duplicateRequestTypeLabel(requestType: string): string {
  const labels: Record<string, string> = {
    enforcement: "단속·계도",
    compensation: "보상·권리",
    facility_improvement: "시설 개선",
    safety_action: "안전 조치",
    inquiry: "단순 문의",
    guidance: "안내 요청",
    other: "기타",
  };
  return labels[requestType] ?? "확인 필요";
}

export function duplicateLocationStateLabel(locationState: DuplicateMergeRecord["location_state"]): string {
  const labels: Record<string, string> = {
    exact: "일치",
    nearby: "인접",
    ambiguous: "불명확",
    missing: "정보 부족",
    conflict: "충돌",
  };
  return labels[locationState] ?? "확인 필요";
}

export function canCreateDraftReply(group: DuplicateMergeRecord): boolean {
  return group.status === "confirmed" && group.allowed_actions.includes("draft_reply");
}

// /reply-draft(실제 대표 답변 초안 생성)는 /draft-reply(payload 조회)와 같은 confirmed-only 조건이지만,
// 혼동을 피하려고 별도 helper로 둔다(핸드오프 §6).
export function canGenerateDuplicateReplyDraft(group: DuplicateMergeRecord): boolean {
  return group.status === "confirmed" && group.allowed_actions.includes("draft_reply");
}

// 답변 초안 사후 점검 결과(safety_warnings) 코드를 담당자용 문구로 바꾼다(핸드오프 §11).
export function safetyWarningLabel(code: string): string {
  const labels: Record<string, string> = {
    PII_PHONE: "초안 내 전화번호 의심 표현 확인 필요",
    PII_EMAIL: "초안 내 이메일 의심 표현 확인 필요",
    PII_DETAILED_ADDRESS: "초안 내 상세주소 의심 표현 확인 필요",
    AUTO_SEND_PROMISE: "자동 발송으로 오해될 표현 확인 필요",
    AUTO_MERGE_PROMISE: "자동 병합·일괄 처리로 오해될 표현 확인 필요",
    COMPENSATION_PROMISE: "보상 확정 표현 확인 필요",
    DEADLINE_CHANGE_PROMISE: "처리기한 확정 표현 확인 필요",
    NO_SEARCH_CONTEXT: "검색 근거 부족",
    RETRIEVAL_ERROR: "검색 실패로 안전 초안 사용",
    RISK_FLAGS_PRESENT: "병합 주의 사유가 있는 그룹",
  };
  return labels[code] ?? code;
}

// 안전 fallback 초안이면 상단에 보여줄 안내 문구를 반환한다(핸드오프 §5/§E). 정상 생성이면 null.
export function replyDraftFallbackNotice(metadata: Record<string, unknown>): string | null {
  if (!metadata || metadata.fallback_used !== true) return null;
  const reason = String(metadata.fallback_reason ?? "");
  const retrievalWarning = String(metadata.retrieval_warning ?? "");
  if (reason.includes("RETRIEVAL_ERROR") || retrievalWarning.includes("RETRIEVAL_ERROR")) {
    return "검색 실패로 담당자 검토용 안전 초안이 생성되었습니다.";
  }
  if (reason.includes("NO_SEARCH_CONTEXT")) {
    return "검색 근거가 부족해 안전 초안이 생성되었습니다.";
  }
  return "담당자 검토용 안전 초안이 생성되었습니다.";
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

function requestTypeValues(group: DuplicateMergeRecord): string[] {
  return [...new Set(Object.values(group.request_types).filter(Boolean))].sort();
}

function locationStateDifferenceLabel(locationState: DuplicateMergeRecord["location_state"]): string {
  if (locationState === "exact") return "";
  if (locationState === "nearby") return "장소가 가까운 수준이라 세부 위치 확인이 필요합니다.";
  if (locationState === "ambiguous") return "장소 근거가 불명확합니다.";
  if (locationState === "missing") return "장소 정보가 부족합니다.";
  if (locationState === "conflict") return "장소 신호가 서로 충돌합니다.";
  return "";
}

function locationChecklistDetail(locationState: DuplicateMergeRecord["location_state"]): string {
  if (locationState === "exact") return "같은 장소나 시설로 볼 근거가 있습니다.";
  if (locationState === "nearby") return "인접 장소가 같은 현장인지 확인하세요.";
  if (locationState === "ambiguous") return "민원별 상세 위치를 다시 확인하세요.";
  if (locationState === "missing") return "장소 정보가 부족해 확정 전 보완이 필요합니다.";
  return "장소가 충돌하므로 병합하면 안 될 수 있습니다.";
}

function locationChecklistTone(locationState: DuplicateMergeRecord["location_state"]): DuplicateReviewTone {
  if (locationState === "exact") return "ok";
  if (locationState === "conflict") return "blocker";
  return "review";
}

function riskToneForCode(group: DuplicateMergeRecord, code: string): DuplicateReviewTone {
  const flag = group.risk_flags.find((item) => item.code === code);
  if (!flag) return "ok";
  return flag.severity === "blocker" ? "blocker" : "review";
}

function hasRiskCode(group: DuplicateMergeRecord, code: string): boolean {
  return group.risk_flags.some((flag) => flag.code === code);
}

function uniqueStrings(items: string[]): string[] {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
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

// 행정 인사이트 표시용 순수 로직(렌더링 없음 → 단위 테스트 대상).

// 우선순위 color(gray/blue/amber/red) → 뱃지 tailwind 클래스. 미지값은 slate 폴백.
export function priorityColorClass(color: string): string {
  switch (color) {
    case "red":
      return "bg-red-100 text-red-800 border border-red-200";
    case "amber":
      return "bg-amber-100 text-amber-800 border border-amber-200";
    case "blue":
      return "bg-blue-100 text-blue-800 border border-blue-200";
    case "gray":
    default:
      return "bg-slate-100 text-slate-700 border border-slate-200";
  }
}

// 정렬 우선순위: CRITICAL > HIGH > MEDIUM > LOW > 기타.
export function priorityRank(priority: string): number {
  switch (priority) {
    case "CRITICAL":
      return 0;
    case "HIGH":
      return 1;
    case "MEDIUM":
      return 2;
    case "LOW":
      return 3;
    default:
      return 4;
  }
}

// 우선순위 높은 순 정렬. 원본 불변.
export function sortInsightsByPriority<T extends { priority: string }>(insights: T[]): T[] {
  return [...insights].sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority));
}

// 추천 조치 horizon(백엔드 enum) → 한국어 라벨 + 표시 순서(§4.3: 즉시/단기/중기/장기).
export const HORIZON_ORDER = ["IMMEDIATE", "SHORT_TERM", "MID_TERM", "LONG_TERM"] as const;
export const HORIZON_LABELS: Record<string, string> = {
  IMMEDIATE: "즉시",
  SHORT_TERM: "단기",
  MID_TERM: "중기",
  LONG_TERM: "장기",
};

// recommended_actions를 horizon별로 묶는다. 정의된 순서대로, 비어있지 않은 그룹만.
// 알 수 없는 horizon은 '기타' 그룹으로 마지막에 모은다.
export function groupActionsByHorizon<T extends { horizon: string }>(
  actions: T[],
): Array<{ key: string; label: string; actions: T[] }> {
  const known = new Set<string>(HORIZON_ORDER);
  const groups: Array<{ key: string; label: string; actions: T[] }> = HORIZON_ORDER.map((key) => ({
    key,
    label: HORIZON_LABELS[key],
    actions: actions.filter((a) => a.horizon === key),
  }));
  const others = actions.filter((a) => !known.has(a.horizon));
  if (others.length > 0) {
    groups.push({ key: "OTHER", label: "기타", actions: others });
  }
  return groups.filter((g) => g.actions.length > 0);
}

// top_aspects/citizen_requests 항목(loose dict)에서 라벨+건수를 안전 추출.
export function labeledCount(item: Record<string, unknown>, labelKey: string): { label: string; count: number } {
  const rawLabel = item[labelKey];
  const rawCount = item.count;
  return {
    label: typeof rawLabel === "string" ? rawLabel : "",
    count: typeof rawCount === "number" ? rawCount : 0,
  };
}

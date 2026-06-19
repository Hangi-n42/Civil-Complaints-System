// 실시간 이슈 경보 표시용 순수 로직(렌더링 없음 → 단위 테스트 대상).

// 백엔드가 주는 color(gray/amber/red)를 뱃지 tailwind 클래스로 매핑한다.
// 라벨(관찰/주의/긴급)은 백엔드 severity_label을 그대로 쓰고, 색만 여기서 결정한다.
// 알 수 없는 값은 slate로 폴백.
export function severityColorClass(color: string): string {
  switch (color) {
    case "red":
      return "bg-red-100 text-red-800 border border-red-200";
    case "amber":
      return "bg-amber-100 text-amber-800 border border-amber-200";
    case "gray":
    default:
      return "bg-slate-100 text-slate-700 border border-slate-200";
  }
}

// 정렬 우선순위: 긴급(CRITICAL) > 주의(WARNING) > 관찰(WATCH) > 기타.
export function severityRank(severity: string): number {
  switch (severity) {
    case "CRITICAL":
      return 0;
    case "WARNING":
      return 1;
    case "WATCH":
      return 2;
    default:
      return 3;
  }
}

// severity 높은 순으로, 동순위는 급증비(surge_ratio) 높은 순으로 정렬한다.
// 원본 배열은 변경하지 않는다.
export function sortAlertsBySeverity<T extends { severity: string; surge_ratio: number }>(alerts: T[]): T[] {
  return [...alerts].sort((a, b) => {
    const rankDiff = severityRank(a.severity) - severityRank(b.severity);
    if (rankDiff !== 0) return rankDiff;
    return (b.surge_ratio ?? 0) - (a.surge_ratio ?? 0);
  });
}

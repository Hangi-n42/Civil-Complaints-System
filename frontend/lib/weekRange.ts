// 관리자 통계 "주간 트렌드" 라벨용 주 구간 계산.
// 주 시작은 월요일. 기준일이 속한 주는 진행 중이므로 제외하고,
// 직전 완료 주부터 과거로 count개를 오래된 순서(1주차..N주차)로 반환한다.

export type WeekRange = { start: Date; end: Date };

export function getRecentCompletedWeekRanges(ref: Date, count: number): WeekRange[] {
  // ref가 속한 주의 월요일 (월=0 기준 경과일수만큼 빼기)
  const mondayOffset = (ref.getDay() + 6) % 7;
  const thisMonday = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate() - mondayOffset);

  const ranges: WeekRange[] = [];
  for (let i = count; i >= 1; i -= 1) {
    const start = new Date(thisMonday.getFullYear(), thisMonday.getMonth(), thisMonday.getDate() - 7 * i);
    const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
    ranges.push({ start, end });
  }
  return ranges;
}

// "6.8~6.14" 형식 (연도 제외)
export function formatWeekRange({ start, end }: WeekRange): string {
  const fmt = (d: Date) => `${d.getMonth() + 1}.${d.getDate()}`;
  return `${fmt(start)}~${fmt(end)}`;
}

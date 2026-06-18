import { describe, it, expect } from "vitest";
import { getRecentCompletedWeekRanges, formatWeekRange } from "../lib/weekRange";

// 월 인덱스는 0-기반(5 = 6월). 로컬 시간 기준으로 생성한다.
const d = (y: number, m: number, day: number) => new Date(y, m - 1, day);

describe("getRecentCompletedWeekRanges", () => {
  it("기준일이 속한 진행 중 주는 제외하고, 직전 완료 주부터 오래된 순으로 반환한다", () => {
    // 2026-06-18(목) -> 이번 주(6.15~6.21)는 진행 중이라 제외
    const ranges = getRecentCompletedWeekRanges(d(2026, 6, 18), 4);
    expect(ranges.map(formatWeekRange)).toEqual([
      "5.18~5.24", // 1주차(가장 오래됨)
      "5.25~5.31", // 2주차
      "6.1~6.7", // 3주차
      "6.8~6.14", // 4주차(가장 최근, 완료 주)
    ]);
  });

  it("기준일이 월요일이어도 그 주(진행 중)는 제외한다", () => {
    // 2026-06-15(월) -> 최신 완료 주는 직전 주 6.8~6.14
    const ranges = getRecentCompletedWeekRanges(d(2026, 6, 15), 1);
    expect(formatWeekRange(ranges[0])).toBe("6.8~6.14");
  });

  it("기준일이 일요일이면 그 주(월~일)에 속하므로 제외한다", () => {
    // 2026-06-21(일)은 6.15~6.21 주에 속함 -> 최신 완료 주는 6.8~6.14
    const ranges = getRecentCompletedWeekRanges(d(2026, 6, 21), 1);
    expect(formatWeekRange(ranges[0])).toBe("6.8~6.14");
  });

  it("연말 경계에서 이전 연도로 넘어가도 올바르게 계산한다", () => {
    // 2026-01-05(월) -> 최신 완료 주는 2025-12-29 ~ 2026-01-04
    const ranges = getRecentCompletedWeekRanges(d(2026, 1, 5), 1);
    expect(ranges[0].start.getFullYear()).toBe(2025);
    expect(ranges[0].start.getMonth()).toBe(11); // 12월
    expect(ranges[0].start.getDate()).toBe(29);
    expect(formatWeekRange(ranges[0])).toBe("12.29~1.4");
  });
});

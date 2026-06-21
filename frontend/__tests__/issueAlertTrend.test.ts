import { describe, expect, it } from "vitest";
import { formatIssueAlertSummary, formatIssueAlertTrend } from "../components/intelligence/IssueAlertCard";

describe("formatIssueAlertTrend", () => {
  it("baseline이 0이면 배율 대신 신규 급증 문구를 쓴다", () => {
    expect(formatIssueAlertTrend({ recent_count: 6, baseline: 0, surge_ratio: 6 })).toBe(
      "최근 6건 · 과거 7일 기준선 0건 · 신규 급증",
    );
  });

  it("baseline이 1보다 작으면 기준선 없음 문구로 표시한다", () => {
    expect(formatIssueAlertTrend({ recent_count: 6, baseline: 0.3, surge_ratio: 6 })).toBe(
      "최근 6건 · 기준선 없음 · 급증 감지",
    );
  });

  it("baseline이 1 이상이면 기존 배율 문구를 유지한다", () => {
    expect(formatIssueAlertTrend({ recent_count: 9, baseline: 3, surge_ratio: 3 })).toBe(
      "최근 9건 · 과거 7일 기준선 3건 대비 3.0배",
    );
  });

  it("baseline이 낮은 카드 summary에서는 배율 표현을 완화한다", () => {
    expect(
      formatIssueAlertSummary({
        recent_count: 6,
        baseline: 0,
        summary: "최근 3시간 동안 6건이 접수되었고 7일 기준선 대비 6.0배 증가했습니다.",
      }),
    ).toBe("최근 6건이 같은 이슈로 집중 접수되었습니다. 담당자 검토가 필요한 신규 급증 신호입니다.");
  });
});

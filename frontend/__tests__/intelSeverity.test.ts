import { describe, it, expect } from "vitest";
import { severityColorClass, severityRank, sortAlertsBySeverity } from "../components/intelligence/severity";

describe("severityColorClass", () => {
  it("color 값을 뱃지 클래스로 매핑한다", () => {
    expect(severityColorClass("red")).toContain("bg-red-100");
    expect(severityColorClass("amber")).toContain("bg-amber-100");
    expect(severityColorClass("gray")).toContain("bg-slate-100");
  });

  it("알 수 없는 color는 slate로 폴백한다", () => {
    expect(severityColorClass("purple")).toContain("bg-slate-100");
    expect(severityColorClass("")).toContain("bg-slate-100");
  });
});

describe("severityRank", () => {
  it("CRITICAL < WARNING < WATCH < 기타 순서", () => {
    expect(severityRank("CRITICAL")).toBeLessThan(severityRank("WARNING"));
    expect(severityRank("WARNING")).toBeLessThan(severityRank("WATCH"));
    expect(severityRank("WATCH")).toBeLessThan(severityRank("UNKNOWN"));
  });
});

describe("sortAlertsBySeverity", () => {
  it("심각도 높은 순, 동순위는 surge_ratio 높은 순", () => {
    const alerts = [
      { severity: "WATCH", surge_ratio: 1.2 },
      { severity: "CRITICAL", surge_ratio: 3.0 },
      { severity: "WARNING", surge_ratio: 5.0 },
      { severity: "CRITICAL", surge_ratio: 4.2 },
    ];
    const ordered = sortAlertsBySeverity(alerts).map((a) => `${a.severity}:${a.surge_ratio}`);
    expect(ordered).toEqual(["CRITICAL:4.2", "CRITICAL:3", "WARNING:5", "WATCH:1.2"]);
  });

  it("원본 배열을 변경하지 않는다", () => {
    const alerts = [
      { severity: "WATCH", surge_ratio: 1 },
      { severity: "CRITICAL", surge_ratio: 2 },
    ];
    const copy = [...alerts];
    sortAlertsBySeverity(alerts);
    expect(alerts).toEqual(copy);
  });
});

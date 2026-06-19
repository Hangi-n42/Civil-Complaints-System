import { describe, it, expect } from "vitest";
import {
  priorityColorClass,
  priorityRank,
  sortInsightsByPriority,
  groupActionsByHorizon,
  labeledCount,
} from "../components/intelligence/insight";

describe("priorityColorClass", () => {
  it("color를 뱃지 클래스로 매핑(blue 포함)", () => {
    expect(priorityColorClass("red")).toContain("bg-red-100");
    expect(priorityColorClass("amber")).toContain("bg-amber-100");
    expect(priorityColorClass("blue")).toContain("bg-blue-100");
    expect(priorityColorClass("gray")).toContain("bg-slate-100");
  });

  it("알 수 없는 color는 slate 폴백", () => {
    expect(priorityColorClass("teal")).toContain("bg-slate-100");
  });
});

describe("priorityRank / sortInsightsByPriority", () => {
  it("CRITICAL > HIGH > MEDIUM > LOW 순서", () => {
    expect(priorityRank("CRITICAL")).toBeLessThan(priorityRank("HIGH"));
    expect(priorityRank("HIGH")).toBeLessThan(priorityRank("MEDIUM"));
    expect(priorityRank("MEDIUM")).toBeLessThan(priorityRank("LOW"));
  });

  it("우선순위 높은 순 정렬 + 원본 불변", () => {
    const insights = [{ priority: "LOW" }, { priority: "CRITICAL" }, { priority: "MEDIUM" }];
    const copy = [...insights];
    expect(sortInsightsByPriority(insights).map((i) => i.priority)).toEqual(["CRITICAL", "MEDIUM", "LOW"]);
    expect(insights).toEqual(copy);
  });
});

describe("groupActionsByHorizon", () => {
  it("정의된 순서(즉시/단기/중기/장기)로 비어있지 않은 그룹만", () => {
    const actions = [
      { horizon: "LONG_TERM", action: "a" },
      { horizon: "IMMEDIATE", action: "b" },
      { horizon: "IMMEDIATE", action: "c" },
    ];
    const groups = groupActionsByHorizon(actions);
    expect(groups.map((g) => g.label)).toEqual(["즉시", "장기"]);
    expect(groups[0].actions.map((a) => a.action)).toEqual(["b", "c"]);
  });

  it("알 수 없는 horizon은 '기타' 그룹으로 마지막에", () => {
    const groups = groupActionsByHorizon([{ horizon: "WHENEVER", action: "x" }]);
    expect(groups.map((g) => g.label)).toEqual(["기타"]);
  });
});

describe("labeledCount", () => {
  it("라벨키와 count를 안전 추출", () => {
    expect(labeledCount({ aspect: "소음", count: 5 }, "aspect")).toEqual({ label: "소음", count: 5 });
    expect(labeledCount({ request: "점검", count: 3 }, "request")).toEqual({ label: "점검", count: 3 });
  });

  it("값이 비정상이면 빈 라벨/0으로 폴백", () => {
    expect(labeledCount({}, "aspect")).toEqual({ label: "", count: 0 });
    expect(labeledCount({ aspect: 123, count: "x" }, "aspect")).toEqual({ label: "", count: 0 });
  });
});

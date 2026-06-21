import { describe, expect, it } from "vitest";
import { mergeCaseStatusOverrides, processedCaseCount } from "../lib/caseStatus";

describe("case status helpers", () => {
  it("기존 상태를 보존하면서 선택한 민원만 처리완료로 합친다", () => {
    expect(
      mergeCaseStatusOverrides(
        {
          "CASE-1": "검토중",
          "CASE-2": "잘못된상태",
        },
        ["CASE-3", "CASE-3", " "],
        "처리완료",
      ),
    ).toEqual({
      "CASE-1": "검토중",
      "CASE-3": "처리완료",
    });
  });

  it("중복된 민원 ID를 하나로 보고 처리완료 건수를 센다", () => {
    expect(
      processedCaseCount(["CASE-1", "CASE-1", "CASE-2", "CASE-3"], {
        "CASE-1": "처리완료",
        "CASE-2": "검토중",
        "CASE-3": "처리완료",
      }),
    ).toBe(2);
  });
});

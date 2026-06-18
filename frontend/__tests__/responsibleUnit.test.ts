import { describe, it, expect } from "vitest";
import {
  confidenceBand,
  firstEvidence,
  validResponsibleUnits,
  reviewAssignment,
  buildTransferMemo,
} from "../lib/responsibleUnit";

describe("confidenceBand", () => {
  it("0.6 이상은 높음(level 3)", () => {
    expect(confidenceBand(0.8548)).toEqual({ label: "높음", level: 3 });
    expect(confidenceBand(0.6)).toEqual({ label: "높음", level: 3 });
  });

  it("0.3~0.6 미만은 보통(level 2)", () => {
    expect(confidenceBand(0.4)).toEqual({ label: "보통", level: 2 });
    expect(confidenceBand(0.3)).toEqual({ label: "보통", level: 2 });
    expect(confidenceBand(0.5999)).toEqual({ label: "보통", level: 2 });
  });

  it("0.3 미만은 낮음(level 1)", () => {
    expect(confidenceBand(0.217)).toEqual({ label: "낮음", level: 1 });
    expect(confidenceBand(0)).toEqual({ label: "낮음", level: 1 });
  });

  it("값이 없거나 비정상이면 낮음으로 폴백", () => {
    expect(confidenceBand(undefined)).toEqual({ label: "낮음", level: 1 });
    expect(confidenceBand(NaN)).toEqual({ label: "낮음", level: 1 });
  });
});

describe("firstEvidence", () => {
  it("첫 번째 비어있지 않은 근거를 trim해서 반환", () => {
    expect(firstEvidence({ name: "도로안전과", evidence: ["  교량 보도육교 ", "단속"] })).toBe("교량 보도육교");
  });

  it("근거가 없으면 빈 문자열", () => {
    expect(firstEvidence({ name: "도로안전과" })).toBe("");
    expect(firstEvidence(undefined)).toBe("");
    expect(firstEvidence({ name: "x", evidence: ["", "  "] })).toBe("");
  });
});

describe("validResponsibleUnits", () => {
  it("이름이 있는 후보만 남긴다", () => {
    const units = [
      { name: "공원여가정책과", confidence: 0.85 },
      { name: "", confidence: 0.1 },
      { name: "  ", confidence: 0.0 },
    ];
    expect(validResponsibleUnits(units).map((u) => u.name)).toEqual(["공원여가정책과"]);
  });

  it("배열이 아니면 빈 배열", () => {
    expect(validResponsibleUnits(undefined)).toEqual([]);
  });
});

describe("reviewAssignment", () => {
  const units = [{ name: "공원여가정책과", confidence: 0.85 }];

  it("배정명과 추천명이 (공백 무시) 같으면 match", () => {
    expect(reviewAssignment("공원여가정책과", units)).toEqual({
      status: "match",
      current: "공원여가정책과",
      suggested: "공원여가정책과",
    });
  });

  it("배정명과 추천명이 다르면 differ", () => {
    expect(reviewAssignment("공원녹지과", units)).toEqual({
      status: "differ",
      current: "공원녹지과",
      suggested: "공원여가정책과",
    });
  });

  it("배정이 비었거나 미지정이면 unassigned", () => {
    expect(reviewAssignment("미지정", units)).toEqual({ status: "unassigned", suggested: "공원여가정책과" });
    expect(reviewAssignment("", units)).toEqual({ status: "unassigned", suggested: "공원여가정책과" });
  });

  it("추천이 없으면 none", () => {
    expect(reviewAssignment("공원녹지과", [])).toEqual({ status: "none" });
  });
});

describe("buildTransferMemo", () => {
  it("수신/발신/요지/근거를 포함한 이관 전달문을 만든다", () => {
    const memo = buildTransferMemo({
      recommended: "공원여가정책과",
      currentUnit: "공원녹지과",
      caseTitle: "근린공원 야간 조명 고장",
      observation: "야간 조명 다수 소등",
      request: "조속한 수리 요청",
      confidenceLabel: "높음",
      evidence: "근린공원 시설",
    });
    expect(memo).toContain("수신: 공원여가정책과 (귀 부서)");
    expect(memo).toContain("발신: 공원녹지과");
    expect(memo).toContain("「공원여가정책과」 소관");
    expect(memo).toContain("근린공원 야간 조명 고장");
    expect(memo).toContain("4. 판단 근거: 근린공원 시설");
    expect(memo).toContain("신뢰도 높음");
  });

  it("근거가 없으면 근거 줄을 생략한다", () => {
    const memo = buildTransferMemo({ recommended: "도로안전과" });
    expect(memo).not.toContain("판단 근거");
    expect(memo).toContain("발신: 미지정");
  });
});

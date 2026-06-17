import { describe, it, expect } from "vitest";
import {
  buildDraftTextareaValue,
  computeSegmentViewMode,
  pairSegmentsWithActions,
  DRAFT_ERROR_FALLBACK,
} from "../lib/draft";
import fixturesJson from "./fixtures/qa_demo_fixtures.json";

// 이슈 #388: 공식 회신문 편집창에서 structured_output 메타데이터 분리.
// 픽스처는 실제 데모 민원 + 백엔드 실제 분해 규칙(_derive_request_segments)으로 생성된다.
// 재생성: python frontend/__tests__/fixtures/build_fixtures.py

type FixtureCase = {
  complaintId: string;
  answer: string;
  structuredOutput: { summary: string; actionItems: string[]; requestSegments: string[] };
  _meta: { n_segments: number; mode: "multi" | "single" | "empty" };
};

const fixtures = fixturesJson as unknown as { cases: FixtureCase[]; empty: FixtureCase };

const allCases = fixtures.cases;
const emptyCase = fixtures.empty;
const labeledCases = allCases.map((c) => ({ ...c, mode: c._meta.mode }));
const multiCases = allCases.filter((c) => c._meta.mode === "multi");
const singleCases = allCases.filter((c) => c._meta.mode === "single");

// FE가 과거에 본문 앞에 붙이던 합성 메타 문구들 — textarea에 더 이상 나타나선 안 된다.
const META_MARKERS = ["[복합 요청 모드]", "[단일 요청 모드]", "세그먼트:", "· Action:", "조치 항목:"];

describe("실데이터 픽스처 sanity", () => {
  it("복합/단일/빈 케이스가 모두 존재한다 (AC4)", () => {
    expect(multiCases.length).toBeGreaterThan(0);
    expect(singleCases.length).toBeGreaterThan(0);
    expect(emptyCase.structuredOutput.requestSegments.length).toBe(0);
  });
});

describe("buildDraftTextareaValue — 회신문 textarea에는 answer만 (AC1/AC3)", () => {
  it.each(labeledCases)("[$mode] $complaintId: textarea 값이 data.answer와 정확히 일치", (c) => {
    expect(buildDraftTextareaValue({ draftStage: "success", answer: c.answer })).toBe(c.answer);
  });

  it.each(labeledCases)("[$mode] $complaintId: 합성 메타 문구가 본문에 섞이지 않는다", (c) => {
    const value = buildDraftTextareaValue({ draftStage: "success", answer: c.answer });
    for (const marker of META_MARKERS) {
      // 원래 answer에 없던 메타 문구가 새로 추가되지 않았는지 확인
      expect(value.includes(marker)).toBe(c.answer.includes(marker));
    }
  });

  it("복합 케이스(segment>=2)에서도 Segment/Action 표식이 본문에 없다", () => {
    const c = multiCases[0];
    const value = buildDraftTextareaValue({ draftStage: "success", answer: c.answer });
    expect(value).toBe(c.answer);
    expect(value).not.toContain("Segment 1");
    expect(value).not.toContain("· Action:");
    expect(value).not.toContain("[복합 요청 모드]");
  });

  it("빈 segment 케이스도 answer만 반환 (AC4)", () => {
    expect(buildDraftTextareaValue({ draftStage: "success", answer: emptyCase.answer })).toBe(emptyCase.answer);
  });

  it("loading 단계는 빈 문자열, error 단계는 answer 또는 폴백", () => {
    expect(buildDraftTextareaValue({ draftStage: "loading", answer: "x" })).toBe("");
    expect(buildDraftTextareaValue({ draftStage: "error", answer: "부분답변" })).toBe("부분답변");
    expect(buildDraftTextareaValue({ draftStage: "error", answer: undefined })).toBe(DRAFT_ERROR_FALLBACK);
  });
});

describe("computeSegmentViewMode — 보조 UI 분기 (AC2/AC4)", () => {
  it("segment 개수와 단계에 따라 모드를 결정한다", () => {
    expect(computeSegmentViewMode({ draftStage: "success", segmentCount: 3 })).toBe("multi");
    expect(computeSegmentViewMode({ draftStage: "success", segmentCount: 1 })).toBe("single");
    expect(computeSegmentViewMode({ draftStage: "success", segmentCount: 0 })).toBe("empty");
    expect(computeSegmentViewMode({ draftStage: "loading", segmentCount: 3 })).toBe("loading");
    expect(computeSegmentViewMode({ draftStage: "error", segmentCount: 3 })).toBe("error");
    expect(computeSegmentViewMode({ draftStage: "idle", segmentCount: 3 })).toBe("empty");
  });

  it.each(multiCases)("실데이터 복합 케이스 $complaintId → multi", (c) => {
    expect(
      computeSegmentViewMode({ draftStage: "success", segmentCount: c.structuredOutput.requestSegments.length }),
    ).toBe("multi");
  });
});

describe("pairSegmentsWithActions — 세그먼트/조치 분리 표시용 (AC2)", () => {
  it("실데이터 복합 케이스: segment와 action을 순서대로 짝짓는다", () => {
    const c = multiCases[0];
    const pairs = pairSegmentsWithActions(c.structuredOutput.requestSegments, c.structuredOutput.actionItems);
    expect(pairs.length).toBe(c.structuredOutput.requestSegments.length);
    expect(pairs[0].text).toBe(c.structuredOutput.requestSegments[0]);
    expect(pairs[0].action).toBe(c.structuredOutput.actionItems[0]);
    expect(pairs[0].index).toBe(0);
  });

  it("action이 segment보다 적으면 나머지 action은 undefined", () => {
    const pairs = pairSegmentsWithActions(["a", "b"], ["x"]);
    expect(pairs[1].action).toBeUndefined();
  });
});

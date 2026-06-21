import { describe, it, expect } from "vitest";
import { normalizeSegmentAnswers, hashQuery, isDraftStale } from "../lib/draft";

// 이슈 #451: BE3(이슈 #450)의 structured_output.segment_answers를 FE가 요청별 답변·근거 카드로 소비한다.
// 입력은 백엔드 계약(app/api/routers/generation.py _normalize_segment_answers)을 그대로 본뜬다:
//   { segment_index:int, request_segment:str, answer:str, case_ids:str[], evidence_status:"grounded"|"no_evidence" }
const SEGMENT_NO_EVIDENCE_MESSAGE = "유사 선례 없음 — 담당부서 확인 필요";

// 복합 민원: 1번 요청은 근거 있음(grounded), 2번 요청은 근거 없음(no_evidence).
const backendSegmentAnswers = [
  {
    segment_index: 0,
    request_segment: "단체 사전 예매 가능 여부",
    answer: "단체 사전 예매는 콜센터를 통해 신청하실 수 있습니다.",
    case_ids: ["CASE-1001", "CASE-1002"],
    evidence_status: "grounded",
  },
  {
    segment_index: 1,
    request_segment: "주차 요금 감면 대상",
    answer: SEGMENT_NO_EVIDENCE_MESSAGE,
    case_ids: [],
    evidence_status: "no_evidence",
  },
];

describe("normalizeSegmentAnswers — BE3 segment_answers 계약 소비 (AC: 요청별 답변·근거 분리)", () => {
  it("grounded/no_evidence 요청을 순서대로 카드로 변환한다", () => {
    const cards = normalizeSegmentAnswers(backendSegmentAnswers);
    expect(cards.length).toBe(2);
    expect(cards[0]).toEqual({
      index: 0,
      requestSegment: "단체 사전 예매 가능 여부",
      answer: "단체 사전 예매는 콜센터를 통해 신청하실 수 있습니다.",
      caseIds: ["CASE-1001", "CASE-1002"],
      hasEvidence: true,
    });
  });

  it("근거 없는 요청은 hasEvidence=false (→ '선례 없음' 배지)", () => {
    const cards = normalizeSegmentAnswers(backendSegmentAnswers);
    expect(cards[1].hasEvidence).toBe(false);
    expect(cards[1].caseIds).toEqual([]);
    expect(cards[1].answer).toBe(SEGMENT_NO_EVIDENCE_MESSAGE);
  });

  it("evidence_status가 누락돼도 case_id가 있으면 근거 있음으로 본다", () => {
    const cards = normalizeSegmentAnswers([
      { segment_index: 0, request_segment: "x", answer: "a", case_ids: ["C-1"] },
    ]);
    expect(cards[0].hasEvidence).toBe(true);
  });

  it("case_ids의 공백/빈 값은 제거한다", () => {
    const cards = normalizeSegmentAnswers([
      { segment_index: 0, request_segment: "x", answer: "a", case_ids: [" C-1 ", "", null], evidence_status: "grounded" },
    ]);
    expect(cards[0].caseIds).toEqual(["C-1"]);
  });

  it("배열이 아니거나(구버전 응답) 비면 빈 배열 → 평면 answer 폴백", () => {
    expect(normalizeSegmentAnswers(undefined)).toEqual([]);
    expect(normalizeSegmentAnswers(null)).toEqual([]);
    expect(normalizeSegmentAnswers({})).toEqual([]);
    expect(normalizeSegmentAnswers([])).toEqual([]);
  });

  it("segment_index가 없거나 answer가 빈 항목은 건너뛴다", () => {
    const cards = normalizeSegmentAnswers([
      { request_segment: "no index", answer: "a", case_ids: [] },
      { segment_index: 1, request_segment: "empty answer", answer: "   ", case_ids: [] },
      { segment_index: 2, request_segment: "ok", answer: "valid", case_ids: [], evidence_status: "no_evidence" },
    ]);
    expect(cards.length).toBe(1);
    expect(cards[0].index).toBe(2);
  });
});

describe("hashQuery / isDraftStale — 오래된 검색 결과 방어 (선택)", () => {
  it("같은 쿼리는(공백 정규화 포함) 같은 해시, 다른 쿼리는 다른 해시", () => {
    expect(hashQuery("주차 요금  감면")).toBe(hashQuery(" 주차 요금 감면 "));
    expect(hashQuery("주차 요금 감면")).not.toBe(hashQuery("단체 예매 절차"));
  });

  it("빈 쿼리는 빈 해시 → 비교에서 제외된다", () => {
    expect(hashQuery("")).toBe("");
    expect(hashQuery("   ")).toBe("");
  });

  it("초안 쿼리와 화면 검색 쿼리가 다르면 stale", () => {
    const draftQueryHash = hashQuery("단체 예매 절차");
    const searchQueryHash = hashQuery("주차 요금 감면");
    expect(isDraftStale({ draftQueryHash, searchQueryHash })).toBe(true);
  });

  it("같은 쿼리면 stale 아님", () => {
    const h = hashQuery("단체 예매 절차");
    expect(isDraftStale({ draftQueryHash: h, searchQueryHash: h })).toBe(false);
  });

  it("한쪽 해시가 비어 있으면(검색 전/복원 직후) 판단 보류 → not stale", () => {
    expect(isDraftStale({ draftQueryHash: null, searchQueryHash: hashQuery("a") })).toBe(false);
    expect(isDraftStale({ draftQueryHash: hashQuery("a"), searchQueryHash: "" })).toBe(false);
  });
});

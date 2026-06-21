import { describe, expect, it } from "vitest";
import {
  canCreateDraftReply,
  duplicateBadgeForCase,
  duplicateGroupTitle,
  duplicateStatusLabel,
  evidenceLabel,
  representativeReasonLabel,
  riskFlagLabel,
} from "../components/intelligence/duplicateMerge";
import type { DuplicateMergeRecord } from "../lib/api";

function group(overrides: Partial<DuplicateMergeRecord>): DuplicateMergeRecord {
  return {
    merge_id: "dup-test",
    status: "candidate",
    representative_complaint_id: "dm-risk-parking-02",
    member_complaint_ids: ["dm-risk-parking-01", "dm-risk-parking-02"],
    confidence: 0.82,
    recommendation_level: "review",
    recommended_decision: "REVIEW_BEFORE_MERGE",
    evidence: [],
    risk_flags: [],
    allowed_actions: ["confirm", "split", "reject"],
    blocked_actions: ["draft_reply"],
    linked_issue_alert_ids: [],
    linked_public_insight_ids: [],
    representative: {
      complaint_id: "dm-risk-parking-02",
      selection_reason: "4요소 구조화 정보가 풍부함, 위치/시설 신호가 명확함, 요구사항이 구체적임, PII 노출 위험이 낮음",
      quality_score: 0.8,
    },
    score_breakdown: {},
    location_state: "exact",
    request_types: {},
    created_at: "2026-06-20T00:00:00Z",
    updated_at: "2026-06-20T00:00:00Z",
    ...overrides,
  };
}

describe("duplicate merge display helpers", () => {
  it("candidate와 confirmed를 담당자용 문구로 구분한다", () => {
    expect(duplicateStatusLabel("candidate")).toBe("추천 후보");
    expect(duplicateStatusLabel("confirmed")).toBe("담당자 확정 그룹");
  });

  it("답변 초안 자료는 확정 상태와 허용 작업이 모두 맞아야 가능하다", () => {
    expect(canCreateDraftReply(group({ status: "candidate" }))).toBe(false);
    expect(canCreateDraftReply(group({ status: "confirmed", allowed_actions: ["draft_reply", "split"] }))).toBe(true);
    expect(canCreateDraftReply(group({ status: "confirmed", allowed_actions: ["split"] }))).toBe(false);
  });

  it("risk flag 코드를 업무 언어로 바꾼다", () => {
    expect(riskFlagLabel({ code: "REQUEST_TYPE_MISMATCH", severity: "warning", message: "", affected_case_ids: [], evidence: [] }))
      .toBe("요청 유형 혼합");
    expect(riskFlagLabel({ code: "LEGAL_RIGHTS_OR_DEADLINE_RISK", severity: "blocker", message: "", affected_case_ids: [], evidence: [] }))
      .toBe("권리관계·처리기한 주의");
  });

  it("중복 그룹 제목은 내부 merge id가 아니라 사건 중심으로 표시한다", () => {
    expect(duplicateGroupTitle(group({ merge_id: "dup-0bea82b603ae" }))).toBe("새빛초 후문 불법 주정차 관련 민원");
  });

  it("대표 민원 이유에서 내부 개인정보 용어를 그대로 노출하지 않는다", () => {
    const label = representativeReasonLabel(group({}));
    expect(label).toContain("장소와 요청 내용");
    expect(label).not.toContain("PII");
  });

  it("병합 근거에서 내부 분석 용어를 담당자용 문장으로 바꾼다", () => {
    const semantic = evidenceLabel({
      type: "semantic_similarity",
      message: "PII-safe 분석 텍스트 간 의미 유사도입니다.",
      affected_case_ids: [],
      value: 0.92,
    });
    const location = evidenceLabel({
      type: "location_state",
      message: "장소 신호는 exact 상태입니다.",
      affected_case_ids: [],
      value: "exact",
    });

    expect(semantic).toBe("민원 요약과 요청 내용이 서로 유사합니다.");
    expect(location).toBe("장소와 시설 신호가 일치합니다.");
    expect(`${semantic} ${location}`).not.toContain("PII-safe");
    expect(`${semantic} ${location}`).not.toContain("exact");
  });

  it("메인 민원 목록 배지는 confirmed를 우선 표시한다", () => {
    const badge = duplicateBadgeForCase("dm-risk-parking-01", [
      group({ status: "candidate" }),
      group({ merge_id: "dup-confirmed", status: "confirmed", allowed_actions: ["split", "draft_reply"] }),
    ]);

    expect(badge?.label).toBe("확정 그룹");
  });
});

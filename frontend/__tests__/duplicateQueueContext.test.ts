import { describe, expect, it } from "vitest";
import { duplicateQueueContextLabel } from "../components/intelligence/duplicateMerge";
import type { DuplicateMergeRecord } from "../lib/api";

function group(overrides: Partial<DuplicateMergeRecord>): DuplicateMergeRecord {
  return {
    merge_id: "dup-test",
    status: "candidate",
    representative_complaint_id: "case-1",
    member_complaint_ids: ["case-1", "case-2"],
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
      complaint_id: "case-1",
      selection_reason: "구조화 정보가 충분합니다.",
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

describe("duplicate merge queue context helpers", () => {
  it("핫스팟 연결 그룹과 일반 큐 그룹을 구분한다", () => {
    expect(duplicateQueueContextLabel(group({ linked_issue_alert_ids: ["issue-1"] })).label).toBe("핫스팟 연결 1건");
    expect(duplicateQueueContextLabel(group({ linked_issue_alert_ids: [] })).label).toBe("일반 검토");
  });
});

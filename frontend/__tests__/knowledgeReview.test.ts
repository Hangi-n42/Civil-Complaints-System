import { describe, expect, it } from "vitest";
import { bulkLabelChanges, canConvert, coverageRows, decisionBody, editPatch, evidenceSpan, groupChanges, makeDraft, readableRefs, simpleLabelChange, type Change, type Changeset, type DiscoveryRun } from "../lib/knowledgeReview";

function candidate(id = "change-1"): Change {
  const metadata = { evidence_refs: [{ evidence_id: "e1", block_id: "e1", source_version_id: "v1", parse_run_id: "p1", span: [0,2], quote: "원문", locator: {} }], counter_evidence_refs: [], qualifiers: { scope: "현재 업무", time: "", negation: "unknown", statement_type: "design_proposal" }, cq_ids: ["cq1"], scope_item_ids: [], support_type: "design_proposal", hierarchy_review: {} };
  return { id, change_id: id, target_id: `target-${id}`, symbol: `T${id}`, target_kind: "class", operation: "update", before: { kind: "class", name: "기존 명칭", definition: "정의", ...metadata }, after: { name: "표기 수정", definition: "정의" }, ...metadata, rationale: "표기 수정", unresolved_issues: [], origin: {}, review_status: "unreviewed", dependency_ids: [], affected_reference_ids: [], affected_references: [], can_accept: true, validation: { structural_errors: [], semantic_review: [], unresolved_dependency_ids: [] } };
}
function changeset(c = candidate()): Changeset {
  return { id: "cs", revision: 7, run_id: "run", input_status: "partial", base_ontology_version_id: null, ontology_head_id: null, reviewed_ontology_version_id: null, unresolved_count: 1, candidates: [c], decisions: [], analysis_result: {}, reference_material: [] };
}

describe("A4 검수 계약", () => {
  it("A5 직접 의존 처리는 명시한 수락에만 보내고 편집·보류에는 넣지 않는다", () => {
    const c = candidate(), draft = makeDraft(c);
    for (const action of ["accept", "modify"]) {
      expect(decisionBody(changeset(c), "검토자", "직접 영향 보류", action, [c.id], draft, true).decisions[0].consumer_action).toBe("review_required");
      expect(decisionBody(changeset(c), "검토자", "일반 결정", action, [c.id], draft).decisions[0]).not.toHaveProperty("consumer_action");
    }
    expect(decisionBody(changeset(c), "검토자", "편집", "edit", [c.id], draft, true).decisions[0]).not.toHaveProperty("consumer_action");
  });
  it("서버와 같은 코드포인트 구간으로 비 BMP 문자 전후를 강조한다", () => {
    expect(evidenceSpan("😀 국민임대", [2,6])).toEqual({ before: "😀 ", quote: "국민임대", after: "" });
    expect(evidenceSpan("앞😀뒤", [1,2])).toEqual({ before: "앞", quote: "😀", after: "뒤" });
  });
  it("종료된 저장 산출물만 명시적으로 변환하고 partial/실패/취소를 숨기지 않는다", () => {
    for (const status of ["partial","failed","cancelled","review_ready"]) expect(canConvert({ status, has_result: true })).toBe(true);
    for (const status of ["running","queued","succeeded"]) expect(canConvert({ status, has_result: true })).toBe(false);
    expect(canConvert({ status: "failed", has_result: false })).toBe(false);
  });
  it("수정 요청은 ID·원문 버전을 유지하고 명시적인 revision과 null head를 보낸다", () => {
    const c = candidate(), draft = makeDraft(c);
    draft.after = JSON.stringify({ ...c.after, name: "사람이 바꾼 표기" });
    const body = decisionBody(changeset(c), "검토자", "원문 대조", "edit", [c.id], draft);
    expect(body.expected_changeset_revision).toBe(7); expect(body).toHaveProperty("expected_ontology_head_id", null);
    const patch = body.decisions[0].patch!;
    expect(patch).not.toHaveProperty("target_id"); expect(patch).not.toHaveProperty("symbol"); expect(patch).not.toHaveProperty("origin");
    expect(patch.evidence_refs).toEqual(c.evidence_refs); expect(patch.after.name).toBe("사람이 바꾼 표기");
    expect(c.after.name).toBe("표기 수정");
  });
  it("JSON 문법 오류나 빈 사유를 빈 성공/자동 보정으로 보내지 않는다", () => {
    const draft = makeDraft(candidate()); draft.after = "{";
    expect(() => editPatch(draft)).toThrow();
    expect(() => decisionBody(changeset(), "검토자", " ", "accept", ["change-1"])).toThrow();
  });
  it("보류·기각과 can_accept=false도 edit 경로로 재검토할 수 있다", () => {
    for (const status of ["deferred","rejected"]) {
      const c = { ...candidate(), review_status: status, can_accept: false };
      expect(decisionBody(changeset(c), "검토자", "추가 근거 확인", "edit", [c.id], makeDraft(c)).decisions[0].action).toBe("edit");
    }
  });
  it("반복 표기는 서로 다른 후보·근거·상태를 그대로 보존한 표시 묶음이다", () => {
    const a = candidate(), b = { ...candidate("second"), review_status: "deferred" };
    const groups = groupChanges([a,b]); expect(groups).toEqual([[a,b]]);
    expect(a.target_id).not.toBe(b.target_id); expect(b.review_status).toBe("deferred");
    expect(groupChanges([{ ...a, after: {}, before: null },{ ...b, after: {}, before: null }])).toHaveLength(2);
  });
  it("같은 영향 범위의 근거가 같은 표기 수정만 일괄 수락 대상이다", () => {
    const a = candidate(), b = candidate("second");
    expect(simpleLabelChange(a)).toBe(true); expect(bulkLabelChanges([a,b],[a.id,b.id])).toHaveLength(2);
    for (const patch of [{ operation: "merge" }, { operation: "deprecate" }, { operation: "add" }, { target_kind: "hierarchy" },
      { qualifiers: { scope: "다른 범위" } }, { can_accept: false }, { counter_evidence_refs: a.evidence_refs }, { unresolved_issues: ["충돌 검토"] },
      { after: { ...a.after, definition: "의미 변경" } }]) expect(simpleLabelChange({ ...a,...patch })).toBe(false);
    expect(bulkLabelChanges([a,{ ...b, affected_reference_ids: ["new-impact"] }],[a.id,b.id])).toEqual([]);
    expect(bulkLabelChanges([a,b],[a.id,b.id,"missing"])).toEqual([]);
  });
  it("CQ 연결을 해결 판정으로 만들지 않고 미기록 상태와 보류를 구분한다", () => {
    const c = { ...candidate(), review_status: "deferred" }, change = changeset(c);
    change.analysis_result.coverage = [{ kind: "cq", id: "cq1", status: "evidence_linked", reason: "의미 해결 미검증" }];
    const run = { cqs: [{ id: "cq1", question: "어떤 유형인가?" },{ id: "cq2", question: "예외는 무엇인가?" }], scope_items: [] } as unknown as DiscoveryRun;
    const rows = coverageRows(run,change);
    expect(rows[0].status).toBe("생성 당시 근거 연결"); expect(rows[0].deferred).toBe(1);
    expect(rows[1].status).toBe("범위별 조사 상태 미기록"); expect(rows[1].candidates).toEqual([]);
  });
  it("잘못된 근거는 조회 가능한 근거로 꾸미지 않고 원본 편집 입력에 보존한다", () => {
    const c = candidate(); expect(readableRefs(c.evidence_refs)).toEqual(c.evidence_refs);
    expect(readableRefs([null,{}, { ...c.evidence_refs[0], span: 42 }])).toEqual([]);
    const malformed = { ...c, evidence_refs: [null] } as unknown as Change;
    expect(makeDraft(malformed).evidence_refs).toBe("[\n  null\n]");
  });
});

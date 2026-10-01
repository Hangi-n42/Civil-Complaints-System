import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import KnowledgeDiscoveryReview from "../components/KnowledgeDiscoveryReview";
import { makeDraft, type Change, type Changeset, type DiscoveryRun, type EditDraft, type Ontology } from "../lib/knowledgeReview";

const state = vi.hoisted(() => ({ values: [] as unknown[] }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useState: () => [state.values.shift(), vi.fn()], useEffect: vi.fn() }));
vi.mock("@/lib/knowledgeReview", () => import("../lib/knowledgeReview"));
vi.mock("../components/KnowledgeReviewEvidence", () => ({ default: () => null }));
vi.mock("../components/KnowledgeHumanCost", () => ({ default: () => null }));
vi.mock("../components/KnowledgeDiscoveryStart", () => ({ default: () => null }));
vi.mock("../components/KnowledgeMissingProposal", () => ({ default: () => null }));

function candidate(): Change {
  return { id: "change", change_id: "change", target_id: "alias", symbol: "Alias", target_kind: "alias", operation: "add",
    before: null, after: { name: "별칭", alias_of: "LegacyType" }, qualifiers: {}, support_type: "design_proposal", rationale: "검수",
    evidence_refs: [], counter_evidence_refs: [], cq_ids: [], scope_item_ids: [], unresolved_issues: [], hierarchy_review: {}, origin: {},
    review_status: "unreviewed", dependency_ids: [], affected_reference_ids: [], affected_references: [], can_accept: true,
    validation: { structural_errors: [], semantic_review: [], unresolved_dependency_ids: [] } };
}

function render(c: Change, reviewed: Ontology, draft: EditDraft = makeDraft(c)) {
  const run: DiscoveryRun = { id: "run", status: "partial", cqs: [], scope_items: [], frozen_input: { scope: "current_discovery", step: 0, files: [] } };
  const change: Changeset = { id: "change", revision: 0, run_id: run.id, input_status: "partial", base_ontology_version_id: "base",
    ontology_head_id: "base", reviewed_ontology_version_id: null, unresolved_count: 1, candidates: [c], decisions: [], analysis_result: {}, reference_material: [] };
  // Seed the saved-run state; no network, effects or database mutations in this rendering check.
  state.values = [[], null, run, change, c.id, draft, { counter: false, index: 0 }, "tester", "", false, "", "", false, null, null, reviewed, []];
  const html = renderToStaticMarkup(createElement(KnowledgeDiscoveryReview, { request: async () => { throw Error("unexpected request"); } }));
  return html.split("의미·범위·예외를 어떻게 바꿉니까?")[1].split("반례·의존·영향에서 더 확인할 것은 무엇입니까?")[0];
}

describe("A4 실제 컴포넌트 비교 출력", () => {
  it("v1 candidates와 v2 targets의 이름을 별칭·관계·계층·병합에서 공통 조회한다", () => {
    for (const reviewed of [{ status: "reviewed", candidates: [{ id: "LegacyType", name: "기존기준유형" }] },
      { status: "reviewed", targets: [{ id: "LegacyType", name: "기존기준유형" }] }]) {
      for (const [after, text] of [
        [{ alias_of: "LegacyType" }, "다른 이름으로 연결할 대상: 기존기준유형"],
        [{ domain_id: "LegacyType", range: "LegacyType" }, "기존기준유형의 특성·관계 → 기존기준유형"],
        [{ child_id: "LegacyType", parent_id: "LegacyType", relation: "is_a" }, "기존기준유형 → 기존기준유형"],
        [{ canonical_id: "LegacyType" }, "같은 대상으로 통합할 대상: 기존기준유형"],
      ] as const) expect(render({ ...candidate(), after }, reviewed)).toContain(text);
    }
    const html = render(candidate(), { status: "reviewed", candidates: [{ id: "Other", name: "추정하면 안 되는 이름" }] });
    expect(html).toContain("다른 이름으로 연결할 대상: 연결 대상 확인 필요");
    expect(html).not.toContain("추정하면 안 되는 이름");
    expect(html).toContain("이전 항목 없음 · 신규 제안");
  });

  it("조건·시점·부정·진술 성격의 저장 전후와 미저장 편집을 구분한다", () => {
    const c = { ...candidate(), operation: "update", target_kind: "class",
      before: { name: "유형", qualifiers: { scope: "기존조건_2020년_입주자", time: "2020년", negation: "affirmed", statement_type: "definition" } },
      after: { name: "유형" }, qualifiers: { scope: "새조건_2026년_입주자", time: "2026년", negation: "negated", statement_type: "design_proposal" } };
    const draft = makeDraft(c); draft.qualifiers = JSON.stringify({ ...c.qualifiers, scope: "저장 전 편집 조건" });
    const html = render(c, { status: "reviewed", targets: [] }, draft);
    const before = html.split("변경 전</h4>")[1].split("변경안 · 저장된 값</h4>")[0];
    const after = html.split("변경안 · 저장된 값</h4>")[1].split("변경 이유:")[0];
    for (const text of ["기존조건_2020년_입주자", "2020년", "긍정 진술", "정의"]) expect(before).toContain(text);
    for (const text of ["새조건_2026년_입주자", "2026년", "부정 진술", "설계 제안"]) expect(after).toContain(text);
    expect(before).not.toContain("새조건_2026년_입주자");
    expect(after).not.toContain("저장 전 편집 조건");
    expect(html.split("검토자가 수정할 내용 · 아직 저장되지 않음")[1]).toContain("저장 전 편집 조건");
  });
});

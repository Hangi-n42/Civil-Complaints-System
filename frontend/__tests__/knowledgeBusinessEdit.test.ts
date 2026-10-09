import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { EventEditor, eventEditRequest, resumeBusinessRequest, reviewedQueryFields } from "../components/KnowledgeBusiness";

const event = { id: "event", role: "event_entity", statement: "기존 문장", raw: { Event: "기존 문장", Entity: ["기관"] },
  conditions: ["기존 조건"], evidence: [{ block_id: "body", quote: "원문 근거" }] };
const change = { id: "change", revision: 3, candidates: [event, { ...event, id: "relation", role: "entity_relation" }],
  eligible_ids: [], candidate_versions: { event: "content-version" } };

it("offers natural text editing with evidence and explicit unsupported/approval boundaries", () => {
  const html = renderToStaticMarkup(createElement(EventEditor, { change, busy: false, onSubmit: async () => {} }));
  expect(html).toContain("수정 문장 (조건 포함)");
  expect(html).toContain("연결된 대상 목록·관계형 주장·대체된 후보는 편집하지 않습니다");
  expect(html).toContain("수정은 승인이 아니며");
  expect(html).toContain("기존 조건");
  expect(html).toContain("원문 근거");
  expect(html).not.toContain('value="relation"');
  expect(html).not.toContain('name="raw"');
});

it("submits only the selected candidate, version, evidence and attributed text edit", () => {
  const form = new FormData();
  form.set("actor", "검사 운영자"); form.set("reason", "원문 대조"); form.set("event", "조건을 보존한 문장");
  form.append("evidence", "0");
  expect(eventEditRequest(change, event, form)).toEqual({ expected_revision: 3, expected_claim_version: "content-version",
    claim_id: "event", actor: "검사 운영자", reason: "원문 대조", event: "조건을 보존한 문장",
    evidence: [{ block_id: "body", quote: "원문 근거" }] });
});

it("continues edited text through stored-pool reassessment instead of extracting over it", () => {
  const run = { id: "edited-run", status: "partial", recipe: { options: { repair: true } }, units: [], assessments: [],
    repairs: [{ id: "edit", status: "recheck_incomplete", origin: "user", changes: [] }] };
  const request = resumeBusinessRequest(run, {});
  expect(request).toMatchObject({ reassess_run_id: "edited-run", resume_run_id: null, reuse_run_id: null, repair: false });
  expect(resumeBusinessRequest({ ...run, id: "next-run", repairs: [], recipe: { options: request } }, {}))
    .toMatchObject({ reassess_run_id: "next-run", resume_run_id: null, reuse_run_id: null, repair: false });
});

it("binds explicit source correction to the displayed version without inventing independence", () => {
  const source = { requirement_id: "r", version: "meaning-v1", meaning: { key: "m", statement: "이전 해석", conditions: [], exceptions: [], period: "", references: [], evidence: [{ block_id: "body", quote: "원문 근거" }] } };
  const form = new FormData();
  form.set("error_owner", "both"); form.set("source_meaning", "r:m"); form.set("source_mode", "replace");
  form.set("source_statement", "조건을 보존한 해석"); form.set("source_conditions", "조건 하나\n조건 둘");
  form.set("premise_state", "unknown"); form.append("evidence", "0");
  expect(eventEditRequest({ ...change, source_meanings: [source] }, event, form)).toMatchObject({ error_owner: "both", source_edits: [{
    expected_meaning_version: "meaning-v1", statement: "조건을 보존한 해석", conditions: ["조건 하나", "조건 둘"], premise_keys: null }] });
  form.set("source_mode", "reassess");
  expect(eventEditRequest({ ...change, source_meanings: [source] }, event, form).source_edits?.[0]).not.toHaveProperty("statement");
});

it("uses the public requirement wording for literal reviewed answers", () => {
  const form = new FormData(); form.set("answer_mode", "reviewed_items"); form.set("answer_requirement", "r");
  const requirement = { id: "r", question_ids: [], revision: 2, question: "어디서 처리하는가?", criterion: "서류와 범위 확인", target: "", situation: "", period: "", source_ids: [], required: true, status: "partial" };
  expect(reviewedQueryFields(form, [requirement])).toMatchObject({ answer_mode: "reviewed_items", requirement_ids: ["r"], answer_items: [
    { field: "question", request_quote: requirement.question, requirement_revision: 2 }, { field: "criterion", request_quote: requirement.criterion, requirement_revision: 2 }] });
});

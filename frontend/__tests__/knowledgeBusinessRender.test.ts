import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import KnowledgeBusiness, { CapacityRetrySettings, RepairChange, resumeBusinessRequest } from "../components/KnowledgeBusiness";
import replacement from "./fixtures/knowledgeBusinessReplacement.json";

it("offers public criteria and parsed source versions with explicit review and change controls", () => {
  const html = renderToStaticMarkup(createElement(KnowledgeBusiness, {
    request: async () => { throw Error("SSR must not execute a product call"); }, visible: false,
    sources: [{ source: { id: "source", title: "업무 안내" }, versions: [
      { id: "parsed-version", processing_status: "parsed" }, { id: "unparsed-version", processing_status: "registered" },
    ] }],
  }));
  for (const text of ["업무 질문", "대상", "상황", "기준 기간", "충족 기준", "업무 안내", "원문 변경 영향 확인", "검토한 지식에 질문"]) expect(html).toContain(text);
  expect(html).not.toContain("unparsed-version");
  expect(html).toContain('type="checkbox"');
  expect(html).toContain('disabled=""');
  expect(html).toContain('value="plain" selected=""');
  expect(html).toContain('value="hipporag2" selected=""');
  expect(html).toContain('개념·관계 연결 검색 (개발 기본)');
  expect(html).toContain('연결 구조 (선택 시험)');
});

it("only exposes capacity fields for failed stages and carries explicit changes into a new run", () => {
  const run = {
    id: "previous", status: "partial", recipe: { options: {
      source_tokens: 16384, review_tokens: 4096, context_tokens: 49152, representation_context_tokens: 65536,
      requirement_ids: ["same-requirement"], resume_run_id: "older", reuse_run_id: null,
    } },
    units: [{ id: "R", stage: "requirement_representation", status: "failed", error: "truncated" }],
    assessments: [], repairs: [],
  };
  const markup = (value = run) => renderToStaticMarkup(createElement(CapacityRetrySettings, {
    run: value, values: {}, onChange: () => {},
  }));
  const html = markup();
  expect(html).toContain('name="representation_tokens"');
  expect(html).toContain('value="4096"');
  expect(html).toContain('name="representation_context_tokens"');
  expect(html).toContain('value="65536"');
  expect(html).not.toContain('name="source_tokens"');
  const inputBlocked = markup({ ...run, units: [{ ...run.units[0], error: "input_capacity" }] });
  expect(inputBlocked).toContain('name="representation_context_tokens"');
  expect(inputBlocked).not.toContain('name="representation_tokens"');
  expect(html).toContain("같은 값으로 이어가면 동일한 원인이 남습니다");
  expect(markup({ ...run, status: "running" })).toBe("");
  expect(markup({ ...run, units: [{ ...run.units[0], error: "schema_error" }] })).toBe("");
  expect(markup({ ...run, units: [{ ...run.units[0], stage: "requirement_source", error: "truncated" }] })).toContain('name="source_tokens"');
  const options = resumeBusinessRequest(run, { representation_tokens: 16384, representation_context_tokens: 98304, source_tokens: 999 });
  expect(options).toMatchObject({ representation_tokens: 16384, representation_context_tokens: 98304,
    source_tokens: 16384, requirement_ids: ["same-requirement"], resume_run_id: "previous", reuse_run_id: null });
  expect(run.recipe.options.review_tokens).toBe(4096);
  expect(resumeBusinessRequest(run, {})).toMatchObject({ review_tokens: 4096, representation_context_tokens: 65536 });
});

it("shows the actual stored replacement instead of the superseded statement as the repair result", () => {
  const before = JSON.stringify(replacement);
  const { change, claims } = replacement;
  expect(change.after.statement).toBe(change.before.statement);
  const html = renderToStaticMarkup(createElement(RepairChange, { ...change, claims }));
  expect(html).toContain(`전: ${change.before.statement}`);
  expect(html).not.toContain(`후: ${change.after.statement}`);
  expect(html).toContain("후: 기존 후보로 대체");
  expect(html).toContain(claims[0].statement);
  expect(html).toContain(claims[0].evidence[0].quote);
  expect(JSON.stringify(replacement)).toBe(before);
});

it("keeps all replacement locations and reports an unavailable candidate without reviving the old claim", () => {
  const second = { id: "second", statement: "다른 대체 후보", evidence: [] };
  const claims = [...replacement.claims, second];
  const after = { ...replacement.change.after, superseded_by: [claims[0].id, "missing", second.id] };
  const html = renderToStaticMarkup(createElement(RepairChange, { ...replacement.change, after, claims }));
  expect(html).toContain(claims[0].statement);
  expect(html).toContain(second.statement);
  expect(html).toContain("대체 후보를 확인할 수 없습니다: missing");
  expect(html).not.toContain(`후: ${after.statement}`);
});

it("retains ordinary edits and recovered claims without treating them as replacements", () => {
  const after = { id: "edited", statement: "수정된 문장", evidence: [{ block_id: "b", quote: "수정 근거" }] };
  const html = renderToStaticMarkup(createElement(RepairChange, { before: replacement.change.before, after, claims: [] }));
  expect(html).toContain("후: 수정된 문장");
  expect(html).toContain("수정 근거");
  expect(html).not.toContain("기존 후보로 대체");
  const recovered = renderToStaticMarkup(createElement(RepairChange, { after, claims: [] }));
  expect(recovered).toContain("전: 표현 없음");
  expect(recovered).toContain("후: 수정된 문장");
});

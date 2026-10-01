import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import KnowledgeConsumer from "../components/KnowledgeConsumer";

const state = vi.hoisted(() => ({ values: [] as unknown[] }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useState: () => [state.values.shift(), vi.fn()], useEffect: vi.fn() }));

it("선택 버전의 새 ID 의미 대응과 부분 추출·보류·별도 활성화를 표시한다", () => {
  state.values = [{ contract: { ontology_version_id: "v2", review_id: null, target_ids: {} }, ontology_head_id: "v2", mapping_editable: true,
    mapping_roles: { ATTRIBUTE_003: { kind: "attribute", definition: "LH 원문 수량", inclusion: "원문 범위", exclusion: "현재 재고 추정 제외" } },
    definitions: [{ id: "new-slot", kind: "attribute", name: "주택 수량", definition: "새 정본 정의", required: true }, { id: "unsupported", kind: "attribute", name: "목록", unsupported_reason: "다중값 미지원" }],
    unresolved_profile_ids: ["ATTRIBUTE_003"], vocabulary_registry: { targets: {} } }, {}, "reviewer", "", "", false];
  const html = renderToStaticMarkup(createElement(KnowledgeConsumer, { id: "v2", request: async () => { throw Error("no request"); }, predicates: ["new-slot"], onPredicates: vi.fn() }));
  for (const text of ["새 사실을 검토", "활성화는 별도", "부분 추출", "최소 한 필드 선택", "주택 수량", "필수", "다중값 미지원", "의미 대응 검토", "보류 · 대응 없음", "현재 재고 추정 제외", "이 버전의 의미 대응 저장"]) expect(html).toContain(text);
  expect(html).toContain('value="new-slot"');
});

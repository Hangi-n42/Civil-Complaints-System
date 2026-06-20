import { afterEach, describe, expect, it, vi } from "vitest";
import { runQaApi } from "../lib/api";

describe("runQaApi — 복합 요청 세그먼트 전달", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("초안 생성 요청에 원본 민원의 requestSegments를 routing_trace로 보낸다", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          complaint_id: "NEW-2026-0001",
          answer: "답변 초안",
          structured_output: {
            summary: "브런치 콘서트 단체 예매 문의",
            action_items: [],
            request_segments: ["단체 예매 문의"],
          },
        },
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await runQaApi({
      complaintId: "NEW-2026-0001",
      query: "브런치 콘서트 단체 예매 절차 문의",
      routingHint: {
        topicType: "general",
        complexityLevel: "medium",
        strategy_id: "topic_general_medium_v1",
        route_key: "general/medium",
      },
      routingTrace: {
        topicType: "general",
        complexityLevel: "medium",
        complexityScore: 0.58,
        requestSegments: ["단체 예매 문의"],
        complexityTrace: {
          intent_count: 1,
          constraint_count: 1,
          entity_diversity: 1,
          policy_reference_count: 0,
          cross_sentence_dependency: false,
        },
        routeReason: "테스트 라우팅",
      },
      caseContext: {
        caseId: "NEW-2026-0001",
        category: "문화체육관광",
        summary: "브런치 콘서트 단체 예매 문의",
        requestSegments: ["단체 사전 예매 가능 여부", "예매 매수 제한", "콜센터 또는 현장 예매 가능 여부"],
      },
    });

    const [, init] = (fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>)[0];
    const body = JSON.parse(String(init?.body || "{}"));

    expect(body.routing_trace.request_segments).toEqual([
      "단체 사전 예매 가능 여부",
      "예매 매수 제한",
      "콜센터 또는 현장 예매 가능 여부",
    ]);
    expect(body.routing_trace.complexity_trace.intent_count).toBe(3);
    expect(response.data.structuredOutput?.requestSegments).toEqual([
      "단체 사전 예매 가능 여부",
      "예매 매수 제한",
      "콜센터 또는 현장 예매 가능 여부",
    ]);
  });
});

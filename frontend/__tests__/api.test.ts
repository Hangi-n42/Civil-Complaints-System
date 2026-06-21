import { afterEach, describe, expect, it, vi } from "vitest";
import { runQaApi, searchCasesApi } from "../lib/api";

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

describe("searchCasesApi — 유사민원 답변 표시 데이터", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("검색 결과의 과거 답변을 RetrievedDoc.answer로 보존한다", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          query: "가로등 고장",
          strategy_id: "topic_traffic_medium_v1",
          route_key: "traffic/medium",
          routing_hint: {
            strategy_id: "topic_traffic_medium_v1",
            route_key: "traffic/medium",
            top_k: 5,
            snippet_max_chars: 1100,
            chunk_policy: "balanced",
          },
          routing_trace: {
            topic_type: "traffic",
            complexity_level: "medium",
            complexity_score: 0.58,
            request_segments: ["가로등 수리 요청"],
            complexity_trace: {
              intent_count: 1,
              constraint_count: 1,
              entity_diversity: 1,
              policy_reference_count: 0,
              cross_sentence_dependency: false,
            },
            route_reason: "테스트",
          },
          results: [
            {
              doc_id: "DOC-1",
              case_id: "CASE-1",
              chunk_id: "CASE-1__chunk-0",
              title: "공영주차장 가로등 고장",
              snippet: "가로등 수리를 요청합니다.",
              answer: "현장 점검 후 고장 조명을 교체했습니다.",
              score: 0.91,
              summary: {
                observation: "공영주차장 가로등 고장",
                request: "가로등 수리 요청",
              },
              metadata: {
                created_at: "2026-06-10T09:00:00+09:00",
                category: "도로",
                region: "서울",
              },
            },
          ],
        },
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await searchCasesApi({
      complaintId: "NEW-1",
      query: "가로등 고장",
    });

    expect(response.error).toBeNull();
    expect(response.data.results[0].answer).toBe("현장 점검 후 고장 조명을 교체했습니다.");
    expect(response.data.results[0].summary?.request).toBe("가로등 수리 요청");
  });
});

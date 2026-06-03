import { mockAssignedCases, mockWorkbenchSimilarCases, type MockAssignedCase } from "./mockData";

export type TopicType = "general" | "welfare" | "traffic" | "environment" | "construction";

export type RoutingTrace = {
  topicType: TopicType;
  complexityLevel: "low" | "medium" | "high";
  complexityScore: number;
  complexityTrace: Record<string, number | boolean>;
  routeReason: string;
};

export type RoutingHint = {
  routeKey: string;
  strategyId: string;
  note: string;
};

export type WorkbenchCaseContext = {
  caseId: string;
  title: string;
  category: string;
  region: string;
  summary: string;
  priority: string;
};

export type RetrievedDoc = {
  rank: number;
  docId: string;
  caseId: string;
  case_id: string;
  title: string;
  received_at: string;
  snippet: string;
  similarity_score: number;
  score: number;
  chunkId: string;
  chunk_id: string;
  content: {
    observation: string;
    result: string;
    request: string;
    context: string;
  };
  metadata: {
    created_at: string | null;
    category: string | null;
    region: string | null;
    entity_labels: string[];
    strategy_id?: string | null;
    route_key?: string | null;
    topic_type?: string | null;
    retrieval_policy?: string | null;
    matched_segments?: string[];
  };
  summary: {
    observation: string;
    request: string;
  };
  answers_by_admin_unit: Record<string, string>;
  department_answers: Record<string, string>;
};

export type SearchResponseData = {
  query: string;
  results: RetrievedDoc[];
  retrievedDocs: RetrievedDoc[];
  searchResults: RetrievedDoc[];
  routingTrace: RoutingTrace;
  routingHint: RoutingHint;
  strategyId: string;
  routeKey: string;
  totalFound: number;
  elapsedMs: number;
};

export type QaResponseData = {
  complaintId: string;
  answer: string;
  citations: Array<{
    ref_id: number;
    doc_id?: string;
    chunk_id: string;
    case_id: string;
    snippet: string;
    relevance_score?: number;
    source?: string;
  }>;
  limitations: string[];
  meta: {
    processing_time: number;
    model: string;
    validation_warning: string;
  };
  qa_validation: {
    is_valid: boolean;
    errors: Array<{ code: string; message: string }>;
    warnings: Array<{ code: string; message: string }>;
  };
  structuredOutput: {
    summary: string;
    actionItems: string[];
    requestSegments: string[];
  };
};

export type StatusUxType = "idle" | "loading" | "success" | "error" | "error_fallback";

export type AssignedCase = MockAssignedCase;

export type UiCasesResponseData = {
  count: number;
  cases: AssignedCase[];
};

type ApiErrorPayload = {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
};

type ApiResponse<T> = { data: T; error: ApiErrorPayload | null };

type ApiErrorEnvelope = {
  message?: string;
  code?: string;
  details?: Record<string, unknown>;
  retryable?: boolean;
};

type ApiEnvelope<T> = {
  success?: boolean;
  request_id?: string;
  timestamp?: string;
  data?: T;
  error?: ApiErrorEnvelope | string | null;
};

type BackendUiCaseItem = Partial<AssignedCase> & {
  case_id?: string;
  title?: string;
  category?: string;
  region?: string;
  priority?: AssignedCase["priority"] | string;
  status?: AssignedCase["status"] | string;
  received_at?: string;
  raw_text?: string;
  summary?: string;
  description?: string;
  text?: string;
  assignee?: string;
  structured?: AssignedCase["structured"];
};

type BackendUiCasesResponseData = {
  count?: number;
  cases?: BackendUiCaseItem[];
};

type BackendSearchResult = {
  rank?: number;
  case_id?: string;
  similarity_score?: number;
  content?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  doc_id?: string;
  score?: number;
  chunk_id?: string;
  snippet?: string;
  summary?: Record<string, unknown>;
  answers_by_admin_unit?: Record<string, string>;
  department_answers?: Record<string, string>;
  title?: string;
};

type BackendSearchResponseData = {
  complaint_id?: string;
  strategy_id?: string;
  route_key?: string;
  routing_hint?: RoutingHint;
  routing_trace?: RoutingTrace;
  retrieved_docs?: BackendSearchResult[];
  results?: BackendSearchResult[];
  total_found?: number;
  elapsed_ms?: number;
  query?: string;
  top_k?: number;
  count?: number;
  took_ms?: number;
};

type BackendQaResponseData = {
  complaint_id?: string;
  strategy_id?: string;
  route_key?: string;
  routing_trace?: RoutingTrace;
  structured_output?: {
    summary?: string;
    action_items?: string[];
    request_segments?: string[];
  };
  answer?: string;
  citations?: Array<Record<string, unknown>>;
  limitations?: string[];
  meta?: {
    processing_time?: number;
    model?: string;
    validation_warning?: string;
  };
  qa_validation?: {
    is_valid?: boolean;
    errors?: Array<{ code?: string; message?: string }>;
    warnings?: Array<{ code?: string; message?: string }>;
  };
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_BACKEND_API_URL ||
  "http://127.0.0.1:8000";

const USE_MOCK_API = process.env.NEXT_PUBLIC_USE_MOCK_API !== "false";

const ROUTING_STORAGE_KEY = "routing-info";
const LAST_DRAFT_STORAGE_KEY = "last-draft";

export async function searchCasesApi(params: {
  complaintId: string;
  query: string;
  topK: number;
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): Promise<ApiResponse<SearchResponseData>> {
  // When using mock API, use mock case data as input to backend
  if (USE_MOCK_API) {
    // Find the mock case matching the complaintId
    const mockCase = mockAssignedCases.find(
      (c) => c.case_id === params.complaintId || c.case_id.includes(params.complaintId)
    );

    if (mockCase) {
      // Use mock case's raw_text as the search query to backend
      const backendResult = await fetchSearchCasesFromBackend({
        ...params,
        query: mockCase.raw_text || params.query,
      });
      if (backendResult) {
        return backendResult;
      }
    }

    // Fallback to mock response if backend fails
    return buildMockSearchResponse(params);
  }

  const backendResult = await fetchSearchCasesFromBackend(params);
  if (backendResult) {
    return backendResult;
  }

  return buildMockSearchResponse(params);
}

export async function runQaApi(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults: boolean;
  searchResults: RetrievedDoc[];
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): Promise<ApiResponse<QaResponseData>> {
  const validationError = validateQaRequest(params);
  if (validationError) {
    return {
      data: buildEmptyQaResponse(params),
      error: validationError,
    };
  }

  // When using mock API, always call backend (backend will process mock data)
  if (USE_MOCK_API) {
    const backendResult = await fetchQaFromBackend(params);
    if (backendResult) {
      return backendResult;
    }
    // Fallback to mock response if backend fails
    return buildMockQaResponse(params);
  }

  const backendResult = await fetchQaFromBackend(params);
  if (backendResult) {
    return backendResult;
  }

  return buildMockQaResponse(params);
}

export function loadPersistedRoutingInfo() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ROUTING_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function loadLastDraft() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LAST_DRAFT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveDraftSnapshot(draft: QaResponseData) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAST_DRAFT_STORAGE_KEY, JSON.stringify({ draft }));
}

export function loadDraftSnapshot() {
  return loadLastDraft();
}

export function clearDraftSnapshot() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LAST_DRAFT_STORAGE_KEY);
}

export function getStatusUxMessage(status: StatusUxType) {
  switch (status) {
    case "loading":
      return "처리 중입니다.";
    case "success":
      return "작업이 완료되었습니다.";
    case "error":
    case "error_fallback":
      return "오류가 발생했습니다.";
    default:
      return "대기 중입니다.";
  }
}

function mapCategoryToTopicType(category: string): TopicType {
  const value = (category || "").toLowerCase();
  if (value.includes("복지")) return "welfare";
  if (value.includes("교통")) return "traffic";
  if (value.includes("환경")) return "environment";
  if (value.includes("도로") || value.includes("안전")) return "construction";
  return "general";
}

async function fetchSearchCasesFromBackend(params: {
  complaintId: string;
  query: string;
  topK: number;
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): Promise<ApiResponse<SearchResponseData> | null> {
  try {
    const response = await fetch(buildApiUrl("/api/v1/search"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        complaint_id: params.complaintId,
        query: params.query,
        top_k: params.topK,
        filters: params.filters || undefined,
        collection_name: "civil_cases_v1",
      }),
    });

    const payload = (await response.json().catch(() => null)) as ApiEnvelope<BackendSearchResponseData> | null;

    if (!response.ok) {
      return {
        data: buildEmptySearchResponse(params),
        error: buildApiErrorPayload(
          extractApiErrorMessage(payload) || `검색 API 요청에 실패했습니다. (${response.status})`,
          response.status >= 500 ? "SERVER_ERROR" : "BAD_REQUEST",
          response.status >= 500,
          extractErrorDetails(payload),
        ),
      };
    }

    const data = payload?.data;
    if (!data) {
      return {
        data: buildEmptySearchResponse(params),
        error: buildApiErrorPayload("검색 API 응답에 data가 없습니다.", "BAD_RESPONSE", false, {}),
      };
    }

    return {
      data: normalizeSearchResponseData(data, params),
      error: null,
    };
  } catch {
    return null;
  }
}

async function fetchQaFromBackend(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults: boolean;
  searchResults: RetrievedDoc[];
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): Promise<ApiResponse<QaResponseData> | null> {
  try {
    const response = await fetch(buildApiUrl("/api/v1/qa"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        complaint_id: params.complaintId,
        query: params.query,
        routing_hint: params.routingHint,
        use_search_results: params.useSearchResults,
        search_results: params.searchResults.map((item) => ({
          doc_id: item.docId,
          chunk_id: item.chunkId,
          case_id: item.caseId,
          snippet: item.snippet,
          score: item.score,
        })),
        filters: params.filters || undefined,
        top_k: params.searchResults.length > 0 ? params.searchResults.length : 5,
      }),
    });

    const payload = (await response.json().catch(() => null)) as ApiEnvelope<BackendQaResponseData> | null;

    if (!response.ok) {
      return {
        data: buildMockQaResponse(params).data,
        error: buildApiErrorPayload(
          extractApiErrorMessage(payload) || `QA API 요청에 실패했습니다. (${response.status})`,
          response.status >= 500 ? "SERVER_ERROR" : "BAD_REQUEST",
          response.status >= 500,
          extractErrorDetails(payload),
        ),
      };
    }

    const data = payload?.data;
    if (!data) {
      return {
        data: buildMockQaResponse(params).data,
        error: buildApiErrorPayload("QA API 응답에 data가 없습니다.", "BAD_RESPONSE", false, {}),
      };
    }

    return {
      data: normalizeQaResponseData(data, params),
      error: null,
    };
  } catch {
    return null;
  }
}

function buildApiUrl(path: string) {
  return new URL(path, API_BASE_URL).toString();
}

function extractApiErrorMessage(payload: ApiEnvelope<unknown> | null) {
  if (!payload) {
    return null;
  }

  if (typeof payload.error === "string") {
    return payload.error;
  }

  if (payload.error && typeof payload.error === "object") {
    return payload.error.message || null;
  }

  return null;
}

function extractErrorDetails(payload: ApiEnvelope<unknown> | null) {
  if (!payload || typeof payload !== "object" || !payload.error || typeof payload.error !== "object" || Array.isArray(payload.error)) {
    return {} as Record<string, unknown>;
  }

  const error = payload.error as ApiErrorEnvelope;
  return error.details && typeof error.details === "object" && !Array.isArray(error.details) ? error.details : {};
}

function buildApiErrorPayload(
  message: string,
  code: string,
  retryable: boolean,
  details: Record<string, unknown>,
): ApiErrorPayload {
  return {
    code,
    message,
    retryable,
    details: details || {},
  };
}

function validateQaRequest(params: {
  query: string;
  useSearchResults: boolean;
  searchResults: RetrievedDoc[];
}): ApiErrorPayload | null {
  if (!params.query.trim()) {
    return buildApiErrorPayload("QA query는 비어 있을 수 없습니다.", "VALIDATION_ERROR", false, { field: "query" });
  }

  if (params.useSearchResults && params.searchResults.length === 0) {
    return buildApiErrorPayload(
      "use_search_results=true 일 때 search_results가 필요합니다.",
      "VALIDATION_ERROR",
      false,
      { field: "search_results", use_search_results: true },
    );
  }

  const invalidResult = params.searchResults.find((doc) => typeof doc.score !== "number" || Number.isNaN(doc.score));
  if (invalidResult) {
    return buildApiErrorPayload(
      "search_results의 각 항목에는 score가 필요합니다.",
      "VALIDATION_ERROR",
      false,
      { field: "search_results", missing: "score", case_id: invalidResult.caseId },
    );
  }

  return null;
}

function normalizeAnswerCitationTokens(value: string) {
  return value
    .replace(/\[\[CITE\s*:?\s*(\d+)\]\]/gi, "[[출처 $1]]")
    .replace(/\[출처\s*(\d+)\]/gi, "[[출처 $1]]")
    .replace(/\(출처\s*(\d+)\)/gi, "[[출처 $1]]");
}

function normalizeStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as string[];
  }

  return value.map((item) => String(item).trim()).filter(Boolean);
}

function normalizeValidationIssues(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as Array<{ code: string; message: string }>;
  }

  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }

      const raw = item as { code?: unknown; message?: unknown };
      return {
        code: asString(raw.code || "VALIDATION_ERROR") || "VALIDATION_ERROR",
        message: asString(raw.message || ""),
      };
    })
    .filter((item): item is { code: string; message: string } => Boolean(item));
}

function normalizeCitations(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as QaResponseData["citations"];
  }

  const normalized: QaResponseData["citations"] = [];

  value.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      return;
    }

    const raw = item as Record<string, unknown>;
    const refId = Number(raw.ref_id ?? raw.refId ?? index + 1) || index + 1;
    const chunkId = asString(raw.chunk_id ?? raw.chunkId ?? `chunk-${refId}`) || `chunk-${refId}`;
    const caseId = asString(raw.case_id ?? raw.caseId ?? raw.doc_id ?? raw.docId ?? "") || "";
    const docId = asString(raw.doc_id ?? raw.docId ?? caseId) || undefined;

    normalized.push({
      ref_id: refId,
      doc_id: docId,
      chunk_id: chunkId,
      case_id: caseId,
      snippet: asString(raw.snippet ?? ""),
      relevance_score: raw.relevance_score == null ? undefined : Number(raw.relevance_score) || 0,
      source: asString(raw.source ?? "") || undefined,
    });
  });

  return normalized;
}

function buildEmptyQaResponse(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults: boolean;
  searchResults: RetrievedDoc[];
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): QaResponseData {
  const fallbackAnswer = normalizeAnswerCitationTokens(
    `${params.caseContext.title} 관련 민원을 검토했습니다. ${params.routingHint?.note || "검색 결과"}를 바탕으로 후속 조치를 안내합니다.`,
  );

  return {
    complaintId: params.complaintId,
    answer: fallbackAnswer,
    citations: [],
    limitations: [],
    meta: {
      processing_time: 0,
      model: "",
      validation_warning: "",
    },
    qa_validation: {
      is_valid: true,
      errors: [],
      warnings: [],
    },
    structuredOutput: {
      summary: params.caseContext.summary,
      actionItems: [
        `${params.caseContext.category} 담당 부서 현장 확인`,
        `${params.filters?.region || params.caseContext.region} 지역 내 후속 조치 일정 안내`,
      ],
      requestSegments: params.useSearchResults
        ? params.searchResults.map((doc) => doc.snippet)
        : [params.query || params.caseContext.summary].filter(Boolean),
    },
  };
}

function normalizeSearchResponseData(
  data: BackendSearchResponseData,
  params: {
    complaintId: string;
    query: string;
    topK: number;
    filters?: { region?: string; category?: string };
    caseContext: WorkbenchCaseContext;
  },
): SearchResponseData {
  const backendResults = Array.isArray(data.results) && data.results.length > 0 ? data.results : data.retrieved_docs || [];
  const normalizedResults = backendResults.map((item, index) => normalizeSearchResultItem(item, index, params));
  const routingTrace = normalizeRoutingTrace(data.routing_trace || buildDefaultRoutingTrace(params));
  const routingHint = normalizeRoutingHint(data.routing_hint || buildDefaultRoutingHint(routingTrace, params), params);
  const strategyId = data.strategy_id || routingHint.strategyId || buildDefaultStrategyId(routingTrace);
  const routeKey = data.route_key || routingHint.routeKey || buildDefaultRouteKey(routingTrace);

  return {
    query: data.query || params.query,
    results: normalizedResults,
    retrievedDocs: normalizedResults,
    searchResults: normalizedResults,
    routingTrace,
    routingHint,
    strategyId,
    routeKey,
    totalFound: Number(data.total_found ?? data.count ?? normalizedResults.length) || normalizedResults.length,
    elapsedMs: Number(data.elapsed_ms ?? data.took_ms ?? 0) || 0,
  };
}

function normalizeSearchResultItem(
  item: BackendSearchResult,
  index: number,
  params: {
    complaintId: string;
    query: string;
    topK: number;
    filters?: { region?: string; category?: string };
    caseContext: WorkbenchCaseContext;
  },
): RetrievedDoc {
  const caseId = String(item.case_id || item.doc_id || params.complaintId || `CASE-${index + 1}`);
  const docId = String(item.doc_id || caseId);
  const chunkId = String(item.chunk_id || `${docId}__chunk-0`);
  const metadata = item.metadata || {};
  const summary = item.summary || {};
  const content = item.content || {};
  const createdAt = asString(metadata.created_at || metadata.createdAt || null);
  const observation = asString(summary.observation || content.observation || item.title || "");
  const requestText = asString(summary.request || content.request || item.snippet || "");
  const resultText = asString(content.result || summary.result || "");
  const contextText = asString(content.context || "");
  const snippet = asString(item.snippet || requestText || observation || contextText || item.title || "");
  const title = buildSearchResultTitle(item.title, observation, requestText, snippet, params.caseContext.category);
  const similarityScore = Number(item.similarity_score ?? item.score ?? 0) || 0;
  const entityLabels = Array.isArray(metadata.entity_labels) ? metadata.entity_labels.map((label) => String(label)) : [];
  const answersByAdminUnit = normalizeAdminUnitAnswers(
    item.answers_by_admin_unit || item.department_answers || metadata.answers_by_admin_unit || metadata.department_answers,
  );

  return {
    rank: Number(item.rank ?? index + 1) || index + 1,
    docId,
    caseId,
    case_id: caseId,
    title,
    received_at: createdAt || "-",
    snippet,
    similarity_score: similarityScore,
    score: Number(item.score ?? similarityScore) || similarityScore,
    chunkId,
    chunk_id: chunkId,
    content: {
      observation,
      result: resultText,
      request: requestText,
      context: contextText,
    },
    metadata: {
      created_at: createdAt,
      category: asString(metadata.category || params.caseContext.category || null),
      region: asString(metadata.region || params.caseContext.region || null),
      entity_labels: entityLabels,
      strategy_id: asString(metadata.strategy_id || null),
      route_key: asString(metadata.route_key || null),
      topic_type: asString(metadata.topic_type || null),
      retrieval_policy: asString(metadata.retrieval_policy || null),
      matched_segments: Array.isArray(metadata.matched_segments) ? metadata.matched_segments.map((segment) => String(segment)) : [],
    },
    summary: {
      observation,
      request: requestText,
    },
    answers_by_admin_unit: answersByAdminUnit,
    department_answers: answersByAdminUnit,
  };
}

function buildDefaultRoutingTrace(params: {
  query: string;
  caseContext: WorkbenchCaseContext;
  filters?: { region?: string; category?: string };
}): RoutingTrace {
  const topicType = mapCategoryToTopicType(params.caseContext.category);
  const complexityLevel: RoutingTrace["complexityLevel"] = params.query.length > 80 ? "high" : params.query.length > 35 ? "medium" : "low";

  return {
    topicType,
    complexityLevel,
    complexityScore: complexityLevel === "high" ? 0.81 : complexityLevel === "medium" ? 0.62 : 0.39,
    complexityTrace: {
      intent_count: 1,
      constraint_count: Math.min(3, Math.max(1, Math.ceil(params.query.length / 40))),
      entity_diversity: params.filters?.category ? 2 : 1,
      policy_reference_count: params.query.includes("단속") || params.query.includes("점검") ? 1 : 0,
      cross_sentence_dependency: params.query.length > 60,
    },
    routeReason: `${params.caseContext.category} 민원을 기준으로 ${complexityLevel} 복잡도 경로를 선택했습니다.`,
  };
}

function buildDefaultRoutingHint(routingTrace: RoutingTrace, params: { caseContext: WorkbenchCaseContext }): RoutingHint {
  return {
    routeKey: buildDefaultRouteKey(routingTrace),
    strategyId: buildDefaultStrategyId(routingTrace),
    note: `${params.caseContext.region} / ${params.caseContext.category} 중심 검색`,
  };
}

function buildDefaultRouteKey(routingTrace: RoutingTrace) {
  return `${routingTrace.topicType}/${routingTrace.complexityLevel}`;
}

function buildDefaultStrategyId(routingTrace: RoutingTrace) {
  return `topic_${routingTrace.topicType}_${routingTrace.complexityLevel}_v1`;
}

function normalizeRoutingHint(value: unknown, params: { caseContext: WorkbenchCaseContext }): RoutingHint {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return buildDefaultRoutingHint(buildDefaultRoutingTrace({ query: params.caseContext.summary, caseContext: params.caseContext }), params);
  }

  const raw = value as Record<string, unknown>;
  const fallback = buildDefaultRoutingHint(
    buildDefaultRoutingTrace({ query: params.caseContext.summary, caseContext: params.caseContext }),
    params,
  );

  return {
    routeKey: asString(raw.route_key || raw.routeKey || fallback.routeKey),
    strategyId: asString(raw.strategy_id || raw.strategyId || fallback.strategyId),
    note: fallback.note,
  };
}

function normalizeRoutingTrace(value: unknown): RoutingTrace {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return value as RoutingTrace;
  }

  const raw = value as Record<string, unknown>;
  return {
    topicType: asString(raw.topic_type || raw.topicType || "general") as TopicType,
    complexityLevel: (raw.complexity_level || raw.complexityLevel || "low") as RoutingTrace["complexityLevel"],
    complexityScore: Number(raw.complexity_score ?? raw.complexityScore ?? 0) || 0,
    complexityTrace: (raw.complexity_trace || raw.complexityTrace || {}) as Record<string, number | boolean>,
    routeReason: asString(raw.route_reason || raw.routeReason || ""),
  };
}

function normalizeAdminUnitAnswers(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {} as Record<string, string>;
  }

  const normalized: Record<string, string> = {};
  for (const [key, rawValue] of Object.entries(value as Record<string, unknown>)) {
    const normalizedKey = String(key || "").trim();
    const normalizedValue = String(rawValue ?? "").trim();
    if (normalizedKey) {
      normalized[normalizedKey] = normalizedValue;
    }
  }
  return normalized;
}

function buildSearchResultTitle(
  explicitTitle: string | undefined,
  observation: string,
  requestText: string,
  snippet: string,
  category: string,
) {
  const titleCandidates = [explicitTitle, observation, requestText, snippet, category]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  if (titleCandidates.length === 0) {
    return "유사 민원";
  }
  return titleCandidates[0].split(" - ")[0].trim().slice(0, 60);
}

function asString(value: unknown) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function buildEmptySearchResponse(params: {
  complaintId: string;
  query: string;
  topK: number;
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): SearchResponseData {
  const routingTrace = buildDefaultRoutingTrace(params);
  const routingHint = buildDefaultRoutingHint(routingTrace, params);
  const strategyId = buildDefaultStrategyId(routingTrace);
  const routeKey = buildDefaultRouteKey(routingTrace);

  return {
    query: params.query,
    results: [],
    retrievedDocs: [],
    searchResults: [],
    routingTrace,
    routingHint,
    strategyId,
    routeKey,
    totalFound: 0,
    elapsedMs: 0,
  };
}

function normalizeUiCasesResponseData(data: BackendUiCasesResponseData): UiCasesResponseData {
  const cases = Array.isArray(data.cases) ? data.cases.map((item, index) => normalizeUiCaseItem(item, index)) : [];

  return {
    count: Number(data.count ?? cases.length) || cases.length,
    cases,
  };
}

function normalizeUiCaseItem(item: BackendUiCaseItem, index: number): AssignedCase {
  const caseId = asString(item.case_id || `CASE-${index + 1}`) || `CASE-${index + 1}`;
  const rawText = asString(item.raw_text || item.text || item.summary || item.description || "");
  const observation = asString(item.structured?.observation?.text || "");
  const request = asString(item.structured?.request?.text || "");
  const result = asString(item.structured?.result?.text || "");
  const context = asString(item.structured?.context?.text || "");

  return {
    case_id: caseId,
    title: asString(item.title || rawText || caseId || "민원"),
    category: asString(item.category || "기타"),
    region: asString(item.region || "-"),
    assignee: asString(item.assignee || "미지정"),
    priority: (item.priority as AssignedCase["priority"]) || "보통",
    received_at: asString(item.received_at || "-"),
    status: (item.status as AssignedCase["status"]) || "미처리",
    raw_text: rawText,
    summary: asString(item.summary || ""),
    description: asString(item.description || ""),
    text: asString(item.text || ""),
    structured:
      item.structured || observation || request || result || context
        ? {
            observation: { text: observation },
            request: { text: request },
            result: { text: result },
            context: { text: context },
          }
        : undefined,
  };
}

function buildMockUiCasesResponse(): ApiResponse<UiCasesResponseData> {
  return {
    data: {
      count: mockAssignedCases.length,
      cases: mockAssignedCases,
    },
    error: null,
  };
}

function normalizeQaResponseData(
  data: BackendQaResponseData,
  params: {
    complaintId: string;
    query: string;
    routingHint?: RoutingHint;
    useSearchResults: boolean;
    searchResults: RetrievedDoc[];
    filters?: { region?: string; category?: string };
    caseContext: WorkbenchCaseContext;
  },
): QaResponseData {
  const actionItems = Array.isArray(data.structured_output?.action_items)
    ? data.structured_output.action_items.map((item) => String(item)).filter(Boolean)
    : [];
  const requestSegments = Array.isArray(data.structured_output?.request_segments)
    ? data.structured_output.request_segments.map((item) => String(item)).filter(Boolean)
    : [];
  const citations = normalizeCitations(data.citations);
  const limitations = normalizeStringArray(data.limitations);
  const meta = {
    processing_time: Number(data.meta?.processing_time ?? 0) || 0,
    model: asString(data.meta?.model || ""),
    validation_warning: asString(data.meta?.validation_warning || ""),
  };
  const qaValidation = {
    is_valid: Boolean(data.qa_validation?.is_valid ?? true),
    errors: normalizeValidationIssues(data.qa_validation?.errors),
    warnings: normalizeValidationIssues(data.qa_validation?.warnings),
  };

  return {
    complaintId: data.complaint_id || params.complaintId,
    answer: normalizeAnswerCitationTokens(
      data.answer || `${params.caseContext.title} 관련 민원을 검토했습니다. ${params.routingHint?.note || "검색 결과"}를 바탕으로 후속 조치를 안내합니다.`,
    ),
    citations: citations.length > 0 ? citations : buildEmptyQaResponse(params).citations,
    limitations: limitations.length > 0 ? limitations : buildEmptyQaResponse(params).limitations,
    meta,
    qa_validation: qaValidation,
    structuredOutput: {
      summary: data.structured_output?.summary || params.caseContext.summary,
      actionItems: actionItems.length > 0 ? actionItems : buildMockQaResponse(params).data.structuredOutput.actionItems,
      requestSegments:
        requestSegments.length > 0
          ? requestSegments
          : params.useSearchResults
            ? params.searchResults.map((doc) => doc.snippet)
            : [params.query || params.caseContext.summary].filter(Boolean),
    },
  };
}

function buildMockSearchResponse(params: {
  complaintId: string;
  query: string;
  topK: number;
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): ApiResponse<SearchResponseData> {
  const currentCase = mockAssignedCases.find((item) => item.case_id === params.complaintId);
  const topicType = mapCategoryToTopicType(params.caseContext.category);
  const complexityLevel: RoutingTrace["complexityLevel"] = params.query.length > 80 ? "high" : params.query.length > 35 ? "medium" : "low";
  const routeKey = `${topicType}/${complexityLevel}`;
  const strategyId = `topic_${topicType}_${complexityLevel}_v1`;

  const routingTrace: RoutingTrace = {
    topicType,
    complexityLevel,
    complexityScore: complexityLevel === "high" ? 0.81 : complexityLevel === "medium" ? 0.62 : 0.39,
    complexityTrace: {
      intent_count: 1,
      constraint_count: Math.min(3, Math.max(1, Math.ceil(params.query.length / 40))),
      entity_diversity: params.filters?.category ? 2 : 1,
      policy_reference_count: params.query.includes("단속") || params.query.includes("점검") ? 1 : 0,
      cross_sentence_dependency: params.query.length > 60,
    },
    routeReason: `${params.caseContext.category} 민원을 기준으로 ${complexityLevel} 복잡도 경로를 선택했습니다.`,
  };

  const routingHint: RoutingHint = {
    routeKey,
    strategyId,
    note: `${params.caseContext.region} / ${params.caseContext.category} 중심 검색`,
  };

  const docs: RetrievedDoc[] = mockWorkbenchSimilarCases.slice(0, Math.max(1, Math.min(params.topK, mockWorkbenchSimilarCases.length))).map((item, idx) => {
    const score = Number((item.similarity_score - idx * 0.01).toFixed(2));
    const answerMap = item.department_tracks.reduce<Record<string, string>>((acc, track) => {
      acc[track.admin_unit] = track.answer;
      return acc;
    }, {});

    return {
      rank: idx + 1,
      docId: item.case_id,
      caseId: item.case_id,
      case_id: item.case_id,
      title: item.title,
      received_at: item.received_at,
      snippet: item.snippet,
      similarity_score: score,
      score,
      chunkId: `${item.case_id}__chunk-0`,
      chunk_id: `${item.case_id}__chunk-0`,
      content: {
        observation: item.complaint,
        result: item.answer,
        request: item.answer,
        context: "",
      },
      metadata: {
        created_at: item.received_at,
        category: currentCase?.category || params.caseContext.category,
        region: currentCase?.region || params.caseContext.region,
        entity_labels: [],
      },
      summary: {
        observation: item.complaint,
        request: item.answer,
      },
      answers_by_admin_unit: answerMap,
      department_answers: answerMap,
    };
  });

  const filteredDocs = docs.filter((doc) => {
    const current = currentCase?.raw_text || params.caseContext.summary;
    const haystack = `${doc.title} ${doc.snippet} ${current}`.toLowerCase();
    const regionOk = params.filters?.region ? currentCase?.region === params.filters.region : true;
    const categoryOk = params.filters?.category ? currentCase?.category === params.filters.category : true;
    return haystack.includes(params.query.toLowerCase().slice(0, 16)) || regionOk || categoryOk;
  });

  const retrievedDocs = (filteredDocs.length > 0 ? filteredDocs : docs).slice(0, params.topK);

  return {
    data: {
      query: params.query,
      results: retrievedDocs,
      retrievedDocs,
      searchResults: retrievedDocs,
      routingTrace,
      routingHint,
      strategyId,
      routeKey,
      totalFound: retrievedDocs.length,
      elapsedMs: 0,
    },
    error: null,
  };
}

function buildMockQaResponse(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults: boolean;
  searchResults: RetrievedDoc[];
  filters?: { region?: string; category?: string };
  caseContext: WorkbenchCaseContext;
}): ApiResponse<QaResponseData> {
  const actionItems = [
    `${params.caseContext.category} 담당 부서 현장 확인`,
    `${params.filters?.region || params.caseContext.region} 지역 내 후속 조치 일정 안내`,
  ];

  const requestSegments = params.useSearchResults
    ? params.searchResults.map((doc) => doc.snippet)
    : [params.query || params.caseContext.summary].filter(Boolean);

  return {
    data: {
      complaintId: params.complaintId,
      answer: normalizeAnswerCitationTokens(`${params.caseContext.title} 관련 민원을 검토했습니다. ${params.routingHint?.note || "검색 결과"}를 바탕으로 후속 조치를 안내합니다.`),
      citations: [],
      limitations: [],
      meta: {
        processing_time: 0,
        model: "",
        validation_warning: "",
      },
      qa_validation: {
        is_valid: true,
        errors: [],
        warnings: [],
      },
      structuredOutput: {
        summary: params.caseContext.summary,
        actionItems,
        requestSegments,
      },
    },
    error: null,
  };
}

export async function fetchUiCasesApi(): Promise<ApiResponse<UiCasesResponseData>> {
  if (USE_MOCK_API) {
    return buildMockUiCasesResponse();
  }

  const backendResult = await fetchUiCasesFromBackend();
  if (backendResult) {
    return backendResult;
  }

  return buildMockUiCasesResponse();
}

async function fetchUiCasesFromBackend(): Promise<ApiResponse<UiCasesResponseData> | null> {
  try {
    const response = await fetch(buildApiUrl("/api/v1/ui/cases"), {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const payload = (await response.json().catch(() => null)) as ApiEnvelope<BackendUiCasesResponseData> | null;

    if (!response.ok) {
      return {
        data: buildMockUiCasesResponse().data,
        error: buildApiErrorPayload(
          extractApiErrorMessage(payload) || `UI 케이스 API 요청에 실패했습니다. (${response.status})`,
          response.status >= 500 ? "SERVER_ERROR" : "BAD_REQUEST",
          response.status >= 500,
          extractErrorDetails(payload),
        ),
      };
    }

    const data = payload?.data;
    if (!data) {
      return {
        data: buildMockUiCasesResponse().data,
        error: buildApiErrorPayload("UI 케이스 API 응답에 data가 없습니다.", "BAD_RESPONSE", false, {}),
      };
    }

    return {
      data: normalizeUiCasesResponseData(data),
      error: null,
    };
  } catch {
    return null;
  }
}
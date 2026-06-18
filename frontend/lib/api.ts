import { mockAssignedCases, mockWorkbenchSimilarCases } from "./mockData";
import type { ResponsibleUnit } from "./responsibleUnit";

export type TopicType = "welfare" | "traffic" | "environment" | "construction" | "general";

export type CaseStructuredFields = {
  observation?: { text?: string };
  request?: { text?: string };
  result?: { text?: string };
  context?: { text?: string };
  responsible_unit?: ResponsibleUnit[];
};

export type AssignedCase = {
  case_id: string;
  title?: string;
  received_at: string;
  category: string;
  region: string;
  priority: string;
  status?: string;
  assignee?: string;
  raw_text: string;
  text?: string;
  summary?: string;
  description?: string;
  structured?: CaseStructuredFields;
};

export type RoutingTrace = {
  topicType: TopicType;
  complexityLevel: "low" | "medium" | "high";
  complexityScore: number;
  requestSegments?: string[];
  complexityTrace: {
    intent_count: number;
    constraint_count: number;
    entity_diversity: number;
    policy_reference_count: number;
    cross_sentence_dependency: boolean;
  };
  routeReason: string;
  routeKey?: string;
  strategyId?: string;
  appliedFilters?: Record<string, unknown>;
};

export type RoutingHint = {
  topicType: TopicType;
  complexityLevel: "low" | "medium" | "high";
  suggestedDepartment?: string;
  reason?: string;
  strategy_id?: string;
  route_key?: string;
  top_k?: number;
  snippet_max_chars?: number;
  chunk_policy?: "compact" | "balanced" | "expanded";
};

export type WorkbenchCaseContext = {
  caseId: string;
  title?: string;
  category?: string;
  region?: string;
  summary?: string;
  priority?: string;
};

export type RetrievedDoc = {
  docId: string;
  chunkId?: string;
  caseId?: string;
  case_id?: string;
  title: string;
  snippet: string;
  score: number;
  similarity_score?: number;
  received_at?: string;
  summary?: {
    observation?: string;
    request?: string;
  };
  answers_by_admin_unit?: Record<string, string>;
  department_answers?: Record<string, string>;
};

export type SearchResponseData = {
  query: string;
  retrievedDocs: RetrievedDoc[];
  results: RetrievedDoc[];
  searchResults: RetrievedDoc[];
  routingTrace: RoutingTrace;
  routingHint: RoutingHint;
  strategyId: string;
  routeKey: string;
};

export type QaResponseData = {
  complaintId?: string;
  answer: string;
  citations?: Array<{
    doc_id?: string;
    source?: string;
    quote?: string;
  }>;
  limitations?: string[];
  structuredOutput?: {
    summary?: string;
    actionItems?: string[];
    requestSegments?: string[];
  };
};

type ApiResponse<T> = {
  data: T;
  error: { message: string } | null;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const ROUTING_STORAGE_KEY = "workbench-routing-info";
const DRAFT_STORAGE_KEY = "workbench-last-draft";

type BackendEnvelope<T> = {
  success?: boolean;
  data?: T;
  error?: { message?: string };
  detail?: string;
};

type BackendRoutingTrace = {
  topic_type?: string;
  complexity_level?: string;
  complexity_score?: number;
  request_segments?: string[];
  complexity_trace?: Partial<RoutingTrace["complexityTrace"]>;
  route_reason?: string;
  route_key?: string;
  strategy_id?: string;
  applied_filters?: Record<string, unknown>;
};

type BackendRoutingHint = {
  strategy_id?: string;
  route_key?: string;
  top_k?: number;
  snippet_max_chars?: number;
  chunk_policy?: "compact" | "balanced" | "expanded";
};

type BackendSearchResult = {
  rank?: number;
  case_id?: string;
  doc_id?: string;
  chunk_id?: string;
  title?: string;
  snippet?: string;
  score?: number;
  similarity_score?: number;
  summary?: {
    observation?: string;
    request?: string;
  };
  content?: {
    observation?: string;
    request?: string;
    result?: string;
    context?: string;
  };
  metadata?: {
    created_at?: string;
    category?: string;
    region?: string;
  };
  answers_by_admin_unit?: Record<string, string>;
  department_answers?: Record<string, string>;
};

type BackendSearchData = {
  query?: string;
  strategy_id?: string;
  route_key?: string;
  routing_hint?: BackendRoutingHint;
  routing_trace?: BackendRoutingTrace;
  retrieved_docs?: BackendSearchResult[];
  results?: BackendSearchResult[];
  items?: BackendSearchResult[];
};

type BackendQaData = {
  complaint_id?: string;
  answer?: string;
  citations?: QaResponseData["citations"];
  limitations?: string[];
  structured_output?: {
    summary?: string;
    action_items?: string[];
    request_segments?: string[];
  };
};

export async function fetchUiCasesApi(): Promise<ApiResponse<{ cases: AssignedCase[] }>> {
  try {
    const payload = await fetchBackend<{ cases?: AssignedCase[] }>("/api/v1/ui/cases");
    const cases = Array.isArray(payload.cases) && payload.cases.length > 0 ? payload.cases : mockAssignedCases;
    return { data: { cases }, error: null };
  } catch (error) {
    return { data: { cases: mockAssignedCases }, error: toApiError(error) };
  }
}

export async function searchCasesApi(params: {
  complaintId: string;
  query: string;
  topK?: number;
  filters?: {
    region?: string;
    category?: string;
  };
  caseContext?: WorkbenchCaseContext;
}): Promise<ApiResponse<SearchResponseData>> {
  try {
    const filters = normalizeSearchFilters(params.filters);
    const payload = await fetchBackend<BackendSearchData>("/api/v1/search", {
      method: "POST",
      body: JSON.stringify({
        complaint_id: params.complaintId,
        query: params.query,
        top_k: params.topK || 5,
        filters,
        collection_name: "civil_cases_v1",
      }),
    });

    return { data: mapSearchData(payload, params), error: null };
  } catch (error) {
    return { data: mockSearchData(params), error: toApiError(error) };
  }
}

export async function runQaApi(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults?: boolean;
  searchResults?: RetrievedDoc[];
  filters?: {
    region?: string;
    category?: string;
  };
  caseContext?: WorkbenchCaseContext;
}): Promise<ApiResponse<QaResponseData>> {
  try {
    const filters = normalizeSearchFilters(params.filters);
    const payload = await fetchBackend<BackendQaData>("/api/v1/qa", {
      method: "POST",
      body: JSON.stringify({
        complaint_id: params.complaintId,
        query: params.query,
        routing_hint: toBackendRoutingHint(params.routingHint),
        use_search_results: params.useSearchResults,
        search_results: (params.searchResults || []).map(toQaSearchResult),
        filters,
      }),
    });

    return { data: mapQaData(payload, params), error: null };
  } catch (error) {
    return { data: mockQaData(params), error: toApiError(error) };
  }
}

export function loadPersistedRoutingInfo() {
  return readLocalStorageJson(ROUTING_STORAGE_KEY);
}

export function loadLastDraft() {
  return readLocalStorageJson(DRAFT_STORAGE_KEY);
}

export function saveDraftSnapshot(draft: QaResponseData) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ draft }));
}

export function clearDraftSnapshot() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(DRAFT_STORAGE_KEY);
}

function buildRoutingTrace(category: string): RoutingTrace {
  const topicType = mapCategoryToTopic(category);
  return {
    topicType,
    complexityLevel: "medium",
    complexityScore: 0.58,
    complexityTrace: {
      intent_count: 1,
      constraint_count: 1,
      entity_diversity: 1,
      policy_reference_count: 0,
      cross_sentence_dependency: false,
    },
    routeReason: `Mock 데이터의 카테고리(${category})를 기반으로 라우팅했습니다.`,
  };
}

async function fetchBackend<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  const envelope = (await response.json().catch(() => ({}))) as BackendEnvelope<T>;

  if (!response.ok || envelope.success === false) {
    throw new Error(envelope.error?.message || envelope.detail || `API 요청 실패 (${response.status})`);
  }
  if (!envelope.data) {
    throw new Error("API 응답에 data 필드가 없습니다.");
  }
  return envelope.data;
}

function mapSearchData(payload: BackendSearchData, params: {
  complaintId: string;
  query: string;
  topK?: number;
  filters?: { region?: string; category?: string };
  caseContext?: WorkbenchCaseContext;
}): SearchResponseData {
  const routingTrace = toRoutingTrace(payload.routing_trace, params.caseContext?.category || params.filters?.category || "일반");
  const strategyId = payload.strategy_id || payload.routing_hint?.strategy_id || routingTrace.strategyId || `topic_${routingTrace.topicType}_${routingTrace.complexityLevel}_v1`;
  const routeKey = payload.route_key || payload.routing_hint?.route_key || routingTrace.routeKey || `${routingTrace.topicType}/${routingTrace.complexityLevel}`;
  const docs = (payload.retrieved_docs || payload.results || payload.items || [])
    .slice(0, params.topK || 5)
    .map((item, index) => toRetrievedDoc(item, index));

  const routingHint: RoutingHint = {
    ...toRoutingHint(payload.routing_hint, routingTrace, params.caseContext?.category || params.filters?.category),
    strategy_id: strategyId,
    route_key: routeKey,
  };

  return {
    query: payload.query || params.query,
    retrievedDocs: docs,
    results: docs,
    searchResults: docs,
    routingTrace,
    routingHint,
    strategyId,
    routeKey,
  };
}

function toRoutingTrace(input: BackendRoutingTrace | undefined, fallbackCategory: string): RoutingTrace {
  const fallback = buildRoutingTrace(fallbackCategory);
  const topicType = normalizeTopicType(input?.topic_type) || fallback.topicType;
  const complexityLevel = normalizeComplexityLevel(input?.complexity_level) || fallback.complexityLevel;
  const complexityTrace = input?.complexity_trace || {};

  return {
    topicType,
    complexityLevel,
    complexityScore: Number(input?.complexity_score ?? fallback.complexityScore),
    requestSegments: input?.request_segments || [],
    complexityTrace: {
      intent_count: Number(complexityTrace.intent_count ?? fallback.complexityTrace.intent_count),
      constraint_count: Number(complexityTrace.constraint_count ?? fallback.complexityTrace.constraint_count),
      entity_diversity: Number(complexityTrace.entity_diversity ?? fallback.complexityTrace.entity_diversity),
      policy_reference_count: Number(complexityTrace.policy_reference_count ?? fallback.complexityTrace.policy_reference_count),
      cross_sentence_dependency: Boolean(complexityTrace.cross_sentence_dependency ?? fallback.complexityTrace.cross_sentence_dependency),
    },
    routeReason: input?.route_reason || fallback.routeReason,
    routeKey: input?.route_key,
    strategyId: input?.strategy_id,
    appliedFilters: input?.applied_filters,
  };
}

function toRoutingHint(input: BackendRoutingHint | undefined, trace: RoutingTrace, category = ""): RoutingHint {
  return {
    topicType: trace.topicType,
    complexityLevel: trace.complexityLevel,
    suggestedDepartment: suggestDepartment(category),
    reason: "백엔드 /api/v1/search 라우팅 결과입니다.",
    strategy_id: input?.strategy_id,
    route_key: input?.route_key,
    top_k: input?.top_k,
    snippet_max_chars: input?.snippet_max_chars,
    chunk_policy: input?.chunk_policy,
  };
}

function toRetrievedDoc(item: BackendSearchResult, index: number): RetrievedDoc {
  const caseId = String(item.case_id || item.doc_id || `RESULT-${index + 1}`);
  const docId = String(item.doc_id || caseId || `result-${index + 1}`);
  const summary = item.summary || {
    observation: item.content?.observation || "",
    request: item.content?.request || "",
  };
  const title = item.title || summary.observation || item.snippet || `유사 민원 ${index + 1}`;
  const score = Number(item.score ?? item.similarity_score ?? 0);

  return {
    docId,
    chunkId: item.chunk_id,
    caseId,
    case_id: caseId,
    title,
    snippet: item.snippet || summary.request || summary.observation || "",
    score,
    similarity_score: Number(item.similarity_score ?? score),
    received_at: item.metadata?.created_at,
    summary,
    answers_by_admin_unit: item.answers_by_admin_unit || item.department_answers || {},
    department_answers: item.department_answers || item.answers_by_admin_unit || {},
  };
}

function toBackendRoutingHint(hint?: RoutingHint): BackendRoutingHint | undefined {
  if (!hint?.strategy_id || !hint.route_key) return undefined;
  return {
    strategy_id: hint.strategy_id,
    route_key: hint.route_key,
    top_k: hint.top_k || 5,
    snippet_max_chars: hint.snippet_max_chars || 1100,
    chunk_policy: hint.chunk_policy || "balanced",
  };
}

function toQaSearchResult(item: RetrievedDoc) {
  const caseId = item.caseId || item.case_id || item.docId;
  return {
    doc_id: item.docId,
    chunk_id: item.chunkId || `${caseId}__chunk-0`,
    case_id: caseId,
    snippet: item.snippet || item.summary?.observation || "",
    score: Number(item.score || item.similarity_score || 0),
  };
}

function mapQaData(payload: BackendQaData, params: {
  complaintId: string;
  query: string;
  caseContext?: WorkbenchCaseContext;
}): QaResponseData {
  return {
    complaintId: payload.complaint_id || params.complaintId,
    answer: payload.answer || "",
    citations: payload.citations || [],
    limitations: payload.limitations || [],
    structuredOutput: {
      summary: payload.structured_output?.summary || params.caseContext?.summary || params.query,
      actionItems: payload.structured_output?.action_items || [],
      requestSegments: payload.structured_output?.request_segments || [params.caseContext?.summary || params.query].filter(Boolean),
    },
  };
}

function mockSearchData(params: {
  complaintId: string;
  query: string;
  topK?: number;
  filters?: { region?: string; category?: string };
  caseContext?: WorkbenchCaseContext;
}): SearchResponseData {
  const routingTrace = buildRoutingTrace(params.caseContext?.category || params.filters?.category || "일반");
  const docs = mockWorkbenchSimilarCases
    .filter((item) => {
      if (params.filters?.region && item.region && item.region !== params.filters.region) return false;
      if (params.filters?.category && item.category && item.category !== params.filters.category) return false;
      return true;
    })
    .slice(0, params.topK || 5)
    .map<RetrievedDoc>((item, index) => ({
      docId: `mock-doc-${index + 1}`,
      caseId: item.case_id,
      case_id: item.case_id,
      title: item.complaint,
      snippet: item.answer,
      score: item.score,
      similarity_score: item.score,
      received_at: item.received_at,
      summary: {
        observation: item.complaint,
        request: item.answer,
      },
      answers_by_admin_unit: Object.fromEntries(
        item.department_tracks.map((track) => [track.admin_unit, track.answer]),
      ),
    }));

  return {
    query: params.query,
    retrievedDocs: docs,
    results: docs,
    searchResults: docs,
    routingTrace,
    routingHint: {
      topicType: routingTrace.topicType,
      complexityLevel: routingTrace.complexityLevel,
      suggestedDepartment: suggestDepartment(params.caseContext?.category || params.filters?.category),
      reason: "백엔드 API 호출 실패 후 목업 데이터로 대체했습니다.",
      strategy_id: `topic_${routingTrace.topicType}_${routingTrace.complexityLevel}_mock`,
      route_key: `${routingTrace.topicType}/${routingTrace.complexityLevel}`,
      top_k: params.topK || 5,
      snippet_max_chars: 1100,
      chunk_policy: "balanced",
    },
    strategyId: `topic_${routingTrace.topicType}_${routingTrace.complexityLevel}_mock`,
    routeKey: `${routingTrace.topicType}/${routingTrace.complexityLevel}`,
  };
}

function mockQaData(params: {
  complaintId: string;
  query: string;
  routingHint?: RoutingHint;
  useSearchResults?: boolean;
  caseContext?: WorkbenchCaseContext;
}): QaResponseData {
  const summary = params.caseContext?.summary || params.query || "민원 내용을 검토했습니다.";
  const department = params.routingHint?.suggestedDepartment || suggestDepartment(params.caseContext?.category);
  const answer = [
    `안녕하세요. 접수하신 민원(${params.complaintId})은 ${department}에서 검토하겠습니다.`,
    "현장 확인 및 관련 부서 협의를 거쳐 처리 가능 여부와 예정 일정을 안내드리겠습니다.",
    params.useSearchResults ? "유사 민원 처리 이력을 참고해 빠르게 후속 조치를 진행하겠습니다." : "필요 시 추가 자료를 요청드릴 수 있습니다.",
  ].join("\n");

  return {
    complaintId: params.complaintId,
    answer,
    citations: [],
    limitations: ["백엔드 API 호출 실패 후 프론트엔드 목업 데이터로 생성되었습니다."],
    structuredOutput: {
      summary,
      actionItems: [
        "담당 부서 배정 및 접수 내용 확인",
        "현장 또는 관련 자료 확인",
        "민원인에게 처리 계획 안내",
      ],
      requestSegments: [summary].filter(Boolean),
    },
  };
}

function compactObject<T extends Record<string, unknown>>(value: T): Partial<T> | null {
  const entries = Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== "");
  return entries.length > 0 ? Object.fromEntries(entries) as Partial<T> : null;
}

function normalizeSearchFilters(filters?: { region?: string; category?: string }) {
  const region = normalizeFilterValue(filters?.region);
  const category = normalizeFilterValue(filters?.category);
  return compactObject({
    region,
    category: category === "기타" ? undefined : category,
  });
}

function normalizeFilterValue(value?: string) {
  const normalized = String(value || "").trim();
  if (!normalized || normalized === "전체" || normalized === "-") return undefined;
  return normalized;
}

function normalizeTopicType(value?: string): TopicType | null {
  if (value === "welfare" || value === "traffic" || value === "environment" || value === "construction" || value === "general") {
    return value;
  }
  return null;
}

function normalizeComplexityLevel(value?: string): "low" | "medium" | "high" | null {
  if (value === "low" || value === "medium" || value === "high") {
    return value;
  }
  return null;
}

function toApiError(error: unknown) {
  return {
    message: error instanceof Error ? error.message : "API 요청 중 오류가 발생했습니다.",
  };
}

function mapCategoryToTopic(category = ""): TopicType {
  if (category.includes("복지") || category.includes("주거")) return "welfare";
  if (category.includes("교통")) return "traffic";
  if (category.includes("환경")) return "environment";
  if (category.includes("안전") || category.includes("도로") || category.includes("건설")) return "construction";
  return "general";
}

function suggestDepartment(category = "") {
  if (category.includes("복지") || category.includes("주거")) return "복지정책과";
  if (category.includes("교통")) return "교통행정과";
  if (category.includes("환경")) return "환경관리과";
  if (category.includes("안전") || category.includes("도로") || category.includes("건설")) return "도로안전과";
  return "민원조정실";
}

function readLocalStorageJson(key: string) {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

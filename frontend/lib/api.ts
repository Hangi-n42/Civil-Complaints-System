import { mockAssignedCases, mockWorkbenchSimilarCases } from "./mockData";

export type TopicType = "welfare" | "traffic" | "environment" | "construction" | "general";

export type CaseStructuredFields = {
  observation?: { text?: string };
  request?: { text?: string };
  result?: { text?: string };
  context?: { text?: string };
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
  complexityTrace: {
    intent_count: number;
    constraint_count: number;
    entity_diversity: number;
    policy_reference_count: number;
    cross_sentence_dependency: boolean;
  };
  routeReason: string;
};

export type RoutingHint = {
  topicType: TopicType;
  complexityLevel: "low" | "medium" | "high";
  suggestedDepartment?: string;
  reason?: string;
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

const ROUTING_STORAGE_KEY = "workbench-routing-info";
const DRAFT_STORAGE_KEY = "workbench-last-draft";

export async function fetchUiCasesApi(): Promise<ApiResponse<{ cases: AssignedCase[] }>> {
  return {
    data: { cases: mockAssignedCases },
    error: null,
  };
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

  const routingHint: RoutingHint = {
    topicType: routingTrace.topicType,
    complexityLevel: routingTrace.complexityLevel,
    suggestedDepartment: suggestDepartment(params.caseContext?.category || params.filters?.category),
    reason: "Mock 검색 결과를 기준으로 임시 라우팅 정보를 생성했습니다.",
  };

  return {
    data: {
      query: params.query,
      retrievedDocs: docs,
      results: docs,
      searchResults: docs,
      routingTrace,
      routingHint,
      strategyId: `topic_${routingTrace.topicType}_${routingTrace.complexityLevel}_mock`,
      routeKey: `${routingTrace.topicType}/${routingTrace.complexityLevel}`,
    },
    error: null,
  };
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
  const summary = params.caseContext?.summary || params.query || "민원 내용을 검토했습니다.";
  const department = params.routingHint?.suggestedDepartment || suggestDepartment(params.caseContext?.category);
  const answer = [
    `안녕하세요. 접수하신 민원(${params.complaintId})은 ${department}에서 검토하겠습니다.`,
    "현장 확인 및 관련 부서 협의를 거쳐 처리 가능 여부와 예정 일정을 안내드리겠습니다.",
    params.useSearchResults ? "유사 민원 처리 이력을 참고해 빠르게 후속 조치를 진행하겠습니다." : "필요 시 추가 자료를 요청드릴 수 있습니다.",
  ].join("\n");

  return {
    data: {
      complaintId: params.complaintId,
      answer,
      structuredOutput: {
        summary,
        actionItems: [
          "담당 부서 배정 및 접수 내용 확인",
          "현장 또는 관련 자료 확인",
          "민원인에게 처리 계획 안내",
        ],
        requestSegments: [params.caseContext?.summary || params.query].filter(Boolean) as string[],
      },
    },
    error: null,
  };
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

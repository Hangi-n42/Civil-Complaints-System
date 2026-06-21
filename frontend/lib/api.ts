import { mockAssignedCases, mockWorkbenchSimilarCases } from "./mockData";
import type { ResponsibleUnit } from "./responsibleUnit";
import { normalizeSegmentAnswers, type SegmentAnswerCard } from "./draft";

export type TopicType = "welfare" | "traffic" | "environment" | "construction" | "general";

export type CaseStructuredFields = {
  observation?: { text?: string };
  request?: { text?: string };
  result?: { text?: string };
  context?: { text?: string };
  responsible_unit?: ResponsibleUnit[];
};

export type CivilCategory = {
  primary?: string;
  secondary?: string;
  secondary_candidates?: string[];
  confidence?: number;
  evidence?: string[];
  source?: string;
};

export type AssignedCase = {
  case_id: string;
  title?: string;
  received_at: string;
  category: string;
  category_display?: string;
  civil_category?: CivilCategory;
  region: string;
  priority: string;
  status?: string;
  assignee?: string;
  raw_text: string;
  text?: string;
  summary?: string;
  description?: string;
  request_segments?: string[];
  requestSegments?: string[];
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
  requestSegments?: string[];
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
    // 이슈 #451: 요청별 답변·근거(BE3 segment_answers). 구버전 응답엔 없어 폴백으로 평면 answer를 쓴다.
    segmentAnswers?: SegmentAnswerCard[];
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
    segment_answers?: unknown;
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

export type CategoryStat = { name: string; count: number };
export type TrendPoint = { year: string; count: number };
export type AdminOverviewData = {
  year: string;
  category?: string[];
  available_years: string[];
  total: number;
  categories: CategoryStat[];
  regions: CategoryStat[];
  issues: CategoryStat[];
  trend: TrendPoint[];
};

// 관리자 대시보드 실데이터 종합(카테고리·지역·이슈유형·연도추이).
// year=연도 또는 "all"/undefined(전체). categories=카테고리 드릴다운(복수, 합집합으로 지역·이슈·건수·추이에 적용).
export async function fetchAdminOverviewApi(year?: string, categories?: string[]): Promise<ApiResponse<AdminOverviewData>> {
  const empty: AdminOverviewData = { year: year || "all", available_years: [], total: 0, categories: [], regions: [], issues: [], trend: [] };
  try {
    const params = new URLSearchParams();
    if (year) params.set("year", year);
    (categories ?? []).forEach((c) => { if (c) params.append("category", c); });
    const query = params.toString() ? `?${params.toString()}` : "";
    const payload = await fetchBackend<AdminOverviewData>(`/api/v1/admin/overview${query}`);
    return { data: payload, error: null };
  } catch (error) {
    return { data: empty, error: toApiError(error) };
  }
}

// ── 민원 인텔리전스(Complaint Intelligence) ─────────────────────────────
// 백엔드 read model(app/api/routers/complaint_intelligence.py)을 그대로 받는다.
// 카드가 이미 FE-shaped라 snake_case를 유지하고 별도 camelCase 매퍼를 두지 않는다.

export type IntelDashboardSummary = {
  as_of?: string | null;
  latest_event_at?: string | null;
  event_count?: number;
  alert_count: number;
  active_alert_count?: number;
  critical_alert_count: number;
  public_insight_count: number;
  high_priority_insight_count: number;
  human_review_required_count: number;
  linked_alert_count: number;
};

export type IntelIssueAlertCard = {
  id: string;
  status: string;
  severity: string;
  severity_label: string;
  color: string;
  title: string;
  summary: string;
  topic: string;
  region: string | null;
  center: Record<string, number> | null;
  radius: number | null;
  recent_count: number;
  baseline: number;
  surge_ratio: number;
  confidence: number;
  keywords: string[];
  representative_complaint_ids: string[];
  linked_insight_ids: string[];
  map_focus: Record<string, unknown> | null;
  first_seen: string;
  last_seen: string;
};

export type IntelActionItem = {
  action: string;
  horizon: string;
  action_type: string;
  responsible_unit_hint: string | null;
  why: string;
  supporting_evidence_ids: string[];
  expected_impact: string | null;
  risk_or_dependency: string | null;
};

export type IntelPublicInsightCard = {
  id: string;
  type: string;
  type_label: string;
  status: string;
  priority: string;
  priority_label: string;
  color: string;
  title: string;
  summary: string;
  problem_diagnosis: string;
  topic: string;
  target_area: string;
  affected_count: number;
  affected_region: Record<string, unknown> | null;
  related_department: string | null;
  window_start: string;
  window_end: string;
  confidence: number;
  grounding_score: number;
  requires_human_review: boolean;
  linked_alert_ids: string[];
  representative_evidence_ids: string[];
  top_aspects: Array<Record<string, unknown>>;
  citizen_requests: Array<Record<string, unknown>>;
  recommended_actions: IntelActionItem[];
  uncertainty: string[];
  metrics: Record<string, number | string>;
};

export type IntelDashboardData = {
  summary: IntelDashboardSummary;
  tabs: Array<{ id: string; label: string }>;
  issue_alerts: IntelIssueAlertCard[];
  public_insights: IntelPublicInsightCard[];
  empty_state: Record<string, string>; // 알려진 키: issue_alerts, public_insights
};

// run-analysis 요청 이벤트(핸드오프 §2.2). events 소스가 정해지기 전까지는 미사용.
export type IntelAnalysisEvent = {
  id: string;
  received_at: string;
  body: string;
  region?: string;
  final_department?: string;
  status?: string;
  structured_elements?: Record<string, { text?: string; confidence?: number }>;
};

// EvidencePack 대표 민원(관리자/디버그). 원문 PII 없이 masked_text만 노출된다(§5).
export type IntelEvidenceComplaint = {
  complaint_id?: string;
  source_complaint_ids?: string[];
  masked_text?: string;
  created_at?: string;
  region?: string | null;
  department?: string | null;
  status?: string | null;
  structured_elements?: Record<string, unknown>;
};

export type IntelEvidencePack = {
  candidate_id: string;
  type_hint: string | null;
  topic_label: string;
  region_summary: Record<string, unknown> | null;
  department_summary: Record<string, unknown> | null;
  window_start: string;
  window_end: string;
  complaint_count: number;
  baseline_count: number | null;
  trend_metrics: Record<string, number | string>;
  operational_metrics: Record<string, number | string>;
  representative_complaints: IntelEvidenceComplaint[];
  key_phrases: string[];
  extracted_aspects: Array<Record<string, unknown>>;
  citizen_requests: Array<Record<string, unknown>>;
  linked_alert_ids: string[];
  similar_past_patterns: Array<Record<string, unknown>>;
  allowed_action_catalog: string[];
};

export type DuplicateMergeStatus = "candidate" | "confirmed" | "split" | "rejected";
export type DuplicateMergeAction = "confirm" | "split" | "reject" | "draft_reply";
export type DuplicateRiskSeverity = "info" | "warning" | "blocker";

export type DuplicateEvidence = {
  type: string;
  message: string;
  affected_case_ids: string[];
  value?: number | string | null;
  details?: Record<string, unknown>;
};

export type DuplicateRiskFlag = {
  code: string;
  severity: DuplicateRiskSeverity;
  message: string;
  affected_case_ids: string[];
  evidence: string[];
};

export type DuplicateRepresentative = {
  complaint_id: string;
  selection_reason: string;
  quality_score: number;
};

export type DuplicateMergeRecord = {
  merge_id: string;
  status: DuplicateMergeStatus;
  representative_complaint_id: string;
  member_complaint_ids: string[];
  confidence: number;
  recommendation_level: "weak" | "review" | "strong";
  recommended_decision: "REVIEW_BEFORE_MERGE";
  evidence: DuplicateEvidence[];
  risk_flags: DuplicateRiskFlag[];
  allowed_actions: DuplicateMergeAction[];
  blocked_actions: DuplicateMergeAction[];
  linked_issue_alert_ids: string[];
  linked_public_insight_ids: string[];
  representative: DuplicateRepresentative;
  score_breakdown: Record<string, number>;
  location_state: "exact" | "nearby" | "ambiguous" | "missing" | "conflict";
  request_types: Record<string, string>;
  created_at: string;
  updated_at: string;
};

export type DuplicateGroupsData = {
  event_count?: number | null;
  count: number;
  duplicate_groups: DuplicateMergeRecord[];
};

export type DuplicateDraftReplyPayload = {
  merge_id: string;
  representative_complaint_id: string;
  member_complaint_ids: string[];
  representative: Record<string, unknown>;
  members: Array<Record<string, unknown>>;
  merge_evidence: DuplicateEvidence[];
  risk_flags: DuplicateRiskFlag[];
  system_instruction: string;
  common_reply_constraints: string[];
  prohibited_content_rules: string[];
};

const EMPTY_DUPLICATE_GROUPS: DuplicateGroupsData = {
  count: 0,
  duplicate_groups: [],
};

// 백엔드 호출 실패 시에도 탭이 렌더되도록 비어 있는 대시보드로 폴백한다(fetchAdminOverviewApi 패턴).
const EMPTY_INTEL_DASHBOARD: IntelDashboardData = {
  summary: {
    alert_count: 0,
    critical_alert_count: 0,
    public_insight_count: 0,
    high_priority_insight_count: 0,
    human_review_required_count: 0,
    linked_alert_count: 0,
  },
  tabs: [
    { id: "issue_alerts", label: "실시간 이슈" },
    { id: "public_insights", label: "행정 인사이트" },
  ],
  issue_alerts: [],
  public_insights: [],
  empty_state: {
    issue_alerts: "현재 표시할 실시간 이슈가 없습니다.",
    public_insights: "현재 표시할 행정 인사이트가 없습니다.",
  },
};

// 저장된 대시보드 조회. ⚠️ 경로는 루트(/complaint-intelligence/...), /api/v1 접두사 없음.
export async function fetchIntelDashboardApi(filters?: {
  status?: string;
  type?: string;
}): Promise<ApiResponse<IntelDashboardData>> {
  try {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.type) params.set("type", filters.type);
    const query = params.toString() ? `?${params.toString()}` : "";
    const payload = await fetchBackend<IntelDashboardData>(`/complaint-intelligence/dashboard${query}`);
    return { data: payload, error: null };
  } catch (error) {
    return { data: EMPTY_INTEL_DASHBOARD, error: toApiError(error) };
  }
}

// 분석 실행 후 대시보드 카드 응답 수신. 응답 구조는 GET /dashboard와 동일(DashboardResponse).
export async function runIntelAnalysisApi(payload: {
  request_id?: string;
  events: IntelAnalysisEvent[];
}): Promise<ApiResponse<IntelDashboardData>> {
  try {
    const data = await fetchBackend<IntelDashboardData>("/complaint-intelligence/dashboard/run-analysis", {
      method: "POST",
      body: JSON.stringify({ request_id: payload.request_id, events: payload.events }),
    });
    return { data, error: null };
  } catch (error) {
    return { data: EMPTY_INTEL_DASHBOARD, error: toApiError(error) };
  }
}

// EvidencePack(관리자/디버그) 단건. 백엔드가 봉투 없이 모델을 직접 반환하므로 fetchBackend 대신 raw fetch.
export async function fetchEvidencePackApi(
  insightId: string,
): Promise<ApiResponse<IntelEvidencePack | null>> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/complaint-intelligence/public-insights/${encodeURIComponent(insightId)}/evidence-pack`,
      { headers: { "Content-Type": "application/json" } },
    );
    if (!response.ok) {
      const detail = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(detail.detail || `EvidencePack 요청 실패 (${response.status})`);
    }
    const pack = (await response.json()) as IntelEvidencePack;
    return { data: pack, error: null };
  } catch (error) {
    return { data: null, error: toApiError(error) };
  }
}

export async function fetchDuplicateGroupsApi(filters?: {
  status?: DuplicateMergeStatus;
  complaintId?: string;
  issueAlertId?: string;
  publicInsightId?: string;
}): Promise<ApiResponse<DuplicateGroupsData>> {
  try {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.complaintId) params.set("complaint_id", filters.complaintId);
    if (filters?.issueAlertId) params.set("issue_alert_id", filters.issueAlertId);
    if (filters?.publicInsightId) params.set("public_insight_id", filters.publicInsightId);
    const query = params.toString() ? `?${params.toString()}` : "";
    const payload = await fetchBackend<DuplicateGroupsData>(`/complaint-intelligence/duplicate-groups${query}`);
    return { data: payload, error: null };
  } catch (error) {
    return { data: EMPTY_DUPLICATE_GROUPS, error: toApiError(error) };
  }
}

export async function transitionDuplicateGroupApi(
  mergeId: string,
  action: Exclude<DuplicateMergeAction, "draft_reply">,
): Promise<ApiResponse<{ duplicate_group: DuplicateMergeRecord } | null>> {
  try {
    const payload = await fetchBackend<{ duplicate_group: DuplicateMergeRecord }>(
      `/complaint-intelligence/duplicate-groups/${encodeURIComponent(mergeId)}/${action}`,
      { method: "POST" },
    );
    return { data: payload, error: null };
  } catch (error) {
    return { data: null, error: toApiError(error) };
  }
}

export async function fetchDuplicateDraftReplyApi(
  mergeId: string,
): Promise<ApiResponse<{ draft_reply_payload: DuplicateDraftReplyPayload } | null>> {
  try {
    const payload = await fetchBackend<{ draft_reply_payload: DuplicateDraftReplyPayload }>(
      `/complaint-intelligence/duplicate-groups/${encodeURIComponent(mergeId)}/draft-reply`,
      { method: "POST" },
    );
    return { data: payload, error: null };
  } catch (error) {
    return { data: null, error: toApiError(error) };
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
  routingTrace?: RoutingTrace;
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
        routing_trace: toBackendRoutingTrace(params.routingTrace, params.caseContext, params.routingHint),
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

// SSE 프레임("event: X\ndata: Y") 1개를 파싱한다. data 라인이 없으면 null.
export function parseSseFrame(frame: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

// 초안 생성을 SSE(/qa/stream)로 호출한다. 백엔드가 보내는 실제 단계(retrieving→grounding→
// generating)를 onStage로 흘려보내고, done 이벤트의 최종 응답을 반환한다.
// 스트림이 불가하거나 done 없이 끝나면 기존 비스트림 /qa로 폴백해 초안 생성은 보장한다.
export async function streamQaApi(
  params: {
    complaintId: string;
    query: string;
    routingHint?: RoutingHint;
    routingTrace?: RoutingTrace;
    useSearchResults?: boolean;
    searchResults?: RetrievedDoc[];
    filters?: {
      region?: string;
      category?: string;
    };
    caseContext?: WorkbenchCaseContext;
  },
  onStage?: (stage: string, label: string) => void,
): Promise<ApiResponse<QaResponseData>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/qa/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        complaint_id: params.complaintId,
        query: params.query,
        routing_hint: toBackendRoutingHint(params.routingHint),
        routing_trace: toBackendRoutingTrace(params.routingTrace, params.caseContext, params.routingHint),
        use_search_results: params.useSearchResults,
        search_results: (params.searchResults || []).map(toQaSearchResult),
        filters: normalizeSearchFilters(params.filters),
      }),
    });

    if (!response.ok || !response.body) {
      return runQaApi(params); // 스트림 불가 → 비스트림 폴백
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let doneData: QaResponseData | null = null;
    let errorMessage: string | null = null;

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const parsed = frame.trim() ? parseSseFrame(frame) : null;
        if (!parsed) continue;
        if (parsed.event === "stage") {
          const d = parsed.data as { stage?: string; label?: string };
          if (d.stage) onStage?.(d.stage, d.label || "");
        } else if (parsed.event === "done") {
          const d = parsed.data as BackendEnvelope<BackendQaData>;
          if (d.data) doneData = mapQaData(d.data, params);
        } else if (parsed.event === "error") {
          const d = parsed.data as { error?: { message?: string } };
          errorMessage = d.error?.message || "초안 생성 중 오류가 발생했습니다.";
        }
      }
    }

    if (errorMessage) {
      return { data: mockQaData(params), error: { message: errorMessage } };
    }
    if (doneData) {
      return { data: doneData, error: null };
    }
    return runQaApi(params); // done 없이 종료 → 폴백
  } catch {
    return runQaApi(params); // 네트워크/파싱 실패 → 폴백
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
  return buildRoutingTraceWithSegments(category, []);
}

function buildRoutingTraceWithSegments(category: string, requestSegments: string[]): RoutingTrace {
  const topicType = mapCategoryToTopic(category);
  const normalizedSegments = normalizeSegments(requestSegments);
  return {
    topicType,
    complexityLevel: "medium",
    complexityScore: 0.58,
    requestSegments: normalizedSegments,
    complexityTrace: {
      intent_count: Math.max(1, normalizedSegments.length),
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
  const routingTrace = toRoutingTrace(
    payload.routing_trace,
    params.caseContext?.category || params.filters?.category || "일반",
    params.caseContext?.requestSegments,
  );
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

function toRoutingTrace(input: BackendRoutingTrace | undefined, fallbackCategory: string, fallbackSegments?: string[]): RoutingTrace {
  const fallback = buildRoutingTraceWithSegments(fallbackCategory, fallbackSegments || []);
  const topicType = normalizeTopicType(input?.topic_type) || fallback.topicType;
  const complexityLevel = normalizeComplexityLevel(input?.complexity_level) || fallback.complexityLevel;
  const complexityTrace = input?.complexity_trace || {};
  const requestSegments = preferDetailedSegments(input?.request_segments, fallback.requestSegments);

  return {
    topicType,
    complexityLevel,
    complexityScore: Number(input?.complexity_score ?? fallback.complexityScore),
    requestSegments,
    complexityTrace: {
      intent_count: Math.max(requestSegments.length, Number(complexityTrace.intent_count ?? fallback.complexityTrace.intent_count)),
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

function toBackendRoutingTrace(
  trace: RoutingTrace | undefined,
  caseContext: WorkbenchCaseContext | undefined,
  hint?: RoutingHint,
): BackendRoutingTrace | undefined {
  const fallbackTrace = buildRoutingTraceWithSegments(caseContext?.category || "일반", caseContext?.requestSegments || []);
  const sourceTrace = trace || (fallbackTrace.requestSegments?.length ? fallbackTrace : undefined);
  if (!sourceTrace) return undefined;

  const requestSegments = preferDetailedSegments(sourceTrace.requestSegments, caseContext?.requestSegments);
  return {
    topic_type: sourceTrace.topicType || hint?.topicType || fallbackTrace.topicType,
    complexity_level: sourceTrace.complexityLevel || hint?.complexityLevel || fallbackTrace.complexityLevel,
    complexity_score: Number(sourceTrace.complexityScore ?? fallbackTrace.complexityScore),
    request_segments: requestSegments,
    complexity_trace: {
      ...sourceTrace.complexityTrace,
      intent_count: Math.max(requestSegments.length, sourceTrace.complexityTrace?.intent_count || 1),
    },
    route_reason: sourceTrace.routeReason || "선택된 민원의 요청 세그먼트를 초안 생성에 전달했습니다.",
    route_key: hint?.route_key || sourceTrace.routeKey,
    strategy_id: hint?.strategy_id || sourceTrace.strategyId,
    applied_filters: sourceTrace.appliedFilters || {},
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
  const requestSegments = preferDetailedSegments(
    payload.structured_output?.request_segments,
    params.caseContext?.requestSegments,
  );
  return {
    complaintId: payload.complaint_id || params.complaintId,
    answer: payload.answer || "",
    citations: payload.citations || [],
    limitations: payload.limitations || [],
    structuredOutput: {
      summary: payload.structured_output?.summary || params.caseContext?.summary || params.query,
      actionItems: payload.structured_output?.action_items || [],
      requestSegments: requestSegments.length > 0 ? requestSegments : [params.caseContext?.summary || params.query].filter(Boolean),
      segmentAnswers: normalizeSegmentAnswers(payload.structured_output?.segment_answers),
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
  const requestSegments = deriveMockRequestSegments(summary, params.caseContext?.requestSegments);
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
      actionItems: requestSegments.map((segment) => `${segment} 관련 확인 및 안내`),
      requestSegments,
    },
  };
}

function deriveMockRequestSegments(summary: string, explicitSegments?: string[]) {
  const cleaned = normalizeSegments(explicitSegments);
  if (cleaned.length > 0) return cleaned;
  return [summary].filter(Boolean);
}

function preferDetailedSegments(primary?: string[], fallback?: string[]): string[] {
  const primarySegments = normalizeSegments(primary);
  const fallbackSegments = normalizeSegments(fallback);
  if (fallbackSegments.length > primarySegments.length && fallbackSegments.length > 1) return fallbackSegments;
  if (primarySegments.length > 1) return primarySegments;
  if (fallbackSegments.length > 1) return fallbackSegments;
  if (primarySegments.length > 0) return primarySegments;
  return fallbackSegments;
}

function normalizeSegments(segments?: string[]): string[] {
  return (segments || [])
    .map((segment) => String(segment || "").split(/\s+/).join(" "))
    .filter(Boolean);
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

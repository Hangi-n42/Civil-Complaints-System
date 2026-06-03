"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mockAssignedCases, mockWorkbenchSimilarCases } from "@/lib/mockData";
import AppSidebar from "@/components/AppSidebar";
import {
  type RoutingHint,
  type RoutingTrace,
  type TopicType,
  fetchUiCasesApi,
  type AssignedCase,
  runQaApi,
  searchCasesApi,
  type QaResponseData,
  type RetrievedDoc,
  type SearchResponseData,
  type WorkbenchCaseContext,
  loadPersistedRoutingInfo,
  loadLastDraft,
  saveDraftSnapshot,
  clearDraftSnapshot,
} from "@/lib/api";
import { PriorityBadge, StatusBadge } from "@/components/SearchUI";
import { readJsonFromLocalStorage, sanitizeCaseStatuses, safeString } from "@/lib/safe-data";

const CASE_STATUS_STORAGE_KEY = "case-status-overrides";
const MAX_STATUS_STORAGE_BYTES = 24 * 1024;

type SearchStage = "empty" | "loading" | "success" | "error";
type DraftStage = "idle" | "loading" | "success" | "error";
type SegmentViewMode = "loading" | "error" | "empty" | "single" | "multi";

type WorkbenchStructuredFields = {
  observation?: { text?: string };
  request?: { text?: string };
  result?: { text?: string };
  context?: { text?: string };
};

type WorkbenchCase = AssignedCase & {
  case_id: string;
  title?: string;
  category?: string;
  region?: string;
  priority?: string;
  received_at?: string;
  raw_text?: string;
  text?: string;
  summary?: string;
  description?: string;
  structured?: WorkbenchStructuredFields;
};

type PersistedRoutingInfo = {
  routingTrace?: RoutingTrace;
  strategyId?: string | null;
  routeKey?: string | null;
};

type DraftSnapshot = {
  draft?: QaResponseData & {
    complaintId?: string;
    structuredOutput?: {
      summary?: string;
      actionItems?: string[];
      requestSegments?: string[];
    };
    answer?: string;
  };
};

type DepartmentTrack = {
  admin_unit: string;
  complaint: string;
  answer: string;
  memoIndex?: number;
};

type AccordionDetail = {
  complaint: string;
  answer: string;
  tracks: DepartmentTrack[];
};

type MockWorkbenchSimilarCase = {
  case_id?: string;
  complaint?: string;
  answer?: string;
  department_tracks?: DepartmentTrack[];
};

function WorkbenchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlCaseId = searchParams.get("case_id");

  const [caseList, setCaseList] = useState<WorkbenchCase[]>(mockAssignedCases as WorkbenchCase[]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || mockAssignedCases[0]?.case_id || "");
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchRegion, setSearchRegion] = useState("전체");
  const [searchCategory, setSearchCategory] = useState("전체");
  const [searchStage, setSearchStage] = useState<SearchStage>("empty");
  const [searchBundle, setSearchBundle] = useState<SearchResponseData | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [, setRoutingTrace] = useState<RoutingTrace | null>(null);
  const [routingHint, setRoutingHint] = useState<RoutingHint | null>(null);
  const [, setStrategyId] = useState<string | null>(null);
  const [, setRouteKey] = useState<string | null>(null);
  const [draftStage, setDraftStage] = useState<DraftStage>("idle");
  const [draftResponse, setDraftResponse] = useState<QaResponseData | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftEditorValue, setDraftEditorValue] = useState("");
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);
  const [isRawCollapsed, setIsRawCollapsed] = useState(true);

  useEffect(() => {
    let isMounted = true;

    fetchUiCasesApi()
      .then((response) => {
        if (!isMounted || response.error) {
          return;
        }

        if (Array.isArray(response.data.cases) && response.data.cases.length > 0) {
          setCaseList(response.data.cases);
        }
      })
      .catch(() => {
        // keep the fallback mock list
      });

    return () => {
      isMounted = false;
    };
  }, [caseList]);

  const selectedCase = useMemo<WorkbenchCase>(() => {
    return (caseList.find((item) => item.case_id === selectedCaseId) || caseList[0]) as WorkbenchCase;
  }, [selectedCaseId, caseList]);

  const selectedIndex = useMemo(() => {
    return caseList.findIndex((item) => item.case_id === selectedCase.case_id);
  }, [selectedCase, caseList]);

  const caseContext = useMemo<WorkbenchCaseContext>(() => {
    return buildCaseContext(selectedCase);
  }, [selectedCase]);

  const regionOptions = useMemo(() => {
    return ["전체", ...Array.from(new Set(caseList.map((item) => item.region).filter(Boolean)))];
  }, [caseList]);

  const categoryOptions = useMemo(() => {
    return ["전체", ...Array.from(new Set(caseList.map((item) => item.category).filter(Boolean)))];
  }, [caseList]);

  useEffect(() => {
    if (caseList.length === 0) {
      return;
    }

    const selectedExists = caseList.some((item) => item.case_id === selectedCaseId);
    if (selectedExists) {
      return;
    }

    const nextSelectedId = urlCaseId && caseList.some((item) => item.case_id === urlCaseId) ? urlCaseId : caseList[0]?.case_id || "";
    if (nextSelectedId && nextSelectedId !== selectedCaseId) {
      setSelectedCaseId(nextSelectedId);
    }
  }, [caseList, selectedCaseId, urlCaseId]);

  useEffect(() => {
    const parsed = readJsonFromLocalStorage<Record<string, string>>(CASE_STATUS_STORAGE_KEY, {
      maxBytes: MAX_STATUS_STORAGE_BYTES,
      removeOnOversize: true,
    });

    if (parsed) {
      setCaseStatuses(sanitizeCaseStatuses(parsed, caseList.map((item) => item.case_id)));
    }
  }, [caseList]);

  useEffect(() => {
    if (urlCaseId && urlCaseId !== selectedCaseId) {
      setSelectedCaseId(urlCaseId);
    }
  }, [selectedCaseId, urlCaseId]);

  useEffect(() => {
    if (!selectedCase) {
      return;
    }

    setSearchQuery("");
    setSearchRegion(selectedCase.region || "전체");
    setSearchCategory(selectedCase.category || "전체");
    setSearchStage("empty");
    setSearchBundle(null);
    setSearchError(null);
    setRoutingTrace(null);
    setRoutingHint(null);
    setStrategyId(null);
    setRouteKey(null);
    setDraftStage("idle");
    setDraftResponse(null);
    setDraftError(null);
    setExpandedDocId(null);
    setIsRawCollapsed(true);
    // Clear draft snapshot when switching cases
    clearDraftSnapshot();
  }, [selectedCaseId, selectedCase]);

  // Restore persisted routing info and last draft when selecting a case + ensure center-right sync (no UI changes)
  useEffect(() => {
    try {
      const persisted = loadPersistedRoutingInfo() as PersistedRoutingInfo | null;
      const last = loadLastDraft() as DraftSnapshot | null;

      // Set default routing info based on selected case context for center-right sync
      const defaultInfo = buildDefaultRoutingInfoFromCase(selectedCase);
      setRoutingTrace(defaultInfo.routingTrace);
      setStrategyId(defaultInfo.strategyId);
      setRouteKey(defaultInfo.routeKey);

      // Override with persisted routing info if available
      if (persisted && persisted.routingTrace) {
        setRoutingTrace(persisted.routingTrace);
        setStrategyId(persisted.strategyId || null);
        setRouteKey(persisted.routeKey || null);
      }

      // Restore last draft if it matches selected case
      if (last && last.draft && last.draft.complaintId === selectedCase.case_id) {
        setDraftResponse(last.draft);
        setDraftStage("success");
        setDraftError(null);

        const respSegments = last.draft.structuredOutput?.requestSegments || [];
        const segMode: SegmentViewMode = respSegments.length > 1 ? "multi" : respSegments.length === 1 ? "single" : "empty";
        const textarea = buildDraftTextareaValue({
          draftStage: "success",
          segmentViewMode: segMode,
          answer: last.draft.answer,
          summary: last.draft.structuredOutput?.summary,
          actionItems: last.draft.structuredOutput?.actionItems || [],
          requestSegments: respSegments,
        });
        setDraftEditorValue(textarea);
      }
    } catch {
      // no-op: best-effort restore
    }
  }, [selectedCaseId, selectedCase]);

  function persistStatuses(nextStatuses: Record<string, string>) {
    const sanitized = sanitizeCaseStatuses(nextStatuses, caseList.map((item) => item.case_id));
    setCaseStatuses(sanitized);
    const serialized = JSON.stringify(sanitized);
    if (serialized.length > MAX_STATUS_STORAGE_BYTES) {
      window.localStorage.removeItem(CASE_STATUS_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(CASE_STATUS_STORAGE_KEY, serialized);
  }

  function navigateToCase(caseId: string) {
    if (caseId === selectedCaseId) {
      return;
    }
    setSelectedCaseId(caseId);
    router.replace(`/workbench?case_id=${encodeURIComponent(caseId)}`);
  }

  function handleStatusChange(newStatus: string) {
    const nextStatuses = { ...caseStatuses, [selectedCaseId]: newStatus };
    persistStatuses(nextStatuses);

    if ((newStatus === "처리완료" || newStatus === "검토중") && selectedIndex >= 0) {
      const nextCase = caseList[selectedIndex + 1];
      if (nextCase) {
        navigateToCase(nextCase.case_id);
      }
    }
  }

  function handleRefreshStatuses() {
    persistStatuses({});
  }

  async function handleSearch() {
    const query = searchQuery.trim();
    const effectiveQuery = query || buildDefaultQuery(selectedCase).trim();
    if (!effectiveQuery) {
      setSearchStage("empty");
      setSearchBundle(null);
      setSearchError(null);
      return;
    }

    setSearchStage("loading");
    setSearchError(null);
    setSearchBundle(null);
    setExpandedDocId(null);

    const response = await searchCasesApi({
      complaintId: selectedCase.case_id,
      query: effectiveQuery,
      topK: 5,
      filters: {
        region: searchRegion !== "전체" ? searchRegion : undefined,
        category: searchCategory !== "전체" ? searchCategory : undefined,
      },
      caseContext,
    });

    if (response.error) {
      setSearchStage("error");
      setSearchError(response.error.message);
      setRoutingTrace(null);
      setRoutingHint(null);
      setStrategyId(null);
      setRouteKey(null);
      return;
    }

    setSearchBundle(response.data);
    setRoutingTrace(response.data.routingTrace);
    setRoutingHint(response.data.routingHint);
    setStrategyId(response.data.strategyId);
    setRouteKey(response.data.routeKey);
    setSearchStage(response.data.retrievedDocs.length > 0 ? "success" : "empty");
  }

  async function handleGenerateDraft() {
    setDraftStage("loading");
    setDraftError(null);

    try {
      const response = await runQaApi({
        complaintId: selectedCase.case_id,
        query: searchBundle?.query || searchQuery || buildDefaultQuery(selectedCase),
        routingHint: routingHint || undefined,
        useSearchResults: Boolean(searchBundle?.results?.length || searchBundle?.searchResults?.length),
        searchResults: searchBundle?.results || searchBundle?.searchResults || [],
        filters: {
          region: searchRegion !== "전체" ? searchRegion : undefined,
          category: searchCategory !== "전체" ? searchCategory : undefined,
        },
        caseContext,
      });

      if (response.error) {
        setDraftStage("error");
        setDraftError(response.error.message);
        return;
      }

      setDraftStage("success");
      setDraftResponse(response.data);
      // Save draft snapshot for before/after comparison
      saveDraftSnapshot(response.data);
    } catch (error: unknown) {
      setDraftStage("error");
      setDraftError(error instanceof Error ? error.message : "초안 생성 중 오류가 발생했습니다.");
    }
  }

  const rawText = safeString(selectedCase?.raw_text || selectedCase?.text || selectedCase?.summary).trim();
  const structuredSummary = getCaseSummaryText(selectedCase) || "선택된 민원의 핵심 요약이 표시됩니다.";
  const summaryObservation = selectedCase.structured?.observation?.text || getCaseDisplayTitle(selectedCase, 80);
  const summaryAnalysis = selectedCase.structured?.result?.text || selectedCase.structured?.context?.text || structuredSummary || "분석 정보 없음";
  const summaryRequest = selectedCase.structured?.request?.text || selectedCase.summary || selectedCase.raw_text || "처리 요청 확인 필요";

  const responseSegments = draftResponse?.structuredOutput?.requestSegments || [];
  const fallbackSegments = buildFallbackSegments(selectedCase);
  const requestSegments = responseSegments.length > 0 ? responseSegments : fallbackSegments;
  const segmentViewMode: SegmentViewMode =
    draftStage === "loading"
      ? "loading"
      : draftStage === "error"
        ? "error"
        : draftStage === "success"
          ? requestSegments.length > 1
            ? "multi"
            : requestSegments.length === 1
              ? "single"
              : "empty"
          : "empty";

  const draftTextareaValue = buildDraftTextareaValue({
    draftStage,
    segmentViewMode,
    answer: draftResponse?.answer,
    summary: draftResponse?.structuredOutput?.summary,
    actionItems: draftResponse?.structuredOutput?.actionItems || [],
    requestSegments,
  });

  useEffect(() => {
    setDraftEditorValue(draftTextareaValue);
  }, [draftTextareaValue]);

  const currentStatus = caseStatuses[selectedCase.case_id] || selectedCase.status || "미처리";
  const topDocs = searchBundle?.results || searchBundle?.retrievedDocs || [];
  const isPreSearchState = searchStage === "empty" && topDocs.length === 0;

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen w-full">
        <AppSidebar activeMenu="workbench" />

        <main className="min-w-0 flex min-h-screen flex-1 flex-col px-6 py-3 lg:px-12 xl:px-16">
          <div className="flex items-center justify-between pb-3 text-sm font-semibold text-slate-700">
            <div>
              <button type="button" onClick={() => router.push("/")} className="hover:text-slate-900">민원 목록으로</button>
              <span className="mx-2 text-slate-300">|</span>
              <button type="button" onClick={() => router.push("/admin")} className="hover:text-slate-900">관리자 통계</button>
            </div>
            <div>상태: {currentStatus}</div>
          </div>

          <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <section className="flex flex-col border border-slate-300 bg-white">
              <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                <div className="text-sm font-bold text-slate-900">민원 목록</div>
                <button
                  type="button"
                  onClick={handleRefreshStatuses}
                  className="inline-flex h-8 w-8 items-center justify-center rounded border border-slate-300 bg-white text-slate-700 transition-colors hover:bg-slate-50 hover:text-slate-900"
                  aria-label="갱신"
                >
                  <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-4 w-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 10a6 6 0 0 1 10.2-4.2L16 7.6" />
                    <path d="M16 4.8v2.8h-2.8" />
                    <path d="M16 10a6 6 0 0 1-10.2 4.2L4 12.4" />
                    <path d="M4 15.2v-2.8h2.8" />
                  </svg>
                </button>
              </div>

              <div className="grid border-b border-slate-300 bg-[#e7ebf2] px-2 py-1.5 text-[11px] font-bold text-slate-700 items-center" style={{ gridTemplateColumns: "2.5fr 1fr 1fr 0.7fr 0.7fr", gridAutoRows: "2.5rem", gap: "0.75rem" }}>
                <div>제목</div>
                <div>접수일</div>
                <div>카테고리</div>
                <div>우선순위</div>
                <div>상태</div>
              </div>

              <div style={{ gridAutoRows: "2.5rem", gap: "0.75rem" }}>
                {caseList.map((item) => {
                  const status = caseStatuses[item.case_id] || item.status || "미처리";
                  const selected = item.case_id === selectedCase.case_id;
                  return (
                    <button
                      key={item.case_id}
                      type="button"
                      onClick={() => navigateToCase(item.case_id)}
                      className={`grid w-full border-b border-slate-200 px-2 py-1.5 text-left text-[12px] transition items-center ${selected ? "bg-white" : "bg-slate-100 hover:bg-slate-200"}`}
                      style={{ gridTemplateColumns: "2.5fr 1fr 1fr 0.7fr 0.7fr", gap: "0.75rem" }}
                    >
                      <div className="truncate font-semibold text-slate-800">{getCaseDisplayTitle(item, 30)}</div>
                      <div className="text-slate-600">{item.received_at || "-"}</div>
                      <div className="text-slate-600">{item.category}</div>
                      <div><PriorityBadge priority={item.priority || "보통"} /></div>
                      <div><StatusBadge status={status} /></div>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="flex min-h-0 flex-col gap-3">
              <div className="border border-slate-300 bg-white">
                <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="text-sm font-bold text-slate-900">원문 텍스트</div>
                  <button
                    type="button"
                    onClick={() => setIsRawCollapsed((prev) => !prev)}
                    className="text-xs font-semibold text-slate-500"
                    aria-label="원문 텍스트 접기/펼치기"
                  >
                    {isRawCollapsed ? "▶" : "▼"}
                  </button>
                </div>
                {!isRawCollapsed && (
                  <div className="px-3 py-2 text-sm leading-6 text-slate-700">{rawText.slice(0, 220) || "선택된 민원의 원문이 표시됩니다."}</div>
                )}
              </div>

              <div className="border border-slate-300 bg-white">
                <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="text-sm font-bold text-slate-900">민원 요약 (AI 분석)</div>
                  <span className="rounded-full border border-slate-300 bg-white px-2 py-0.5 text-xs font-bold text-slate-700">TOPIC: welfare / LEVEL: high</span>
                </div>
                <div className="grid border-b border-slate-300 bg-[#e7ebf2] px-3 py-2 text-[11px] font-bold text-slate-700" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  <div>관찰내용</div>
                  <div>문제분석</div>
                  <div>요청사항</div>
                </div>
                <div className="grid px-3 py-2 text-[12px] text-slate-700" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  <div className="truncate pr-2">{summaryObservation}</div>
                  <div className="truncate pr-2">{summaryAnalysis}</div>
                  <div className="truncate">{summaryRequest}</div>
                </div>
              </div>

              <div className="border border-slate-300 bg-white">
                <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="text-sm font-bold text-slate-900">답변 초안 및 비교</div>
                  <button
                    type="button"
                    onClick={handleGenerateDraft}
                    className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700"
                  >
                    초안
                  </button>
                </div>
                <div className="p-2">
                  <textarea
                    value={draftEditorValue}
                    onChange={(event) => setDraftEditorValue(event.target.value)}
                    className="h-44 w-full resize-none border border-slate-300 bg-slate-50 px-3 py-2 text-sm leading-7 text-slate-700 outline-none"
                  />
                  {draftError && <div className="mt-2 text-xs text-red-600">{draftError}</div>}
                </div>
              </div>

              <div className="border border-slate-300 bg-white">
                <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="text-sm font-bold text-slate-900">유사 민원 검색</div>
                  <button
                    type="button"
                    onClick={handleSearch}
                    className="inline-flex h-7 items-center whitespace-nowrap rounded border border-slate-300 bg-white px-2.5 text-[11px] font-semibold leading-none text-slate-700"
                  >
                    유사민원검색
                  </button>
                </div>

                <div className="grid gap-2 border-b border-slate-300 px-2 py-2 sm:grid-cols-[1fr_200px_200px]">
                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    className="h-9 border border-slate-300 px-2 text-sm outline-none"
                    placeholder="검색어"
                  />
                  <select
                    value={searchCategory}
                    onChange={(event) => setSearchCategory(event.target.value)}
                    className="h-9 border border-slate-300 px-2 text-sm outline-none"
                  >
                    {categoryOptions.map((category) => (
                      <option key={category} value={category}>{category}</option>
                    ))}
                  </select>
                  <select
                    value={searchRegion}
                    onChange={(event) => setSearchRegion(event.target.value)}
                    className="h-9 border border-slate-300 px-2 text-sm outline-none"
                  >
                    {regionOptions.map((region) => (
                      <option key={region} value={region}>{region}</option>
                    ))}
                  </select>
                </div>

                {searchStage === "error" && <div className="px-3 py-2 text-xs text-red-600">{searchError}</div>}

                <div>
                  {searchStage === "loading" ? (
                    <div className="px-3 py-4 text-sm text-slate-500">유사 민원을 검색 중입니다...</div>
                  ) : topDocs.length === 0 ? (
                    <div className={`flex items-center px-4 py-4 text-sm text-slate-500 ${isPreSearchState ? "min-h-32" : "min-h-24"}`}>
                      유사 민원 결과가 표시됩니다.
                    </div>
                  ) : (
                    topDocs.map((doc, index) => (
                      <div key={doc.docId} className="border-t border-slate-200">
                        <button
                          type="button"
                          onClick={() => setExpandedDocId((prev) => (prev === doc.docId ? null : doc.docId))}
                          className={`w-full px-3 py-2 text-left ${expandedDocId === doc.docId ? "bg-slate-50" : "hover:bg-slate-50"}`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-[11px] font-bold text-slate-700">유사민원 {index + 1}</div>
                              <div className="truncate text-[13px] font-semibold text-slate-900">{doc.title}</div>
                              <div className="line-clamp-1 text-[11px] text-slate-500">{doc.snippet}</div>
                            </div>
                            <div className="text-right text-[11px] text-slate-500">
                              <div className="font-bold text-slate-900">{Math.round(Number(doc.score) * 100)}%</div>
                              <div className="flex items-center justify-end gap-1">
                                <span>COMPLETED</span>
                                <span className="text-slate-400">{expandedDocId === doc.docId ? "▲" : "▼"}</span>
                              </div>
                            </div>
                          </div>
                        </button>

                        {expandedDocId === doc.docId && (
                          <div className="grid gap-2 border-t border-slate-200 bg-[#f7f9fc] px-2 py-2 md:grid-cols-[1.1fr_0.9fr]">
                            <div className="rounded border border-slate-300 bg-white p-2">
                              <div className="mb-1 text-[11px] font-bold text-slate-600">유사민원</div>
                              <div className="text-[12px] font-semibold text-slate-900">{getAccordionDetail(doc, index).complaint}</div>
                              <div className="mt-2 text-[12px] leading-6 text-slate-600">{getAccordionDetail(doc, index).answer}</div>
                            </div>
                            <div className="rounded border border-slate-300 bg-white p-2">
                              <div className="mb-1 text-[11px] font-bold text-slate-600">타부서 메모</div>
                              <div className="space-y-1">
                                {getAccordionDetail(doc, index).tracks.map((track: DepartmentTrack, memoIndex: number) => (
                                  <div key={`${doc.docId}-memo-${memoIndex}`} className="rounded border border-slate-200 bg-slate-50 p-2">
                                    <div className="flex items-center justify-between text-[11px] font-bold text-slate-700">
                                      <span>{track.admin_unit}</span>
                                      <span className="text-slate-400">메모 {memoIndex + 1}</span>
                                    </div>
                                    <div className="mt-1 text-[11px] text-slate-700">{track.complaint}</div>
                                    <div className="mt-1 text-[11px] leading-5 text-slate-500">{track.answer}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 pb-2">
                <button
                  type="button"
                  onClick={() => handleStatusChange("처리완료")}
                  className="inline-flex h-11 items-center justify-center whitespace-nowrap border-2 border-slate-900 bg-black px-3 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800"
                >
                  처리완료
                </button>
                <button
                  type="button"
                  onClick={() => handleStatusChange("검토중")}
                  className="inline-flex h-11 items-center justify-center whitespace-nowrap border-2 border-slate-900 bg-[#fafafa] px-3 text-sm font-bold text-slate-900 shadow-sm transition hover:bg-slate-50"
                >
                  검토중
                </button>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

export default function WorkbenchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50" />}>
      <WorkbenchContent />
    </Suspense>
  );
}

function buildCaseContext(caseItem: WorkbenchCase): WorkbenchCaseContext {
  return {
    caseId: caseItem.case_id,
    title: caseItem.title,
    category: caseItem.category,
    region: caseItem.region,
    summary: getCaseSummaryText(caseItem),
    priority: caseItem.priority,
  };
}

function buildDefaultRoutingInfoFromCase(caseItem: WorkbenchCase): { routingTrace: RoutingTrace; strategyId: string; routeKey: string } {
  const category = caseItem.category || "일반";
  const topic: TopicType = mapCategoryToTopicType(category);
  const complexityLevel: "low" | "medium" | "high" = "medium";

  const routingTrace: RoutingTrace = {
    topicType: topic,
    complexityLevel,
    complexityScore: 0.58,
    complexityTrace: {
      intent_count: 1,
      constraint_count: 1,
      entity_diversity: 1,
      policy_reference_count: 0,
      cross_sentence_dependency: false,
    },
    routeReason: `선택된 민원 카테고리(${category})를 기반으로 기본 라우팅 정보를 설정했습니다.`,
  };

  const routeKey = `${topic}/${complexityLevel}`;
  const strategyId = `topic_${topic}_${complexityLevel}_v1`;

  return { routingTrace, strategyId, routeKey };
}

function mapCategoryToTopicType(category: string): TopicType {
  const lower = (category || "").toLowerCase();
  if (lower.includes("주거") || lower.includes("복지")) return "welfare";
  if (lower.includes("교통")) return "traffic";
  if (lower.includes("환경")) return "environment";
  if (lower.includes("안전") || lower.includes("도로") || lower.includes("건설")) return "construction";
  return "general";
}

function buildDefaultQuery(caseItem: WorkbenchCase) {
  return getCaseSummaryText(caseItem) || getCaseDisplayTitle(caseItem, 120) || caseItem.raw_text || "";
}

function buildFallbackSegments(caseItem: WorkbenchCase): string[] {
  const request = caseItem?.structured?.request?.text;
  if (typeof request === "string" && request.trim().length > 0) {
    return [request.trim()];
  }
  return [];
}

function buildDraftTextareaValue(params: {
  draftStage: DraftStage;
  segmentViewMode: SegmentViewMode;
  answer?: string;
  summary?: string;
  actionItems: string[];
  requestSegments: string[];
}) {
  const { draftStage, segmentViewMode, answer, summary, actionItems, requestSegments } = params;

  if (draftStage === "loading") {
    return "초안 생성중입니다...";
  }

  if (draftStage === "error") {
    return answer || "초안 생성 중 오류가 발생했습니다. 다시 시도해주세요.";
  }

  if (segmentViewMode === "empty") {
    return answer || "여기에 내용을 입력하거나 AI가 생성한 초안을 편집하세요...";
  }

  if (segmentViewMode === "single") {
    const actionText = actionItems.length > 0 ? actionItems.map((item, idx) => `${idx + 1}. ${item}`).join("\n") : "1. 후속 조치 항목 없음";
    const segment = requestSegments[0] || "요청 항목 없음";
    return [
      "[단일 요청 모드]",
      `요청: ${segment}`,
      `요약: ${summary || "요약 정보 없음"}`,
      "조치 항목:",
      actionText,
      "",
      answer || "초안 답변 없음",
    ].join("\n");
  }

  const multiSegmentText = requestSegments
    .map((segment, idx) => {
      const action = actionItems[idx] || "조치 항목 미정";
      return `- Segment ${idx + 1}: ${segment}\n  · Action: ${action}`;
    })
    .join("\n");

  return [
    "[복합 요청 모드]",
    `요약: ${summary || "요약 정보 없음"}`,
    "세그먼트:",
    multiSegmentText || "- 세그먼트 정보 없음",
    "",
    answer || "초안 답변 없음",
  ].join("\n");
}

function getCaseDisplayTitle(caseItem: WorkbenchCase, maxLength: number = 48) {
  if (caseItem.title && String(caseItem.title).trim().length > 0) {
    return sanitizeTitle(String(caseItem.title)).slice(0, maxLength);
  }
  if (caseItem.structured?.observation?.text) {
    return sanitizeTitle(String(caseItem.structured.observation.text)).slice(0, maxLength);
  }
  if (caseItem.summary && String(caseItem.summary).trim().length > 0) {
    return sanitizeTitle(String(caseItem.summary)).slice(0, maxLength);
  }
  const fallback = caseItem.raw_text || "제목 없음 민원";
  return sanitizeTitle(String(fallback)).slice(0, maxLength);
}

function getCaseSummaryText(caseItem: WorkbenchCase) {
  const observation = caseItem.structured?.observation?.text;
  const result = caseItem.structured?.result?.text || caseItem.structured?.context?.text;
  const request = caseItem.structured?.request?.text;

  const parts = [observation, result, request].filter((value) => typeof value === "string" && value.trim().length > 0);
  if (parts.length > 0) {
    return parts.join(" / ");
  }

  return caseItem.summary || caseItem.description || caseItem.raw_text || "";
}

function sanitizeTitle(value: string) {
  return value.split(" - ")[0].trim();
}

function getAccordionDetail(doc: RetrievedDoc, index: number): AccordionDetail {
  const answersByAdminUnit = doc.answers_by_admin_unit || doc.department_answers || {};
  const complaint = doc.summary?.observation || doc.title;
  const answer = doc.summary?.request || doc.snippet || "유사 민원 상세가 없습니다.";
  const tracks: DepartmentTrack[] = Object.entries(answersByAdminUnit).map(([adminUnit, departmentAnswer], memoIndex) => ({
    admin_unit: adminUnit,
    complaint: complaint || doc.title,
    answer: departmentAnswer || answer,
    memoIndex,
  }));

  if (tracks.length > 0) {
    return {
      complaint: complaint || doc.title,
      answer,
      tracks,
    };
  }

  const fallbackDetail = mockWorkbenchSimilarCases[index % mockWorkbenchSimilarCases.length] as MockWorkbenchSimilarCase | undefined;
  const matched = (mockWorkbenchSimilarCases.find((item) => item.case_id === doc.caseId) as MockWorkbenchSimilarCase | undefined) || fallbackDetail;

  return {
    complaint: matched?.complaint || complaint || doc.title,
    answer: matched?.answer || answer,
    tracks: matched?.department_tracks?.length
      ? matched.department_tracks
      : [
          {
            admin_unit: "참고부서",
            complaint: doc.title,
            answer: doc.snippet || "추가 메모가 없습니다.",
          },
        ],
  };
}


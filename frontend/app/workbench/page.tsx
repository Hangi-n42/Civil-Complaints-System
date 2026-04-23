"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mockAssignedCases, mockWorkbenchSimilarCases } from "@/lib/mockData";
import AppSidebar from "@/components/AppSidebar";
import {
  type RoutingHint,
  type RoutingTrace,
  runQaApi,
  searchCasesApi,
  type QaResponseData,
  type RetrievedDoc,
  type SearchResponseData,
  type WorkbenchCaseContext,
} from "@/lib/api";
import { PriorityBadge, StatusBadge } from "@/components/SearchUI";

const CASE_STATUS_STORAGE_KEY = "case-status-overrides";
const STATUS_OPTIONS = ["미처리", "검토중", "처리완료"] as const;
const DEFAULT_CASE_LIST = mockAssignedCases as Array<any>;
const MAX_STATUS_STORAGE_BYTES = 24 * 1024;

type SearchStage = "empty" | "loading" | "success" | "error";
type DraftStage = "idle" | "loading" | "success" | "error";
type SegmentViewMode = "loading" | "error" | "empty" | "single" | "multi";

function WorkbenchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlCaseId = searchParams.get("case_id");

  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || DEFAULT_CASE_LIST[0]?.case_id || "");
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchRegion, setSearchRegion] = useState("전체");
  const [searchCategory, setSearchCategory] = useState("전체");
  const [searchStage, setSearchStage] = useState<SearchStage>("empty");
  const [searchBundle, setSearchBundle] = useState<SearchResponseData | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [routingTrace, setRoutingTrace] = useState<RoutingTrace | null>(null);
  const [routingHint, setRoutingHint] = useState<RoutingHint | null>(null);
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [routeKey, setRouteKey] = useState<string | null>(null);
  const [draftStage, setDraftStage] = useState<DraftStage>("idle");
  const [draftResponse, setDraftResponse] = useState<QaResponseData | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftEditorValue, setDraftEditorValue] = useState("");
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);
  const [isRawCollapsed, setIsRawCollapsed] = useState(true);

  const selectedCase = useMemo(() => {
    return DEFAULT_CASE_LIST.find((item) => item.case_id === selectedCaseId) || DEFAULT_CASE_LIST[0];
  }, [selectedCaseId]);

  const selectedIndex = useMemo(() => {
    return DEFAULT_CASE_LIST.findIndex((item) => item.case_id === selectedCase.case_id);
  }, [selectedCase]);

  const caseContext = useMemo<WorkbenchCaseContext>(() => {
    return buildCaseContext(selectedCase);
  }, [selectedCase]);

  const regionOptions = useMemo(() => {
    return ["전체", ...Array.from(new Set(DEFAULT_CASE_LIST.map((item) => item.region).filter(Boolean)))];
  }, []);

  const categoryOptions = useMemo(() => {
    return ["전체", ...Array.from(new Set(DEFAULT_CASE_LIST.map((item) => item.category).filter(Boolean)))];
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(CASE_STATUS_STORAGE_KEY);
      if (!raw) {
        return;
      }
      if (raw.length > MAX_STATUS_STORAGE_BYTES) {
        window.localStorage.removeItem(CASE_STATUS_STORAGE_KEY);
        setCaseStatuses({});
        return;
      }
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        setCaseStatuses(sanitizeCaseStatuses(parsed as Record<string, string>));
      }
    } catch {
      setCaseStatuses({});
    }
  }, []);

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
  }, [selectedCaseId, selectedCase]);

  function persistStatuses(nextStatuses: Record<string, string>) {
    const sanitized = sanitizeCaseStatuses(nextStatuses);
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

    if (newStatus === "처리완료" && selectedIndex >= 0) {
      const nextCase = DEFAULT_CASE_LIST[selectedIndex + 1];
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
      setSearchError(response.error);
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
        useSearchResults: Boolean(searchBundle?.searchResults?.length),
        searchResults: searchBundle?.searchResults || [],
        filters: {
          region: searchRegion !== "전체" ? searchRegion : undefined,
          category: searchCategory !== "전체" ? searchCategory : undefined,
        },
        caseContext,
      });

      if (response.error) {
        setDraftStage("error");
        setDraftError(response.error);
        return;
      }

      setDraftStage("success");
      setDraftResponse(response.data);
    } catch (error: any) {
      setDraftStage("error");
      setDraftError(error?.message || "초안 생성 중 오류가 발생했습니다.");
    }
  }

  const rawText = selectedCase.raw_text || selectedCase.text || selectedCase.summary || "";
  const structuredSummary = getCaseSummaryText(selectedCase) || "선택된 민원의 핵심 요약이 표시됩니다.";
  const summaryObservation = selectedCase.structured?.observation?.text || getCaseDisplayTitle(selectedCase, 80);
  const summaryAnalysis = selectedCase.structured?.result?.text || selectedCase.structured?.context?.text || structuredSummary || "분석 정보 없음";
  const summaryRequest = selectedCase.structured?.request?.text || selectedCase.request || "처리 요청 확인 필요";

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
  const topDocs = searchBundle?.retrievedDocs || [];
  const isPreSearchState = searchStage === "empty" && topDocs.length === 0;
  const hasSearchResults = topDocs.length > 0;

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen w-full">
        <AppSidebar activeMenu="workbench" />

        <main className="min-w-0 flex h-screen flex-1 flex-col px-6 py-3 lg:px-12 xl:px-16">
          <div className="flex items-center justify-between pb-3 text-sm font-semibold text-slate-700">
            <div>
              <button type="button" onClick={() => router.push("/")} className="hover:text-slate-900">민원 목록으로</button>
              <span className="mx-2 text-slate-300">|</span>
              <button type="button" onClick={() => router.push("/admin")} className="hover:text-slate-900">관리자 통계</button>
            </div>
            <div>상태: {currentStatus}</div>
          </div>

          <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,0.88fr)_minmax(720px,1.12fr)]">
            <section className="flex h-full min-h-0 flex-col overflow-hidden border border-slate-300 bg-white">
              <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                <div className="text-sm font-bold text-slate-900">민원 목록</div>
                <button
                  type="button"
                  onClick={handleRefreshStatuses}
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700"
                >
                  갱신
                </button>
              </div>

              <div className="grid border-b border-slate-300 bg-[#e7ebf2] px-2 py-2 text-[11px] font-bold text-slate-700" style={{ gridTemplateColumns: "2.05fr 0.95fr 0.75fr 0.55fr 0.55fr" }}>
                <div>제목</div>
                <div>접수일</div>
                <div>카테고리</div>
                <div>우선순위</div>
                <div>상태</div>
              </div>

              <div className="min-h-0 flex-1 overflow-auto">
                {DEFAULT_CASE_LIST.map((item) => {
                  const status = caseStatuses[item.case_id] || item.status || "미처리";
                  const selected = item.case_id === selectedCase.case_id;
                  return (
                    <button
                      key={item.case_id}
                      type="button"
                      onClick={() => navigateToCase(item.case_id)}
                      className={`grid w-full border-b border-slate-200 px-2 py-3 text-left text-[12px] transition ${selected ? "bg-white" : "bg-slate-100 hover:bg-slate-200"}`}
                      style={{ gridTemplateColumns: "2.05fr 0.95fr 0.75fr 0.55fr 0.55fr" }}
                    >
                      <div className="truncate pr-2 font-semibold text-slate-800">{getCaseDisplayTitle(item, 30)}</div>
                      <div className="text-slate-600">{item.received_at || item.created_at || item.date || "-"}</div>
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
                    className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700"
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

                <div
                  className={hasSearchResults ? "overflow-auto" : "overflow-hidden"}
                  style={{
                    maxHeight: hasSearchResults ? "420px" : "320px",
                    minHeight: hasSearchResults ? "280px" : "300px",
                  }}
                >
                  {searchStage === "loading" ? (
                    <div className="px-3 py-4 text-sm text-slate-500">유사 민원을 검색 중입니다...</div>
                  ) : topDocs.length === 0 ? (
                    <div className={`flex items-center px-4 text-sm text-slate-500 ${isPreSearchState ? "min-h-72" : "min-h-64"}`}>
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
                                {getAccordionDetail(doc, index).tracks.map((track: any, memoIndex: number) => (
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

              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => handleStatusChange("처리완료")}
                  className="h-12 border-2 border-slate-900 bg-black text-sm font-bold text-white shadow-sm transition hover:bg-slate-800"
                >
                  처리완료
                </button>
                <button
                  type="button"
                  onClick={() => handleStatusChange("검토중")}
                  className="h-12 border-2 border-slate-900 bg-[#fafafa] text-sm font-bold text-slate-900 shadow-sm transition hover:bg-slate-50"
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

function buildCaseContext(caseItem: any): WorkbenchCaseContext {
  return {
    caseId: caseItem.case_id,
    title: caseItem.title,
    category: caseItem.category,
    region: caseItem.region,
    summary: getCaseSummaryText(caseItem),
    priority: caseItem.priority,
  };
}

function buildDefaultQuery(caseItem: any) {
  return getCaseSummaryText(caseItem) || getCaseDisplayTitle(caseItem, 120) || caseItem.raw_text || "";
}

function buildDraftPrompt(caseItem: any, query: string) {
  return [
    `민원 제목: ${getCaseDisplayTitle(caseItem, 120)}`,
    `카테고리: ${caseItem.category}`,
    `지역: ${caseItem.region}`,
    `검색어: ${query}`,
    `핵심 요약: ${getCaseSummaryText(caseItem)}`,
  ].join("\n");
}

function formatComplexityTrace(trace: Record<string, number | boolean>) {
  const intent = trace.intent_count;
  const constraint = trace.constraint_count;
  const entity = trace.entity_diversity;
  const cross = trace.cross_sentence_dependency;
  return `의도 ${intent ?? "-"}, 제약 ${constraint ?? "-"}, 엔티티 ${entity ?? "-"}, 문장연계 ${cross === true ? "Y" : cross === false ? "N" : "-"}`;
}

function buildFallbackSegments(caseItem: any): string[] {
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

function getCaseDisplayTitle(caseItem: any, maxLength: number = 48) {
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

function getCaseSummaryText(caseItem: any) {
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

function getAccordionDetail(doc: RetrievedDoc, index: number) {
  const fallbackDetail = mockWorkbenchSimilarCases[index % mockWorkbenchSimilarCases.length];
  const matched = mockWorkbenchSimilarCases.find((item) => item.case_id === doc.caseId) || fallbackDetail;

  return {
    complaint: matched?.complaint || doc.title,
    answer: matched?.answer || doc.snippet || "유사 민원 상세가 없습니다.",
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

function sanitizeCaseStatuses(value: Record<string, string>): Record<string, string> {
  const allowedCaseIds = new Set(DEFAULT_CASE_LIST.map((item) => item.case_id));
  const allowedStatuses = new Set<string>(STATUS_OPTIONS);
  const sanitized: Record<string, string> = {};

  for (const [caseId, status] of Object.entries(value || {})) {
    if (!allowedCaseIds.has(caseId)) {
      continue;
    }
    if (!allowedStatuses.has(String(status))) {
      continue;
    }
    sanitized[caseId] = status;
  }

  return sanitized;
}

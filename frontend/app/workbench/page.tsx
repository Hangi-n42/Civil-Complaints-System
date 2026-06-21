"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AppSidebar from "@/components/AppSidebar";
import {
  type RoutingHint,
  type RoutingTrace,
  type TopicType,
  type CivilCategory,
  fetchUiCasesApi,
  type AssignedCase,
  streamQaApi,
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
import { loadCaseStatusOverrides, persistCaseStatusSubset } from "@/lib/caseStatus";
import { safeString } from "@/lib/safe-data";
import { confidenceBand, firstEvidence, validResponsibleUnits, reviewAssignment, buildTransferMemo, type ResponsibleUnit } from "@/lib/responsibleUnit";
import {
  buildDraftTextareaValue,
  computeSegmentViewMode,
  pairSegmentsWithActions,
  selectDraftRequestSegments,
  hashQuery,
  isDraftStale,
  type DraftStage,
  type SegmentViewMode,
  type SupplementarySegment,
  type SegmentAnswerCard,
} from "@/lib/draft";

type SearchStage = "empty" | "loading" | "success" | "error";

// 초안 생성 진행 단계. 백엔드 /qa/stream SSE가 보내는 실제 단계를 그대로 표시한다(타이머 추정 아님).
// 라벨은 백엔드 QA_STAGE_LABELS와 1:1로 일치한다(retrieving/grounding/generating).
const DRAFT_PROGRESS_STAGES = ["유사 사례 분석 중", "관련 근거 정리 중", "초안 작성 중"] as const;
// 백엔드 SSE 단계명 → 진행 표시 인덱스.
const QA_STAGE_TO_STEP: Record<string, number> = { retrieving: 0, grounding: 1, generating: 2 };

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
  category_display?: string;
  civil_category?: CivilCategory;
  region?: string;
  priority?: string;
  received_at?: string;
  raw_text?: string;
  text?: string;
  summary?: string;
  description?: string;
  request_segments?: string[];
  requestSegments?: string[];
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
  request: string;
  answer: string;
  hasAnswer: boolean;
  caseId: string;
  receivedAt: string;
  category: string;
  region: string;
  tracks: DepartmentTrack[];
};

function WorkbenchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlCaseId = searchParams.get("case_id");

  const [caseList, setCaseList] = useState<WorkbenchCase[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(urlCaseId || "");
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [searchStage, setSearchStage] = useState<SearchStage>("empty");
  const [searchBundle, setSearchBundle] = useState<SearchResponseData | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [routingTrace, setRoutingTrace] = useState<RoutingTrace | null>(null);
  const [routingHint, setRoutingHint] = useState<RoutingHint | null>(null);
  const [, setStrategyId] = useState<string | null>(null);
  const [, setRouteKey] = useState<string | null>(null);
  const [draftStage, setDraftStage] = useState<DraftStage>("idle");
  const [draftResponse, setDraftResponse] = useState<QaResponseData | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftEditorValue, setDraftEditorValue] = useState("");
  const [draftProgressStep, setDraftProgressStep] = useState(0);
  // 이슈 #451: 초안을 만든 쿼리의 해시. 이후 다른 쿼리로 재검색하면 화면 초안이 stale임을 표시한다.
  const [draftQueryHash, setDraftQueryHash] = useState<string | null>(null);
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);
  const [isRawCollapsed, setIsRawCollapsed] = useState(false);

  useEffect(() => {
    let isMounted = true;

    fetchUiCasesApi()
      .then((response) => {
        if (!isMounted) {
          return;
        }

        // fetchUiCasesApi는 백엔드 오류·빈 응답이면 목업으로 폴백하므로 결과를 그대로 사용한다.
        setCaseList(response.data.cases);
      })
      .finally(() => {
        if (isMounted) {
          setCasesLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const selectedCase = useMemo<WorkbenchCase>(() => {
    // 로딩 중(caseList 비어있음)에도 selectedCase가 undefined가 되지 않도록 빈 케이스로 폴백한다.
    return (caseList.find((item) => item.case_id === selectedCaseId) || caseList[0] || { case_id: "" }) as WorkbenchCase;
  }, [selectedCaseId, caseList]);

  const selectedIndex = useMemo(() => {
    return caseList.findIndex((item) => item.case_id === selectedCase.case_id);
  }, [selectedCase, caseList]);

  const caseContext = useMemo<WorkbenchCaseContext>(() => {
    return buildCaseContext(selectedCase);
  }, [selectedCase]);

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
      router.replace(`/workbench?case_id=${encodeURIComponent(nextSelectedId)}`);
    }
  }, [caseList, router, selectedCaseId, urlCaseId]);

  useEffect(() => {
    setCaseStatuses(loadCaseStatusOverrides(caseList.map((item) => item.case_id)));
  }, [caseList]);

  useEffect(() => {
    if (urlCaseId && urlCaseId !== selectedCaseId && caseList.some((item) => item.case_id === urlCaseId)) {
      setSelectedCaseId(urlCaseId);
    }
  }, [caseList, selectedCaseId, urlCaseId]);

  useEffect(() => {
    if (!selectedCase) {
      return;
    }

    setSearchQuery("");
    setSearchStage("empty");
    setSearchBundle(null);
    setSearchError(null);
    setRoutingTrace(null);
    setRoutingHint(null);
    setStrategyId(null);
    setRouteKey(null);
    setDraftStage("idle");
    setDraftResponse(null);
    setDraftQueryHash(null);
    setDraftError(null);
    setExpandedDocId(null);
    setIsRawCollapsed(false);
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

      // Restore last draft if it matches selected case.
      // 편집 textarea 값(answer)은 draftTextareaValue useEffect가 단일 소스로 채우므로 여기선 응답 상태만 복원한다(이슈 #388, AC5).
      if (last && last.draft && last.draft.complaintId === selectedCase.case_id) {
        setDraftResponse(last.draft);
        setDraftStage("success");
        setDraftError(null);
      }
    } catch {
      // no-op: best-effort restore
    }
  }, [selectedCaseId, selectedCase]);

  function persistStatuses(nextStatuses: Record<string, string>) {
    const sanitized = persistCaseStatusSubset(nextStatuses, caseList.map((item) => item.case_id));
    setCaseStatuses(sanitized);
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

  // 유사 민원 검색을 실행하고 결과 번들을 반환한다.
  // /qa가 검색 단계의 routing_hint를 필수로 요구하므로 초안 생성에서도 재사용한다.
  async function runSearch(): Promise<SearchResponseData | null> {
    const query = searchQuery.trim();
    const effectiveQuery = query || buildDefaultQuery(selectedCase).trim();
    if (!effectiveQuery) {
      setSearchStage("empty");
      setSearchBundle(null);
      setSearchError(null);
      return null;
    }

    setSearchStage("loading");
    setSearchError(null);
    setSearchBundle(null);
    setExpandedDocId(null);

    const response = await searchCasesApi({
      complaintId: selectedCase.case_id,
      query: effectiveQuery,
      topK: 5,
      caseContext,
    });

    if (response.error) {
      setSearchStage("error");
      setSearchError(response.error.message);
      setRoutingTrace(null);
      setRoutingHint(null);
      setStrategyId(null);
      setRouteKey(null);
      return null;
    }

    setSearchBundle(response.data);
    setRoutingTrace(response.data.routingTrace);
    setRoutingHint(response.data.routingHint);
    setStrategyId(response.data.strategyId);
    setRouteKey(response.data.routeKey);
    setSearchStage(response.data.retrievedDocs.length > 0 ? "success" : "empty");
    return response.data;
  }

  async function handleSearch() {
    await runSearch();
  }

  async function handleGenerateDraft() {
    setDraftStage("loading");
    setDraftError(null);
    setDraftProgressStep(0);

    try {
      // 검색이 선행되지 않았으면 유사 민원 검색을 자동으로 먼저 수행한다.
      // (/qa는 검색이 만들어내는 routing_hint가 없으면 400으로 실패하기 때문이다.)
      let bundle = searchBundle;
      if (!bundle || !routingHint) {
        bundle = await runSearch();
      }

      const effectiveRoutingHint = bundle?.routingHint || routingHint || undefined;
      if (!effectiveRoutingHint) {
        setDraftStage("error");
        setDraftError("유사 민원 검색에 실패해 초안을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.");
        return;
      }

      // 초안을 만든 쿼리를 stale 검사용으로 기억해 둔다(아래 성공 분기에서 해시 저장).
      const generationQuery = bundle?.query || searchQuery || buildDefaultQuery(selectedCase);
      const response = await streamQaApi(
        {
          complaintId: selectedCase.case_id,
          query: generationQuery,
          routingHint: effectiveRoutingHint,
          routingTrace: bundle?.routingTrace || routingTrace || undefined,
          useSearchResults: Boolean(bundle?.results?.length || bundle?.searchResults?.length),
          searchResults: bundle?.results || bundle?.searchResults || [],
          caseContext,
        },
        // 백엔드가 보내는 실제 단계로 진행도를 갱신한다.
        (stage) => setDraftProgressStep(QA_STAGE_TO_STEP[stage] ?? 0),
      );

      if (response.error) {
        setDraftStage("error");
        setDraftError(response.error.message);
        return;
      }

      setDraftStage("success");
      setDraftResponse(response.data);
      setDraftQueryHash(hashQuery(generationQuery));
      // Save draft snapshot for before/after comparison
      saveDraftSnapshot(response.data);
    } catch (error: unknown) {
      setDraftStage("error");
      setDraftError(error instanceof Error ? error.message : "초안 생성 중 오류가 발생했습니다.");
    }
  }

  const rawText = formatMaskedText(safeString(selectedCase?.raw_text || selectedCase?.text || selectedCase?.summary)).trim();
  const structuredSummary = formatMaskedText(getCaseSummaryText(selectedCase)) || "선택된 민원의 핵심 요약이 표시됩니다.";
  const summaryObservation = formatMaskedText(selectedCase.structured?.observation?.text || getCaseDisplayTitle(selectedCase, 80));
  const summaryAnalysis = formatMaskedText(selectedCase.structured?.result?.text || selectedCase.structured?.context?.text || structuredSummary || "분석 정보 없음");
  const summaryRequest = formatMaskedText(selectedCase.structured?.request?.text || selectedCase.summary || selectedCase.raw_text || "처리 요청 확인 필요");

  const responseSegments = draftResponse?.structuredOutput?.requestSegments || [];
  const fallbackSegments = buildFallbackSegments(selectedCase);
  const requestSegments = selectDraftRequestSegments({ responseSegments, fallbackSegments });
  const segmentViewMode = computeSegmentViewMode({ draftStage, segmentCount: requestSegments.length });
  const supplementarySegments = pairSegmentsWithActions(requestSegments, draftResponse?.structuredOutput?.actionItems || []);
  const draftSummary = draftResponse?.structuredOutput?.summary || "";
  // 이슈 #451: 요청별 답변·근거. 비면([]) 패널은 기존 세그먼트/조치 표시로 폴백한다.
  const segmentAnswers = draftResponse?.structuredOutput?.segmentAnswers ?? [];
  // 화면에 떠 있는 검색 결과의 쿼리와 초안을 만든 쿼리가 어긋나면 stale 경고를 띄운다.
  const draftIsStale =
    draftStage === "success" &&
    isDraftStale({ draftQueryHash, searchQueryHash: searchBundle ? hashQuery(searchBundle.query) : null });

  // 공식 회신문 편집값은 answer만 사용한다(이슈 #388). 보조 메타데이터는 DraftSupplementaryPanel에서만 표시한다.
  const draftTextareaValue = buildDraftTextareaValue({ draftStage, answer: draftResponse?.answer });

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
                <div className="text-sm font-bold text-slate-900">처리대기 민원</div>
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
                <div>문의 요지</div>
                <div>접수일</div>
                <div>카테고리</div>
                <div>우선순위</div>
                <div>상태</div>
              </div>

              <div style={{ gridAutoRows: "2.5rem", gap: "0.75rem" }}>
                {casesLoading
                  ? [0, 1, 2, 3, 4, 5].map((i) => (
                      <div
                        key={`skeleton-${i}`}
                        className="grid w-full animate-pulse items-center border-b border-slate-200 px-2 py-1.5"
                        style={{ gridTemplateColumns: "2.5fr 1fr 1fr 0.7fr 0.7fr", gap: "0.75rem" }}
                      >
                        <div className="h-3 w-4/5 rounded bg-slate-200" />
                        <div className="h-3 w-3/5 rounded bg-slate-200" />
                        <div className="h-3 w-3/5 rounded bg-slate-200" />
                        <div className="h-4 w-10 rounded bg-slate-200" />
                        <div className="h-4 w-10 rounded bg-slate-200" />
                      </div>
                    ))
                  : caseList.map((item) => {
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
                      <div className="truncate font-semibold text-slate-800">{formatMaskedText(getCaseDisplayTitle(item, 30))}</div>
                      <div className="text-slate-600">{formatReceivedDate(item.received_at)}</div>
                      <div className="truncate text-slate-600" title={getCaseCategoryLabel(item)}>{getCaseCategoryPrimary(item)}</div>
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
                <div className="flex items-center justify-between gap-2 border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="shrink-0 text-sm font-bold text-slate-900">민원 요약 (AI 분석)</div>
                    <span className="truncate rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-800" title={getCaseCategoryLabel(selectedCase)}>분야: {getCaseCategoryLabel(selectedCase)}</span>
                  </div>
                </div>
                <div className="grid gap-x-3 border-b border-slate-300 bg-[#e7ebf2] px-3 py-2 text-[11px] font-bold text-slate-700" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  <div>요약</div>
                  <div>핵심요청</div>
                  <div>확인필요</div>
                </div>
                <div className="grid items-start gap-x-3 px-3 py-2 text-[12px] leading-5 text-slate-700" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  <div className="break-words">{summaryObservation}</div>
                  <div className="break-words">{summaryAnalysis}</div>
                  <div className="break-words">{summaryRequest}</div>
                </div>
              </div>

              <ResponsibleUnitCard
                units={selectedCase.structured?.responsible_unit}
                assignee={selectedCase.assignee}
                caseTitle={selectedCase.title || getCaseDisplayTitle(selectedCase)}
                observation={summaryObservation}
                request={summaryRequest}
              />

              <div className="border border-slate-300 bg-white">
                <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2">
                  <div className="text-sm font-bold text-slate-900">답변 초안 및 비교</div>
                  <button
                    type="button"
                    onClick={handleGenerateDraft}
                    disabled={draftStage === "loading"}
                    className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {draftStage === "loading" ? (
                      <>
                        <Spinner className="h-3.5 w-3.5 text-slate-500" />
                        생성 중…
                      </>
                    ) : (
                      "초안"
                    )}
                  </button>
                </div>
                <div className="p-2">
                  {draftStage === "loading" ? (
                    <DraftLoadingState step={draftProgressStep} referenceCount={topDocs.length} />
                  ) : (
                    <textarea
                      value={draftEditorValue}
                      onChange={(event) => setDraftEditorValue(event.target.value)}
                      placeholder="여기에 내용을 입력하거나 AI가 생성한 초안을 편집하세요..."
                      className="h-44 w-full resize-none border border-slate-300 bg-slate-50 px-3 py-2 text-sm leading-7 text-slate-700 outline-none"
                    />
                  )}
                  {draftError && <div className="mt-2 text-xs text-red-600">{draftError}</div>}
                  {draftStage === "success" && (segmentViewMode === "single" || segmentViewMode === "multi") && (
                    <DraftSupplementaryPanel
                      mode={segmentViewMode}
                      summary={draftSummary}
                      segments={supplementarySegments}
                      segmentAnswers={segmentAnswers}
                      stale={draftIsStale}
                    />
                  )}
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

                <div className="border-b border-slate-300 px-2 py-2">
                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    className="h-9 w-full border border-slate-300 px-2 text-sm outline-none"
                    placeholder="검색어"
                  />
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
                    topDocs.map((doc, index) => {
                      const detail = getAccordionDetail(doc);
                      const receivedDate = formatReceivedDate(detail.receivedAt);
                      const answerText = detail.hasAnswer ? detail.answer : "저장된 과거 답변이 없습니다.";

                      return (
                        <div key={doc.docId} className="border-t border-slate-200">
                          <button
                            type="button"
                            onClick={() => setExpandedDocId((prev) => (prev === doc.docId ? null : doc.docId))}
                            className={`w-full px-3 py-2 text-left ${expandedDocId === doc.docId ? "bg-slate-50" : "hover:bg-slate-50"}`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <div className="text-[11px] font-bold text-slate-700">유사민원 {index + 1}</div>
                                <div className="line-clamp-2 break-words text-[13px] font-semibold text-slate-900" title={detail.complaint}>{detail.complaint}</div>
                                {detail.request && (
                                  <div className="mt-1 line-clamp-1 break-words text-[11px] leading-4 text-slate-500" title={detail.request}>
                                    요청사항: {detail.request}
                                  </div>
                                )}
                                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-4 text-slate-500">
                                  <span>접수일 {receivedDate}</span>
                                  {detail.category !== "-" && <span>분야 {detail.category}</span>}
                                  {detail.region !== "-" && <span>지역 {detail.region}</span>}
                                  {!detail.hasAnswer && <span className="text-slate-400">답변 없음</span>}
                                </div>
                              </div>
                              <div className="shrink-0 text-[11px] text-slate-400">
                                {expandedDocId === doc.docId ? "▲" : "▼"}
                              </div>
                            </div>
                          </button>

                          {expandedDocId === doc.docId && (
                            <div className="grid gap-3 border-t border-slate-200 bg-[#f7f9fc] px-3 py-3 md:grid-cols-[0.9fr_1.1fr]">
                              <div className="rounded border border-slate-300 bg-white p-3">
                                <div className="mb-2 text-[11px] font-bold text-slate-600">유사민원 정보</div>
                                <div className="break-words text-[13px] font-bold leading-6 text-slate-900">{detail.complaint}</div>
                                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] leading-5 text-slate-600">
                                  <div>
                                    <span className="font-bold text-slate-500">사건번호</span>
                                    <div className="break-words text-slate-800">{detail.caseId}</div>
                                  </div>
                                  <div>
                                    <span className="font-bold text-slate-500">접수일</span>
                                    <div className="text-slate-800" title={detail.receivedAt}>{receivedDate}</div>
                                  </div>
                                  <div>
                                    <span className="font-bold text-slate-500">분야</span>
                                    <div className="break-words text-slate-800">{detail.category}</div>
                                  </div>
                                  <div>
                                    <span className="font-bold text-slate-500">지역</span>
                                    <div className="break-words text-slate-800">{detail.region}</div>
                                  </div>
                                </div>
                                {detail.request && (
                                  <div className="mt-3 border-t border-slate-200 pt-2">
                                    <div className="text-[11px] font-bold text-slate-500">요청사항</div>
                                    <div className="mt-1 whitespace-pre-line break-words text-[12px] leading-6 text-slate-700">{detail.request}</div>
                                  </div>
                                )}
                              </div>
                              <div className="rounded border border-blue-200 bg-white p-3">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <div className="text-[11px] font-bold text-blue-700">해당 유사민원 답변</div>
                                  {detail.hasAnswer && <div className="text-[11px] font-semibold text-slate-400">저장됨</div>}
                                </div>
                                <div className={`min-h-28 whitespace-pre-line break-words text-[13px] leading-7 ${detail.hasAnswer ? "text-slate-900" : "text-slate-500"}`}>
                                  {answerText}
                                </div>
                                {detail.tracks.length > 0 && (
                                  <div className="mt-3 border-t border-slate-200 pt-2">
                                    <div className="mb-1 text-[11px] font-bold text-slate-500">부서별 답변</div>
                                    <div className="space-y-2">
                                      {detail.tracks.map((track: DepartmentTrack, trackIndex: number) => (
                                        <div key={`${doc.docId}-track-${trackIndex}`} className="border-l-2 border-slate-300 pl-2">
                                          <div className="text-[11px] font-bold text-slate-700">{track.admin_unit}</div>
                                          {track.complaint && <div className="mt-0.5 text-[11px] text-slate-600">{track.complaint}</div>}
                                          <div className="mt-0.5 whitespace-pre-line text-[11px] leading-5 text-slate-500">{track.answer}</div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })
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
    requestSegments: getCaseRequestSegments(caseItem),
  };
}

function ConfidenceBadge({ confidence }: { confidence?: number }) {
  const band = confidenceBand(confidence);
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
      <span className="inline-flex gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`h-1.5 w-1.5 rounded-full ${i <= band.level ? "bg-blue-500" : "bg-slate-200"}`} />
        ))}
      </span>
      신뢰도 {band.label}
    </span>
  );
}

// 백엔드 담당부서 추천(responsible_unit) 표시 카드.
// A) 현재 배정 ↔ AI 추천 비교(무판정, 다를 때 이관·협조 검토 안내)
// B) 추천 부서로 보내는 '이관 전달문' 생성(편집·복사). confidence는 %가 아닌 정성 단계로 표기.
function ResponsibleUnitCard({ units, assignee, caseTitle, observation, request }: {
  units?: ResponsibleUnit[];
  assignee?: string;
  caseTitle?: string;
  observation?: string;
  request?: string;
}) {
  const [memoText, setMemoText] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const list = validResponsibleUnits(units);
  const primary = list[0];
  const alternates = list.slice(1);
  const evidence = firstEvidence(primary);
  const review = reviewAssignment(assignee, units);

  function openMemo() {
    if (!primary) return;
    setMemoText(
      buildTransferMemo({
        recommended: primary.name,
        currentUnit: assignee,
        caseTitle,
        observation,
        request,
        confidenceLabel: confidenceBand(primary.confidence).label,
        evidence,
      }),
    );
    setCopied(false);
  }

  async function copyMemo() {
    if (memoText == null) return;
    try {
      await navigator.clipboard.writeText(memoText);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="border border-slate-300 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-slate-300 bg-slate-50 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="shrink-0 text-sm font-bold text-slate-900">담당부서 추천</div>
          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
            AI 추천
          </span>
        </div>
        <span className="text-[11px] font-semibold text-slate-400">자동결정 아님 · 담당자 최종 확인</span>
      </div>

      {primary ? (
        <div className="px-3 py-2">
          <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
            <div className="min-w-0">
              {review.status !== "none" && (
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
                  <span className="text-slate-500">현재 <span className="font-semibold text-slate-700">{review.status === "unassigned" ? "미지정" : review.current}</span></span>
                  {review.status === "differ" && <span className="font-semibold text-amber-700">추천과 다름 · 이관/협조 검토</span>}
                  {review.status === "match" && <span className="font-semibold text-emerald-700">추천과 일치</span>}
                </div>
              )}

              <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className="rounded border border-blue-200 bg-blue-50 px-2.5 py-1 text-sm font-bold text-blue-800">{primary.name}</span>
                <ConfidenceBadge confidence={primary.confidence} />
                {evidence && (
                  <span className="min-w-0 max-w-full truncate text-[12px] text-slate-500 xl:max-w-[520px]" title={evidence}>
                    근거: {evidence}
                  </span>
                )}
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {alternates.length > 0 && (
                  <>
                    <span className="text-[11px] font-semibold text-slate-400">대안</span>
                    {alternates.map((unit) => (
                      <span key={unit.name} className="rounded border border-slate-300 px-2 py-0.5 text-[12px] leading-4 text-slate-600">{unit.name}</span>
                    ))}
                  </>
                )}
                <span className="text-[11px] text-slate-400">신뢰도는 상대 추정치</span>
              </div>
            </div>

            <button
              type="button"
              onClick={memoText == null ? openMemo : () => setMemoText(null)}
              className="w-fit rounded border border-blue-300 bg-white px-3 py-1.5 text-[12px] font-semibold text-blue-700 hover:bg-blue-50 xl:justify-self-end"
            >
              {memoText == null ? "이관 전달문 작성" : "전달문 닫기"}
            </button>
          </div>

          {memoText != null && (
            <div className="mt-2">
              <textarea
                value={memoText}
                onChange={(e) => { setMemoText(e.target.value); setCopied(false); }}
                rows={7}
                className="w-full resize-y rounded border border-slate-300 bg-slate-50 p-2 text-[12px] leading-5 text-slate-700 outline-none focus:border-blue-400"
              />
              <div className="mt-1 flex items-center gap-2">
                <button
                  type="button"
                  onClick={copyMemo}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1 text-[12px] font-semibold text-slate-700 hover:bg-slate-50"
                >
                  복사
                </button>
                {copied && <span className="text-[11px] font-semibold text-emerald-700">복사됨</span>}
                <span className="text-[11px] text-slate-400">담당자가 검토·수정 후 사용하세요.</span>
              </div>
            </div>
          )}

        </div>
      ) : (
        <div className="px-3 py-3 text-[12px] text-slate-500">자동 추천 없음 — 유사 민원 검색 결과의 부서 태그를 참고하세요.</div>
      )}
    </div>
  );
}

function buildDefaultRoutingInfoFromCase(caseItem: WorkbenchCase): { routingTrace: RoutingTrace; strategyId: string; routeKey: string } {
  const category = caseItem.civil_category?.primary || caseItem.category || "일반";
  const displayCategory = getCaseCategoryLabel(caseItem);
  const topic: TopicType = mapCategoryToTopicType(category);
  const complexityLevel: "low" | "medium" | "high" = "medium";
  const requestSegments = getCaseRequestSegments(caseItem);

  const routingTrace: RoutingTrace = {
    topicType: topic,
    complexityLevel,
    complexityScore: 0.58,
    requestSegments,
    complexityTrace: {
      intent_count: Math.max(1, requestSegments.length),
      constraint_count: 1,
      entity_diversity: 1,
      policy_reference_count: 0,
      cross_sentence_dependency: false,
    },
    routeReason: `선택된 민원 카테고리(${displayCategory})를 기반으로 기본 라우팅 정보를 설정했습니다.`,
  };

  const routeKey = `${topic}/${complexityLevel}`;
  const strategyId = `topic_${topic}_${complexityLevel}_v1`;

  return { routingTrace, strategyId, routeKey };
}

function getCaseCategoryLabel(caseItem: Pick<WorkbenchCase, "category" | "category_display" | "civil_category">): string {
  if (caseItem.category_display) {
    return caseItem.category_display;
  }
  const primary = caseItem.civil_category?.primary;
  const secondary = caseItem.civil_category?.secondary;
  if (primary && secondary) {
    return `${primary} > ${secondary}`;
  }
  return primary || caseItem.category || "기타";
}

// 좁은 리스트용 — 대분류(primary)만. category_display가 "대분류 > 세부"라 잘리기 쉬워서
// 리스트에서는 대분류만 보여주고 전체는 hover(title)/중앙 패널에서 확인한다.
function getCaseCategoryPrimary(caseItem: Pick<WorkbenchCase, "category" | "category_display" | "civil_category">): string {
  const primary = caseItem.civil_category?.primary;
  if (primary) return primary;
  if (caseItem.category_display) return caseItem.category_display.split(">")[0].trim();
  return caseItem.category || "기타";
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
  const explicitSegments = getCaseRequestSegments(caseItem);
  if (explicitSegments.length > 0) {
    return explicitSegments;
  }
  const request = caseItem?.structured?.request?.text;
  if (typeof request === "string" && request.trim().length > 0) {
    return [request.trim()];
  }
  return [];
}

function getCaseRequestSegments(caseItem: WorkbenchCase): string[] {
  const rawSegments = caseItem.request_segments || caseItem.requestSegments || [];
  return rawSegments
    .map((segment) => String(segment || "").split(/\s+/).join(" "))
    .filter(Boolean);
}

// 이슈 #451: segmentAnswers가 있으면 요청별 답변·근거를 보여주고(근거 없는 요청은 "선례 없음" 배지),
// 없으면(구버전 응답) 기존 세그먼트/조치 표시로 폴백한다. stale면 상단에 경고 배지를 띄운다.
function DraftSupplementaryPanel({
  mode,
  summary,
  segments,
  segmentAnswers,
  stale,
}: {
  mode: SegmentViewMode;
  summary: string;
  segments: SupplementarySegment[];
  segmentAnswers: SegmentAnswerCard[];
  stale: boolean;
}) {
  const count = segmentAnswers.length > 0 ? segmentAnswers.length : segments.length;
  return (
    <div className="mt-2 border border-slate-200 bg-slate-50/70 p-2.5 text-xs">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-slate-300 bg-white px-2 py-0.5 font-bold text-slate-600">
          {mode === "multi" ? `복합 요청 · ${count}건` : "단일 요청"}
        </span>
        {stale && (
          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 font-semibold text-amber-700">
            ⚠ 검색 결과가 갱신됨 · 초안 재생성 권장
          </span>
        )}
        <span className="text-[11px] text-slate-400">분석 보조 정보 · 공식 회신문에는 포함되지 않습니다</span>
      </div>
      {summary && (
        <div className="mb-2">
          <div className="mb-0.5 font-semibold text-slate-700">요약</div>
          <div className="leading-5 text-slate-600">{summary}</div>
        </div>
      )}
      {segmentAnswers.length > 0 ? (
        <div>
          <div className="mb-1 font-semibold text-slate-700">요청별 답변 · 근거</div>
          <ul className="space-y-1.5">
            {segmentAnswers.map((card) => (
              <li key={card.index} className="rounded border border-slate-200 bg-white px-2 py-1.5">
                <div className="flex items-start gap-2">
                  <span className="font-semibold text-slate-500">{card.index + 1}.</span>
                  <span className="flex-1 font-medium text-slate-700">{card.requestSegment || `요청 ${card.index + 1}`}</span>
                  {card.hasEvidence ? (
                    <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                      근거 {card.caseIds.length}건
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                      선례 없음
                    </span>
                  )}
                </div>
                <div className="mt-1 leading-5 text-slate-600">{card.answer}</div>
                {card.caseIds.length > 0 && (
                  <div className="mt-1 text-[11px] text-slate-400">근거 사례: {card.caseIds.join(", ")}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        segments.length > 0 && (
          <div>
            <div className="mb-1 font-semibold text-slate-700">요청 세그먼트 / 조치</div>
            <ul className="space-y-1">
              {segments.map((seg) => (
                <li key={seg.index} className="rounded border border-slate-200 bg-white px-2 py-1.5">
                  <div className="text-slate-700">
                    <span className="font-semibold text-slate-500">{seg.index + 1}.</span> {seg.text}
                  </div>
                  {seg.action && <div className="mt-0.5 text-[11px] text-slate-500">· 조치: {seg.action}</div>}
                </li>
              ))}
            </ul>
          </div>
        )
      )}
    </div>
  );
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
    </svg>
  );
}

function DraftLoadingState({ step, referenceCount }: { step: number; referenceCount: number }) {
  const current = Math.min(step, DRAFT_PROGRESS_STAGES.length - 1);
  return (
    <div
      className="h-44 w-full border border-slate-300 bg-slate-50 px-3 py-3"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
        <Spinner className="h-4 w-4 text-slate-400" />
        <span>{DRAFT_PROGRESS_STAGES[current]}</span>
        <span className="ml-auto text-xs font-normal text-slate-400">
          {current + 1}/{DRAFT_PROGRESS_STAGES.length}단계
        </span>
      </div>

      <div className="mt-2 flex gap-1">
        {DRAFT_PROGRESS_STAGES.map((label, i) => (
          <div
            key={label}
            className={`h-1 flex-1 rounded ${i <= current ? "bg-slate-400" : "bg-slate-200"}`}
          />
        ))}
      </div>

      <div className="mt-3 space-y-2">
        <div className="h-3 w-11/12 animate-pulse rounded bg-slate-200" />
        <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
        <div className="h-3 w-9/12 animate-pulse rounded bg-slate-200" />
      </div>

      {referenceCount > 0 && (
        <p className="mt-3 text-xs text-slate-500">유사 민원 {referenceCount}건을 근거로 작성하고 있습니다.</p>
      )}
      <p className="mt-1 text-xs text-slate-400">보통 10~20초 정도 걸립니다.</p>
    </div>
  );
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

function formatReceivedDate(value?: string) {
  const raw = String(value || "").trim();
  if (!raw || raw === "-") {
    return "-";
  }

  const compactMatch = raw.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (compactMatch) {
    return `${compactMatch[1]}.${compactMatch[2]}.${compactMatch[3]}`;
  }

  const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoMatch) {
    return `${isoMatch[1]}.${isoMatch[2]}.${isoMatch[3]}`;
  }

  return raw;
}

const MASK_LABELS: Record<string, string> = {
  ADDRESS: "주소 비공개",
  ACCOUNT: "계좌번호 비공개",
  CARD: "카드번호 비공개",
  EMAIL: "이메일 비공개",
  NAME: "성명 비공개",
  PERSON: "성명 비공개",
  PHONE: "전화번호 비공개",
  RRN: "주민등록번호 비공개",
};

function formatMaskedText(value?: string) {
  const text = String(value || "");
  return text.replace(/\[REDACTED(?::([A-Z_]+))?\]/g, (_, rawLabel: string | undefined) => {
    if (!rawLabel) {
      return "개인정보 비공개";
    }
    return MASK_LABELS[rawLabel] || "개인정보 비공개";
  });
}

function getAccordionDetail(doc: RetrievedDoc): AccordionDetail {
  const answersByAdminUnit = doc.answers_by_admin_unit || doc.department_answers || {};
  const complaint = formatMaskedText(doc.summary?.observation || doc.title);
  const request = formatMaskedText(doc.summary?.request || doc.snippet || "");
  const tracks: DepartmentTrack[] = Object.entries(answersByAdminUnit).map(([adminUnit, departmentAnswer], memoIndex) => ({
    admin_unit: formatMaskedText(adminUnit),
    complaint: complaint || doc.title,
    answer: formatMaskedText(departmentAnswer || ""),
    memoIndex,
  })).filter((track) => track.answer.trim().length > 0);
  const firstDepartmentAnswer = tracks.find((track) => track.answer.trim().length > 0)?.answer || "";
  const answer = formatMaskedText(String(doc.answer || firstDepartmentAnswer || "").trim());

  return {
    complaint: complaint || formatMaskedText(doc.title),
    request,
    answer,
    hasAnswer: answer.length > 0,
    caseId: doc.caseId || doc.case_id || doc.docId,
    receivedAt: doc.received_at || "-",
    category: formatMaskedText(doc.category || "-"),
    region: formatMaskedText(doc.region || "-"),
    tracks,
  };
}

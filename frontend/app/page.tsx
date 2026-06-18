// src/app/page.tsx
"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { mockAssignedCases } from "@/lib/mockData";
import { PriorityBadge, StatusBadge } from "@/components/SearchUI";
import AppSidebar from "@/components/AppSidebar";
import { fetchUiCasesApi, type AssignedCase } from "@/lib/api";
import { CASE_STATUS_OPTIONS, readJsonFromLocalStorage, sanitizeCaseStatuses, safeString } from "@/lib/safe-data";

const CASE_STATUS_STORAGE_KEY = "case-status-overrides";
const MAX_STATUS_STORAGE_BYTES = 24 * 1024;

export default function QueuePage() {
  const router = useRouter();

  // 필터 상태 관리
  const [priorityFilter, setPriorityFilter] = useState("전체");
  const [statusFilter, setStatusFilter] = useState("전체");
  const [sortBy, setSortBy] = useState("우선순위");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});
  const [caseList, setCaseList] = useState<AssignedCase[]>(mockAssignedCases);

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
        // keep fallback mock data
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    const parsed = readJsonFromLocalStorage<Record<string, string>>(CASE_STATUS_STORAGE_KEY, {
      maxBytes: MAX_STATUS_STORAGE_BYTES,
      removeOnOversize: true,
    });

    if (parsed) {
      setCaseStatuses(sanitizeCaseStatuses(parsed, mockAssignedCases.map((item) => item.case_id)));
    }
  }, []);

  const getEffectiveStatus = useCallback(
    (c: AssignedCase) => caseStatuses[c.case_id] || c.status || "미처리",
    [caseStatuses],
  );

  // KPI 계산
  const kpis = useMemo(() => {
    let open = 0;
    let urgent = 0;
    let done = 0;

    caseList.forEach((c) => {
      const status = getEffectiveStatus(c);
      if (status === "미처리" || status === "검토중") open++;
      if (c.priority === "매우급함" && (status === "미처리" || status === "검토중")) urgent++;
      if (status === "처리완료") done++;
    });

    return { open, urgent, done };
  }, [caseList, getEffectiveStatus]);

  // 필터 초기화 함수
  const resetFilters = () => {
    setPriorityFilter("전체");
    setStatusFilter("전체");
    setSortBy("우선순위");
    setSearchKeyword("");
  };

  // 필터 및 정렬 로직 적용
  const filteredCases = useMemo(() => {
    let result = [...caseList];

    // 상태 필터
    if (statusFilter !== "전체") {
      result = result.filter((c) => getEffectiveStatus(c) === statusFilter);
    }

    // 우선순위 필터
    if (priorityFilter !== "전체") {
      result = result.filter((c) => (c.priority || "보통") === priorityFilter);
    }

    // 검색어 필터
    if (searchKeyword.trim()) {
      const keyword = searchKeyword.toLowerCase();
      result = result.filter((c) => {
        const haystack = `${c.case_id} ${getCaseCategoryLabel(c)} ${c.category} ${c.assignee} ${c.region} ${c.raw_text}`.toLowerCase();
        return haystack.includes(keyword);
      });
    }

    // 정렬
    if (sortBy === "우선순위") {
      const rank: Record<string, number> = { 매우급함: 0, 급함: 1, 보통: 2 };
      result.sort((a, b) => {
        const rankA = rank[a.priority || "보통"] ?? 9;
        const rankB = rank[b.priority || "보통"] ?? 9;
        if (rankA !== rankB) return rankA - rankB;
        return a.received_at > b.received_at ? -1 : 1;
      });
    } else {
      result.sort((a, b) => (a.received_at > b.received_at ? -1 : 1));
    }

    return result;
  }, [priorityFilter, statusFilter, sortBy, searchKeyword, caseList, getEffectiveStatus]);

  // 타이틀 생성 헬퍼
  const buildTitle = (c: AssignedCase) => {
    const observation = safeString(c?.structured?.observation?.text).trim();
    const request = safeString(c?.structured?.request?.text).trim();

    if (observation && request) {
      return `${observation} - ${request}`;
    }

    const rawText = safeString(c?.raw_text).trim();
    if (!rawText) {
      return "제목 없음 민원";
    }

    return rawText.length > 40 ? `${rawText.substring(0, 40)}...` : rawText;
  };

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen w-full">
        <AppSidebar activeMenu="queue" />

        <main className="min-w-0 flex-1 p-6">
          <div className="max-w-7xl mx-auto space-y-6">
        
        {/* 상단 헤더 */}
        <div className="flex justify-between items-end">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">처리 대상 민원 선택</h1>
            <p className="text-sm font-medium text-slate-500 mt-1">
              민원 목록에서 항목을 클릭하면 바로 처리 워크벤치로 이동합니다.
            </p>
          </div>
          <button 
            onClick={() => router.push('/admin')}
            className="px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            관리자 통계 대시보드 →
          </button>
        </div>

        {/* KPI 카드 섹션 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm border-l-4 border-l-blue-600">
            <div className="text-xs font-bold text-slate-500 mb-1">열린 건</div>
            <div className="text-3xl font-extrabold text-slate-900">{kpis.open}건</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm border-l-4 border-l-red-600">
            <div className="text-xs font-bold text-slate-500 mb-1">매우급함</div>
            <div className="text-3xl font-extrabold text-slate-900">{kpis.urgent}건</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm border-l-4 border-l-emerald-600">
            <div className="text-xs font-bold text-slate-500 mb-1">오늘 완료</div>
            <div className="text-3xl font-extrabold text-slate-900">{kpis.done}건</div>
          </div>
        </div>

        {/* 필터 컨트롤 섹션 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
          <h2 className="text-sm font-bold text-slate-800">빠른 필터</h2>
          <div className="grid grid-cols-12 gap-4 items-end">
            <div className="col-span-3">
              <label className="block text-xs font-bold text-slate-500 mb-1">우선순위</label>
              <select
                className="w-full bg-slate-50 border border-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
              >
                <option value="전체">전체</option>
                <option value="매우급함">매우급함</option>
                <option value="급함">급함</option>
                <option value="보통">보통</option>
              </select>
            </div>
            <div className="col-span-3">
              <label className="block text-xs font-bold text-slate-500 mb-1">상태</label>
              <select
                className="w-full bg-slate-50 border border-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="전체">전체</option>
                {CASE_STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
                <option value="보류">보류</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-bold text-slate-500 mb-1">정렬</label>
              <select
                className="w-full bg-slate-50 border border-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="우선순위">우선순위</option>
                <option value="최신 접수">최신 접수</option>
              </select>
            </div>
            <div className="col-span-3">
              <label className="block text-xs font-bold text-slate-500 mb-1">빠른 검색</label>
              <input
                type="text"
                placeholder="ID, 카테고리, 지역..."
                className="w-full bg-slate-50 border border-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
              />
            </div>
            <div className="col-span-1">
              <button 
                onClick={resetFilters}
                className="w-full h-9.5 bg-slate-100 border border-slate-300 rounded-lg text-sm font-bold text-slate-700 hover:bg-slate-200 transition-colors shadow-sm"
              >
                초기화
              </button>
            </div>
          </div>
        </div>

        {/* 민원 목록 테이블 */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50/50">
            <h3 className="text-sm font-bold text-slate-800">민원 목록 ({filteredCases.length}건)</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-200">
              <thead>
                <tr className="bg-slate-50 text-xs font-bold text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-3 w-[35%]">민원 제목</th>
                  <th className="px-4 py-3">케이스ID</th>
                  <th className="px-4 py-3">접수일</th>
                  <th className="px-4 py-3">카테고리</th>
                  <th className="px-4 py-3">우선순위</th>
                  <th className="px-5 py-3">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredCases.map((c) => (
                  <tr
                    key={c.case_id}
                    onClick={() => router.push(`/workbench?case_id=${c.case_id}`)}
                    className="hover:bg-blue-50/50 cursor-pointer transition-colors group"
                  >
                    <td className="px-5 py-3">
                      <div className="text-sm font-bold text-slate-800 group-hover:text-blue-600 transition-colors truncate max-w-75">
                        {buildTitle(c)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-[11px] font-medium text-slate-400 truncate max-w-30">{c.case_id}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">{c.received_at}</td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      <div className="max-w-60 truncate" title={getCaseCategoryLabel(c)}>{getCaseCategoryLabel(c)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <PriorityBadge priority={c.priority} />
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={getEffectiveStatus(c)} />
                    </td>
                  </tr>
                ))}
                {filteredCases.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-5 py-16 text-center text-sm text-slate-500 font-medium bg-slate-50/30">
                      조건에 맞는 민원이 없습니다. 필터를 조정해보세요.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function getCaseCategoryLabel(c: AssignedCase): string {
  if (c.category_display) {
    return c.category_display;
  }
  const primary = c.civil_category?.primary;
  const secondary = c.civil_category?.secondary;
  if (primary && secondary) {
    return `${primary} > ${secondary}`;
  }
  return primary || c.category || "기타";
}

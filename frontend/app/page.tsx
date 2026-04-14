// src/app/page.tsx
"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { mockAssignedCases } from "@/lib/mockData";
import { PriorityBadge, StatusBadge } from "@/components/SearchUI";
import AppSidebar from "@/components/AppSidebar";

const CASE_STATUS_STORAGE_KEY = "case-status-overrides";
const STATUS_OPTIONS = ["미처리", "검토중", "처리완료"] as const;
const MAX_STATUS_STORAGE_BYTES = 24 * 1024;

export default function QueuePage() {
  const router = useRouter();

  // 필터 상태 관리
  const [priorityFilter, setPriorityFilter] = useState("전체");
  const [statusFilter, setStatusFilter] = useState("전체");
  const [sortBy, setSortBy] = useState("우선순위");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(CASE_STATUS_STORAGE_KEY);
      if (!raw) return;
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

  const getEffectiveStatus = (c: any) => caseStatuses[c.case_id] || c.status || "미처리";

  // KPI 계산
  const kpis = useMemo(() => {
    let open = 0;
    let urgent = 0;
    let done = 0;

    mockAssignedCases.forEach((c) => {
      const status = getEffectiveStatus(c);
      if (status === "미처리" || status === "검토중") open++;
      if (c.priority === "매우급함" && (status === "미처리" || status === "검토중")) urgent++;
      if (status === "처리완료") done++;
    });

    return { open, urgent, done };
  }, [caseStatuses]);

  // 필터 초기화 함수
  const resetFilters = () => {
    setPriorityFilter("전체");
    setStatusFilter("전체");
    setSortBy("우선순위");
    setSearchKeyword("");
  };

  // 필터 및 정렬 로직 적용
  const filteredCases = useMemo(() => {
    let result = [...mockAssignedCases];

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
        const haystack = `${c.case_id} ${c.category} ${c.assignee} ${c.region} ${c.raw_text}`.toLowerCase();
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
  }, [priorityFilter, statusFilter, sortBy, searchKeyword]);

  // 타이틀 생성 헬퍼
  const buildTitle = (c: any) => {
    if (c.structured?.observation?.text && c.structured?.request?.text) {
      return `${c.structured.observation.text} - ${c.structured.request.text}`;
    }
    return c.raw_text.length > 40 ? c.raw_text.substring(0, 40) + "..." : c.raw_text;
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
                <option value="미처리">미처리</option>
                <option value="검토중">검토중</option>
                <option value="보류">보류</option>
                <option value="처리완료">처리완료</option>
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
                  <th className="px-4 py-3">지역</th>
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
                    <td className="px-4 py-3 text-sm text-slate-600">{c.category}</td>
                    <td className="px-4 py-3 text-sm text-slate-600">{c.region}</td>
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
                    <td colSpan={7} className="px-5 py-16 text-center text-sm text-slate-500 font-medium bg-slate-50/30">
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

function sanitizeCaseStatuses(value: Record<string, string>): Record<string, string> {
  const allowedCaseIds = new Set(mockAssignedCases.map((item) => item.case_id));
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
// src/app/admin/page.tsx
"use client";

import { useEffect, useState } from "react";
import { fetchAdminOverviewApi, type AdminOverviewData } from "@/lib/api";
import AppSidebar from "@/components/AppSidebar";

export default function AdminDashboardPage() {
  const [year, setYear] = useState("all");
  const [overview, setOverview] = useState<AdminOverviewData | null>(null);

  useEffect(() => {
    let active = true;
    fetchAdminOverviewApi(year).then((res) => {
      if (active && !res.error) setOverview(res.data);
    });
    return () => {
      active = false;
    };
  }, [year]);

  // 전부 백엔드 실데이터(부산 대분류·지역·이슈유형·연도별 추이)
  const categories = overview?.categories ?? [];
  const regions = overview?.regions ?? [];
  const issues = overview?.issues ?? [];
  const trend = overview?.trend ?? [];
  const maxCatCount = Math.max(1, ...categories.map((c) => c.count));
  const maxIssueCount = Math.max(1, ...issues.map((i) => i.count));
  const maxTrendCount = Math.max(1, ...trend.map((t) => t.count));
  const regionTotal = regions.reduce((sum, r) => sum + r.count, 0) || 1;

  // KPI(실데이터, 연도 선택 반응)
  const totalCount = overview?.total ?? 0;
  const topCategory = categories[0];
  const availableYears = overview?.available_years ?? [];
  const dataSpan = availableYears.length ? `${availableYears[availableYears.length - 1]}~${availableYears[0]}` : "—";
  const periodLabel = year === "all" ? "전체" : `${year}년`;

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900 font-sans">
      <div className="flex min-h-screen w-full">
        <AppSidebar activeMenu="admin" />

        <main className="min-w-0 flex-1 p-6 pb-20">
          <div className="max-w-6xl mx-auto space-y-6">

        {/* 상단 헤더 및 네비게이션 */}
        <div className="flex justify-between items-end border-b border-slate-200 pb-4">
          <div>
            <h1 className="text-2xl font-black tracking-tight text-slate-900">관리자 통계 대시보드</h1>
            <p className="text-sm font-medium text-slate-500 mt-1">부산 대분류·지역·이슈 유형·연도별 추이를 실데이터로 분석합니다.</p>
          </div>
        </div>

        {/* 조회 설정 */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-xs font-bold text-slate-500 mb-1">조회 연도</label>
            <select
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-sm font-medium rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 transition-all"
            >
              <option value="all">전체</option>
              {availableYears.map((y) => (
                <option key={y} value={y}>{y}년</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white transition-colors hover:bg-slate-800"
            aria-label="새로고침"
          >
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-4 w-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 10a6 6 0 0 1 10.2-4.2L16 7.6" />
              <path d="M16 4.8v2.8h-2.8" />
              <path d="M16 10a6 6 0 0 1-10.2 4.2L4 12.4" />
              <path d="M4 15.2v-2.8h2.8" />
            </svg>
          </button>
        </div>

        {/* KPI 카드 (실데이터 · 연도 선택 반응) */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="text-sm font-bold text-slate-500 mb-2">{periodLabel} 발생 건수</div>
            <div className="text-3xl font-black text-blue-700">{totalCount.toLocaleString()}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="text-sm font-bold text-slate-500 mb-2">분야 수</div>
            <div className="text-3xl font-black text-emerald-600">
              {categories.length}<span className="ml-1 text-lg text-slate-400">개</span>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="text-sm font-bold text-slate-500 mb-2">최다 분야</div>
            <div className="truncate text-xl font-black text-purple-700" title={topCategory?.name}>{topCategory?.name ?? "—"}</div>
            <div className="text-xs font-medium text-slate-400 mt-1">{topCategory ? `${topCategory.count.toLocaleString()}건` : " "}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="text-sm font-bold text-slate-500 mb-2">수집 기간</div>
            <div className="text-2xl font-black text-amber-600">{dataSpan}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 차트 1: 카테고리별 발생 현황 (수직 막대) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="mb-5 flex items-baseline justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-black text-blue-900">카테고리별 발생 현황</h3>
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">실데이터</span>
              </div>
              <span className="text-xs font-medium text-slate-400">{periodLabel} · {totalCount.toLocaleString()}건</span>
            </div>
            {categories.length === 0 ? (
              <div className="flex h-56 items-center justify-center text-sm text-slate-400">카테고리 통계를 불러오는 중…</div>
            ) : (
              <div className="space-y-2.5">
                {categories.map((c, idx) => {
                  const widthPct = (c.count / maxCatCount) * 100;
                  const colors = ["bg-blue-600", "bg-emerald-600", "bg-amber-500", "bg-purple-600", "bg-slate-600", "bg-rose-500", "bg-cyan-600", "bg-indigo-500"];
                  return (
                    <div key={c.name} className="flex items-center gap-3">
                      <div className="w-28 shrink-0 truncate text-right text-[13px] font-bold text-slate-700" title={c.name}>
                        {c.name}
                      </div>
                      <div className="flex h-5 flex-1 items-center overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full ${colors[idx % colors.length]} transition-all duration-500`}
                          style={{ width: `${widthPct}%`, minWidth: c.count > 0 ? "6px" : "0" }}
                        ></div>
                      </div>
                      <div className="w-14 shrink-0 text-right text-[13px] font-bold text-slate-500 tabular-nums">
                        {c.count.toLocaleString()}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 차트 2: 이슈 유형 Top N (수평 막대, 실데이터) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="mb-6 flex items-center gap-2">
              <h3 className="text-base font-black text-blue-900">이슈 유형 Top {issues.length}</h3>
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">실데이터</span>
            </div>
            <div className="space-y-3">
              {issues.map((item, idx) => {
                const widthPct = (item.count / maxIssueCount) * 100;
                const colors = ["bg-red-500", "bg-orange-500", "bg-amber-400", "bg-lime-500", "bg-emerald-500", "bg-cyan-500", "bg-blue-500", "bg-indigo-500"];
                return (
                  <div key={item.name} className="flex items-center gap-3">
                    <div className="w-28 shrink-0 truncate text-right text-[13px] font-bold text-slate-700" title={item.name}>
                      {item.name}
                    </div>
                    <div className="flex h-5 flex-1 items-center overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full ${colors[idx % colors.length]} transition-all duration-500`}
                        style={{ width: `${widthPct}%`, minWidth: item.count > 0 ? "6px" : "0" }}
                      ></div>
                    </div>
                    <div className="w-14 shrink-0 text-right text-[13px] font-bold text-slate-500 tabular-nums">
                      {item.count.toLocaleString()}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 하단 2단 레이아웃 (지역별 표 / 주간 트렌드) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 지역별 발생 현황 테이블 */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
              <h3 className="text-base font-black text-blue-900">지역별 민원 발생 현황</h3>
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">실데이터</span>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-2 px-4 font-bold">지역</th>
                  <th className="py-2 px-4 font-bold text-right">건수</th>
                  <th className="py-2 px-4 font-bold text-right">비율</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {regions.map((r) => {
                  const pct = ((r.count / regionTotal) * 100).toFixed(1);
                  return (
                    <tr key={r.name} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-bold text-slate-700">{r.name}</td>
                      <td className="py-3 px-4 text-right font-medium text-slate-600 tabular-nums">{r.count.toLocaleString()}건</td>
                      <td className="py-3 px-4 text-right font-bold text-blue-600 tabular-nums">{pct}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 연도별 발생 추이 (수직 막대, 실데이터) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="text-base font-black text-blue-900">연도별 발생 추이</h3>
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">실데이터</span>
            </div>
            <p className="text-xs font-medium text-slate-400 mb-5">접수 연도 기준 · {dataSpan}</p>
            <div className="flex items-end gap-1 h-48 px-1 mt-4">
              {trend.map((item) => {
                const heightPct = (item.count / maxTrendCount) * 100;
                return (
                  <div key={item.year} className="flex flex-1 min-w-0 flex-col items-center group">
                    <div className="text-[10px] font-bold text-blue-600 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">{item.count.toLocaleString()}</div>
                    <div className="h-32 w-full max-w-8 flex items-end">
                      <div
                        className="w-full bg-blue-100 border-2 border-blue-400 rounded-t-sm transition-all duration-500 hover:bg-blue-300"
                        style={{ height: `${heightPct}%`, minHeight: "6px" }}
                      ></div>
                    </div>
                    <div className="text-[10px] font-bold text-slate-600 mt-2">{item.year}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>


          </div>
        </main>
      </div>
    </div>
  );
}

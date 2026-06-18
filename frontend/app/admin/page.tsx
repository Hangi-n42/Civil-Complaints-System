// src/app/admin/page.tsx
"use client";

import { useState } from "react";
import { mockHazardStatistics, mockModelBenchmarkReport } from "@/lib/mockData";
import { getRecentCompletedWeekRanges, formatWeekRange } from "@/lib/weekRange";
import AppSidebar from "@/components/AppSidebar";

export default function AdminDashboardPage() {
  const [period, setPeriod] = useState("지난 30일");

  // 데이터 불러오기
  const stats = mockHazardStatistics;
  const benchmark = mockModelBenchmarkReport;

  // 차트 렌더링을 위한 최대값 계산
  const maxCatCount = Math.max(...stats.category_stats.count);
  const maxHazardCount = Math.max(...stats.hazard_top5.map((h) => h.count));

  // 주간 트렌드: 건수는 데모용 목업(Streamlit과 동일)이며, 날짜 구간만 오늘 기준
  // "지난 4주(완료 주, 월~일)"로 계산해 N주차 라벨의 모호함을 없앤다.
  const WEEKLY_COUNTS = [58, 71, 94, 64];
  const weeklyData = getRecentCompletedWeekRanges(new Date(), WEEKLY_COUNTS.length).map((range, i) => ({
    week: `${i + 1}주차`,
    range: formatWeekRange(range),
    count: WEEKLY_COUNTS[i],
  }));
  const maxWeeklyCount = Math.max(...weeklyData.map((w) => w.count));

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
            <p className="text-sm font-medium text-slate-500 mt-1">민원 발생 현황, 카테고리별 추이, 위험요소 분포를 분석합니다.</p>
          </div>
        </div>

        {/* 조회 설정 */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-xs font-bold text-slate-500 mb-1">조회 기간</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-sm font-medium rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 transition-all"
            >
              <option>지난 7일</option>
              <option>지난 30일</option>
              <option>지난 90일</option>
              <option>올해</option>
              <option>전체</option>
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

        {/* KPI 카드 3개 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm text-center">
            <div className="text-sm font-bold text-slate-500 mb-2">전체 누적 건수</div>
            <div className="text-4xl font-black text-blue-700">{stats.total_cases}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm text-center border-b-4 border-b-emerald-500">
            <div className="text-sm font-bold text-slate-500 mb-2">이번 달 건수</div>
            <div className="text-4xl font-black text-emerald-600">{stats.cases_this_month}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm text-center border-b-4 border-b-amber-500">
            <div className="text-sm font-bold text-slate-500 mb-2">이번 주 건수</div>
            <div className="text-4xl font-black text-amber-500">{stats.cases_this_week}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 차트 1: 카테고리별 발생 현황 (수직 막대) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 className="text-base font-black text-blue-900 mb-6">카테고리별 발생 현황</h3>
            <div className="flex items-end justify-around h-56 px-2 mt-4">
              {stats.category_stats.category.map((cat, idx) => {
                const count = stats.category_stats.count[idx];
                const heightPct = (count / maxCatCount) * 100;
                const colors = ["bg-blue-600", "bg-emerald-600", "bg-amber-500", "bg-purple-600", "bg-slate-600"];

                return (
                  <div key={cat} className="flex flex-col items-center group w-1/6">
                    <div className="text-xs font-bold text-slate-500 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {count}건
                    </div>
                    <div className="h-40 w-10 flex items-end">
                      <div
                        className={`w-full ${colors[idx % colors.length]} rounded-t-md transition-all duration-500 hover:opacity-80`}
                        style={{ height: `${heightPct}%`, minHeight: "8px" }}
                      ></div>
                    </div>
                    <div className="text-xs font-bold text-slate-600 mt-3 text-center break-keep">
                      {cat}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 차트 2: 위험요소 Top 5 (수평 막대) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 className="text-base font-black text-blue-900 mb-6">위험요소 Top 5</h3>
            <div className="space-y-4">
              {stats.hazard_top5.map((item, idx) => {
                const widthPct = (item.count / maxHazardCount) * 100;
                const colors = ["bg-red-500", "bg-orange-500", "bg-amber-400", "bg-lime-500", "bg-emerald-500"];

                return (
                  <div key={item.hazard} className="flex items-center gap-3">
                    <div className="w-24 text-sm font-bold text-slate-700 text-right truncate">
                      {item.hazard}
                    </div>
                    <div className="flex-1 h-6 bg-slate-100 rounded-full overflow-hidden flex items-center">
                      <div
                        className={`h-full ${colors[idx % colors.length]} transition-all duration-500`}
                        style={{ width: `${widthPct}%` }}
                      ></div>
                    </div>
                    <div className="w-12 text-sm font-bold text-slate-500">
                      {item.count}건
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
            <h3 className="text-base font-black text-blue-900 mb-4">지역별 민원 발생 현황</h3>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-2 px-4 font-bold">지역</th>
                  <th className="py-2 px-4 font-bold text-right">건수</th>
                  <th className="py-2 px-4 font-bold text-right">비율</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stats.region_stats.region.map((reg, idx) => {
                  const count = stats.region_stats.count[idx];
                  const total = stats.region_stats.count.reduce((a, b) => a + b, 0);
                  const pct = ((count / total) * 100).toFixed(1);
                  return (
                    <tr key={reg} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-bold text-slate-700">{reg}</td>
                      <td className="py-3 px-4 text-right font-medium text-slate-600">{count}건</td>
                      <td className="py-3 px-4 text-right font-bold text-blue-600">{pct}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 주간 트렌드 (수직 막대) */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 className="text-base font-black text-blue-900 mb-1">주간 트렌드 (지난 4주)</h3>
            <p className="text-xs font-medium text-slate-400 mb-5">완료 주(월~일) 기준</p>
            <div className="flex items-end justify-around h-48 px-4 mt-4">
              {weeklyData.map((item) => {
                const heightPct = (item.count / maxWeeklyCount) * 100;
                return (
                  <div key={item.week} className="flex flex-col items-center group w-1/5">
                    <div className="text-xs font-bold text-blue-600 mb-1">{item.count}건</div>
                    <div className="h-32 w-10 flex items-end">
                      <div
                        className="w-full bg-blue-100 border-2 border-blue-400 rounded-t-sm transition-all duration-500 hover:bg-blue-300"
                        style={{ height: `${heightPct}%`, minHeight: "10px" }}
                      ></div>
                    </div>
                    <div className="text-xs font-bold text-slate-600 mt-2">{item.week}</div>
                    <div className="text-[10px] font-medium text-slate-400 mt-0.5">{item.range}</div>
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

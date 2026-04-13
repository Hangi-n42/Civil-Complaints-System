// src/app/admin/page.tsx
"use client";

import { useState } from "react";
import { mockHazardStatistics, mockModelBenchmarkReport } from "@/lib/mockData";
import AppSidebar from "@/components/AppSidebar";

export default function AdminDashboardPage() {
  const [period, setPeriod] = useState("지난 30일");

  // 데이터 불러오기
  const stats = mockHazardStatistics;
  const benchmark = mockModelBenchmarkReport;

  // 차트 렌더링을 위한 최대값 계산
  const maxCatCount = Math.max(...stats.category_stats.count);
  const maxHazardCount = Math.max(...stats.hazard_top5.map((h) => h.count));

  // 주간 트렌드 하드코딩 데이터 (Streamlit과 동일)
  const weeklyData = [
    { week: "1주차", count: 58 },
    { week: "2주차", count: 71 },
    { week: "3주차", count: 94 },
    { week: "4주차", count: 64 },
  ];
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
          <button className="px-6 py-2 bg-slate-900 text-white text-sm font-bold rounded-lg hover:bg-slate-800 transition-colors">
            새로고침
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
            <h3 className="text-base font-black text-blue-900 mb-6">주간 트렌드 (지난 4주)</h3>
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
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 주간 AI 모델 성능 벤치마크 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mt-8">
          <div className="flex justify-between items-end border-b border-slate-100 pb-3 mb-4">
            <h3 className="text-lg font-black text-blue-900">주간 AI 모델 성능 벤치마크</h3>
            <div className="text-xs font-bold text-slate-500">
              모델: {benchmark.model_info.llm_model} | 임베딩: {benchmark.model_info.embedding_model}
            </div>
          </div>

          {/* AI KPI */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-slate-50 border border-slate-200 p-4 rounded-lg text-center">
              <div className="text-xs font-bold text-slate-500 mb-1">구조화 F1 Score</div>
              <div className="text-2xl font-black text-slate-800">{(benchmark.summary.average_f1_score * 100).toFixed(1)}%</div>
            </div>
            <div className="bg-slate-50 border border-slate-200 p-4 rounded-lg text-center">
              <div className="text-xs font-bold text-slate-500 mb-1">검색 명중률 (Recall@5)</div>
              <div className="text-2xl font-black text-slate-800">{(benchmark.summary.average_recall_at_5 * 100).toFixed(1)}%</div>
            </div>
            <div className="bg-slate-50 border border-slate-200 p-4 rounded-lg text-center">
              <div className="text-xs font-bold text-slate-500 mb-1">평균 추론 지연</div>
              <div className="text-2xl font-black text-slate-800">{benchmark.summary.average_latency_sec.toFixed(2)}s</div>
            </div>
          </div>

          {/* AI 시나리오별 표 */}
          <table className="w-full text-left text-sm border border-slate-200 rounded-lg overflow-hidden">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                <th className="py-3 px-4 font-bold border-b border-slate-200">시나리오</th>
                <th className="py-3 px-4 font-bold border-b border-slate-200 text-center">F1 Score</th>
                <th className="py-3 px-4 font-bold border-b border-slate-200 text-center">Recall@5</th>
                <th className="py-3 px-4 font-bold border-b border-slate-200 text-right">지연(초)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {benchmark.scenarios.map((scen, idx) => (
                <tr key={idx} className="hover:bg-slate-50">
                  <td className="py-3 px-4 font-bold text-slate-700">{scen.name}</td>
                  <td className="py-3 px-4 text-center font-medium text-blue-600">{scen.f1_score.toFixed(2)}</td>
                  <td className="py-3 px-4 text-center font-medium text-emerald-600">{scen.recall_at_5.toFixed(2)}</td>
                  <td className="py-3 px-4 text-right font-medium text-slate-500">{scen.latency_sec.toFixed(2)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-right mt-2 text-[10px] text-slate-400">
            출처: logs/evaluation/week3/model_benchmark_report_final.json
          </div>
        </div>

          </div>
        </main>
      </div>
    </div>
  );
}

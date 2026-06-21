"use client";

import { useEffect, useState } from "react";
import AppSidebar from "@/components/AppSidebar";
import { fetchIntelDashboardApi, type IntelDashboardData, type IntelDashboardSummary, type IntelPublicInsightCard } from "@/lib/api";
import { IssueAlertList } from "@/components/intelligence/IssueAlertList";
import { PublicInsightList } from "@/components/intelligence/PublicInsightList";
import { InsightDetailPanel } from "@/components/intelligence/InsightDetailPanel";
import { findById } from "@/components/intelligence/links";

// summary → 상단 KPI 카드 메타. 값은 런타임에 summary에서 뽑는다.
// '이슈 경보'는 신규 active_alert_count 우선, 없으면(옛 서버) alert_count로 폴백.
const SUMMARY_CARDS: Array<{ label: string; accent: string; value: (s: IntelDashboardSummary) => number }> = [
  { label: "이슈 경보", accent: "border-l-blue-600", value: (s) => s.active_alert_count ?? s.alert_count },
  { label: "긴급 경보", accent: "border-l-red-600", value: (s) => s.critical_alert_count },
  { label: "행정 인사이트", accent: "border-l-blue-600", value: (s) => s.public_insight_count },
  { label: "높음·긴급 인사이트", accent: "border-l-amber-500", value: (s) => s.high_priority_insight_count },
  { label: "검토 필요", accent: "border-l-amber-500", value: (s) => s.human_review_required_count },
  { label: "연결된 경보", accent: "border-l-emerald-600", value: (s) => s.linked_alert_count },
];

// ISO 타임스탬프를 hydration-안전하게 짧게 표기(YYYY-MM-DD HH:MM). Date/locale 미사용.
function shortTs(iso?: string | null): string {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}

export default function IntelligencePage() {
  const [data, setData] = useState<IntelDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("issue_alerts");
  const [selectedInsight, setSelectedInsight] = useState<IntelPublicInsightCard | null>(null);
  const [focusedAlertId, setFocusedAlertId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    fetchIntelDashboardApi()
      .then((response) => {
        if (!isMounted) return;
        setData(response.data);
        setErrorMsg(response.error ? response.error.message : null);
        setLoading(false);
      })
      .catch(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const summary = data?.summary;
  const tabs = data?.tabs ?? [];
  const monitoringContext = summary
    ? [
        summary.as_of ? `관제 기준 ${shortTs(summary.as_of)}` : null,
        summary.latest_event_at ? `마지막 관측 ${shortTs(summary.latest_event_at)}` : null,
        summary.event_count != null ? `전체 관측 ${summary.event_count}건` : null,
      ]
        .filter(Boolean)
        .join("  ·  ")
    : "";

  // 경보 → 연결 인사이트: 인사이트 탭으로 전환하고 상세 패널을 연다.
  function goToInsight(insightId: string) {
    const insight = data ? findById(data.public_insights, insightId) : undefined;
    if (!insight) return;
    setActiveTab("public_insights");
    setSelectedInsight(insight);
  }

  // 인사이트 → 연결 경보: 경보 탭으로 전환하고 해당 경보를 포커스(하이라이트)한다.
  function goToAlert(alertId: string) {
    setSelectedInsight(null);
    setActiveTab("issue_alerts");
    setFocusedAlertId(alertId);
  }

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen w-full">
        <AppSidebar activeMenu="intelligence" />

        <main className="min-w-0 flex-1 p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            {/* 헤더 */}
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">민원 인텔리전스</h1>
              <p className="text-sm font-medium text-slate-500 mt-1">
                실시간 이슈 경보와 행정 인사이트를 한 곳에서 확인합니다.
              </p>
              {monitoringContext && <p className="mt-1 text-xs text-slate-400">{monitoringContext}</p>}
            </div>

            {errorMsg && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                백엔드 연결에 실패해 빈 대시보드를 표시합니다. ({errorMsg})
              </div>
            )}

            {/* 요약 KPI */}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {SUMMARY_CARDS.map((card) => (
                <div
                  key={card.label}
                  className={`bg-white border border-slate-200 rounded-xl p-4 shadow-sm border-l-4 ${card.accent}`}
                >
                  <div className="text-xs font-bold text-slate-500 mb-1">{card.label}</div>
                  <div className="text-2xl font-extrabold text-slate-900">{loading || !summary ? "—" : card.value(summary)}</div>
                </div>
              ))}
            </div>

            {/* 내부 탭 + 패널 */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
              <div className="flex gap-1 border-b border-slate-200 bg-slate-50/50 px-3 pt-3">
                {tabs.map((tab) => {
                  const isActive = tab.id === activeTab;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={
                        isActive
                          ? "rounded-t-lg border border-b-0 border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-900"
                          : "rounded-t-lg px-4 py-2 text-sm font-semibold text-slate-500 hover:text-slate-800"
                      }
                    >
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              <div className="p-6">
                {loading ? (
                  <div className="space-y-2">
                    <div className="h-3 w-11/12 animate-pulse rounded bg-slate-200" />
                    <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
                    <div className="h-3 w-9/12 animate-pulse rounded bg-slate-200" />
                  </div>
                ) : activeTab === "issue_alerts" ? (
                  data && data.issue_alerts.length > 0 ? (
                    <IssueAlertList alerts={data.issue_alerts} onOpenInsight={goToInsight} focusedAlertId={focusedAlertId} />
                  ) : (
                    <div className="py-12 text-center text-sm font-medium text-slate-500">
                      {data?.empty_state?.issue_alerts ?? "표시할 실시간 이슈가 없습니다."}
                    </div>
                  )
                ) : data && data.public_insights.length > 0 ? (
                  <PublicInsightList insights={data.public_insights} onSelect={setSelectedInsight} />
                ) : (
                  <div className="py-12 text-center text-sm font-medium text-slate-500">
                    {data?.empty_state?.public_insights ?? "표시할 행정 인사이트가 없습니다."}
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>

      {selectedInsight && (
        <InsightDetailPanel insight={selectedInsight} onClose={() => setSelectedInsight(null)} onOpenAlert={goToAlert} />
      )}
    </div>
  );
}

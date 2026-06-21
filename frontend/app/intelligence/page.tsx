"use client";

import { useEffect, useState } from "react";
import AppSidebar from "@/components/AppSidebar";
import {
  fetchDuplicateGroupsApi,
  fetchIntelDashboardApi,
  type DuplicateMergeRecord,
  type IntelDashboardData,
  type IntelDashboardSummary,
  type IntelPublicInsightCard,
} from "@/lib/api";
import { DuplicateGroupTriage } from "@/components/intelligence/DuplicateGroupTriage";
import { HotspotMap } from "@/components/intelligence/HotspotMap";
import { InsightDetailPanel } from "@/components/intelligence/InsightDetailPanel";
import { IssueAlertList } from "@/components/intelligence/IssueAlertList";
import { PublicInsightList } from "@/components/intelligence/PublicInsightList";
import { countGroupsLinkedToAlert } from "@/components/intelligence/duplicateMerge";
import { findById } from "@/components/intelligence/links";

const SUMMARY_CARDS: Array<{ label: string; accent: string; value: (summary: IntelDashboardSummary) => number }> = [
  { label: "이슈 경보", accent: "border-l-blue-600", value: (summary) => summary.active_alert_count ?? summary.alert_count },
  { label: "긴급 경보", accent: "border-l-red-600", value: (summary) => summary.critical_alert_count },
  { label: "행정 인사이트", accent: "border-l-blue-600", value: (summary) => summary.public_insight_count },
  { label: "고우선 인사이트", accent: "border-l-amber-500", value: (summary) => summary.high_priority_insight_count },
  { label: "검토 필요", accent: "border-l-amber-500", value: (summary) => summary.human_review_required_count },
  { label: "연결 경보", accent: "border-l-emerald-600", value: (summary) => summary.linked_alert_count },
];

const TABS = [
  { id: "issue_alerts", label: "실시간 이슈" },
  { id: "public_insights", label: "행정 인사이트" },
  { id: "duplicate_groups", label: "중복 병합" },
];

function shortTs(iso?: string | null): string {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}

export default function IntelligencePage() {
  const [data, setData] = useState<IntelDashboardData | null>(null);
  const [duplicateGroups, setDuplicateGroups] = useState<DuplicateMergeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [duplicateLoading, setDuplicateLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [duplicateErrorMsg, setDuplicateErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("issue_alerts");
  const [selectedInsight, setSelectedInsight] = useState<IntelPublicInsightCard | null>(null);
  const [focusedAlertId, setFocusedAlertId] = useState<string | null>(null);
  const [duplicateIssueAlertFilterId, setDuplicateIssueAlertFilterId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    Promise.all([fetchIntelDashboardApi(), fetchDuplicateGroupsApi()])
      .then(([response, duplicateResponse]) => {
        if (!isMounted) return;
        setData(response.data);
        setErrorMsg(response.error ? response.error.message : null);
        setDuplicateGroups(duplicateResponse.data.duplicate_groups);
        setDuplicateErrorMsg(duplicateResponse.error ? duplicateResponse.error.message : null);
        setLoading(false);
        setDuplicateLoading(false);
      })
      .catch(() => {
        if (isMounted) {
          setErrorMsg("민원 인텔리전스 데이터를 불러오지 못했습니다.");
          setLoading(false);
          setDuplicateLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const summary = data?.summary;
  const duplicateGroupCountsByAlert = Object.fromEntries(
    (data?.issue_alerts ?? []).map((alert) => [
      alert.id,
      countGroupsLinkedToAlert(alert.id, duplicateGroups),
    ]),
  );
  const monitoringContext = summary
    ? [
        summary.as_of ? `관제 기준 ${shortTs(summary.as_of)}` : null,
        summary.latest_event_at ? `마지막 관측 ${shortTs(summary.latest_event_at)}` : null,
        summary.event_count != null ? `전체 관측 ${summary.event_count}건` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  function goToInsight(insightId: string) {
    const insight = data ? findById(data.public_insights, insightId) : undefined;
    if (!insight) return;
    setActiveTab("public_insights");
    setSelectedInsight(insight);
  }

  function goToAlert(alertId: string) {
    setSelectedInsight(null);
    setActiveTab("issue_alerts");
    setFocusedAlertId(alertId);
  }

  function openDuplicateGroupsForAlert(alertId: string) {
    setFocusedAlertId(alertId);
    setDuplicateIssueAlertFilterId(alertId);
    setActiveTab("duplicate_groups");
  }

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen w-full">
        <div className="hidden md:block">
          <AppSidebar activeMenu="intelligence" />
        </div>

        <main className="min-w-0 flex-1 p-4 md:p-6">
          <div className="mx-auto max-w-7xl space-y-6">
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">민원 인텔리전스</h1>
              <p className="mt-1 text-sm font-medium text-slate-500">
                급증 이슈, 행정 인사이트, 중복 민원 병합 후보를 한 화면에서 확인합니다.
              </p>
              {monitoringContext && <p className="mt-1 text-xs text-slate-400">{monitoringContext}</p>}
            </div>

            {errorMsg && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                백엔드 연결에 실패해 일부 정보를 표시하지 못했습니다. ({errorMsg})
              </div>
            )}
            {duplicateErrorMsg && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700">
                중복 병합 그룹을 불러오지 못했습니다. 기존 인텔리전스 정보는 계속 사용할 수 있습니다. ({duplicateErrorMsg})
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {SUMMARY_CARDS.map((card) => (
                <div
                  key={card.label}
                  className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm border-l-4 ${card.accent}`}
                >
                  <div className="mb-1 text-xs font-bold text-slate-500">{card.label}</div>
                  <div className="text-2xl font-extrabold text-slate-900">{loading || !summary ? "-" : card.value(summary)}</div>
                </div>
              ))}
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-wrap gap-1 border-b border-slate-200 bg-slate-50/50 px-3 pt-3">
                {TABS.map((tab) => {
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

              <div className="p-4 md:p-6">
                {loading ? (
                  <div className="space-y-2">
                    <div className="h-3 w-11/12 animate-pulse rounded bg-slate-200" />
                    <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
                    <div className="h-3 w-9/12 animate-pulse rounded bg-slate-200" />
                  </div>
                ) : activeTab === "issue_alerts" ? (
                  data && data.issue_alerts.length > 0 ? (
                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
                      <section className="order-2 min-w-0 xl:order-1" aria-label="핫스팟 카드 목록">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <h2 className="text-base font-extrabold text-slate-900">핫스팟 카드 목록</h2>
                            <p className="mt-1 text-xs text-slate-500">긴급도와 최근 건수 기준으로 먼저 볼 이슈를 정렬합니다.</p>
                          </div>
                          <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">
                            {data.issue_alerts.length}건
                          </span>
                        </div>
                        <IssueAlertList
                          alerts={data.issue_alerts}
                          onOpenInsight={goToInsight}
                          onFocusAlert={setFocusedAlertId}
                          onOpenDuplicateGroups={openDuplicateGroupsForAlert}
                          focusedAlertId={focusedAlertId}
                          duplicateGroupCounts={duplicateGroupCountsByAlert}
                        />
                      </section>
                      <div className="order-1 xl:order-2">
                        <HotspotMap
                          alerts={data.issue_alerts}
                          duplicateGroupCounts={duplicateGroupCountsByAlert}
                          focusedAlertId={focusedAlertId}
                          onFocusAlert={setFocusedAlertId}
                          onOpenDuplicateGroups={openDuplicateGroupsForAlert}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="py-12 text-center text-sm font-medium text-slate-500">
                      {data?.empty_state?.issue_alerts ?? "표시할 실시간 이슈가 없습니다."}
                    </div>
                  )
                ) : activeTab === "duplicate_groups" ? (
                  <DuplicateGroupTriage
                    groups={duplicateGroups}
                    loading={duplicateLoading}
                    issueAlertFilterId={duplicateIssueAlertFilterId}
                    onClearIssueAlertFilter={() => setDuplicateIssueAlertFilterId(null)}
                    onGroupUpdated={(updated) => {
                      setDuplicateGroups((current) => current.map((group) => (group.merge_id === updated.merge_id ? updated : group)));
                    }}
                  />
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

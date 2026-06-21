"use client";

import { useEffect, useMemo, useState } from "react";
import AppSidebar from "@/components/AppSidebar";
import {
  fetchDuplicateGroupsApi,
  fetchIntelDashboardApi,
  type DuplicateMergeRecord,
  type IntelDashboardData,
  type IntelIssueAlertCard,
  type IntelPublicInsightCard,
} from "@/lib/api";
import { DuplicateGroupTriage } from "@/components/intelligence/DuplicateGroupTriage";
import { HotspotMap } from "@/components/intelligence/HotspotMap";
import { InsightDetailPanel } from "@/components/intelligence/InsightDetailPanel";
import { IssueAlertList } from "@/components/intelligence/IssueAlertList";
import { PublicInsightList } from "@/components/intelligence/PublicInsightList";
import { countGroupsLinkedToAlert, duplicateGroupTitle } from "@/components/intelligence/duplicateMerge";
import { sortInsightsByPriority } from "@/components/intelligence/insight";
import { findById } from "@/components/intelligence/links";
import { sortAlertsBySeverity } from "@/components/intelligence/severity";

type ActiveIntelTab = "issue_alerts" | "public_insights" | "duplicate_groups";
type HotspotMapSize = "compact" | "large";
type Tone = "red" | "amber" | "blue" | "emerald" | "slate";
type ImmediateAction = {
  id: string;
  label: string;
  title: string;
  meta: string;
  actionLabel: string;
  tone: Tone;
  onClick: () => void;
};

const TABS: Array<{ id: ActiveIntelTab; label: string }> = [
  { id: "issue_alerts", label: "실시간 이슈" },
  { id: "public_insights", label: "행정 인사이트" },
  { id: "duplicate_groups", label: "중복 병합" },
];

function shortTs(iso?: string | null): string {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}

async function loadIntelligenceData() {
  const [dashboardResponse, duplicateResponse] = await Promise.all([
    fetchIntelDashboardApi(),
    fetchDuplicateGroupsApi(),
  ]);
  return { dashboardResponse, duplicateResponse };
}

export default function IntelligencePage() {
  const [data, setData] = useState<IntelDashboardData | null>(null);
  const [duplicateGroups, setDuplicateGroups] = useState<DuplicateMergeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [duplicateLoading, setDuplicateLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [duplicateErrorMsg, setDuplicateErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveIntelTab>("issue_alerts");
  const [selectedInsight, setSelectedInsight] = useState<IntelPublicInsightCard | null>(null);
  const [focusedAlertId, setFocusedAlertId] = useState<string | null>(null);
  const [focusedDuplicateGroupId, setFocusedDuplicateGroupId] = useState<string | null>(null);
  const [duplicateIssueAlertFilterId, setDuplicateIssueAlertFilterId] = useState<string | null>(null);
  const [showOverview, setShowOverview] = useState(false);
  const [mapSize, setMapSize] = useState<HotspotMapSize>("compact");

  useEffect(() => {
    let isMounted = true;
    loadIntelligenceData()
      .then(({ dashboardResponse, duplicateResponse }) => {
        if (!isMounted) return;
        setData(dashboardResponse.data);
        setErrorMsg(dashboardResponse.error ? dashboardResponse.error.message : null);
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
  const sortedAlerts = useMemo(() => sortAlertsBySeverity(data?.issue_alerts ?? []), [data?.issue_alerts]);
  const sortedInsights = useMemo(() => sortInsightsByPriority(data?.public_insights ?? []), [data?.public_insights]);
  const candidateDuplicateGroups = useMemo(
    () =>
      duplicateGroups
        .filter((group) => group.status === "candidate")
        .sort((a, b) => {
          const confirmDelta = Number(b.allowed_actions.includes("confirm")) - Number(a.allowed_actions.includes("confirm"));
          if (confirmDelta !== 0) return confirmDelta;
          const riskDelta = b.risk_flags.length - a.risk_flags.length;
          if (riskDelta !== 0) return riskDelta;
          return b.confidence - a.confidence;
        }),
    [duplicateGroups],
  );
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
  const tabCounts: Record<ActiveIntelTab, number> = {
    issue_alerts: data?.issue_alerts.length ?? 0,
    public_insights: data?.public_insights.length ?? 0,
    duplicate_groups: duplicateGroups.length,
  };
  const activeTabMeta = TABS.find((tab) => tab.id === activeTab) ?? TABS[0];

  async function handleRefresh() {
    setRefreshing(true);
    setErrorMsg(null);
    setDuplicateErrorMsg(null);
    const { dashboardResponse, duplicateResponse } = await loadIntelligenceData().catch(() => ({
      dashboardResponse: null,
      duplicateResponse: null,
    }));
    if (!dashboardResponse || !duplicateResponse) {
      setErrorMsg("민원 인텔리전스 데이터를 다시 불러오지 못했습니다.");
      setRefreshing(false);
      return;
    }
    setData(dashboardResponse.data);
    setErrorMsg(dashboardResponse.error ? dashboardResponse.error.message : null);
    setDuplicateGroups(duplicateResponse.data.duplicate_groups);
    setDuplicateErrorMsg(duplicateResponse.error ? duplicateResponse.error.message : null);
    setRefreshing(false);
  }

  function goToInsight(insightId: string) {
    const insight = data ? findById(data.public_insights, insightId) : undefined;
    if (!insight) return;
    setSelectedInsight(insight);
  }

  function goToAlert(alertId: string) {
    setSelectedInsight(null);
    setActiveTab("issue_alerts");
    setFocusedAlertId(alertId);
  }

  function openDuplicateGroupsForAlert(alertId: string) {
    setFocusedAlertId(alertId);
    setFocusedDuplicateGroupId(null);
    setDuplicateIssueAlertFilterId(alertId);
    setActiveTab("duplicate_groups");
  }

  function openDuplicateGroup(groupId: string) {
    setDuplicateIssueAlertFilterId(null);
    setFocusedDuplicateGroupId(groupId);
    setActiveTab("duplicate_groups");
  }

  const immediateActions = buildImmediateActions({
    alerts: sortedAlerts,
    insights: sortedInsights,
    duplicateGroups: candidateDuplicateGroups,
    duplicateGroupCountsByAlert,
    onOpenAlert: goToAlert,
    onOpenInsight: goToInsight,
    onOpenDuplicateGroup: openDuplicateGroup,
  });

  return (
    <div className="min-h-screen bg-[#f5f7fa] text-slate-900">
      <div className="flex min-h-screen w-full">
        <div className="hidden md:block">
          <AppSidebar activeMenu="intelligence" />
        </div>

        <main className="min-w-0 flex-1 p-4 md:p-6 xl:p-8">
          <div className="mx-auto max-w-[1440px] space-y-4">
            <section className="rounded-lg border border-slate-200 bg-white px-4 py-4 shadow-sm md:px-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <h1 className="text-2xl font-extrabold tracking-tight text-slate-950">민원 인텔리전스</h1>
                  {monitoringContext && <p className="mt-1 text-xs font-semibold text-slate-400">{monitoringContext}</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowOverview((value) => !value)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold text-slate-700 hover:bg-slate-50"
                  >
                    {showOverview ? "지표 접기" : "지표 보기"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRefresh()}
                    disabled={loading || refreshing}
                    className="rounded-md border border-slate-300 bg-slate-900 px-3 py-2 text-xs font-extrabold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    {refreshing ? "갱신 중" : "새로고침"}
                  </button>
                </div>
              </div>

              <div className="mt-4 grid gap-2 md:grid-cols-3">
                <FocusMetric label="긴급" value={summary?.critical_alert_count ?? 0} tone="red" onClick={() => setActiveTab("issue_alerts")} />
                <FocusMetric label="검토" value={summary?.human_review_required_count ?? 0} tone="amber" onClick={() => setActiveTab("public_insights")} />
                <FocusMetric label="중복 후보" value={candidateDuplicateGroups.length} tone="emerald" onClick={() => setActiveTab("duplicate_groups")} />
              </div>

              {showOverview && (
                <div className="mt-3 grid gap-2 border-t border-slate-100 pt-3 text-xs md:grid-cols-4">
                  <OverviewMetric label="활성 경보" value={summary?.active_alert_count ?? summary?.alert_count ?? 0} />
                  <OverviewMetric label="인사이트" value={summary?.public_insight_count ?? 0} />
                  <OverviewMetric label="고우선" value={summary?.high_priority_insight_count ?? 0} />
                  <OverviewMetric label="전체 관측" value={summary?.event_count ?? 0} />
                </div>
              )}
            </section>

            {errorMsg && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                백엔드 연결에 실패해 일부 정보를 표시하지 못했습니다. ({errorMsg})
              </div>
            )}
            {duplicateErrorMsg && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700">
                중복 병합 그룹을 불러오지 못했습니다. ({duplicateErrorMsg})
              </div>
            )}

            <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
              <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
                <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                    <h2 className="text-sm font-extrabold text-slate-950">우선 처리</h2>
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{immediateActions.length}건</span>
                  </div>
                  <div className="space-y-2 p-3">
                    {loading ? (
                      <QueueSkeleton />
                    ) : immediateActions.length > 0 ? (
                      immediateActions.map((item) => (
                        <QueueActionButton key={item.id} item={item} />
                      ))
                    ) : (
                      <div className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-xs font-semibold text-slate-500">
                        긴급 항목 없음
                      </div>
                    )}
                  </div>
                </section>

                <nav className="rounded-lg border border-slate-200 bg-white p-2 shadow-sm" aria-label="민원 인텔리전스 업무 탭">
                  {TABS.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={
                        tab.id === activeTab
                          ? "flex w-full items-center justify-between rounded-md bg-slate-900 px-3 py-2.5 text-left text-sm font-extrabold text-white"
                          : "flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-sm font-bold text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      }
                    >
                      <span>{tab.label}</span>
                      <span className={tab.id === activeTab ? "text-xs text-white/80" : "text-xs text-slate-400"}>{tabCounts[tab.id]}</span>
                    </button>
                  ))}
                </nav>
              </aside>

              <section className="min-w-0 rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-3 border-b border-slate-200 px-4 py-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h2 className="text-base font-extrabold text-slate-950">{activeTabMeta.label}</h2>
                    <p className="mt-0.5 text-xs font-semibold text-slate-400">{tabCounts[activeTab]}건</p>
                  </div>
                  {activeTab === "issue_alerts" && data && data.issue_alerts.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setMapSize((value) => (value === "large" ? "compact" : "large"));
                        }}
                        className="w-fit rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold text-slate-700 hover:bg-slate-50"
                      >
                        {mapSize === "large" ? "지도 작게보기" : "지도 크게보기"}
                      </button>
                    </div>
                  )}
                </div>

                <div className="p-4 md:p-5">
                  {loading ? (
                    <div className="space-y-2">
                      <div className="h-3 w-11/12 animate-pulse rounded bg-slate-200" />
                      <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
                      <div className="h-3 w-9/12 animate-pulse rounded bg-slate-200" />
                    </div>
                  ) : activeTab === "issue_alerts" ? (
                    data && data.issue_alerts.length > 0 ? (
                      <div
                        className={
                          mapSize === "large"
                            ? "space-y-4"
                            : "grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]"
                        }
                      >
                        {mapSize === "large" && (
                          <HotspotMap
                            alerts={data.issue_alerts}
                            duplicateGroupCounts={duplicateGroupCountsByAlert}
                            focusedAlertId={focusedAlertId}
                            size="large"
                            onFocusAlert={setFocusedAlertId}
                            onClearFocus={() => setFocusedAlertId(null)}
                            onOpenDuplicateGroups={openDuplicateGroupsForAlert}
                          />
                        )}
                        <IssueAlertList
                          alerts={data.issue_alerts}
                          onOpenInsight={goToInsight}
                          onFocusAlert={(alertId) => {
                            setFocusedAlertId(alertId);
                          }}
                          onOpenDuplicateGroups={openDuplicateGroupsForAlert}
                          focusedAlertId={focusedAlertId}
                          duplicateGroupCounts={duplicateGroupCountsByAlert}
                        />
                        {mapSize === "compact" && (
                          <HotspotMap
                            alerts={data.issue_alerts}
                            duplicateGroupCounts={duplicateGroupCountsByAlert}
                            focusedAlertId={focusedAlertId}
                            size="compact"
                            onFocusAlert={setFocusedAlertId}
                            onClearFocus={() => setFocusedAlertId(null)}
                            onOpenDuplicateGroups={openDuplicateGroupsForAlert}
                          />
                        )}
                      </div>
                    ) : (
                      <EmptyState text={data?.empty_state?.issue_alerts ?? "표시할 실시간 이슈가 없습니다."} />
                    )
                  ) : activeTab === "duplicate_groups" ? (
                    <DuplicateGroupTriage
                      groups={duplicateGroups}
                      loading={duplicateLoading}
                      focusedGroupId={focusedDuplicateGroupId}
                      issueAlertFilterId={duplicateIssueAlertFilterId}
                      onClearIssueAlertFilter={() => setDuplicateIssueAlertFilterId(null)}
                      onGroupUpdated={(updated) => {
                        setDuplicateGroups((current) => current.map((group) => (group.merge_id === updated.merge_id ? updated : group)));
                      }}
                    />
                  ) : data && data.public_insights.length > 0 ? (
                    <PublicInsightList insights={data.public_insights} onSelect={setSelectedInsight} />
                  ) : (
                    <EmptyState text={data?.empty_state?.public_insights ?? "표시할 행정 인사이트가 없습니다."} />
                  )}
                </div>
              </section>
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

function FocusMetric({ label, value, tone, onClick }: { label: string; value: number; tone: Tone; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-16 items-center justify-between rounded-md border px-3 py-2 text-left transition hover:shadow-sm ${focusMetricToneClass(tone)}`}
    >
      <span className="text-xs font-extrabold text-slate-500">{label}</span>
      <span className="text-2xl font-black tabular-nums text-slate-950">{value}</span>
    </button>
  );
}

function OverviewMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <div className="text-[10px] font-bold text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-extrabold tabular-nums text-slate-800">{value}</div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 py-12 text-center text-sm font-semibold text-slate-500">
      {text}
    </div>
  );
}

function QueueSkeleton() {
  return (
    <>
      {[0, 1, 2].map((item) => (
        <div key={item} className="animate-pulse rounded-md border border-slate-200 bg-slate-50 p-3">
          <div className="h-3 w-20 rounded bg-slate-200" />
          <div className="mt-3 h-4 w-11/12 rounded bg-slate-200" />
          <div className="mt-2 h-3 w-9/12 rounded bg-slate-200" />
        </div>
      ))}
    </>
  );
}

function QueueActionButton({ item }: { item: ImmediateAction }) {
  return (
    <button
      type="button"
      onClick={item.onClick}
      className={`w-full rounded-md border px-3 py-2 text-left transition hover:shadow-sm ${queueToneClass(item.tone)}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-extrabold">{item.label}</span>
        <span className="shrink-0 text-[10px] font-bold opacity-70">{item.actionLabel}</span>
      </div>
      <div className="mt-1 line-clamp-2 text-xs font-extrabold leading-snug text-slate-950">{item.title}</div>
      <div className="mt-1 line-clamp-1 text-[11px] font-medium text-slate-500">{item.meta}</div>
    </button>
  );
}

function buildImmediateActions({
  alerts,
  insights,
  duplicateGroups,
  duplicateGroupCountsByAlert,
  onOpenAlert,
  onOpenInsight,
  onOpenDuplicateGroup,
}: {
  alerts: IntelIssueAlertCard[];
  insights: IntelPublicInsightCard[];
  duplicateGroups: DuplicateMergeRecord[];
  duplicateGroupCountsByAlert: Record<string, number>;
  onOpenAlert: (alertId: string) => void;
  onOpenInsight: (insightId: string) => void;
  onOpenDuplicateGroup: (groupId: string) => void;
}): ImmediateAction[] {
  const urgentAlerts = alerts
    .filter((alert) => alert.severity === "CRITICAL" || alert.severity === "WARNING")
    .slice(0, 2)
    .map((alert) => ({
      id: `alert-${alert.id}`,
      label: alert.severity === "CRITICAL" ? "긴급 경보" : "주의 경보",
      title: alert.title,
      meta: `${alert.region ?? "지역 미상"} · 최근 ${alert.recent_count}건 · 중복 후보 ${duplicateGroupCountsByAlert[alert.id] ?? 0}그룹`,
      actionLabel: "경보 열기",
      tone: alert.severity === "CRITICAL" ? "red" as const : "amber" as const,
      onClick: () => onOpenAlert(alert.id),
    }));

  const reviewInsights = insights
    .filter((insight) => insight.requires_human_review || insight.priority === "CRITICAL" || insight.priority === "HIGH")
    .slice(0, 2)
    .map((insight) => ({
      id: `insight-${insight.id}`,
      label: insight.requires_human_review ? "검토 인사이트" : "고우선 인사이트",
      title: insight.title,
      meta: `${insight.target_area || "대상 지역 확인"} · 규모 ${insight.affected_count}건 · 추천 조치 ${insight.recommended_actions.length}건`,
      actionLabel: "상세 열기",
      tone: insight.priority === "CRITICAL" ? "red" as const : "blue" as const,
      onClick: () => onOpenInsight(insight.id),
    }));

  const duplicateActions = duplicateGroups.slice(0, 2).map((group) => ({
    id: `duplicate-${group.merge_id}`,
    label: group.risk_flags.length > 0 ? "주의 중복" : "중복 후보",
    title: duplicateGroupTitle(group),
    meta: `${group.member_complaint_ids.length}건 · 검토 점수 ${(group.confidence * 100).toFixed(0)}% · 주의 사유 ${group.risk_flags.length}건`,
    actionLabel: "검토 열기",
    tone: group.risk_flags.some((flag) => flag.severity === "blocker") ? "red" as const : "emerald" as const,
    onClick: () => onOpenDuplicateGroup(group.merge_id),
  }));

  return [...urgentAlerts, ...reviewInsights, ...duplicateActions].slice(0, 5);
}

function focusMetricToneClass(tone: Tone): string {
  if (tone === "red") return "border-red-200 bg-red-50/70 hover:border-red-300";
  if (tone === "amber") return "border-amber-200 bg-amber-50/70 hover:border-amber-300";
  if (tone === "emerald") return "border-emerald-200 bg-emerald-50/70 hover:border-emerald-300";
  if (tone === "blue") return "border-sky-200 bg-sky-50/70 hover:border-sky-300";
  return "border-slate-200 bg-slate-50 hover:border-slate-300";
}

function queueToneClass(tone: Tone): string {
  if (tone === "red") return "border-red-200 bg-red-50/80 text-red-800 hover:border-red-300";
  if (tone === "amber") return "border-amber-200 bg-amber-50/80 text-amber-800 hover:border-amber-300";
  if (tone === "emerald") return "border-emerald-200 bg-emerald-50/80 text-emerald-800 hover:border-emerald-300";
  if (tone === "blue") return "border-sky-200 bg-sky-50/80 text-sky-800 hover:border-sky-300";
  return "border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300";
}

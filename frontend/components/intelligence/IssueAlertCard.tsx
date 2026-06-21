import type { IntelIssueAlertCard } from "@/lib/api";
import { SeverityBadge } from "./SeverityBadge";

type IssueAlertTrendInput = Pick<IntelIssueAlertCard, "recent_count" | "baseline" | "surge_ratio">;

export function formatIssueAlertTrend(alert: IssueAlertTrendInput): string {
  const recentCount = Number.isFinite(alert.recent_count) ? alert.recent_count : 0;
  const baseline = Number.isFinite(alert.baseline) ? alert.baseline : 0;
  if (baseline === 0) {
    return `최근 ${recentCount}건 · 과거 7일 기준선 0건 · 신규 급증`;
  }
  if (baseline < 1) {
    return `최근 ${recentCount}건 · 기준선 없음 · 급증 감지`;
  }
  const baselineText = Number.isInteger(baseline) ? `${baseline}` : baseline.toFixed(1);
  const surge = Number.isFinite(alert.surge_ratio) ? alert.surge_ratio.toFixed(1) : "-";
  return `최근 ${recentCount}건 · 과거 7일 기준선 ${baselineText}건 대비 ${surge}배`;
}

export function formatIssueAlertSummary(alert: Pick<IntelIssueAlertCard, "summary" | "recent_count" | "baseline">): string {
  const baseline = Number.isFinite(alert.baseline) ? alert.baseline : 0;
  if (baseline < 1) {
    return `최근 ${alert.recent_count}건이 같은 이슈로 집중 접수되었습니다. 담당자 검토가 필요한 신규 급증 신호입니다.`;
  }
  return alert.summary;
}

export function IssueAlertCard({
  alert,
  onOpenInsight,
  onFocusAlert,
  onOpenDuplicateGroups,
  highlighted = false,
  duplicateGroupCount = 0,
}: {
  alert: IntelIssueAlertCard;
  onOpenInsight?: (insightId: string) => void;
  onFocusAlert?: (alertId: string) => void;
  onOpenDuplicateGroups?: (alertId: string) => void;
  highlighted?: boolean;
  duplicateGroupCount?: number;
}) {
  const hasDuplicateGroups = duplicateGroupCount > 0;

  return (
    <article
      id={`issue-alert-${alert.id}`}
      className={`rounded-md border bg-white px-3 py-3 transition ${
        highlighted ? "border-sky-500 ring-2 ring-sky-100" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/40"
      }`}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <SeverityBadge color={alert.color} label={alert.severity_label} />
            {hasDuplicateGroups && (
              <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700">
                중복 {duplicateGroupCount}
              </span>
            )}
            <span className="text-[11px] font-bold text-slate-400">신뢰도 {(alert.confidence * 100).toFixed(0)}%</span>
          </div>

          <h3 className="line-clamp-1 text-sm font-extrabold leading-snug text-slate-950">{alert.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-semibold text-slate-500">
            {alert.region && <span>{alert.region}</span>}
            <span>최근 {alert.recent_count}건</span>
            <span>급증 {formatSurge(alert.surge_ratio)}</span>
            <span>인사이트 {alert.linked_insight_ids.length}건</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          {onFocusAlert && (
            <button type="button" onClick={() => onFocusAlert(alert.id)} className={actionButtonClass("quiet")}>
              지도
            </button>
          )}
          {alert.linked_insight_ids.length > 0 && onOpenInsight && (
            <button
              type="button"
              onClick={() => onOpenInsight(alert.linked_insight_ids[0])}
              className={actionButtonClass(hasDuplicateGroups ? "secondary" : "primaryBlue")}
            >
              인사이트
            </button>
          )}
          {hasDuplicateGroups && onOpenDuplicateGroups && (
            <button type="button" onClick={() => onOpenDuplicateGroups(alert.id)} className={actionButtonClass("primary")}>
              중복
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

function formatSurge(ratio: number): string {
  if (!Number.isFinite(ratio) || ratio <= 0) return "-";
  return `${ratio.toFixed(1)}배`;
}

function actionButtonClass(kind: "primary" | "primaryBlue" | "secondary" | "quiet"): string {
  if (kind === "primary") {
    return "rounded-md border border-amber-300 bg-amber-100 px-3 py-1.5 text-xs font-extrabold text-amber-900 hover:bg-amber-200";
  }
  if (kind === "primaryBlue") {
    return "rounded-md border border-blue-300 bg-blue-600 px-3 py-1.5 text-xs font-extrabold text-white hover:bg-blue-700";
  }
  if (kind === "secondary") {
    return "rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-100";
  }
  return "rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50";
}

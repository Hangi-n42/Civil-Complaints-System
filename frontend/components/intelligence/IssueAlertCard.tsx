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
      tabIndex={0}
      onClick={() => onFocusAlert?.(alert.id)}
      onFocus={() => onFocusAlert?.(alert.id)}
      onMouseEnter={() => onFocusAlert?.(alert.id)}
      className={`rounded-lg border bg-white p-4 shadow-sm outline-none transition ${
        highlighted ? "border-blue-500 ring-2 ring-blue-200" : "border-slate-200 hover:border-slate-300"
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SeverityBadge color={alert.color} label={alert.severity_label} />
        {hasDuplicateGroups && (
          <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700">
            중복 후보 {duplicateGroupCount}그룹
          </span>
        )}
      </div>

      <h3 className="text-sm font-extrabold leading-snug text-slate-900">{alert.title}</h3>
      {alert.summary && <p className="mt-2 text-xs leading-relaxed text-slate-600">{formatIssueAlertSummary(alert)}</p>}

      <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">
        {formatIssueAlertTrend(alert)}
      </div>

      {alert.keywords.length > 0 && (
        <div className="mt-3 text-xs text-slate-500">
          주요 표현: <span className="font-semibold text-slate-700">{alert.keywords.slice(0, 5).join(", ")}</span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {alert.region && <span>지역 {alert.region}</span>}
        <span>대표 민원 {alert.representative_complaint_ids.length}건</span>
        <span>연결 인사이트 {alert.linked_insight_ids.length}건</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {alert.linked_insight_ids.length > 0 && onOpenInsight && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenInsight(alert.linked_insight_ids[0]);
            }}
            className="rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-100"
          >
            인사이트 보기
          </button>
        )}
        {hasDuplicateGroups && onOpenDuplicateGroups && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDuplicateGroups(alert.id);
            }}
            className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-800 hover:bg-amber-100"
          >
            중복 후보 보기
          </button>
        )}
      </div>
    </article>
  );
}

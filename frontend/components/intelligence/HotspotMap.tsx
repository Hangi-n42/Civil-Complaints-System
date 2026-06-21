"use client";

import dynamic from "next/dynamic";
import type { IntelIssueAlertCard } from "@/lib/api";
import { formatIssueAlertTrend } from "./IssueAlertCard";
import { resolveHotspotMapPoint, hotspotSeverityTone } from "./hotspotMapUtils";
import { sortAlertsBySeverity } from "./severity";

const LeafletHotspotMap = dynamic(
  () => import("./LeafletHotspotMap").then((module) => module.LeafletHotspotMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center bg-slate-50 text-xs font-semibold text-slate-500">
        지도를 불러오는 중입니다.
      </div>
    ),
  },
);

type HotspotMapProps = {
  alerts: IntelIssueAlertCard[];
  duplicateGroupCounts?: Record<string, number>;
  focusedAlertId?: string | null;
  onFocusAlert?: (alertId: string) => void;
  onOpenDuplicateGroups?: (alertId: string) => void;
};

export function HotspotMap({
  alerts,
  duplicateGroupCounts = {},
  focusedAlertId,
  onFocusAlert,
  onOpenDuplicateGroups,
}: HotspotMapProps) {
  const sortedAlerts = sortAlertsBySeverity(alerts);
  const visibleAlerts = sortedAlerts.filter((alert) => resolveHotspotMapPoint(alert) !== null);
  const unknownAlerts = sortedAlerts.filter((alert) => resolveHotspotMapPoint(alert) === null);
  const selectedAlert =
    sortedAlerts.find((alert) => alert.id === focusedAlertId) ??
    sortedAlerts[0] ??
    null;

  return (
    <aside className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm xl:sticky xl:top-6">
      <div className="mb-3">
        <h2 className="text-sm font-extrabold text-slate-900">핫스팟 지도</h2>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          지도 위에 민원 발생 중심과 반경을 표시합니다. 정확한 주소가 아니라 관제용 위치 신호입니다.
        </p>
      </div>

      <div className="relative h-[340px] overflow-hidden rounded-lg border border-slate-200 bg-slate-50 md:h-[380px] xl:h-[420px]">
        {visibleAlerts.length > 0 ? (
          <LeafletHotspotMap
            alerts={visibleAlerts}
            duplicateGroupCounts={duplicateGroupCounts}
            focusedAlertId={selectedAlert?.id ?? focusedAlertId}
            onFocusAlert={onFocusAlert}
            onOpenDuplicateGroups={onOpenDuplicateGroups}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm font-medium text-slate-500">
            지도에 표시할 위치 신호가 없습니다.
          </div>
        )}
      </div>

      {selectedAlert && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${severityBadgeClass(selectedAlert.severity)}`}>
              {selectedAlert.severity_label || hotspotSeverityTone(selectedAlert.severity).label}
            </span>
            {selectedAlert.region && <span className="text-xs font-semibold text-slate-500">{selectedAlert.region}</span>}
          </div>
          <h3 className="mt-2 line-clamp-2 text-sm font-extrabold text-slate-900">{selectedAlert.title}</h3>
          <p className="mt-1 text-xs font-medium text-slate-600">{formatIssueAlertTrend(selectedAlert)}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] font-semibold text-slate-500">
            <span>최근 {selectedAlert.recent_count}건</span>
            <span>연결 인사이트 {selectedAlert.linked_insight_ids.length}건</span>
            <span>중복 후보 {duplicateGroupCounts[selectedAlert.id] ?? 0}그룹</span>
          </div>
          {(duplicateGroupCounts[selectedAlert.id] ?? 0) > 0 && (
            <button
              type="button"
              onClick={() => onOpenDuplicateGroups?.(selectedAlert.id)}
              className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-extrabold text-amber-800 hover:bg-amber-100"
            >
              중복 후보 보기
            </button>
          )}
        </div>
      )}

      {unknownAlerts.length > 0 && (
        <div className="mt-3 rounded-lg border border-dashed border-slate-200 p-3">
          <div className="text-xs font-extrabold text-slate-600">위치 불명확</div>
          <ul className="mt-2 space-y-1 text-xs text-slate-500">
            {unknownAlerts.slice(0, 3).map((alert) => (
              <li key={alert.id} className="line-clamp-1">
                {alert.title}
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

function severityBadgeClass(severity: string): string {
  const normalized = severity.toUpperCase();
  if (normalized === "CRITICAL") return "border-red-200 bg-red-50 text-red-700";
  if (normalized === "WARNING") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

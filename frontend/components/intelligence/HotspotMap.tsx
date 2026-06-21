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
  size?: "compact" | "large";
  onFocusAlert?: (alertId: string) => void;
  onClearFocus?: () => void;
  onOpenDuplicateGroups?: (alertId: string) => void;
};

export function HotspotMap({
  alerts,
  duplicateGroupCounts = {},
  focusedAlertId,
  size = "compact",
  onFocusAlert,
  onClearFocus,
  onOpenDuplicateGroups,
}: HotspotMapProps) {
  const sortedAlerts = sortAlertsBySeverity(alerts);
  const visibleAlerts = sortedAlerts.filter((alert) => resolveHotspotMapPoint(alert) !== null);
  const unknownAlerts = sortedAlerts.filter((alert) => resolveHotspotMapPoint(alert) === null);
  const selectedAlert = sortedAlerts.find((alert) => alert.id === focusedAlertId) ?? null;
  const mapHeightClass = size === "large" ? "h-[520px] md:h-[620px]" : "h-[340px] md:h-[380px] xl:h-[420px]";
  const detailClass = size === "large" ? "grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]" : "";

  return (
    <aside className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-extrabold text-slate-950">핫스팟 지도</h2>
          <div className="flex flex-wrap items-center gap-2">
            {selectedAlert && (
              <button
                type="button"
                onClick={onClearFocus}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-extrabold text-slate-700 hover:bg-slate-50"
              >
                대한민국 전체보기
              </button>
            )}
            <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">
              {visibleAlerts.length}개 표시
            </span>
          </div>
        </div>
        <p className="mt-1 text-xs font-medium leading-relaxed text-slate-500">민원 발생 중심과 반경을 확인합니다.</p>
      </div>

      <div className={`relative overflow-hidden rounded-lg border border-slate-200 bg-slate-50 ${mapHeightClass}`}>
        {visibleAlerts.length > 0 ? (
          <LeafletHotspotMap
            alerts={visibleAlerts}
            duplicateGroupCounts={duplicateGroupCounts}
            focusedAlertId={focusedAlertId}
            onFocusAlert={onFocusAlert}
            onOpenDuplicateGroups={onOpenDuplicateGroups}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm font-medium text-slate-500">
            지도에 표시할 위치 신호가 없습니다.
          </div>
        )}
      </div>

      {selectedAlert ? (
        <div className={`mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 ${detailClass}`}>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${severityBadgeClass(selectedAlert.severity)}`}>
                {selectedAlert.severity_label || hotspotSeverityTone(selectedAlert.severity).label}
              </span>
              {selectedAlert.region && <span className="text-xs font-semibold text-slate-500">{selectedAlert.region}</span>}
            </div>
            <h3 className="mt-2 line-clamp-2 text-sm font-extrabold text-slate-900">{selectedAlert.title}</h3>
            <p className="mt-1 text-xs font-medium text-slate-600">{formatIssueAlertTrend(selectedAlert)}</p>
          </div>
          <div>
            <div className="mt-3 grid grid-cols-3 overflow-hidden rounded-md border border-slate-200 bg-white text-center">
              <MapMetric label="최근" value={`${selectedAlert.recent_count}건`} />
              <MapMetric label="인사이트" value={`${selectedAlert.linked_insight_ids.length}건`} />
              <MapMetric label="중복" value={`${duplicateGroupCounts[selectedAlert.id] ?? 0}그룹`} />
            </div>
            {(duplicateGroupCounts[selectedAlert.id] ?? 0) > 0 && (
              <button
                type="button"
                onClick={() => onOpenDuplicateGroups?.(selectedAlert.id)}
                className="mt-3 w-full rounded-md border border-amber-300 bg-amber-100 px-3 py-2 text-xs font-extrabold text-amber-900 hover:bg-amber-200"
              >
                중복 후보 보기
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs font-semibold text-slate-500">
          지도에서 핫스팟을 클릭하면 상세 정보를 확인할 수 있습니다.
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

function MapMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-r border-slate-200 px-2 py-2 last:border-r-0">
      <div className="text-[10px] font-bold text-slate-400">{label}</div>
      <div className="mt-0.5 text-[11px] font-extrabold text-slate-700">{value}</div>
    </div>
  );
}

function severityBadgeClass(severity: string): string {
  const normalized = severity.toUpperCase();
  if (normalized === "CRITICAL") return "border-red-200 bg-red-50 text-red-700";
  if (normalized === "WARNING") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

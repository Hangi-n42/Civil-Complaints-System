"use client";

import L from "leaflet";
import { Fragment, useEffect, useMemo } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import type { IntelIssueAlertCard } from "@/lib/api";
import { formatIssueAlertTrend } from "./IssueAlertCard";
import {
  averageMapCenter,
  hotspotCircleRadius,
  hotspotMarkerSize,
  hotspotSeverityTone,
  resolveHotspotMapPoint,
  type HotspotMapPoint,
} from "./hotspotMapUtils";

type LeafletHotspotMapProps = {
  alerts: IntelIssueAlertCard[];
  duplicateGroupCounts: Record<string, number>;
  focusedAlertId?: string | null;
  onFocusAlert?: (alertId: string) => void;
  onOpenDuplicateGroups?: (alertId: string) => void;
};

export function LeafletHotspotMap({
  alerts,
  duplicateGroupCounts,
  focusedAlertId,
  onFocusAlert,
  onOpenDuplicateGroups,
}: LeafletHotspotMapProps) {
  const plottedAlerts = useMemo(() => {
    return alerts
      .map((alert) => ({ alert, point: resolveHotspotMapPoint(alert) }))
      .filter((item): item is { alert: IntelIssueAlertCard; point: HotspotMapPoint } => item.point !== null);
  }, [alerts]);

  const selectedItem = plottedAlerts.find((item) => item.alert.id === focusedAlertId) ?? plottedAlerts[0] ?? null;
  const center = selectedItem
    ? [selectedItem.point.latitude, selectedItem.point.longitude] as [number, number]
    : averageMapCenter(plottedAlerts.map((item) => item.point));

  return (
    <MapContainer
      center={center}
      zoom={13}
      scrollWheelZoom={false}
      className="h-full w-full"
      attributionControl
    >
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapFocus point={selectedItem?.point ?? null} />
      {plottedAlerts.map(({ alert, point }) => {
        const duplicateCount = duplicateGroupCounts[alert.id] ?? 0;
        const selected = alert.id === selectedItem?.alert.id;
        const tone = hotspotSeverityTone(alert.severity);
        const icon = createHotspotIcon({
          color: tone.markerColor,
          borderColor: selected ? "#1d4ed8" : tone.borderColor,
          count: alert.recent_count,
          duplicateCount,
          selected,
          size: hotspotMarkerSize(alert.recent_count),
        });

        return (
          <Fragment key={alert.id}>
            <Circle
              center={[point.latitude, point.longitude]}
              radius={hotspotCircleRadius(alert)}
              pathOptions={{
                color: tone.borderColor,
                fillColor: tone.fillColor,
                fillOpacity: selected ? 0.35 : 0.2,
                opacity: selected ? 0.9 : 0.55,
                weight: selected ? 3 : 2,
              }}
              eventHandlers={{
                click: () => onFocusAlert?.(alert.id),
                mouseover: () => onFocusAlert?.(alert.id),
              }}
            />
            <Marker
              position={[point.latitude, point.longitude]}
              icon={icon}
              eventHandlers={{
                click: () => onFocusAlert?.(alert.id),
                mouseover: () => onFocusAlert?.(alert.id),
              }}
            >
              <Popup>
                <div className="w-56 space-y-2 text-xs text-slate-700">
                  <div>
                    <div className="font-extrabold text-slate-900">{alert.title}</div>
                    <div className="mt-1 text-slate-500">{point.source === "center" ? "관측 중심" : `${point.label} 대표 위치`}</div>
                  </div>
                  <div>{formatIssueAlertTrend(alert)}</div>
                  <div className="flex flex-wrap gap-1">
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-bold">최근 {alert.recent_count}건</span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-bold">중복 후보 {duplicateCount}그룹</span>
                  </div>
                  {duplicateCount > 0 && (
                    <button
                      type="button"
                      onClick={() => onOpenDuplicateGroups?.(alert.id)}
                      className="w-full rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 font-extrabold text-amber-800 hover:bg-amber-100"
                    >
                      중복 후보 보기
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          </Fragment>
        );
      })}
    </MapContainer>
  );
}

function MapFocus({ point }: { point: HotspotMapPoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (point) {
      map.setView([point.latitude, point.longitude], Math.max(map.getZoom(), 13), { animate: true });
    }
  }, [map, point]);
  return null;
}

function createHotspotIcon({
  color,
  borderColor,
  count,
  duplicateCount,
  selected,
  size,
}: {
  color: string;
  borderColor: string;
  count: number;
  duplicateCount: number;
  selected: boolean;
  size: number;
}) {
  const badge = duplicateCount > 0
    ? `<span style="position:absolute;right:-8px;top:-8px;min-width:20px;height:20px;border-radius:999px;border:2px solid white;background:#f59e0b;color:white;font-size:10px;line-height:16px;text-align:center;font-weight:800;">${duplicateCount}</span>`
    : "";

  return L.divIcon({
    className: "hotspot-leaflet-marker",
    html: `
      <span
        aria-hidden="true"
        style="position:relative;display:flex;align-items:center;justify-content:center;width:${size}px;height:${size}px;border-radius:999px;border:3px solid ${borderColor};background:${color};color:white;font-size:11px;font-weight:900;box-shadow:${selected ? "0 0 0 6px rgba(37,99,235,0.24)" : "0 8px 18px rgba(15,23,42,0.22)"};"
      >
        ${count}
        ${badge}
      </span>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

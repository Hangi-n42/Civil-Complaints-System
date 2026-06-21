import type { IntelIssueAlertCard } from "@/lib/api";

export type HotspotMapPoint = {
  latitude: number;
  longitude: number;
  source: "region" | "center";
  label: string;
};

export const KOREA_MAP_CENTER: [number, number] = [36.45, 127.85];
export const KOREA_MAP_ZOOM = 7;

// 실제 주소 좌표가 아니라 데모 지도 표시용 행정구역 대표 좌표입니다.
const REGION_POINTS: Record<string, { latitude: number; longitude: number }> = {
  중구: { latitude: 37.5636, longitude: 126.9976 },
  서구: { latitude: 37.5454, longitude: 126.6759 },
  동구: { latitude: 37.4739, longitude: 126.6432 },
  남구: { latitude: 37.4634, longitude: 126.6506 },
  북구: { latitude: 35.1941, longitude: 126.9121 },
  새빛동: { latitude: 37.5665, longitude: 126.978 },
  달빛동: { latitude: 37.5563, longitude: 126.9237 },
  온누리동: { latitude: 37.5729, longitude: 126.9794 },
};

export function resolveHotspotMapPoint(alert: IntelIssueAlertCard): HotspotMapPoint | null {
  const latitude = numericValue(alert.center, "latitude");
  const longitude = numericValue(alert.center, "longitude");
  const region = normalizeRegion(alert.region);

  if (latitude !== null && longitude !== null) {
    return {
      latitude: clamp(latitude, 33, 39),
      longitude: clamp(longitude, 124, 132),
      source: "center",
      label: region || "관측 중심",
    };
  }

  if (region && REGION_POINTS[region]) {
    return { ...REGION_POINTS[region], source: "region", label: region };
  }

  return null;
}

export function hotspotMarkerSize(recentCount: number): number {
  if (recentCount >= 12) return 44;
  if (recentCount >= 8) return 38;
  if (recentCount >= 4) return 32;
  return 28;
}

export function hotspotCircleRadius(alert: IntelIssueAlertCard): number {
  const radiusKm = typeof alert.radius === "number" && Number.isFinite(alert.radius) ? alert.radius : null;
  if (radiusKm !== null && radiusKm > 0) {
    return Math.max(180, Math.min(1200, radiusKm * 1000));
  }
  return Math.max(180, Math.min(900, alert.recent_count * 80));
}

export function hotspotSeverityTone(severity: string): {
  markerColor: string;
  fillColor: string;
  borderColor: string;
  label: string;
} {
  const normalized = severity.toUpperCase();
  if (normalized === "CRITICAL") {
    return {
      markerColor: "#dc2626",
      fillColor: "#fee2e2",
      borderColor: "#b91c1c",
      label: "긴급",
    };
  }
  if (normalized === "WARNING") {
    return {
      markerColor: "#f59e0b",
      fillColor: "#fef3c7",
      borderColor: "#d97706",
      label: "주의",
    };
  }
  return {
    markerColor: "#2563eb",
    fillColor: "#dbeafe",
    borderColor: "#1d4ed8",
    label: "관찰",
  };
}

export function averageMapCenter(points: HotspotMapPoint[]): [number, number] {
  if (points.length === 0) return KOREA_MAP_CENTER;
  const latitude = points.reduce((sum, point) => sum + point.latitude, 0) / points.length;
  const longitude = points.reduce((sum, point) => sum + point.longitude, 0) / points.length;
  return [latitude, longitude];
}

function normalizeRegion(region: string | null): string | null {
  const value = (region ?? "").trim();
  return value || null;
}

function numericValue(center: IntelIssueAlertCard["center"], key: string): number | null {
  if (!center) return null;
  const value = center[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

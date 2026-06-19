import type { IntelIssueAlertCard } from "@/lib/api";
import { SeverityBadge } from "./SeverityBadge";

// 실시간 이슈 경보 1건 카드(핸드오프 §4.1). 지도는 본 단계 범위 밖(별도/2단계).
export function IssueAlertCard({ alert }: { alert: IntelIssueAlertCard }) {
  const surge = Number.isFinite(alert.surge_ratio) ? alert.surge_ratio.toFixed(1) : "-";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <SeverityBadge color={alert.color} label={alert.severity_label} />
        <h3 className="text-sm font-bold text-slate-900">{alert.title}</h3>
      </div>

      {alert.summary && <p className="mb-2 text-xs leading-relaxed text-slate-600">{alert.summary}</p>}

      <div className="mb-2 text-xs font-medium text-slate-700">
        최근 <span className="font-bold">{alert.recent_count}건</span>
        {" · baseline "}
        {alert.baseline} 대비 <span className="font-bold text-red-600">{surge}배</span>
      </div>

      {alert.keywords.length > 0 && (
        <div className="mb-2 text-xs text-slate-500">
          대표 표현: <span className="text-slate-700">{alert.keywords.join(", ")}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
        {alert.region && <span>지역 {alert.region}</span>}
        <span>대표 민원 {alert.representative_complaint_ids.length}건</span>
        <span>연결 인사이트 {alert.linked_insight_ids.length}건</span>
      </div>
    </div>
  );
}

import type { IntelPublicInsightCard } from "@/lib/api";
import { InsightPriorityBadge } from "./InsightPriorityBadge";
import { actionTypeLabel } from "./insight";

// 행정 인사이트 1건 카드(핸드오프 §4.2). 클릭하면 상세 패널을 연다.
export function PublicInsightCard({
  insight,
  onSelect,
}: {
  insight: IntelPublicInsightCard;
  onSelect: (insight: IntelPublicInsightCard) => void;
}) {
  const primaryActionLabel = insight.recommended_actions[0]
    ? actionTypeLabel(insight.recommended_actions[0].action_type)
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(insight)}
      className="w-full rounded-md border border-slate-200 bg-white px-3 py-3 text-left transition hover:border-slate-300 hover:bg-slate-50/50"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{insight.type_label}</span>
            <InsightPriorityBadge color={insight.color} label={insight.priority_label} />
            {insight.requires_human_review && (
              <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                담당자 검토 필요
              </span>
            )}
          </div>

          <h3 className="line-clamp-1 text-sm font-extrabold text-slate-950">{insight.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-semibold text-slate-500">
            <span>{insight.target_area || "대상 확인"}</span>
            <span>규모 {insight.affected_count}건</span>
            <span>추천 {insight.recommended_actions.length}건</span>
            {primaryActionLabel && <span>우선 {primaryActionLabel}</span>}
          </div>
        </div>

        <span className="shrink-0 rounded-md border border-blue-200 bg-white px-3 py-1.5 text-xs font-extrabold text-blue-700">
          상세 검토
        </span>
      </div>
    </button>
  );
}

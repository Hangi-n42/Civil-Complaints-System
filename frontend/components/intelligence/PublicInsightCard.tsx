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
  return (
    <button
      type="button"
      onClick={() => onSelect(insight)}
      className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-colors hover:bg-slate-50"
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{insight.type_label}</span>
        <InsightPriorityBadge color={insight.color} label={insight.priority_label} />
        {insight.requires_human_review && (
          <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
            담당자 검토 필요
          </span>
        )}
      </div>

      <h3 className="text-sm font-bold text-slate-900">{insight.title}</h3>
      {insight.summary && <p className="mt-1 text-xs leading-relaxed text-slate-600">{insight.summary}</p>}
      {insight.problem_diagnosis && (
        <p className="mt-2 line-clamp-2 text-xs text-slate-500">진단: {insight.problem_diagnosis}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
        {insight.target_area && <span>{insight.target_area}</span>}
        <span>규모 {insight.affected_count}건</span>
        <span>신뢰도 {(insight.grounding_score * 100).toFixed(0)}%</span>
        <span>추천 조치 {insight.recommended_actions.length}건</span>
      </div>
      {insight.recommended_actions[0] && (
        <div className="mt-2 text-[11px] font-semibold text-slate-500">
          우선 조치: {actionTypeLabel(insight.recommended_actions[0].action_type)}
        </div>
      )}
    </button>
  );
}

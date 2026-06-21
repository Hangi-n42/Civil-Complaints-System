import { priorityColorClass } from "./insight";

// 행정 인사이트 우선순위 뱃지. 백엔드가 준 color/priority_label을 그대로 소비한다.
export function InsightPriorityBadge({ color, label }: { color: string; label: string }) {
  return (
    <span
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-2 py-0.5 text-[10px] font-bold leading-tight ${priorityColorClass(color)}`}
    >
      {label}
    </span>
  );
}

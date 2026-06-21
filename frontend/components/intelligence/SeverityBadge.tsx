import { severityColorClass } from "./severity";

// 이슈 경보 심각도 뱃지. 백엔드가 준 color/severity_label을 그대로 소비한다.
export function SeverityBadge({ color, label }: { color: string; label: string }) {
  return (
    <span
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-2 py-0.5 text-[10px] font-bold leading-tight ${severityColorClass(color)}`}
    >
      {label}
    </span>
  );
}

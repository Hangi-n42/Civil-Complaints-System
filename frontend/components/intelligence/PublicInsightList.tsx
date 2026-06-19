import type { IntelPublicInsightCard } from "@/lib/api";
import { PublicInsightCard } from "./PublicInsightCard";
import { sortInsightsByPriority } from "./insight";

// 행정 인사이트 목록 — 우선순위 높은 순으로 정렬해 카드로 렌더한다.
export function PublicInsightList({
  insights,
  onSelect,
}: {
  insights: IntelPublicInsightCard[];
  onSelect: (insight: IntelPublicInsightCard) => void;
}) {
  const sorted = sortInsightsByPriority(insights);

  return (
    <div className="space-y-3">
      {sorted.map((insight) => (
        <PublicInsightCard key={insight.id} insight={insight} onSelect={onSelect} />
      ))}
    </div>
  );
}

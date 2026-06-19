import type { IntelIssueAlertCard } from "@/lib/api";
import { IssueAlertCard } from "./IssueAlertCard";
import { sortAlertsBySeverity } from "./severity";

// 실시간 이슈 경보 목록 — 심각도 높은 순으로 정렬해 카드로 렌더한다.
export function IssueAlertList({ alerts }: { alerts: IntelIssueAlertCard[] }) {
  const sorted = sortAlertsBySeverity(alerts);

  return (
    <div className="space-y-3">
      {sorted.map((alert) => (
        <IssueAlertCard key={alert.id} alert={alert} />
      ))}
    </div>
  );
}

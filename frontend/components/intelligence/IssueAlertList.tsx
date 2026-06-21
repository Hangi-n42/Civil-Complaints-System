"use client";

import { useEffect, useRef } from "react";
import type { IntelIssueAlertCard } from "@/lib/api";
import { IssueAlertCard } from "./IssueAlertCard";
import { sortAlertsBySeverity } from "./severity";

export function IssueAlertList({
  alerts,
  onOpenInsight,
  onFocusAlert,
  onOpenDuplicateGroups,
  focusedAlertId,
  duplicateGroupCounts = {},
}: {
  alerts: IntelIssueAlertCard[];
  onOpenInsight?: (insightId: string) => void;
  onFocusAlert?: (alertId: string) => void;
  onOpenDuplicateGroups?: (alertId: string) => void;
  focusedAlertId?: string | null;
  duplicateGroupCounts?: Record<string, number>;
}) {
  const sorted = sortAlertsBySeverity(alerts);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!focusedAlertId) return;
    const element = document.getElementById(`issue-alert-${focusedAlertId}`);
    element?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedAlertId]);

  return (
    <div ref={containerRef} className="space-y-3">
      {sorted.map((alert) => (
        <IssueAlertCard
          key={alert.id}
          alert={alert}
          onOpenInsight={onOpenInsight}
          onFocusAlert={onFocusAlert}
          onOpenDuplicateGroups={onOpenDuplicateGroups}
          highlighted={alert.id === focusedAlertId}
          duplicateGroupCount={duplicateGroupCounts[alert.id] ?? 0}
        />
      ))}
    </div>
  );
}

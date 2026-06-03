// components/SearchUI.tsx
import React from "react";
import { safeNumber, safeString } from "@/lib/safe-data";
import type { RetrievedDoc } from "@/lib/api";

type BadgeSpec = {
  styles: Record<string, string>;
  fallbackValue: string;
  defaultClassName: string;
};

function MappedBadge({
  value,
  spec,
}: {
  value: unknown;
  spec: BadgeSpec;
}) {
  const label = safeString(value, spec.fallbackValue).trim() || spec.fallbackValue;
  const styleClass = spec.styles[label] || spec.styles[spec.fallbackValue];

  return (
    <span className={`${spec.defaultClassName} ${styleClass}`}>
      {label}
    </span>
  );
}

const BADGE_BASE_CLASS = "inline-flex items-center justify-center whitespace-nowrap px-2 py-0 text-[10px] leading-tight h-5 min-w-[64px]";

// 1. 상태 배지 (StatusBadge)
export const StatusBadge = ({ status }: { status: string }) => (
  <MappedBadge
    value={status}
    spec={{
      styles: {
        미처리: "bg-slate-800 text-white",
        검토중: "bg-slate-200 text-slate-500",
        처리완료: "bg-white text-slate-500 border border-slate-400",
      },
      fallbackValue: "미처리",
      defaultClassName: `${BADGE_BASE_CLASS} rounded-full font-black tracking-wide`,
    }}
  />
);

// 2. 우선순위 배지 (PriorityBadge)
export const PriorityBadge = ({ priority }: { priority: string }) => (
  <MappedBadge
    value={priority}
    spec={{
      styles: {
        매우급함: "bg-red-100 text-red-800 border border-red-200",
        급함: "bg-amber-100 text-amber-800 border border-amber-200",
        보통: "bg-blue-50 text-blue-800 border border-blue-200",
      },
      fallbackValue: "보통",
      defaultClassName: `${BADGE_BASE_CLASS} rounded-md font-bold`,
    }}
  />
);

// 3. 신뢰도 점수 (ConfidenceScore)
export const ConfidenceScore = ({ score }: { score: number }) => {
  const normalizedScore = safeNumber(score, Number.NaN);

  if (!Number.isFinite(normalizedScore)) {
    return null;
  }

  const percentage = (normalizedScore * 100).toFixed(0);
  if (normalizedScore >= 0.9) return <span className="text-emerald-500 font-bold text-xs">{percentage}% (높음)</span>;
  if (normalizedScore >= 0.75) return <span className="text-amber-500 font-bold text-xs">{percentage}% (중간)</span>;
  return <span className="text-red-500 font-bold text-xs">{percentage}% (낮음)</span>;
};

// 4. 검색 결과 카드 (SearchResultCard)
export function SearchResultCard({ result, idx }: { result: Partial<RetrievedDoc>; idx: number }) {
  const title = safeString(result?.title, "제목 없음").trim() || "제목 없음";
  const caseId = safeString(result?.case_id, "-").trim() || "-";
  const receivedAt = safeString(result?.received_at, "-").trim() || "-";
  const snippet = safeString(result?.snippet, "").trim() || "상세 설명이 없습니다.";
  const similarityScore = safeNumber(result?.similarity_score, 0);

  return (
    <div className="p-4 border-b border-slate-100 hover:bg-slate-50 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 pr-4">
          <span className="font-bold text-sm text-blue-600 mr-2">유사민원 {idx + 1}</span>
          <span className="font-bold text-sm text-slate-800">{title}</span>
        </div>
        <div className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100 shrink-0">
          {Math.round(similarityScore * 100)}%
        </div>
      </div>
      <div className="text-[11px] text-slate-500 mb-2 flex items-center gap-2">
        <span>{caseId}</span>
        <span>|</span>
        <span>{receivedAt}</span>
      </div>
      <div className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
        {snippet}
      </div>
    </div>
  );
}

// 5. 검색 상태 배너 (StatusBanner)
export function StatusBanner({ state, resultCount, errorMsg }: { state: string | null; resultCount?: number; errorMsg?: string | null }) {
  if (!state || state === "idle") return <div className="p-3 bg-blue-50 text-blue-800 text-sm rounded-lg border border-blue-100">검색 조건을 입력하고 실행하세요.</div>;
  if (state === "loading") return <div className="p-3 bg-slate-100 text-slate-700 text-sm rounded-lg border border-slate-200 animate-pulse">검색 요청을 처리 중입니다...</div>;
  if (state === "error" || state === "error_fallback") return <div className="p-3 bg-red-50 text-red-800 text-sm rounded-lg border border-red-100">{errorMsg || "서버 지연으로 인해 Mock 데이터를 표시합니다."}</div>;
  if (state === "success") return <div className="p-3 bg-emerald-50 text-emerald-800 text-sm rounded-lg border border-emerald-100">총 {resultCount || 0}건의 유사 사례를 찾았습니다.</div>;
  return null;
}
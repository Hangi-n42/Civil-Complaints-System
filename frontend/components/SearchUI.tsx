// components/SearchUI.tsx
import React from 'react';

// 1. 상태 배지 (StatusBadge)
export const StatusBadge = ({ status }: { status: string }) => {
  const styles: Record<string, string> = {
    '미처리': 'bg-slate-800 text-white',
    '검토중': 'bg-slate-200 text-slate-500',
    '처리완료': 'bg-white text-slate-500 border border-slate-400',
  };
  
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-black tracking-wide ${styles[status] || styles['미처리']}`}>
      {status || '미처리'}
    </span>
  );
};

// 2. 우선순위 배지 (PriorityBadge)
export const PriorityBadge = ({ priority }: { priority: string }) => {
  const styles: Record<string, string> = {
    '매우급함': 'bg-red-100 text-red-800 border border-red-200',
    '급함': 'bg-amber-100 text-amber-800 border border-amber-200',
    '보통': 'bg-blue-50 text-blue-800 border border-blue-200',
  };
  
  return (
    <span className={`inline-block px-2 py-0.5 rounded-md text-[11px] font-bold ${styles[priority] || styles['보통']}`}>
      {priority || '보통'}
    </span>
  );
};

// 3. 신뢰도 점수 (ConfidenceScore)
export const ConfidenceScore = ({ score }: { score: number }) => {
  if (typeof score !== 'number') return null;
  const percentage = (score * 100).toFixed(0);
  if (score >= 0.90) return <span className="text-emerald-500 font-bold text-xs">{percentage}% (높음)</span>;
  if (score >= 0.75) return <span className="text-amber-500 font-bold text-xs">{percentage}% (중간)</span>;
  return <span className="text-red-500 font-bold text-xs">{percentage}% (낮음)</span>;
};

// 4. 검색 결과 카드 (SearchResultCard)
export function SearchResultCard({ result, idx, onUseResult }: { result: any, idx: number, onUseResult?: (res: any) => void }) {
  return (
    <div className="p-4 border-b border-slate-100 hover:bg-slate-50 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 pr-4">
          <span className="font-bold text-sm text-blue-600 mr-2">유사민원 {idx + 1}</span>
          <span className="font-bold text-sm text-slate-800">{result.title}</span>
        </div>
        <div className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100 shrink-0">
          {(result.similarity_score * 100).toFixed(0)}%
        </div>
      </div>
      <div className="text-[11px] text-slate-500 mb-2 flex items-center gap-2">
        <span>{result.case_id}</span>
        <span>|</span>
        <span>{result.received_at}</span>
      </div>
      <div className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
        {result.snippet}
      </div>
    </div>
  );
}

// 5. 검색 상태 배너 (StatusBanner)
export function StatusBanner({ state, resultCount, errorMsg }: { state: string | null, resultCount?: number, errorMsg?: string | null }) {
  if (!state || state === "idle") return <div className="p-3 bg-blue-50 text-blue-800 text-sm rounded-lg border border-blue-100">검색 조건을 입력하고 실행하세요.</div>;
  if (state === "loading") return <div className="p-3 bg-slate-100 text-slate-700 text-sm rounded-lg border border-slate-200 animate-pulse">검색 요청을 처리 중입니다...</div>;
  if (state === "error" || state === "error_fallback") return <div className="p-3 bg-red-50 text-red-800 text-sm rounded-lg border border-red-100">{errorMsg || "서버 지연으로 인해 Mock 데이터를 표시합니다."}</div>;
  if (state === "success") return <div className="p-3 bg-emerald-50 text-emerald-800 text-sm rounded-lg border border-emerald-100">총 {resultCount || 0}건의 유사 사례를 찾았습니다.</div>;
  return null;
}
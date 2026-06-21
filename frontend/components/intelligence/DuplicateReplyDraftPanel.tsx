"use client";

import type { DuplicateReplyDraft } from "@/lib/api";
import { replyDraftFallbackNotice, safetyWarningLabel } from "./duplicateMerge";

// /reply-draft 결과 패널. 자동 발송이 아니라 담당자 검토용 대표 답변 초안을 표시한다(핸드오프 §E/§11).
export function DuplicateReplyDraftPanel({
  replyDraft,
  onClose,
}: {
  replyDraft: DuplicateReplyDraft;
  onClose: () => void;
}) {
  const fallbackNotice = replyDraftFallbackNotice(replyDraft.generation_metadata);
  const safetyWarnings = replyDraft.safety_warnings ?? [];
  const limitations = replyDraft.limitations ?? [];
  const citations = replyDraft.citations ?? [];
  const searchResults = replyDraft.search_results ?? [];

  return (
    <section
      aria-label="담당자 검토용 대표 답변 초안"
      className="rounded-lg border border-emerald-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold text-slate-900">담당자 검토용 대표 답변 초안</h3>
          <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
            확정된 중복 그룹에 공통으로 적용할 대표 답변 초안입니다. 자동 발송 대상이 아니며 담당자 검토 후 사용하세요.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-600 hover:bg-slate-50"
        >
          닫기
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-800">
          자동 발송 아님
        </span>
        {replyDraft.requires_human_review && (
          <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-800">
            담당자 검토 필요
          </span>
        )}
        <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-bold text-slate-600">
          검색 근거 {searchResults.length}건
        </span>
      </div>

      {fallbackNotice && (
        <div className="mt-3 rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-semibold text-orange-800">
          {fallbackNotice}
        </div>
      )}

      {safetyWarnings.length > 0 && (
        <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3">
          <div className="text-xs font-bold text-rose-800">발송 전 확인이 필요한 사항</div>
          <ul className="mt-1 space-y-1">
            {safetyWarnings.map((code) => (
              <li
                key={code}
                className={`text-xs font-semibold ${code.startsWith("PII") ? "text-rose-700" : "text-slate-600"}`}
              >
                · {safetyWarningLabel(code)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <div className="mb-1 text-xs font-bold text-slate-500">대표 답변 초안</div>
        <div className="whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
          {replyDraft.answer}
        </div>
      </div>

      {limitations.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-bold text-slate-500">적용 한계·검토 조건</div>
          <ul className="space-y-1">
            {limitations.map((item, index) => (
              <li key={index} className="text-xs text-slate-600">
                · {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {citations.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-bold text-slate-500">생성 근거</div>
          <ul className="space-y-1">
            {citations.map((citation, index) => (
              <li key={index} className="text-xs text-slate-600">
                · {citationLabel(citation)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {searchResults.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-bold text-slate-500">참고 검색 결과</div>
          <ul className="space-y-1">
            {searchResults.map((result, index) => (
              <li key={index} className="line-clamp-2 text-xs text-slate-600">
                · {searchResultSnippet(result)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function citationLabel(citation: Record<string, unknown>): string {
  const quote = typeof citation.quote === "string" ? citation.quote : "";
  const source =
    typeof citation.source === "string"
      ? citation.source
      : typeof citation.doc_id === "string"
        ? citation.doc_id
        : "";
  if (quote) return source ? `${quote} (${source})` : quote;
  return source || "근거 정보";
}

function searchResultSnippet(result: Record<string, unknown>): string {
  const snippet = typeof result.snippet === "string" ? result.snippet : "";
  return snippet || "검색 결과 본문 없음";
}

"use client";

import { useMemo, useState } from "react";
import type { DuplicateReplyDraft } from "@/lib/api";
import { replyDraftFallbackNotice, safetyWarningLabel } from "./duplicateMerge";

// /reply-draft 결과 패널. 자동 발송이 아니라 담당자 검토용 대표 답변 초안을 표시한다(핸드오프 §E/§11).
export function DuplicateReplyDraftPanel({
  replyDraft,
  processedCaseIds = [],
  onClose,
  onMarkProcessed,
}: {
  replyDraft: DuplicateReplyDraft;
  processedCaseIds?: string[];
  onClose: () => void;
  onMarkProcessed?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const fallbackNotice = replyDraftFallbackNotice(replyDraft.generation_metadata);
  const safetyWarnings = replyDraft.safety_warnings ?? [];
  const limitations = replyDraft.limitations ?? [];
  const citations = replyDraft.citations ?? [];
  const searchResults = replyDraft.search_results ?? [];
  const memberComplaintIds = useMemo(() => {
    return Array.from(new Set(replyDraft.member_complaint_ids.filter(Boolean)));
  }, [replyDraft.member_complaint_ids]);
  const processedSet = useMemo(() => new Set(processedCaseIds), [processedCaseIds]);
  const processedCount = memberComplaintIds.filter((caseId) => processedSet.has(caseId)).length;
  const allProcessed = memberComplaintIds.length > 0 && processedCount === memberComplaintIds.length;

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(replyDraft.answer);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section
      aria-label="담당자 검토용 대표 답변 초안"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
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
        <span className={`rounded-md border px-2 py-1 text-[11px] font-bold ${allProcessed ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
          처리완료 {processedCount}/{memberComplaintIds.length}건
        </span>
      </div>

      {fallbackNotice && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          {fallbackNotice}
        </div>
      )}

      {safetyWarnings.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
          <div className="text-xs font-bold text-amber-800">발송 전 확인이 필요한 사항</div>
          <ul className="mt-1 space-y-1">
            {safetyWarnings.map((code) => (
              <li
                key={code}
                className={`text-xs font-semibold ${code.startsWith("PII") ? "text-amber-700" : "text-slate-600"}`}
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

      <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-xs font-bold text-slate-500">처리 기록</div>
            <div className={`mt-1 text-sm font-extrabold ${allProcessed ? "text-blue-700" : "text-slate-800"}`}>
              처리완료 {processedCount}/{memberComplaintIds.length}건
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={copyAnswer}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50"
            >
              {copied ? "복사됨" : "초안 복사"}
            </button>
            <button
              type="button"
              disabled={!onMarkProcessed || allProcessed || memberComplaintIds.length === 0}
              onClick={onMarkProcessed}
              className={
                !onMarkProcessed || allProcessed || memberComplaintIds.length === 0
                  ? "cursor-not-allowed rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-400"
                  : "rounded-md border border-blue-600 bg-blue-600 px-3 py-1.5 text-xs font-extrabold text-white hover:bg-blue-700"
              }
            >
              {allProcessed ? "처리완료 기록됨" : "전체 처리완료 기록"}
            </button>
          </div>
        </div>
      </div>

      {limitations.length > 0 && (
        <details className="mt-3 rounded-md border border-slate-200 bg-white">
          <summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-600">
            적용 한계·검토 조건 {limitations.length}건
          </summary>
          <ul className="space-y-1 border-t border-slate-200 p-3">
            {limitations.map((item, index) => (
              <li key={index} className="text-xs text-slate-600">
                · {item}
              </li>
            ))}
          </ul>
        </details>
      )}

      {citations.length > 0 && (
        <details className="mt-2 rounded-md border border-slate-200 bg-white">
          <summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-600">
            생성 근거 {citations.length}건
          </summary>
          <ul className="space-y-1 border-t border-slate-200 p-3">
            {citations.map((citation, index) => (
              <li key={index} className="text-xs text-slate-600">
                · {citationLabel(citation)}
              </li>
            ))}
          </ul>
        </details>
      )}

      {searchResults.length > 0 && (
        <details className="mt-2 rounded-md border border-slate-200 bg-white">
          <summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-600">
            참고 검색 결과 {searchResults.length}건
          </summary>
          <ul className="space-y-1 border-t border-slate-200 p-3">
            {searchResults.map((result, index) => (
              <li key={index} className="line-clamp-2 text-xs text-slate-600">
                · {searchResultSnippet(result)}
              </li>
            ))}
          </ul>
        </details>
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

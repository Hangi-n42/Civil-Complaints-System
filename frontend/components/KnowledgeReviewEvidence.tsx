"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import { display, evidenceSpan, strings, type EvidenceRef, type KnowledgeRequest, type RecordValue } from "@/lib/knowledgeReview";

type Block = { id: string; text: string; source_version_id: string; run_id: string; parse_run_id?: string; locator: RecordValue };
type Evidence = { block: Block; version: { id: string; sha256: string }; source: { id: string; title: string }; source_role?: string;
  context: { blocks: Block[]; status: string; title?: unknown; headers?: unknown; notes: string[]; omitted_restricted_count: number } };

export default function KnowledgeReviewEvidence({ request, runId, reference }: { request: KnowledgeRequest; runId: string; reference: EvidenceRef }) {
  const [value, setValue] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    request<Evidence>(`/evidence/${encodeURIComponent(reference.evidence_id)}?run_id=${encodeURIComponent(runId)}`).then(data => {
      if (data.block.id !== reference.block_id || data.version.id !== reference.source_version_id ||
          (data.block.parse_run_id || data.block.run_id) !== reference.parse_run_id) throw new Error("고정된 근거 버전·파싱 참조가 일치하지 않습니다.");
      if (!disposed) { setValue(data); setError(""); }
    }).catch(e => { if (!disposed) { setError(e.message); setValue(null); } });
    return () => { disposed = true; };
  }, [request, runId, reference]);
  if (error) return <p role="alert" className="rounded bg-amber-50 p-3 text-sm text-amber-900">원문 확인 필요: {error} 보류 사유에 기록할 수 있습니다.</p>;
  if (!value) return <p role="status" className="text-sm">고정된 원문 문맥을 불러오는 중입니다.</p>;
  const [start, end] = reference.span || [];
  const parts = evidenceSpan(value.block.text, reference.span || []);
  const matched = Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && parts.quote === reference.quote;
  return <section aria-label="선택 근거 원문" className="space-y-3 text-sm">
    <div><h4 className="font-semibold">{value.source.title}</h4><p className="text-slate-600">자료 역할: {value.source_role || "미기록"}</p>
      <a className="underline" target="_blank" rel="noreferrer" href={`${API_BASE_URL}/api/v1/knowledge/sources/${encodeURIComponent(value.source.id)}/versions/${encodeURIComponent(value.version.id)}/raw`}>이 버전의 원본 열기</a></div>
    {!matched && <p className="text-amber-900">저장된 인용 구간이 원문과 일치하지 않습니다. 근거를 수정하거나 보류하세요.</p>}
    <p>제목·절: {display(value.context.title)}<br />표 열: {display(value.context.headers)}</p>
    {value.context.blocks.map(b => <div key={b.id} className={`rounded border p-3 ${b.id === value.block.id ? "border-blue-500 bg-blue-50" : "bg-slate-50"}`}>
      <p className="mb-2 text-xs font-medium">{b.id === value.block.id ? "인용 원문" : "인접 구간 · 다른 행/대상일 수 있음"}</p>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-sans">{b.id === value.block.id && matched ? <>{parts.before}<mark className="bg-yellow-200">{parts.quote}</mark>{parts.after}</> : b.text}</pre>
      <details className="mt-2 text-xs"><summary>페이지·행·표 위치</summary><pre className="whitespace-pre-wrap break-all">{JSON.stringify(b.locator,null,2)}</pre></details>
    </div>)}
    {strings(value.context.notes).map((note,i) => <p key={i} className="text-xs text-amber-900">{note}</p>)}
    {value.context.omitted_restricted_count > 0 && <p className="text-amber-900">사용 제한으로 제외된 주변 구간 {value.context.omitted_restricted_count}개 · 문맥 확인 필요</p>}
    <details className="text-xs"><summary>고정 근거 식별 정보</summary><dl className="break-all"><dt>자료 버전</dt><dd>{reference.source_version_id}</dd><dt>파싱 실행</dt><dd>{reference.parse_run_id}</dd><dt>근거</dt><dd>{reference.evidence_id}</dd><dt>문자 구간</dt><dd>{reference.span?.join(" ~ ")}</dd><dt>원문 해시</dt><dd>{value.version.sha256}</dd></dl></details>
  </section>;
}

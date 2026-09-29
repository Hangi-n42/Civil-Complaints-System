"use client";

import { useEffect, useRef, useState } from "react";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type View = { snapshot_id: string | null; entities: { id: string; name: string }[]; sources: { id: string; title: string }[] };
type Citation = { evidence_id: string; title: string; quote: string; locator: Record<string, unknown> };
type Result = {
  status: string; answer_style?: string; answer: string | null; snapshot_id: string | null; status_revision: number; status_checked_at: string;
  sentences?: { section?: string; text: string; evidence_ids: string[] }[]; citations: Citation[];
  fact_details?: { text: string; evidence_ids: string[] }[];
  entity_candidates: { entity_id: string; label: string; source_ids: string[] }[]; entities?: { id: string; name: string }[];
  paths: { entity_ids: string[]; assertion_ids: string[]; edges: { assertion_id: string; subject_id: string; object_entity_id: string }[] }[];
  coverage: { selected_source_ids: string[]; included_version_ids: string[]; excluded: { source_id: string; reason: string }[]; selected_assertion_count: number; used_assertion_ids: string[]; omitted_assertion_ids: string[]; not_selected_assertion_ids?: string[]; recommended_assertion_ids?: string[]; context_assertion_ids?: string[]; partial: boolean };
  validity_status: string; limitations: string[]; metrics: { llm_calls: number; model_total_s: number; elapsed_s: number };
};
type Evidence = { block: { text: string; locator: Record<string, unknown> }; source: { title: string }; usage_restrictions?: { state: string }[] };
const field = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const button = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const status: Record<string, string> = { answered: "근거 표시", partial: "부분 답변", insufficient: "근거 부족", ambiguous: "대상 선택 필요", stale: "상태 변경 · 재검색 필요" };

export default function KnowledgeSearch({ request, visible }: { request: Request; visible: boolean }) {
  const epoch = useRef(0);
  const [snapshots, setSnapshots] = useState<{ id: string; reason: string }[]>([]);
  const [snapshotId, setSnapshotId] = useState("active");
  const [view, setView] = useState<View | null>(null);
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [entityId, setEntityId] = useState("");
  const [query, setQuery] = useState("");
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [submitted, setSubmitted] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    epoch.current += 1;
    if (!visible) return;
    let cancelled = false;
    setLoading(true); setView(null); setResult(null); setEvidence(null); setError(""); setEntityId("");
    Promise.all([request<{ items: { id: string; reason: string }[] }>("/snapshots"), request<View>(`/snapshots/${snapshotId}`)])
      .then(([list, detail]) => { if (!cancelled) { setSnapshots(list.items); setView(detail); setSourceIds(detail.sources.map(s => s.id)); } })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; epoch.current += 1; };
  }, [request, visible, snapshotId]);

  async function search(target = entityId) {
    const current = epoch.current;
    setBusy(true); setError(""); setResult(null); setEvidence(null); setSubmitted(query);
    try {
      const value = await request<Result>("/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        mode: "local", query, snapshot_id: view?.snapshot_id, source_ids: sourceIds, as_of: asOf || null,
        scope: { entity_ids: target ? [target] : [], text: null },
      }) });
      if (current === epoch.current) setResult(value);
    } catch (e) { if (current === epoch.current) setError((e as Error).message); } finally { setBusy(false); }
  }
  async function openEvidence(id: string) {
    const current = epoch.current;
    setEvidence(null); setError(""); setBusy(true);
    try { const value = await request<Evidence>(`/evidence/${id}`); if (current === epoch.current) setEvidence(value); }
    catch (e) { if (current === epoch.current) setError((e as Error).message); } finally { setBusy(false); }
  }
  const changed = () => { setResult(null); setEvidence(null); };
  const name = (id: string) => result?.entities?.find(e => e.id === id)?.name || view?.entities.find(e => e.id === id)?.name || id;
  return <section className="space-y-4">
    <h2 className="text-xl font-semibold">지식 검색</h2>
    <p className="text-sm text-slate-600">질문에 관련된 근거를 우선 추천하고, 함께 조회된 맥락과 구분해 검토 사실·원문 조건을 표시합니다. 현재 법률·실시간 공실을 판정하는 서비스가 아닙니다.</p>
    <div className="flex gap-3"><span className="rounded bg-slate-800 px-3 py-2 text-sm text-white">Local · 대상 검색</span><span className="p-2 text-sm text-slate-500">Global · K7 준비 중</span></div>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
    <fieldset disabled={busy || loading} className="space-y-3">
      <label className="block">지식 버전<select className={field} value={snapshotId} onChange={e => setSnapshotId(e.target.value)}><option value="active">현재 활성 버전</option>{snapshots.map(s => <option key={s.id} value={s.id}>{s.reason} · {s.id.slice(0, 8)}</option>)}</select></label>
      <div className="grid gap-3 md:grid-cols-2"><label>대상<select className={field} value={entityId} onChange={e => { setEntityId(e.target.value); changed(); }}><option value="">질문의 ID·명칭으로 찾기</option>{view?.entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label><label>업무 기준일<input className={field} type="date" value={asOf} onChange={e => { setAsOf(e.target.value); changed(); }} /></label></div>
      <fieldset className="rounded border p-3"><legend>사용할 자료</legend>{view?.sources.map(s => <label key={s.id} className="block text-sm"><input type="checkbox" checked={sourceIds.includes(s.id)} onChange={e => { setSourceIds(ids => e.target.checked ? [...ids, s.id] : ids.filter(id => id !== s.id)); changed(); }} /> {s.title}</label>)}</fieldset>
      <label className="block">질문<textarea className={field} rows={3} maxLength={4000} value={query} onChange={e => { setQuery(e.target.value); changed(); }} placeholder="단지 이름이나 공식 ID와 궁금한 내용을 입력하세요." /></label>
      <button className={button} disabled={!query.trim() || !sourceIds.length || !view?.snapshot_id} onClick={() => search()}>검색</button>
    </fieldset>
    {(busy || loading) && <p role="status">{loading ? "버전 읽는 중…" : "처리 중…"}</p>}
    {!loading && !view?.snapshot_id && <p>활성 지식 버전이 없습니다. 지식 버전 탭에서 준비하거나 저장된 버전을 선택하세요.</p>}
    {result && <article className="space-y-3 rounded border bg-white p-4">
      <h3 className="font-semibold">{status[result.status]}</h3>{result.answer_style === "reviewed_facts" && <p className="text-sm text-slate-600">검토된 사실·원문 조건 — 수치와 조건을 재요약하지 않았습니다. 모델 추천 여부는 신뢰도나 질문 충족 여부의 판정이 아닙니다.</p>}<p className="text-sm">질문: {submitted}</p>
      <p className="break-all text-xs text-slate-500">지식 버전 {result.snapshot_id} · 사용 상태 {result.status_revision} · 확인 {result.status_checked_at}</p>
      {(result.sentences || []).map((s, i) => <div key={i}>{(i === 0 || s.section !== result.sentences?.[i-1].section) && <h4 className="my-2 font-semibold">{s.section === "assessment" ? "질문에 대한 판단" : s.section === "answer" ? "선택한 근거" : s.section === "context" ? "함께 조회된 맥락" : "우선 추천 근거"}</h4>}<p className="whitespace-pre-wrap">{s.text} {s.evidence_ids.map(id => <button key={id} disabled={busy} className="mx-1 text-sm text-blue-700 underline" onClick={() => openEvidence(id)}>[근거 {result.citations.findIndex(c => c.evidence_id === id) + 1}]</button>)}</p></div>)}
      {!!result.limitations.length && <ul className="list-inside list-disc text-sm text-amber-900">{result.limitations.map((v, i) => <li key={i}>{v}</li>)}</ul>}
      {result.validity_status === "unverified" && <p className="text-xs">기준일 유효성 미확인: 자료의 사건 날짜를 유효기간으로 추정하지 않았습니다.</p>}
      {result.status === "stale" && <button className={button} disabled={busy} onClick={() => search()}>최신 상태로 재검색</button>}
      {!!result.entity_candidates.length && <div className="flex flex-wrap gap-2">{result.entity_candidates.map(e => <button key={e.entity_id} className={button} disabled={busy} onClick={() => { setEntityId(e.entity_id); search(e.entity_id); }}>{e.label} · {e.source_ids.map(id => view?.sources.find(s => s.id === id)?.title || id.slice(0,8)).join(" / ")} · {e.entity_id.slice(0,8)} 선택 후 검색</button>)}</div>}
      <p className="text-sm">모델 호출 {result.metrics.llm_calls}회 · 모델 {result.metrics.model_total_s}초 · 전체 {result.metrics.elapsed_s}초</p>
      {!!result.citations.length && <details open={result.answer_style === "reviewed_facts"}><summary>원문 인용 {result.citations.length}개</summary>{result.citations.map((c, i) => <div key={c.evidence_id} className="my-2 rounded bg-slate-50 p-3 text-sm"><strong>[{i+1}] {c.title}</strong><p className="whitespace-pre-wrap">{c.quote}</p><p className="break-all text-xs">{JSON.stringify(c.locator)}</p><button disabled={busy} className="underline" onClick={() => openEvidence(c.evidence_id)}>원문 블록 확인</button></div>)}</details>}
      {!!result.fact_details?.length && <details><summary>조회된 사실 상세 {result.fact_details.length}개</summary><p className="text-sm text-slate-600">본문에 선택하지 않은 조회 사실도 포함합니다.</p>{result.fact_details.map((f,i) => <div key={i} className="my-2 rounded bg-slate-50 p-3 text-sm"><p className="whitespace-pre-wrap">{f.text}</p>{f.evidence_ids.map(id => <button key={id} disabled={busy} className="mr-2 underline" onClick={() => openEvidence(id)}>원문 확인</button>)}</div>)}</details>}
      {!!result.paths.length && <details><summary>조회한 관계 경로</summary>{result.paths.map((p,i) => <div key={i} className="my-2 text-sm"><p>탐색: {p.entity_ids.map(name).join(" ↔ ")}</p>{p.edges.map(e => <p key={e.assertion_id}>저장 관계: {name(e.subject_id)} → {name(e.object_entity_id)}</p>)}<p className="break-all text-xs">주장: {p.assertion_ids.join(", ")}</p></div>)}</details>}
      <details><summary>사용·제외 범위</summary><p className="text-sm">관련 주장 {result.coverage.selected_assertion_count}개 · 답변 인용 {result.coverage.used_assertion_ids.length}개 · 예산 제외 {result.coverage.omitted_assertion_ids.length}개 · 우선 추천 {result.coverage.recommended_assertion_ids?.length || 0}개 · 함께 조회 {result.coverage.context_assertion_ids?.length || 0}개 · 미표시 {result.coverage.not_selected_assertion_ids?.length || 0}개</p><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(result.coverage,null,2)}</pre></details>
    </article>}
    {evidence && <aside className="rounded border bg-white p-4"><h3 className="font-semibold">{evidence.source.title}</h3>{!!evidence.usage_restrictions?.length && <p className="text-red-700">이 근거의 사용이 현재 제한돼 있습니다. 답변을 다시 검색하세요.</p>}<pre className="max-h-96 overflow-auto whitespace-pre-wrap text-sm">{evidence.block.text}</pre><p className="break-all text-xs">{JSON.stringify(evidence.block.locator)}</p></aside>}
  </section>;
}

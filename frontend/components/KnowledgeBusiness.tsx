"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type Source = { source: { id: string; title: string }; versions: { id: string; processing_status?: string }[] };
type Requirement = { id: string; question_ids: string[]; question: string; target: string; situation: string; period: string; criterion: string; source_ids: string[]; required: boolean; revision: number; status: string };
type Claim = { role?: string; raw?: { Event: string; Entity: string[] }; conditions?: string[]; exceptions?: string[]; period?: string; references?: string[]; extraction_error?: string; id: string; statement: string; evidence: { block_id: string; quote?: string; precision?: string }[]; superseded_by?: string[] };
type Assessment = { id: string; requirement_id: string; phase: string; status: string; errors: string[]; source_scope?: { provided_block_ids: string[]; model_examined_block_ids: string[]; provided_not_declared_ids: string[] }; source?: { gaps: string[]; meanings: { key: string; statement: string; conditions?: string[]; exceptions?: string[]; period?: string; references?: string[]; source_status: string; availability: string; evidence: { quote: string }[] }[] }; representation?: { reason: string; source_challenges?: string[]; source_checks?: { meaning_key: string; required_for_requirement: boolean; field_checks: Record<string, string>; reason: string }[] }; preservation_complete?: boolean };
type Run = { recipe: { options: Record<string, unknown> }; id: string; status: string; changeset_id?: string; metrics?: { llm_calls: number; reused_responses?: number }; units: { id: string; stage: string; status: string; error?: string }[]; assessments: Assessment[]; repairs: { id: string; status: string; origin?: string; actor?: string; reason?: string; changes: { before?: Claim; after: Claim }[]; after?: Claim[] }[] };
type Change = { id: string; revision: number; candidate_versions?: Record<string, string>; candidates: Claim[]; eligible_ids: string[] };
type Snapshot = { id: string; reason: string; counts: { claims: number } };
const field = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const button = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const meaningFields: Record<string, string> = { statement: "문장", conditions: "조건", exceptions: "예외", period: "기간", references: "참조" };
const status: Record<string, string> = { retrieval_failed: "근거 검색 실패", no_source_passages: "검색할 원문 구간 없음", no_reviewed_claims: "승인된 지식 없음", answered: "답변 생성", unverified: "답변 확인 미완료", unassessed: "미검수", satisfied: "충족", partial: "일부 미완료", unknown: "판정 미확정", needs_review: "변경 후 재검토 필요", review_ready: "검토 대기", running: "실행 중", queued: "대기", failed: "실패", cancelled: "취소됨", cancel_requested: "취소 요청됨", succeeded: "완료", rechecked: "수정 후 요구 재확인", recheck_incomplete: "수정 후 재확인 미완료", supported: "원문 지지", refuted: "원문 반박", provided: "제공됨", missing: "자료 부족", unread: "미읽기", unselected: "미선택", ambiguous: "해석 미확정" };
const json = (value: unknown, method = "POST") => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });

export function RepairChange({ before, after, claims }: { before?: Claim; after: Claim; claims: Claim[] }) {
  const replacements = after.superseded_by || [];
  return <div className="mt-2"><p>전: {before?.statement || "표현 없음"}</p>
    {replacements.length ? <><p>후: 기존 후보로 대체</p><p className="text-sm">교정 시점에 저장된 대체 내용입니다. 승인 여부는 별도 검토 결과를 확인하세요.</p>{replacements.map(id => {
      const replacement = claims.find(c => c.id === id);
      return replacement ? <div key={id}><p>{replacement.statement}</p>{replacement.evidence.map((e, i) => <blockquote key={i} className="whitespace-pre-wrap">{e.quote || `원문 구간 ${e.block_id}`}</blockquote>)}</div>
        : <p key={id} className="text-amber-800">대체 후보를 확인할 수 없습니다: {id}</p>;
    })}</> : <><p>후: {after.statement}</p>{after.evidence.map((e, i) => <blockquote key={i}>{e.quote}</blockquote>)}</>}
  </div>;
}


export function eventEditRequest(change: Change, claim: Claim, form: FormData) {
  return { expected_revision: change.revision, expected_claim_version: change.candidate_versions?.[claim.id],
    claim_id: claim.id, actor: form.get("actor"), reason: form.get("reason"), event: form.get("event"),
    evidence: form.getAll("evidence").map(index => ({ block_id: claim.evidence[Number(index)].block_id, quote: claim.evidence[Number(index)].quote })) };
}

export function EventEditor({ change, busy, onSubmit }: {
  change: Change; busy: boolean; onSubmit: (value: ReturnType<typeof eventEditRequest>) => Promise<void>;
}) {
  const candidates = change.candidates.filter(c => c.role === "event_entity" && c.raw && !c.superseded_by?.length && !c.extraction_error);
  const [id, setId] = useState(candidates[0]?.id || "");
  const [validation, setValidation] = useState("");
  const claim = candidates.find(c => c.id === id);
  return <details className="rounded border bg-white p-4"><summary>원문 근거로 문장 직접 수정</summary>
    <p className="text-sm">업무 내용 문장과 그 안의 조건만 수정합니다. 연결된 대상 목록·관계형 주장·대체된 후보는 편집하지 않습니다. 수정은 승인이 아니며 정상 의미 보존과 업무 요구를 다시 확인합니다.</p>
    {!claim ? <p>이 실행에는 편집 가능한 업무 내용 문장이 없습니다.</p> : <>
      <label className="block">수정할 문장<select className={field} value={id} onChange={e => setId(e.target.value)} disabled={busy}>{candidates.map(c => <option key={c.id} value={c.id}>{c.statement}</option>)}</select></label>
      <form key={claim.id} className="mt-3 space-y-3" onChange={() => setValidation("")} onSubmit={e => {
        e.preventDefault(); const form = new FormData(e.currentTarget);
        if (!form.getAll("evidence").length) { setValidation("수정 근거를 하나 이상 선택하세요."); return; }
        onSubmit(eventEditRequest(change, claim, form));
      }}>
        {validation && <p role="alert" className="text-red-800">{validation}</p>}
        <p className="text-sm">유지되는 연결 대상: {claim.raw?.Entity.join(" / ")}</p>
        <p className="text-sm">기존 조건·예외·기간·참조 중 정상 내용도 아래 문장에 보존하세요. 이전 해석은 이력으로 남고 수정문에 대한 검증으로 재사용되지 않습니다.</p>
        {([['conditions', claim.conditions?.join(' / ')], ['exceptions', claim.exceptions?.join(' / ')], ['period', claim.period], ['references', claim.references?.join(' / ')]] as const).map(([key, value]) => value ? <p key={key}>{meaningFields[key]}: {value}</p> : null)}
        <label className="block">수정 문장 (조건 포함)<textarea name="event" required className={field} defaultValue={claim.raw?.Event} /></label>
        <fieldset className="max-h-72 overflow-auto rounded border p-2"><legend>수정 근거 선택</legend>{claim.evidence.filter(e => e.quote).map(e => <label key={claim.evidence.indexOf(e)} className="block whitespace-pre-wrap"><input type="checkbox" name="evidence" value={claim.evidence.indexOf(e)} /> {e.quote}</label>)}</fieldset>
        <label className="block">수정자<input name="actor" required className={field} /></label>
        <label className="block">수정 이유<textarea name="reason" required className={field} /></label>
        <button className={button} disabled={busy || !change.candidate_versions?.[claim.id]}>수정 저장·재검수</button>
      </form>
    </>}
  </details>;
}


type RetryLimit = { key: string; label: string; value: number; min: number };
function retryCapacityFields(run: Run): RetryLimit[] {
  if (["queued", "running", "cancel_requested"].includes(run.status)) return [];
  const failed = new Set(run.units.filter(u => u.status === "failed" && ["input_capacity", "truncated"].includes(u.error || "")).map(u => u.stage));
  const options = run.recipe.options;
  const fields: RetryLimit[] = [];
  const truncated = new Set(run.units.filter(u => u.status === "failed" && u.error === "truncated").map(u => u.stage));
  for (const [stage, key, label] of [
    ["requirement_source", "source_tokens", "원문 판단 응답 길이"],
    ["source_reassessment", "source_reassessment_tokens", "원문 재판단 응답 길이"],
    ["requirement_representation", "representation_tokens", "후보 대조 응답 길이"],
  ]) if (truncated.has(stage)) fields.push({ key, label, min: 256, value: Number(options[key] ?? options.review_tokens ?? 4096) });
  if (failed.has("requirement_representation")) fields.push({ key: "representation_context_tokens", label: "후보 대조 처리 용량", min: 4096, value: Number(options.representation_context_tokens ?? options.context_tokens ?? 49152) });
  return fields;
}

export function resumeBusinessRequest(run: Run, limits: Record<string, number>) {
  const changed = Object.fromEntries(retryCapacityFields(run).filter(f => f.key in limits).map(f => [f.key, limits[f.key]]));
  const edited = run.repairs.some(r => r.origin === "user") || !!run.recipe.options.reassess_run_id;
  return { ...run.recipe.options, ...changed, resume_run_id: edited ? null : run.id, reuse_run_id: null,
    reassess_run_id: edited ? run.id : null, ...(edited ? { repair: false } : {}) };
}

export function CapacityRetrySettings({ run, values, onChange }: {
  run: Run; values: Record<string, number>; onChange: (key: string, value: number) => void;
}) {
  const fields = retryCapacityFields(run);
  const sourceInputBlocked = !["queued", "running", "cancel_requested"].includes(run.status) && run.units.some(u => u.status === "failed" && u.error === "input_capacity" && ["requirement_source", "source_reassessment"].includes(u.stage));
  if (!fields.length && !sourceInputBlocked) return null;
  return <fieldset className="space-y-2 rounded border border-amber-300 p-3">
    <legend>용량 부족 후 이어가기</legend>
    <p className="text-sm">이전 입력 또는 응답이 용량 한도에 걸렸습니다. 같은 값으로 이어가면 동일한 원인이 남습니다. 아래 값은 토큰 단위이며, 늘리면 처리 시간과 메모리 사용이 늘 수 있습니다.</p>
    {sourceInputBlocked && <p className="text-sm">원문 판단의 입력 용량 부족은 별도 실행 설정 조정이 필요합니다. 응답 길이만 늘리면 해결되지 않습니다.</p>}
    {fields.map(f => <label key={f.key} className="block">{f.label}<input type="number" required name={f.key} min={f.min} step={1} className={field} value={values[f.key] ?? f.value} onChange={e => onChange(f.key, Number(e.target.value))} /></label>)}
    <p className="text-sm">변경한 값으로 새 실행을 저장합니다. 이전 실행을 보존하며, 성공한 동일 응답의 재사용 여부와 실제 한도는 실행 기록에서 확인할 수 있습니다. 용량 변경이 의미 정확성을 보장하지는 않습니다.</p>
  </fieldset>;
}


export default function KnowledgeBusiness({ request, sources, visible }: { request: Request; sources: Source[]; visible: boolean }) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [editing, setEditing] = useState<Requirement | null>(null);
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>([]);
  const [versions, setVersions] = useState<string[]>([]);
  const [neighborMode, setNeighborMode] = useState<"plain" | "structured">("plain");
  const [run, setRun] = useState<Run | null>(null);
  const [runId, setRunId] = useState("");
  const [retryLimits, setRetryLimits] = useState<Record<string, number>>({});
  const [savedRuns, setSavedRuns] = useState<{ id: string; status: string; started_at?: string; questions: string[] }[]>([]);
  const [change, setChange] = useState<Change | null>(null);
  const [accepted, setAccepted] = useState<string[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [querySource, setQuerySource] = useState("reviewed");
  const [answer, setAnswer] = useState<{ status: string; answer?: { answer: string; citations: string[]; limitations: string[] } } | null>(null);
  const [impacts, setImpacts] = useState<{ requirement_id: string; status: string; reason: string; new_relevance: boolean }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = useCallback(async () => {
    const [r, s, runs] = await Promise.all([request<{ items: Requirement[] }>("/requirements"), request<{ items: Snapshot[] }>("/business/snapshots"), request<{ items: typeof savedRuns }>("/business/runs")]);
    setRequirements(r.items); setSnapshots(s.items); setSavedRuns(runs.items);
  }, [request]);
  useEffect(() => { if (visible) refresh().catch(e => setError(e.message)); }, [visible, refresh]);
  const loadRun = useCallback(async (id: string) => {
    const value = await request<Run>(`/runs/${encodeURIComponent(id)}`);
    setRun(value); setRunId(value.id); setRetryLimits({});
    if (value.changeset_id) setChange(await request<Change>(`/business/changes/${value.changeset_id}`));
    else setChange(null);
    await refresh();
  }, [request, refresh]);
  const running = !!run && ["queued", "running", "cancel_requested"].includes(run.status);
  useEffect(() => {
    if (!visible || !running || !run) return;
    const timer = setInterval(() => { loadRun(run.id).catch(e => setError(e.message)); }, 4000);
    return () => clearInterval(timer);
  }, [visible, running, run, loadRun]);
  async function action(fn: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function saveRequirement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const id = editing?.id || crypto.randomUUID();
    await action(async () => {
      await request(`/requirements/${encodeURIComponent(id)}`, json({
        id, question_ids: editing?.question_ids || [id], question: form.get("question"), target: form.get("target"),
        situation: form.get("situation"), period: form.get("period"), criterion: form.get("criterion"),
        source_ids: editing?.source_ids || [], required: editing?.required ?? true, expected_revision: editing?.revision || 0,
      }, "PUT"));
      setEditing(null); await refresh(); setNotice("업무 요구를 저장했습니다.");
    });
  }
  const toggle = (values: string[], id: string, checked: boolean) => checked ? [...new Set([...values, id])] : values.filter(v => v !== id);
  const versionOptions = sources.flatMap(s => s.versions.filter(v => v.processing_status === "parsed").map(v => ({ id: v.id, label: `${s.source.title} · ${v.id.slice(0, 8)}` })));

  return <section className="space-y-4">
    <h2 className="text-xl font-semibold">업무 지식</h2>
    <p className="text-sm text-slate-600">업무 질문과 충족 기준을 저장하고 원문 근거·표현·수정 결과를 검토합니다. 승인한 출처 지식 버전을 선택해 질문할 수 있습니다.</p>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <details className="rounded border bg-white p-4" open={!!editing}><summary>{editing ? "업무 요구 수정" : "업무 요구 등록"}</summary>
      <form key={editing?.id || "new"} onSubmit={saveRequirement} className="mt-3 grid gap-3 md:grid-cols-2">
        {([['question', '업무 질문'], ['target', '대상'], ['situation', '상황'], ['period', '기준 기간'], ['criterion', '충족 기준']] as const).map(([key, label]) => <label key={key}>{label}<textarea name={key} required className={field} defaultValue={editing?.[key] || ""} /></label>)}
        <div><button className={button} disabled={busy}>저장</button>{editing && <button type="button" className="ml-3 underline" onClick={() => setEditing(null)}>새 요구 등록으로 전환</button>}</div>
      </form>
    </details>
    <div className="grid gap-4 md:grid-cols-2">
      <fieldset className="rounded border p-3"><legend>확인할 업무 요구</legend>{requirements.map(r => <div key={r.id} className="mb-2"><label><input type="checkbox" checked={selectedRequirements.includes(r.id)} onChange={e => setSelectedRequirements(toggle(selectedRequirements, r.id, e.target.checked))} /> {r.question} · {status[r.status] || r.status}</label><button className="ml-2 underline" onClick={() => setEditing(r)}>수정</button><p className="text-sm text-slate-600">{r.target} / {r.situation} / {r.period}<br />{r.criterion}</p></div>)}</fieldset>
      <fieldset className="rounded border p-3"><legend>이번에 읽을 자료 버전</legend>{versionOptions.map(v => <label key={v.id} className="block"><input type="checkbox" checked={versions.includes(v.id)} onChange={e => setVersions(toggle(versions, v.id, e.target.checked))} /> {v.label}</label>)}<p className="mt-2 text-sm">자료 탭에서 원문 추출을 마친 버전만 표시합니다.</p></fieldset>
    </div>
    <label className="block">새 실행의 이웃 문맥 표현<select className={field} value={neighborMode} onChange={e => setNeighborMode(e.target.value as "plain" | "structured")}><option value="plain">일반 문맥 (기본)</option><option value="structured">연결 구조 (선택 시험)</option></select><span className="text-sm">두 방식 모두 실제 연결 이웃과 필수 원문을 사용합니다.</span></label>
    <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || running || !versions.length || !selectedRequirements.length} onClick={() => action(async () => { setAccepted([]); const value = await request<{ run_id: string }>("/business/runs", json({ source_version_ids: versions, requirement_ids: selectedRequirements, neighbor_mode: neighborMode })); await loadRun(value.run_id); })}>추출·개념화·요구 확인 시작</button>
      <label>저장된 실행<select className={field} value={runId} onChange={e => setRunId(e.target.value)}><option value="">선택</option>{savedRuns.map(r => <option key={r.id} value={r.id}>{r.started_at ? new Date(r.started_at).toLocaleString("ko-KR") : "대기"} · {r.questions.join(" / ")} · {status[r.status] || r.status}</option>)}</select></label><button className={button} disabled={busy || !runId} onClick={() => action(() => loadRun(runId))}>불러오기</button>
      {running && <button className={button} disabled={busy} onClick={() => action(async () => { await request(`/runs/${run!.id}/cancel`, { method: "POST" }); await loadRun(run!.id); })}>실행 취소</button>}
    </div>
    {run && !running && <form className="space-y-3" onSubmit={e => { e.preventDefault(); action(async () => { const next = await request<{ run_id: string }>("/business/runs", json(resumeBusinessRequest(run, retryLimits))); setAccepted([]); await loadRun(next.run_id); }); }}><CapacityRetrySettings run={run} values={retryLimits} onChange={(key, value) => setRetryLimits(previous => ({ ...previous, [key]: value }))} /><button className={button} disabled={busy}>저장된 응답을 재사용해 새 실행으로 이어가기</button></form>}
    {run && <div className="space-y-3"><p role="status">실행 상태: {status[run.status] || run.status} · 완료 단계 {run.units.filter(u => u.status === "succeeded").length}{run.metrics && <> · 모델 새 호출 {run.metrics.llm_calls} · 응답 재사용 {run.metrics.reused_responses ?? 0}</>}</p>
      {run.units.filter(u => u.error).map(u => <p key={u.id} className="text-red-800">{u.stage}: {u.error}</p>)}
      {(run.assessments || []).map(a => <details key={a.id} className="rounded border bg-white p-3"><summary>{requirements.find(r => r.id === a.requirement_id)?.question || a.requirement_id} · {status[a.status] || a.status}</summary>
        <p>{a.representation?.reason}</p>{a.source?.gaps.map((g, i) => <p key={i}>공백: {g}</p>)}{a.errors.map((e, i) => <p key={i} className="text-red-800">{e}</p>)}
        {a.source_scope && <p className="text-sm">제공 구간 {a.source_scope.provided_block_ids.length}개 · 모델 조사 선언 {a.source_scope.model_examined_block_ids.length}개 · 미선언 {a.source_scope.provided_not_declared_ids.length}개. 이 목록은 실제 완독이나 의미 보존을 증명하지 않습니다.</p>}
        {a.representation?.source_challenges?.map((v, i) => <p key={i} className="text-amber-900">원문 판단 정정 요청: {v}</p>)}
        {a.source?.meanings.map(m => <div key={m.key} className="mt-2 border-t pt-2"><p>{m.statement}</p><p>{status[m.source_status] || m.source_status} · {status[m.availability] || m.availability}</p>
          {([['conditions', m.conditions?.join(' / ')], ['exceptions', m.exceptions?.join(' / ')], ['period', m.period], ['references', m.references?.join(' / ')]] as const).map(([key, value]) => value ? <p key={key}>{meaningFields[key]}: {value}</p> : null)}
          {a.representation?.source_checks?.filter(c => c.meaning_key === m.key).map(c => <div key={c.meaning_key} className="text-sm"><p>요구 필수 범위: {c.required_for_requirement ? '해당' : '해당하지 않음'}</p><p>{Object.entries(c.field_checks).map(([k, v]) => `${meaningFields[k] || k}: ${v === 'not_applicable' ? '주장 내용 없음' : status[v] || v}`).join(' · ')}</p><p>{c.reason}</p></div>)}
          {m.evidence.map((e, i) => <blockquote key={i} className="whitespace-pre-wrap bg-slate-50 p-2">{e.quote}</blockquote>)}</div>)}
      </details>)}
      {(run.repairs || []).map(r => <details key={r.id} className="rounded border p-3"><summary>교정·누락 복구 · {status[r.status] || r.status}</summary>{r.origin === "user" && <p>직접 입력 · 수정자: {r.actor} · 이유: {r.reason}</p>}{r.origin === "model" && <p>모델 제안으로 교정</p>}{r.changes.map(c => <RepairChange key={c.after.id} before={c.before} after={c.after} claims={r.after || []} />)}</details>)}
    </div>}
    {change && <EventEditor key={change.id} change={change} busy={busy || running} onSubmit={value => action(async () => {
      const next = await request<{ run_id: string }>(`/business/changes/${change.id}/edits`, json(value));
      setAccepted([]); await loadRun(next.run_id); setNotice("수정 기록을 저장했습니다. 재검수 후 승인할 항목을 다시 선택하세요.");
    })} />}
    {change && <form className="space-y-3 rounded border bg-white p-4" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action(async () => { const value = await request<{ snapshot_id: string }>(`/business/changes/${change.id}/decisions`, json({ expected_revision: change.revision, actor: f.get("actor"), reason: f.get("reason"), accept_ids: accepted })); setSnapshotId(value.snapshot_id); setAccepted([]); await loadRun(run!.id); setNotice("선택한 지식을 검토 버전으로 저장했습니다."); }); }}>
      <h3 className="font-semibold">원문 대조 후 승인할 지식 선택</h3><p className="text-sm">자동 검수는 사람의 승인이 아닙니다. 목록에서 검토한 항목을 직접 선택하세요. 검색용 개념을 승인된 상위 유형으로 승격하지 않습니다.</p>
      <div className="max-h-80 overflow-auto">{change.candidates.map(c => <div key={c.id} className="mb-2"><label><input type="checkbox" disabled={!change.eligible_ids.includes(c.id) || busy} checked={accepted.includes(c.id)} onChange={e => setAccepted(toggle(accepted, c.id, e.target.checked))} /> {c.statement}</label>{!change.eligible_ids.includes(c.id) && <span className="text-amber-800"> · 근거·표현 확인 미완료</span>}<details><summary>근거</summary>{c.evidence.map((e, i) => <blockquote key={i}>{e.quote || `원문 구간 ${e.block_id} (${e.precision || '구간 단위'})`}</blockquote>)}</details></div>)}</div>
      <label className="block">검토자<input name="actor" required className={field} /></label><label className="block">판단 이유<input name="reason" required className={field} /></label><button className={button} disabled={busy || running || !accepted.length}>선택 항목 승인·버전 저장</button>
    </form>}
    <form className="space-y-3 rounded border p-4" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action(async () => setAnswer(await request("/business/search", json({ ...(querySource === "extracted" ? { source_run_id: run!.id } : { snapshot_id: snapshotId }), question: f.get("question"), retrieval: f.get("retrieval") })))); }}>
      <h3 className="font-semibold">검토한 지식에 질문</h3><label className="block">답변 근거<select className={field} value={querySource} onChange={e => { setQuerySource(e.target.value); setAnswer(null); }}><option value="reviewed">승인한 지식 버전</option><option value="extracted" disabled={!run || running}>선택한 추출 실행의 원문</option></select></label>{querySource === "extracted" && <p className="text-sm">현재 선택한 실행의 그래프로 원문을 찾습니다. 답변 생성은 온톨로지 승인이나 업무 요구 전체의 충족을 뜻하지 않습니다.</p>}<label className="block">근거 찾기<select name="retrieval" className={field} defaultValue="hipporag2"><option value="hipporag2">개념·관계 연결 검색 (개발 기본)</option><option value="bm25">단어 검색 (BM25 비교)</option></select></label><label className="block">사용할 버전<select className={field} required={querySource === "reviewed"} disabled={querySource === "extracted"} value={snapshotId} onChange={e => { setSnapshotId(e.target.value); setAnswer(null); }}><option value="">선택</option>{snapshots.map(s => <option key={s.id} value={s.id}>{s.reason} · {s.counts.claims}개 주장</option>)}</select></label><label className="block">질문<textarea name="question" required className={field} /></label><button className={button} disabled={busy || (querySource === "reviewed" ? !snapshotId : !run || running)}>답변 확인</button>
      {answer && <div><p>{status[answer.status] || answer.status}</p><p className="whitespace-pre-wrap">{answer.answer?.answer}</p>{answer.answer?.limitations.map((l, i) => <p key={i}>{l}</p>)}<p className="text-xs">사용 근거: {answer.answer?.citations.join(", ") || "없음"}</p></div>}
    </form>
    <form className="space-y-3 rounded border p-4" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action(async () => { const result = await request<{ impacts: typeof impacts }>("/business/changes", json({ before_version_id: f.get("before"), after_version_id: f.get("after"), key_fields: String(f.get("keys") || "").split(",").map(v => v.trim()).filter(Boolean) })); setImpacts(result.impacts); await refresh(); }); }}>
      <h3 className="font-semibold">원문 변경 영향 확인</h3><p className="text-sm">기존 근거 연결과 새 의미의 관련성을 함께 확인합니다. 영향이 있거나 미확정이면 위에서 새 버전으로 같은 요구를 다시 확인하세요.</p>
      {([['before', '변경 전'], ['after', '변경 후']] as const).map(([name, label]) => <label key={name} className="block">{label}<select name={name} required className={field}><option value="">같은 자료의 버전 선택</option>{versionOptions.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}</select></label>)}
      <label className="block">표의 행 식별 열 (쉼표 구분, 일반 문서는 비움)<input name="keys" className={field} /></label><button className={button} disabled={busy || running}>변경 영향 확인</button>{impacts.map(i => <p key={i.requirement_id}>{requirements.find(r => r.id === i.requirement_id)?.question || i.requirement_id} · {({ affected: "영향 있음", unaffected: "영향 없음", unknown: "미확정" })[i.status] || i.status}{i.new_relevance ? " · 새 관련 요구" : ""}<br />{i.reason}</p>)}
    </form>
  </section>;
}

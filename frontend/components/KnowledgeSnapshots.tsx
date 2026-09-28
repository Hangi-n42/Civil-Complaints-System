"use client";

import { useCallback, useEffect, useState } from "react";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type Candidate = { id: string; kind: string; review_status: string; mention?: string; predicate_id?: string; raw_value?: string; subject_link_id?: string; object_link_id?: string; validation_errors?: string[] };
type Change = { id: string; revision: number; ontology_version_id: string; run_id: string; candidates: Candidate[] };
type Counts = { entities: number; links: number; assertions: number; excluded?: number };
type Snapshot = { id: string; parent_id: string | null; created_at: string; reason: string; actor: string; counts: Counts };
type Listing = { active_snapshot_id: string | null; status_revision: number; items: Snapshot[]; events: { id: string; before_id: string | null; after_id: string; actor: string; reason: string; created_at: string }[] };
type Target = { type: "assertion" | "evidence" | "source_version"; id: string };
type Availability = { type: Target["type"]; target_id: string; state: string; status_revision: number; history: { id: string; state: string; actor: string; reason: string; recorded_at: string }[] };
type Assertion = { id: string; subject_id: string; predicate_id: string; object_entity_id?: string; value: unknown; unit?: string; scope: Record<string, unknown>; dates: unknown[]; conditions: string[]; exceptions: string[]; evidence_ids: string[]; validity_status: string };
type View = { snapshot_id: string | null; active_snapshot_id: string | null; ontology_version_id?: string; status_revision: number; counts: Counts; definitions?: { id: string; name: string }[]; entities: { id: string; name: string; official_id?: string }[]; assertions: Assertion[]; evidence: { id: string; source_version_id: string; locator: Record<string, unknown> }[]; sources: { id: string; title: string }[]; versions: { id: string; source_id: string; format: string }[]; coverage: { entity_id?: string | null; as_of?: string | null; excluded: { id: string; reasons: { type?: Target["type"]; id?: string; state: string }[] }[] }; validity_status: string };
type Evidence = { evidence: { quote: string }; block: { locator: Record<string, unknown>; text: string }; source: { id: string; title: string }; version: { id: string }; availability?: { state: string } };
const field = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const button = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const labels: Record<string, string> = { allowed: "사용 가능", needs_review: "재검토 필요", blocked: "사용 중단" };

export default function KnowledgeSnapshots({ request, visible }: { request: Request; visible: boolean }) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [ontologies, setOntologies] = useState<{ id: string; status: string }[]>([]);
  const [ontologyId, setOntologyId] = useState("");
  const [selection, setSelection] = useState<Record<string, string[]>>({});
  const [snapshotId, setSnapshotId] = useState("active");
  const [view, setView] = useState<View | null>(null);
  const [entityId, setEntityId] = useState("");
  const [asOf, setAsOf] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [state, setState] = useState("needs_review");
  const [actor, setActor] = useState("local-user");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async (id = "active") => {
    const [list, candidates, schemas, detail] = await Promise.all([
      request<Listing>("/snapshots"), request<{ changesets: Change[] }>("/candidates?kind=entity_link"),
      request<{ items: { id: string; status: string }[] }>("/ontologies"), request<View>(`/snapshots/${id}`),
    ]);
    setListing(list); setChanges(candidates.changesets); setOntologies(schemas.items.filter(s => s.status === "reviewed"));
    setView(detail); setSnapshotId(id); setEntityId(""); setAsOf(""); setEvidence(null); setTarget(null); setAvailability(null);
  }, [request]);
  useEffect(() => { if (visible) refresh().catch(e => setError(e.message)); }, [visible, refresh]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function toggle(change: Change, ids: string[], checked: boolean) {
    setSelection(previous => ({ ...previous, [change.id]: checked ? [...new Set([...(previous[change.id] || []), ...ids])] : (previous[change.id] || []).filter(id => !ids.includes(id)) }));
  }
  async function create() {
    const selections = changes.filter(c => c.ontology_version_id === ontologyId && selection[c.id]?.length).map(c => ({ changeset_id: c.id, expected_changeset_revision: c.revision, candidate_ids: selection[c.id] }));
    const result = await request<{ snapshot_id: string }>("/snapshots", post({ selections, expected_active_id: listing?.active_snapshot_id ?? null, actor, reason }));
    await refresh(result.snapshot_id); setNotice("비활성 지식 버전을 만들었습니다. 내용을 확인한 뒤 활성화하세요.");
  }
  async function activate() {
    if (!view?.snapshot_id) return;
    const result = await request<{ counts: Counts }>(`/snapshots/${view.snapshot_id}/activate`, post({ expected_active_id: listing?.active_snapshot_id ?? null, actor, reason }));
    await refresh(view.snapshot_id); setNotice(`활성 버전을 변경했습니다. 사용 가능한 주장 ${result.counts.assertions}개 · 제외 ${result.counts.excluded || 0}개`);
  }
  async function inspectTarget(next: Target) {
    setTarget(null); setAvailability(null);
    const value = await request<Availability>(`/availability?type=${next.type}&id=${encodeURIComponent(next.id)}`);
    setTarget(next); setAvailability(value); setState(value.state);
  }
  async function inspectEvidence(id: string) {
    const result = await request<Evidence>(`/evidence/${id}`); setEvidence(result);
    await inspectTarget({ type: "evidence", id });
  }
  async function updateState() {
    if (!target || !availability) return;
    await request("/availability", post({ targets: [target], state, expected_status_revision: availability.status_revision, actor, reason }));
    await refresh(snapshotId); await inspectTarget(target); setNotice("사용 상태를 저장했습니다. 과거 버전에도 같은 제한을 적용합니다.");
  }
  const query = () => new URLSearchParams({ ...(entityId ? { entity_id: entityId } : {}), ...(asOf ? { as_of: asOf } : {}) });
  async function filter() { setView(await request<View>(`/snapshots/${snapshotId}?${query()}`)); setEvidence(null); }
  async function download(format: "json" | "csv") {
    const params = new URLSearchParams({ format }); if (view?.coverage.entity_id) params.set("entity_id", view.coverage.entity_id); if (view?.coverage.as_of) params.set("as_of", view.coverage.as_of); if (view?.snapshot_id) params.set("snapshot_id", view.snapshot_id);
    const data = await request<{ content?: string }>(`/export?${params}`);
    const blob = new Blob([format === "csv" ? "\uFEFF" + (data.content || "") : JSON.stringify(data, null, 2)], { type: format === "csv" ? "text/csv;charset=utf-8" : "application/json" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `knowledge-${view?.snapshot_id || "empty"}.${format}`; link.click(); URL.revokeObjectURL(url);
  }
  const name = (id: string) => view?.entities.find(e => e.id === id)?.name || id;
  const slot = (id: string) => view?.definitions?.find(d => d.id === id)?.name || id;
  const validAction = !busy && !!actor.trim() && !!reason.trim();
  const selectedCount = Object.values(selection).reduce((n, ids) => n + ids.length, 0);

  return <section className="space-y-4">
    <h2 className="text-xl font-semibold">지식 버전</h2>
    <p className="text-sm text-slate-600">수락한 항목을 선택해 버전으로 저장하고 활성화합니다. 사용 중단 상태는 이전 버전으로 되돌려도 유지됩니다.</p>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error} <button className="underline" disabled={busy} onClick={() => action(async () => { await refresh(snapshotId); setSelection({}); setAvailability(null); setTarget(null); })}>최신 상태 다시 읽기</button></p>}
    {notice && <p role="status" className="rounded bg-blue-50 p-3">{notice}</p>}
    <div className="grid gap-3 md:grid-cols-2"><label>결정자<input className={field} value={actor} onChange={e => setActor(e.target.value)} /></label><label>변경 사유<input className={field} value={reason} onChange={e => setReason(e.target.value)} /></label></div>
    <details className="rounded border bg-white p-4"><summary>수락 항목으로 새 버전 만들기 · 선택 {selectedCount}개</summary>
      <label className="mt-3 block">기준 온톨로지<select className={field} value={ontologyId} onChange={e => { setOntologyId(e.target.value); setSelection({}); }}><option value="">검토된 온톨로지 선택</option>{ontologies.map(o => <option key={o.id} value={o.id}>{o.id}</option>)}</select></label>
      <p className="my-2 text-sm">이전 버전에 자동 누적하지 않습니다. 필요한 사실과 주체·대상 연결을 함께 선택하세요. 과거 실험 묶음도 있으므로 실행 ID를 확인하세요.</p>
      {changes.filter(c => c.ontology_version_id === ontologyId).map(change => {
        const accepted = change.candidates.filter(c => c.review_status === "accepted" && !c.validation_errors?.length);
        return <details key={change.id} className="my-2 rounded border p-3"><summary>실행 {change.run_id?.slice(0, 8)} · 묶음 {change.id.slice(0, 8)} · 수락 {accepted.length} / 보류 {change.candidates.filter(c => c.review_status === "deferred").length} / 기각 {change.candidates.filter(c => c.review_status === "rejected").length}</summary>
          <label className="my-2 block"><input type="checkbox" disabled={busy || !accepted.length} checked={!!accepted.length && accepted.every(c => selection[change.id]?.includes(c.id))} onChange={e => toggle(change, accepted.map(c => c.id), e.target.checked)} /> 이 묶음의 수락 항목 전체</label>
          <ul className="max-h-64 overflow-auto text-sm">{accepted.map(c => <li key={c.id}><label><input type="checkbox" disabled={busy} checked={selection[change.id]?.includes(c.id) || false} onChange={e => toggle(change, [c.id], e.target.checked)} /> {c.kind === "entity_link" ? `연결: ${c.mention}` : `${c.predicate_id}: ${c.raw_value || "관계"}`} · {c.id.slice(0, 8)}</label></li>)}</ul>
        </details>;
      })}
      <button className={button} disabled={!validAction || !selectedCount} onClick={() => action(create)}>선택 항목으로 버전 만들기</button>
    </details>
    <div className="flex flex-wrap items-end gap-3"><label className="grow">조회 버전<select className={field} disabled={busy} value={snapshotId} onChange={e => action(() => refresh(e.target.value))}><option value="active">현재 활성 버전</option>{listing?.items.map(s => <option key={s.id} value={s.id}>{s.id.slice(0, 8)} · {s.reason} {s.id === listing.active_snapshot_id ? "(활성)" : ""}</option>)}</select></label><button className={button} disabled={!validAction || !view?.snapshot_id || view.snapshot_id === listing?.active_snapshot_id} onClick={() => action(activate)}>이 버전 활성화 / 되돌리기</button><button className={button} disabled={busy} onClick={() => action(() => refresh(snapshotId))}>새로고침</button></div>
    {!view?.snapshot_id ? <p>아직 활성 지식 버전이 없습니다. 새 버전을 만들거나 저장된 버전을 선택하세요.</p> : <>
      <p>개체 {view.counts.entities} · 연결 {view.counts.links} · 사용 가능한 주장 {view.counts.assertions} · 제외 {view.counts.excluded || 0} · 상태 버전 {view.status_revision}</p>
      <div className="flex flex-wrap items-end gap-3"><label>대상<select className={field} value={entityId} onChange={e => setEntityId(e.target.value)}><option value="">전체</option>{view.entities.map(e => <option key={e.id} value={e.id}>{e.name} · {e.official_id}</option>)}</select></label><label>업무 기준일<input type="date" className={field} value={asOf} onChange={e => setAsOf(e.target.value)} /></label><button className={button} disabled={busy} onClick={() => action(filter)}>조회</button><button className={button} disabled={busy} onClick={() => action(() => download("json"))}>JSON 내보내기</button><button className={button} disabled={busy} onClick={() => action(() => download("csv"))}>CSV 내보내기</button></div>
      <p className="text-sm text-slate-600">{view.validity_status === "unverified" ? "유효기간 판정 근거가 없는 항목이 있습니다. 사건 날짜를 기준일의 유효기간으로 추정하지 않습니다." : "명시된 유효기간 근거에 따라 조회했습니다."}</p>
      <div className="grid gap-4 lg:grid-cols-2"><div className="max-h-[600px] space-y-2 overflow-auto">{view.assertions.map(a => <article key={a.id} className="rounded border bg-white p-3 text-sm"><strong>{name(a.subject_id)} · {slot(a.predicate_id)}</strong><p>{a.object_entity_id ? `→ ${name(a.object_entity_id)}` : `${typeof a.value === "object" ? JSON.stringify(a.value) : String(a.value)} ${a.unit || ""}`}</p><p>범위: {String(a.scope.description || "미확인")}</p>{!!a.dates.length && <p>날짜: {JSON.stringify(a.dates)}</p>}{!!a.conditions.length && <p>조건: {a.conditions.join(" / ")}</p>}{!!a.exceptions.length && <p>예외: {a.exceptions.join(" / ")}</p>}<div className="mt-2 flex flex-wrap gap-2">{a.evidence_ids.map((id, n) => <button key={id} disabled={busy} className="underline" onClick={() => action(() => inspectEvidence(id))}>근거 {n + 1}</button>)}<button className="underline" disabled={busy} onClick={() => action(() => inspectTarget({ type: "assertion", id: a.id }))}>주장 사용 상태</button></div></article>)}</div>
      <aside className="space-y-3 rounded border bg-white p-4"><h3 className="font-semibold">원문·위치 확인</h3>{evidence ? <><p>{evidence.source.title}</p><p className="whitespace-pre-wrap rounded bg-slate-50 p-3">{evidence.evidence.quote}</p><pre className="overflow-auto text-xs">{JSON.stringify(evidence.block.locator, null, 2)}</pre><details><summary>원문 블록 확인</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap text-sm">{evidence.block.text}</pre></details><button className="underline" disabled={busy} onClick={() => action(() => inspectTarget({ type: "source_version", id: evidence.version.id }))}>이 자료 버전 사용 상태</button></> : <p className="text-sm">주장의 근거를 선택하세요.</p>}
        <h3 className="font-semibold">사용 상태·이력</h3>{target && availability ? <><p className="break-all text-xs">{target.type} · {target.id}</p><p>현재: {labels[availability.state]}</p><label>변경할 상태<select className={field} value={state} onChange={e => setState(e.target.value)}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button className={button} disabled={!validAction} onClick={() => action(updateState)}>사용 상태 저장</button><p className="text-xs">재허용은 선택 대상에만 적용됩니다. 다른 근거나 자료의 사용 중단은 유지됩니다.</p><ul className="max-h-48 overflow-auto text-xs">{availability.history.map(h => <li key={h.id}>{h.recorded_at} · {labels[h.state]} · {h.actor} · {h.reason}</li>)}</ul></> : <p className="text-sm">주장·근거·자료의 사용 상태를 선택하세요.</p>}</aside></div>
      {!!view.coverage.excluded.length && <details open className="rounded border p-3"><summary>제외된 주장 {view.coverage.excluded.length}개</summary><ul className="text-sm">{view.coverage.excluded.map(x => <li key={x.id}>{x.id.slice(0, 8)}: {x.reasons.map((r, n) => <span key={n}>{labels[r.state] || r.state} {r.type && r.id && <button className="underline" disabled={busy} onClick={() => action(() => inspectTarget({ type: r.type!, id: r.id! }))}>사유·상태 확인</button>} </span>)}</li>)}</ul></details>}
      <details className="rounded border p-3"><summary>자료 버전 사용 상태</summary><ul>{view.versions.map(v => <li key={v.id}><button className="text-sm underline" disabled={busy} onClick={() => action(() => inspectTarget({ type: "source_version", id: v.id }))}>{view.sources.find(s => s.id === v.source_id)?.title} · {v.format}</button></li>)}</ul></details>
    </>}
    <details className="rounded border p-3"><summary>활성화·되돌리기 이력</summary><ul className="text-sm">{listing?.events.map(e => <li key={e.id}>{e.created_at} · {e.before_id?.slice(0, 8) || "없음"} → {e.after_id.slice(0, 8)} · {e.actor} · {e.reason}</li>)}</ul></details>
  </section>;
}

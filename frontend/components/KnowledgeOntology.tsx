"use client";

import { useCallback, useEffect, useState } from "react";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type SourceItem = { source: { id: string; title: string }; versions: { id: string; format: string; processing_status?: string }[] };
type CQ = { id: string; question: string };
type Candidate = { id: string; kind: "concept" | "attribute" | "relation"; name: string; definition: string; inclusion: string; exclusion: string; domain_id?: string | null; range: string; required: boolean; multivalued: boolean; enum_values: string[]; evidence: { evidence_id: string; quote: string }[]; cq_ids: string[]; review_status?: string; issues?: unknown[] };
type Changeset = { id: string; revision: number; ontology_version_id?: string; review?: unknown; original_candidates?: Candidate[]; reviewed_ontology_version_id?: string; decisions?: { id: string; candidate_id: string; action: string; actor: string; created_at: string; reason: string }[] };
type Candidates = { items: Candidate[]; changeset_id?: string; changeset_revision?: number; unresolved_count?: number; changesets?: Changeset[] };
type Ontology = { id: string; status: string; changeset_id: string; created_at: string; linkml_yaml?: string; json_schema?: unknown; candidates?: Candidate[] };
type Run = { id: string; status: string; units: { id: string; stage?: string; status: string; error?: string; output?: unknown }[]; metrics?: { llm_calls?: number; model_total_s?: number; elapsed_s?: number }; changeset_id?: string; ontology_version_id?: string; review?: unknown };
type Evidence = { evidence: { quote: string }; block: { text: string; locator: unknown }; source: { title: string } };
const inputClass = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const buttonClass = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const active = (status: string) => ["queued", "running", "cancel_requested"].includes(status);
const labels: Record<string, string> = { queued: "대기", running: "처리 중", succeeded: "완료", failed: "실패", cancelled: "취소됨", cancel_requested: "취소 요청됨", concept: "개념", attribute: "속성", relation: "관계", pending: "검토 전", proposed: "검토 전", accepted: "수락", modified: "수정 후 수락", deferred: "보류", rejected: "기각", draft: "초안", reviewed: "검토됨", analyze: "자료 분석", analysis: "자료 분석", accept: "수락", modify: "수정 후 수락", defer: "보류", reject: "기각", design: "온톨로지 설계", review: "반례 검토", revise: "수정" };
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export default function KnowledgeOntology({ request, sources }: { request: Request; sources: SourceItem[] }) {
  const [versionIds, setVersionIds] = useState<string[] | null>(null);
  const [cqs, setCqs] = useState<CQ[]>([]);
  const [baseId, setBaseId] = useState("");
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [ontology, setOntology] = useState<Ontology | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [concepts, setConcepts] = useState<Candidate[]>([]);
  const [result, setResult] = useState<Candidates | null>(null);
  const [changesetId, setChangesetId] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<Candidate | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [actor, setActor] = useState("local-user");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = !!run && active(run.status);
  const selectedVersions = versionIds ?? sources.flatMap(s => s.versions.filter(v => v.processing_status === "parsed" && (v.format === "csv" || (v.format === "html" && s.source.title.includes("20796")))).map(v => v.id));
  const changeset = result?.changesets?.find(c => c.id === changesetId);
  const revision = result?.changeset_revision ?? changeset?.revision;
  const unresolved = result?.unresolved_count ?? result?.items.filter(c => !["accepted", "modified", "rejected"].includes(c.review_status || "pending")).length ?? 0;
  const original = changeset?.original_candidates?.find(c => c.id === draft?.id);
  const review = changeset?.review ?? run?.review ?? run?.units.find(u => u.stage === "review")?.output;

  const refreshOntologies = useCallback(async () => setOntologies((await request<{ items: Ontology[] }>("/ontologies")).items), [request]);
  const loadCandidates = useCallback(async (id: string) => {
    const data = await request<Candidates>(`/candidates?changeset_id=${encodeURIComponent(id)}`);
    const currentVersion = data.changesets?.find(c => c.id === id)?.ontology_version_id;
    const schema = currentVersion ? await request<Ontology>(`/ontologies/${currentVersion}`) : null;
    setConcepts((schema?.candidates || data.items).filter(c => c.kind === "concept"));
    setChangesetId(id); setResult(data); setSelectedIds([]); setDraft(null); setEvidence(null);
  }, [request]);
  useEffect(() => {
    let disposed = false;
    Promise.all([request<{ items: CQ[] }>("/ontology-cqs"), request<{ items: Ontology[] }>("/ontologies")]).then(([questions, versions]) => {
      if (!disposed) { setCqs(questions.items); setOntologies(versions.items); }
    }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [request]);
  useEffect(() => {
    if (!run || !running) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const next = await request<Run>(`/runs/${run.id}`);
        if (disposed) return;
        setRun(next);
        if (!active(next.status)) {
          await refreshOntologies();
          if (next.changeset_id) await loadCandidates(next.changeset_id);
        }
      } catch (e) { if (!disposed) setError((e as Error).message); }
    }, 1500);
    return () => { disposed = true; clearInterval(timer); };
  }, [run, running, request, refreshOntologies, loadCandidates]);

  async function start(retry = false) {
    setBusy(true); setError("");
    try {
      const body = retry && run ? { kind: "ontology", retry_of_run_id: run.id } : { kind: "ontology", source_version_ids: selectedVersions, cqs: cqs.filter(q => q.question.trim()), base_ontology_version_id: baseId || undefined };
      const created = await request<{ run_id: string }>("/runs", post(body));
      setResult(null); setDraft(null); setEvidence(null); setOntology(null); setSelectedIds([]);
      const next = await request<Run>(`/runs/${created.run_id}`); setRun(next);
      if (!active(next.status)) { await refreshOntologies(); if (next.changeset_id) await loadCandidates(next.changeset_id); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function openOntology(id: string) {
    if (!id) return;
    setBusy(true); setError(""); setRun(null);
    try {
      const data = await request<Ontology>(`/ontologies/${id}`); setOntology(data);
      if (data.changeset_id) await loadCandidates(data.changeset_id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function decide(action: "accept" | "modify" | "defer" | "reject", ids: string[]) {
    if (!changesetId || revision === undefined || !ids.length) return;
    setBusy(true); setError("");
    try {
      let patch: Partial<Candidate> | undefined;
      if (action === "modify" && draft) {
        const { name, definition, inclusion, exclusion, domain_id, range, required, multivalued, enum_values, evidence, cq_ids } = draft;
        patch = { name, definition, inclusion, exclusion, domain_id, range, required, multivalued, enum_values: enum_values.filter(value => value.trim()), evidence, cq_ids };
      }
      await request<Candidates>(`/changes/${changesetId}/decisions`, post({ expected_changeset_revision: revision, actor, decisions: ids.map(candidate_id => ({ candidate_id, action, reason, ...(patch ? { patch } : {}) })) }));
      await loadCandidates(changesetId); await refreshOntologies(); setOntology(null); setReason("");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return <section className="space-y-4">
    <p className="rounded bg-blue-50 p-3 text-sm">정의·포함/제외 기준은 자료를 종합한 설계 제안입니다. 후보 수락은 운영 지식 활성화를 뜻하지 않습니다.</p>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
    <details className="rounded border bg-white p-4" open={!result}>
      <summary className="cursor-pointer font-semibold">온톨로지 초안 생성</summary>
      <fieldset disabled={busy || running} className="mt-4 space-y-4">
        <div><h3 className="font-medium">파싱 완료 자료</h3><div className="mt-2 max-h-56 space-y-2 overflow-auto">{sources.flatMap(s => s.versions.filter(v => v.processing_status === "parsed").map(v => <label key={v.id} className="block text-sm"><input type="checkbox" checked={selectedVersions.includes(v.id)} onChange={e => setVersionIds(e.target.checked ? [...selectedVersions, v.id] : selectedVersions.filter(id => id !== v.id))} /> {s.source.title} · {v.format.toUpperCase()}</label>))}{!sources.some(s => s.versions.some(v => v.processing_status === "parsed")) && <p className="text-sm text-slate-500">자료 탭에서 원문 추출을 먼저 완료하세요.</p>}</div></div>
        <div className="space-y-2"><h3 className="font-medium">업무 질문 (CQ)</h3><p className="text-xs text-slate-500">개발 과제의 질문만 초기값으로 사용합니다. 선택 자료와 관계없는 질문은 삭제하거나 수정하세요.</p>{cqs.map((q, i) => <div key={q.id} className="flex items-start gap-2"><label className="flex-1 text-xs">{q.id}<textarea className={inputClass} value={q.question} onChange={e => setCqs(cqs.map((item, j) => j === i ? { ...item, question: e.target.value } : item))} /></label><button type="button" className="mt-5 text-sm underline" onClick={() => setCqs(cqs.filter((_, j) => j !== i))}>삭제</button></div>)}<button type="button" className="text-sm underline" onClick={() => setCqs([...cqs, { id: `CQ-${Date.now()}`, question: "" }])}>질문 추가</button></div>
        <label className="block text-sm">기준 온톨로지<select className={inputClass} value={baseId} onChange={e => setBaseId(e.target.value)}><option value="">새 초안</option>{ontologies.filter(o => o.status === "reviewed").map(o => <option key={o.id} value={o.id}>{new Date(o.created_at).toLocaleString("ko-KR")} · {o.id.slice(0, 8)}</option>)}</select></label>
        <p className="text-xs text-slate-500">자료 분석 → 설계 → 반례 검토 1회 → 필요한 경우 수정 1회. 자료·질문·모델 설정은 실행 시 고정됩니다.</p>
        <button className={buttonClass} onClick={() => start()} disabled={busy || running || !selectedVersions.length || !cqs.some(q => q.question.trim())}>초안 생성</button>
      </fieldset>
    </details>
    {run && <div role="status" className="rounded border bg-white p-4 text-sm"><p className="font-semibold">생성 작업: {labels[run.status] || run.status}</p><p>모델 호출 {run.metrics?.llm_calls ?? 0}회 · 모델 시간 {(run.metrics?.model_total_s ?? 0).toFixed(1)}초 · 경과 {(run.metrics?.elapsed_s ?? 0).toFixed(1)}초</p><ul className="my-2 space-y-1">{run.units.map(u => <li key={u.id}>{labels[u.stage || ""] || u.stage || u.id}: {labels[u.status] || u.status}{u.error && <span className="ml-2 text-red-700">{u.error}</span>}</li>)}</ul>{running && <button disabled={busy || run.status === "cancel_requested"} className="underline disabled:opacity-40" onClick={async () => { setBusy(true); try { await request(`/runs/${run.id}/cancel`, { method: "POST" }); setRun(await request<Run>(`/runs/${run.id}`)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>현재 호출 종료 후 중단</button>}{["failed", "cancelled", "partial"].includes(run.status) && <button disabled={busy} className={buttonClass} onClick={() => start(true)}>성공 단계 재사용 · 실패 단계부터 재시도</button>}</div>}
    <label className="block rounded border bg-white p-4 text-sm">저장된 온톨로지 버전<select className={`${inputClass} mt-2`} value={ontology?.id || ""} disabled={busy || running} onChange={e => openOntology(e.target.value)}><option value="">버전 선택</option>{ontologies.map(o => <option key={o.id} value={o.id}>{labels[o.status] || o.status} · {new Date(o.created_at).toLocaleString("ko-KR")} · {o.id.slice(0, 8)}</option>)}</select></label>
    {ontology && <details className="rounded border bg-white p-4 text-sm"><summary className="cursor-pointer">LinkML 정본 · 파생 JSON Schema</summary><h3 className="mt-3 font-semibold">LinkML</h3><pre className="max-h-80 overflow-auto whitespace-pre-wrap p-2">{ontology.linkml_yaml}</pre><h3 className="font-semibold">JSON Schema</h3><pre className="max-h-80 overflow-auto whitespace-pre-wrap p-2">{JSON.stringify(ontology.json_schema, null, 2)}</pre></details>}
    {result && <>
      <div className="rounded border bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">후보 검토 · {result.items.length}개 · 미해결 {unresolved}개</h2><button disabled={busy} className="text-sm underline" onClick={async () => { setBusy(true); try { await loadCandidates(changesetId); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>최신 검토 상태 불러오기</button></div><p className="mt-1 text-xs text-slate-500">개념을 참조하는 속성·관계는 해당 개념과 함께 수락하세요. 수정 후 수락은 화면의 편집 내용을 저장합니다.</p>{review != null && <details className="mt-3 text-sm"><summary>AI 반례 검토 의견</summary><p className="my-2 text-slate-600">수정 전 검토 의견입니다. 수정 후 해결 여부를 AI가 재검증하지 않았으므로 원문과 대조해 결정하세요.</p><pre className="max-h-60 overflow-auto whitespace-pre-wrap">{JSON.stringify(review, null, 2)}</pre></details>}<details className="mt-3 text-sm"><summary>검토 결정 이력 ({changeset?.decisions?.length || 0}건)</summary><ul className="mt-2 space-y-2">{changeset?.decisions?.map(d => <li key={d.id}>{d.candidate_id} · {labels[d.action] || d.action} · {d.actor} · {new Date(d.created_at).toLocaleString("ko-KR")}<p className="text-slate-600">{d.reason || "사유 미기록"}</p></li>)}</ul></details><div className="mt-3 grid gap-2 md:grid-cols-2"><label className="text-sm">결정자<input className={inputClass} value={actor} onChange={e => setActor(e.target.value)} /></label><label className="text-sm">짧은 판단 사유<input className={inputClass} value={reason} onChange={e => setReason(e.target.value)} /></label></div><div className="mt-3 flex flex-wrap items-center gap-2"><label className="text-sm"><input type="checkbox" checked={result.items.length > 0 && selectedIds.length === result.items.length} onChange={e => setSelectedIds(e.target.checked ? result.items.map(c => c.id) : [])} /> 전체 선택</label>{([['accept', '선택 수락'], ['defer', '선택 보류'], ['reject', '선택 기각']] as const).map(([action, label]) => <button key={action} disabled={busy || !actor.trim() || !selectedIds.length} className={buttonClass} onClick={() => decide(action, selectedIds)}>{label}</button>)}</div></div>
      <div className="grid gap-4 xl:grid-cols-2"><section className="space-y-2 rounded border bg-white p-4"><h3 className="font-semibold">개념·속성·관계</h3><div className="max-h-72 space-y-2 overflow-auto">{result.items.map(c => <div key={c.id} className={`flex items-center gap-2 rounded border p-2 ${draft?.id === c.id ? "border-blue-500 bg-blue-50" : ""}`}><input aria-label={`${c.name} 일괄 선택`} type="checkbox" checked={selectedIds.includes(c.id)} onChange={e => setSelectedIds(e.target.checked ? [...selectedIds, c.id] : selectedIds.filter(id => id !== c.id))} /><button disabled={busy} className="flex-1 text-left text-sm" onClick={() => { setDraft({ ...c }); setEvidence(null); }}>{labels[c.kind]} · {c.name}<span className="ml-2 text-xs text-slate-500">{labels[c.review_status || "pending"] || c.review_status}</span></button></div>)}</div>
      {draft && <fieldset disabled={busy} className="space-y-3 border-t pt-3"><legend className="pt-3 text-sm font-semibold">후보 편집 · {draft.id}</legend>{([['name', '이름'], ['definition', '정의 (설계 제안)'], ['inclusion', '포함 기준'], ['exclusion', '제외 기준']] as const).map(([key, title]) => <label key={key} className="block text-sm">{title}<textarea className={inputClass} value={draft[key] || ""} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>)}{draft.kind !== "concept" && <><label className="block text-sm">소속 개념 · 관계 출발점<select className={inputClass} value={draft.domain_id || ""} onChange={e => setDraft({ ...draft, domain_id: e.target.value || null })}><option value="">선택</option>{concepts.map(c => <option key={c.id} value={c.id}>{c.name} · {c.id}</option>)}</select></label><label className="block text-sm">값 유형 · 관계 도착점<input className={inputClass} value={draft.range || ""} onChange={e => setDraft({ ...draft, range: e.target.value })} list="ontology-ranges" /><datalist id="ontology-ranges">{["string", "integer", "float", "double", "boolean", "date", "datetime", "uri", ...concepts.map(c => c.id)].map(value => <option key={value} value={value} />)}</datalist></label><label className="block text-sm">허용 값 (한 줄에 하나)<textarea className={inputClass} value={(draft.enum_values || []).join("\n")} onChange={e => setDraft({ ...draft, enum_values: e.target.value.split("\n") })} /></label><div className="flex gap-4 text-sm"><label><input type="checkbox" checked={!!draft.required} onChange={e => setDraft({ ...draft, required: e.target.checked })} /> 필수</label><label><input type="checkbox" checked={!!draft.multivalued} onChange={e => setDraft({ ...draft, multivalued: e.target.checked })} /> 여러 값 허용</label></div></>}<p className="text-xs text-slate-500">연결 업무 질문: {(draft.cq_ids || []).join(", ") || "없음"}</p>{draft.issues && draft.issues.length > 0 && <pre className="whitespace-pre-wrap text-xs text-amber-800">{JSON.stringify(draft.issues, null, 2)}</pre>}<button disabled={!actor.trim()} className={buttonClass} onClick={() => decide("modify", [draft.id])}>수정 후 수락</button>{original && <details className="text-xs"><summary>AI 원제안</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap">{JSON.stringify(original, null, 2)}</pre></details>}</fieldset>}
      </section><section className="rounded border bg-white p-4"><h3 className="font-semibold">근거 원문 · 위치</h3>{!draft ? <p className="mt-3 text-sm text-slate-500">후보를 선택하면 근거를 확인할 수 있습니다.</p> : <div className="mt-3 space-y-2">{(draft.evidence || []).map((e, i) => <button key={`${e.evidence_id}-${i}`} disabled={busy} className="block w-full rounded border p-3 text-left text-sm" onClick={async () => { setBusy(true); try { setEvidence(await request<Evidence>(`/evidence/${e.evidence_id}`)); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}><span className="block text-xs text-slate-500">{e.evidence_id}</span>{e.quote}</button>)}{!draft.evidence?.length && <p className="text-sm text-amber-700">연결된 근거가 없습니다.</p>}</div>}{evidence && <div className="mt-4 border-t pt-3"><h4 className="text-sm font-medium">{evidence.source.title}</h4><pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">{evidence.block.text || evidence.evidence.quote}</pre><details className="mt-2 text-xs" open><summary>페이지·표·문단 위치</summary><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify(evidence.block.locator, null, 2)}</pre></details></div>}</section></div>
    </>}
  </section>;
}

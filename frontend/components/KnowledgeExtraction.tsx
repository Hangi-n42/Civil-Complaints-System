"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type SourceItem = { source: { id: string; title: string }; versions: { id: string; format: string; processing_status?: string }[] };
type CQ = { id: string; question: string };
type Block = { id: string; source_version_id?: string; text: string; evidence_id: string; locator: { physical_page?: number; printed_page?: number; side?: string; table?: number; [key: string]: unknown } };
type Ontology = { id: string; status: string; created_at: string };
type Entity = { id: string; concept_id: string; namespace: string; official_id?: string; name: string };
type DateFact = { role?: string; value?: string; precision?: string; [key: string]: unknown };
type BaseCandidate = { usage_restrictions?: { state: string }[]; id: string; review_status: string; revision: number; evidence_ids: string[]; validation_errors?: unknown[]; scope: Record<string, unknown> };
type EntityLink = BaseCandidate & { kind: "entity_link"; mention: string; concept_id: string; target_entity_id: string | null; method: string; candidate_entity_ids?: string[] };
type Assertion = BaseCandidate & { kind: "assertion"; subject_link_id: string; subject_id?: string; predicate_id: string; object_link_id?: string | null; object_entity_id?: string | null; value: unknown; raw_value: string; unit?: string | null; conditions: string[]; exceptions: string[]; dates: DateFact[]; field_evidence: Record<string, string[]>; link_dependencies?: { link_id: string; revision: number }[] };
type Candidate = EntityLink | Assertion;
type Decision = { id: string; candidate_id: string; action: string; reason: string; actor: string; created_at: string };
type Changeset = { id: string; kind?: string; run_id?: string; revision: number; created_at?: string; decisions?: Decision[] };
type Results = { items: Candidate[]; changesets: Changeset[]; changeset_id: string; changeset_revision: number; unresolved_count: number };
type Definition = { id: string; name: string; kind: string; range: string; multivalued?: boolean };
type Run = { unsupported_slots?: string[]; frozen_blocks?: Block[]; ontology_candidates?: Definition[]; id: string; status: string; changeset_id?: string; units: { id: string; stage?: string; kind?: string; status: string; error?: string; block_ids?: string[]; invalid_records?: unknown[]; coverage?: { id: string; status: string; reason?: string; fact_count?: number }[] }[]; metrics?: { llm_calls?: number; planned_llm_calls?: number; model_total_s?: number; elapsed_s?: number; [key: string]: unknown }; planned_llm_calls?: number; invalid_record_count?: number; processed_block_ids?: string[]; candidate_counts?: { manual?: number; automatic?: number; valid: number; invalid: number; unresolved: number }; excluded_blocks?: unknown[]; counts?: Record<string, number>; ontology_version_id?: string; input_version_ids?: string[]; parse_run_ids?: Record<string, string> };
type Evidence = { usage_restrictions?: { state: string }[]; evidence: { quote: string; alignment_status?: string; start_char?: number; end_char?: number }; block: Block; source: { id: string; title: string }; version: { id: string } };
type EntityDetail = { entity: Entity; aliases: EntityLink[]; links: EntityLink[]; assertions: Assertion[] };
const field = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const button = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const labels: Record<string, string> = { proposed: "검토 전", accepted: "수락", deferred: "보류", rejected: "기각", queued: "대기", running: "처리 중", succeeded: "처리 완료", failed: "실패", cancelled: "취소됨", cancel_requested: "취소 요청됨", entity_link: "개체 연결", assertion: "사실·관계", official_id: "공식 ID", accepted_alias: "검토된 별칭", manual: "수동 연결", unresolved: "미연결", pdf: "PDF 표 매핑", mapped: "필드 매핑", llm: "모델 추출", accept: "수락", modify: "수정", defer: "보류", reject: "기각", unlink: "연결 해제", matched: "위치 일치", ambiguous: "위치 모호", unmatched: "위치 불일치" };
const active = (status: string) => ["queued", "running", "cancel_requested"].includes(status);
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const groupKey = (b: Block) => [b.locator.physical_page, b.locator.printed_page, b.locator.side, b.locator.table ?? "text"].join(":");
const groupLabel = (b: Block) => `물리 ${b.locator.physical_page ?? "?"}쪽 / 인쇄 ${b.locator.printed_page ?? "미기록"}쪽 · ${{ left: "왼쪽", right: "오른쪽", full: "전체 면" }[b.locator.side || ""] || b.locator.side || ""} · ${b.locator.table == null ? "본문" : `표 ${b.locator.table + 1}`}`;
const title = (c: Candidate) => c.kind === "entity_link" ? c.mention : `${c.predicate_id}: ${c.object_entity_id || c.raw_value || JSON.stringify(c.value)}`;
const htmlPilotBlock = (b: Block) => b.locator.script_array === "sbdList" || (b.locator.script_array === "list:complex_image" && b.locator.field === "imgAhflDesc");
const lines = (s: string) => s.split("\n").map(v => v.trim()).filter(Boolean);

export default function KnowledgeExtraction({ request, sources }: { request: Request; sources: SourceItem[] }) {
  const [general, setGeneral] = useState(false);
  const [localIds, setLocalIds] = useState<string[]>([]);
  const [blockIds, setBlockIds] = useState<string[]>([]);
  const [localDraft, setLocalDraft] = useState({ concept_id: "", name: "", block_id: "" });
  const [localConcepts, setLocalConcepts] = useState<{ id: string; kind: string; name: string }[]>([]);
  const [versionIds, setVersionIds] = useState<string[] | null>(null);
  const [registryId, setRegistryId] = useState<string | null>(null);
  const [ontologyId, setOntologyId] = useState("");
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const effectiveOntologyId = ontologyId || ontologies[0]?.id || "";
  const [cqs, setCqs] = useState<CQ[]>([]);
  const [blocks, setBlocks] = useState<Record<string, Block[]>>({});
  const [htmlLimited, setHtmlLimited] = useState(true);
  const [pdfGroups, setPdfGroups] = useState<Record<string, string[]>>({});
  const [run, setRun] = useState<Run | null>(null);
  const [changesets, setChangesets] = useState<Changeset[]>([]);
  const [result, setResult] = useState<Results | null>(null);
  const [draft, setDraft] = useState<Candidate | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entityDetail, setEntityDetail] = useState<EntityDetail | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [actor, setActor] = useState("local-user");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [manual, setManual] = useState({ subject_link_id: "", object_link_id: "", predicate_id: "", block_id: "", quote: "", raw_value: "", scope: "미확인" });
  const [evidenceRole, setEvidenceRole] = useState("value");
  const definitions = run?.ontology_candidates || [];
  const slotName = (id: string) => definitions.find(d => d.id === id)?.name || id;
  const [busy, setBusy] = useState(false);
  const running = !!run && active(run.status);
  const versions = useMemo(() => sources.flatMap(s => s.versions.filter(v => v.processing_status === "parsed").map(v => ({ ...v, source: s.source }))), [sources]);
  const selectedVersions = useMemo(() => versionIds ?? versions.filter(v => v.format === "csv" || (["html", "pdf"].includes(v.format) && v.source.title.includes("20796"))).map(v => v.id), [versionIds, versions]);
  const registry = registryId ?? versions.find(v => v.format === "csv")?.id ?? "";
  const selectedDocuments = useMemo(() => versions.filter(v => selectedVersions.includes(v.id) && ["html", "pdf", "hwpx"].includes(v.format)), [versions, selectedVersions]);
  const selectedPDFs = useMemo(() => versions.filter(v => selectedVersions.includes(v.id) && v.format === "pdf"), [versions, selectedVersions]);
  const links = result?.items.filter((c): c is EntityLink => c.kind === "entity_link") ?? [];
  const currentChange = result?.changesets.find(c => c.id === result.changeset_id);
  const evidenceRow = evidence?.block.locator.table == null ? [] : (blocks[evidence.version.id] || []).filter(b => {
    const selected = evidence.block.locator;
    return b.locator.physical_page === selected.physical_page && b.locator.side === selected.side && b.locator.table === selected.table && (b.locator.row === selected.row || b.locator.row === 0);
  });

  const refresh = useCallback(async () => {
    const [schemaData, linkData, entityData] = await Promise.all([request<{ items: Ontology[] }>("/ontologies"), request<Results>("/candidates?kind=entity_link"), request<{ items: Entity[] }>("/entities")]);
    setOntologies(schemaData.items.filter(o => o.status === "reviewed"));
    setChangesets(linkData.changesets); setEntities(entityData.items);
  }, [request]);
  useEffect(() => {
    let disposed = false;
    request<{ items: CQ[] }>("/ontology-cqs").then(data => { if (!disposed) setCqs(data.items.filter(q => ["DEV-02", "DEV-04"].includes(q.id))); }).catch(e => { if (!disposed) setError(e.message); });
    refresh().catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [request, refresh]);
  useEffect(() => {
    const missing = selectedDocuments.filter(v => !blocks[v.id]);
    if (!missing.length) return;
    let disposed = false;
    Promise.all(missing.map(async v => ({ id: v.id, format: v.format, data: await request<{ items: Block[] }>(`/sources/${v.source.id}/versions/${v.id}/blocks`) }))).then(values => {
      if (disposed) return;
      setBlocks(previous => ({ ...previous, ...Object.fromEntries(values.map(v => [v.id, v.data.items])) }));
      setPdfGroups(previous => ({ ...previous, ...Object.fromEntries(values.filter(v => v.format === "pdf" && previous[v.id] === undefined).map(v => [v.id, [...new Set(v.data.items.filter(b => b.locator.printed_page === 4 && b.locator.table != null && b.text.includes("최초입주")).map(groupKey))]])) }));
    }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [selectedDocuments, blocks, request]);
  useEffect(() => {
    if (!effectiveOntologyId) { setLocalConcepts([]); return; }
    let cancelled = false;
    request<{ candidates: { id: string; kind: string; name: string }[] }>(`/ontologies/${effectiveOntologyId}`).then(v => { if (!cancelled) setLocalConcepts(v.candidates.filter(c => c.kind === "concept")); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [effectiveOntologyId, request]);
  async function registerLocal() {
    setBusy(true); setError("");
    try {
      const block = Object.values(blocks).flat().find(b => b.id === localDraft.block_id);
      if (!block) throw new Error("원문 블록을 선택하세요.");
      const created = await request<Entity>("/entities", post({ ontology_version_id: effectiveOntologyId, concept_id: localDraft.concept_id, name: localDraft.name, source_version_id: block.source_version_id, evidence_ids: [block.evidence_id], actor, reason }));
      setLocalIds(ids => [...ids, created.id]); setBlockIds(ids => [...new Set([...ids, block.id])]); await refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const loadResults = useCallback(async (id: string) => {
    const data = await request<Results>(`/candidates?changeset_id=${encodeURIComponent(id)}`);
    setResult(data); setDraft(null); setEvidence(null); setSelectedIds([]);
    setEntities((await request<{ items: Entity[] }>("/entities")).items);
  }, [request]);
  useEffect(() => {
    if (!run || !running) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const next = await request<Run>(`/runs/${run.id}`);
        if (disposed) return;
        setRun(next);
        if (!active(next.status)) { await refresh(); if (next.changeset_id) await loadResults(next.changeset_id); }
      } catch (e) { if (!disposed) setError((e as Error).message); }
    }, 1500);
    return () => { disposed = true; clearInterval(timer); };
  }, [run, running, request, refresh, loadResults]);

  async function start(retry = false) {
    setBusy(true); setError("");
    try {
      let payload: Record<string, unknown> = { kind: "extract", retry_of_run_id: run?.id };
      if (!retry) {
        const chosen = versions.filter(v => selectedVersions.includes(v.id));
        const ids: string[] = [];
        for (const v of chosen) {
          const sourceBlocks = blocks[v.id] ?? (await request<{ items: Block[] }>(`/sources/${v.source.id}/versions/${v.id}/blocks`)).items;
          ids.push(...sourceBlocks.filter(b => v.format === "pdf" ? (pdfGroups[v.id] || []).includes(groupKey(b)) : v.format === "html" && htmlLimited ? htmlPilotBlock(b) : true).map(b => b.id));
        }
        payload = { kind: "extract", source_version_ids: selectedVersions, registry_source_version_id: general ? null : registry, local_entity_ids: general ? localIds : [], ontology_version_id: ontologyId || ontologies[0]?.id, block_ids: general ? blockIds : ids, cqs: cqs.filter(q => q.question.trim()) };
      }
      const created = await request<{ run_id: string }>("/runs", post(payload));
      setResult(null); setDraft(null); setEvidence(null); setSelectedIds([]);
      const next = await request<Run>(`/runs/${created.run_id}`); setRun(next);
      if (!active(next.status)) { await refresh(); if (next.changeset_id) await loadResults(next.changeset_id); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function openChange(id: string) {
    if (!id) return;
    setBusy(true); setError("");
    try {
      await loadResults(id);
      const change = changesets.find(c => c.id === id);
      setRun(change?.run_id ? await request<Run>(`/runs/${change.run_id}`) : null);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function decide(action: "accept" | "modify" | "defer" | "reject" | "unlink", ids: string[]) {
    if (!result || !ids.length) return;
    setBusy(true); setError("");
    try {
      let patch: Record<string, unknown> | undefined;
      if (action === "modify" && draft) {
        if (draft.kind === "entity_link") patch = { mention: draft.mention, evidence_ids: draft.evidence_ids.map(id => id.trim()).filter(Boolean), target_entity_id: draft.target_entity_id, scope: draft.scope };
        else { const { value, raw_value, unit, scope, conditions, exceptions, dates, evidence_ids, field_evidence, subject_link_id, object_link_id } = draft; patch = { value, raw_value, unit, scope, conditions: conditions.filter(v => v.trim()), exceptions: exceptions.filter(v => v.trim()), dates, evidence_ids: evidence_ids.filter(v => v.trim()), field_evidence, subject_link_id, object_link_id }; }
      }
      await request(`/changes/${result.changeset_id}/decisions`, post({ expected_changeset_revision: result.changeset_revision, actor, decisions: ids.map(candidate_id => ({ candidate_id, action, reason, ...(patch ? { patch } : {}) })) }));
      await loadResults(result.changeset_id); await refresh(); setReason(""); setEntityDetail(null);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const updateAssertion = (patch: Partial<Assertion>) => setDraft(current => {
    if (current?.kind !== "assertion") return current;
    const changed = { ...current, ...patch };
    if ("value" in patch && !patch.dates) changed.dates = current.dates.map(d => ({ ...d, value: String(patch.value ?? "") }));
    return changed;
  });
  function chooseEvidence(block: Block) {
    if (!draft) return;
    const id = block.evidence_id || block.id;
    const ids = [...new Set([...draft.evidence_ids, id])];
    setDraft(draft.kind === "assertion" ? { ...draft, evidence_ids: ids, field_evidence: { ...draft.field_evidence, [evidenceRole]: [id] } } : { ...draft, evidence_ids: ids });
  }
  async function addManual() {
    if (!result) return;
    setBusy(true); setError("");
    try {
      await request(`/changes/${result.changeset_id}/assertions`, post({ ...manual, object_link_id: manual.object_link_id || null, actor, reason, expected_changeset_revision: result.changeset_revision }));
      await loadResults(result.changeset_id);
      if (run) setRun(await request<Run>(`/runs/${run.id}`));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return <section className="space-y-4">
    <p className="rounded bg-blue-50 p-3 text-sm">원문 표기와 사실·관계 후보를 검토합니다. 위치 일치는 의미의 정확성을 보장하지 않으며, 수락된 후보도 운영 지식으로 활성화되지 않습니다.</p>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
    <details className="rounded border bg-white p-4" open={!result}><summary className="cursor-pointer font-semibold">개체·사실 추출</summary><fieldset disabled={busy || running} className="mt-4 space-y-4">
      <label className="block text-sm">검토된 온톨로지<select className={field} value={ontologyId || ontologies[0]?.id || ""} onChange={e => setOntologyId(e.target.value)}>{!ontologies.length && <option value="">온톨로지 검토를 먼저 완료하세요</option>}{ontologies.map(o => <option key={o.id} value={o.id}>{new Date(o.created_at).toLocaleString("ko-KR")} · {o.id.slice(0, 8)}</option>)}</select></label>
      <div><h3 className="font-medium">추출 자료</h3><div className="mt-2 max-h-56 space-y-2 overflow-auto">{versions.map(v => <label key={v.id} className="block text-sm"><input type="checkbox" checked={selectedVersions.includes(v.id)} onChange={e => setVersionIds(e.target.checked ? [...selectedVersions, v.id] : selectedVersions.filter(id => id !== v.id))} /> {v.source.title} · {v.format.toUpperCase()}</label>)}</div></div>
      <label className="block text-sm">공식 단지 등록부 (추출 자료와 별도 선택 가능)<select className={field} value={registry} onChange={e => setRegistryId(e.target.value)}><option value="">선택</option>{versions.filter(v => v.format === "csv").map(v => <option key={v.id} value={v.id}>{v.source.title}</option>)}</select></label>
      {selectedDocuments.some(v => v.format === "html") && <div className="rounded border p-3 text-sm"><label><input type="checkbox" checked={htmlLimited} onChange={e => setHtmlLimited(e.target.checked)} /> HTML 공식 단지 필드·단지 설명만 선택</label><p className="my-1 text-xs text-slate-500">포함: 공식 단지 메타데이터(sbdList), 단지 이미지 설명(imgAhflDesc). 제외: 사이트 안내·탐색 메뉴·접수 일정·일반 공고 표 등 나머지 HTML 구간. 원문은 보존되며 이 실행의 입력에서만 제외합니다.</p>{selectedDocuments.filter(v => v.format === "html").map(v => <p key={v.id} className="text-xs">{v.source.title}: {blocks[v.id] ? `선택 ${htmlLimited ? blocks[v.id].filter(htmlPilotBlock).length : blocks[v.id].length}개 / 전체 ${blocks[v.id].length}개 · 제외 ${htmlLimited ? blocks[v.id].filter(b => !htmlPilotBlock(b)).length : 0}개` : "범위를 불러오는 중"}</p>)}{!htmlLimited && <p className="mt-2 text-xs text-amber-800">HTML 전체를 선택했습니다. 공고군의 범위를 넘어 입력 예산을 초과할 수 있습니다.</p>}</div>}
      {selectedPDFs.map(v => <div key={v.id} className="rounded border p-3 text-sm"><h3 className="font-medium">{v.source.title} · PDF 추출 범위</h3><p className="my-1 text-xs text-slate-500">실제 추출 위치로 선택합니다. 표를 선택하면 그 표의 제목·열·행을 함께 전달합니다. 인쇄 4쪽의 최초입주 열이 있는 단지 표를 기본 선택합니다.</p>{!blocks[v.id] ? <p>원문 위치를 불러오는 중입니다.</p> : <div className="max-h-48 space-y-1 overflow-auto">{[...new Map(blocks[v.id].map(b => [groupKey(b), b])).entries()].map(([key, b]) => <label key={key} className="block"><input type="checkbox" checked={(pdfGroups[v.id] || []).includes(key)} onChange={e => setPdfGroups({ ...pdfGroups, [v.id]: e.target.checked ? [...(pdfGroups[v.id] || []), key] : (pdfGroups[v.id] || []).filter(item => item !== key) })} /> {groupLabel(b)} · {blocks[v.id].filter(item => groupKey(item) === key).slice(0, 4).map(item => item.text).join(" / ").slice(0, 80)}</label>)}</div>}</div>)}
      <div className="space-y-2"><h3 className="font-medium">업무 질문 (CQ)</h3>{cqs.map((q, i) => <label key={q.id} className="block text-xs">{q.id}<textarea className={field} value={q.question} onChange={e => setCqs(cqs.map((item, j) => i === j ? { ...item, question: e.target.value } : item))} /></label>)}<p className="text-xs text-slate-500">CQ는 범위 선정 이력에 보존합니다. 사실 추출 프롬프트에 질문·정답은 넣지 않습니다.</p></div>
      <p className="text-xs text-slate-500">명시 필드와 지원 PDF 표는 코드로 매핑합니다. 단지 이미지 설명은 세대수·주택유형을 대상으로 묶음당 모델을 1회 호출합니다. CSV를 추출 자료에서 해제해도 등록부 연결 문맥은 유지됩니다. 자동 평가·재작성은 수행하지 않습니다.</p><button className={button} disabled={busy || running || !ontologies.length || (!general && !registry) || !selectedVersions.length || (general && (!localIds.length || !blockIds.length)) || !cqs.some(q => q.question.trim()) || selectedDocuments.some(v => !blocks[v.id]) || (!general && selectedPDFs.some(v => !pdfGroups[v.id]?.length))} onClick={() => start()}>개체·사실 추출 시작</button>
    </fieldset></details>
    {run && <section role="status" className="rounded border bg-white p-4 text-sm"><h3 className="font-semibold">추출 작업 · {labels[run.status] || run.status}</h3><p>모델 호출 {run.metrics?.llm_calls ?? 0}회 / 예정 {run.planned_llm_calls ?? run.metrics?.planned_llm_calls ?? "미기록"}회 · 모델 시간 {(run.metrics?.model_total_s ?? 0).toFixed(1)}초 · 전체 {(run.metrics?.elapsed_s ?? 0).toFixed(1)}초</p><p className="mt-1">처리한 원문 구간 {(run.processed_block_ids?.length ?? new Set(run.units.filter(u => u.status === "succeeded").flatMap(u => u.block_ids || [])).size)}개 / 선택 {new Set(run.units.flatMap(u => u.block_ids || [])).size}개 · 후보로 변환하지 못한 레코드 {run.invalid_record_count ?? run.units.reduce((count, u) => count + (u.invalid_records?.length || 0), 0)}개 · 실행 제외 {run.excluded_blocks?.length ?? 0}개</p>{run.candidate_counts && <p className="mt-1">자동 후보 {run.candidate_counts.automatic ?? "미기록"}개 · 수동 추가 {run.candidate_counts.manual ?? 0}개 · 형식·참조 검사 통과 {run.candidate_counts.valid}개 · 오류 {run.candidate_counts.invalid}개 · 미해결 {run.candidate_counts.unresolved}개</p>}{!!run.unsupported_slots?.length && <p className="text-amber-800">이번 추출에서 미지원인 다중값 속성: {run.unsupported_slots.map(slotName).join(", ")}</p>}{run.counts && <p className="mt-1">{Object.entries(run.counts).map(([key, value]) => `${labels[key] || key} ${value}`).join(" · ")}</p>}<ul className="my-2 max-h-48 space-y-1 overflow-auto">{run.units.map(u => <li key={u.id}>{labels[u.stage || u.kind || ""] || u.stage || u.kind || u.id} · {labels[u.status] || u.status}{u.error && <p className="text-red-700">{u.error}</p>}{!!u.invalid_records?.length && <details><summary>변환하지 못한 출력 {u.invalid_records.length}개</summary><pre className="max-h-48 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(u.invalid_records, null, 2)}</pre></details>}{u.coverage && <details><summary>입력 단위/필드 {u.coverage.length}개 · 미처리/검토 필요 {u.coverage.filter(c => c.status !== "extracted").length}개</summary><p className="text-xs">설명문 처리됨은 사실을 빠짐없이 찾았다는 뜻이 아닙니다.</p>{u.coverage.map((c, i) => <p key={i} className="break-all text-xs">{c.id} · {c.status} {c.reason}</p>)}</details>}</li>)}</ul><details className="my-2"><summary>고정 입력 버전</summary><p>온톨로지: {run.ontology_version_id}</p><p>자료: {run.input_version_ids?.join(", ")}</p><p>파싱: {Object.values(run.parse_run_ids || {}).join(", ")}</p></details>{running && <button className="underline disabled:opacity-40" disabled={busy || run.status === "cancel_requested"} onClick={async () => { setBusy(true); try { await request(`/runs/${run.id}/cancel`, { method: "POST" }); setRun(await request<Run>(`/runs/${run.id}`)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>현재 호출 종료 후 중단</button>}{["failed", "cancelled", "partial"].includes(run.status) && <button className={button} disabled={busy} onClick={() => start(true)}>성공 단위 재사용 · 실패 단위 재시도</button>}</section>}
    <div className="flex items-end gap-2 rounded border bg-white p-4"><label className="flex-1 text-sm">저장된 추출 검토 묶음<select className={field} value={result?.changeset_id || ""} disabled={busy || running} onChange={e => openChange(e.target.value)}><option value="">묶음 선택</option>{changesets.map(c => <option key={c.id} value={c.id}>{c.created_at ? new Date(c.created_at).toLocaleString("ko-KR") : c.id} · {c.id.slice(0, 8)}</option>)}</select></label><button className={button} disabled={busy || running} onClick={async () => { setBusy(true); setError(""); try { await refresh(); if (result) await loadResults(result.changeset_id); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>새로고침</button></div>
    {result && <><section className="rounded border bg-white p-4"><h2 className="font-semibold">후보 {result.items.length}개 · 형식·참조 오류 {result.items.filter(c => c.validation_errors?.length).length}개 · 미해결 {result.unresolved_count}개</h2><p className="mt-1 text-xs text-slate-500">개체 연결을 먼저 또는 사실과 함께 수락하세요. 연결 해제는 직접 의존 사실을 재검토 상태로 돌립니다.</p><div className="my-3 grid gap-2 md:grid-cols-2"><label className="text-sm">결정자<input className={field} value={actor} onChange={e => setActor(e.target.value)} /></label><label className="text-sm">짧은 판단 사유 (연결 해제 시 필수)<input className={field} value={reason} onChange={e => setReason(e.target.value)} /></label></div><div className="flex flex-wrap items-center gap-2"><label className="text-sm"><input type="checkbox" checked={!!result.items.length && selectedIds.length === result.items.length} onChange={e => setSelectedIds(e.target.checked ? result.items.map(c => c.id) : [])} /> 전체 선택</label>{([['accept', '선택 수락'], ['defer', '선택 보류'], ['reject', '선택 기각']] as const).map(([action, name]) => <button key={action} className={button} disabled={busy || !actor.trim() || !selectedIds.length} onClick={() => decide(action, selectedIds)}>{name}</button>)}</div><details className="mt-3 text-sm"><summary>결정 이력 {currentChange?.decisions?.length || 0}건</summary><ul className="mt-2 max-h-48 space-y-2 overflow-auto">{currentChange?.decisions?.map(d => <li key={d.id}>{d.candidate_id} · {labels[d.action] || d.action} · {d.actor} · {new Date(d.created_at).toLocaleString("ko-KR")}<p>{d.reason || "사유 미기록"}</p></li>)}</ul></details></section>
      <div className="grid gap-4 xl:grid-cols-2"><section className="space-y-3 rounded border bg-white p-4"><h3 className="font-semibold">개체 연결 · 사실 · 관계</h3><div className="max-h-72 space-y-2 overflow-auto">{[...result.items].sort((a, b) => (a.kind === "entity_link" ? a.id : a.subject_link_id).localeCompare(b.kind === "entity_link" ? b.id : b.subject_link_id)).map(c => <div key={c.id} className={`flex items-center gap-2 rounded border p-2 ${draft?.id === c.id ? "border-blue-500 bg-blue-50" : ""}`}><input type="checkbox" aria-label={`${title(c)} 일괄 선택`} checked={selectedIds.includes(c.id)} onChange={e => setSelectedIds(e.target.checked ? [...selectedIds, c.id] : selectedIds.filter(id => id !== c.id))} /><button disabled={busy} className="flex-1 text-left text-sm" onClick={() => { setDraft(c); setEvidence(null); }}>{labels[c.kind]} · {c.kind === "assertion" ? `${links.find(l => l.id === c.subject_link_id)?.mention || "미연결"} · ${slotName(c.predicate_id)}: ${String(c.value ?? c.raw_value ?? "")}` : title(c)}<span className="ml-2 text-xs text-slate-500">{labels[c.review_status] || c.review_status}{c.usage_restrictions?.length ? " · 사용 제한 있음" : ""}{c.validation_errors?.length ? ` · 오류 ${c.validation_errors.length}` : ""}</span></button></div>)}</div>
      {draft && <fieldset disabled={busy} className="space-y-3 border-t pt-3"><legend className="pt-3 text-sm font-semibold">후보 수정 · {draft.id}</legend>{draft.validation_errors && draft.validation_errors.length > 0 && <pre className="whitespace-pre-wrap text-xs text-amber-800">{JSON.stringify(draft.validation_errors, null, 2)}</pre>}
        {draft.kind === "entity_link" ? <><label className="block text-sm">원문 표기<input className={field} value={draft.mention} onChange={e => setDraft({ ...draft, mention: e.target.value })} /></label><label className="block text-sm">근거 ID (한 줄에 하나)<textarea className={field} value={(draft.evidence_ids || []).join("\n")} onChange={e => setDraft({ ...draft, evidence_ids: e.target.value.split("\n") })} /></label><p className="text-sm">연결 방법: {labels[draft.method] || draft.method}<br />개념: {draft.concept_id}</p><label className="block text-sm">연결 대상<select className={field} value={draft.target_entity_id || ""} onChange={e => setDraft({ ...draft, target_entity_id: e.target.value || null })}><option value="">미연결</option>{entities.filter(entity => entity.concept_id === draft.concept_id).map(entity => <option key={entity.id} value={entity.id}>{entity.name} · {entity.official_id || entity.id} {draft.candidate_entity_ids?.includes(entity.id) ? "· 제안 대상" : ""}</option>)}</select></label><button className="rounded border border-red-300 px-3 py-2 text-sm text-red-700 disabled:opacity-40" disabled={!actor.trim() || !reason.trim()} onClick={() => decide("unlink", [draft.id])}>연결 해제</button></> : <>
          <p className="text-sm">속성·관계: {slotName(draft.predicate_id)} ({draft.predicate_id})</p><label className="block text-sm">주체 원문 연결<select className={field} value={draft.subject_link_id || ""} onChange={e => updateAssertion({ subject_link_id: e.target.value })}><option value="">선택</option>{links.map(link => <option key={link.id} value={link.id}>{link.mention} · {link.id.slice(0, 8)}</option>)}</select></label>
          <label className="block text-sm">관계 대상 원문 연결 (속성은 비움)<select className={field} value={draft.object_link_id || ""} onChange={e => updateAssertion({ object_link_id: e.target.value || null, value: e.target.value ? null : draft.value })}><option value="">선택</option>{links.map(link => <option key={link.id} value={link.id}>{link.mention} · {link.id.slice(0, 8)}</option>)}</select></label>{!(draft.object_link_id || draft.object_entity_id) && <><label className="block text-sm">값 유형<select className={field} value={typeof draft.value === "number" ? "number" : typeof draft.value === "boolean" ? "boolean" : "string"} onChange={e => updateAssertion({ value: e.target.value === "number" ? 0 : e.target.value === "boolean" ? false : String(draft.value ?? "") })}><option value="string">문자열 / 월 정밀도</option><option value="number">수치</option><option value="boolean">참/거짓</option></select></label><label className="block text-sm">정규화 값{typeof draft.value === "boolean" ? <select className={field} value={String(draft.value)} onChange={e => updateAssertion({ value: e.target.value === "true" })}><option value="true">참</option><option value="false">거짓</option></select> : typeof draft.value === "number" ? <input type="number" step="any" className={field} value={draft.value} onChange={e => { if (e.target.value !== "" && Number.isFinite(e.target.valueAsNumber)) updateAssertion({ value: e.target.valueAsNumber }); }} /> : <textarea className={field} value={String(draft.value ?? "")} onChange={e => updateAssertion({ value: e.target.value })} />}</label></>}
          <label className="block text-sm">원문 값<input className={field} value={draft.raw_value || ""} onChange={e => updateAssertion({ raw_value: e.target.value })} /></label><label className="block text-sm">원문 단위<input className={field} value={draft.unit || ""} onChange={e => updateAssertion({ unit: e.target.value || null })} /></label>{([['conditions', '조건'], ['exceptions', '예외']] as const).map(([key, name]) => <label key={key} className="block text-sm">{name} (한 줄에 하나)<textarea className={field} value={(draft[key] || []).join("\n")} onChange={e => updateAssertion({ [key]: e.target.value.split("\n") })} /></label>)}
          <div className="space-y-2"><h4 className="text-sm font-medium">날짜와 역할</h4>{(draft.dates || []).map((date, i) => <div key={i} className="grid grid-cols-3 gap-2"><label className="text-xs">역할<input className={field} value={date.role || ""} onChange={e => updateAssertion({ dates: draft.dates.map((item, j) => j === i ? { ...item, role: e.target.value } : item) })} /></label><label className="text-xs">날짜 값<input className={field} value={date.value || ""} onChange={e => updateAssertion({ dates: draft.dates.map((item, j) => j === i ? { ...item, value: e.target.value } : item) })} /></label><label className="text-xs">정밀도<input className={field} value={date.precision || ""} onChange={e => updateAssertion({ dates: draft.dates.map((item, j) => j === i ? { ...item, precision: e.target.value } : item) })} /></label><button className="text-left text-xs underline" onClick={() => updateAssertion({ dates: draft.dates.filter((_, j) => j !== i) })}>날짜 삭제</button></div>)}<button className="text-sm underline" onClick={() => updateAssertion({ dates: [...(draft.dates || []), { role: "", value: "", precision: "" }] })}>날짜 추가</button></div>
          <label className="block text-sm">근거 ID (한 줄에 하나)<textarea className={field} value={(draft.evidence_ids || []).join("\n")} onChange={e => updateAssertion({ evidence_ids: e.target.value.split("\n") })} /></label><details className="text-sm"><summary>필드별 근거 연결</summary>{Object.entries(draft.field_evidence || {}).map(([key, ids]) => <label key={key} className="mt-2 block text-xs">{key}<textarea className={field} value={ids.join("\n")} onChange={e => updateAssertion({ field_evidence: { ...draft.field_evidence, [key]: lines(e.target.value) } })} /></label>)}</details><p className="text-xs text-slate-500">의존 연결: {draft.link_dependencies?.map(link => `${link.link_id} (revision ${link.revision})`).join(", ") || "없음"}</p>
        </>}
        <div className="space-y-2"><h4 className="text-sm font-medium">범위·출처 맥락</h4>{Object.entries(draft.scope || {}).filter(([key]) => key !== "description").map(([key, value]) => <p key={key} className="break-all text-xs text-slate-500">{key}: {typeof value === "string" ? value : JSON.stringify(value)}</p>)}<label className="block text-xs">범위 설명<input className={field} value={String(draft.scope?.description || "")} onChange={e => setDraft({ ...draft, scope: { ...draft.scope, description: e.target.value } })} /></label></div>
        <button className={button} disabled={!actor.trim()} onClick={() => decide("modify", [draft.id])}>수정 저장 · 수락 가능 여부 확인</button><p className="text-xs text-slate-500">검사 오류가 남으면 검토 전 상태로 보존됩니다. 정렬 위치나 ID를 임의로 확정하지 않습니다.</p>
      </fieldset>}</section>
      <section className="space-y-3 rounded border bg-white p-4"><h3 className="font-semibold">근거 원문 · 위치</h3><label className="block text-sm">선택 근거의 역할<select className={field} value={evidenceRole} onChange={e => setEvidenceRole(e.target.value)}>{["value", "object", "scope", "conditions", "exceptions"].map(v => <option key={v}>{v}</option>)}</select></label><label className="block text-sm">고정 원문에서 근거 선택<select className={field} value="" disabled={!draft} onChange={e => { const b = run?.frozen_blocks?.find(b => b.id === e.target.value); if (b) chooseEvidence(b); }}><option value="">셀/문단 선택</option>{run?.frozen_blocks?.map(b => <option key={b.id} value={b.id}>{b.locator.format as string} · 행 {String(b.locator.row ?? "-")} · {b.text.slice(0, 90)}</option>)}</select></label>{!draft ? <p className="text-sm text-slate-500">후보를 선택하세요.</p> : <div className="flex flex-wrap gap-2">{(draft.evidence_ids || []).filter(Boolean).map(id => <button key={id} className="rounded border px-2 py-1 text-xs" disabled={busy} onClick={async () => { setBusy(true); setError(""); try { const found = await request<Evidence>(`/evidence/${id}`); setEvidence(found); if (found.block.locator.format === "pdf" && !blocks[found.version.id]) { const sourceBlocks = await request<{ items: Block[] }>(`/sources/${found.source.id}/versions/${found.version.id}/blocks`); setBlocks(previous => ({ ...previous, [found.version.id]: sourceBlocks.items })); } } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>{id}</button>)}</div>}{evidence && <><p className="text-sm font-medium">{evidence.source.title}</p>{!!evidence.usage_restrictions?.length && <p className="text-sm text-amber-800">사용 제한된 근거입니다. 지식 버전 탭에서 상태·사유를 확인하세요.</p>}<p className="text-xs">정렬: {labels[evidence.evidence.alignment_status || ""] || evidence.evidence.alignment_status || "미기록"} · 위치 {evidence.evidence.start_char ?? "없음"}–{evidence.evidence.end_char ?? "없음"}</p><blockquote className="whitespace-pre-wrap border-l-4 border-blue-300 bg-blue-50 p-3 text-sm">{evidence.evidence.quote}</blockquote><pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">{evidence.block.text}</pre>{evidenceRow.length > 0 && <div className="rounded border p-3 text-sm"><h4 className="font-medium">같은 표의 열 제목·선택 행</h4><p className="mb-2 text-xs text-slate-500">원문 셀 문맥입니다. 새 근거나 연결 승인을 자동으로 생성하지 않습니다.</p><ul className="space-y-1">{evidenceRow.map(b => <li key={b.id} className={b.id === evidence.block.id ? "bg-blue-50 p-1" : ""}>행 {String(b.locator.row)} · 열 {String(b.locator.column)}: {b.text} <button className="underline" disabled={!draft || busy} onClick={() => chooseEvidence(b)}>이 셀을 근거로 선택</button></li>)}</ul></div>}<details className="text-xs" open><summary>페이지·표·문단 위치</summary><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify(evidence.block.locator, null, 2)}</pre></details></>}</section></div>
    </>}
    {result && <details className="rounded border bg-white p-4"><summary>원문에서 누락 사실·관계 추가</summary><p className="my-2 text-xs">수동 후보로 저장하고 별도로 검토합니다. 원래 AI 출력은 바뀌지 않습니다.</p><div className="space-y-2"><label className="block text-sm">주체 연결<select className={field} value={manual.subject_link_id} onChange={e => setManual({ ...manual, subject_link_id: e.target.value })}><option value="">선택</option>{links.map(l => <option key={l.id} value={l.id}>{l.mention} · {l.id.slice(0, 8)}</option>)}</select></label><label className="block text-sm">속성·관계<select className={field} value={manual.predicate_id} onChange={e => setManual({ ...manual, predicate_id: e.target.value, object_link_id: "" })}><option value="">선택</option>{definitions.filter(d => ["attribute", "relation"].includes(d.kind) && (d.kind === "relation" || !d.multivalued)).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>{definitions.find(d => d.id === manual.predicate_id)?.kind === "relation" && <label className="block text-sm">관계 대상<select className={field} value={manual.object_link_id} onChange={e => setManual({ ...manual, object_link_id: e.target.value })}><option value="">선택</option>{links.map(l => <option key={l.id} value={l.id}>{l.mention}</option>)}</select></label>}<label className="block text-sm">근거 원문<select className={field} value={manual.block_id} onChange={e => { const b = run?.frozen_blocks?.find(b => b.id === e.target.value); setManual({ ...manual, block_id: e.target.value, quote: b?.text || "", raw_value: b?.text || "" }); }}><option value="">선택</option>{run?.frozen_blocks?.map(b => <option key={b.id} value={b.id}>{b.locator.format as string} · 행 {String(b.locator.row ?? "-")} · {b.text.slice(0, 100)}</option>)}</select></label><label className="block text-sm">인용 구간 (원문 그대로)<textarea className={field} value={manual.quote} onChange={e => setManual({ ...manual, quote: e.target.value })} /></label><label className="block text-sm">원문 값 (숫자·월은 자동 정규화)<input className={field} value={manual.raw_value} onChange={e => setManual({ ...manual, raw_value: e.target.value })} /></label><label className="block text-sm">범위 설명<input className={field} value={manual.scope} onChange={e => setManual({ ...manual, scope: e.target.value })} /></label><button className={button} disabled={busy || running || !actor.trim() || !manual.subject_link_id || !manual.predicate_id || !manual.block_id} onClick={addManual}>수동 후보 추가</button></div></details>}
    <details className="rounded border bg-white p-4"><summary>일반 문서의 로컬 개체·입력 범위</summary>
      <label className="block"><input type="checkbox" checked={general} disabled={busy || running} onChange={e => setGeneral(e.target.checked)} /> 단지 등록부 없이 선택한 로컬 개체·블록으로 추출</label>
      <p className="text-xs">공식 ID가 없는 문서 내 대상을 등록합니다. 등록 후에도 연결·사실의 수락과 지식 버전 저장은 별도로 진행합니다.</p>
      <label className="block">결정자<input className={field} value={actor} onChange={e => setActor(e.target.value)} /></label><label className="block">등록 사유<input className={field} value={reason} onChange={e => setReason(e.target.value)} /></label>
      <label className="block">개념<select className={field} value={localDraft.concept_id} onChange={e => setLocalDraft({ ...localDraft, concept_id: e.target.value })}><option value="">위에서 온톨로지를 선택하세요</option>{localConcepts.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label className="block">원문 표기<input className={field} value={localDraft.name} onChange={e => setLocalDraft({ ...localDraft, name: e.target.value })} /></label>
      <label className="block">식별 근거<select className={field} value={localDraft.block_id} onChange={e => setLocalDraft({ ...localDraft, block_id: e.target.value })}><option value="">선택 자료의 원문 블록 선택</option>{selectedDocuments.flatMap(v => (blocks[v.id] || []).map(b => <option key={b.id} value={b.id}>{b.text.slice(0,100)}</option>))}</select></label>
      <button className={button} disabled={busy || running || !effectiveOntologyId || !localDraft.concept_id || !localDraft.name.trim() || !localDraft.block_id || !actor.trim() || !reason.trim()} onClick={registerLocal}>근거 있는 로컬 개체 등록</button>
      <fieldset className="my-2"><legend>이번 추출에 사용할 로컬 개체</legend>{entities.filter(e => e.namespace.startsWith("local:")).map(e => <label key={e.id} className="block text-sm"><input type="checkbox" checked={localIds.includes(e.id)} onChange={v => setLocalIds(ids => v.target.checked ? [...ids, e.id] : ids.filter(id => id !== e.id))} /> {e.name} · {e.id.slice(0,8)}</label>)}</fieldset>
      {general && <fieldset className="max-h-72 overflow-auto"><legend>고정할 블록 · 표는 해당 행과 열 제목을 함께 선택</legend>{selectedDocuments.flatMap(v => (blocks[v.id] || []).map(b => <label key={b.id} className="block text-sm"><input type="checkbox" checked={blockIds.includes(b.id)} onChange={e => setBlockIds(ids => e.target.checked ? [...ids, b.id] : ids.filter(id => id !== b.id))} /> {b.text.slice(0,160)}</label>))}</fieldset>}
    </details>
    <section className="rounded border bg-white p-4"><h3 className="font-semibold">등록 개체</h3><label className="mt-2 block text-sm">개체 선택<select className={field} disabled={busy} value={entityDetail?.entity.id || ""} onChange={async e => { if (!e.target.value) { setEntityDetail(null); return; } setBusy(true); try { setEntityDetail(await request<EntityDetail>(`/entities/${e.target.value}`)); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}><option value="">선택</option>{entities.map(entity => <option key={entity.id} value={entity.id}>{entity.name} · {entity.official_id || entity.id}</option>)}</select></label>{entityDetail && <div className="mt-3 space-y-2 text-sm"><p>{entityDetail.entity.name} · {entityDetail.entity.namespace} · {entityDetail.entity.official_id || "공식 ID 미확정"}</p><p>검토된 별칭: {entityDetail.aliases.map(alias => alias.mention).join(", ") || "없음"}</p><p>연결 후보 {entityDetail.links.length}개 · 사실·관계 후보 {entityDetail.assertions.length}개</p><ul className="max-h-48 space-y-1 overflow-auto">{entityDetail.assertions.map(assertion => <li key={assertion.id}>{title(assertion)} · {labels[assertion.review_status] || assertion.review_status}</li>)}</ul></div>}</section>
  </section>;
}

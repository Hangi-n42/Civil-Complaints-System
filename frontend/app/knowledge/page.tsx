"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import AppSidebar from "@/components/AppSidebar";
import KnowledgeOntology from "@/components/KnowledgeOntology";
import KnowledgeExtraction from "@/components/KnowledgeExtraction";
import KnowledgeSearch from "@/components/KnowledgeSearch";
import KnowledgeSnapshots from "@/components/KnowledgeSnapshots";
import { API_BASE_URL } from "@/lib/api";

type Version = { id: string; format: string; processing_status?: string; sha256: string; latest_parse_run_id?: string; verified_at?: string; acquired_at?: string; dates?: {role: string; value: string}[] };
type Source = { id: string; title: string; publisher: string; source_url?: string; rights: { status: string; note?: string } };
type SourceItem = { source: Source; versions: Version[] };
type Block = { id: string; text: string; locator: Record<string, unknown>; evidence_id: string };
type Run = { id: string; status: string; units: { id: string; source_version_id: string; status: string; error?: string }[]; metrics?: { elapsed_s?: number }; };
type Evidence = { usage_restrictions?: { state: string }[]; evidence: { quote: string; start_char: number; end_char: number }; block: Block; version: Version; source: Source };
const endpoint = (path: string) => `${API_BASE_URL}/api/v1/knowledge${path}`;
const labels: Record<string, string> = { registered: "등록됨", parsed: "추출 완료", failed: "실패", partial: "일부 완료", queued: "대기", running: "처리 중", succeeded: "완료", cancel_requested: "취소 요청됨", cancelled: "취소됨", unknown: "미확인", local_only: "로컬 사용", allowed: "사용 허용", restricted: "제한됨" };
const inputClass = "w-full rounded border border-slate-300 px-3 py-2 text-sm";
const buttonClass = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), init);
  const result = await response.json();
  if (!response.ok || result.success === false) {
    if (result.error?.code === "KNOWLEDGE_DISABLED") throw new Error("회사 지식 기능이 꺼져 있습니다. 로컬 설정에서 KNOWLEDGE_ENABLED=true로 지정한 뒤 백엔드를 재시작하세요.");
    throw new Error(result.error?.message || result.detail || `요청 실패 (${response.status})`);
  }
  return result.data as T;
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<"sources" | "ontology" | "extraction" | "snapshots" | "search">("sources");
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [selected, setSelected] = useState<{ source: Source; version: Version } | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [existingSource, setExistingSource] = useState("");
  const [format, setFormat] = useState("");
  const [loading, setLoading] = useState(true);

  const refreshSources = useCallback(async () => {
    const data = await request<{ items: SourceItem[] }>("/sources");
    setSources(data.items);
  }, []);
  useEffect(() => { refreshSources().catch(e => setError(String(e.message))).finally(() => setLoading(false)); }, [refreshSources]);

  const openVersion = useCallback(async (source: Source, version: Version) => {
    setSelected({ source, version }); setEvidence(null); setBlocks([]); setError("");
    try {
      const data = await request<{ items: Block[] }>(`/sources/${source.id}/versions/${version.id}/blocks`);
      setBlocks(data.items);
    } catch (e) { setError((e as Error).message); }
  }, []);

  const running = !!run && ["queued", "running", "cancel_requested"].includes(run.status);
  useEffect(() => {
    if (!running || !run) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const next = await request<Run>(`/runs/${run.id}`);
        if (disposed) return;
        setRun(next);
        if (!["queued", "running", "cancel_requested"].includes(next.status)) {
          await refreshSources();
          if (selected) await openVersion(selected.source, selected.version);
        }
      } catch (e) { if (!disposed) setError((e as Error).message); }
    }, 1000);
    return () => { disposed = true; clearInterval(timer); };
  }, [run, running, selected, refreshSources, openVersion]);

  async function selectVersion(source: Source, version: Version) {
    setBusy(true);
    setRun(null);
    try {
      await openVersion(source, version);
      if (version.latest_parse_run_id) setRun(await request<Run>(`/runs/${version.latest_parse_run_id}`));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!file) return;
    const form = new FormData(event.currentTarget);
    let selected_scope: Record<string, unknown> = {};
    if (format === "pdf") {
      if (form.get("pageEnd")) selected_scope.physical_pages_inclusive = [Number(form.get("pageStart") || 1), Number(form.get("pageEnd"))];
      selected_scope.two_up = form.get("twoUp") === "on";
    } else if (format === "csv" && form.get("codes")) {
      selected_scope.knowledge_input_complex_codes = String(form.get("codes")).split(",").map(x => x.trim()).filter(Boolean);
    } else if (format === "html") {
      selected_scope = { selector: String(form.get("selector") || "body") };
    } else if (format === "hwpx" && form.get("rental") === "on") {
      selected_scope = { include: "임대주택 Q1~Q16", metadata_include: { hwpx_member: "Contents/section0.xml", element_preorder_index_zero_based: 86, quote: "2026.03 기준" } };
    }
    const metadata = {
      source_id: existingSource || undefined,
      title: String(form.get("title")), publisher: String(form.get("publisher")),
      namespace: "local-document", external_id: String(form.get("externalId") || file.name),
      source_url: String(form.get("url") || "") || null,
      rights: { status: String(form.get("rights")), note: String(form.get("rightsNote") || "") },
      selected_scope,
    };
    const body = new FormData(); body.append("file", file); body.append("metadata", JSON.stringify(metadata));
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<{ disposition: string }>("/sources", { method: "POST", body });
      setNotice(result.disposition === "duplicate" ? "동일한 원문이 이미 등록되어 기존 버전을 사용합니다." : "자료를 등록했습니다. 목록에서 버전을 선택해 원문을 추출하세요.");
      await refreshSources();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function startParse(retry = false) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const data = await request<{ run_id: string }>("/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(retry && run ? { kind: "parse", retry_of_run_id: run.id, unit_ids: run.units.filter(u => u.source_version_id === selected.version.id && ["failed", "cancelled"].includes(u.status)).map(u => u.id) } : { kind: "parse", source_version_ids: [selected.version.id] }) });
      const next = await request<Run>(`/runs/${data.run_id}`);
      setRun(next);
      if (!["queued", "running", "cancel_requested"].includes(next.status)) { await refreshSources(); await openVersion(selected.source, selected.version); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return <div className="flex min-h-screen bg-slate-50 text-slate-900">
    <AppSidebar activeMenu="knowledge" />
    <main className="min-w-0 flex-1 space-y-5 p-6">
      <header><h1 className="text-2xl font-bold">회사 지식 워크벤치</h1><p className="mt-1 text-sm text-slate-600">원문과 추출 후보를 검토하고, 선택한 지식 버전을 활성화하여 조회합니다.</p></header>
      <nav aria-label="회사 지식 작업" className="flex gap-2"><button aria-pressed={tab === "sources"} className={tab === "sources" ? buttonClass : "rounded border px-3 py-2 text-sm"} onClick={() => setTab("sources")}>자료</button><button aria-pressed={tab === "ontology"} className={tab === "ontology" ? buttonClass : "rounded border px-3 py-2 text-sm"} onClick={() => setTab("ontology")}>온톨로지 초안</button><button aria-pressed={tab === "extraction"} className={tab === "extraction" ? buttonClass : "rounded border px-3 py-2 text-sm"} onClick={() => setTab("extraction")}>개체·사실</button><button aria-pressed={tab === "snapshots"} className={tab === "snapshots" ? buttonClass : "rounded border px-3 py-2 text-sm"} onClick={() => setTab("snapshots")}>지식 버전</button><button aria-pressed={tab === "search"} className={tab === "search" ? buttonClass : "rounded border px-3 py-2 text-sm"} onClick={() => setTab("search")}>지식 검색</button></nav>
      <div hidden={tab !== "search"}><KnowledgeSearch request={request} visible={tab === "search"} /></div>
      <div hidden={tab !== "snapshots"}><KnowledgeSnapshots request={request} visible={tab === "snapshots"} /></div>
      <div hidden={tab !== "extraction"}><KnowledgeExtraction request={request} sources={sources} /></div>
      <div hidden={tab !== "ontology"}><KnowledgeOntology request={request} sources={sources} /></div>
      <div hidden={tab !== "sources"} className="space-y-5">
      {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded bg-blue-50 p-3 text-blue-800">{notice}</p>}
      <details className="rounded border bg-white p-4" open={sources.length === 0}>
        <summary className="cursor-pointer font-semibold">새 자료 / 후속 버전 등록</summary>
        <form onSubmit={register} className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-sm">자료 파일<input required type="file" accept=".csv,.html,.pdf,.hwpx" className={inputClass} onChange={e => { const f = e.target.files?.[0] || null; setFile(f); setFormat(f?.name.split(".").pop()?.toLowerCase() || ""); }} /></label>
          <label className="text-sm">등록 대상<select value={existingSource} onChange={e => setExistingSource(e.target.value)} className={inputClass}><option value="">새 자료</option>{sources.map(s => <option key={s.source.id} value={s.source.id}>{s.source.title} · 후속 버전</option>)}</select></label>
          <label className="text-sm">자료 이름<input name="title" required className={inputClass} /></label>
          <label className="text-sm">발행기관<input name="publisher" required className={inputClass} /></label>
          <label className="text-sm">문서 식별자 (없으면 파일명)<input name="externalId" className={inputClass} /></label>
          <label className="text-sm">공식 출처 URL<input name="url" type="url" className={inputClass} /></label>
          <label className="text-sm">이용 조건<select name="rights" className={inputClass}><option value="unknown">미확인</option><option value="local_only">로컬 사용</option><option value="allowed">사용 허용</option><option value="restricted">제한됨</option></select></label>
          <label className="text-sm">이용 조건 메모<input name="rightsNote" className={inputClass} /></label>
          {format === "pdf" && <fieldset className="flex flex-wrap items-center gap-3 md:col-span-2"><legend className="text-sm">추출 범위 · 물리 페이지 (종료를 비우면 전체)</legend><label>시작 <input aria-label="시작 페이지" name="pageStart" type="number" min="1" defaultValue="1" className="w-20 rounded border p-2" /></label><label>종료 <input aria-label="종료 페이지" name="pageEnd" type="number" min="1" className="w-20 rounded border p-2" /></label><label><input name="twoUp" type="checkbox" /> 한 페이지에 좌우 두 면</label></fieldset>}
          {format === "csv" && <label className="text-sm md:col-span-2">대상 단지코드 (쉼표 구분, 비우면 전체)<input name="codes" className={inputClass} /></label>}
          {format === "html" && <label className="text-sm md:col-span-2">본문 영역 (CSS 선택자)<input name="selector" defaultValue="#cntntsView" className={inputClass} /></label>}
          {format === "hwpx" && <label className="text-sm md:col-span-2"><input name="rental" type="checkbox" /> LH 2026 Q&A의 표지 기준월·임대주택 Q1~Q16만 추출</label>}
          <button className={buttonClass} disabled={busy || !file}>자료 등록</button>
        </form>
      </details>
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded border bg-white p-4"><h2 className="mb-3 font-semibold">등록 자료</h2>{loading ? <p>자료를 불러오는 중입니다.</p> : sources.length === 0 ? <p className="text-sm text-slate-500">등록된 자료가 없습니다.</p> : sources.map(item => <article key={item.source.id} className="mb-3 border-b pb-3"><h3 className="font-medium">{item.source.title}</h3><p className="text-xs text-slate-500">{item.source.publisher} · 이용 조건: {labels[item.source.rights.status] || item.source.rights.status}</p>{item.versions.map(v => <button key={v.id} disabled={running || busy} onClick={() => selectVersion(item.source, v)} className={`mt-2 block w-full rounded border p-2 text-left text-sm ${selected?.version.id === v.id ? "border-blue-600 bg-blue-50" : "border-slate-200"}`}>{v.format.toUpperCase()} · {labels[v.processing_status || "registered"] || v.processing_status} · {v.sha256.slice(0, 12)}</button>)}</article>)}</section>
        <section className="rounded border bg-white p-4"><h2 className="mb-3 font-semibold">원문 위치 확인</h2>{!selected ? <p className="text-sm text-slate-500">자료 버전을 선택하세요.</p> : <>
          <p className="mb-3 text-sm">{selected.source.title}<br />원문 확인: {selected.version.verified_at ? new Date(selected.version.verified_at).toLocaleString("ko-KR") : "미기록"}<br />원문 취득: {selected.version.acquired_at || "최초 취득시각 미기록"}</p>
          <div className="flex flex-wrap gap-2"><button onClick={() => startParse()} disabled={busy || running} className={buttonClass}>원문 추출</button><a href={endpoint(`/sources/${selected.source.id}/versions/${selected.version.id}/raw`)} target="_blank" rel="noreferrer" className="rounded border px-3 py-2 text-sm">원본 열기 / 다운로드</a></div>
          {run && <div className="my-3 rounded bg-slate-100 p-3 text-sm" role="status"><p>작업: {labels[run.status] || run.status}</p><p>작업 전체 단위 {run.units.filter(u => u.status === "succeeded").length}/{run.units.length} 완료</p>{run.units.filter(u => u.error).map(u => <p key={u.id} className="text-red-700">{u.id}: {u.error}</p>)}{running && <button className="mt-2 underline" onClick={async () => { try { await request(`/runs/${run.id}/cancel`, { method: "POST" }); setRun(await request<Run>(`/runs/${run.id}`)); } catch (e) { setError((e as Error).message); } }}>다음 단위부터 취소</button>}{["failed", "partial", "cancelled"].includes(run.status) && run.units.some(u => u.source_version_id === selected.version.id && ["failed", "cancelled"].includes(u.status)) && <button disabled={busy} className="mt-2 underline" onClick={() => startParse(true)}>실패·미완료 단위만 재실행</button>}</div>}
          <p className="my-3 text-sm text-slate-500">추출 구간 {blocks.length}개 · 위치 일치는 내용의 정확성 검토를 뜻하지 않습니다.</p>
          <div className="max-h-72 space-y-2 overflow-auto">{blocks.map(b => <button key={b.id} className="block w-full rounded border p-2 text-left text-sm hover:bg-slate-50" onClick={async () => { try { setEvidence(await request<Evidence>(`/evidence/${b.evidence_id}`)); } catch (e) { setError((e as Error).message); } }}>{b.text.slice(0, 160)}</button>)}</div>
          {evidence && <div className="mt-4 border-t pt-3"><h3 className="font-semibold">선택 구간 · 원문 발췌</h3>{!!evidence.usage_restrictions?.length && <p className="text-sm text-amber-800">사용 제한된 근거입니다. 지식 버전 탭에서 상태·사유를 확인하세요.</p>}<pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">{evidence.evidence.quote}</pre><details className="mt-2 text-xs"><summary>페이지·표·문단 위치</summary><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify(evidence.block.locator, null, 2)}</pre></details></div>}
        </>}</section>
      </div>
      </div>
    </main>
  </div>;
}

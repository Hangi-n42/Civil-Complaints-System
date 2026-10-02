"use client";

import { useEffect, useState } from "react";
import { label, post, type KnowledgeRequest, type DiscoveryRun } from "@/lib/knowledgeReview";

type Catalog = { bundle_id: string; manifest_sha256: string; items: { file_id: string; title: string; kind?: string; role?: string }[] };
type Version = { id: string; created_at?: string; lineage_id?: string; scope?: string; step?: number; candidates?: { name: string; definition?: string }[]; targets?: { name: string; definition?: string }[] };
const input = "mt-1 w-full rounded border px-3 py-2 text-sm";
export default function KnowledgeDiscoveryStart({ request, onReady, disabled }: { request: KnowledgeRequest; onReady: (id: string) => void; disabled: boolean }) {
  const [scope, setScope] = useState("current_discovery");
  const [step, setStep] = useState(0);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [questions, setQuestions] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [base, setBase] = useState("");
  const [baseDetail, setBaseDetail] = useState<Version | null>(null);
  const [inputRun, setInputRun] = useState<DiscoveryRun | null>(null);
  const [analysis, setAnalysis] = useState<DiscoveryRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = [inputRun,analysis].some(r => r && ["queued","running","cancel_requested"].includes(r.status));
  const locked = disabled || busy || running;
  useEffect(() => {
    let disposed = false;
    Promise.all([request<Catalog>(`/discovery/sources?scope=${scope}&step=${step}`),request<{items: Version[]}>("/ontologies")]).then(([c,v]) => {
      if (!disposed) { setCatalog(c); setVersions(v.items); setFiles([]); setInputRun(null); setAnalysis(null); setBase(""); setError(""); }
    }).catch(e => { if (!disposed) { setCatalog(null); setError(e.message); } });
    return () => { disposed = true; };
  }, [request,scope,step]);
  useEffect(() => {
    let disposed = false;
    setBaseDetail(null);
    if (base) request<Version>(`/ontologies/${base}`).then(v=>{if (!disposed) setBaseDetail(v);}).catch(e=>{if (!disposed) setError(e.message);});
    return () => { disposed = true; };
  }, [request,base]);
  useEffect(() => {
    const active = analysis || inputRun;
    if (!active || !["queued","running","cancel_requested"].includes(active.status)) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const value = await request<DiscoveryRun>(`/runs/${active.id}`);
        if (disposed) return;
        if (analysis) setAnalysis(value); else setInputRun(value);
        if (analysis && !disabled && !["queued","running","cancel_requested"].includes(value.status)) onReady(value.id);
      } catch (e) { if (!disposed) setError((e as Error).message); }
    },2000);
    return () => { disposed = true; clearInterval(timer); };
  }, [request,inputRun,analysis,onReady,disabled]);
  async function start(analyze: boolean) {
    setBusy(true); setError("");
    try {
      const chosen = versions.find(v => v.id===base);
      const body = analyze ? {kind:"discovery",discovery_mode:"analyze",input_run_id:inputRun?.id,
        cqs:questions.split("\n").map(q=>q.trim()).filter(Boolean).map((question,i)=>({id:`cq${i+1}`,question})),
        base_ontology_version_id:base||null,lineage_id:chosen?.lineage_id||`ui-${crypto.randomUUID()}`} :
        {kind:"discovery",scope,step,file_ids:files,bundle_id:catalog?.bundle_id,manifest_hash:catalog?.manifest_sha256};
      const value = await request<{run_id:string}>("/runs",post(body));
      const current = await request<DiscoveryRun>(`/runs/${value.run_id}`);
      if (analyze) { setAnalysis(current); if (!disabled && !["queued","running","cancel_requested"].includes(current.status)) onReady(current.id); }
      else { setInputRun(current); setAnalysis(null); }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const availableVersions = versions.filter((v,i,all)=>
    (scope==="historical_change" ? step>0 && v.scope==="historical_change" && (v.step||0)<=step : v.scope!=="historical_change") &&
    (!v.lineage_id || all.findIndex(other=>other.lineage_id===v.lineage_id)===i));
  return <details className="space-y-3 rounded border bg-white p-4"><summary className="cursor-pointer font-semibold" onClick={()=>request<{items:Version[]}>("/ontologies").then(v=>setVersions(v.items)).catch(e=>setError(e.message))}>새 탐색 준비 · 자료와 업무 질문 선택</summary>
    <fieldset disabled={locked} className="space-y-3 pt-3">
      <label className="block text-sm">자료 범위<select className={input} value={scope} onChange={e=>{setScope(e.target.value);setStep(0);}}><option value="current_discovery">현재 업무</option><option value="contrast_extension">대비 자료 확장</option><option value="historical_change">역사 변경</option></select></label>
      {scope==="historical_change" && <label className="block text-sm">역사 단계<select className={input} value={step} onChange={e=>setStep(Number(e.target.value))}>{[0,1,2].map(n=><option key={n} value={n}>{n===0 ? "최초 자료" : `${n}차 변경까지`}</option>)}</select></label>}
      <p className="text-sm">선택한 자료 버전과 파싱 결과를 먼저 고정합니다. 작은 정의·조건 묶음부터 선택하세요.</p>
      <div className="max-h-64 overflow-auto">{catalog?.items.map(f=><label className="block p-1 text-sm" key={f.file_id}><input type="checkbox" checked={files.includes(f.file_id)} onChange={e=>{setFiles(e.target.checked?[...files,f.file_id]:files.filter(i=>i!==f.file_id));setInputRun(null);setAnalysis(null);}} /> {f.title}{f.kind ? ` · ${f.kind}` : ""}{f.role ? ` · ${f.role}` : ""}</label>)}</div>
      <button className="rounded border px-3 py-2 text-sm disabled:opacity-40" disabled={!files.length} onClick={()=>start(false)}>선택 자료 고정</button>
      {inputRun && <p role="status" className="text-sm">자료 준비: {inputRun.status==="succeeded"?"완료":label(inputRun.status)} {inputRun.error || inputRun.stop_reason}</p>}
      <label className="block text-sm">이 자료로 답할 업무 질문 · 한 줄에 하나<textarea className={input} rows={3} value={questions} onChange={e=>setQuestions(e.target.value)} placeholder="어떤 유형이 있고 공급 조건과 예외는 무엇인가요?" /></label>
      <label className="block text-sm">이어갈 최신 검토 기준<select className={input} value={base} onChange={e=>setBase(e.target.value)}><option value="">기준 없음 · 새 초안</option>{availableVersions.map((v,i)=><option key={v.id} value={v.id}>검토 버전 {availableVersions.length-i} · {v.created_at ? new Date(v.created_at).toLocaleString("ko-KR") : "시각 미기록"}</option>)}</select></label>
      {baseDetail && <ul className="max-h-48 overflow-auto text-sm" aria-label="선택 기준의 정의">{(baseDetail.targets||baseDetail.candidates||[]).map((c,i)=><li key={i}>{c.name} · {c.definition||"정의 미기록"}</li>)}</ul>}
      <p className="text-xs text-slate-600">기준 없음은 별도 초안으로 시작합니다. 기준을 이어가려면 그 기준의 근거 자료도 선택해야 합니다.</p>
      <p className="text-xs text-slate-600">로컬 모델 순차 실행 · 최대 48회, 추가 탐색 2라운드, 후보 수정 1회. 불완전한 결과도 미처리 범위와 함께 검수하며 자동 수락하지 않습니다.</p>
      <button className="rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40" disabled={!questions.trim() || inputRun?.status!=="succeeded"} onClick={()=>start(true)}>고정 자료로 분석 시작</button>
    </fieldset>
    {analysis && <p role="status" className="text-sm">분석: {label(analysis.status)} · 호출 {analysis.metrics?.llm_calls||0}회 · {analysis.stop_reason}</p>}
    {analysis && !["queued","running","cancel_requested"].includes(analysis.status) && <button className="text-sm underline disabled:opacity-40" disabled={disabled} onClick={()=>onReady(analysis.id)}>이 분석 결과 검수하기 · 현재 편집 저장 후 가능</button>}
    {running && <button className="text-sm underline" onClick={async()=>{try {await request(`/runs/${(analysis||inputRun)?.id}/cancel`,post({}));}catch(e){setError((e as Error).message);}}}>현재 호출 저장 후 중단</button>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </details>;
}

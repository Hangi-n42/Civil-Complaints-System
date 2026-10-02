"use client";
import { useState } from "react";
import KnowledgeReviewEvidence from "./KnowledgeReviewEvidence";
import { post, type EvidenceRef, type KnowledgeRequest, type Changeset, type DiscoveryRun, type RecordValue } from "@/lib/knowledgeReview";
const input="mt-1 w-full rounded border px-3 py-2 text-sm";
type Hit={id:string;block_id?:string;text:string;source_version_id:string;run_id:string;parse_run_id?:string;locator:RecordValue;title:string};
export default function KnowledgeMissingProposal({request,run,change,question,onSaved,disabled}:{request:KnowledgeRequest;run:DiscoveryRun;change:Changeset;question:{id:string;question:string;kind:string};onSaved:()=>Promise<void>;disabled:boolean}) {
  const [name,setName]=useState(""); const [definition,setDefinition]=useState(""); const [query,setQuery]=useState("");
  const [hits,setHits]=useState<Hit[]>([]);const [ref,setRef]=useState<EvidenceRef|null>(null);const [evidence,setEvidence]=useState<EvidenceRef|null>(null);
  const [actor,setActor]=useState(""); const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function search(){setBusy(true);try{const r=await request<{items:Hit[]}>(`/discovery/search?run_id=${run.id}&q=${encodeURIComponent(query)}&limit=10`);setHits(r.items);setError("");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <details className="rounded border p-3"><summary className="cursor-pointer text-sm">이 질문의 누락 제안 추가</summary><fieldset disabled={disabled||busy} className="space-y-2">
    <p className="text-sm">{question.question} · 미승인 유형 제안으로 추가한 뒤 종류·관계를 검토하세요.</p>
    <label className="block text-sm">누락된 유형 이름<input className={input} value={name} onChange={e=>setName(e.target.value)}/></label>
    <label className="block text-sm">원문에 근거한 정의<textarea className={input} value={definition} onChange={e=>setDefinition(e.target.value)}/></label>
    <label className="block text-sm">고정 원문에서 근거 찾기<input className={input} value={query} onChange={e=>setQuery(e.target.value)}/></label><button className="text-sm underline" disabled={!query.trim()} onClick={search}>근거 검색</button>
    {hits.map(h=><button className="block w-full rounded border p-2 text-left text-sm" key={h.id||h.block_id} onClick={()=>setRef({evidence_id:h.id||h.block_id!,block_id:h.id||h.block_id!,source_version_id:h.source_version_id,parse_run_id:h.parse_run_id||h.run_id,span:[0,Array.from(h.text).length],quote:h.text,locator:h.locator})}>{h.title} · {Array.from(h.text).slice(0,120).join("")}</button>)}
    {ref && <KnowledgeReviewEvidence request={request} runId={run.id} reference={ref} onSelect={setEvidence}/>}
    {evidence && <p className="text-sm">연결한 구절: {evidence.quote}</p>}
    <label className="block text-sm">작성자<input className={input} value={actor} onChange={e=>setActor(e.target.value)}/></label><label className="block text-sm">추가 이유<input className={input} value={reason} onChange={e=>setReason(e.target.value)}/></label>
    <button className="rounded border px-3 py-2 text-sm disabled:opacity-40" disabled={!name.trim()||!definition.trim()||!evidence||!actor.trim()||!reason.trim()} onClick={async()=>{setBusy(true);try{await request(`/changes/${change.id}/ontology-candidates`,post({expected_changeset_revision:change.revision,actor,reason,candidates:[{target_kind:"class",operation:"add",after:{name,definition,inclusion:"",exclusion:""},evidence_refs:[evidence],support_type:"explicit",qualifiers:{scope:"",time:"",negation:"affirmed",statement_type:"definition"},cq_ids:question.kind==="cq"?[question.id]:[],scope_item_ids:question.kind==="scope"?[question.id]:[],rationale:reason}]}));await onSaved();setName("");setDefinition("");setEvidence(null);setError("");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>근거와 함께 미승인 제안 저장</button>
    {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
  </fieldset></details>;
}

"use client";
import { useEffect, useState } from "react";
import { type DiscoveryRun, type Changeset } from "@/lib/knowledgeReview";
const phases={training_s:"교육",preparation_s:"자료 준비",cq_s:"업무 질문 작성",construction_s:"구축",review_s:"검수",repair_s:"수정",update_s:"갱신",lookup_s:"조회",operations_s:"운영",complaint_s:"민원 적용",evidence_check_s:"제출 전 근거 확인"};
export default function KnowledgeHumanCost({run,change}:{run:DiscoveryRun|null;change:Changeset|null}){
  const [participant,setParticipant]=useState("");const [condition,setCondition]=useState("C1");
  const [phase,setPhase]=useState("preparation_s");const [started,setStarted]=useState<number|null>(null);
  const [times,setTimes]=useState<Record<string,string>>({});const [events,setEvents]=useState<{phase:string;seconds:number;at:string}[]>([]);
  const [completion,setCompletion]=useState("unmeasured");const [errors,setErrors]=useState("");const [notes,setNotes]=useState("");
  function pause(){if(started===null)return;const seconds=(Date.now()-started)/1000;setTimes(t=>({...t,[phase]:String(Math.round(((Number(t[phase])||0)+seconds)*1000)/1000)}));setEvents(e=>[...e,{phase,seconds,at:new Date().toISOString()}]);setStarted(null);}
  useEffect(()=>{function hidden(){if(document.hidden)pause();}document.addEventListener("visibilitychange",hidden);return()=>document.removeEventListener("visibilitychange",hidden);});
  const complete=Object.keys(phases).every(k=>times[k]!==undefined&&times[k]!=="");
  const hasRecord=events.length>0||Object.values(times).some(v=>v!=="");
  return <details className="rounded border bg-white p-4"><summary className="cursor-pointer font-semibold">사람 비교 시험 기록 · 실제 참여 시 사용</summary>
    <p className="my-2 text-sm">기존 비용 항목을 사용합니다. 모델 대기·휴식에는 타이머를 멈추세요. 탭이 숨겨지면 자동 중지됩니다. 미측정은 빈칸, 해당 없는 활동은 확인 후 0을 입력하세요. 총 시간만으로 동등 품질이나 효과를 판정하지 않습니다.</p>
    <div className="grid gap-3 text-sm md:grid-cols-2"><label>익명 참가자 이름<input className="block w-full rounded border p-2" value={participant} onChange={e=>setParticipant(e.target.value)}/></label>
    <label>비교 조건<select className="block w-full rounded border p-2" disabled={started!==null||hasRecord} value={condition} onChange={e=>setCondition(e.target.value)}><option value="C0">C0 · 직접 구축</option><option value="C1">C1 · AI 초안 검수</option><option value="B1">B1 · 기존 업무 방식</option><option value="B2">B2 · 온톨로지 활용</option></select></label>
    <label>현재 활동<select className="block w-full rounded border p-2" disabled={started!==null} value={phase} onChange={e=>setPhase(e.target.value)}>{Object.entries(phases).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><div className="flex gap-2"><button className="rounded border p-2" disabled={started!==null||!participant.trim()} onClick={()=>setStarted(Date.now())}>실제 활동 시간 시작</button><button className="rounded border p-2" disabled={started===null} onClick={pause}>대기·휴식 / 시간 저장</button></div>
    {Object.entries(phases).map(([k,v])=><label key={k}>{v} · 실제 초<input className="block w-full rounded border p-2" type="number" min="0" step="0.001" disabled={started!==null} value={times[k]??""} placeholder="미측정" onChange={e=>setTimes({...times,[k]:e.target.value})}/></label>)}
    <label>필수 업무 결과 완료<select className="block w-full rounded border p-2" value={completion} onChange={e=>setCompletion(e.target.value)}><option value="unmeasured">미판정</option><option value="complete">완료 · 별도 품질 대조 필요</option><option value="incomplete">미완료</option></select></label><label>최종 핵심 오류 수<input className="block w-full rounded border p-2" type="number" min="0" value={errors} placeholder="미측정" onChange={e=>setErrors(e.target.value)}/></label></div>
    <label className="my-2 block text-sm">완료 결과·오류 근거·재작업·열람 부담 기록<textarea className="block w-full rounded border p-2" value={notes} onChange={e=>setNotes(e.target.value)}/></label>
    <p className="text-sm">총 사람 시간: {complete?`${Object.values(times).reduce((n,v)=>n+Number(v),0).toFixed(3)}초`:"필수 비용 미측정 · 계산하지 않음"}</p>
    <p className="text-xs">다른 비교 조건은 현재 기록을 내려받은 뒤 새로고침하여 시작하세요. 새로고침하면 화면의 측정 기록은 사라집니다.</p>
    <button className="mt-2 rounded border p-2 text-sm disabled:opacity-40" disabled={started!==null||!participant.trim()||(errors!==""&&(!Number.isInteger(Number(errors))||Number(errors)<0))||Object.values(times).some(v=>v!==""&&(!Number.isFinite(Number(v))||Number(v)<0))} onClick={()=>{
      const record={protocol:"post-k10-workflow-v1",participant_kind:"human",participant_id:participant,condition,run_id:run?.id||null,changeset_id:change?.id||null,changeset_revision:change?.revision??null,
        costs:Object.fromEntries(Object.keys(phases).map(k=>[k,times[k]===undefined||times[k]===""?null:Number(times[k])])),total_human_s:complete?Object.values(times).reduce((n,v)=>n+Number(v),0):null,completion,critical_errors:errors===""?null:Number(errors),notes,events,recorded_at:new Date().toISOString(),effectiveness:"별도 동등 품질 비교 전 미판정"};
      const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=`human-cost-${condition}-${Date.now()}.json`;a.click();URL.revokeObjectURL(url);
    }}>측정 기록 내려받기</button>
  </details>;
}

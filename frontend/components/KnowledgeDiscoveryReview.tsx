"use client";

import { useEffect, useState } from "react";
import KnowledgeReviewEvidence from "./KnowledgeReviewEvidence";
import KnowledgeHumanCost from "./KnowledgeHumanCost";
import KnowledgeDiscoveryStart from "./KnowledgeDiscoveryStart";
import KnowledgeMissingProposal from "./KnowledgeMissingProposal";
import { canConvert, connectionTargets, manualAlignmentProposal, changeName, coverageRows, decisionBody, display, groupChanges, label, makeDraft, post, pretty, readableRefs, record, records, strings,
  type CandidateResponse, type Change, type Changeset, type DiscoveryRun, type EditDraft, type KnowledgeRequest, type Ontology, type RecordValue, type RunSummary } from "@/lib/knowledgeReview";

const inputClass = "mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm";
const buttonClass = "rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-40";
const panelClass = "min-w-0 space-y-3 rounded border bg-white p-4";
const fieldLabels: Record<string,string> = { name: "표시명", definition: "의미·정의", inclusion: "포함 기준", exclusion: "제외·예외", scope: "적용 범위·조건", time: "적용 시점", negation: "부정 여부", statement_type: "진술 성격" };

function JsonDetail({ title, value }: { title: string; value: unknown }) {
  return <details className="text-sm"><summary className="cursor-pointer">{title}</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-3 text-xs">{pretty(value)}</pre></details>;
}

function Schema({ title, value }: { title: string; value: Ontology | null }) {
  if (!value) return null;
  return <details className={panelClass}><summary className="cursor-pointer font-medium">{title}</summary>
    <p className="text-sm">{value.id ? `버전 ${value.id}` : "저장하지 않은 미승인 preview"}</p>
    {value.error ? <p role="alert">파생 확인 불가: {value.error}</p> : <>
      <ul className="space-y-2 text-sm">{(value.targets||value.candidates||[]).map(t=><li key={String(t.id)}><strong>{String(t.name)}</strong> · {String(t.definition||"")}<p>포함: {String(t.inclusion||"미기록")} · 제외: {String(t.exclusion||"미기록")}</p><p>적용 조건: {String(record(t.qualifiers).scope||"미기록")} · 시점: {String(record(t.qualifiers).time||"미기록")}</p>{t.domain_id ? <p>관계: {String((value.targets||value.candidates||[]).find(v=>v.id===t.domain_id)?.name||"대상 미확인")} → {String((value.targets||value.candidates||[]).find(v=>v.id===t.range)?.name||t.range)} · {label(String(record(t.qualifiers).negation||"unknown"))}</p> : null}</li>)}</ul>
      <JsonDetail title="현재 적용 슬롯 · 상속 포함" value={value.effective_class_slots} />
      <JsonDetail title="어휘와 이전 ID → 최종 정본 대응" value={value.vocabulary_registry} />
      <details><summary>저장 LinkML</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{value.linkml_yaml}</pre></details>
      <JsonDetail title="파생 JSON Schema" value={value.json_schema} />
      {value.included_change_ids && <JsonDetail title="preview 포함·제외 후보 ID" value={{ included: value.included_change_ids, excluded: value.excluded_change_ids }} />}
    </>}
  </details>;
}

export default function KnowledgeDiscoveryReview({ request }: { request: KnowledgeRequest }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [change, setChange] = useState<Changeset | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [reference, setReference] = useState<{ counter: boolean; index: number }>({ counter: false, index: 0 });
  const [actor, setActor] = useState("local-user");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<Changeset | null>(null);
  const [preview, setPreview] = useState<Ontology | null>(null);
  const [reviewed, setReviewed] = useState<Ontology | null>(null);
  const [batch, setBatch] = useState<string[]>([]);
  const [reviewDependencies, setReviewDependencies] = useState(false);
  const [bundlePreview, setBundlePreview] = useState<Ontology | null>(null);
  const [alignmentTarget, setAlignmentTarget] = useState("");
  const [preserveDefinition, setPreserveDefinition] = useState(true);
  const selected = change?.candidates.find(c => c.id === selectedId);
  const dirty = !!selected && !!draft && pretty(draft) !== pretty(makeDraft(selected));
  const locked = busy || dirty || conflict;
  const refs = readableRefs(selected ? (reference.counter ? selected.counter_evidence_refs : selected.evidence_refs) : []);
  const currentRef = Array.isArray(refs) ? refs[reference.index] : undefined;

  useEffect(() => {
    let disposed = false;
    request<{ items: RunSummary[]; next_before: number | null }>("/runs").then(data => {
      if (!disposed) { setRuns(data.items); setNextBefore(data.next_before); }
    }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [request]);

  function select(c?: Change) {
    setSelectedId(c?.id || ""); setDraft(c ? makeDraft(c) : null);
    setReference({ counter: false, index: 0 }); setReason(""); setReviewDependencies(false); setAlignmentTarget(""); setPreserveDefinition(true);
  }
  async function getChange(id: string) {
    const response = await request<CandidateResponse>(`/candidates?changeset_id=${encodeURIComponent(id)}`);
    const value = response.changesets.find(c => c.id === id);
    if (!value) throw new Error("저장된 변경안을 찾을 수 없습니다.");
    return value;
  }
  async function derived(value: Changeset) {
    const id = value.reviewed_ontology_version_id || value.base_ontology_version_id;
    const [p, v] = await Promise.all([request<Ontology>(`/changes/${value.id}/schema-preview`), id ? request<Ontology>(`/ontologies/${id}`) : Promise.resolve(null)]);
    setPreview(p); setReviewed(v);
  }
  async function loadChange(id: string, keepId?: string) {
    const value = await getChange(id);
    setBatch([]); setBundlePreview(null); setChange(value); select(value.candidates.find(c => c.id === keepId) || value.candidates[0]);
    await derived(value);
  }
  async function chooseRun(id: string) {
    if (!id) return;
    setBusy(true); setError(""); setNotice(""); setRun(null); setChange(null); setPreview(null); setReviewed(null); setConflict(false); setLatest(null); setBatch([]); setBundlePreview(null); select();
    try {
      const value = await request<DiscoveryRun>(`/runs/${encodeURIComponent(id)}`); setRun(value);
      const refreshed = await request<{items:RunSummary[];next_before:number|null}>("/runs"); setRuns(refreshed.items);setNextBefore(refreshed.next_before);
      if (value.changeset_id) await loadChange(value.changeset_id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function convert() {
    if (!run) return;
    setBusy(true); setError("");
    try {
      const value = await request<{ changeset_id: string }>(`/runs/${run.id}/ontology-changes`, post({}));
      setRun({ ...run, changeset_id: value.changeset_id }); await loadChange(value.changeset_id);
      setNotice("저장된 분석 결과를 변경안으로 연결했습니다. 모델·파싱 재실행은 없습니다.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function decide(action: string, ids = selected ? [selected.id] : [], fromBundle = false) {
    if (!change || !draft || !ids.length || conflict) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (fromBundle && (dirty || bundlePreview?.changeset_revision !== change.revision || bundlePreview.error || !ids.every(id=>bundlePreview.included_change_ids?.includes(id)))) throw new Error("편집 저장 후 선택 묶음의 의존 미리보기를 확인하세요.");
      await request(`/changes/${change.id}/decisions`, post(decisionBody(change, actor, reason, action, ids, draft, ids.length === 1 && !fromBundle && reviewDependencies)));
      await loadChange(change.id, selectedId);
      setNotice("결정과 전후 값·이력·검토된 버전을 다시 조회했습니다. 운영 활성화는 별도 절차입니다.");
    } catch (e) {
      setError((e as Error).message);
      if ((e as { status?: number }).status === 409) { setConflict(true); setLatest(null); }
    } finally { setBusy(false); }
  }
  function changeText(field: "after" | "qualifiers", key: string, value: unknown) {
    if (!draft) return;
    try { setDraft({ ...draft, [field]: pretty({ ...record(JSON.parse(draft[field])), [key]: value }) }); setError(""); }
    catch { setError("모델링 상세의 JSON 문법을 먼저 고쳐 주세요. 편집 입력은 유지됩니다."); }
  }
  function draftRecord(field: "after" | "qualifiers") {
    try { return record(JSON.parse(draft?.[field] || "{}")); } catch { return {}; }
  }
  const result = change?.analysis_result || run?.result || {};
  const baseAfter = record(selected?.before);
  const after = draftRecord("after");
  const qualifiers = draftRecord("qualifiers");
  const stat = (key: string) => result[key] == null ? "미기록" : Array.isArray(result[key]) ? (result[key] as unknown[]).length : display(result[key]);
  function targetName(id: unknown) {
    const candidate = change?.candidates.find(c => c.target_id === id);
    const target = (reviewed?.targets ?? reviewed?.candidates)?.find(t => t.id === id);
    return candidate ? changeName(candidate) : display(target?.name ?? "연결 대상 확인 필요");
  }
  function connection(value: RecordValue) {
    if (value.canonical_id) return `같은 대상으로 통합할 대상: ${targetName(value.canonical_id)}`;
    if (value.child_id || value.parent_id) return `${targetName(value.child_id)} → ${targetName(value.parent_id)} · ${{ is_a: "모든 대상의 포함", broader: "더 넓은 용어", related: "관련 용어", part_of: "부분 관계", instance_of: "개별 대상과 유형" }[display(value.relation)] || "관계 확인 필요"} 제안`;
    if (value.alias_of) return `다른 이름으로 연결할 대상: ${targetName(value.alias_of)}`;
    if (value.domain_id) return `${targetName(value.domain_id)}의 특성·관계 → ${targetName(value.range)}`;
    return "";
  }

  const targets = [...new Map([...(reviewed?.targets || reviewed?.candidates || []).map(t=>[String(t.id),t] as const), ...(change?.candidates || []).map(c=>[c.target_id,{id:c.target_id,kind:c.target_kind,...record(c.after)}] as const)]).values()];
  function targetSelect(key: string, title: string, primitive=false) {
    return <label className="block text-sm" key={key}>{title}<select className={inputClass} value={String(after[key] || "")} onChange={e=>changeText("after",key,e.target.value||null)}><option value="">대상 선택</option>{primitive && ["string","integer","float","boolean","date","datetime"].map(v=><option key={v} value={v}>{({string:"문자",integer:"정수",float:"실수",boolean:"참·거짓",date:"날짜",datetime:"날짜·시간"})[v]}</option>)}{connectionTargets(targets,key,draft?.target_kind || "").map(t=><option key={String(t.id)} value={String(t.id)}>{String(t.name)} · {String(t.definition || "").slice(0,60)}</option>)}</select></label>;
  }
  return <section className="space-y-4" aria-label="탐색 변경 검수">
    <KnowledgeHumanCost run={run} change={change} />
    <KnowledgeDiscoveryStart request={request} onReady={chooseRun} disabled={locked} />
    <div className={panelClass}><h2 className="text-lg font-semibold">탐색 초안의 의미와 근거 검수</h2>
      <p className="text-sm text-slate-600">저장된 분석 결과를 선택해 원문과 변경을 대조합니다. 수락은 검토된 온톨로지 버전을 만들며 운영 지식을 활성화하지 않습니다.</p>
      <label className="block text-sm">저장된 탐색 실행<select className={inputClass} value={run?.id || ""} disabled={locked} onChange={e => chooseRun(e.target.value)}>
        <option value="">실행 선택</option>{runs.map(r => <option key={r.id} value={r.id}>{label(r.status)} · {r.scope}/{r.step} · {r.started_at ? new Date(r.started_at).toLocaleString("ko-KR") : "시작 시각 미기록"} · {r.id.slice(0,8)}{!r.has_result ? " · 저장 결과 없음" : ""}</option>)}
      </select></label>
      {!runs.length && <p className="text-sm">저장된 탐색 실행이 없습니다.</p>}
      {nextBefore && <button disabled={locked} className="text-sm underline" onClick={async () => {
        setBusy(true); try { const data = await request<{ items: RunSummary[]; next_before: number | null }>(`/runs?before=${nextBefore}`); setRuns([...runs,...data.items]); setNextBefore(data.next_before); }
        catch (e) { setError((e as Error).message); } finally { setBusy(false); }
      }}>이전 실행 더 불러오기</button>}
    </div>
    {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-900">{error}</p>}
    {notice && <p role="status" className="rounded bg-blue-50 p-3 text-sm">{notice}</p>}
    {run && <section className={panelClass} aria-label="탐색 처리 범위">
      <h3 className="font-semibold">{label(run.status)} · {run.frozen_input.scope} / 단계 {run.frozen_input.step}</h3>
      <p className="text-sm">종료 사유: {run.stop_reason || run.error || "미기록"}</p>
      <div className="grid gap-2 text-sm md:grid-cols-3"><p>구조 조사 {stat("structure_surveyed")}개 · 원문 제공 {stat("raw_provided")}개</p><p>양 역할 근거 연결 {stat("analysis_succeeded")}개 · 의미 해결과 구분</p><p>원문 미제공 {stat("unvisited_block_ids")}개 · 분석 근거 미연결 {stat("unanalysed_block_ids")}개</p><p>필수 미처리 {stat("mandatory_pending")}개 · 실패 {stat("failures")}개 · 미복구 의미 {stat("unresolved_recovery_requests")}개</p><p>모델 누적 {run.metrics?.llm_calls ?? "미기록"}회 · 검수 중 추가 호출 없음</p><p>변경 {change?.candidates.length ?? 0}개 · 보류 {change?.candidates.filter(c => c.review_status === "deferred").length ?? 0}개 · 미해결 {change?.unresolved_count ?? "미변환"}개</p></div>
      <ul className="space-y-1 text-sm">{run.frozen_input.files.map(f => <li key={f.file_id}>{f.title} · {f.role || "역할 미기록"}</li>)}</ul>
      <details className="text-xs"><summary>사용 자료 버전 · 실행 ID</summary><pre className="whitespace-pre-wrap break-all">{pretty({ run_id: run.id, files: run.frozen_input.files })}</pre></details>
      {!change && <><button disabled={busy || !canConvert({ status: run.status, has_result: !!run.result })} className={buttonClass} onClick={convert}>저장 결과를 변경안으로 변환</button><p className="text-xs">저장 결과가 있는 종료 실행만 변환합니다. 실패·취소·일부 처리 상태를 완료로 바꾸지 않습니다.</p></>}
    </section>}
    {run && change && <>
      <section className={panelClass}><h3 className="font-semibold">원문과 비교해 판단할 항목</h3>
        <div className="grid gap-2 break-all text-xs md:grid-cols-3"><p>기준 온톨로지: {change.base_ontology_version_id || "빈 기준"}</p><p>현재 검토 head: {change.ontology_head_id || "없음"}</p><p>변경안 revision: {change.revision}</p></div>
        <p className="text-sm">반복 표시는 후보별 ID·근거·결정을 유지합니다. 같은 이름이 같은 대상을 뜻하는지 개별 확인하세요.</p>
        <button disabled={locked} className="text-sm underline" onClick={async () => { setBusy(true); try { await loadChange(change.id,selectedId); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }}>최신 검토 상태 다시 조회</button>
        {dirty && <p className="text-sm text-amber-900">저장하지 않은 편집이 있습니다. 저장 또는 편집 취소 후 다른 후보로 이동하세요.</p>}
        <div className="max-h-72 space-y-2 overflow-auto">{groupChanges(change.candidates).map(group => <div className="rounded border p-2" key={group[0].id}>
          {group.length > 1 && <p className="text-xs font-medium">같은 표기의 제안 {group.length}개 · 자동 병합 아님</p>}
          {group.map(c => <div key={c.id} className="flex items-center gap-2">
            <input type="checkbox" aria-label={`${changeName(c)} 의존 묶음 선택`} disabled={locked} checked={batch.includes(c.id)} onChange={e => {setBatch(e.target.checked ? [...batch,c.id] : batch.filter(i => i !== c.id)); setBundlePreview(null);}} />
            <button disabled={locked} aria-pressed={selectedId === c.id} className={`w-full rounded p-2 text-left text-sm ${selectedId === c.id ? "bg-blue-50 font-semibold" : "hover:bg-slate-50"}`} onClick={() => select(c)}>{changeName(c)} · {label(c.operation)} · {label(c.review_status)}<span className="block text-xs font-normal text-slate-600">{c.validation.structural_errors.length ? "구조·근거 확인 필요" : "형식 검사 통과 · 의미 검수 필요"} · 근거 {Array.isArray(c.evidence_refs) ? c.evidence_refs.length : 0}개 · 후보 {c.id.slice(0,11)}</span></button>
          </div>)}
        </div>)}</div>
        {!change.candidates.length && <p>변환된 변경 후보가 없습니다. 아래 참고 표본과 누락 기록을 확인하세요.</p>}
      </section>
      {conflict && <section role="alert" className="space-y-3 rounded border border-amber-500 bg-amber-50 p-4">
        <h3 className="font-semibold">다른 결정과 충돌했습니다. 작성한 입력은 유지됩니다.</h3><p className="text-sm">최신 변경과 비교한 뒤 다시 검토하세요. 다른 변경안이 head를 바꾼 경우 수락에는 새 기준의 탐색 실행이 필요합니다.</p>
        <button disabled={busy} className={buttonClass} onClick={async () => { setBusy(true); try { setLatest(await getChange(change.id)); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }}>최신 변경과 비교</button>
        {latest && <><p className="text-sm break-all">최신 revision {latest.revision} · head {latest.ontology_head_id || "없음"}</p><JsonDetail title="서버 최신 값 · 내 편집 값 비교" value={{ latest: latest.candidates.find(c => c.id === selectedId), my_edit: draft }} />
          <button disabled={busy} className={buttonClass} onClick={async () => { setChange(latest); setConflict(false); setLatest(null); setBatch([]); setError(""); setNotice("입력을 유지하고 최신 revision을 선택했습니다. 변경 내용과 의존을 다시 검토한 뒤 결정하세요."); try { await derived(latest); } catch(e) { setError((e as Error).message); } }}>비교 후 최신 revision에서 다시 검토 · 입력 유지</button></>}
      </section>}
      {selected && draft && <>
        <div className="grid items-start gap-4 2xl:grid-cols-3 xl:grid-cols-2">
          <section className={panelClass}><h3 className="font-semibold">원문이 이 의미와 조건을 뒷받침합니까?</h3>
            <div className="flex flex-wrap gap-2 text-sm">{([false,true] as const).map(counter => <button key={String(counter)} className="rounded border px-2 py-1" aria-pressed={reference.counter === counter} onClick={() => setReference({ counter, index: 0 })}>{counter ? "반례 원문" : "제안 근거"} ({Array.isArray(counter ? selected.counter_evidence_refs : selected.evidence_refs) ? (counter ? selected.counter_evidence_refs : selected.evidence_refs).length : 0})</button>)}</div>
            {Array.isArray(refs) && refs.map((r,i) => <button className="block w-full rounded border p-2 text-left text-sm" key={`${r.evidence_id}-${i}`} aria-pressed={reference.index === i} onClick={() => setReference({ ...reference, index: i })}>{i+1}. {Array.from(r.quote).slice(0,120).join("")}{Array.from(r.quote).length > 120 ? "…" : ""}</button>)}
            {currentRef ? <KnowledgeReviewEvidence key={`${currentRef.evidence_id}:${currentRef.quote}:${reference.counter}`} request={request} runId={run.id} reference={currentRef} onSelect={busy || conflict ? undefined : ref=>{ if (!draft) return; const key=reference.counter ? "counter_evidence_refs" : "evidence_refs"; setDraft({...draft,[key]:pretty([ref])}); setNotice("선택한 원문 구절을 편집 근거로 연결했습니다. 편집 저장 또는 수정 후 수락으로 기록하세요."); }} /> : <p className="text-sm text-amber-900">{reference.counter ? "연결된 반례 원문이 없습니다. 반례가 없다는 판정은 아닙니다." : "근거 문맥 확인 필요 · 근거를 연결하거나 보류하세요."}</p>}
          </section>
          <section className={panelClass}><h3 className="font-semibold">의미·범위·예외를 어떻게 바꿉니까?</h3>
            <p className="text-sm">{label(selected.support_type)} · {label(selected.operation)} · {selected.operation === "merge" ? "같은 대상이라는 판단을 개별 검수하세요." : "원문 명시와 설계 제안을 구분하세요."}</p>
            <p className="text-sm">{connection(record(selected.after))}</p>
            {connection(baseAfter) && <p className="text-xs text-slate-600">기존 연결: {connection(baseAfter)}</p>}
            <div className="grid gap-2 text-sm sm:grid-cols-2">{[
              { title: "변경 전", definition: selected.before, qualifiers: record(baseAfter.qualifiers), color: "bg-slate-50" },
              { title: "변경안 · 저장된 값", definition: selected.after, qualifiers: selected.qualifiers, color: "bg-blue-50" },
            ].map(side => <div key={side.title} className={`rounded p-3 ${side.color}`}><h4 className="font-semibold">{side.title}</h4>
              {side.definition === null ? <p className="mt-2">이전 항목 없음 · 신규 제안</p> : <>
                {["name","definition","inclusion","exclusion"].map(k => <p className="mt-2 whitespace-pre-wrap" key={k}>{fieldLabels[k]}: {display(record(side.definition)[k])}</p>)}
                <dl className="mt-3 space-y-1">{["scope","time","negation","statement_type"].map(k => <div key={k}><dt className="font-medium">{fieldLabels[k]}</dt><dd className="whitespace-pre-wrap">{label(display(side.qualifiers[k]))}</dd></div>)}</dl>
              </>}
            </div>)}</div>
            <p className="whitespace-pre-wrap text-sm">변경 이유: {display(selected.rationale)}</p>
            {(selected.origin.source_relation || selected.origin.source_relations) ? <div className="rounded border bg-amber-50 p-3 text-sm"><h4 className="font-semibold">설계의 출처인 원문 진술 · 조건 실행 규칙 아님</h4>
              {[...records(selected.origin.source_relations),...(selected.origin.source_relation ? [record(selected.origin.source_relation)] : [])].map((rule,i)=><div className="mt-2" key={i}><p>{display(record(rule.endpoint_labels).subject || rule.subject)} · {display(rule.predicate)} · {display(record(rule.endpoint_labels).object || rule.object)}</p><p>{label(display(rule.statement_type))} · {label(display(rule.negation))}</p><p>조건·예외: {display(rule.conditions)}</p><p>시점: {display(rule.time)}</p></div>)}
              <p>설계 관계의 존재는 실제 행위·법적 권한·조건 충족을 확인한 결과가 아닙니다.</p></div> : null}
            <fieldset disabled={busy || conflict} className="space-y-3 border-t pt-3"><legend className="font-medium">검토자가 수정할 내용 · 아직 저장되지 않음</legend>
              {["add","update"].includes(selected.operation) && !["hierarchy"].includes(draft.target_kind) && ["name", ...(draft.target_kind === "alias" ? [] : ["definition","inclusion","exclusion"])].map(k => <label key={k} className="block text-sm">{fieldLabels[k]}<textarea className={inputClass} value={typeof after[k] === "string" ? after[k] as string : ""} onChange={e => changeText("after",k,e.target.value)} /></label>)}
              <label className="block text-sm">항목 종류<select className={inputClass} value={draft.target_kind} onChange={e=>setDraft({...draft,target_kind:e.target.value})}>{["class","attribute","relation","vocabulary_concept","hierarchy","alias"].map(k=><option key={k} value={k}>{label(k)}</option>)}</select></label>
              {["relation","attribute"].includes(draft.target_kind) && <>{targetSelect("domain_id","출발 유형 · 주체")}{targetSelect("range","도착 유형 · 대상 또는 값",draft.target_kind==="attribute")}
                <label className="block text-sm">관계 방향<select className={inputClass} value={String(after.direction || "unresolved")} onChange={e=>changeText("after","direction",e.target.value)}><option value="unresolved">판단 미정</option><option value="subject_to_object">출발 유형에서 도착 유형으로</option></select></label>
                {["required","multivalued"].map(k=><label className="block text-sm" key={k}><input type="checkbox" checked={after[k]===true} onChange={e=>changeText("after",k,e.target.checked)}/> {k==="required"?"필수값":"여러 값 허용"}</label>)}</>}
              {draft.target_kind==="alias" && targetSelect("alias_of","같은 뜻의 정본 유형")}
              {selected.operation==="merge" && targetSelect("canonical_id","통합 후 정본 유형")}
              {draft.target_kind==="hierarchy" && <>{targetSelect("child_id","하위 · 부분 유형")}{targetSelect("parent_id","상위 · 전체 유형")}
                <label className="block text-sm">포함 관계의 성격<select className={inputClass} value={String(after.relation || "")} onChange={e=>changeText("after","relation",e.target.value)}><option value="">선택</option>{Object.entries({is_a:"모든 대상 포함",part_of:"부분",instance_of:"개별 대상의 유형",broader:"더 넓은 용어",related:"관련 용어"}).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
                {(["a_to_b","b_to_a"] as const).map(direction=>{let review:RecordValue={};try{review=record(JSON.parse(draft.hierarchy_review));}catch{} const builder=record(review.builder);const check=record(builder[direction]);return <div className="rounded border p-2" key={direction}><label className="block text-sm">{direction==="a_to_b"?"하위의 모든 대상이 상위에 포함됩니까?":"상위의 모든 대상이 하위에 포함됩니까?"}<select className={inputClass} value={String(check.judgment||"unknown")} onChange={e=>setDraft({...draft,hierarchy_review:pretty({...review,builder:{...builder,[direction]:{...check,judgment:e.target.value,evidence_ids:readableRefs(JSON.parse(draft.evidence_refs)).map(r=>r.evidence_id),counter_evidence_ids:readableRefs(JSON.parse(draft.counter_evidence_refs)).map(r=>r.evidence_id)}}})})}>{["supported","refuted","unknown"].map(j=><option key={j} value={j}>{label(j)}</option>)}</select></label><label className="block text-sm">이 방향의 판단 이유<textarea className={inputClass} value={String(check.reason||"")} onChange={e=>setDraft({...draft,hierarchy_review:pretty({...review,builder:{...builder,[direction]:{...check,judgment:check.judgment||"unknown",reason:e.target.value,evidence_ids:readableRefs(JSON.parse(draft.evidence_refs)).map(r=>r.evidence_id),counter_evidence_ids:readableRefs(JSON.parse(draft.counter_evidence_refs)).map(r=>r.evidence_id)}}})})}/></label></div>;})}</>}
              {[["negation","부정 여부",["affirmed","negated","unknown"]],["statement_type","진술 성격",["definition","rule","instance","design_proposal","unresolved"]]].map(([key,title,values])=><label className="block text-sm" key={String(key)}>{String(title)}<select className={inputClass} value={String(qualifiers[String(key)]||"unknown")} onChange={e=>changeText("qualifiers",String(key),e.target.value)}>{(values as string[]).map(v=><option key={v} value={v}>{label(v)}</option>)}</select></label>)}
              <label className="block text-sm">제안 성격<select className={inputClass} value={draft.support_type} onChange={e => setDraft({ ...draft, support_type: e.target.value })}><option value="explicit">원문 명시 제안</option><option value="design_proposal">설계 제안</option><option value="unresolved">판단 미정</option></select></label>
              {["scope","time"].map(k => <label key={k} className="block text-sm">{fieldLabels[k]}<textarea className={inputClass} value={typeof qualifiers[k] === "string" ? qualifiers[k] as string : ""} onChange={e => changeText("qualifiers",k,e.target.value)} /></label>)}
              <label className="block text-sm">변경안의 이유<textarea className={inputClass} value={draft.rationale} onChange={e => setDraft({ ...draft, rationale: e.target.value })} /></label>
              <label className="block text-sm">남은 검토 쟁점 · 해결한 항목은 삭제하고 판단 사유에 근거 기록<textarea className={inputClass} value={(()=>{try{return JSON.parse(draft.unresolved_issues).map((v:unknown)=>typeof v==="string"?v:display(record(v).reason||v)).join("\n");}catch{return "";}})()} onChange={e=>setDraft({...draft,unresolved_issues:pretty(e.target.value.split("\n").filter(Boolean))})}/></label>
              <details><summary className="cursor-pointer text-sm">모델링 상세 · 종류·참조·근거 수정</summary><p className="my-2 break-all text-xs">대상 ID {selected.target_id}<br />symbol {selected.symbol}<br />후보 ID {selected.id} · ID는 수정하지 않습니다.</p>
                <label className="block text-sm">종류<select className={inputClass} value={draft.target_kind} onChange={e => setDraft({ ...draft, target_kind: e.target.value })}>{["class","attribute","relation","vocabulary_concept","hierarchy","alias"].map(k => <option key={k} value={k}>{label(k)}</option>)}</select></label>
                <p className="my-2 text-xs">정의의 domain_id/range/child_id/parent_id/alias_of/canonical_id는 서버 대상 ID를 사용합니다. 근거의 버전·parse·span은 원문과 일치해야 하며 저장 시 서버가 검사합니다.</p>
                <JsonDetail title="이 변경안의 대상 ID 목록" value={change.candidates.map(c => ({ target_id: c.target_id, name: changeName(c), kind: c.target_kind }))} />
                {([['after','변경 후 정의·참조'],['qualifiers','범위·시점·부정·진술 성격'],['evidence_refs','제안 근거'],['counter_evidence_refs','반례 근거'],['hierarchy_review','양방향 검토 기록'],['unresolved_issues','미해결 쟁점']] as const).map(([key,title]) => <label className="mt-3 block text-sm" key={key}>{title} (JSON)<textarea rows={4} spellCheck={false} className={`${inputClass} font-mono text-xs`} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>)}
              </details>
              {([['cq_ids',run.cqs,'관련 업무 질문'],['scope_item_ids',run.scope_items,'관련 허용 범위']] as const).map(([key,items,title]) => <fieldset key={key}><legend className="text-sm">{title}</legend>{items.map(q => <label key={q.id} className="block text-sm"><input type="checkbox" checked={draft[key].includes(q.id)} onChange={e => setDraft({ ...draft, [key]: e.target.checked ? [...draft[key],q.id] : draft[key].filter(id => id !== q.id) })} /> {q.question}</label>)}</fieldset>)}
            </fieldset>
          </section>
          <section className={panelClass}><h3 className="font-semibold">반례·의존·영향에서 더 확인할 것은 무엇입니까?</h3>
            <p className="text-sm font-medium">{selected.validation.structural_errors.length ? "구조·근거 확인 필요" : "형식 검사 통과"} · 의미 검수 필요</p>
            <ul className="list-inside list-disc text-sm text-amber-900">{selected.validation.structural_errors.map((v,i) => <li key={i}>{v}</li>)}</ul>
            <p className="text-sm">미수락 의존 {selected.validation.unresolved_dependency_ids.length}개 · 자동 수락하지 않습니다.</p>
            <ul className="space-y-1 text-sm">{selected.dependency_ids.map(id => { const c = change.candidates.find(v => v.id === id); return <li key={id}>{c ? `${changeName(c)} · ${label(c.review_status)}` : id}</li>; })}</ul>
            <p className="text-sm">확인된 직접 참조 {selected.affected_reference_ids.length}개 · 간접 영향은 미탐색</p>
            {selected.consumer_impact && <div className="rounded border p-2 text-sm"><p>소비자 작업: {{ display_refresh: "표시·검색 참조 갱신", partial_extract: "필요한 필드·자료만 추가 추출", semantic_review: "의미 대응·영향 사실 재검토", review_dependencies: "이전 ID 대응·직접 의존 검토" }[selected.consumer_impact.action] || selected.consumer_impact.action}</p><p>직접 영향 사실 {selected.consumer_impact.affected_assertion_ids.length}개 {selected.consumer_impact.new_required ? "· 새 필수값 호환성 확인 필요" : ""}</p></div>}
            <JsonDetail title="직접 참조 상세" value={selected.affected_references} />
            <JsonDetail title="미해결·보류할 쟁점" value={selected.unresolved_issues} />
            {selected.target_kind === "hierarchy" && <HierarchyReview value={record(selected.hierarchy_review)} a={targetName(record(selected.after).child_id)} b={targetName(record(selected.after).parent_id)} />}
            <div className="border-t pt-3"><h4 className="text-sm font-semibold">AI 분석 당시 의견 · 현재 의미 검증 아님</h4>
              <p className="mt-1 text-xs text-amber-900">대상: A2 실행 {run.id.slice(0,8)}의 원제안. {selected.origin.human_edited || dirty ? "사람이 수정한 내용은 AI가 다시 검토하지 않았습니다." : "A2 후속 수정의 해결 여부와 현재 의미 정확성은 원문으로 확인하세요."} 현재 변경안 revision {change.revision}.</p>
              {[...records(selected.origin.critiques),...records(selected.origin.relation_checks)].map((opinion,i) => <p key={i} className="mt-2 text-sm">{opinion.judgment ? `${label(display(opinion.judgment))} · ` : ""}{display(opinion.reason || opinion.description || opinion.issue || opinion)}</p>)}
              <JsonDetail title="원제안·Critic 의견·수정 전후 기록" value={{ original: change.original_candidates?.find(c => c.change_id === selected.change_id), origin: selected.origin }} />
              <JsonDetail title="서버가 구분한 의미 검수 항목" value={selected.validation.semantic_review} />
            </div>
          </section>
        </div>
        <section className={panelClass}><h3 className="font-semibold">검토 결과 기록</h3>
          <p className="text-sm">근거 부족·예외 미확인 시 보류할 수 있습니다. 편집 저장은 미승인 상태이며, 보류·기각 항목도 편집 저장 후 다시 검토할 수 있습니다.</p>
          <div className="grid gap-3 md:grid-cols-2"><label className="text-sm">결정자<input className={inputClass} value={actor} disabled={busy} onChange={e => setActor(e.target.value)} /></label><label className="text-sm">판단 사유 · 범위·반례·보류 이유<input className={inputClass} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} /></label></div>
          {selected.consumer_impact?.requires_resolution && <label className="my-2 block text-sm"><input type="checkbox" checked={reviewDependencies} disabled={busy || conflict} onChange={e => setReviewDependencies(e.target.checked)} /> 직접 영향 사실을 재검토 상태로 보류하고 이 온톨로지 변경 수락 · 과거 실행/스냅샷 보존, 새 버전에서 필요한 부분만 재추출</label>}
          <div className="flex flex-wrap gap-2">{([['edit','편집 저장 · 미승인'],['modify','수정 후 수락'],['accept','이 변경 수락'],['defer','보류'],['reject','기각']] as const).map(([action,title]) => <button key={action} className={buttonClass} disabled={busy || conflict || !actor.trim() || !reason.trim() || (action === 'accept' && ((!selected.can_accept && !reviewDependencies) || dirty)) || (['defer','reject'].includes(action) && dirty) || (action === 'modify' && !dirty)} onClick={() => decide(action)}>{title}</button>)}
            <button className="rounded border px-3 py-2 text-sm" disabled={busy || conflict || !dirty} onClick={() => { setDraft(makeDraft(selected)); setError(""); }}>편집 취소 · 저장된 값 복원</button>
          </div>
          {!selected.can_accept && <p className="text-xs text-amber-900">현재 값은 바로 수락할 수 없습니다. 오류·의존을 확인해 편집하거나 보류하세요. 수정 후 수락도 서버 검사를 통과해야 합니다.</p>}
          {["class","vocabulary_concept"].includes(selected.target_kind) && <details className="space-y-2 border-t pt-3"><summary className="cursor-pointer text-sm">기존 대상으로 명시 대응 제안</summary>
            <p className="text-sm">기존 이름과 정의를 대조하고 동일한 대상이라고 판단한 근거를 위 판단 사유에 기록하세요. 새 미승인 제안으로 저장됩니다.</p>
            <select aria-label="명시 대응할 기존 대상" className={inputClass} value={alignmentTarget} disabled={locked} onChange={e=>setAlignmentTarget(e.target.value)}><option value="">기존 이름·정의 선택</option>{(reviewed?.targets||reviewed?.candidates||[]).filter(t=>!t.deprecated && (t.kind==="concept"?"class":t.kind)===selected.target_kind).map(t=><option key={String(t.id)} value={String(t.id)}>{String(t.name)} · {String(t.definition||"")}</option>)}</select>
            <label className="block text-sm"><input type="checkbox" checked={preserveDefinition} disabled={locked} onChange={e=>setPreserveDefinition(e.target.checked)}/> 기존 이름·정의 유지, 근거 추가 · 해제하면 현재 후보의 정의로 변경 제안</label>
            <button className={buttonClass} disabled={locked || !alignmentTarget || !actor.trim() || !reason.trim()} onClick={async()=>{setBusy(true);setError("");try{const target=(reviewed?.targets||reviewed?.candidates||[]).find(t=>t.id===alignmentTarget)!;await request(`/changes/${change.id}/ontology-candidates`,post({expected_changeset_revision:change.revision,actor,reason,candidates:[manualAlignmentProposal(selected,target,preserveDefinition,reason)]}));await loadChange(change.id);setNotice("사람의 명시 대응 제안을 저장했습니다. 원래 제안과 새 제안을 각각 검토하세요.");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>근거·사유와 함께 명시 대응 저장</button>
          </details>}
          {batch.length > 0 && <div className="space-y-2 border-t pt-3"><p className="text-sm">선택한 의존 묶음 {batch.length}개 · 각 후보의 편집을 먼저 저장하세요. 필요한 유형도 직접 선택해야 합니다.</p>
            <ul className="text-sm">{batch.map(id=>{const c=change.candidates.find(c=>c.id===id)!;return <li key={id}>{changeName(c)} · {label(c.target_kind)} · {label(c.review_status)}</li>;})}</ul>
            <button className={buttonClass} disabled={locked} onClick={async()=>{setBusy(true);setError("");try{const query=new URLSearchParams();batch.forEach(id=>query.append("candidate_ids",id));setBundlePreview(await request<Ontology>(`/changes/${change.id}/schema-preview?${query}`));}catch(e){setError((e as Error).message);setBundlePreview(null);}finally{setBusy(false);}}}>선택 묶음 의존 미리보기</button>
            <button className={buttonClass} disabled={locked || !actor.trim() || !reason.trim() || bundlePreview?.changeset_revision!==change.revision || !!bundlePreview?.error || !batch.every(id=>bundlePreview?.included_change_ids?.includes(id))} onClick={()=>decide("accept",batch,true)}>선택한 유형·관계 묶음 수락</button>
            <Schema title="선택 묶음 미리보기 · 기존 수락 항목 포함" value={bundlePreview}/>
          </div>}
        </section>
      </>}
      <section className={panelClass}><h3 className="font-semibold">업무 질문·허용 범위에 남은 공백</h3><p className="text-sm">후보나 근거가 연결됐다는 사실은 질문 해결을 뜻하지 않습니다. 전체 미탐색·자료 부족 기록을 특정 질문에 임의 배정하지 않습니다.</p>
        <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">질문·범위</th><th>저장된 조사 상태</th><th>현재 연결 후보·보류</th></tr></thead><tbody>{coverageRows(run,change).map(row => <tr key={`${row.kind}:${row.id}`} className="border-t"><td className="p-2">{row.question}</td><td className="p-2">{row.status}<p className="text-xs text-slate-600">{row.reason}</p></td><td className="p-2">후보 {row.candidates.length} · 보류 {row.deferred}<ul>{row.candidates.map(c => <li key={c.id}>{changeName(c)} · {label(c.review_status)}</li>)}</ul><KnowledgeMissingProposal request={request} run={run} change={change} question={row} onSaved={()=>loadChange(change.id)} disabled={locked}/></td></tr>)}</tbody></table></div>
        <ul className="list-inside list-disc text-sm text-amber-900">{strings(result.gaps).map((gap,i) => <li key={i}>{gap}</li>)}</ul>
        <JsonDetail title="자료 필요·후보 누락 의심·미탐색·실패의 저장 기록" value={{ reference_gaps: result.reference_gaps, unfulfilled_read_requests: result.unfulfilled_read_requests, mandatory_pending: result.mandatory_pending, unvisited_block_ids: result.unvisited_block_ids, unprocessed_features: result.unprocessed_features, failures: result.failures, revision_deferrals: result.revision_deferrals }} />
        <JsonDetail title="허용 범위 밖·불확실 발견 (수락 후보와 구분)" value={{ outside_scope: result.outside_scope, alignments: result.alignments }} />
        <JsonDetail title="개별 대상·값·사실 참고 표본 (온톨로지 수락과 구분)" value={change.reference_material} />
      </section>
      <section className={panelClass}><h3 className="font-semibold">검토 결정 이력 · {change.decisions.length}건</h3><ul className="space-y-3 text-sm">{change.decisions.map(d => <li key={d.id} className="border-b pb-2"><p>{label(d.action)} · {d.actor} · {new Date(d.created_at).toLocaleString("ko-KR")} · revision {d.revision}</p><p className="whitespace-pre-wrap">{d.reason}</p><p className="break-all text-xs">후보 {d.candidate_id} · 검토 버전 {d.ontology_version_id || "없음"}</p><JsonDetail title="이 결정의 수정 전후" value={{ before: d.before, after: d.after }} /></li>)}</ul></section>
      <Schema title="미승인 변경안 preview · 기각·보류·오류 제외" value={preview} />
      <Schema title="저장된 검토 버전 · 정본과 파생 결과" value={reviewed} />
    </>}
  </section>;
}

function HierarchyReview({ value, a, b }: { value: RecordValue; a: string; b: string }) {
  const reviews = [record(value.builder), ...records(value.critic)];
  return <div className="space-y-2 border-t pt-3"><h4 className="text-sm font-semibold">포함 관계의 양방향 검토 의견</h4>
    <p className="text-xs">판단 불가는 부정·비소속이 아닙니다. 양방향 지지도 자동 병합하지 않습니다.</p>
    {reviews.map((review,i) => <div key={i} className="space-y-1 text-sm"><p className="font-medium">{i === 0 ? "구조 제안 당시" : `반례 검토 당시 ${i}`}</p>{([['a_to_b',`${a}의 모든 대상은 ${b}에 포함됩니까?`],['b_to_a',`${b}의 모든 대상은 ${a}에 포함됩니까?`]] as const).map(([key,title]) => { const check = record(review[key]); return <div key={key}><p>{title} {label(display(check.judgment))}</p><p>{display(check.reason)}</p><JsonDetail title="이 판단의 근거·반례 ID" value={{ evidence: check.evidence_ids, counter_evidence: check.counter_evidence_ids }} /></div>; })}</div>)}
    {value.possible_equivalence === true && <p className="text-sm text-amber-900">양방향 지지에 따른 동치 검토 의견 · 개별 판단 필요</p>}
  </div>;
}

"use client";

import { useEffect, useState } from "react";

type Definition = { id: string; kind: string; name: string; definition: string; inclusion?: string; exclusion?: string; required?: boolean; unsupported_reason?: string };
type Contract = { ontology_version_id: string; review_id: string | null; target_ids: Record<string, string> };
type View = { contract: Contract; ontology_head_id: string | null; mapping_editable: boolean; review?: { actor: string; reason: string }; definitions: Definition[]; mapping_roles: Record<string, Omit<Definition, "id" | "name">>; unresolved_profile_ids: string[]; vocabulary_registry: unknown };
type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
const field = "w-full rounded border p-2 text-sm";

export default function KnowledgeConsumer({ id, request, predicates, onPredicates }: { id: string; request: Request; predicates: string[] | null; onPredicates: (ids: string[] | null) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [actor, setActor] = useState("local-user");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let stopped = false;
    request<View>(`/ontologies/${id}/consumer`).then(data => { if (!stopped) { setView(data); setMapping(data.contract.target_ids); } }).catch(e => { if (!stopped) setError(e.message); });
    return () => { stopped = true; };
  }, [id, request]);
  async function save() {
    if (!view) return;
    setBusy(true); setError("");
    try {
      const data = await request<View>(`/ontologies/${id}/consumer`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actor, reason,
        expected_review_id: view.contract.review_id, expected_ontology_head_id: view.ontology_head_id, target_ids: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)) }) });
      setView(data); setMapping(data.contract.target_ids); setReason("");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="space-y-3 rounded border p-3">
    <p className="text-sm">선택한 온톨로지에서 새 사실을 검토합니다. 과거 사실은 자동 승격되지 않으며 지식 버전 활성화는 별도입니다.</p>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {view && <>
      <label className="block text-sm"><input type="checkbox" checked={predicates !== null} onChange={e => onPredicates(e.target.checked ? [] : null)} /> 필요한 속성·관계만 부분 추출</label>
      {predicates !== null && <fieldset className="max-h-48 overflow-auto"><legend className="text-sm">아래 자료 선택과 함께 적용 · 최소 한 필드 선택</legend>{view.definitions.filter(d => ["attribute", "relation"].includes(d.kind)).map(d => <label key={d.id} className="block text-sm"><input type="checkbox" disabled={!!d.unsupported_reason} checked={predicates.includes(d.id)} onChange={e => onPredicates(e.target.checked ? [...predicates, d.id] : predicates.filter(i => i !== d.id))} /> {d.name} {d.required ? "· 필수" : ""} {d.unsupported_reason || ""}</label>)}</fieldset>}
      <details><summary className="cursor-pointer text-sm">LH 공식 필드의 의미 대응 검토 · 미연결 {view.unresolved_profile_ids.length}개</summary>
        <p className="my-2 text-xs">새 ID는 이름 유사도로 연결하지 않습니다. 정의·포함·제외 조건을 대조하고 대응 가능한 역할만 저장하세요. 빈 대응은 보류되며 다른 온톨로지 버전에 자동 적용하지 않습니다.</p>
        {Object.entries(view.mapping_roles).map(([original, expected]) => {
          const target = view.definitions.find(d => d.id === mapping[original]);
          return <div key={original} className="my-2 border-t py-2"><label className="block text-sm">{original} · {expected.definition}<select className={field} value={mapping[original] || ""} onChange={e => setMapping({ ...mapping, [original]: e.target.value })}><option value="">보류 · 대응 없음</option>{view.definitions.filter(d => d.kind === expected.kind && !d.unsupported_reason).map(d => <option key={d.id} value={d.id}>{d.name} · {d.id}</option>)}</select></label>
            <p className="text-xs">LH 포함: {expected.inclusion} / 제외: {expected.exclusion}</p>{target && <p className="whitespace-pre-wrap text-sm">선택 정의: {target.definition}<br />포함: {target.inclusion} / 제외: {target.exclusion}</p>}</div>;
        })}
        <label className="block text-sm">대응 검토자<input className={field} value={actor} onChange={e => setActor(e.target.value)} /></label>
        <label className="block text-sm">의미 대응·보류 사유<input className={field} value={reason} onChange={e => setReason(e.target.value)} /></label>
        <button type="button" className="mt-2 rounded border p-2 text-sm" disabled={busy || !view.mapping_editable || !actor.trim() || !reason.trim()} onClick={save}>이 버전의 의미 대응 저장</button>
        {!view.mapping_editable && <p className="text-xs">v1은 기존 LH 매핑을 유지합니다. 새 의미 대응은 검토된 v2에서 저장하세요.</p>}
        {view.review && <p className="text-xs">대응 검토: {view.review.actor} · {view.review.reason}</p>}
        <p className="text-xs">저장된 대응: {view.contract.review_id || "기존 ID와 정의가 동일한 대응만 사용"}</p>
      </details>
      <details><summary className="text-sm">같은 버전의 어휘·이전 ID 대응</summary><pre className="max-h-48 overflow-auto text-xs">{JSON.stringify(view.vocabulary_registry, null, 2)}</pre></details>
    </>}
  </div>;
}

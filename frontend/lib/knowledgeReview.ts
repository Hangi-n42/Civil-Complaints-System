export type KnowledgeRequest = <T>(path: string, init?: RequestInit) => Promise<T>;
export type RecordValue = Record<string, unknown>;
export type EvidenceRef = { evidence_id: string; block_id: string; source_version_id: string; parse_run_id: string; span: number[]; quote: string; locator: RecordValue };
export type Change = {
  id: string; change_id: string; target_id: string; symbol: string; target_kind: string; operation: string;
  before: RecordValue | null; after: RecordValue; qualifiers: RecordValue; support_type: string; rationale: string;
  evidence_refs: EvidenceRef[]; counter_evidence_refs: EvidenceRef[]; cq_ids: string[]; scope_item_ids: string[];
  unresolved_issues: unknown[]; hierarchy_review: RecordValue; origin: RecordValue; review_status: string;
  dependency_ids: string[]; affected_reference_ids: string[]; affected_references: RecordValue[]; can_accept: boolean;
  consumer_impact?: { action: string; affected_assertion_ids: string[]; requires_resolution: boolean; new_required: boolean };
  validation: { structural_errors: string[]; semantic_review: string[]; unresolved_dependency_ids: string[] };
};
export type Decision = { id: string; revision: number; candidate_id: string; action: string; actor: string; reason: string; created_at: string; before: Change; after: Change; ontology_version_id?: string };
export type Changeset = { id: string; revision: number; run_id: string; input_status: string; base_ontology_version_id: string | null; ontology_head_id: string | null; reviewed_ontology_version_id: string | null; unresolved_count: number; candidates: Change[]; original_candidates?: Change[]; decisions: Decision[]; analysis_result: RecordValue; reference_material: RecordValue[] };
export type CandidateResponse = { items: Change[]; changesets: Changeset[] };
export type DiscoveryRun = { id: string; status: string; started_at?: string; finished_at?: string; changeset_id?: string; stop_reason?: string; error?: string;
  cqs: { id: string; question: string }[]; scope_items: { id: string; question: string }[];
  frozen_input: { scope: string; step: number; files: { file_id: string; title: string; role?: string; source_version_id: string }[] };
  result?: RecordValue; metrics?: { llm_calls?: number; model_total_s?: number } };
export type RunSummary = { id: string; status: string; started_at?: string; scope: string; step: number; has_result: boolean; changeset_id?: string };
export type Ontology = { id?: string; changeset_revision?: number; status: string; linkml_yaml?: string; json_schema?: unknown; effective_class_slots?: Record<string, string[]>; vocabulary_registry?: RecordValue; targets?: RecordValue[]; candidates?: RecordValue[]; error?: string; included_change_ids?: string[]; excluded_change_ids?: string[] };
export type EditDraft = { after: string; qualifiers: string; target_kind: string; support_type: string; rationale: string; evidence_refs: string; counter_evidence_refs: string; cq_ids: string[]; scope_item_ids: string[]; unresolved_issues: string; hierarchy_review: string };
export const record = (v: unknown): RecordValue => v !== null && typeof v === "object" && !Array.isArray(v) ? v as RecordValue : {};
export const records = (v: unknown): RecordValue[] => Array.isArray(v) ? v.map(record) : [];
export const strings = (v: unknown): string[] => Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : [];
export const display = (v: unknown): string => typeof v === "string" ? v : v == null ? "미기록" : JSON.stringify(v);
export const pretty = (v: unknown) => JSON.stringify(v, null, 2);
export const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const reviewLabels: Record<string, string> = { source_extract: "원문 구간 추출", source_role: "출처 명제의 역할", synthesis: "근거 종합 설계", direct: "이전 직접 작성", maintained: "정상 의미 유지", corrected: "근거에 따른 정정", lost: "정상 의미 소실",
  fulfilled: "요구 충족", source_absent: "원문 자료 필요", scope_conflict: "적용 범위 재검토", extraction_missing: "누락 의미 재추출", endpoint: "관계 끝점 교정",
  human_edited_unclassified: "사람 수정 · 작성 성격 재확인", legacy_unspecified: "이전 기록 · 방식 미지정", partial: "일부 처리", review_ready: "초안 검수 준비", failed: "실패", cancelled: "취소됨", running: "실행 중", queued: "대기", cancel_requested: "취소 요청 중", unreviewed: "미검수", accepted: "수락", deferred: "보류", rejected: "기각", edit: "미승인 편집", accept: "수락", modify: "수정 후 수락", defer: "보류", reject: "기각", class: "유형", attribute: "특성", relation: "업무 관계", vocabulary_concept: "용어", hierarchy: "포함·부분 관계", alias: "다른 이름", add: "새 제안", update: "정의 변경", merge: "같은 대상으로 통합", deprecate: "현행 사용 중단", explicit: "원문 명시 제안", design_proposal: "설계 제안", unresolved: "판단 미정", supported: "지지", refuted: "반증", unknown: "판단 불가" };
export const label = (v: string) => ({ affirmed: "긍정 진술", negated: "부정 진술", definition: "정의", rule: "규칙 진술", instance: "개별 사실" }[v] || reviewLabels[v] || v);
export const changeName = (c: Change) => display(record(c.after).name ?? record(c.before).name ?? "이름 확인 필요");
export const canConvert = (run: Pick<RunSummary, "status" | "has_result">) => !!run.has_result && ["partial", "review_ready", "failed", "cancelled"].includes(run.status);

export function makeDraft(c: Change): EditDraft {
  return { after: pretty(c.after), qualifiers: pretty(c.qualifiers), target_kind: c.target_kind, support_type: c.support_type,
    rationale: typeof c.rationale === "string" ? c.rationale : "", evidence_refs: pretty(c.evidence_refs), counter_evidence_refs: pretty(c.counter_evidence_refs),
    cq_ids: strings(c.cq_ids), scope_item_ids: strings(c.scope_item_ids), unresolved_issues: pretty(c.unresolved_issues), hierarchy_review: pretty(c.hierarchy_review) };
}

export function editPatch(draft: EditDraft) {
  // Syntax only; the server owns evidence, kind, reference and canonical validation.
  return { ...draft, after: JSON.parse(draft.after), qualifiers: JSON.parse(draft.qualifiers), evidence_refs: JSON.parse(draft.evidence_refs),
    counter_evidence_refs: JSON.parse(draft.counter_evidence_refs), unresolved_issues: JSON.parse(draft.unresolved_issues), hierarchy_review: JSON.parse(draft.hierarchy_review) };
}

export function decisionBody(change: Changeset, actor: string, reason: string, action: string, ids: string[], draft?: EditDraft, reviewDependencies = false) {
  if (!actor.trim() || !reason.trim()) throw new Error("결정자와 판단 사유가 필요합니다.");
  if (!ids.length || new Set(ids).size !== ids.length || ids.some(id => !change.candidates.some(c => c.id === id))) throw new Error("결정 대상 후보를 확인하세요.");
  if (ids.length > 1 && ["edit", "modify"].includes(action)) throw new Error("각 후보의 편집을 따로 저장한 뒤 묶음을 수락하세요.");
  return { expected_changeset_revision: change.revision, expected_ontology_head_id: change.ontology_head_id, actor: actor.trim(),
    decisions: ids.map(candidate_id => ({ candidate_id, action, reason: reason.trim(), ...(reviewDependencies && ["accept", "modify"].includes(action) ? { consumer_action: "review_required" } : {}), ...((action === "edit" || action === "modify") && draft ? { patch: editPatch(draft) } : {}) })) };
}

export function connectionTargets(targets: RecordValue[], key: string, kind: string) {
  const classesOnly = key === "domain_id" || (key === "range" && ["relation", "attribute"].includes(kind));
  return targets.filter(t => !t.deprecated && (classesOnly ? ["class", "concept"] : ["class", "concept", "vocabulary_concept"]).includes(String(t.kind)));
}

export function manualAlignmentProposal(source: Change, target: RecordValue, preserveDefinition: boolean, reason: string) {
  if (!reason.trim() || !target.id || !["class", "vocabulary_concept"].includes(source.target_kind) ||
      (target.kind === "concept" ? "class" : target.kind) !== source.target_kind) throw new Error("같은 종류의 기존 대상과 대응 사유가 필요합니다.");
  const definition = preserveDefinition ? target : source.after;
  const after = Object.fromEntries(["name", "definition", "inclusion", "exclusion"].filter(k => k in definition).map(k => [k, definition[k]]));
  const evidence = [...readableRefs(target.evidence_refs), ...source.evidence_refs];
  const counters = [...(preserveDefinition ? readableRefs(target.counter_evidence_refs) : []), ...source.counter_evidence_refs];
  return { operation: "update", target_id: target.id, target_kind: source.target_kind, after,
    qualifiers: preserveDefinition ? record(target.qualifiers) : source.qualifiers,
    support_type: preserveDefinition ? target.support_type || source.support_type : source.support_type,
    evidence_refs: [...new Map(evidence.map(e => [JSON.stringify(e), e])).values()],
    counter_evidence_refs: [...new Map(counters.map(e => [JSON.stringify(e), e])).values()], cq_ids: source.cq_ids, scope_item_ids: source.scope_item_ids,
    rationale: reason.trim() };
}

export function groupChanges(candidates: Change[]) {
  const groups = new Map<string, Change[]>();
  for (const c of candidates) {
    const name = record(c.after).name ?? record(c.before).name;
    const key = typeof name === "string" && name.trim() ? `${c.target_kind}:${name.trim().toLocaleLowerCase()}` : c.id;
    groups.set(key, [...(groups.get(key) || []), c]);
  }
  return [...groups.values()];
}

export function readableRefs(value: unknown): EvidenceRef[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is EvidenceRef => v && ["evidence_id","block_id","source_version_id","parse_run_id","quote"].every(k => typeof v[k] === "string") &&
    Array.isArray(v.span) && v.span.length === 2 && v.span.every(Number.isInteger));
}

export function coverageRows(run: DiscoveryRun, change: Changeset) {
  const saved = records(change.analysis_result.coverage);
  return (["cq", "scope"] as const).flatMap(kind => (kind === "cq" ? run.cqs : run.scope_items).map(q => {
    const candidates = change.candidates.filter(c => strings(kind === "cq" ? c.cq_ids : c.scope_item_ids).includes(q.id));
    const entry = saved.find(v => v.id === q.id && v.kind === kind);
    return { kind, ...q, candidates, status: entry?.status === "evidence_linked" ? "생성 당시 근거 연결" : entry?.status === "gap" ? "자료 필요 또는 후보 누락" : "범위별 조사 상태 미기록", reason: display(entry?.reason),
      deferred: candidates.filter(c => c.review_status === "deferred").length };
  }));
}

// Python's stored spans count Unicode code points, not JavaScript UTF-16 units.
export function evidenceSpan(text: string, span: number[]) {
  const chars = Array.from(text), [start, end] = span;
  return { before: chars.slice(0, start).join(""), quote: chars.slice(start, end).join(""), after: chars.slice(end).join("") };
}

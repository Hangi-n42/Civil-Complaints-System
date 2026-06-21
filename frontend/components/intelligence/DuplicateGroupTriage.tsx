"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchDuplicateDraftReplyApi,
  fetchDuplicateReplyDraftApi,
  transitionDuplicateGroupApi,
  type DuplicateDraftReplyPayload,
  type DuplicateMergeRecord,
  type DuplicateMergeStatus,
  type DuplicateReplyDraft,
} from "@/lib/api";
import { loadCaseStatusOverrides, markCasesStatus, processedCaseCount } from "@/lib/caseStatus";
import {
  canCreateDraftReply,
  canGenerateDuplicateReplyDraft,
  duplicateCandidateGrade,
  duplicateCaseReviewRows,
  duplicateCommonPoints,
  duplicateDifferencePoints,
  duplicateGroupTitle,
  duplicatePreMergeChecklist,
  duplicateQueueContextLabel,
  duplicateReviewPriorityLabel,
  type DuplicateReviewTone,
  duplicateStatusLabel,
  duplicateStatusTone,
  evidenceLabel,
  representativeReasonLabel,
  riskFlagLabel,
  riskFlagTone,
} from "./duplicateMerge";
import { DuplicateReplyDraftPanel } from "./DuplicateReplyDraftPanel";

const STATUS_FILTERS: Array<{ value: "all" | DuplicateMergeStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "candidate", label: "추천 후보" },
  { value: "confirmed", label: "담당자 확정" },
  { value: "split", label: "분리됨" },
  { value: "rejected", label: "추천 기각" },
];

type ActionMessage = {
  type: "success" | "error" | "info";
  text: string;
};

export function DuplicateGroupTriage({
  groups,
  loading = false,
  focusedGroupId = null,
  issueAlertFilterId = null,
  onClearIssueAlertFilter,
  onGroupUpdated,
}: {
  groups: DuplicateMergeRecord[];
  loading?: boolean;
  focusedGroupId?: string | null;
  issueAlertFilterId?: string | null;
  onClearIssueAlertFilter?: () => void;
  onGroupUpdated?: (group: DuplicateMergeRecord) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<"all" | DuplicateMergeStatus>("all");
  const [riskOnly, setRiskOnly] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<ActionMessage | null>(null);
  const [draftPayload, setDraftPayload] = useState<DuplicateDraftReplyPayload | null>(null);
  const [replyDraft, setReplyDraft] = useState<DuplicateReplyDraft | null>(null);
  const [caseStatuses, setCaseStatuses] = useState<Record<string, string>>({});
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(focusedGroupId);

  const groupCaseIds = useMemo(() => {
    return Array.from(new Set(groups.flatMap((group) => group.member_complaint_ids)));
  }, [groups]);

  const filteredGroups = useMemo(() => {
    return groups
      .filter((group) => (statusFilter === "all" ? true : group.status === statusFilter))
      .filter((group) => (riskOnly ? group.risk_flags.length > 0 : true))
      .filter((group) => (issueAlertFilterId ? group.linked_issue_alert_ids.includes(issueAlertFilterId) : true))
      .sort((a, b) => {
        const confirmDelta = Number(b.allowed_actions.includes("confirm")) - Number(a.allowed_actions.includes("confirm"));
        if (!riskOnly && confirmDelta !== 0) return confirmDelta;
        const riskDelta = b.risk_flags.length - a.risk_flags.length;
        if (riskDelta !== 0) return riskDelta;
        return b.confidence - a.confidence;
    });
  }, [groups, issueAlertFilterId, riskOnly, statusFilter]);

  useEffect(() => {
    setCaseStatuses(loadCaseStatusOverrides(groupCaseIds));
  }, [groupCaseIds]);

  useEffect(() => {
    if (!focusedGroupId) return;
    setSelectedGroupId(focusedGroupId);
    const element = document.getElementById(`duplicate-group-${focusedGroupId}`);
    element?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedGroupId]);

  useEffect(() => {
    if (filteredGroups.length === 0) {
      if (selectedGroupId !== null) setSelectedGroupId(null);
      return;
    }
    if (!selectedGroupId || !filteredGroups.some((group) => group.merge_id === selectedGroupId)) {
      setSelectedGroupId(filteredGroups[0].merge_id);
    }
  }, [filteredGroups, selectedGroupId]);

  const selectedGroup = filteredGroups.find((group) => group.merge_id === selectedGroupId) ?? filteredGroups[0] ?? null;

  async function runTransition(group: DuplicateMergeRecord, action: "confirm" | "split" | "reject") {
    setBusyId(group.merge_id);
    setMessage(null);
    setDraftPayload(null);
    setReplyDraft(null);
    const response = await transitionDuplicateGroupApi(group.merge_id, action);
    setBusyId(null);
    if (response.error || !response.data) {
      setMessage({ type: "error", text: response.error?.message ?? "중복 그룹 상태 변경에 실패했습니다." });
      return;
    }
    onGroupUpdated?.(response.data.duplicate_group);
    setMessage({ type: "success", text: "중복 그룹 상태를 갱신했습니다." });
  }

  async function openDraftPayload(group: DuplicateMergeRecord) {
    setBusyId(group.merge_id);
    setMessage(null);
    setReplyDraft(null);
    const response = await fetchDuplicateDraftReplyApi(group.merge_id);
    setBusyId(null);
    if (response.error || !response.data) {
      setMessage({ type: "error", text: response.error?.message ?? "대표 답변 초안 자료를 가져오지 못했습니다." });
      return;
    }
    setDraftPayload(response.data.draft_reply_payload);
  }

  async function openReplyDraft(group: DuplicateMergeRecord) {
    setBusyId(group.merge_id);
    setMessage(null);
    setDraftPayload(null);
    setReplyDraft(null);
    const response = await fetchDuplicateReplyDraftApi(group.merge_id);
    setBusyId(null);
    if (response.error || !response.data) {
      if (response.error?.code === "DUPLICATE_GROUP_NOT_CONFIRMED") {
        setMessage({ type: "info", text: "담당자 확정 후에만 대표 답변 초안을 생성할 수 있습니다." });
      } else {
        setMessage({ type: "error", text: response.error?.message ?? "대표 답변 초안을 생성하지 못했습니다." });
      }
      return;
    }
    setReplyDraft(response.data.reply_draft);
  }

  function markReplyDraftProcessed(draft: DuplicateReplyDraft) {
    const nextStatuses = markCasesStatus(draft.member_complaint_ids, "처리완료");
    setCaseStatuses(nextStatuses);
    setMessage({
      type: "success",
      text: `중복 그룹 ${draft.member_complaint_ids.length}건을 처리완료로 기록했습니다.`,
    });
  }

  function selectGroup(groupId: string) {
    setSelectedGroupId(groupId);
    setDraftPayload(null);
    setReplyDraft(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 lg:flex-row lg:items-center lg:justify-end">
        {issueAlertFilterId && (
          <div className="flex flex-wrap items-center gap-2 lg:mr-auto">
            <span className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-bold text-blue-700">
              핫스팟 연결 후보
            </span>
            <button
              type="button"
              onClick={onClearIssueAlertFilter}
              className="text-[11px] font-bold text-slate-500 hover:text-slate-800"
            >
              필터 해제
            </button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap rounded-lg border border-slate-200 bg-slate-50 p-1" aria-label="중복 병합 상태 필터">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => setStatusFilter(filter.value)}
                className={
                  statusFilter === filter.value
                    ? "rounded-md bg-white px-3 py-1.5 text-xs font-extrabold text-slate-950 shadow-sm"
                    : "rounded-md px-3 py-1.5 text-xs font-bold text-slate-500 hover:bg-white hover:text-slate-800"
                }
              >
                {filter.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600">
            <input
              type="checkbox"
              checked={riskOnly}
              onChange={(event) => setRiskOnly(event.target.checked)}
              className="h-3.5 w-3.5 rounded border-slate-300"
            />
            주의 사유만
          </label>
        </div>
      </div>

      {message && (
        <div
          className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
            message.type === "success"
              ? "border-blue-200 bg-blue-50 text-blue-700"
              : message.type === "info"
                ? "border-amber-200 bg-amber-50 text-amber-700"
                : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {message.text}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          <div className="h-3 w-11/12 animate-pulse rounded bg-slate-200" />
          <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
          <div className="h-3 w-9/12 animate-pulse rounded bg-slate-200" />
        </div>
      ) : filteredGroups.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm font-medium text-slate-500">
          현재 조건에 맞는 중복 병합 그룹이 없습니다.
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
              <h3 className="text-sm font-extrabold text-slate-950">검토 큐</h3>
              <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">
                {filteredGroups.length}건
              </span>
            </div>
            <div className="max-h-[620px] space-y-2 overflow-y-auto p-2">
              {filteredGroups.map((group) => (
                <DuplicateGroupQueueItem
                  key={group.merge_id}
                  group={group}
                  selected={group.merge_id === selectedGroup?.merge_id}
                  onSelect={selectGroup}
                  processedCount={processedCaseCount(group.member_complaint_ids, caseStatuses)}
                />
              ))}
            </div>
          </section>

          <div className="min-w-0 space-y-3">
            {selectedGroup && (
              <DuplicateGroupDetail
                group={selectedGroup}
                busy={busyId === selectedGroup.merge_id}
                focused={selectedGroup.merge_id === focusedGroupId}
                onTransition={runTransition}
                onDraft={openDraftPayload}
                onReplyDraft={openReplyDraft}
                processedCount={processedCaseCount(selectedGroup.member_complaint_ids, caseStatuses)}
              />
            )}

            {draftPayload && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-blue-900">대표 답변 초안 자료</h3>
                    <p className="mt-0.5 text-xs text-blue-700">확정 그룹에 적용할 답변 검토용 요약 자료입니다.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDraftPayload(null)}
                    className="rounded-md border border-blue-200 bg-white px-2 py-1 text-xs font-bold text-blue-700"
                  >
                    닫기
                  </button>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-blue-900 md:grid-cols-3">
                  <div>대표 민원: {formatComplaintName(draftPayload.representative_complaint_id)}</div>
                  <div>대상 민원: {draftPayload.member_complaint_ids.length}건</div>
                  <div>주의 사유: {draftPayload.risk_flags.length}건</div>
                </div>
              </div>
            )}

            {replyDraft && (
              <DuplicateReplyDraftPanel
                replyDraft={replyDraft}
                processedCaseIds={replyDraft.member_complaint_ids.filter((caseId) => caseStatuses[caseId] === "처리완료")}
                onClose={() => setReplyDraft(null)}
                onMarkProcessed={() => markReplyDraftProcessed(replyDraft)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DuplicateGroupQueueItem({
  group,
  selected,
  onSelect,
  processedCount,
}: {
  group: DuplicateMergeRecord;
  selected: boolean;
  onSelect: (groupId: string) => void;
  processedCount: number;
}) {
  const candidateGrade = duplicateCandidateGrade(group);
  const riskCount = group.risk_flags.length;
  const allProcessed = processedCount === group.member_complaint_ids.length && group.member_complaint_ids.length > 0;

  return (
    <button
      id={`duplicate-group-${group.merge_id}`}
      type="button"
      onClick={() => onSelect(group.merge_id)}
      className={`w-full rounded-md border px-3 py-2 text-left transition ${
        selected ? "border-blue-400 bg-blue-50/70 ring-1 ring-blue-100" : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${duplicateStatusTone(group.status)}`}>
          {duplicateStatusLabel(group.status)}
        </span>
        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${candidateGrade.className}`}>
          {candidateGrade.label}
        </span>
      </div>
      <div className="line-clamp-2 text-xs font-extrabold leading-snug text-slate-950">{duplicateGroupTitle(group)}</div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-semibold text-slate-500">
        <span>{group.member_complaint_ids.length}건</span>
        <span>주의 {riskCount}건</span>
        {processedCount > 0 && <span className={allProcessed ? "text-blue-700" : "text-amber-700"}>처리 {processedCount}/{group.member_complaint_ids.length}</span>}
      </div>
      <div className="mt-2 text-[11px] font-extrabold text-slate-700">{nextActionLabel(group)}</div>
    </button>
  );
}

function DuplicateGroupDetail({
  group,
  busy,
  focused,
  onTransition,
  onDraft,
  onReplyDraft,
  processedCount,
}: {
  group: DuplicateMergeRecord;
  busy: boolean;
  focused: boolean;
  onTransition: (group: DuplicateMergeRecord, action: "confirm" | "split" | "reject") => void;
  onDraft: (group: DuplicateMergeRecord) => void;
  onReplyDraft: (group: DuplicateMergeRecord) => void;
  processedCount: number;
}) {
  const confirmAllowed = group.allowed_actions.includes("confirm");
  const splitAllowed = group.allowed_actions.includes("split");
  const rejectAllowed = group.allowed_actions.includes("reject");
  const draftAllowed = canCreateDraftReply(group);
  const replyDraftAllowed = canGenerateDuplicateReplyDraft(group);
  const queueContext = duplicateQueueContextLabel(group);
  const isCandidate = group.status === "candidate";
  const isConfirmed = group.status === "confirmed";
  const candidateGrade = duplicateCandidateGrade(group);
  const commonPoints = duplicateCommonPoints(group);
  const differencePoints = duplicateDifferencePoints(group);
  const checklist = duplicatePreMergeChecklist(group);
  const caseRows = duplicateCaseReviewRows(group);
  const allProcessed = processedCount === group.member_complaint_ids.length && group.member_complaint_ids.length > 0;
  const visibleRiskFlags = group.risk_flags.slice(0, 3);

  return (
    <article
      className={`rounded-lg border bg-white p-4 transition ${
        focused ? "border-blue-500 ring-2 ring-blue-100" : "border-slate-200"
      }`}
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${duplicateStatusTone(group.status)}`}>
              {duplicateStatusLabel(group.status)}
            </span>
            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${candidateGrade.className}`} title={candidateGrade.description}>
              {candidateGrade.label}
            </span>
            <span
              className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600"
              title="이 값은 중복 후보 검토 우선순위이며, 병합 가능성이나 법적 동일성을 보장하지 않습니다."
            >
              {duplicateReviewPriorityLabel(group)}
            </span>
            {processedCount > 0 && (
              <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${allProcessed ? "border-blue-200 bg-blue-50 text-blue-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}>
                처리완료 {processedCount}/{group.member_complaint_ids.length}
              </span>
            )}
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${queueContext.className}`}
              title={queueContext.title}
            >
              {queueContext.label}
            </span>
          </div>
          <h3 className="text-base font-extrabold text-slate-950">{duplicateGroupTitle(group)}</h3>
          <p className="mt-1 text-xs font-medium text-slate-500">
            대표 민원: {formatComplaintName(group.representative_complaint_id)}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 xl:max-w-sm">
          {candidateGrade.description}
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-xs font-extrabold text-slate-700">다음 처리</div>
            <div className="mt-1 text-[11px] font-semibold text-slate-500">{nextActionDescription(group, processedCount)}</div>
          </div>
          <div className="flex flex-wrap gap-2">
          {isCandidate && (
            <button
              type="button"
              disabled={busy || !confirmAllowed}
              onClick={() => onTransition(group, "confirm")}
              title={confirmAllowed ? "담당자 확정 처리" : "차단 위험이 있거나 추천 후보 상태가 아니어서 확정할 수 없습니다."}
              className={buttonClass(!busy && confirmAllowed, "primary")}
            >
              병합 확정
            </button>
          )}
          {isConfirmed && (
            <button
              type="button"
              disabled={busy || !replyDraftAllowed}
              onClick={() => onReplyDraft(group)}
              title={replyDraftAllowed ? "확정된 그룹의 대표 답변 초안을 생성합니다." : "담당자 확정 후 생성 가능"}
              className={buttonClass(!busy && replyDraftAllowed, "primary")}
            >
              {busy ? "생성 중..." : "답변 초안 생성"}
            </button>
          )}
          {isConfirmed && (
            <button
              type="button"
              disabled={busy || !draftAllowed}
              onClick={() => onDraft(group)}
              title={draftAllowed ? "대표 답변 초안 자료 보기" : "담당자 확정 후에만 초안 자료를 만들 수 있습니다."}
              className={buttonClass(!busy && draftAllowed, "secondary")}
            >
              초안 자료
            </button>
          )}
          {splitAllowed && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onTransition(group, "split")}
              className={buttonClass(!busy, "secondary")}
            >
              분리
            </button>
          )}
          {isCandidate && (
            <button
              type="button"
              disabled={busy || !rejectAllowed}
              onClick={() => onTransition(group, "reject")}
              className={buttonClass(!busy && rejectAllowed, "danger")}
            >
              기각
            </button>
          )}
          </div>
        </div>
      </div>

      {group.risk_flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {visibleRiskFlags.map((flag, index) => (
            <span key={`${group.merge_id}-${flag.code}-${index}`} className={`rounded-md border px-2 py-1 text-[11px] font-bold ${riskFlagTone(flag)}`}>
              {riskFlagLabel(flag)}
            </span>
          ))}
          {group.risk_flags.length > visibleRiskFlags.length && (
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-bold text-slate-500">
              +{group.risk_flags.length - visibleRiskFlags.length}
            </span>
          )}
        </div>
      )}

      <div className="mt-3">
        <div className="mb-2 text-xs font-extrabold text-slate-700">핵심 체크</div>
        <div className="grid gap-2">
          {checklist.map((item) => (
            <div key={item.label} className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 ${reviewToneClass(item.tone)}`}>
              <div className="text-[10px] font-bold opacity-70">{item.label}</div>
              <div className="text-right text-xs font-extrabold">{item.value}</div>
            </div>
          ))}
        </div>
      </div>

      <details className="mt-3 rounded-lg border border-slate-200 bg-white">
        <summary className="cursor-pointer px-3 py-2 text-xs font-extrabold text-slate-700">
          상세 근거 보기
        </summary>
        <div className="border-t border-slate-200 p-3">
          <div className="grid gap-3 text-xs text-slate-600 lg:grid-cols-2">
            <ReviewPanel title="공통점" tone="ok" items={commonPoints} />
            <ReviewPanel title="차이점·차단 신호" tone={group.risk_flags.some((flag) => flag.severity === "blocker") ? "blocker" : "review"} items={differencePoints} />
          </div>

          <div className="mt-3 rounded-lg bg-slate-50 p-3">
            <div className="mb-2 font-bold text-slate-500">민원별 확인표</div>
            <div className="max-h-48 overflow-y-auto rounded-md border border-slate-200 bg-white">
              <table className="w-full min-w-[520px] border-collapse text-left">
                <thead className="sticky top-0 bg-slate-50 text-[10px] font-bold text-slate-400">
                  <tr>
                    <th className="px-2 py-2">민원</th>
                    <th className="px-2 py-2">역할</th>
                    <th className="px-2 py-2">요청 유형</th>
                    <th className="px-2 py-2">확인</th>
                  </tr>
                </thead>
                <tbody>
                  {caseRows.map((row) => (
                    <tr key={row.complaintId} className="border-t border-slate-100">
                      <td className="max-w-[220px] px-2 py-2">
                        <div className="truncate font-semibold text-slate-700">{formatComplaintName(row.complaintId)}</div>
                      </td>
                      <td className="px-2 py-2">
                        <span className={row.role === "대표" ? "font-extrabold text-blue-700" : "text-slate-500"}>{row.role}</span>
                      </td>
                      <td className="px-2 py-2 text-slate-500">{row.requestType}</td>
                      <td className="px-2 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${reviewBadgeClass(row.tone)}`}>{row.attention}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
            <div className="mb-1 font-bold text-slate-500">병합 검토 근거</div>
            <ul className="space-y-1">
              {group.evidence.slice(0, 4).map((item, index) => (
                <li key={`${group.merge_id}-evidence-${index}`} className="line-clamp-1">
                  · {evidenceLabel(item)}
                </li>
              ))}
            </ul>
            <div className={`mt-3 text-sm font-extrabold ${allProcessed ? "text-blue-700" : "text-slate-800"}`}>
              처리완료 {processedCount}/{group.member_complaint_ids.length}건
            </div>
            <div className="mt-1 text-[11px] text-slate-400">대표 선정 기준: {representativeReasonLabel(group)}</div>
          </div>
        </div>
      </details>
    </article>
  );
}

function nextActionLabel(group: DuplicateMergeRecord): string {
  if (group.status === "candidate") {
    if (group.allowed_actions.includes("confirm")) return "다음: 병합 확정";
    if (group.allowed_actions.includes("split")) return "다음: 분리 검토";
    return "다음: 기각 검토";
  }
  if (group.status === "confirmed") {
    if (group.allowed_actions.includes("draft_reply")) return "다음: 답변 초안";
    return "확정됨";
  }
  if (group.status === "split") return "분리 처리됨";
  if (group.status === "rejected") return "기각 처리됨";
  return "상태 확인";
}

function nextActionDescription(group: DuplicateMergeRecord, processedCount: number): string {
  if (group.status === "candidate") {
    return group.allowed_actions.includes("confirm")
      ? "같은 사건으로 묶어도 되는지 확인한 뒤 확정합니다."
      : "차단 신호가 있어 확정 대신 분리 또는 기각을 먼저 검토합니다.";
  }
  if (group.status === "confirmed") {
    return processedCount > 0
      ? `답변 초안 검토 후 남은 ${Math.max(group.member_complaint_ids.length - processedCount, 0)}건을 처리합니다.`
      : "대표 답변 초안을 생성해 묶인 민원을 함께 처리합니다.";
  }
  if (group.status === "split") return "이 그룹은 분리되었으므로 개별 민원으로 처리합니다.";
  if (group.status === "rejected") return "이 추천은 기각되어 병합 처리 대상에서 제외되었습니다.";
  return "현재 상태를 확인하세요.";
}

function ReviewPanel({ title, tone, items }: { title: string; tone: DuplicateReviewTone; items: string[] }) {
  return (
    <div className={`rounded-lg border p-3 ${reviewToneClass(tone)}`}>
      <div className="mb-2 text-xs font-extrabold">{title}</div>
      <ul className="space-y-1">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="text-xs leading-relaxed">
            · {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatComplaintName(caseId: string): string {
  if (caseId.startsWith("dm-hotspot-noise")) return variedTitle(caseId, [
    "한빛아파트 공사 소음 신고",
    "한빛아파트 북문 진동 민원",
    "한빛아파트 야간 공사 소음 문의",
    "한빛아파트 공사장 방음 요청",
  ]);
  if (caseId.startsWith("dm-general-lamp")) return variedTitle(caseId, [
    "늘봄공원 가로등 고장 신고",
    "늘봄공원 산책로 조명 불량 민원",
    "늘봄공원 북문 보안등 점검 요청",
    "늘봄공원 야간 조도 개선 문의",
  ]);
  if (caseId === "dm-risk-parking-01") return "새빛초 후문 불법 주정차 단속 요청";
  if (caseId === "dm-risk-parking-02") return "새빛초 후문 주정차 보상 상담 요청";
  if (caseId.startsWith("dm-confirmed-library")) return variedTitle(caseId, [
    "온누리도서관 어린이실 냉난방기 고장 신고",
    "온누리도서관 열람실 온도 불편 민원",
    "온누리도서관 냉난방 점검 요청",
    "온누리도서관 실내 환경 개선 문의",
  ]);
  if (caseId.startsWith("demo-sinkhole_hotspot")) return variedTitle(caseId, [
    "을지로 보행로 꺼짐 안전 점검 요청",
    "을지로 도로 침하 임시 조치 요청",
    "을지로 보도 포트홀 확인 요청",
    "을지로 보행로 균열 보수 문의",
    "을지로 도로 파임 현장 확인 요청",
    "을지로 인근 보행 위험 신고",
    "을지로 노면 침하 보수 일정 문의",
    "을지로 보도블록 꺼짐 재점검 요청",
    "을지로 도로 안전 표지 설치 요청",
    "을지로 침하 구간 긴급 확인 요청",
  ]);
  if (caseId.startsWith("demo-illegal_parking_enforcement")) return variedTitle(caseId, [
    "가정초 후문 불법 주정차 단속 요청",
    "가정초 등교 시간 차량 정체 신고",
    "가정초 어린이보호구역 주차 단속 요청",
    "가정초 후문 통학로 차량 계도 요청",
    "가정초 주변 불법 주차 반복 신고",
    "가정초 후문 승하차 혼잡 정리 요청",
    "가정초 통학 안전 주정차 관리 요청",
    "가정초 후문 단속 안내 표지 요청",
    "가정초 주변 반복 주차 민원",
    "가정초 후문 교통지도 강화 요청",
  ]);
  if (caseId.startsWith("demo-bulky_waste_guidance")) return variedTitle(caseId, [
    "덕진동 대형폐기물 배출 신청 안내 요청",
    "덕진동 폐가구 수거 절차 문의",
    "덕진동 대형폐기물 스티커 구매 문의",
    "덕진동 폐가전 배출 방법 확인 요청",
    "덕진동 수거일 안내 부족 민원",
    "덕진동 대형폐기물 접수 경로 문의",
    "덕진동 폐기물 배출장소 안내 요청",
    "덕진동 스티커 부착 기준 문의",
    "덕진동 수거 신청 처리 확인 요청",
    "덕진동 대형폐기물 안내 개선 요청",
  ]);
  if (caseId.startsWith("demo-welfare_support_process")) return variedTitle(caseId, [
    "중촌동 복지 지원 신청 절차 안내 요청",
    "중촌동 복지 서류 준비 기준 문의",
    "중촌동 지원 대상 확인 요청",
    "중촌동 복지 신청 창구 안내 요청",
    "중촌동 생활지원 신청 방법 문의",
    "중촌동 복지 기준 설명 요청",
    "중촌동 지원 서류 보완 안내 요청",
    "중촌동 복지 접수 절차 개선 요청",
    "중촌동 지원 가능 여부 확인 요청",
    "중촌동 복지 상담 연결 요청",
  ]);
  if (caseId.startsWith("demo-odor_night_hotspot")) return variedTitle(caseId, [
    "삼산동 하수 악취 야간 현장 확인 요청",
    "삼산동 산책로 냄새 원인 점검 요청",
    "삼산동 하수구 악취 반복 신고",
    "삼산동 야간 악취 민원",
    "삼산동 오수 냄새 확인 요청",
    "삼산동 공장 인근 악취 점검 요청",
    "삼산동 배수로 냄새 개선 요청",
    "삼산동 새벽 악취 현장 확인 요청",
    "삼산동 생활 악취 원인 조사 요청",
    "삼산동 하수 악취 안내 요청",
  ]);
  // 이슈 #466 FE 확인 포인트 P4: 미등록 ID는 기술 ID(demo-*) 노출을 막기 위해 중립 라벨로 마스킹한다.
  return "민원 사례";
}

function variedTitle(caseId: string, titles: string[]): string {
  const index = Math.max(parseInt(suffix(caseId), 10) || 1, 1) - 1;
  return titles[index % titles.length];
}

function suffix(caseId: string): string {
  const match = caseId.match(/-(\d+)$/);
  return match ? match[1] : "";
}

function buttonClass(enabled: boolean, variant: "primary" | "secondary" | "danger"): string {
  if (!enabled) {
    return "cursor-not-allowed rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-400";
  }
  if (variant === "primary") {
    return "rounded-md border border-blue-600 bg-blue-600 px-3 py-1.5 text-xs font-extrabold text-white shadow-sm hover:bg-blue-700";
  }
  if (variant === "danger") {
    return "rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-50";
  }
  return "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50";
}

function reviewToneClass(tone: DuplicateReviewTone): string {
  if (tone === "blocker") return "border-red-200 bg-red-50 text-red-800";
  if (tone === "review") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function reviewBadgeClass(tone: DuplicateReviewTone): string {
  if (tone === "blocker") return "bg-red-100 text-red-700";
  if (tone === "review") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-600";
}

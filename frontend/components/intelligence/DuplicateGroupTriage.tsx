"use client";

import { useMemo, useState } from "react";
import {
  fetchDuplicateDraftReplyApi,
  transitionDuplicateGroupApi,
  type DuplicateDraftReplyPayload,
  type DuplicateMergeRecord,
  type DuplicateMergeStatus,
} from "@/lib/api";
import {
  canCreateDraftReply,
  duplicateGroupTitle,
  duplicateQueueContextLabel,
  duplicateStatusLabel,
  duplicateStatusTone,
  evidenceLabel,
  representativeReasonLabel,
  riskFlagLabel,
  riskFlagTone,
} from "./duplicateMerge";

const STATUS_FILTERS: Array<{ value: "all" | DuplicateMergeStatus; label: string }> = [
  { value: "all", label: "전체" },
  { value: "candidate", label: "추천 후보" },
  { value: "confirmed", label: "담당자 확정" },
  { value: "split", label: "분리됨" },
  { value: "rejected", label: "추천 기각" },
];

type ActionMessage = {
  type: "success" | "error";
  text: string;
};

export function DuplicateGroupTriage({
  groups,
  loading = false,
  issueAlertFilterId = null,
  onClearIssueAlertFilter,
  onGroupUpdated,
}: {
  groups: DuplicateMergeRecord[];
  loading?: boolean;
  issueAlertFilterId?: string | null;
  onClearIssueAlertFilter?: () => void;
  onGroupUpdated?: (group: DuplicateMergeRecord) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<"all" | DuplicateMergeStatus>("all");
  const [riskOnly, setRiskOnly] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<ActionMessage | null>(null);
  const [draftPayload, setDraftPayload] = useState<DuplicateDraftReplyPayload | null>(null);

  const filteredGroups = useMemo(() => {
    return groups
      .filter((group) => (statusFilter === "all" ? true : group.status === statusFilter))
      .filter((group) => (riskOnly ? group.risk_flags.length > 0 : true))
      .filter((group) => (issueAlertFilterId ? group.linked_issue_alert_ids.includes(issueAlertFilterId) : true))
      .sort((a, b) => {
        const riskDelta = b.risk_flags.length - a.risk_flags.length;
        if (riskDelta !== 0) return riskDelta;
        return b.confidence - a.confidence;
      });
  }, [groups, issueAlertFilterId, riskOnly, statusFilter]);

  async function runTransition(group: DuplicateMergeRecord, action: "confirm" | "split" | "reject") {
    setBusyId(group.merge_id);
    setMessage(null);
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
    const response = await fetchDuplicateDraftReplyApi(group.merge_id);
    setBusyId(null);
    if (response.error || !response.data) {
      setMessage({ type: "error", text: response.error?.message ?? "대표 답변 초안 자료를 가져오지 못했습니다." });
      return;
    }
    setDraftPayload(response.data.draft_reply_payload);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-base font-extrabold text-slate-900">중복 민원 병합 검토</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            추천 후보는 실제 민원 상태를 바꾸지 않습니다. 담당자가 확정한 그룹에서만 대표 답변 초안 자료를 만들 수 있습니다.
          </p>
          {issueAlertFilterId && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-bold text-blue-700">
                선택한 핫스팟에 연결된 후보만 보기
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
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-bold text-slate-500" htmlFor="duplicate-status-filter">
            상태
          </label>
          <select
            id="duplicate-status-filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as "all" | DuplicateMergeStatus)}
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
          >
            {STATUS_FILTERS.map((filter) => (
              <option key={filter.value} value={filter.value}>
                {filter.label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-xs font-semibold text-slate-600">
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
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {message.text}
        </div>
      )}

      {draftPayload && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-blue-900">대표 답변 초안 자료</h3>
              <p className="mt-0.5 text-xs text-blue-700">
                확정된 중복 그룹에 공통으로 적용할 답변을 검토하기 위한 안전한 요약 자료입니다.
              </p>
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
            <div>함께 검토할 민원: {draftPayload.member_complaint_ids.length}건</div>
            <div>주의 사유: {draftPayload.risk_flags.length}건</div>
          </div>
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
        <div className="space-y-3">
          {filteredGroups.map((group) => (
            <DuplicateGroupCard
              key={group.merge_id}
              group={group}
              busy={busyId === group.merge_id}
              onTransition={runTransition}
              onDraft={openDraftPayload}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DuplicateGroupCard({
  group,
  busy,
  onTransition,
  onDraft,
}: {
  group: DuplicateMergeRecord;
  busy: boolean;
  onTransition: (group: DuplicateMergeRecord, action: "confirm" | "split" | "reject") => void;
  onDraft: (group: DuplicateMergeRecord) => void;
}) {
  const confirmAllowed = group.allowed_actions.includes("confirm");
  const splitAllowed = group.allowed_actions.includes("split");
  const rejectAllowed = group.allowed_actions.includes("reject");
  const draftAllowed = canCreateDraftReply(group);
  const queueContext = duplicateQueueContextLabel(group);

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${duplicateStatusTone(group.status)}`}>
              {duplicateStatusLabel(group.status)}
            </span>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
              신뢰도 {(group.confidence * 100).toFixed(0)}%
            </span>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
              {group.member_complaint_ids.length}건
            </span>
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${queueContext.className}`}
              title={queueContext.title}
            >
              {queueContext.label}
            </span>
          </div>
          <h3 className="truncate text-sm font-extrabold text-slate-900">{duplicateGroupTitle(group)}</h3>
          <p className="mt-1 text-xs text-slate-500">
            대표로 볼 민원: {formatComplaintName(group.representative_complaint_id)} · {representativeReasonLabel(group)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy || !confirmAllowed}
            onClick={() => onTransition(group, "confirm")}
            title={confirmAllowed ? "담당자 확정 처리" : "차단 위험이 있거나 추천 후보 상태가 아니어서 확정할 수 없습니다."}
            className={buttonClass(confirmAllowed)}
          >
            확정
          </button>
          <button
            type="button"
            disabled={busy || !splitAllowed}
            onClick={() => onTransition(group, "split")}
            className={buttonClass(splitAllowed)}
          >
            분리
          </button>
          <button
            type="button"
            disabled={busy || !rejectAllowed}
            onClick={() => onTransition(group, "reject")}
            className={buttonClass(rejectAllowed)}
          >
            기각
          </button>
          <button
            type="button"
            disabled={busy || !draftAllowed}
            onClick={() => onDraft(group)}
            title={draftAllowed ? "대표 답변 초안 자료 보기" : "담당자 확정 후에만 초안 자료를 만들 수 있습니다."}
            className={buttonClass(draftAllowed)}
          >
            {draftAllowed ? "초안 자료 보기" : "확정 후 생성 가능"}
          </button>
        </div>
      </div>

      {group.risk_flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {group.risk_flags.map((flag, index) => (
            <span key={`${group.merge_id}-${flag.code}-${index}`} className={`rounded-md border px-2 py-1 text-[11px] font-bold ${riskFlagTone(flag)}`}>
              {riskFlagLabel(flag)}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 grid gap-3 text-xs text-slate-600 md:grid-cols-2">
        <div>
          <div className="mb-1 font-bold text-slate-500">함께 검토할 민원</div>
          <div className="line-clamp-2">{group.member_complaint_ids.map(formatComplaintName).join(", ")}</div>
        </div>
        <div>
          <div className="mb-1 font-bold text-slate-500">병합 검토 근거</div>
          <ul className="space-y-1">
            {group.evidence.slice(0, 2).map((item, index) => (
              <li key={`${group.merge_id}-evidence-${index}`} className="line-clamp-1">
                {evidenceLabel(item)}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  );
}

function formatComplaintName(caseId: string): string {
  if (caseId.startsWith("dm-hotspot-noise")) return `한빛아파트 공사 소음 신고 ${suffix(caseId)}`;
  if (caseId.startsWith("dm-general-lamp")) return `늘봄공원 가로등 고장 신고 ${suffix(caseId)}`;
  if (caseId === "dm-risk-parking-01") return "새빛초 후문 불법 주정차 단속 요청";
  if (caseId === "dm-risk-parking-02") return "새빛초 후문 주정차 보상 상담 요청";
  if (caseId.startsWith("dm-confirmed-library")) return `온누리도서관 냉난방기 고장 신고 ${suffix(caseId)}`;
  return `민원 ${caseId}`;
}

function suffix(caseId: string): string {
  const match = caseId.match(/-(\d+)$/);
  return match ? match[1] : "";
}

function buttonClass(enabled: boolean): string {
  return enabled
    ? "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50"
    : "cursor-not-allowed rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-400";
}

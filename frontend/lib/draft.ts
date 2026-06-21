// 이슈 #388: 공식 회신문(answer)과 분석 보조 메타데이터(structured_output)를 화면에서 분리한다.
// 편집 textarea에는 answer만 노출하고, summary/request_segments/action_items는 보조 UI에서만 표시한다.
// page.tsx에서 분리한 순수 로직 — 사이드이펙트가 없어 단위 테스트 대상이 된다.

export type DraftStage = "idle" | "loading" | "success" | "error";
export type SegmentViewMode = "loading" | "error" | "empty" | "single" | "multi";

export const DRAFT_ERROR_FALLBACK = "초안 생성 중 오류가 발생했습니다. 다시 시도해주세요.";

/**
 * 공식 회신문 편집 textarea에 들어갈 값을 만든다.
 * 분석용 메타데이터([복합 요청 모드]/Segment/Action/요약 등)는 절대 포함하지 않고 answer만 반환한다.
 */
export function buildDraftTextareaValue(params: { draftStage: DraftStage; answer?: string }): string {
  const { draftStage, answer } = params;

  // 로딩 표시는 DraftLoadingState(스켈레톤+단계 진행)가 담당하므로 편집값은 비운다.
  if (draftStage === "loading") {
    return "";
  }
  if (draftStage === "error") {
    return answer || DRAFT_ERROR_FALLBACK;
  }
  return answer || "";
}

/** request_segments 개수와 진행 단계로 보조 패널 표시 모드를 결정한다. */
export function computeSegmentViewMode(params: { draftStage: DraftStage; segmentCount: number }): SegmentViewMode {
  const { draftStage, segmentCount } = params;
  if (draftStage === "loading") return "loading";
  if (draftStage === "error") return "error";
  if (draftStage !== "success") return "empty";
  if (segmentCount > 1) return "multi";
  if (segmentCount === 1) return "single";
  return "empty";
}

/** 응답이 단일로 축소돼도 원본 민원에 명시된 복합 세그먼트가 있으면 그 기준을 우선한다. */
export function selectDraftRequestSegments(params: {
  responseSegments?: string[];
  fallbackSegments?: string[];
}): string[] {
  const responseSegments = normalizeSegments(params.responseSegments);
  const fallbackSegments = normalizeSegments(params.fallbackSegments);

  if (fallbackSegments.length > responseSegments.length && fallbackSegments.length > 1) return fallbackSegments;
  if (responseSegments.length > 1) return responseSegments;
  if (fallbackSegments.length > 1) return fallbackSegments;
  if (responseSegments.length > 0) return responseSegments;
  return fallbackSegments;
}

export type SupplementarySegment = {
  index: number;
  text: string;
  action?: string;
};

/** 보조 UI 렌더용으로 요청 세그먼트와 조치 항목을 순서대로 짝지어 준다. */
export function pairSegmentsWithActions(requestSegments: string[], actionItems: string[]): SupplementarySegment[] {
  return requestSegments.map((text, index) => ({
    index,
    text,
    action: actionItems[index],
  }));
}

// 이슈 #451: BE3(이슈 #450)가 structured_output.segment_answers로 요청별 답변·근거를 내려준다.
// 백엔드 계약(app/api/routers/generation.py _normalize_segment_answers):
//   { segment_index:int, request_segment:str, answer:str, case_ids:str[], evidence_status:"grounded"|"no_evidence" }
// FE는 표시 위주 — 이 순수 함수가 백엔드 배열을 카드로 정규화하고, 비면 빈 배열로 평면 answer 폴백을 유도한다.
export type SegmentAnswerCard = {
  index: number;
  requestSegment: string;
  answer: string;
  caseIds: string[];
  hasEvidence: boolean;
};

/** structured_output.segment_answers(구버전 응답엔 없음)를 화면 카드로 정규화한다. 배열이 아니거나 비면 []. */
export function normalizeSegmentAnswers(raw: unknown): SegmentAnswerCard[] {
  if (!Array.isArray(raw)) return [];
  const cards: SegmentAnswerCard[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const obj = item as Record<string, unknown>;
    const index = Number(obj.segment_index);
    if (!Number.isInteger(index) || index < 0) continue;
    const answer = String(obj.answer ?? "").trim();
    if (!answer) continue;
    const caseIds = Array.isArray(obj.case_ids)
      ? obj.case_ids.map((value) => String(value ?? "").trim()).filter(Boolean)
      : [];
    cards.push({
      index,
      requestSegment: String(obj.request_segment ?? "").trim(),
      answer,
      // 백엔드는 case_ids가 있을 때만 grounded로 표기하지만, 둘 중 하나만 충족해도 근거 있음으로 본다.
      hasEvidence: obj.evidence_status === "grounded" || caseIds.length > 0,
      caseIds,
    });
  }
  return cards;
}

// 이슈 #451 (선택): 오래된 검색 결과로 초안을 만드는 것을 막기 위한 쿼리 일치 검사.
// 서버가 query_hash를 주지 않으므로 FE가 쿼리 문자열을 정규화·해시해 비교한다(빈 쿼리는 "" → 비교 제외).
export function hashQuery(query: string): string {
  const normalized = String(query || "").trim().replace(/\s+/g, " ");
  if (!normalized) return "";
  let hash = 0;
  for (let i = 0; i < normalized.length; i += 1) {
    hash = (hash * 31 + normalized.charCodeAt(i)) | 0;
  }
  return `${normalized.length}:${hash}`;
}

/** 초안 생성에 쓰인 쿼리와 현재 화면 검색 결과의 쿼리가 다르면 stale(낡음)로 본다. 한쪽이라도 비면 판단 보류. */
export function isDraftStale(params: { draftQueryHash: string | null; searchQueryHash: string | null }): boolean {
  const { draftQueryHash, searchQueryHash } = params;
  if (!draftQueryHash || !searchQueryHash) return false;
  return draftQueryHash !== searchQueryHash;
}

function normalizeSegments(segments?: string[]): string[] {
  return (segments || [])
    .map((segment) => String(segment || "").split(/\s+/).join(" "))
    .filter(Boolean);
}

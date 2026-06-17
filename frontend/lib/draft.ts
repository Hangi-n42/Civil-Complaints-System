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

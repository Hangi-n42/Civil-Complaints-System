// 백엔드 DepartmentAssigner.assign() 산출물(담당부서 추천)의 FE 표시 헬퍼.
// confidence는 정답셋이 없는 "보정 안 된 상대 신호"이므로(백엔드 주석 참고)
// %가 아니라 정성 3단계로만 표기한다.

export type ResponsibleUnit = {
  name: string;
  confidence?: number;
  evidence?: string[];
  source?: string;
};

export type ConfidenceBand = { label: "높음" | "보통" | "낮음"; level: 1 | 2 | 3 };

export function confidenceBand(confidence?: number): ConfidenceBand {
  const c = typeof confidence === "number" && Number.isFinite(confidence) ? confidence : 0;
  if (c >= 0.6) return { label: "높음", level: 3 };
  if (c >= 0.3) return { label: "보통", level: 2 };
  return { label: "낮음", level: 1 };
}

// 가장 대표적인 근거 1건(최상위 일치 업무 문구)을 반환. 없으면 빈 문자열.
export function firstEvidence(unit?: ResponsibleUnit): string {
  const list = Array.isArray(unit?.evidence) ? unit!.evidence! : [];
  for (const e of list) {
    if (typeof e === "string" && e.trim()) return e.trim();
  }
  return "";
}

// 표시 가능한(이름이 있는) 후보만 추린다.
export function validResponsibleUnits(units?: ResponsibleUnit[]): ResponsibleUnit[] {
  return Array.isArray(units) ? units.filter((u) => u && typeof u.name === "string" && u.name.trim()) : [];
}

// 현재 배정(assignee)과 AI 추천 1순위를 비교한다.
// 자동 이관/판정이 아니라 담당자 판단 보조용이다. 배정명(팀/구)과 추천명(공식 부서)이
// 명명체계가 달라 다르게 나오는 경우가 많으므로, 결과는 "검토 안내"로만 쓴다.
export type AssignmentReview =
  | { status: "match"; current: string; suggested: string }
  | { status: "differ"; current: string; suggested: string }
  | { status: "unassigned"; suggested: string }
  | { status: "none" };

function normalizeDept(value?: string): string {
  return String(value || "").replace(/\s+/g, "");
}

export function reviewAssignment(assignee: string | undefined, units?: ResponsibleUnit[]): AssignmentReview {
  const top = validResponsibleUnits(units)[0];
  if (!top) return { status: "none" };
  const suggested = top.name;
  const current = String(assignee || "").trim();
  if (!current || current === "미지정") return { status: "unassigned", suggested };
  return normalizeDept(current) === normalizeDept(suggested)
    ? { status: "match", current, suggested }
    : { status: "differ", current, suggested };
}

// 추천 부서로 보내는 '이관 전달문' 초안을 만든다(템플릿 기반·결정적).
export type TransferMemoInput = {
  recommended: string;
  caseTitle?: string;
  observation?: string;
  request?: string;
  currentUnit?: string;
  confidenceLabel?: string;
  evidence?: string;
};

export function buildTransferMemo(input: TransferMemoInput): string {
  const recommended = input.recommended.trim();
  const from = (input.currentUnit || "").trim() || "미지정";
  const title = (input.caseTitle || "").trim() || "(제목 없음)";
  const observation = (input.observation || "").trim() || "-";
  const request = (input.request || "").trim() || "-";
  const evidence = (input.evidence || "").trim();
  const band = (input.confidenceLabel || "").trim();

  const lines = [
    "[민원 이관 요청]",
    "",
    `수신: ${recommended} (귀 부서)`,
    `발신: ${from}`,
    "",
    `1. 민원 건명: ${title}`,
    `2. 이관 사유: 본 민원은 검토 결과 「${recommended}」 소관 사항으로 판단되어 이관합니다.`,
    "3. 민원 요지:",
    `   - 관찰: ${observation}`,
    `   - 요청: ${request}`,
  ];
  if (evidence) lines.push(`4. 판단 근거: ${evidence}`);
  lines.push("");
  lines.push(`※ 본 이관 의견은 AI 추천${band ? `(신뢰도 ${band})` : ""}을 참고한 담당자 검토 결과이며, 귀 부서 확인을 요청드립니다.`);
  return lines.join("\n");
}

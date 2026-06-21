# Duplicate Merge Reply Draft FE Handoff

기준일: 2026-06-21
범위: 중복 민원 후보 생성, 담당자 확정, confirmed 그룹 대표 답변 초안 생성까지의 FE 연결 계약

## 1. 기능 목적

Duplicate Merge Recommendation Layer는 같은 사건으로 반복 접수된 민원을 담당자가 빠르게 검토하도록 돕는 보조 기능이다.

FE에서 반드시 지켜야 할 원칙은 다음과 같다.

- `candidate`는 추천 후보이며, 담당자 확정 전까지 실제 민원 상태를 바꾸지 않는다.
- `confirmed`는 담당자가 내부 검토 단위로 확정한 read-model 상태이며, 실제 민원 상태 변경이나 자동 병합이 아니다.
- 대표 답변 초안은 `confirmed` 그룹에서만 생성할 수 있다.
- 생성된 답변은 자동 발송 대상이 아니라 담당자 검토용 초안이다.
- 답변 초안 화면에는 `requires_human_review: true`를 명확히 표시한다.
- 민원 원문 전체나 실제 개인정보를 FE에서 임의로 조합하거나 재노출하지 않는다.

## 2. 확인한 현재 FE 구조

현재 FE는 Next.js App Router 기반이며, 중복 병합 기본 화면은 이미 민원 인텔리전스 탭에 들어가 있다.

- `frontend/lib/api.ts`
  - `DuplicateMergeRecord`, `DuplicateRiskFlag`, `DuplicateEvidence`, `DuplicateDraftReplyPayload` 타입이 있다.
  - `fetchDuplicateGroupsApi`, `transitionDuplicateGroupApi`, `fetchDuplicateDraftReplyApi`가 있다.
  - 현재 답변 관련 client는 `/draft-reply` payload 조회까지만 연결되어 있다.
- `frontend/components/intelligence/duplicateMerge.ts`
  - 상태 라벨, risk flag 업무 문구, evidence 문구, `canCreateDraftReply()` helper가 있다.
  - `canCreateDraftReply()`는 `status === "confirmed"`와 `allowed_actions.includes("draft_reply")`를 함께 본다.
- `frontend/components/intelligence/DuplicateGroupTriage.tsx`
  - 중복 병합 전용 triage queue다.
  - 상태 필터, 주의 사유 필터, confirm/split/reject, `초안 자료 보기`가 구현되어 있다.
  - 현재 버튼은 `/draft-reply` payload를 표시한다.
- `frontend/app/intelligence/page.tsx`
  - `실시간 이슈`, `행정 인사이트`, `중복 병합` 탭을 제공한다.
  - IssueAlert/Hotspot에서 중복 그룹 탭으로 필터 이동할 수 있다.
- `frontend/app/page.tsx`
  - 메인 민원 목록에서 중복 상태 badge를 보조 정보로 표시한다.

이번 문서의 권장 구현은 기존 구조를 유지하면서 `/reply-draft` client, 타입, 결과 패널을 추가하는 것이다.

## 3. 현재 BE 기능 범위

현재 BE는 다음 기능을 제공한다.

- 중복 민원 `candidate` group 생성
- 대표 민원 자동 선정
- 병합 근거 `evidence` 제공
- 병합 위험 사유 `risk_flags` 제공
- `allowed_actions` / `blocked_actions` 제공
- `candidate -> confirmed`
- `candidate -> split`
- `candidate -> rejected`
- `confirmed -> split`
- `/draft-reply`: confirmed 그룹의 PII-safe BE3 전달 payload 생성
- `/reply-draft`: confirmed 그룹 대상 BE2 검색 + BE3 대표 답변 초안 생성
- 검색 결과가 없거나 검색 실패 시 담당자 검토용 fallback 초안 생성
- 초안 사후 점검 결과 `safety_warnings` 제공

MVP 범위 밖:

- 자동 병합
- 실제 민원 상태 자동 변경
- 실제 답변 자동 발송
- 외부 행정 시스템 연동
- DB migration 기반 영구 저장

## 4. API Endpoint 목록

공통 응답 envelope:

```json
{
  "success": true,
  "request_id": "req-...",
  "timestamp": "2026-06-21T00:00:00Z",
  "data": {}
}
```

중복 그룹 endpoint:

```http
POST /complaint-intelligence/duplicate-groups/run-analysis
GET  /complaint-intelligence/duplicate-groups?status=candidate|confirmed|split|rejected
GET  /complaint-intelligence/duplicate-groups?complaint_id={case_id}
GET  /complaint-intelligence/duplicate-groups?issue_alert_id={alert_id}
GET  /complaint-intelligence/duplicate-groups?public_insight_id={insight_id}
GET  /complaint-intelligence/duplicate-groups/{merge_id}
POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm
POST /complaint-intelligence/duplicate-groups/{merge_id}/split
POST /complaint-intelligence/duplicate-groups/{merge_id}/reject
POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply
POST /complaint-intelligence/duplicate-groups/{merge_id}/reply-draft
```

상태 충돌 응답:

- `candidate`, `split`, `rejected`에서 `/draft-reply` 또는 `/reply-draft`를 호출하면 `409`.
- 대표 오류 코드는 `DUPLICATE_GROUP_NOT_CONFIRMED`.
- FE는 409를 일반 장애처럼만 보지 말고, "담당자 확정 후 생성 가능" 안내로 처리한다.

## 5. `/draft-reply`와 `/reply-draft` 차이

두 endpoint는 이름이 비슷하므로 FE에서 문구를 반드시 구분한다.

### `/draft-reply`

역할:

- 실제 답변 문장을 생성하지 않는다.
- BE3에 넘길 PII-safe 입력 payload를 확인한다.
- 대표 민원 요약, 함께 검토할 민원 요약, 병합 근거, risk flag, 공통 답변 제약, 금지 조건을 보여준다.

응답 위치:

```text
data.draft_reply_payload
```

권장 FE 문구:

- 버튼: `초안 자료 보기`
- 패널 제목: `대표 답변 초안 자료`
- 설명: `확정된 중복 그룹에 공통으로 적용할 답변을 검토하기 위한 민감정보 제외 요약 자료입니다.`

### `/reply-draft`

역할:

- confirmed 그룹에서만 실제 대표 답변 초안을 생성한다.
- Duplicate 전용 context를 만들고, BE2 검색 결과를 거쳐 BE3 `duplicate_group` prompt mode로 답변을 생성한다.
- 검색 근거가 없거나 검색 호출이 실패하면 안전 fallback 초안을 반환한다.
- 항상 담당자 검토가 필요하다.

응답 위치:

```text
data.reply_draft
```

권장 FE 문구:

- 버튼: `대표 답변 초안 생성`
- 패널 제목: `담당자 검토용 대표 답변 초안`
- 고정 배지: `자동 발송 아님`
- 고정 배지: `담당자 검토 필요`

## 6. 상태별 FE 동작 규칙

| status | FE 표시명 | 기본 의미 | 가능한 화면 동작 |
| --- | --- | --- | --- |
| `candidate` | 추천 후보 | 담당자 검토 전 추천 상태 | confirm/split/reject는 `allowed_actions` 기준, 답변 생성 버튼 숨김 또는 disabled |
| `confirmed` | 담당자 확정 그룹 | 내부 검토 단위 확정 | `/draft-reply`, `/reply-draft` 진입 가능 |
| `split` | 분리됨 | 하나의 그룹으로 보지 않음 | 답변 생성 불가 |
| `rejected` | 추천 기각 | 추천을 사용하지 않음 | 답변 생성 불가 |

FE action gating 규칙:

- 버튼 활성화는 반드시 `allowed_actions` 기준으로 한다.
- `blocked_actions`는 disabled 사유나 tooltip에 사용한다.
- 답변 생성 계열 버튼은 `status === "confirmed"`일 때만 보여준다.
- candidate에서 답변 생성 버튼을 보여야 하는 UI라면 반드시 disabled 처리하고 tooltip을 `담당자 확정 후 생성 가능`으로 둔다.
- `/reply-draft` 호출 후에도 실제 발송 버튼과 연결하지 않는다.

현재 BE의 action enum은 `confirm | split | reject | draft_reply`이다. `/reply-draft`는 같은 confirmed-only 답변 생성 영역으로 보되, FE helper 이름은 혼동 방지를 위해 `canGenerateDuplicateReplyDraft()`처럼 새로 두는 것을 권장한다.

## 7. 주요 Response Field 설명

### `DuplicateMergeRecord`

- `merge_id`: 후보/확정/분리/기각 상태 전체에서 유지되는 그룹 ID
- `status`: `candidate | confirmed | split | rejected`
- `representative_complaint_id`: 대표 민원 ID
- `member_complaint_ids`: 함께 검토할 민원 ID 목록
- `representative`: 대표 민원 선정 정보
- `confidence`: 후보 정렬과 참고용 신뢰도
- `recommendation_level`: `weak | review | strong`
- `evidence`: 왜 묶였는지에 대한 근거
- `risk_flags`: 병합 전 또는 답변 전 확인해야 할 위험 사유
- `allowed_actions`: 현재 상태에서 가능한 작업
- `blocked_actions`: 현재 상태에서 막힌 작업
- `linked_issue_alert_ids`: 연결된 IssueAlert ID
- `linked_public_insight_ids`: 연결된 PublicAgencyInsight ID
- `location_state`: `exact | nearby | ambiguous | missing | conflict`
- `request_types`: 민원별 요청 유형 분류

### `reply_draft`

- `reply_draft.answer`: 담당자 검토용 대표 답변 초안 본문
- `reply_draft.citations`: 생성에 사용된 검색 근거
- `reply_draft.limitations`: 답변 적용 한계 또는 검토 조건
- `reply_draft.safety_warnings`: PII, 자동발송, 보상 확정 등 사후 경고 코드
- `reply_draft.requires_human_review`: 항상 `true`로 취급하고 화면에 표시
- `reply_draft.generation_metadata`: fallback 여부, 검색 결과 수, 검색 실패 여부 등 생성 메타데이터
- `reply_draft.search_results`: FE 표시용으로 정리된 검색 결과
- `reply_draft.draft_reply_payload`: `/draft-reply`와 같은 PII-safe payload

## 8. FE 타입/API Client 권장 추가

`frontend/lib/api.ts`에 다음 타입과 client 함수를 추가하는 것을 권장한다.

```ts
export type DuplicateReplyDraft = {
  merge_id: string;
  representative_complaint_id: string;
  member_complaint_ids: string[];
  requires_human_review: boolean;
  answer: string;
  citations: Array<Record<string, unknown>>;
  limitations: string[];
  structured_output: Record<string, unknown>;
  generation_metadata: Record<string, unknown>;
  safety_warnings: string[];
  query: string;
  routing_hint: Record<string, unknown>;
  routing_trace: Record<string, unknown>;
  search_results: Array<Record<string, unknown>>;
  draft_reply_payload: DuplicateDraftReplyPayload;
};

export async function fetchDuplicateReplyDraftApi(
  mergeId: string,
): Promise<ApiResponse<{ reply_draft: DuplicateReplyDraft } | null>> {
  try {
    const payload = await fetchBackend<{ reply_draft: DuplicateReplyDraft }>(
      `/complaint-intelligence/duplicate-groups/${encodeURIComponent(mergeId)}/reply-draft`,
      { method: "POST" },
    );
    return { data: payload, error: null };
  } catch (error) {
    return { data: null, error: toApiError(error) };
  }
}
```

권장 helper:

```ts
export function canGenerateDuplicateReplyDraft(group: DuplicateMergeRecord): boolean {
  return group.status === "confirmed" && group.allowed_actions.includes("draft_reply");
}
```

## 9. UI/UX 연결 설계

### A. 메인 민원 처리 대시보드

민원 row 또는 상세 패널에 중복 상태 badge를 보조 정보로 표시한다.

권장 badge:

- `중복 후보 있음`
- `담당자 확정 그룹`
- `주의 필요`

클릭 동작:

- row의 기본 업무 흐름은 유지한다.
- badge 또는 보조 링크를 클릭하면 중복 그룹 상세 drawer/panel 또는 민원 인텔리전스 중복 병합 탭으로 이동한다.
- 메인 대시보드에서 바로 답변 초안을 생성하지 말고, 그룹 상세에서 상태와 risk를 확인한 뒤 생성하도록 한다.

### B. Complaint Intelligence / Hotspot 화면

기존 `IssueAlert`/Hotspot 카드와 지도에는 중복 후보 수가 표시된다.

권장 섹션:

- 제목: `이 핫스팟 내 반복 민원 후보`
- 표시 내용: 연결 그룹 수, 가장 높은 risk flag, 대표 민원 제목, member count
- CTA: `중복 후보 보기`

핫스팟은 여러 사건의 집합일 수 있으므로, evidence/risk를 함께 보여 "하나의 반복 사건인지", "여러 사건이 같은 키워드로 묶인 것인지" 판단할 수 있게 한다.

### C. 중복 민원 병합 전용 탭

현재 `DuplicateGroupTriage`가 이 역할을 수행한다.

권장 필터:

- 상태: `candidate | confirmed | split | rejected`
- risk flag
- linked issue alert
- linked public insight

권장 정렬:

- confirm 가능한 후보 우선
- blocker/warning risk 많은 그룹 우선
- confidence 높은 그룹 우선
- 최근 접수순

전용 탭은 triage queue로 사용하고, 실제 답변 초안 생성은 group detail 또는 card action에서 confirmed 상태일 때만 노출한다.

### D. 그룹 상세 화면

상단:

- status
- recommendation_level
- confidence
- member count
- linked hotspot/insight badge

본문:

- 대표 민원 영역
- 함께 검토할 민원 목록
- evidence 목록
- risk_flags 목록
- allowed/blocked action

액션:

- candidate: `확정`, `분리`, `기각`
- confirmed: `초안 자료 보기`, `대표 답변 초안 생성`, `분리`
- split/rejected: 읽기 전용

### E. 답변 초안 결과 패널

`/reply-draft` 성공 후 별도 패널 또는 drawer로 표시한다.

필수 표시:

- `answer`
- `requires_human_review` 경고 배지
- `자동 발송 아님` 경고 배지
- `limitations`
- `safety_warnings`
- `citations`
- fallback 안내

fallback 표시 규칙:

- `generation_metadata.fallback_used === true`이면 상단에 경고를 노출한다.
- `NO_SEARCH_CONTEXT`: `검색 근거가 부족해 안전 초안이 생성되었습니다.`
- `RETRIEVAL_ERROR`: `검색 실패로 담당자 검토용 안전 초안이 생성되었습니다.`

## 10. Risk Flag 표시 가이드

코드를 그대로 노출하지 말고 업무 언어로 변환한다.

| code | 권장 문구 |
| --- | --- |
| `LOCATION_MISMATCH` | 장소가 달라 병합 주의 |
| `LOCATION_AMBIGUOUS` | 장소 근거 부족 |
| `REQUEST_TYPE_MISMATCH` | 요청 유형이 달라 개별 검토 필요 |
| `DEPARTMENT_MISMATCH` | 담당 부서 충돌 |
| `SAFETY_AND_INCONVENIENCE_MIXED` | 안전 위험과 단순 불편 혼합 |
| `LEGAL_RIGHTS_OR_DEADLINE_RISK` | 권리관계/처리기한 차이 가능 |
| `PII_RISK` | 개인정보 포함 가능성 |
| `MULTI_INTENT_SEGMENTS` | 여러 요구가 섞여 있음 |
| `SEMANTIC_ONLY_MATCH` | 요약 유사도 중심 근거 |
| `LOW_EVIDENCE` | 구조화 근거 부족 |
| `TIME_WINDOW_TOO_WIDE` | 접수 시간 간격이 넓음 |

표시 원칙:

- `blocker`는 붉은 계열, `warning`은 주의 계열, `info`는 중립 계열로 표시한다.
- 색상만 쓰지 말고 텍스트 라벨을 함께 둔다.
- risk flag가 있으면 답변 초안 생성 결과에도 "검토 조건 있음"을 표시한다.

## 11. Safety Warnings 표시 가이드

`safety_warnings`는 답변 초안 사후 점검 결과다. 완전한 보안 검사가 아니라 담당자 확인 신호로 표시한다.

| code | 권장 문구 |
| --- | --- |
| `PII_PHONE` | 초안 내 전화번호 의심 표현 확인 필요 |
| `PII_EMAIL` | 초안 내 이메일 의심 표현 확인 필요 |
| `PII_DETAILED_ADDRESS` | 초안 내 상세주소 의심 표현 확인 필요 |
| `AUTO_SEND_PROMISE` | 자동 발송으로 오해될 표현 확인 필요 |
| `AUTO_MERGE_PROMISE` | 자동 병합/일괄 처리로 오해될 표현 확인 필요 |
| `COMPENSATION_PROMISE` | 보상 확정 표현 확인 필요 |
| `DEADLINE_CHANGE_PROMISE` | 처리기한 확정 표현 확인 필요 |
| `NO_SEARCH_CONTEXT` | 검색 근거 부족 |
| `RETRIEVAL_ERROR` | 검색 실패로 안전 초안 사용 |
| `RISK_FLAGS_PRESENT` | 병합 주의 사유가 있는 그룹 |

표시 원칙:

- warning이 있으면 초안 본문 위에 접을 수 있는 경고 영역을 둔다.
- PII 관련 warning은 담당자가 발송 전 반드시 본문을 확인하도록 강조한다.
- warning이 없더라도 `requires_human_review`는 계속 표시한다.

## 12. 권장 구현 순서

1. `DuplicateReplyDraft` 타입 추가
2. `fetchDuplicateReplyDraftApi()` 추가
3. `canGenerateDuplicateReplyDraft()` helper 추가
4. `DuplicateGroupTriage` 또는 그룹 상세 컴포넌트에 confirmed-only `대표 답변 초안 생성` 버튼 추가
5. `/draft-reply` payload 패널과 `/reply-draft` 결과 패널 문구 분리
6. `DuplicateReplyDraftPanel` 컴포넌트 추가
7. `safety_warnings` label helper 추가
8. fallback 상태 표시 추가
9. loading/empty/error/409 상태 처리
10. 상태별 rendering 테스트 추가

## 13. 테스트 권장 사항

FE 테스트에서 확인할 것:

- candidate에서는 `대표 답변 초안 생성` 버튼이 hidden 또는 disabled
- candidate에서 `/reply-draft` 409가 오면 "담당자 확정 후 생성 가능"으로 안내
- confirmed에서는 `대표 답변 초안 생성` 버튼 enabled
- split/rejected에서는 답변 생성 불가
- `requires_human_review` 표시
- `자동 발송 아님` 표시
- `safety_warnings` 표시
- `NO_SEARCH_CONTEXT` fallback 안내 표시
- `RETRIEVAL_ERROR` fallback 안내 표시
- `citations`와 `limitations` 렌더링
- evidence/risk_flags 업무 문구 렌더링
- 좁은 화면에서 badge/action 영역이 overflow되지 않음

BE 계약 회귀 테스트는 현재 다음을 포함한다.

- candidate `/draft-reply` 409
- confirmed `/draft-reply` payload 생성
- candidate `/reply-draft` 409
- confirmed `/reply-draft` 생성 흐름
- 구성 민원 검색 결과 제외
- 검색 근거 없음 fallback
- 검색 실패 fallback
- PII/자동발송/보상확정 warning

## 14. 남은 리스크

- 실제 LLM 답변 품질은 운영 검색 인덱스와 prompt 결과에 의존한다.
- `safety_warnings`는 완전한 보안 검사가 아니라 사후 경고다.
- confirmed는 내부 read-model 상태이며 실제 민원 상태 변경이 아니다.
- FE가 `/draft-reply`와 `/reply-draft`를 혼동하면 "자료 보기"와 "문장 생성" UX가 섞일 수 있다.
- `allowed_actions`에는 현재 `draft_reply`만 있으므로 `/reply-draft` 버튼도 같은 confirmed-only 조건을 쓰되, helper 이름과 버튼 문구는 분리해야 한다.
- 검색 실패 fallback은 업무 중단을 막기 위한 안전 초안이므로, 정상 검색 기반 초안보다 낮은 신뢰도로 표시해야 한다.


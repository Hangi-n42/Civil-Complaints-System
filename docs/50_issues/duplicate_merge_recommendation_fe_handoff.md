# Duplicate Merge Recommendation UI/UX FE Handoff

기준일: 2026-06-21
범위: Duplicate Merge Recommendation Layer 운영 전 UI/UX 연결, BE-FE contract, 담당자 검토 흐름

## 1. 기능 목적

중복 민원 병합 기능은 같은 사건으로 반복 접수된 민원을 자동 확정하지 않고, 담당자에게 "추천 후보"로 제시하는 보조 검토 기능이다. MVP에서는 실제 민원 상태 변경, 자동 병합, 자동 일괄 발송을 하지 않는다.

담당자는 후보 그룹을 검토한 뒤 `confirm`, `split`, `reject` 중 하나를 선택한다. 대표 답변 초안 payload는 담당자가 `confirmed`로 확정한 그룹에서만 생성할 수 있다.

## 2. 현재 BE Contract 요약

공통 응답 envelope:

```json
{
  "success": true,
  "request_id": "req-...",
  "timestamp": "2026-06-21T00:00:00Z",
  "data": {}
}
```

API endpoint:

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
```

`draft-reply`는 `status == confirmed`인 경우에만 허용된다. candidate, split, rejected에서 호출하면 409와 `DUPLICATE_GROUP_NOT_CONFIRMED`가 반환된다.

## 3. 상태 표시 규칙

| status | FE 표시명 | 담당자 의미 | draft-reply |
| --- | --- | --- | --- |
| `candidate` | 추천 후보 | 담당자 검토 필요 | 비활성화, "확정 후 생성 가능" |
| `confirmed` | 담당자 확정 그룹 | 병합 검토 단위 확정 | 활성화 가능 |
| `split` | 분리됨 | 하나로 처리하지 않음 | 비활성화 |
| `rejected` | 추천 기각 | 추천을 사용하지 않음 | 비활성화 |

FE는 `status`와 `allowed_actions`를 함께 확인한다. 버튼은 `allowed_actions`에 있을 때만 활성화한다. `blocked_actions`는 disabled 사유 표시나 툴팁에 사용한다.

## 4. 주요 Response Field

`DuplicateMergeRecord` 주요 필드:

- `merge_id`: 후보/확정/분리/기각 상태 전체에서 같은 그룹 ID
- `status`: `candidate | confirmed | split | rejected`
- `representative_complaint_id`: 대표 민원 ID
- `member_complaint_ids`: 그룹 멤버 민원 ID 목록
- `confidence`: 후보 정렬과 참고용 신뢰도
- `recommendation_level`: `weak | review | strong`
- `evidence`: 왜 묶였는지에 대한 근거
- `risk_flags`: 확정 전 확인해야 할 위험 사유
- `allowed_actions`: 현재 상태에서 가능한 작업
- `blocked_actions`: 현재 상태에서 막힌 작업
- `linked_issue_alert_ids`: 연결된 IssueAlert ID
- `linked_public_insight_ids`: 연결된 PublicAgencyInsight ID
- `representative.selection_reason`: 대표 민원 선정 이유

## 5. 현재 FE 구현 요약

추가/연결된 FE 요소:

- `frontend/lib/api.ts`
  - duplicate group 타입 정의
  - `fetchDuplicateGroupsApi`
  - `transitionDuplicateGroupApi`
  - `fetchDuplicateDraftReplyApi`
- `frontend/components/intelligence/duplicateMerge.ts`
  - 상태 라벨, risk flag 업무 문구, draft 가능 여부, 민원 row 배지 helper
- `frontend/components/intelligence/DuplicateGroupTriage.tsx`
  - 중복 병합 전용 triage queue
  - 상태 필터, 주의 사유 필터
  - confirm/split/reject/draft action gating
- `frontend/app/intelligence/page.tsx`
  - "중복 병합" 탭 추가
  - IssueAlert 카드에 연결된 중복 그룹 수 표시
- `frontend/app/page.tsx`
  - 메인 민원 목록에 중복 상태 배지 표시

## 6. 메인 민원 처리 대시보드 사용 방식

메인 민원 목록은 담당자의 기존 업무 시작점이다. 여기서는 중복 병합을 별도 작업으로 밀어붙이지 않고, row 수준의 보조 배지만 표시한다.

배지 우선순위:

1. `confirmed` 포함: "확정 그룹"
2. blocker risk 포함: "주의 필요"
3. 그 외 관련 그룹: "중복 후보 있음"
4. 관련 그룹 없음: `-`

row 클릭은 기존처럼 workbench로 이동한다. 배지는 업무 흐름을 방해하지 않는 보조 신호로만 사용한다.

## 7. 핫스팟/Complaint Intelligence 연결 방식

IssueAlert 카드에는 `linked_issue_alert_ids` 기준으로 연결된 중복 그룹 수를 작게 표시한다.

설계 의도:

- 핫스팟 화면에서는 "이 지역/시설/이슈에 반복 민원 후보가 있다"는 신호만 빠르게 보여준다.
- 실제 병합 판단은 "중복 병합" 탭의 triage queue에서 한다.
- 핫스팟이 하나의 사건 반복인지 여러 사건 집합인지 헷갈릴 수 있으므로, 카드 안에 병합 상세를 과하게 넣지 않는다.

PublicAgencyInsight도 `linked_public_insight_ids`로 같은 방식의 연결이 가능하다. 필요하면 인사이트 상세 패널에 연결 그룹 수를 추가할 수 있다.

## 8. 중복 민원 병합 전용 탭

"중복 병합" 탭은 triage queue다.

기본 표시:

- 상태 badge: 추천 후보 / 담당자 확정 그룹 / 분리됨 / 추천 기각
- 신뢰도
- 멤버 민원 수
- 대표 민원 ID와 선정 이유
- risk flag
- member complaint IDs
- evidence 상위 2개
- confirm / split / reject / draft payload 버튼

필터:

- 상태: 전체, 추천 후보, 담당자 확정, 분리됨, 기각됨
- 주의 사유만 보기

액션 규칙:

- `confirm`: `candidate`이고 blocker risk가 없을 때만 활성화
- `split`: `candidate` 또는 `confirmed`에서 활성화
- `reject`: `candidate`에서만 활성화
- `draft_reply`: `confirmed`이고 `allowed_actions`에 있을 때만 활성화

## 9. Risk Flag 표시 가이드

FE는 code를 그대로 노출하지 않고 업무 문구로 표시한다.

| code | 표시 문구 |
| --- | --- |
| `LOCATION_MISMATCH` | 장소가 다를 수 있음 |
| `LOCATION_AMBIGUOUS` | 장소 근거 부족 |
| `REQUEST_TYPE_MISMATCH` | 요청 유형 혼합 |
| `DEPARTMENT_MISMATCH` | 담당 부서 충돌 |
| `SAFETY_AND_INCONVENIENCE_MIXED` | 안전 위험과 단순 불편 혼합 |
| `LEGAL_RIGHTS_OR_DEADLINE_RISK` | 권리관계/처리기한 주의 |
| `PII_RISK` | 개인정보 확인 필요 |
| `MULTI_INTENT_SEGMENTS` | 복수 요구 포함 |
| `SEMANTIC_ONLY_MATCH` | 의미 유사도 중심 근거 |
| `LOW_EVIDENCE` | 구조화 근거 부족 |
| `TIME_WINDOW_TOO_WIDE` | 접수 시간 간격 큼 |

severity 색상:

- `blocker`: 빨간 경고. confirm 차단
- `warning`: 주황 주의. 담당자 검토 필요
- `info`: 회색 보조 설명

## 10. Evidence 표시 가이드

`evidence`는 "왜 묶였는지"를 설명하는 근거다. 목록 카드에서는 상위 1~2개만 보여주고, 상세 UI에서는 전체를 펼쳐 볼 수 있게 한다.

권장 표시:

- semantic similarity: 참고 점수
- location: 장소 상태
- request type: 요청 유형 비교
- duplicate score: 정렬용 종합 점수

중요: score는 병합 허가 조건이 아니다. hard gate와 risk flag가 우선이다.

## 11. 대표 민원/멤버 민원 표시 가이드

대표 민원:

- `representative_complaint_id`
- `representative.selection_reason`
- `representative.quality_score`

멤버 민원:

- `member_complaint_ids`
- 필요하면 `GET /duplicate-groups/{merge_id}`로 상세 갱신
- 원문 전체를 FE에서 요구하지 않는다.

## 12. 빈 상태, 로딩 상태, 에러 상태

빈 상태:

- "현재 조건에 맞는 중복 병합 그룹이 없습니다."

로딩 상태:

- 기존 인텔리전스 화면과 같은 skeleton row를 사용한다.

에러 상태:

- duplicate group 조회 실패는 인텔리전스 대시보드 전체 실패가 아니다.
- "중복 병합 그룹을 불러오지 못했습니다. 기존 인텔리전스 대시보드는 계속 사용할 수 있습니다."로 안내한다.

409 상태:

- `DUPLICATE_GROUP_NOT_CONFIRMED`는 정상적인 상태 보호 응답이다.
- candidate에서 draft payload를 만들 수 없다는 의미로 보여준다.

## 13. 접근성/반응형 고려사항

- 상태와 위험도는 색상뿐 아니라 텍스트로도 표시한다.
- action button에는 disabled 상태와 title을 제공한다.
- 좁은 화면에서는 카드형 triage queue가 우선이며, 메인 목록은 기존 overflow-x table 구조를 유지한다.
- 긴 evidence와 member IDs는 줄임 처리하고 상세 패널에서 확장하는 구조를 권장한다.

## 14. 아직 남은 BE/FE 리스크

- 현재 저장소는 MVP 원칙에 따라 DB migration 없는 read-model 중심이다.
- 실제 운영 데이터 기준으로 linked issue alert / public insight 품질을 추가 검증해야 한다.
- 1000건 replay batch는 정상 종료됐지만, peak group size가 커질 수 있어 운영 서버 동시성 검증이 필요하다.
- 부서 alias 사전은 holdout에서 확인된 좁은 범위만 반영되어 있다.
- draft payload는 BE3 전달용 payload이며, 실제 답변 문장 생성 UI는 후속 작업이다.

## 15. 검증 참고

최근 검증 기준:

- 100쌍 synthetic evaluation
- 300건 real/replay holdout + 200쌍 labeled evaluation
- 500건/1000건 batch performance evaluation
- duplicate merger API tests
- Complaint Intelligence tests
- FE helper tests

관련 리포트:

- `reports/duplicate_merge_labeled_eval_report.md`
- `reports/duplicate_merge_followup_hardening_report.md`
- `reports/duplicate_merge_real_holdout_eval_report.md`
- `reports/duplicate_merge_batch_performance_report.md`

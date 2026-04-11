# Week6 BE3 스펙 동기화 변경 공지 (팀 공유용)

작성일: 2026-04-11  
작성자: BE3

## 1) 배경

현재 코드는 유지하고, 문서만 실제 구현 기준으로 동기화했습니다.
목적은 FE/BE1/BE2/QA가 문서 기준으로 작업할 때 혼선을 줄이는 것입니다.

## 2) 수정 파일

- docs/60_specs/api_interface_spec.md
- docs/60_specs/data_schema_spec.md
- docs/60_specs/ui_workbench_spec.md

## 3) 핵심 변경 사항

### A. API Interface Spec 정렬

1. `/search` request
- `complaint_id`: required -> optional
- `filters.topic_type`, `session_context`: 예시에서 제거
- `request_id`: optional 필드 설명 추가

2. `/search` response
- `routing_hint`에 `strategy_id`, `route_key` 포함 명시
- `retrieved_docs` 예시를 실제 반환 구조(`rank`, `case_id`, `chunk_id`, `summary`, `metadata.route_key` 등) 기준으로 보강

3. `/qa` request
- `retrieved_docs` 기반 예시 -> `use_search_results + search_results` 기반 예시로 변경

4. Error Schema
- 메시지 예시: `routing_hint.route_key is required` -> `routing_hint is required`
- `retryable: true` -> `retryable: false`
- 본문 스키마 파싱 실패 시 `VALIDATION_ERROR + HTTP 422` 가능성 주석 추가

### B. Data Schema Spec 정렬

1. topic_type 도메인
- `safety` -> `construction`으로 통일
- Pydantic/TypeScript/WorkbenchListItem 예시 모두 동일 적용

2. RoutingTrace
- 구현 반영을 위해 `request_segments`(optional) 명시

### C. UI Workbench Spec 정렬

1. QA 호출 절차
- `/search` 연계 시 `use_search_results=true`, `search_results[]` 전달 규칙 추가

2. API 연동 계약(UI 관점)
- `/qa` 요청 권장 전송 필드에 `use_search_results`, `search_results` 추가

## 4) 팀별 영향

- FE:
  - `/qa` 호출 payload를 `search_results` 기준으로 맞추면 문서/코드 불일치가 사라집니다.
  - 400/422 에러 처리 분기를 같이 고려해주세요.

- BE1/BE2:
  - topic_type 값은 `construction` 기준으로 사용해주세요.
  - routing_trace 확장 필드(`request_segments`) 소비 시 optional 처리 권장합니다.

- QA:
  - 문서의 에러 메시지/retryable 기준이 코드와 일치하도록 업데이트되었습니다.

## 5) 비고

- 이번 변경은 코드 로직 변경 없이 문서만 정렬한 작업입니다.
- 기존 테스트 결과에는 영향이 없습니다.


## 6) BE3 interface문서 수정 내용(추가 반영: diff 체크리스트 106~146)

수정일: 2026-04-11

참조 원문:
- docs/40_delivery/week6/WEEK6_BE3_DOC_RESPONSE_DIFF_CHECKLIST.md

수정 파일:
- docs/10_contracts/interfaces/week5/week5_be3_interface.md
- docs/10_contracts/interfaces/week6/week6_be3_interface.md

반영 항목:
1. Week5 `/qa` 누락 검증 메시지 예시를 실제 구현과 동일하게 수정
- 기존: `routing_hint.route_key is required`
- 변경: `routing_hint is required`

2. Week5 에러 코드 목록을 실제 구현 기준으로 동기화
- 기존: `SEARCH_PIPELINE_ERROR`, `QA_PIPELINE_ERROR`
- 변경: `BAD_REQUEST`, `INDEX_NOT_READY`, `INTERNAL_SERVER_ERROR`

3. Week5 공통 실패 포맷의 `retryable` 값을 실제 검증 에러 동작으로 정정
- 기존: `true`
- 변경: `false`

4. Week6 PromptFactory 입력 예시에서 `request_segments` 위치를 구현 기준으로 정렬
- 기존: top-level `request_segments`
- 변경: `routing_trace.request_segments`

5. Week6 계승 규칙에 전략 불일치 검증 규칙 명시 추가
- 추가: `route_key/strategy_id` 불일치 시 `ROUTING_STRATEGY_INCONSISTENT`

6. Week6 에러 계약 상태코드 정렬
- 기존 문서: `ROUTING_STRATEGY_INCONSISTENT (500)`
- 변경 문서: `ROUTING_STRATEGY_INCONSISTENT (400)`

7. Week6 실패 예시 문구/재시도 여부 동기화
- 메시지: `routing_hint is required`
- `retryable`: `false`

8. Week6 검증 보충 주석 추가
- 요청 본문 스키마 파싱 실패 시 `VALIDATION_ERROR (422)` 가능성 명시

코드 정렬(문서 일치 목적):
- app/api/error_utils.py의 `ROUTING_STRATEGY_INCONSISTENT` 기본 상태코드를 `400`으로 조정

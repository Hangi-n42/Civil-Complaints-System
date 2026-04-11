# Week6 BE3 문서-실응답 Diff 체크리스트

작성일: 2026-04-11  
범위:
- 문서: docs/10_contracts/interfaces/week5/week5_be3_interface.md
- 문서: docs/10_contracts/interfaces/week6/week6_be3_interface.md
- 이슈: docs/50_issues/week5/task_04_be3_search_trace.md
- 이슈: docs/50_issues/week6/task_04_be3_prompt_normalize_unified_output.md
- 구현: app/api/routers/retrieval.py
- 구현: app/api/routers/generation.py
- 구현: app/generation/prompts/prompt_factory.py
- 구현: app/generation/normalization/response_normalizer.py
- 구현: app/api/error_utils.py

---

## 1) Diff 체크리스트

### A. Week5 /search 계약

- [x] success/request_id/timestamp/data 공통 래퍼 유지
- [x] data.strategy_id 포함
- [x] data.route_key 포함
- [x] data.routing_hint 포함
- [x] data.routing_trace 포함
- [x] data.retrieved_docs 포함
- [x] retrieved_docs[].metadata.strategy_id 포함
- [x] retrieved_docs[].metadata.route_key 포함

판정: 구현 일치

### B. Week5 /qa 입력/출력 골격

- [x] complaint_id/query/routing_hint 입력 경로 존재
- [x] routing_hint 누락 시 명시적 검증 에러 반환
- [x] 출력에 routing_trace 포함
- [x] 출력에 structured_output 포함
- [x] 출력에 answer/citations/limitations 포함
- [x] 출력에 latency_ms/quality_signals 포함
- [x] search.strategy_id == qa.strategy_id 유지
- [x] search.route_key == qa.route_key 유지

판정: 구현 일치(골격 기준)

### C. Week6 PromptFactory/정규화

- [x] PromptFactory.build(query, context, routing_trace) 구현
- [x] topic_type 기반 지시문 반영
- [x] complexity_level 기반 지시문 반영
- [x] request_segments 기반 분할 지시문 반영
- [x] normalize_response(payload) 구현
- [x] citations doc_id/source/quote 구조 정규화
- [x] limitations 문자열 배열 강제
- [x] 응답 직전 계약 검증(validate_unified_contract) 존재

판정: 구현 일치

### D. 문구/값 1:1 동기화(엄격 비교)

- [ ] 에러 코드별 HTTP 상태값 완전 일치
- [ ] 실패 응답 retryable 값 완전 일치
- [ ] 누락 필드 에러 메시지 예시 완전 일치
- [ ] PromptFactory 입력 예시 구조와 함수 입력 경로 완전 일치
- [ ] route_key/strategy_id 계승 정의(의미) 완전 일치

판정: 일부 불일치 존재

---

## 2) 불일치 항목 1:1 표

| No | 기준 문서 항목 | 문서 기대값 | 실제 구현값 | 영향 | 권장 정렬 방향 |
|---|---|---|---|---|---|
| 1 | Week6 에러 계약: ROUTING_STRATEGY_INCONSISTENT | 500 | /api/v1/qa에서 400으로 반환 | FE/QA가 상태코드 기반 분기 시 오동작 가능 | 문서 400으로 수정 또는 라우터를 500으로 조정 |
| 2 | Week6 실패 예시: VALIDATION_ERROR retryable | true | /api/v1/qa 검증 실패는 retryable=false | 재시도 UX 안내 문구 불일치 | 문서 retryable=false로 수정 권장 |
| 3 | Week5 실패 예시 메시지 | routing_hint.route_key is required | routing_hint 누락 시 routing_hint is required | QA 스크립트의 문자열 assert 불일치 | 문서 예시를 실제 메시지로 동기화 |
| 4 | Week6 PromptFactory 입력 예시 | request_segments가 routing_trace 바깥(top-level)에도 존재 | 실제 함수는 routing_trace 내부 request_segments를 사용 | 설계 해석 혼선 | 문서 입력 예시를 routing_trace.request_segments 중심으로 정리 |
| 5 | Week6 계승 규칙 설명 | search 단계 값 계승(동일성 중심) | 구현은 동일성 저장 + 형식 일치 검증(불일치 시 에러) | BE1/BE2 연동 시 검증 책임 경계 모호 | 문서에 불일치 검증 규칙을 명시적으로 추가 |
| 6 | Week5 에러 코드 목록 | SEARCH_PIPELINE_ERROR, QA_PIPELINE_ERROR 중심 | 실제는 BAD_REQUEST, INDEX_NOT_READY, INTERNAL_SERVER_ERROR 등 사용 | 운영 대시보드/로그 분류 기준 불일치 | 문서 에러 코드 표를 실제 코드 기준으로 갱신 |
| 7 | Week6 VALIDATION_ERROR 상태값 | 400(문서) | 본문 파싱 단계(스키마 누락)는 422 핸들러 경로 가능 | 클라이언트에서 400/422 혼선 | 문서에 "스키마 검증 422 가능" 주석 추가 |

---

## 3) 정렬 우선순위 제안

1. FE/QA 영향 큰 항목 먼저 정렬
- No 1, 2, 7

2. 문서 해석 혼선 제거
- No 4, 5

3. 운영/로그 계약 정리
- No 6

4. 예시 문구 정밀 동기화
- No 3

---

## 4) 결론

- 기능 구현 관점: Week5/Week6 핵심 요구사항은 충족.
- 문서-실응답 1:1 동기화 관점: 위 7개 항목은 정렬 필요.
- 특히 상태코드(400/422/500)와 retryable 값은 FE 에러 처리와 직접 연결되므로 우선 조치 권장.

## 5) 문서 수정 내용

수정일: 2026-04-11

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

# BE2 단일 RAG 완전 적용 체크리스트 (BE3)

문서 버전: v1.0  
작성일: 2026-04-14

## 1) 계약 정합성 체크 (Week4 기준)

- [x] `/search -> /qa` 요청 연계 가능 (`request_id` 전달/계승)
- [x] `routing_hint` 필수 검증 및 strategy/route_key 일관성 검증
- [x] `citations`가 검색 컨텍스트(`chunk_id`, `case_id`)와 매핑되도록 정규화
- [x] 파싱 재시도 실패 시 `QA_PARSE_ERROR`로 표준화
- [x] `limitations` 비어있을 때 기본 안전 문구 보강

## 2) 적용 파일 맵

- API 검색 라우터: `app/api/routers/retrieval.py`
- API 생성 라우터: `app/api/routers/generation.py`
- QA 요청 스키마: `app/api/schemas/generation.py`
- 검색/생성 서비스: `app/retrieval/service.py`, `app/generation/service.py`
- API 벤치 연계: `scripts/Be3_run_week6_model_benchmark.py`

## 3) 이번 반영 사항 (2026-04-14)

- [x] `QARequest`에 `request_id` 필드 추가
- [x] `/qa`에서 `request.request_id`를 우선 사용하도록 반영
- [x] API 벤치마크 경로에서 `/search` 응답 `request_id`를 `/qa` 요청으로 전달

## 4) 검증 시나리오

1. API 서버 기동 후 `/search` 호출
2. `/search` 응답의 `request_id` 확인
3. 동일 `request_id`를 `/qa` 요청에 전달
4. `/qa` 성공/실패 응답에서 동일 `request_id` 확인
5. `citations[].chunk_id/case_id`가 검색 결과 trace와 일치하는지 샘플 검증

## 5) 미적용/주의 항목

- [ ] direct 모드 벤치마크는 API 체인을 우회하므로 단일 RAG 완전 적용 검증 대상이 아님
- [ ] Week4 계약의 `data.limitations` 타입(string)과 현재 unified payload(list) 사용 관행은 추가 통합 검토 필요

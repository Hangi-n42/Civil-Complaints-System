# Week4 Structured/Metadata Quality Checklist (BE1)

- 기준 인터페이스: `docs/10_contracts/interfaces/week4/week4_be1_interface.md`
- 산출 이슈: #134
- 체크 시각: 2026-04-08T14:20:00+09:00
- 샘플 데이터: `reports/week2_entity_audit/week2_structured_sample_10.json`

## 1) Checklist

| 영역 | 항목 | 규칙 | 결과 | 근거 |
| --- | --- | --- | --- | --- |
| 구조화 | observation/result/request/context 존재 | 4요소 필수 | PASS | 샘플 10건 모두 키 존재 |
| 메타데이터 | region 결측 허용 여부 | 결측 허용 불가 | FAIL | `unknown`/`-` 포함 10/10 |
| 메타데이터 | category 결측 허용 여부 | 결측 허용 불가 | FAIL | `unknown`/`-` 포함 8/10 |
| 메타데이터 | created_at 존재 | 결측 허용 불가 | PASS | 공백 0/10 |
| 시각 포맷 | created_at KST(+09:00) | ISO-8601 +09:00 강제 | FAIL | +09:00 suffix 0/10 |
| 시각 포맷 | structured_at KST(+09:00) | ISO-8601 +09:00 강제 | FAIL | +09:00 suffix 0/10 |
| 검색 연계 | chunk/case trace 연결 | QARequest-SearchResult 연결 가능 | CONDITIONAL | 실행 로그에서 request_id trace 검증 필요 |

## 2) Summary Metrics

- sample_count: 10
- missing_region_like: 10
- missing_category_like: 8
- missing_created_at: 0
- created_at_kst_suffix: 0
- structured_at_kst_suffix: 0

## 3) Action Items

1. region/category 정규화 매핑 강제 (`unknown`, `-` 금지)
2. created_at/structured_at를 `+09:00` 형식으로 재직렬화
3. Gate A 실행 로그에 request_id trace 필수 기록

## 4) Handoff

- BE2: 검색 필터 입력 전 region/category 정규화 여부 검증
- BE3: QA 생성 결과의 citation trace와 request_id 매칭 로그 노출
- FE: 데모 표시 시 metadata 결측/포맷 오류 배너 처리

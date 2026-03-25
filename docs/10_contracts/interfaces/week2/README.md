# Week 2 인터페이스 문서 인덱스

기준일: 2026-03-25  
적용 범위: Week 2 (`ingest -> structure -> validate`) 계약 고정 + search/qa 실연동

## 1) 목적

Week 2 구현 중 변수명, 포맷, 객체명 충돌을 방지하기 위해 공통 규약과 파트별 계약을 고정한다.

## 2) 문서 목록

- Common: `week2_common_interface.md`
- BE1: `week2_be1_interface.md`
- BE2: `week2_be2_interface.md`
- BE3: `week2_be3_interface.md`
- FE: `week2_fe_interface.md`

### 현재 버전

- Common: `v1.5-week2-final`
- BE1: `v1.4-week2-final`
- BE2: `v1.2-week2-final`
- BE3: `v1.3-week2-final`
- FE: `v1.3-week2-final`

## 3) 우선순위 규칙

충돌 시 적용 우선순위:
1. 본 폴더의 Week 2 인터페이스 문서
2. `docs/10_contracts/schema/schema_contract.md`
3. `docs/10_contracts/api/api_spec.md`
4. 기존 Week 1 인터페이스 문서

## 4) 네이밍 규약 요약

- 필드명: `snake_case`
- datetime: ISO-8601 (`YYYY-MM-DDTHH:mm:ss+09:00`)
- ID 접두사:
  - `case_id`: `CASE-`
  - `request_id`: `REQ-`
  - `chunk_id`: `<case_id>__chunk-<n>`
- 불리언: `is_*`, `has_*`
- 배열: 복수형(`records`, `entities`, `errors`, `warnings`)

## 5) 금지 별칭 (전 파트 공통)

- `id` -> 반드시 `case_id` 사용
- `submitted_at` / `date` / `datetime` -> 반드시 `created_at` 사용
- `src` / `source_name` -> 도메인 출처는 반드시 `source` 사용
- `req_text` / `raw` -> 반드시 `text` 또는 `raw_text` 사용
- `entity` -> 반드시 `entities` 사용
- `valid` -> 반드시 `is_valid` 사용

## 6) Week 2 완료 기준 연동

- 샘플 50건+ 처리
- 스키마 통과율 90% 목표
- 구조화 평가 파이프라인 재실행 가능

## 7) 구현 상태 메모 (2026-03-22)

- 구현 완료 API: `POST /api/v1/search`, `POST /api/v1/qa`
- 미구현 API(Week3 예정): `POST /api/v1/ingest`, `POST /api/v1/structure`
- FE 업로드/구조화 화면은 시뮬레이션 경로(`build_structure_success_payload`) 사용

## 10) 2026-03-25 동기화 반영

- FastAPI 검증 오류(HTTP 422)도 Week2 표준 실패 래퍼(`success/request_id/timestamp/error`)로 통일
- `created_at`, `structured_at` 출력은 KST 오프셋 포함 ISO-8601(`+09:00`)으로 통일
- FE search -> qa 중계 시 `doc_id`는 검색 응답의 `doc_id`를 그대로 사용(`id` 금지)

## 8) 라벨 정책 스냅샷

- 허용 라벨: `LOCATION`, `TIME`, `FACILITY`, `HAZARD`, `ADMIN_UNIT`
- 비표준 라벨 매핑: `TYPE/RISK -> HAZARD`, `DATE -> TIME`, `PLACE -> LOCATION`, `AREA -> ADMIN_UNIT`
- 매핑 발생 시 `validation.warnings`에 `entity_label_normalized:<OLD>-><NEW>` 기록

## 9) 증빙 산출물

- 10건 구조화 샘플: `reports/week2_entity_audit/week2_structured_sample_10.json`
- 라벨 분포: `reports/week2_entity_audit/week2_entities_label_distribution_10.json`
- 비표준 라벨 3케이스: `reports/week2_entity_audit/week2_nonstandard_label_cases_3.json`

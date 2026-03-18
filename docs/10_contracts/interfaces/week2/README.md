# Week 2 인터페이스 문서 인덱스

기준일: 2026-03-19  
적용 범위: Week 2 (`ingest -> structure -> validate`)

## 1) 목적

Week 2 구현 중 변수명, 포맷, 객체명 충돌을 방지하기 위해 공통 규약과 파트별 계약을 고정한다.

## 2) 문서 목록

- Common: `week2_common_interface.md`
- BE1: `week2_be1_interface.md`
- BE2: `week2_be2_interface.md`
- BE3: `week2_be3_interface.md`
- FE: `week2_fe_interface.md`

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

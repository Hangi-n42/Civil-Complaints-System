> 과거 실험 기록 · 보관 문서 v1.0 · 정리일 2026-09-26
> 원래 경로: `reports/retrieval/v3/be1_restructured_source_pilot10_search_smoke.md`. 원작성일·실험 조건·수치·결론은 당시 기록이며 현재 성능 확인 결과가 아니다.
> 관련 JSON 산출물: [기존 경로 유지](../../../../../reports/retrieval/v3/be1_restructured_source_pilot10_search_smoke.json). 현재 파일이 이후 재생성될 수 있으므로 실행 시점/모델/데이터 일치를 확인한다.

# BE1 재구조화 컬렉션 검색 Smoke 검증

- 생성 시각(UTC): `2026-06-09T16:40:28.138224+00:00`
- 컬렉션: `civil_cases_be1_source_pilot10`
- 질의 수: 5
- 빈 결과 질의 수: 0

## 질의별 결과

### 공연 예매 취소가 안 됩니다

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-002470` | 0.6400 | 3 | 예매/예약 | 0 | `be1_structured` |
| 2 | `CASE-002468` | 0.6300 | 2 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-002466` | 0.5900 | 4 | 예매/예약 | 0 | `be1_structured` |

### 임금체불 신고와 퇴직금 지급 문의

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-001555` | 0.4400 | 4 | - | 0 | `be1_structured` |
| 2 | `CASE-002470` | 0.4200 | 3 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-002469` | 0.4200 | 2 | 예매/예약 | 0 | `be1_structured` |

### 건설공사 하도급 대금 문제

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-001555` | 0.3900 | 4 | - | 0 | `be1_structured` |
| 2 | `CASE-002465` | 0.3700 | 2 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-002466` | 0.3600 | 4 | 예매/예약 | 0 | `be1_structured` |

### 도로 파손으로 차량 통행이 위험합니다

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-001555` | 0.3700 | 4 | - | 0 | `be1_structured` |
| 2 | `CASE-002467` | 0.3600 | 4 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-000021` | 0.3500 | 1 | - | 0 | `be1_structured` |

### 전세보증금 반환 관련 상담

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-002470` | 0.4800 | 3 | 예매/예약 | 0 | `be1_structured` |
| 2 | `CASE-002466` | 0.4800 | 4 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-002468` | 0.4700 | 2 | 예매/예약 | 0 | `be1_structured` |

## 판단 기준

- 빈 결과가 없어야 한다.
- `entity_texts`, `issue_types`, `legal_refs`, `responsible_units_source`가 검색 결과 metadata에서 읽혀야 한다.
- 이 리포트는 민원 원문과 검색 snippet을 포함하지 않는다.

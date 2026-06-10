# BE1 재구조화 컬렉션 검색 Smoke 검증

- 생성 시각(UTC): `2026-06-10T01:06:18.112331+00:00`
- 컬렉션: `civil_cases_be1_restructured_v1`
- 질의 수: 5
- 빈 결과 질의 수: 0

## 질의별 결과

### 공연 예매 취소가 안 됩니다

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-001683` | 0.6900 | 2 | 예매/예약 | 0 | `be1_structured` |
| 2 | `CASE-001617` | 0.6800 | 3 | 예매/예약 | 0 | `be1_structured` |
| 3 | `CASE-002407` | 0.6600 | 4 | 예매/예약 | 0 | `be1_structured` |

### 임금체불 신고와 퇴직금 지급 문의

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-700455` | 0.7500 | 1 | - | 1 | `be1_structured` |
| 2 | `CASE-700751` | 0.7200 | 1 | 지원금/급여 | 1 | `be1_structured` |
| 3 | `CASE-701320` | 0.7200 | 1 | 지원금/급여 | 1 | `be1_structured` |

### 건설공사 하도급 대금 문제

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-301512` | 0.6500 | 3 | 법령 해석, 허가/등록, 지원금/급여 | 3 | `be1_structured` |
| 2 | `CASE-800151` | 0.6400 | 3 | 지원금/급여, 증빙/서류 | 0 | `be1_structured` |
| 3 | `CASE-301417` | 0.6300 | 4 | 단속/점검, 시설 개선/보수, 법령 해석 | 2 | `be1_structured` |

### 도로 파손으로 차량 통행이 위험합니다

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-30057` | 0.7200 | 4 | 시설 개선/보수 | 0 | `be1_structured` |
| 2 | `CASE-70083` | 0.7000 | 1 | 시설 개선/보수 | 0 | `be1_structured` |
| 3 | `CASE-70138` | 0.6800 | 8 | 단속/점검 | 4 | `be1_structured` |

### 전세보증금 반환 관련 상담

| 순위 | case_id | 점수 | entity_texts 수 | issue_types | legal_refs 수 | 부서 출처 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | `CASE-300734` | 0.7100 | 1 | - | 0 | `be1_structured` |
| 2 | `CASE-300095` | 0.7100 | 2 | 갱신/연장 | 0 | `be1_structured` |
| 3 | `CASE-001305` | 0.7000 | 4 | 갱신/연장 | 0 | `be1_structured` |

## 판단 기준

- 빈 결과가 없어야 한다.
- `entity_texts`, `issue_types`, `legal_refs`, `responsible_units_source`가 검색 결과 metadata에서 읽혀야 한다.
- 이 리포트는 민원 원문과 검색 snippet을 포함하지 않는다.

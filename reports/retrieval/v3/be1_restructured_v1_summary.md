# BE1 최신 구조화 기반 재인덱싱 최종 결과

- 작성일: 2026-06-10
- 작업 이슈: #365
- 기준 브랜치: `codex/be2-be1-restructured-index-365`
- 입력 데이터: `data/Public_Civil_Service_LLM_Data` Training + Validation 원천 데이터 9,132건
- 새 컬렉션: `civil_cases_be1_restructured_v1`

## 실행 결과

BE1 최신 구조화 로직을 원천 민원 9,132건에 적용해 새 Chroma 컬렉션을 구축했다.

| 항목 | 값 |
| --- | ---: |
| 처리 건수 | 9,132 |
| 실패 건수 | 0 |
| 새 컬렉션 적재 건수 | 9,132 |
| 구조화 모드 | `actual` |
| 임베딩 모델 | `BAAI/bge-m3` |
| 부서 출처 | `be1_structured` |

기존 `civil_cases_v1` 컬렉션은 유지했고, BE1 최신 구조화 기반 결과는 새 컬렉션에 분리 적재했다.

## Metadata 적재율

| 필드 | 적재 건수 | 적재율 |
| --- | ---: | ---: |
| `entity_texts` | 7,996 / 9,132 | 87.56% |
| `legal_ref_names` | 3,456 / 9,132 | 37.84% |
| `legal_ref_ids` | 3,456 / 9,132 | 37.84% |
| `issue_types` | 5,571 / 9,132 | 61.01% |
| `key_terms` | 8,192 / 9,132 | 89.71% |
| `responsible_units` | 9,132 / 9,132 | 100.00% |
| `responsible_units_source` | 9,132 / 9,132 | 100.00% |
| `urgency_level` | 9,132 / 9,132 | 100.00% |

BE1 핸드오프 기준의 기존 `civil_cases_v1` `entity_texts` 적재율 11.03% 대비, 새 컬렉션은 87.56%로 개선됐다.

## 검색 Smoke 검증

검색 smoke 질의 5개 모두 빈 결과 없이 top-3 결과가 반환됐다.

| 질의 | 1위 case_id | 확인 |
| --- | --- | --- |
| 공연 예매 취소가 안 됩니다 | `CASE-001683` | `entity_texts`, `issue_types`, `responsible_units_source` 확인 |
| 임금체불 신고와 퇴직금 지급 문의 | `CASE-700455` | `legal_refs`, `responsible_units_source` 확인 |
| 건설공사 하도급 대금 문제 | `CASE-301512` | `entity_texts`, `issue_types`, `legal_refs` 확인 |
| 도로 파손으로 차량 통행이 위험합니다 | `CASE-30057` | `entity_texts`, `issue_types` 확인 |
| 전세보증금 반환 관련 상담 | `CASE-300734` | `entity_texts`, `responsible_units_source` 확인 |

## 로컬 반영 상태

전체 실행 결과를 임베딩 포함 export/import 방식으로 로컬 Chroma에 병합했다. 로컬에는 다음 주요 컬렉션이 함께 존재한다.

| 컬렉션 | 건수 |
| --- | ---: |
| `civil_cases_v1` | 9,132 |
| `civil_cases_be1_restructured_v1` | 9,132 |
| `law_articles_v1` | 17,759 |
| `busan_departments_v1` | 2,114 |

로컬 재검증에서도 최종 적재율과 검색 smoke 결과가 전체 실행 결과와 일치했다.

## 산출물

- `reports/retrieval/v3/be1_restructured_v1_coverage.md`
- `reports/retrieval/v3/be1_restructured_v1_search_smoke.md`
- `reports/retrieval/v3/be1_restructured_v1_local_coverage.md`
- `reports/retrieval/v3/be1_restructured_v1_local_search_smoke.md`

이 리포트와 세부 검증 리포트는 민원 원문과 검색 snippet을 포함하지 않는다.

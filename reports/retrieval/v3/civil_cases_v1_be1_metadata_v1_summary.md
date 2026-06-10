# BE1 Metadata Overlay 컬렉션 최종 결과

- 작성일: 2026-06-10
- 기준 컬렉션: `civil_cases_v1`
- metadata 원본 컬렉션: `civil_cases_be1_restructured_v1`
- 새 컬렉션: `civil_cases_v1_be1_metadata_v1`

## 목적

기존 `civil_cases_v1`은 검색 성능이 좋았지만 BE1 최신 metadata 적재율이 낮았다. 반대로 `civil_cases_be1_restructured_v1`은 metadata 적재율은 높았지만 검색용 본문과 임베딩이 바뀌어 검색 성능이 하락했다.

이번 컬렉션은 기존 검색 성능을 유지하면서 BE1 최신 metadata만 보강하는 것을 목표로 만들었다.

## 구축 방식

| 항목 | 방식 |
| --- | --- |
| 검색용 document text | `civil_cases_v1` 값 그대로 복사 |
| 임베딩 | `civil_cases_v1` 값 그대로 복사 |
| metadata | `civil_cases_be1_restructured_v1`의 BE1 검색 신호를 overlay |
| BE1 값이 빈 필드 | 기존 `civil_cases_v1` 값 보존 |

결과적으로 새 임베딩을 다시 계산하지 않았고, 검색 벡터는 기존 컬렉션과 동일하게 유지했다.

## 구축 결과

| 항목 | 값 |
| --- | ---: |
| 기준 컬렉션 건수 | 9,132 |
| metadata 원본 컬렉션 건수 | 9,132 |
| 새 컬렉션 적재 건수 | 9,132 |
| metadata 매칭 건수 | 9,132 |
| metadata 미매칭 건수 | 0 |

## Metadata 적재율

| 필드 | BE1 값 덮어쓰기 | 기존 값 보존 | 최종 적재율 |
| --- | ---: | ---: | ---: |
| `entity_texts` | 7,996 | 14 | 8,010 / 9,132 = 87.71% |
| `legal_ref_names` | 3,456 | 806 | 4,262 / 9,132 = 46.67% |
| `legal_ref_ids` | 3,456 | 806 | 4,262 / 9,132 = 46.67% |
| `issue_types` | 5,571 | 1,603 | 7,174 / 9,132 = 78.56% |
| `key_terms` | 8,192 | 404 | 8,596 / 9,132 = 94.13% |
| `responsible_units` | 9,132 | 0 | 9,132 / 9,132 = 100.00% |
| `responsible_units_source` | 9,132 | 0 | 9,132 / 9,132 = 100.00% |
| `urgency_level` | 9,132 | 0 | 9,132 / 9,132 = 100.00% |

## 검색 성능

`qrels_final.tsv` 기준으로 기존 `civil_cases_v1`과 새 `civil_cases_v1_be1_metadata_v1`을 동일한 100개 쿼리로 비교했다. 집계 지표는 qrels가 있는 49개 쿼리만 평가에 반영했다.

| 지표 | 기존 `civil_cases_v1` | 새 컬렉션 | 변화 |
| --- | ---: | ---: | ---: |
| nDCG@5 | 0.6108 | 0.6108 | +0.0000 |
| nDCG@10 | 0.6965 | 0.6965 | +0.0000 |
| Recall@5 | 0.3083 | 0.3083 | +0.0000 |
| Recall@10 | 0.6380 | 0.6380 | +0.0000 |
| MRR@5 | 0.5204 | 0.5204 | +0.0000 |
| MRR@10 | 0.5238 | 0.5238 | +0.0000 |
| AP@10 | 0.4741 | 0.4741 | +0.0000 |
| P@5 | 0.7510 | 0.7510 | +0.0000 |

쿼리별 nDCG@10은 개선 0건, 동일 49건, 하락 0건이었다. 전체 100개 검색 쿼리의 Top-1 결과 변경도 0건이었다.

## 검색 Smoke 검증

검색 smoke 질의 5개 모두 빈 결과 없이 top-3 결과가 반환됐다. 반환 결과 metadata에서도 `entity_texts`, `issue_types`, `legal_refs`, `responsible_units_source`가 확인됐다.

## 로컬 반영 상태

로컬 Chroma에도 `civil_cases_v1_be1_metadata_v1` 9,132건을 생성했다.

| 컬렉션 | 건수 |
| --- | ---: |
| `civil_cases_v1` | 9,132 |
| `civil_cases_be1_restructured_v1` | 9,132 |
| `civil_cases_v1_be1_metadata_v1` | 9,132 |

## Metadata Soft Rerank 평가

BE1 metadata를 hard filter가 아니라 약한 점수 boost로만 사용하는 soft rerank를 추가 평가했다. 평가 쿼리 100건 중 qrels 보유 쿼리 49건을 집계에 반영했다.

### Dense

| 지표 | baseline | soft rerank | 변화 |
| --- | ---: | ---: | ---: |
| nDCG@5 | 0.6082 | 0.5947 | -0.0135 |
| nDCG@10 | 0.6968 | 0.6277 | -0.0691 |
| Recall@5 | 0.3078 | 0.3024 | -0.0053 |
| Recall@10 | 0.6380 | 0.5538 | -0.0843 |
| MRR@10 | 0.5204 | 0.5075 | -0.0129 |
| AP@10 | 0.4729 | 0.4004 | -0.0725 |

### Hybrid

| 지표 | baseline | soft rerank | 변화 |
| --- | ---: | ---: | ---: |
| nDCG@5 | 0.5736 | 0.5747 | +0.0011 |
| nDCG@10 | 0.6228 | 0.6150 | -0.0079 |
| Recall@5 | 0.2899 | 0.2895 | -0.0004 |
| Recall@10 | 0.5602 | 0.5501 | -0.0101 |
| MRR@10 | 0.5029 | 0.5029 | +0.0000 |
| AP@10 | 0.3978 | 0.3870 | -0.0108 |

Dense에서는 하락 폭이 크고, 운영 기본 전략인 Hybrid에서도 nDCG@10과 Recall@10이 소폭 하락했다. 따라서 현재 가중치의 metadata soft rerank는 기본 활성화하지 않는다.

## 판단

`civil_cases_v1_be1_metadata_v1`은 기존 검색 성능을 잃지 않으면서 BE1 최신 metadata 적재율을 크게 개선했다. 따라서 기본 검색 컬렉션 전환 후보는 `civil_cases_be1_restructured_v1`이 아니라 `civil_cases_v1_be1_metadata_v1`로 보는 것이 맞다.

다만 metadata soft rerank는 현재 가중치로는 검색 성능을 떨어뜨리므로, 컬렉션 전환과 soft rerank 활성화는 분리해서 판단한다. 현재 추천은 `civil_cases_v1_be1_metadata_v1` 컬렉션은 전환 후보로 유지하되, soft rerank는 비활성 상태로 두는 것이다.

## 산출물

- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_coverage.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_search_smoke.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_collection_ab.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_pilot10.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_eval.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_build.md`
- `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_coverage.md`

이 리포트와 세부 검증 리포트는 민원 원문과 검색 snippet을 포함하지 않는다.

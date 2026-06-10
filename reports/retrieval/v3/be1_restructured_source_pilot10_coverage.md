# ChromaDB 검색 신호 metadata 적재율 점검

- 생성 시각(UTC): `2026-06-09T16:40:21.551727+00:00`
- persist dir: `data/chroma_db`
- collection: `civil_cases_be1_source_pilot10`
- 전체 건수: 10
- 점검 건수: 10
- 제한 실행 여부: 아니오

## 필드별 적재율

| 필드 | 적재 건수 | 빈 값 건수 | 적재율 | 고유 값 수 |
| --- | ---: | ---: | ---: | ---: |
| `entity_texts` | 10 | 0 | 100.00% | 10 |
| `legal_ref_names` | 0 | 10 | 0.00% | 0 |
| `legal_ref_ids` | 0 | 10 | 0.00% | 0 |
| `issue_types` | 8 | 2 | 80.00% | 2 |
| `key_terms` | 10 | 0 | 100.00% | 12 |
| `responsible_units` | 10 | 0 | 100.00% | 18 |
| `responsible_units_source` | 10 | 0 | 100.00% | 1 |
| `urgency_level` | 10 | 0 | 100.00% | 1 |

## 상위 값 분포

`entity_texts`, `key_terms`는 원문 값을 숨기고 해시 prefix만 표시한다.

### `entity_texts`

| sha256 prefix | 건수 |
| --- | ---: |
| `b74eef2a48b6` | 8 |
| `1c3a0a24ef01` | 5 |
| `4e5b38020f5d` | 4 |
| `86d22b3363c4` | 3 |
| `eb19ec902a17` | 2 |
| `9fbe110d36cd` | 2 |
| `e9c0cbcfd144` | 2 |
| `1f8495c6dbc9` | 2 |
| `a2c93caaf559` | 1 |
| `111b61f22f1c` | 1 |

### `legal_ref_names`

값 없음

### `legal_ref_ids`

값 없음

### `issue_types`

| 값 | 건수 |
| --- | ---: |
| `예매/예약` | 8 |
| `증빙/서류` | 1 |

### `key_terms`

| sha256 prefix | 건수 |
| --- | ---: |
| `b74eef2a48b6` | 8 |
| `1c3a0a24ef01` | 5 |
| `a04df23492bd` | 5 |
| `4e5b38020f5d` | 4 |
| `86d22b3363c4` | 3 |
| `eb19ec902a17` | 2 |
| `9fbe110d36cd` | 2 |
| `1f8495c6dbc9` | 2 |
| `e9c0cbcfd144` | 2 |
| `a2c93caaf559` | 1 |

### `responsible_units`

| 값 | 건수 |
| --- | ---: |
| `관광정책과` | 3 |
| `문화유산과` | 3 |
| `문화예술과` | 3 |
| `문화국` | 3 |
| `119특수대응단` | 2 |
| `관광마이스국` | 2 |
| `전국체전기획단` | 2 |
| `장애인복지과` | 2 |
| `재난예방담당관` | 1 |
| `소방재난본부` | 1 |

### `responsible_units_source`

| 값 | 건수 |
| --- | ---: |
| `be1_structured` | 10 |

### `urgency_level`

| 값 | 건수 |
| --- | ---: |
| `낮음` | 10 |

## 해석 기준

- `responsible_units` 적재율이 낮으면 BE1 설정과 인덱싱 경로를 먼저 확인한다.
- `legal_ref_ids`와 `legal_ref_names` 적재율 차이가 크면 법령명과 law_id 매핑을 점검한다.
- 이 스크립트는 ChromaDB metadata를 수정하지 않는다.
- 민원 원문, 검색 snippet, 생성 답변 미리보기는 리포트에 포함하지 않는다.

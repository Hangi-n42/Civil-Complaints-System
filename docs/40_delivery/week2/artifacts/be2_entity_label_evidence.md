# BE2 entity_labels 통합 검증 결과

- generated_at: 2026-03-24T02:05:36.677425+00:00

## 1) 인덱스 저장 샘플 10건

| case_id | entity_labels |
| --- | --- |
| CASE-2026-900001 | FACILITY, HAZARD |
| CASE-2026-900002 | FACILITY |
| CASE-2026-900003 | FACILITY, HAZARD |
| CASE-2026-900004 | LOCATION |
| CASE-2026-900005 | FACILITY, TIME |
| CASE-2026-900006 | FACILITY, HAZARD, TIME |
| CASE-2026-900007 | LOCATION |
| CASE-2026-900008 | FACILITY, ADMIN_UNIT |
| CASE-2026-900009 | FACILITY |
| CASE-2026-900010 | HAZARD, TIME |

## 2) 검색 요청/응답 로그 5세트

### 단일 라벨 필터 FACILITY
- status_code: 200
- request: {"query": "위험", "top_k": 5, "filters": {"entity_labels": ["FACILITY"]}}
- response_excerpt: {"count": 5, "took_ms": 1, "top_results": [{"chunk_id": "CASE-2026-900001__chunk-0", "case_id": "CASE-2026-900001", "score": 0.15}, {"chunk_id": "CASE-2026-900003__chunk-0", "case_id": "CASE-2026-900003", "score": 0.15}, {"chunk_id": "CASE-2026-900002__chunk-0", "case_id": "CASE-2026-900002", "score": 0.0}]}

### 복수 라벨 필터 FACILITY+HAZARD
- status_code: 200
- request: {"query": "위험", "top_k": 5, "filters": {"entity_labels": ["FACILITY", "HAZARD"]}}
- response_excerpt: {"count": 5, "took_ms": 1, "top_results": [{"chunk_id": "CASE-2026-900001__chunk-0", "case_id": "CASE-2026-900001", "score": 0.15}, {"chunk_id": "CASE-2026-900003__chunk-0", "case_id": "CASE-2026-900003", "score": 0.15}, {"chunk_id": "CASE-2026-900010__chunk-0", "case_id": "CASE-2026-900010", "score": 0.15}]}

### 존재하지 않는 라벨 입력 ADMIN_UNIT
- status_code: 200
- request: {"query": "위험", "top_k": 5, "filters": {"entity_labels": ["ADMIN_UNIT"]}}
- response_excerpt: {"count": 1, "took_ms": 1, "top_results": [{"chunk_id": "CASE-2026-900008__chunk-0", "case_id": "CASE-2026-900008", "score": 0.0}]}

### 비표준 라벨 입력 TYPE
- status_code: 422
- request: {"query": "위험", "top_k": 5, "filters": {"entity_labels": ["TYPE"]}}
- response_excerpt: {"detail": [{"type": "value_error", "loc": ["body", "filters", "entity_labels"], "msg": "Value error, filters.entity_labels에 허용되지 않은 라벨이 포함되었습니다: TYPE. 허용 라벨: ADMIN_UNIT, FACILITY, HAZARD, LOCATION, TIME", "input": ["TYPE"], "ctx": {"error": {}}}]}

### entity_labels 미전달
- status_code: 200
- request: {"query": "위험", "top_k": 5}
- response_excerpt: {"count": 5, "took_ms": 1, "top_results": [{"chunk_id": "CASE-2026-900001__chunk-0", "case_id": "CASE-2026-900001", "score": 0.15}, {"chunk_id": "CASE-2026-900003__chunk-0", "case_id": "CASE-2026-900003", "score": 0.15}, {"chunk_id": "CASE-2026-900010__chunk-0", "case_id": "CASE-2026-900010", "score": 0.15}]}

## 3) 필터 적용 전후 결과 건수 비교

| scenario | before_count | after_count | took_ms |
| --- | ---: | ---: | ---: |
| 단일 라벨 필터 FACILITY | 5 | 5 | 6 |
| 복수 라벨 필터 FACILITY+HAZARD | 5 | 5 | 6 |
| 존재하지 않는 라벨 입력 ADMIN_UNIT | 5 | 1 | 5 |
| 비표준 라벨 입력 TYPE | 5 | - | 6 |
| entity_labels 미전달 | - | 5 | 6 |

## 4) 오류 처리 정책 적용 캡처

- 정책: 비표준 라벨 입력 시 422 반환(무시하지 않음)
- invalid_label_response: {"status_code": 422, "body": {"detail": [{"type": "value_error", "loc": ["body", "filters", "entity_labels"], "msg": "Value error, filters.entity_labels에 허용되지 않은 라벨이 포함되었습니다: TYPE. 허용 라벨: ADMIN_UNIT, FACILITY, HAZARD, LOCATION, TIME", "input": ["TYPE"], "ctx": {"error": {}}}]}}

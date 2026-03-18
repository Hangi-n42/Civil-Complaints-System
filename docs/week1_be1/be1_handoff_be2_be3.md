# BE1 Week1 핸드오프 (BE2/BE3)

문서 버전: v1.0  
작성일: 2026-03-18

## 1. BE2 전달 메타데이터 후보

### 1.1 최소 필수

- `case_id`
- `created_at`
- `source`

### 1.2 권장

- `category`
- `region`
- `entities` (-> `entity_labels`, `entity_texts` 파생)
- `raw_text`

### 1.3 보정 규칙

- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`

### 1.4 대체값 정책

- `category`: `unknown`
- `region`: `unknown`
- `entities`: `[]`

## 2. BE3 전달 필드 제약사항

### 2.1 구조화 필수 제약

- `case_id`, `source`, `created_at`, `raw_text` 필수
- `observation/result/request/context` 모두 필수
- 각 필드 `confidence`는 0~1
- 각 필드 `evidence_span` 길이 2

### 2.2 validation 에러 포맷 (→ ValidationIssue 객체 기반)

```json
{
  "is_valid": false,
  "errors": [
    {
      "field": "request",
      "code": "VAL_REQUIRED_FIELD_MISSING",
      "message": "request 필수 필드가 누락되었습니다.",
      "severity": "error",
      "retryable": false
    },
    {
      "field": "observation.confidence",
      "code": "VAL_INVALID_CONFIDENCE_RANGE",
      "message": "observation의 confidence가 0~1 범위를 벗어났습니다.",
      "severity": "error",
      "retryable": false,
      "value": 1.21,
      "expected": "0.0 <= value <= 1.0"
    }
  ]
}
```

### 2.3 ValidationIssue 에러 코드 집합

- `VAL_REQUIRED_FIELD_MISSING`: 필수 필드 누락
- `VAL_INVALID_TYPE`: 필드 타입 비매칭
- `VAL_INVALID_CONFIDENCE_RANGE`: confidence 0~1 범위 위반
- `VAL_INVALID_EVIDENCE_SPAN_ORDER`: evidence_span 시작 인덱스 >= 종료 인덱스

## 3. 전달 경로

- 파일: `data/samples/week2_delivery_sample_20.json`
- API: `/api/v1/ingest`, `/api/v1/structure`

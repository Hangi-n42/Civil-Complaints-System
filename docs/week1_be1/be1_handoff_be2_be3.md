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

### 2.2 validation 에러 포맷 권장

```json
{
  "is_valid": false,
  "errors": [
    "missing:request",
    "invalid_confidence:observation"
  ]
}
```

### 2.3 주요 에러 코드 집합

- `missing:<field>`
- `invalid_type:<field>`
- `invalid_confidence:<field>`
- `invalid_evidence_span:<field>`

## 3. 전달 경로

- 파일: `data/samples/week2_delivery_sample_20.json`
- API: `/api/v1/ingest`, `/api/v1/structure`

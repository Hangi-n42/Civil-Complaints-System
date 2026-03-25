# Week 2 공통 인터페이스 규약

문서 버전: v1.5-week2-final  
작성일: 2026-03-19  
최신화: 2026-03-25 (422 래퍼 통일, KST +09:00 시각 규칙 반영)  
적용 파트: FE, BE1, BE2, BE3

## 1) 공통 원칙

- 모든 JSON 키는 `snake_case`를 사용한다.
- nullable 필드는 `null` 허용 여부를 명시한다.
- 누락과 빈 문자열은 동일하게 취급하지 않는다.
- 모든 API 응답은 UTF-8 JSON으로 고정한다.
- Week2 표준 성공 응답은 `success`, `request_id`, `timestamp`, `data`를 사용한다.
- Week2 표준 실패 응답은 `success`, `request_id`, `timestamp`, `error`를 사용한다.
- `error` 객체는 `code`, `message`, `retryable`를 필수로 포함한다.
- FastAPI 기본 검증 오류(HTTP 422)도 `VALIDATION_ERROR` 코드로 동일 래퍼 형식을 사용한다.

## 2) 표준 객체명 (고정)

- 입력 레코드: `CivilCaseInput`
- 구조화 레코드: `StructuredCivilCase`
- 필드 추출 객체: `FieldExtraction`
- 엔티티 객체: `Entity`
- 검증 객체: `ValidationResult`
- 에러 객체: `ApiError`

## 3) 표준 필드명 (고정)

필수 식별 필드:
- `case_id` (string)
- `source` (string)
- `created_at` (string, ISO-8601)

단계별 규칙:
- 입력 단계: `source` 누락 허용, `created_at` 원천 포맷 허용
- 내부 저장/API 출력: `source` 필수(누락 시 `unknown` 보정), `created_at` ISO-8601 강제
- 내부 저장/API 출력 시각 필드(`created_at`, `structured_at`, `timestamp`)는 KST 오프셋 포함 형식(`+09:00`)을 사용한다.

구조화 필드:
- `observation` (`FieldExtraction`)
- `result` (`FieldExtraction`)
- `request` (`FieldExtraction`)
- `context` (`FieldExtraction`)
- `entities` (`Entity[]`)
- `validation` (`ValidationResult`)

`StructuredCivilCase` 확장 필드 (Week2 운영 허용):
- `metadata` (object, required)
- `supervision` (object, optional)
- `confidence_score` (number, 0~1, required)
- `structured_at` (string, ISO-8601, required)

## 4) 표준 타입 규약

`FieldExtraction`:
```json
{
  "text": "string",
  "confidence": 0.0,
  "evidence_span": [0, 0]
}
```

`Entity`:
```json
{
  "label": "LOCATION",
  "text": "서울시 강남구"
}
```

`ValidationResult`:
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": []
}
```

`StructuredCivilCase` 확장 필드 타입:
```json
{
  "metadata": {
    "source_id": "string",
    "consulting_category": "string",
    "consulting_turns": 0,
    "consulting_length": 0,
    "client_gender": "string",
    "client_age": "string",
    "source_file": "string"
  },
  "supervision": {
    "classification": {"task_category": "string", "instruction": "string", "input": "string", "output": "string"},
    "summary": {"task_category": "string", "instruction": "string", "input": "string", "output": "string"},
    "qa": [{"task_category": "string", "instruction": "string", "question": "string", "answer": "string"}]
  },
  "confidence_score": 0.0,
  "structured_at": "2026-03-20T15:21:04+09:00"
}
```

## 5) 어댑터 매핑 (허용)

원천 데이터 불일치 매핑은 아래만 허용한다.
- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`
- `raw_text` -> 내부 원문 필드 우선 사용
- `text` -> `raw_text` 대체 입력 허용

그 외 별칭은 금지한다.

## 6) Entity 라벨 정책 (서버 강제)

허용 라벨(enum):
- `LOCATION`
- `TIME`
- `FACILITY`
- `HAZARD`
- `ADMIN_UNIT`

비표준 라벨 정규화:
- `TYPE` -> `HAZARD`
- `RISK` -> `HAZARD`
- `DATE` -> `TIME`
- `PLACE` -> `LOCATION`
- `AREA` -> `ADMIN_UNIT`

검증/차단 규칙:
- 매핑 가능한 라벨은 서버에서 강제 정규화한다.
- 매핑 불가능한 라벨은 `invalid_entity_label:<LABEL>` 오류로 차단한다.
- 정규화가 발생하면 `validation.warnings`에 `entity_label_normalized:<OLD>-><NEW>`를 기록한다.

## 7) 충돌 해결 규칙

- 1차: 공통 문서(`week2_common_interface.md`) 기준 적용
- 2차: 파트 문서의 입출력 계약 적용
- 3차: 분쟁 발생 시 BE1(데이터 계약 오너) + BE3(API 계약 오너) 합의 후 문서 우선 수정
- Week2 기간에는 본 문서 규약이 `schema_contract.md`, `api_spec.md`보다 우선한다.

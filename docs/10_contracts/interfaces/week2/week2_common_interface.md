# Week 2 공통 인터페이스 규약

문서 버전: v1.0-week2  
작성일: 2026-03-19  
적용 파트: FE, BE1, BE2, BE3

## 1) 공통 원칙

- 모든 JSON 키는 `snake_case`를 사용한다.
- nullable 필드는 `null` 허용 여부를 명시한다.
- 누락과 빈 문자열은 동일하게 취급하지 않는다.
- 모든 API 응답은 UTF-8 JSON으로 고정한다.

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

구조화 필드:
- `observation` (`FieldExtraction`)
- `result` (`FieldExtraction`)
- `request` (`FieldExtraction`)
- `context` (`FieldExtraction`)
- `entities` (`Entity[]`)
- `validation` (`ValidationResult`)

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

## 5) 어댑터 매핑 (허용)

원천 데이터 불일치 매핑은 아래만 허용한다.
- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`

그 외 별칭은 금지한다.

## 6) 충돌 해결 규칙

- 1차: 공통 문서(`week2_common_interface.md`) 기준 적용
- 2차: 파트 문서의 입출력 계약 적용
- 3차: 분쟁 발생 시 BE1(데이터 계약 오너) + BE3(API 계약 오너) 합의 후 문서 우선 수정

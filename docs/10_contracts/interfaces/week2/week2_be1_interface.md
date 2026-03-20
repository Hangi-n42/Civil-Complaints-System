# Week 2 BE1 인터페이스 문서

문서 버전: v1.0-week2  
작성일: 2026-03-19  
책임: BE1  
협업: BE2, BE3

## 1) 책임 범위

- 입력 민원 정제/PII/중복 처리
- 4요소 구조화 산출
- 구조화 품질 측정 산출물 생성

## 2) BE1 입력 계약 (`CivilCaseInput`)

```json
{
  "case_id": "CASE-2026-000123",
  "source": "aihub_71852",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 강남구",
  "text": "민원 원문",
  "metadata": {
    "source_file": "raw_001.json"
  }
}
```

필수:
- `case_id`, `created_at`, `text`

권장:
- `source`, `category`, `region`, `metadata.source_file`

## 3) BE1 출력 계약 (BE1 -> BE2/BE3)

객체명: `StructuredCivilCase`

```json
{
  "case_id": "CASE-2026-000123",
  "source": "aihub_71852",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 강남구",
  "raw_text": "민원 원문",
  "observation": {"text": "...", "confidence": 0.9, "evidence_span": [0, 10]},
  "result": {"text": "...", "confidence": 0.8, "evidence_span": [11, 20]},
  "request": {"text": "...", "confidence": 0.9, "evidence_span": [21, 30]},
  "context": {"text": "...", "confidence": 0.7, "evidence_span": [31, 40]},
  "entities": [{"label": "FACILITY", "text": "가로등"}],
  "validation": {"is_valid": true, "errors": [], "warnings": []}
}
```

## 4) 변수명 충돌 방지 규칙

- 원문은 `text`(입력), `raw_text`(구조화 출력)로 분리한다.
- 구조화 4요소 이름은 축약 금지 (`obs`, `req`, `ctx` 사용 금지).
- confidence 타입은 숫자(float)만 허용한다.
- `validation.is_valid` 외 `valid` 키 생성 금지.

## 5) BE1 완료 체크

- [ ] 입력(`CivilCaseInput`)에서 `source` 누락 허용 처리 확인
- [ ] 출력(`StructuredCivilCase`)에서 `source` 누락률 0%(누락 시 `unknown` 보정)
- [ ] 4요소 키 이름 고정(축약/별칭 없음)
- [ ] `validation` 객체 항상 포함

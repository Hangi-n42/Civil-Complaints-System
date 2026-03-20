# Week 2 BE1 인터페이스 문서

문서 버전: v1.1-week2-aligned  
작성일: 2026-03-19  
최신화: 2026-03-20 (코드 기준 확장 필드 정합 반영)  
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
  "validation": {"is_valid": true, "errors": [], "warnings": []},
  "metadata": {
    "source_id": "SRC-0001",
    "consulting_category": "도로안전",
    "consulting_turns": 3,
    "consulting_length": 120,
    "client_gender": "",
    "client_age": "",
    "source_file": "raw_001.json"
  },
  "supervision": {
    "summary": {
      "task_category": "요약",
      "instruction": "민원 내용을 요약하시오.",
      "input": "...",
      "output": "..."
    }
  },
  "confidence_score": 0.91,
  "structured_at": "2026-03-20T15:21:04+09:00"
}
```

확장 필드 규칙:
- `metadata`: 항상 포함(원천 추적/품질 분석용)
- `supervision`: 라벨링 정보가 있을 때만 포함(optional)
- `confidence_score`: 구조화 결과 집계 신뢰도(0~1)
- `structured_at`: 구조화 처리 시각(ISO-8601)

## 4) 변수명 충돌 방지 규칙

- 원문은 `text`(입력), `raw_text`(구조화 출력)로 분리한다.
- 구조화 4요소 이름은 축약 금지 (`obs`, `req`, `ctx` 사용 금지).
- confidence 타입은 숫자(float)만 허용한다.
- `validation.is_valid` 외 `valid` 키 생성 금지.
- 확장 필드는 위 규칙 외 키 이름/타입을 임의 변경하지 않는다.

## 5) BE1 완료 체크

- [ ] 입력(`CivilCaseInput`)에서 `source` 누락 허용 처리 확인
- [ ] 출력(`StructuredCivilCase`)에서 `source` 누락률 0%(누락 시 `unknown` 보정)
- [ ] 4요소 키 이름 고정(축약/별칭 없음)
- [ ] `validation` 객체 항상 포함
- [ ] 확장 필드(`metadata`, `supervision`, `confidence_score`, `structured_at`) 규칙 준수 확인

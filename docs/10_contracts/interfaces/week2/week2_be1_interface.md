# Week 2 BE1 인터페이스 문서

문서 버전: v1.4-week2-final  
작성일: 2026-03-19  
최신화: 2026-03-25 (created_at/structured_at KST +09:00 통일 반영)  
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
  "raw_text": "민원 원문 (선택)",
  "metadata": {
    "source_file": "raw_001.json"
  }
}
```

필수:
- `case_id`, `created_at`, `text` 또는 `raw_text` (둘 중 하나 필수)

권장:
- `source`, `category`, `region`, `metadata.source_file`

**필드 매핑 규칙:**
- `text` 또는 `raw_text` 중 존재하는 것을 우선순위대로 읽음
- 우선순위: `raw_text` > `text` (둘 다 있으면 `raw_text` 사용)

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
- `structured_at`: 구조화 처리 시각(ISO-8601, `+09:00` 포함)
- `created_at`: 출력 단계에서는 ISO-8601 KST 오프셋(`+09:00`)으로 통일

**Entity 필드 명시:**
- `entities`: 개체명 인식(NER) 결과 배열
  ```json
  "entities": [
    {"label": "LOCATION", "text": "서울시 강남구"},
    {"label": "FACILITY", "text": "가로등"},
    {"label": "TIME", "text": "2026년 3월 19일"},
    {"label": "HAZARD", "text": "소음"},
    {"label": "ADMIN_UNIT", "text": "강남구"}
  ]
  ```
- `label` 허용값(enum): `LOCATION | TIME | FACILITY | HAZARD | ADMIN_UNIT`
  - LOCATION: 지명, 시설 위치
  - TIME: 시간, 날짜, 기간
  - FACILITY: 도로, 정류장, 가로등, 하수구 등 시설물
  - HAZARD: 소음, 분진, 악취, 위험요소 등
  - ADMIN_UNIT: 행정 단위 (시/도/군/구/면/동 등)
- 비표준 라벨(TYPE, RISK, DATE, PLACE, AREA 등) 입력 시:
  - 자동 정규화 시도 후 `validation.warnings`에 매핑 이력 기록
  - 예: `entity_label_normalized:TYPE->HAZARD`
  - 매핑 불가 라벨은 `invalid_entity_label:<LABEL>` 오류로 차단

## 4) 변수명 충돌 방지 규칙

- 원문은 `text`(입력), `raw_text`(구조화 출력)로 분리한다.
- 구조화 4요소 이름은 축약 금지 (`obs`, `req`, `ctx` 사용 금지).
- confidence 타입은 숫자(float)만 허용한다.
- `validation.is_valid` 외 `valid` 키 생성 금지.
- 확장 필드는 위 규칙 외 키 이름/타입을 임의 변경하지 않는다.

## 5) BE1 완료 체크

- [x] 입력(`CivilCaseInput`)에서 `source` 누락 허용 처리 확인
- [x] 출력(`StructuredCivilCase`)에서 `source` 누락 시 `unknown` 보정 처리 확인
- [x] 입력 원문 매핑 우선순위 `raw_text > text` 적용 확인
- [x] Entity 라벨 허용값 5개 제한 + 비표준 라벨 서버 정규화 확인
- [x] `validation` 객체 항상 포함 및 `warnings` 기록 확인
- [x] 확장 필드(`metadata`, `supervision`, `confidence_score`, `structured_at`) 규칙 준수 확인

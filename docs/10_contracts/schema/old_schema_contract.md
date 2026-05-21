# 스키마 계약 문서

문서 버전: v1.1-week2-aligned  
기준 문서: [PRD](../../00_overview/prd.md), [MVP 범위 문서](../../00_overview/mvp_scope.md), [API 명세서](../api/api_spec.md)  
작성일: 2026-03-11
최신화: 2026-03-25 (+09:00 출력 시각 정책 동기화 반영)

## 0. Week2 Contract Override

- Week2 구현 및 검증 단계에서는 `docs/10_contracts/interfaces/week2/*`를 최우선 기준으로 적용한다.
- 입력 단계는 원천 데이터 호환을 위해 일부 필드를 유연 허용한다.
- 내부 저장 및 API 출력 단계는 필수 필드와 포맷을 엄격 적용한다.

## 1. 문서 목적

본 문서는 프로젝트 전반에서 사용되는 핵심 데이터 구조의 계약을 정의한다.  
목표는 다음과 같다.

- 구조화 결과 형식을 고정해 팀 간 충돌 방지
- 검색과 QA가 동일한 메타데이터 기준을 사용하도록 보장
- 평가 스크립트와 저장 포맷의 기준점 제공
- 스키마 검증 및 후처리 기준을 명확히 정의

## 2. 스키마 설계 원칙

### 2.1 공통 원칙
- 모든 주요 객체는 가능한 한 명시적인 필드를 사용한다.
- 필드명은 snake_case를 사용한다.
- 날짜/시간은 ISO 8601 문자열을 사용한다.
- 출력 시각 필드(`created_at`, `structured_at`, `timestamp`, `generated_at`)는 KST 오프셋 포함 형식(`+09:00`)을 사용한다.
- 입력에서 타임존 정보가 없는 datetime을 수용한 경우, 내부 저장/API 출력 전 KST(`+09:00`)를 부여해 정규화한다.
- confidence는 `0.0 ~ 1.0` 범위를 사용한다.
- evidence_span은 원문 기준 문자 인덱스 `[start, end]` 형태를 사용한다.
- 검색 및 QA에 필요한 메타데이터는 평탄한(flat) 구조를 우선한다.

### 2.2 필수 계약 대상
- 입력 민원 레코드
- 구조화 민원 객체
- 엔티티 객체
- 인덱싱용 청크 객체
- 검색 결과 객체
- QA 응답 객체
- 검증 결과 객체

## 3. 핵심 스키마 목록

| 스키마 | 파일 후보 | 용도 |
| --- | --- | --- |
| CivilCaseInput | `app/api/schemas/ingest.py` | 입력 민원 원문 |
| StructuredCivilCase | `schemas/civil_case.schema.json` | 구조화 저장 기준 |
| SearchChunk | `schemas/search_result.schema.json` 일부 | 인덱싱 및 검색 단위 |
| SearchResult | `schemas/search_result.schema.json` | 검색 응답 기준 |
| QAResponse | `schemas/qa_response.schema.json` | 질의응답 응답 기준 |
| ValidationResult | API/내부 공용 | 스키마 검증 결과 |

## 4. 입력 민원 레코드 스키마

### 4.1 목적
- ingest 및 structure 입력의 기준 형식

### 4.2 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `case_id` | string | Y | 민원 고유 식별자 |
| `source` | string | N | ingest 입력에서는 선택 허용, 저장/출력 전 `unknown` 보정 |
| `created_at` | string(datetime) | Y | ingest 입력은 원천 포맷 허용, 저장/출력은 ISO-8601 KST(`+09:00`) 강제 |
| `category` | string | N | 민원 분류 |
| `region` | string | N | 행정 구역 |
| `text` | string | N | 원문 텍스트 (`raw_text` 대체 허용) |
| `raw_text` | string | N | 원문 텍스트 (`text` 대체 허용) |
| `metadata` | object | N | 추가 메타데이터 |

추가 규칙:
- 입력 단계에서 `text` 또는 `raw_text` 중 하나는 반드시 존재해야 한다.
- 내부 정규화 시 `raw_text`를 우선 사용하고, 없으면 `text`를 사용한다.

### 4.3 예시

```json
{
  "case_id": "CASE-2026-000123",
  "source": "civil_portal",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 OO구",
  "text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. 야간 보행 시 위험합니다. LED 교체를 요청합니다.",
  "metadata": {
    "channel": "web",
    "source_file": "sample_road_cases.csv"
  }
}
```

## 5. 구조화 필드 스키마

구조화 4요소는 동일한 하위 구조를 사용한다.

### 5.1 FieldExtraction 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `text` | string | Y | 추출된 텍스트 |
| `confidence` | number | Y | 0.0 ~ 1.0 |
| `evidence_span` | array[int, int] | Y | 원문 기준 시작/끝 인덱스 |

### 5.2 제약 조건
- `text`는 공백만으로 구성될 수 없다.
- `confidence`는 `0 <= value <= 1` 이어야 한다.
- `evidence_span`은 길이 2 배열이어야 한다.
- `evidence_span[0] <= evidence_span[1]` 이어야 한다.

### 5.3 예시

```json
{
  "text": "LED 교체와 조도 점검을 요청합니다.",
  "confidence": 0.93,
  "evidence_span": [61, 82]
}
```

## 6. 엔티티 스키마

### 6.1 Entity 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `label` | string | Y | 엔티티 타입 |
| `text` | string | Y | 엔티티 표면형 |
| `start` | integer | N | 시작 위치 |
| `end` | integer | N | 끝 위치 |
| `confidence` | number | N | 추출 신뢰도 |

### 6.2 허용 라벨

- `LOCATION`
- `TIME`
- `FACILITY`
- `HAZARD`
- `ADMIN_UNIT`

### 6.4 정규화/차단 규칙

- 비표준 라벨 매핑:
  - `TYPE` -> `HAZARD`
  - `RISK` -> `HAZARD`
  - `DATE` -> `TIME`
  - `PLACE` -> `LOCATION`
  - `AREA` -> `ADMIN_UNIT`
- 매핑이 발생하면 `validation.warnings`에 `entity_label_normalized:<OLD>-><NEW>`를 기록한다.
- 매핑 후에도 허용 라벨이 아니면 `invalid_entity_label:<LABEL>` 오류로 차단한다.

### 6.3 예시

```json
{
  "label": "FACILITY",
  "text": "가로등",
  "start": 8,
  "end": 11,
  "confidence": 0.88
}
```

## 7. 구조화 민원 객체 스키마

### 7.1 목적
- 저장소와 평가의 기준이 되는 핵심 객체

### 7.2 StructuredCivilCase 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `case_id` | string | Y | 민원 식별자 |
| `source` | string | Y | 데이터 출처 |
| `created_at` | string(datetime) | Y | 생성 시각 (ISO-8601, `+09:00`) |
| `category` | string | N | 민원 카테고리 |
| `region` | string | N | 지역 정보 |
| `raw_text` | string | Y | 원문 보관용 텍스트 |
| `observation` | object | Y | 관찰 내용 |
| `result` | object | Y | 영향/결과 |
| `request` | object | Y | 요청 사항 |
| `context` | object | Y | 발생 맥락 |
| `entities` | array[Entity] | Y | 추출 엔티티 목록 |
| `validation` | object | Y | 검증 결과 |

### 7.3 예시

```json
{
  "case_id": "CASE-2026-000123",
  "source": "civil_portal",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 OO구",
  "raw_text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. 야간 보행 시 시야가 확보되지 않아 넘어질 위험이 큽니다. LED 교체와 조도 점검을 요청합니다. 최근 2주간 매일 저녁 8시 이후 발생",
  "observation": {
    "text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
    "confidence": 0.91,
    "evidence_span": [0, 29]
  },
  "result": {
    "text": "야간 보행 시 시야가 확보되지 않아 넘어질 위험이 큽니다.",
    "confidence": 0.87,
    "evidence_span": [30, 60]
  },
  "request": {
    "text": "LED 교체와 조도 점검을 요청합니다.",
    "confidence": 0.93,
    "evidence_span": [61, 82]
  },
  "context": {
    "text": "최근 2주간 매일 저녁 8시 이후 발생",
    "confidence": 0.84,
    "evidence_span": [83, 104]
  },
  "entities": [
    {"label": "LOCATION", "text": "OO동 사거리"},
    {"label": "TIME", "text": "매일 저녁 8시"},
    {"label": "FACILITY", "text": "가로등"}
  ],
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

## 8. 검증 결과 스키마

### 8.1 ValidationResult 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `is_valid` | boolean | Y | 스키마 유효 여부 |
| `errors` | array | Y | 오류 목록 |
| `warnings` | array | Y | 경고 목록 (없으면 빈 배열) |

### 8.2 ValidationError 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `field` | string | Y | 문제 필드 |
| `code` | string | Y | 오류 코드 |
| `message` | string | Y | 설명 |

### 8.3 예시

```json
{
  "is_valid": false,
  "errors": [
    {
      "field": "request.text",
      "code": "EMPTY_TEXT",
      "message": "request.text는 비어 있을 수 없습니다."
    }
  ],
  "warnings": [
    {
      "field": "entities",
      "code": "LOW_ENTITY_COUNT",
      "message": "추출된 엔티티 수가 적습니다."
    }
  ]
}
```

## 9. 인덱싱용 청크 스키마

### 9.1 목적
- 벡터 저장소에 넣을 최소 단위 데이터
- 검색 및 citation의 공통 기준

### 9.2 SearchChunk 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `chunk_id` | string | Y | 청크 식별자 |
| `case_id` | string | Y | 원본 민원 식별자 |
| `chunk_text` | string | Y | 임베딩 대상 텍스트 |
| `chunk_type` | string | Y | `observation`, `result`, `request`, `context`, `combined` |
| `source` | string | Y | 데이터 출처 |
| `created_at` | string(datetime) | Y | 생성 시각 |
| `category` | string | N | 민원 카테고리 |
| `region` | string | N | 지역 |
| `entity_labels` | array[string] | N | 엔티티 라벨 목록 |
| `entity_texts` | array[string] | N | 엔티티 텍스트 목록 |
| `metadata` | object | N | 추가 메타데이터 |

### 9.3 예시

```json
{
  "chunk_id": "CASE-2026-000123__chunk-0",
  "case_id": "CASE-2026-000123",
  "chunk_text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. LED 교체와 조도 점검을 요청합니다.",
  "chunk_type": "combined",
  "source": "civil_portal",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 OO구",
  "entity_labels": ["LOCATION", "FACILITY", "TIME"],
  "entity_texts": ["OO동 사거리", "가로등", "매일 저녁 8시"]
}
```

## 10. 검색 결과 스키마

### 10.1 SearchResult 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `rank` | integer | Y | 검색 순위 |
| `doc_id` | string | Y | 문서 식별자 |
| `score` | number | Y | 유사도 점수 |
| `chunk_id` | string | Y | 청크 식별자 |
| `case_id` | string | Y | 민원 식별자 |
| `title` | string | Y | 검색 카드 제목 |
| `snippet` | string | Y | 근거 미리보기 |
| `summary` | object | N | FE 표시용 요약 |
| `metadata` | object | Y | 필터/표시용 메타데이터 |

### 10.2 metadata 하위 구조

```json
{
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 OO구",
  "entity_labels": ["FACILITY", "HAZARD"]
}
```

### 10.3 summary 하위 구조

```json
{
  "observation": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
  "request": "LED 교체와 조도 점검을 요청합니다."
}
```

### 10.3 예시

```json
{
  "rank": 1,
  "score": 0.9123,
  "chunk_id": "CASE-2026-000123__chunk-0",
  "case_id": "CASE-2026-000123",
  "snippet": "...가로등이 깜빡거리고 일부 구간이 소등됩니다...",
  "summary": {
    "observation": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
    "request": "LED 교체와 조도 점검을 요청합니다."
  },
  "metadata": {
    "created_at": "2026-03-05T10:15:00+09:00",
    "category": "도로안전",
    "region": "서울시 OO구",
    "entity_labels": ["FACILITY", "HAZARD"]
  }
}
```

## 11. QA citation 스키마

### 11.1 Citation 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `ref_id` | integer | Y | 본문 토큰 `[[CITE:n]]`와 매핑되는 키 |
| `doc_id` | string | 조건부 | retrieval 결과에 존재할 때 포함 |
| `chunk_id` | string | Y | 근거 청크 ID |
| `case_id` | string | Y | 원본 민원 ID |
| `snippet` | string | Y | 인용 원문 일부 |
| `relevance_score` | number | N | citation 근거 점수(0~1) |
| `source` | string | N | citation 출처 타입 (예: retrieval) |

### 11.2 예시

```json
{
  "ref_id": 1,
  "doc_id": "DOC-25-088",
  "chunk_id": "CASE-2026-000123__chunk-0",
  "case_id": "CASE-2026-000123",
  "snippet": "...가로등이 깜빡거리고 일부 구간이 소등됩니다...",
  "relevance_score": 0.89,
  "source": "retrieval"
}
```

## 12. QA 응답 스키마

### 12.1 QAResponse 객체

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `success` | boolean | Y | 성공=true, 실패=false |
| `request_id` | string | Y | 요청 추적 ID |
| `timestamp` | string(datetime) | Y | 응답 시각 (ISO-8601, `+09:00`) |
| `answer` | string | success=true 시 Y | 생성 답변 |
| `citations` | array[Citation] | success=true 시 Y | 근거 목록 |
| `confidence` | string | success=true 시 Y | `low`, `medium`, `high` |
| `limitations` | string | success=true 시 Y | 해석 한계 또는 주의사항 |
| `meta` | object | success=true 시 Y | 처리시간/모델/검증 안내 |
| `qa_validation` | object | success=true 시 Y | 검증 결과 |
| `search_trace` | object | success=true 시 Y | 검색 추적 정보 |
| `error` | object | success=false 시 Y | 에러 코드/메시지/재시도 가능 여부 |

### 12.2 meta 예시

```json
{
  "processing_time": 6.2,
  "model": "qwen2.5:7b-instruct",
  "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다."
}
```

### 12.3 예시

```json
{
  "success": true,
  "request_id": "REQ-20260317-AB12CD34",
  "timestamp": "2026-03-17T18:30:00+09:00",
  "answer": "최근 3개월 도로 안전 민원은 야간 조명 불량과 보행자 안전 문제에 집중되어 있습니다. [[CITE:1]]",
  "citations": [
    {
      "ref_id": 1,
      "doc_id": "DOC-25-088",
      "chunk_id": "CASE-2026-000123__chunk-0",
      "case_id": "CASE-2026-000123",
      "snippet": "...가로등이 깜빡거리고 일부 구간이 소등됩니다...",
      "relevance_score": 0.89,
      "source": "retrieval"
    },
    {
      "ref_id": 2,
      "doc_id": "DOC-24-913",
      "chunk_id": "CASE-2026-000204__chunk-0",
      "case_id": "CASE-2026-000204",
      "snippet": "...보행자 전도 위험이 증가하고 있습니다...",
      "relevance_score": 0.84,
      "source": "retrieval"
    }
  ],
  "confidence": "medium",
  "limitations": "수집 데이터 기간이 제한되어 장기 추세 해석에는 주의가 필요합니다.",
  "meta": {
    "processing_time": 6.2,
    "model": "qwen2.5:7b-instruct",
    "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다."
  },
  "qa_validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  },
  "search_trace": {
    "used_top_k": 5,
    "retrieved_count": 5
  }
}
```

### 12.4 실패 예시

```json
{
  "success": false,
  "request_id": "REQ-20260317-34EF56AA",
  "timestamp": "2026-03-17T18:35:00+09:00",
  "error": {
    "code": "PARSE_RETRY_EXHAUSTED",
    "message": "모델 응답을 JSON으로 파싱하지 못했습니다.",
    "retryable": true,
    "details": {
      "retry_count": 3,
      "stage": "decode"
    }
  }
}
```

## 13. 스키마 검증 규칙 요약

### 13.1 구조화 민원 검증 규칙
- `case_id`, `source`, `created_at`, `raw_text`는 필수
- `observation`, `result`, `request`, `context`는 모두 필수
- 각 4요소의 `text`는 빈 문자열일 수 없음
- `confidence`는 0~1 범위
- `entities[].label`은 허용 라벨 목록에 포함되어야 함

### 13.2 검색 결과 검증 규칙
- `rank`는 1 이상
- `score`는 number
- `chunk_id`, `case_id`, `snippet`은 필수

### 13.3 QA 응답 검증 규칙
- `success=true/false`를 항상 포함
- `success=true`일 때 `answer`, `citations`, `confidence`, `limitations`, `meta`, `qa_validation` 포함
- `success=false`일 때 `error.code`, `error.message`, `error.retryable` 포함
- `answer` 내 `[[CITE:n]]` 토큰은 `citations.ref_id`와 1:1 매칭
- `citations.ref_id`는 응답 내 유일
- `chunk_id`는 검색 결과 목록에 존재하고 `case_id`와 일치
- `limitations`는 빈 문자열 불가
- `confidence`는 `low`, `medium`, `high` 중 하나

## 14. 저장 포맷과 API 포맷의 관계

### 저장 포맷
- `StructuredCivilCase`
- `SearchChunk`
- 평가용 annotation 포맷

### API 응답 포맷
- 저장 포맷을 그대로 쓰되, UI 친화적 필드를 일부 추가 가능
- 예: `validation`, `summary`, `took_ms`, `search_trace`

즉, 저장 포맷은 엄격하고, API 응답은 약간 더 표현 친화적으로 가져간다.

## 15. 오픈 이슈

- `raw_text`를 항상 저장할지, 마스킹 버전과 분리 저장할지 결정 필요
- `entity start/end`를 MVP에서 필수로 할지 선택 필요
- chunk 전략을 `combined` 중심으로 할지, 4요소별 분리 인덱싱을 병행할지 검토 필요
- `category`, `region`을 입력 필수로 강제할지 후처리 추출로 둘지 결정 필요

## 16. 후속 산출물 연결

이 문서를 기준으로 다음 파일을 이어서 만들 수 있다.

- `schemas/civil_case.schema.json`
- `schemas/search_result.schema.json`
- `schemas/qa_response.schema.json`
- `app/api/schemas/*.py`
- `app/structuring/validators/schema_validator.py`

## 17. 결론

이 스키마 계약의 핵심은 **모든 모듈이 같은 데이터 언어를 사용하게 만드는 것**이다.  
특히 이 프로젝트는 구조화 → 인덱싱 → 검색 → QA → 평가가 강하게 연결되어 있으므로, 스키마가 흔들리면 후반 통합 비용이 급격히 커진다.  
따라서 MVP 단계에서는 유연성보다 **명확성, 검증 가능성, 재현 가능성**을 우선해야 한다.

## 18. Week 2 공식 계약 섹션 (2026-03-18 확정)

본 섹션은 BE1-BE2-BE3 연동을 위한 운영 계약 우선 규칙이다.  
기존 문서의 예시와 충돌할 경우 본 섹션을 우선 적용한다.

### 18.1 전달 최소 필수 필드 (BE2 인덱싱 기준)

- `case_id`
- `created_at`
- `source`

### 18.2 권장 필드

- `category`
- `region`
- `entities` (BE2 `entity_labels` 파생용)
- `raw_text` (청킹/임베딩 원문)

### 18.3 필드 보정(어댑터) 규칙

- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`

### 18.4 제공 불가 필드 대체값 정책

- `category`: 값이 비었거나 `-`면 `unknown`
- `region`: 값이 없으면 `unknown`
- `entities`: 추출 전 단계면 `[]`

### 18.5 원천데이터(AIHub) 매핑 규칙

| 원천 필드 | 전달 필드 | 정책 |
| --- | --- | --- |
| `source_id` | `case_id` | 문자열 유지 |
| `source` | `source` | 공백/누락 시 `unknown` |
| `consulting_date` | `created_at` | ingest에서 수용 후 내부 저장/API 출력은 ISO-8601 KST(`+09:00`) 변환 |
| `consulting_category` | `category` | `-`는 `unknown` |
| `consulting_content` | `raw_text` | 원문 보존 |

### 18.6 Week 2 전달 경로

- 1차: 파일 전달(JSON)
- 2차: API 전달(`POST /api/v1/ingest`, `POST /api/v1/structure`) 병행

### 18.7 전달 객체 샘플 (Week 2)

```json
{
  "case_id": "000022",
  "source": "서울시",
  "created_at": "2024-07-09T00:00:00+09:00",
  "category": "재난안전",
  "region": "unknown",
  "raw_text": "제목 : 한가람로 풍납동까지 연결해 주세요...",
  "entities": [],
  "metadata": {
    "source_id": "000022",
    "consulting_turns": 2,
    "consulting_length": 199,
    "client_gender": "남",
    "client_age": "30대"
  }
}
```

## 19. 라벨링 데이터(supervision) 활용 계약

AIHub 제공 라벨링 데이터(`분류`, `요약`, `질의응답`)는 아래 원칙으로 사용한다.

- 저장: `supervision` 필드에 보존 가능
- 사용 권장: 약지도(weak supervision), 프롬프트/리랭커 보정, 회귀 테스트셋 구축
- 사용 제한: 최종 KPI 산출용 gold 정답셋으로 단독 사용 금지
- 이유: 제공기관 모델 출력물 기반이므로 편향/오답 전파와 데이터 누수 위험 존재

### 19.1 supervision 구조

```json
{
  "supervision": {
    "classification": {
      "task_category": "상담 요건",
      "instruction": "...",
      "input": "...",
      "output": "단일 요건 민원"
    },
    "summary": {
      "task_category": "길이 제한 요약",
      "instruction": "...",
      "input": "...",
      "output": "..."
    },
    "qa": [
      {
        "task_category": "예/아니요형",
        "instruction": "현재 시에서는 한가람로 개설을 확정했어?",
        "question": "현재 시에서는 한가람로 개설을 확정했어?",
        "answer": "아니."
      }
    ]
  }
}
```

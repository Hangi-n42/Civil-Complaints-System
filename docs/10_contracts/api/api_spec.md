# API 명세서 초안

문서 버전: v1.1-week2-aligned  
기준 문서: [PRD](../../00_overview/prd.md), [MVP 범위 문서](../../00_overview/mvp_scope.md), [폴더 구조 초안](../../00_overview/folder_structure_draft.md)  
작성일: 2026-03-11
최신화: 2026-03-25 (422 래퍼 통일, +09:00 출력 시각 정책 반영)

## 0. Week2 우선 적용 규칙 (Contract Freeze)

- Week2 구현/검증 시 `docs/10_contracts/interfaces/week2/*` 문서를 최우선으로 적용한다.
- 본 문서와 충돌하면 Week2 공통 규약을 우선한다.
- 본 문서는 Week2 이후 확장(API 범위 전체) 시 기준 문서로 유지한다.

## 1. 문서 목적

본 문서는 프론트엔드, 백엔드, 평가 파이프라인이 동일한 인터페이스를 기준으로 개발할 수 있도록 API 계약을 정의한다.  
MVP 단계에서는 **명확한 요청/응답 구조**, **에러 처리 일관성**, **근거 데이터 전달 방식**을 고정하는 것이 목표다.

## 2. API 설계 원칙

### 2.1 기본 원칙
- 모든 API는 로컬 환경에서 동작한다.
- 응답은 JSON을 기본으로 한다.
- 성공/실패 형식을 최대한 일관되게 유지한다.
- UI에 필요한 상태 정보와 디버깅 가능한 메시지를 함께 제공한다.
- RAG 응답은 반드시 근거(citations)를 포함한다.

### 2.2 Base URL

- 로컬 개발 기준: `http://localhost:8000`
- API prefix: `/api/v1`

예시:
- `GET /api/v1/health`
- `POST /api/v1/ingest`

## 3. 공통 규약

### 3.1 공통 성공 응답 원칙

각 엔드포인트는 아래 공통 래퍼를 사용한다.

```json
{
  "success": true,
  "request_id": "REQ-20260320-AB12CD34",
  "timestamp": "2026-03-20T10:00:00+09:00",
  "data": {}
}
```

### 3.2 공통 에러 응답 형식

```json
{
  "success": false,
  "request_id": "REQ-20260320-EF56GH78",
  "timestamp": "2026-03-20T10:00:01+09:00",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 본문 형식이 올바르지 않습니다.",
    "retryable": false,
    "details": {
      "field": "created_at"
    }
  }
}
```

추가 규칙:
- FastAPI/Pydantic 검증 실패(HTTP 422)도 기본 예외 포맷을 그대로 노출하지 않고, 위 실패 래퍼 형식으로 반환한다.
- 422 검증 실패의 `error.code`는 `VALIDATION_ERROR`로 통일한다.
- 422 검증 실패의 `error.details`에는 최소 `path`, `errors`를 포함한다.

422 예시:
```json
{
  "success": false,
  "request_id": "REQ-20260325-AB12CD34",
  "timestamp": "2026-03-25T11:00:00+09:00",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 본문 형식이 올바르지 않습니다.",
    "retryable": false,
    "details": {
      "path": "/api/v1/search",
      "errors": []
    }
  }
}
```

### 3.3 시각(datetime) 출력 정책

- API 출력 시각 필드(`timestamp`, `created_at`, `structured_at`, `generated_at`, `last_updated_at`)는 ISO-8601 KST 오프셋 포함 형식(`+09:00`)을 사용한다.
- 입력에서 타임존 정보가 없는 값이 들어오면 내부 정규화 단계에서 KST(`+09:00`)를 부여한 뒤 출력한다.
- 시간대 표기는 혼용하지 않는다(`Z`, naive datetime, `+09:00` 혼재 금지).

### 3.4 공통 에러 코드

| 코드 | 의미 |
| --- | --- |
| `VALIDATION_ERROR` | 요청 필드 검증 실패 |
| `BAD_REQUEST` | 필수 인자 누락 또는 잘못된 형식 |
| `MODEL_NOT_READY` | LLM/임베딩 모델 사용 불가 |
| `INDEX_NOT_READY` | 인덱스 미생성 또는 로드 실패 |
| `PROCESSING_ERROR` | 내부 처리 실패 |
| `PARSE_JSON_DECODE_ERROR` | LLM 응답 JSON 디코딩 실패 |
| `PARSE_JSON_BLOCK_EXTRACTION_FAILED` | 응답에서 JSON 블록 추출 실패 |
| `PARSE_SCHEMA_MISMATCH` | JSON 스키마 필수 필드 불일치 |
| `PARSE_RETRY_EXHAUSTED` | 파싱 재시도(3회) 모두 실패 (retryable=false) |
| `RESOURCE_NOT_FOUND` | 대상 데이터 없음 |
| `INTERNAL_SERVER_ERROR` | 예기치 못한 서버 오류 |

## 4. 엔드포인트 개요

| Method | Endpoint | 설명 | 우선순위 | Week2 상태 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/health` | 서버/모델/인덱스 상태 확인 | 필수 | 구현 |
| `POST` | `/api/v1/ingest` | 민원 원문 업로드 및 적재 | 필수 | 미구현 (Week3 예정) |
| `POST` | `/api/v1/structure` | 4요소 구조화 및 엔티티 추출 | 필수 | 미구현 (Week3 예정) |
| `POST` | `/api/v1/index` | 임베딩 생성 및 인덱스 반영 | 필수 | 구현 |
| `POST` | `/api/v1/search` | 시맨틱 검색 및 필터 검색 | 필수 | 구현 |
| `POST` | `/api/v1/qa` | 검색 기반 RAG 질의응답 | 필수 | 구현 |

---

## 5. `GET /api/v1/health`

### 목적
- 서버 상태 확인
- 모델 로딩 상태 확인
- 인덱스 준비 여부 확인

### 요청
- 바디 없음
- 호환 경로: `/health` (legacy alias)

### 성공 응답 예시

```json
{
  "success": true,
  "request_id": "REQ-20260320-AB12CD34",
  "timestamp": "2026-03-11T14:30:00+09:00",
  "data": {
    "status": "ok",
    "services": {
      "api": "up",
      "embedding_model": "ready",
      "llm": "ready",
      "vector_store": "ready"
    },
    "index": {
      "is_ready": true,
      "document_count": 523,
      "last_updated_at": "2026-03-11T13:20:00+09:00"
    }
  }
}
```

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 |
| `503` | 모델 또는 인덱스 준비 안 됨 |

---

## 6. `POST /api/v1/ingest`

### 목적
- CSV/JSON/수동 입력 민원을 수집한다.
- 기본 전처리와 PII 마스킹을 수행한다.
- 표준 내부 포맷으로 저장 가능한 상태로 변환한다.

### 요청 바디

```json
{
  "source_type": "manual",
  "source": "demo_input",
  "mask_pii": true,
  "deduplicate": true,
  "records": [
    {
      "case_id": "CASE-2026-000123",
      "created_at": "2026-03-05T10:15:00+09:00",
      "category": "도로안전",
      "region": "서울시 OO구",
      "text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. 야간 보행 시 위험합니다. LED 교체를 요청합니다. 최근 2주간 매일 저녁 8시 이후 발생합니다."
    }
  ]
}
```

### 요청 필드 설명

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `source_type` | string | Y | `manual`, `csv`, `json` |
| `source` | string | Y | 업로드 소스 이름 |
| `mask_pii` | boolean | N | 개인정보 마스킹 여부 |
| `deduplicate` | boolean | N | 중복 탐지 여부 |
| `records` | array | Y | 민원 레코드 목록 |
| `records[].case_id` | string | Y | 민원 식별자 |
| `records[].created_at` | string(datetime) | Y | 생성 시각 |
| `records[].category` | string | N | 민원 카테고리 |
| `records[].region` | string | N | 행정 구역 |
| `records[].text` | string | N | 원문 민원 텍스트 (`raw_text` 대체 허용) |
| `records[].raw_text` | string | N | 원문 민원 텍스트 (`text` 대체 허용) |

추가 규칙:
- BE1 입력 단계에서는 `text` 또는 `raw_text` 중 하나를 허용한다.
- 내부 처리 우선순위는 `raw_text > text`를 적용한다.

### 성공 응답 예시

```json
{
  "success": true,
  "request_id": "REQ-20260320-AB12CD34",
  "timestamp": "2026-03-20T10:00:00+09:00",
  "data": {
    "ingested_count": 1,
    "skipped_count": 0,
    "mask_pii": true,
    "deduplicate": true,
    "records": [
      {
        "case_id": "CASE-2026-000123",
        "status": "accepted",
        "normalized_text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. 야간 보행 시 위험합니다. LED 교체를 요청합니다. 최근 2주간 매일 저녁 8시 이후 발생합니다."
      }
    ]
  }
}
```

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 처리 |
| `400` | 잘못된 요청 |
| `422` | 입력 검증 실패 (`VALIDATION_ERROR` 래퍼 반환) |
| `500` | 내부 처리 오류 |

---

## 7. `POST /api/v1/structure`

### 목적
- 민원 원문을 4요소 구조로 변환한다.
- NER 엔티티를 추출한다.
- 스키마 검증 결과를 함께 반환한다.

### 요청 바디

```json
{
  "records": [
    {
      "case_id": "CASE-2026-000123",
      "source": "civil_portal",
      "created_at": "2026-03-05T10:15:00+09:00",
      "category": "도로안전",
      "region": "서울시 OO구",
      "text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다. 야간 보행 시 시야 확보가 어렵습니다. LED 교체와 조도 점검을 요청합니다. 최근 2주간 매일 저녁 8시 이후 발생했습니다."
    }
  ]
}
```

### 성공 응답 예시

```json
{
  "success": true,
  "structured_count": 1,
  "results": [
    {
      "case_id": "CASE-2026-000123",
      "source": "civil_portal",
      "created_at": "2026-03-05T10:15:00+09:00",
      "category": "도로안전",
      "region": "서울시 OO구",
      "observation": {
        "text": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
        "confidence": 0.91,
        "evidence_span": [0, 29]
      },
      "result": {
        "text": "야간 보행 시 시야 확보가 어렵습니다.",
        "confidence": 0.87,
        "evidence_span": [30, 52]
      },
      "request": {
        "text": "LED 교체와 조도 점검을 요청합니다.",
        "confidence": 0.93,
        "evidence_span": [53, 74]
      },
      "context": {
        "text": "최근 2주간 매일 저녁 8시 이후 발생했습니다.",
        "confidence": 0.84,
        "evidence_span": [75, 101]
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
  ]
}
```

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 처리 |
| `422` | 스키마 또는 요청 검증 실패 (`VALIDATION_ERROR` 래퍼 반환) |
| `500` | 구조화 처리 실패 |

---

## 8. `POST /api/v1/index`

### 목적
- 구조화 결과를 청킹한다.
- 임베딩을 생성한다.
- 벡터 저장소에 문서를 저장한다.

### 요청 바디

```json
{
  "rebuild": false,
  "records": [
    {
      "case_id": "CASE-2026-000123",
      "category": "도로안전",
      "region": "서울시 OO구",
      "created_at": "2026-03-05T10:15:00+09:00",
      "structured_text": {
        "observation": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
        "result": "야간 보행 시 시야 확보가 어렵습니다.",
        "request": "LED 교체와 조도 점검을 요청합니다.",
        "context": "최근 2주간 매일 저녁 8시 이후 발생했습니다."
      },
      "entities": [
        {"label": "LOCATION", "text": "OO동 사거리"},
        {"label": "TIME", "text": "매일 저녁 8시"},
        {"label": "FACILITY", "text": "가로등"}
      ]
    }
  ]
}
```

### 성공 응답 예시

```json
{
  "success": true,
  "indexed_count": 1,
  "chunk_count": 2,
  "index_name": "civil_cases",
  "rebuild": false,
  "records": [
    {
      "case_id": "CASE-2026-000123",
      "chunk_ids": ["CHUNK-00044", "CHUNK-00045"]
    }
  ]
}
```

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 처리 |
| `400` | 인덱싱 입력 부족 |
| `500` | 임베딩/저장소 오류 |

---

## 9. `POST /api/v1/search`

### 목적
- 자연어 질의 기반 유사 민원을 검색한다.
- 기간/지역/카테고리/엔티티 라벨 메타데이터 필터를 적용한다.

### 요청 바디

```json
{
  "query": "최근 3개월 도로 안전 관련 민원",
  "top_k": 5,
  "filters": {
    "region": "서울시 OO구",
    "category": "도로안전",
    "date_from": "2025-12-01T00:00:00+09:00",
    "date_to": "2026-03-11T23:59:59+09:00",
    "entity_labels": ["FACILITY", "HAZARD"]
  }
}
```

### 요청 필드 설명

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `query` | string | Y | 사용자 자연어 질의 |
| `top_k` | integer | N | 기본값 5 |
| `filters.region` | string | N | 지역 필터 |
| `filters.category` | string | N | 카테고리 필터 |
| `filters.date_from` | string(datetime) | N | 시작일 |
| `filters.date_to` | string(datetime) | N | 종료일 |
| `filters.entity_labels` | array[string] | N | 엔티티 라벨 필터 (OR 매칭) |

### 성공 응답 예시

```json
{
  "success": true,
  "query": "최근 3개월 도로 안전 관련 민원",
  "top_k": 5,
  "results": [
    {
      "rank": 1,
      "doc_id": "DOC-25-102",
      "score": 0.94,
      "chunk_id": "CASE-2026-000123__chunk-0",
      "case_id": "CASE-2026-000123",
      "title": "중앙로 10m 인근 포트홀 임시 복구 완료건",
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
  ],
  "count": 1,
  "took_ms": 428
}
```

### FE 카드 연동 규칙 (Week 1 확정)

- `results`는 반드시 배열(Array)로 반환
- `results[].doc_id`, `results[].score`, `results[].title`, `results[].snippet` 필수
- `score`는 소수점 둘째 자리 반올림
- `snippet`은 100~150자 내외로 제한 (권장 140자)

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 처리 |
| `400` | 질의 누락 또는 필터 형식 오류 |
| `503` | 인덱스 미준비 |
| `500` | 검색 처리 오류 |

---

## 10. `POST /api/v1/qa`

### 목적
- 검색 결과를 기반으로 근거 기반 답변을 생성한다.
- citations, confidence, limitations를 함께 반환한다.

### 요청 바디

```json
{
  "query": "최근 3개월 도로 안전 민원의 주요 이슈를 요약해줘.",
  "top_k": 5,
  "filters": {
    "category": "도로안전"
  },
  "use_search_results": true,
  "search_results": [
    {
      "chunk_id": "CASE-2026-000123__chunk-0",
      "case_id": "CASE-2026-000123",
      "snippet": "OO동 사거리 가로등이 깜빡거리고 일부 구간이 소등됩니다.",
      "score": 0.9123
    }
  ]
}
```

### 요청 처리 방식

MVP 기준 두 가지 모드를 허용한다.

1. `use_search_results=true`
   - 클라이언트가 `/search` 결과를 재전달
   - 디버깅 및 UI 제어가 쉬움
2. `use_search_results=false` 또는 미전달
   - 서버 내부에서 검색 후 QA 수행
   - 단일 호출 데모에 유리함

### 성공 응답 예시

```json
{
  "success": true,
  "request_id": "REQ-20260317-AB12CD34",
  "timestamp": "2026-03-17T18:30:00+09:00",
  "answer": "이륜차 전도 위험이 높은 구간으로 확인됩니다. [[CITE:1]] 우천 후 노면 파손 재발 이력이 있습니다. [[CITE:2]]",
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
  "limitations": "수집 데이터 기간과 지역 범위에 따라 해석에 제한이 있습니다.",
  "meta": {
    "processing_time": 6.2,
    "model": "qwen2.5:7b-instruct",
    "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다.",
    "generated_at": "2026-03-17T18:30:00+09:00",
    "validator_version": "be3-val-v0.1"
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

### 실패 응답 예시

```json
{
  "success": false,
  "request_id": "REQ-20260317-34EF56AA",
  "timestamp": "2026-03-17T18:35:00+09:00",
  "error": {
    "code": "PARSE_RETRY_EXHAUSTED",
    "message": "모델 응답을 JSON으로 파싱하지 못했습니다.",
    "retryable": false,
    "details": {
      "retry_count": 3,
      "stage": "decode"
    }
  }
}
```

### 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 정상 처리 |
| `422` | 요청 형식 오류 (`VALIDATION_ERROR` 래퍼 반환) |
| `503` | 모델 또는 인덱스 준비 안 됨 |
| `500` | 생성 또는 파싱 실패 |

---

## 11. FE 연동 기준

### 데이터 적재(선택)
- `POST /api/v1/ingest`
- 필요 시 연속으로 `POST /api/v1/structure`
- 데모 UI는 **파일 업로드 화면을 제공하지 않으며**, 적재는 스크립트/배치로 수행할 수 있다.

### 큐/워크벤치: 구조화 확인
- `POST /api/v1/structure`
- `validation.is_valid`와 `errors`를 함께 표시

### 검색 화면
- `POST /api/v1/search`
- `results[].score`, `results[].snippet`, `results[].metadata` 표시

### QA 화면
- `POST /api/v1/qa`
- `answer` 내 `[[CITE:n]]` 토큰을 `[출처 n]` 배지로 치환
- `citations.ref_id`와 토큰을 1:1 매핑
- `meta.processing_time`, `meta.model`, `meta.validation_warning` 표시
- `success=false` 시 상단 배너에 `error.message` 표시

## 12. 로깅 기준

모든 주요 엔드포인트는 아래 항목을 로그로 남기는 것을 권장한다.

- 요청 시각
- 요청 ID
- endpoint
- 처리 시간(ms)
- 성공 여부
- 에러 코드
- 입력 건수 또는 검색 건수
- 모델명/인덱스명

## 13. MVP 단계의 구현 우선순위

1. `GET /health`
2. `POST /structure`
3. `POST /index`
4. `POST /search`
5. `POST /qa`
6. `POST /ingest`

이 순서는 기술 구현 순서 기준이다.  
실제 사용자 흐름은 `ingest -> structure -> index -> search -> qa`이지만, 개발 초기에는 `structure/search/qa` 핵심 체인을 먼저 검증하는 것이 효율적이다.

## 14. 오픈 이슈

- `/ingest`에서 파일 업로드를 직접 받을지, 프론트에서 파싱 후 JSON으로 넘길지 결정 필요
- `/qa`가 항상 서버 내부 검색을 수행할지, 검색 결과를 입력받을지 최종 결정 필요
- 검색 결과의 `score`를 raw similarity로 노출할지 정규화할지 결정 필요
- 대량 인덱싱 시 비동기 작업 큐가 필요한지 후속 검토 필요

## 15. 결론

이 API 명세의 핵심은 **팀이 같은 계약을 보고 병렬 개발할 수 있게 만드는 것**이다.  
MVP 단계에서는 완벽한 범용성보다, **구조화·검색·QA의 일관된 데이터 흐름과 citation 전달 규칙**을 먼저 고정하는 것이 중요하다.

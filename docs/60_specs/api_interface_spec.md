# API Interface Spec (FastAPI ↔ Next.js Workbench)

문서 버전: v1.1  
기준: PRD v2.1, WBS v4.1, 사용자 시나리오 v1.1(6장, 11장)

## 1. 목적

`/search`, `/qa` 엔드포인트의 요청/응답 계약을 고정한다.  
Week5-8 동안 필수 adaptive 필드(`routing_trace`, `routing_hint`, `structured_output`) 누락을 허용하지 않는다.  
라우팅은 `topic_type + complexity_level` 기반으로 수행한다.

## 2. 공통 규칙

- API Base: `/api/v1` (환경별 prefix 허용)
- Content-Type: `application/json`
- 시간 필드: ISO-8601 `+09:00`
- 공통 응답 래퍼:
  - 성공: `success`, `request_id`, `timestamp`, `data`
  - 실패: `success`, `request_id`, `timestamp`, `error`

## 3. `/search` API

## 3.1 Request Schema

```json
{
  "complaint_id": "CMP-2026-0001",
  "query": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
  "top_k": 6,
  "filters": {
    "region": "seoul",
    "category": "welfare"
  }
}
```

필드 정의:
- `complaint_id` (string, optional)
- `query` (string, required)
- `top_k` (integer, optional)
- `filters` (object, optional)
- `request_id` (string, optional)

## 3.2 Response Schema (Success)

```json
{
  "success": true,
  "request_id": "req-20260410-0001",
  "timestamp": "2026-04-10T17:15:00+09:00",
  "data": {
    "complaint_id": "CMP-2026-0001",
    "strategy_id": "topic_welfare_high_v1",
    "route_key": "welfare/high",
    "routing_hint": {
      "strategy_id": "topic_welfare_high_v1",
      "route_key": "welfare/high",
      "top_k": 9,
      "snippet_max_chars": 1100,
      "chunk_policy": "expanded"
    },
    "routing_trace": {
      "topic_type": "welfare",
      "complexity_level": "high",
      "complexity_score": 0.81,
      "complexity_trace": {
        "intent_count": 3,
        "constraint_count": 4,
        "entity_diversity": 3,
        "policy_reference_count": 1,
        "cross_sentence_dependency": true
      },
      "route_reason": "복지 주제 + 고복잡도 민원으로 expanded 검색 전략 선택"
    },
    "retrieved_docs": [
      {
        "rank": 1,
        "case_id": "CASE-001",
        "doc_id": "DOC-001",
        "title": "유사 민원 처리 사례",
        "snippet": "관리비 이의제기 처리 절차...",
        "similarity_score": 0.89,
        "score": 0.89,
        "chunk_id": "CASE-001__chunk-0",
        "summary": {
          "observation": "관리비 이의제기 민원",
          "request": "처리 절차 안내"
        },
        "metadata": {
          "created_at": "2026-04-10T11:20:00+09:00",
          "category": "welfare",
          "region": "seoul",
          "entity_labels": ["FACILITY"],
          "strategy_id": "topic_welfare_high_v1",
          "route_key": "welfare/high"
        }
      }
    ]
  }
}
```

## 4. `/qa` API

## 4.1 Request Schema

```json
{
  "complaint_id": "CMP-2026-0001",
  "query": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
  "routing_hint": {
    "strategy_id": "topic_welfare_high_v1",
    "route_key": "welfare/high",
    "top_k": 9,
    "snippet_max_chars": 1100,
    "chunk_policy": "expanded"
  },
  "use_search_results": true,
  "search_results": [
    {
      "doc_id": "DOC-001",
      "chunk_id": "CASE-001__chunk-0",
      "case_id": "CASE-001",
      "snippet": "관리비 이의제기 처리 절차...",
      "score": 0.89
    }
  ]
}
```

필드 정의:
- `complaint_id` (string, required)
- `query` (string, required)
- `routing_hint` (object, required)
- `use_search_results` (boolean, optional)
- `search_results` (array, optional: `/search` 연계 시 전달)

## 4.2 Response Schema (Success)

```json
{
  "success": true,
  "request_id": "req-20260410-0002",
  "timestamp": "2026-04-10T17:15:01+09:00",
  "data": {
    "complaint_id": "CMP-2026-0001",
    "strategy_id": "topic_welfare_high_v1",
    "route_key": "welfare/high",
    "routing_trace": {
      "topic_type": "welfare",
      "complexity_level": "high",
      "complexity_score": 0.81,
      "complexity_trace": {
        "intent_count": 3,
        "constraint_count": 4,
        "entity_diversity": 3,
        "policy_reference_count": 1,
        "cross_sentence_dependency": true
      },
      "route_reason": "검색 단계와 동일 전략 유지"
    },
    "structured_output": {
      "summary": "임대주택 보수 지연 및 관리비 이의제기 관련 민원",
      "action_items": [
        "보수 일정 회신",
        "관리비 산정 근거 안내"
      ],
      "request_segments": [
        "보수 지연",
        "관리비 이의제기"
      ]
    },
    "answer": "문의하신 보수 지연 및 관리비 관련 사항에 대해...",
    "citations": [
      {
        "doc_id": "DOC-001",
        "source": "civil_db",
        "quote": "관리비 이의제기 처리 절차..."
      }
    ],
    "limitations": [
      "현장 점검 전 최종 확정 불가"
    ],
    "latency_ms": {
      "analyzer": 48,
      "router": 8,
      "retrieval": 132,
      "generation": 920
    },
    "quality_signals": {
      "citation_coverage": 0.92,
      "hallucination_flag": false,
      "segment_coverage": 1.0
    }
  }
}
```

## 5. Error Schema

```json
{
  "success": false,
  "request_id": "req-20260410-0003",
  "timestamp": "2026-04-10T17:15:02+09:00",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "routing_hint is required",
    "retryable": false,
    "details": {}
  }
}
```

참고:
- 본문 스키마 파싱 실패 경로는 `VALIDATION_ERROR` + HTTP 422로 반환될 수 있다.

## 6. 계약 고정 체크포인트 (Week5-8)

- `/search` 응답은 반드시 `routing_trace`, `routing_hint`, `strategy_id`, `route_key`를 포함한다.
- `route_key`는 `{topic_type}/{complexity_level}` 포맷을 사용한다.
- `/qa` 요청은 반드시 `routing_hint`를 포함한다.
- `/qa` 요청에서 `/search` 연계 전달 시 `use_search_results=true`와 `search_results[]`를 사용한다.
- `/qa` 응답은 반드시 `routing_trace`, `structured_output`, `answer`, `citations`를 포함한다.
- `routing_trace`에는 `topic_type`, `complexity_level`, `complexity_score`, `complexity_trace`가 포함되어야 한다.
- 관측 필드는 시나리오 11장 기준으로 `latency_ms`, `quality_signals`를 유지한다.

## 7. `/qa/stream` SSE API

`POST /api/v1/qa/stream`은 `/api/v1/qa`와 동일한 요청 본문을 받고,
실제 QA 파이프라인 경계에 맞춰 `text/event-stream` 이벤트를 반환한다.
기존 `/api/v1/qa`는 변경 없이 유지한다.

이 엔드포인트는 POST 요청이므로 브라우저 기본 `EventSource` 대신
`fetch` 응답의 `ReadableStream`으로 소비한다.

### 7.1 Stage Events

```text
event: stage
data: {"stage":"retrieving","label":"유사 사례 분석 중"}

event: stage
data: {"stage":"grounding","label":"관련 근거 정리 중"}

event: stage
data: {"stage":"generating","label":"초안 작성 중"}
```

- `retrieving`: 요청 검증 후 검색/전달 검색 결과의 grounding filter를 수행하는 단계
- `grounding`: retrieval 완료 후 QA context를 구성하고 근거를 정리하는 단계
- `generating`: 실제 생성 서비스 호출 직전부터 최종 응답 정규화까지의 단계
- 근거가 없어 안전 fallback을 반환하는 경우 `generating`은 생략될 수 있다.

### 7.2 Terminal Events

성공 시 `done`의 data는 기존 `/api/v1/qa` 성공 응답 본문과 동일하다.

```text
event: done
data: {"success":true,"request_id":"...","timestamp":"...","data":{...}}
```

스트림이 시작된 뒤 발생한 검증/검색/생성 오류는 기존 QA 오류 본문을
`error` 이벤트 data로 반환한다. SSE 연결 자체의 HTTP 상태는 `200`이다.

```text
event: error
data: {"success":false,"request_id":"...","timestamp":"...","error":{...}}
```

응답 헤더:

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no`
- `X-Contract-Version: qa-v1.1`

토큰 단위 `token` 이벤트는 현재 계약에 포함하지 않는다. 생성 서비스가
청크 스트림을 제공하도록 확장된 뒤 하위 호환 이벤트로 추가한다.

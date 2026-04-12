# Week 6 BE3 인터페이스 문서

문서 버전: v1.0-week6-draft  
작성일: 2026-04-10  
책임: BE3  
협업: BE1, BE2, FE

---

## 1) 책임 범위

Week 6에서 BE3는 topic-aware generation과 응답 정규화 레이어를 고정하여 `/qa`가 unified schema를 안정적으로 반환하도록 보장한다.

주요 작업:
1. `PromptFactory.build(query, context, routing_trace)` 구현
2. `normalize_response(payload)` 구현
3. `/qa` 응답 계약 완전 고정

---

## 2) 입력 계약

### 2.1 PromptFactory 입력

```json
{
  "query": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
  "context": [
    {
      "doc_id": "DOC-001",
      "snippet": "관리비 이의제기 처리 절차...",
      "score": 0.89
    }
  ],
  "routing_trace": {
    "topic_type": "welfare",
    "complexity_level": "high",
    "complexity_score": 0.81,
    "request_segments": [
      "보수 지연",
      "관리비 이의제기"
    ],
    "complexity_trace": {
      "intent_count": 3,
      "constraint_count": 4,
      "entity_diversity": 3,
      "policy_reference_count": 1,
      "cross_sentence_dependency": true
    }
  }
}
```

필수 규칙:
- routing_trace 필수
- request_segments는 `routing_trace.request_segments` 또는 `structured_output.request_segments`에 최소 1개
- route_key/strategy_id는 search 단계 값 계승
- route_key/strategy_id 형식 불일치 시 `ROUTING_STRATEGY_INCONSISTENT` 반환

---

## 3) 출력 계약 (`/qa` 성공 응답)

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
      "action_items": ["보수 일정 회신", "관리비 산정 근거 안내"],
      "request_segments": ["보수 지연", "관리비 이의제기"]
    },
    "answer": "문의하신 보수 지연 및 관리비 관련 사항에 대해...",
    "citations": [
      {
        "doc_id": "DOC-001",
        "source": "civil_db",
        "quote": "관리비 이의제기 처리 절차..."
      }
    ],
    "limitations": ["현장 점검 전 최종 확정 불가"],
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

필수 키:
- `routing_trace`
- `structured_output`
- `answer`
- `citations`
- `limitations`
- `latency_ms`
- `quality_signals`

---

## 4) normalize_response 계약

`normalize_response(payload)`가 보장해야 할 사항:
1. 누락 필드 기본값 주입
2. citations를 `doc_id/source/quote` 구조로 변환
3. limitations를 문자열 배열로 강제
4. structured_output 최소 구조 보장

기본값 예시:
- `structured_output.summary = ""`
- `structured_output.action_items = []`
- `structured_output.request_segments = []`
- `citations = []`
- `limitations = []`

---

## 5) 에러/검증 계약

Week6 BE3 에러 코드:
- `VALIDATION_ERROR` (400)
- `PROMPT_BUILD_ERROR` (500)
- `NORMALIZE_RESPONSE_ERROR` (500)
- `ROUTING_STRATEGY_INCONSISTENT` (400)

검증 보충:
- 요청 본문 스키마 파싱 실패(예: 필수 필드 타입 오류)는 FastAPI 검증 경로에서 `VALIDATION_ERROR`(422)로 응답될 수 있음

실패 응답 포맷:

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

---

## 6) 핸드오프

FE로 전달:
- 통합 응답 샘플(단일/복합/빈검색 케이스)
- fields fallback 동작 표

BE1/BE2로 전달:
- generation 단계에서 감지된 route_key 불일치 로그
- request_segments 품질 피드백

완료 체크:
- topic/multi 입력 모두에서 unified schema 반환
- 필수 필드 누락 0건

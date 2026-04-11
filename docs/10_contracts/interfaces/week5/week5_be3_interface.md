# Week 5 BE3 인터페이스 문서

문서 버전: v1.0-week5-draft  
작성일: 2026-04-10  
책임: BE3  
협업: FE, BE1, BE2

---

## 1) 책임 범위

Week 5에서 BE3는 `/search` 응답에 routing 필드를 통합하고, `/qa` 요청의 `routing_hint`를 필수 검증하는 API 경계 계약을 고정한다.

주요 작업:
1. `/search` 응답 필드 확장
2. `/qa` 요청 검증 강화
3. `/qa` 응답 골격(Week6 통합 전 단계) 제공

---

## 2) `/search` API 출력 계약

### 2.1 성공 응답 필수 키
- `success`, `request_id`, `timestamp`, `data`
- `data.strategy_id`
- `data.route_key`
- `data.routing_hint`
- `data.routing_trace`
- `data.retrieved_docs[]`

### 2.2 최소 응답 예시

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
    "retrieved_docs": []
  }
}
```

---

## 3) `/qa` API 입력 계약

### 3.1 필수 입력
- `complaint_id`
- `query`
- `routing_hint`

### 3.2 routing_hint 검증 규칙
- `routing_hint.strategy_id` required
- `routing_hint.route_key` required
- `routing_hint.top_k`, `snippet_max_chars`, `chunk_policy` required

누락 시 에러:
- `VALIDATION_ERROR`
- 메시지 예시: `routing_hint is required`

---

## 4) `/qa` API 출력 계약 (Week5 골격)

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
      "complexity_trace": {}
    },
    "structured_output": {
      "summary": "",
      "action_items": [],
      "request_segments": []
    },
    "answer": "",
    "citations": [],
    "limitations": [],
    "latency_ms": {
      "analyzer": 0,
      "router": 0,
      "retrieval": 0,
      "generation": 0
    },
    "quality_signals": {
      "citation_coverage": 0.0,
      "hallucination_flag": false,
      "segment_coverage": 0.0
    }
  }
}
```

---

## 5) 파이프라인 일관성 규칙

- `/search.data.strategy_id == /qa.data.strategy_id`
- `/search.data.route_key == /qa.data.route_key`
- `routing_trace.complexity_*`는 검색/생성 단계에서 동일 값 유지

---

## 6) 에러 계약

Week5 BE3 에러 코드:
- `VALIDATION_ERROR` (400)
- `BAD_REQUEST` (400)
- `INDEX_NOT_READY` (503)
- `INTERNAL_SERVER_ERROR` (500)

공통 실패 포맷:

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

## 7) 핸드오프

FE로 전달:
- `/search`, `/qa` 샘플 payload 10건
- 필드 누락 에러 재현 시나리오

BE1/BE2로 전달:
- API 경계에서 검증 실패한 입력 샘플
- 전략 불일치 사례 로그

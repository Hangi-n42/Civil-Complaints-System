# Week 7 BE3 인터페이스 문서

문서 버전: v1.0-week7-draft  
작성일: 2026-05-01  
책임: BE3  
협업: FE, BE1, BE2

---

## 1) 책임 범위

Week 7에서 BE3는 답변 초안/근거/제약사항을 FE가 편집 가능한 구조로 반환하는 unified schema를 고정한다.

주요 작업:
1. editable draft schema 고정
2. citation/limitations 표시 계약 고정
3. normalize_response 기반 최종 응답 정규화

---

## 2) 입력 계약

### 2.1 Draft Generation Input
- `complaint_id`
- `query`
- `context`
- `routing_trace`
- `routing_hint`
- `request_segments`

### 2.2 Context Payload
- similar complaint items
- selected complaint summary
- retrieval trace

---

## 3) 출력 계약

### 3.1 DraftAnswerPayload

```json
{
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
```

필수 필드:
- `routing_trace`
- `structured_output`
- `answer`
- `citations`
- `limitations`
- `latency_ms`
- `quality_signals`

---

## 4) 편집 가능성 계약

### 4.1 editable fields
- `answer`
- `structured_output.summary`
- `structured_output.action_items`
- `limitations`

### 4.2 read-only fields
- `citations`
- `routing_trace`
- `route_key`
- `strategy_id`

### 4.3 normalization rules
- citations는 `doc_id/source/quote` 구조 유지
- limitations는 문자열 배열 강제
- structured_output는 최소 3개 키 유지

---

## 5) 검증/에러 계약

Week 7 BE3 에러 코드:
- `VALIDATION_ERROR`
- `PROMPT_BUILD_ERROR`
- `NORMALIZE_RESPONSE_ERROR`
- `RESPONSE_SCHEMA_MISMATCH`

실패 응답 포맷:

```json
{
  "success": false,
  "request_id": "req-20260501-0001",
  "timestamp": "2026-05-01T10:00:00+09:00",
  "error": {
    "code": "RESPONSE_SCHEMA_MISMATCH",
    "message": "citations structure invalid",
    "retryable": true,
    "details": {}
  }
}
```

---

## 6) 핸드오프

FE로 전달:
- 편집 가능한 answer/summary/action_items/limitations 샘플

BE1/BE2로 전달:
- route_key/strategy_id 불일치 사례 로그
- 패널 입력용 draft context

완료 체크:
- FE가 answer와 structured_output를 수정 가능한 형태로 수신한다
- citations와 limitations가 계약대로 유지된다

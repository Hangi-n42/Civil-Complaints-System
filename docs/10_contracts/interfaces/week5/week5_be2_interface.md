# Week 5 BE2 인터페이스 문서

문서 버전: v1.0-week5-draft  
작성일: 2026-04-10  
책임: BE2  
협업: BE1, BE3, FE

---

## 1) 책임 범위

Week 5에서 BE2는 complexity 중심 AdaptiveRouter 1차를 구현하고, 라우팅 결정 결과를 retrieval 파라미터와 함께 표준 계약으로 반환한다.

주요 작업:
1. `route(topic_type, complexity_level, complexity_score)` 구현
2. complexity별 retrieval 파라미터 고정
3. routing trace/strategy 전달 규약 확정

---

## 2) 입력 계약 (BE1 -> BE2)

```json
{
  "topic_type": "welfare",
  "complexity_level": "high",
  "complexity_score": 0.81
}
```

필수 규칙:
- `topic_type` 기본값: `general`
- `complexity_level`은 `low|medium|high`만 허용
- `complexity_score`는 0~1 범위

---

## 3) 출력 계약 (BE2 -> BE3)

### 3.1 RoutingDecision

```json
{
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
  }
}
```

### 3.2 complexity 파라미터 매핑

| complexity_level | top_k | snippet_max_chars | chunk_policy |
| --- | ---: | ---: | --- |
| low | 4 | 400 | compact |
| medium | 6 | 700 | balanced |
| high | 9 | 1100 | expanded |

---

## 4) Retrieval 결과 메타데이터 계약

`retrieved_docs[].metadata` 필수 키:
- `strategy_id`
- `topic_type`
- `complexity_level`

예시:

```json
{
  "doc_id": "DOC-001",
  "snippet": "관리비 이의제기 처리 절차...",
  "score": 0.89,
  "metadata": {
    "strategy_id": "topic_welfare_high_v1",
    "topic_type": "welfare",
    "complexity_level": "high"
  }
}
```

---

## 5) 로그/관측 계약

필수 로그 키:
- `request_id`
- `route_key`
- `strategy_id`
- `complexity_level`
- `complexity_score`
- `applied_params`
- `router_latency_ms`
- `retrieval_latency_ms`

---

## 6) 에러 계약

Week5 BE2 에러 코드:
- `ROUTE_INPUT_INVALID` (400)
- `ROUTE_KEY_BUILD_ERROR` (500)
- `RETRIEVAL_STRATEGY_NOT_FOUND` (500)

에러 응답은 공통 래퍼를 따른다.
- `success=false`
- `error.code`, `error.message`, `error.retryable`

---

## 7) 핸드오프

BE3로 전달:
- RoutingDecision 샘플(레벨별)
- strategy_id 정의 목록

FE로 전달:
- route_key별 UI 표시 문구 가이드

완료 체크:
- `/search`와 `/qa`에서 동일 strategy_id 추적 가능
- route_key 포맷 `{topic_type}/{complexity_level}` 100% 일치

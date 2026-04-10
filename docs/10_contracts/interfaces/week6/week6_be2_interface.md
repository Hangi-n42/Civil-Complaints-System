# Week 6 BE2 인터페이스 문서

문서 버전: v1.0-week6-draft  
작성일: 2026-04-10  
책임: BE2  
협업: BE1, BE3, FE

---

## 1) 책임 범위

Week 6에서 BE2는 topic_type 기반 retrieval 분기와 복합 요청(segment) 병합 규약을 고정하고, trace를 FE/BE3가 그대로 사용할 수 있게 확장한다.

주요 작업:
1. topic-aware retrieval policy 적용
2. segment 검색 병합 규칙 확정
3. retrieval trace 확장 키 고정

---

## 2) 입력 계약 (BE1 -> BE2)

```json
{
  "topic_type": "welfare",
  "complexity_level": "high",
  "complexity_score": 0.81,
  "request_segments": ["보수 지연", "관리비 이의제기"]
}
```

필수 규칙:
- `route_key = {topic_type}/{complexity_level}`
- `request_segments` 길이가 2 이상이면 segment mode 활성화

---

## 3) retrieval 정책 계약

### 3.1 topic policy 키
- `field_ops`
- `admin_policy`
- `general` (fallback)

### 3.2 전략 결정 출력

```json
{
  "strategy_id": "topic_welfare_high_v1",
  "route_key": "welfare/high",
  "topic_policy": "admin_policy",
  "routing_hint": {
    "strategy_id": "topic_welfare_high_v1",
    "route_key": "welfare/high",
    "top_k": 9,
    "snippet_max_chars": 1100,
    "chunk_policy": "expanded"
  }
}
```

---

## 4) segment 병합 계약

### 4.1 병합 처리 규칙
1. segment별 후보 검색 수행
2. `doc_id` 기준 중복 제거
3. 점수 정규화(min-max 또는 rank 기반)
4. 최종 top_k 절단

### 4.2 병합 결과 예시

```json
{
  "segment_count": 2,
  "merge_policy": "dedup_then_rank",
  "retrieved_docs": [
    {
      "doc_id": "DOC-001",
      "score": 0.91,
      "metadata": {
        "strategy_id": "topic_welfare_high_v1",
        "topic_type": "welfare",
        "complexity_level": "high"
      }
    }
  ]
}
```

---

## 5) retrieval trace 계약 (BE2 -> BE3/FE)

필수 키:
- `route_key`
- `strategy_id`
- `applied_filters`
- `segment_count`
- `merge_policy`

예시:

```json
{
  "retrieval_trace": {
    "route_key": "welfare/high",
    "strategy_id": "topic_welfare_high_v1",
    "applied_filters": {
      "topic_type": "welfare",
      "region": "seoul"
    },
    "segment_count": 2,
    "merge_policy": "dedup_then_rank"
  }
}
```

---

## 6) 성능/에러 계약

관측 키:
- `latency_ms.retrieval`
- `retrieval_doc_count`
- `segment_count`

Week6 BE2 에러 코드:
- `TOPIC_POLICY_NOT_FOUND` (500)
- `SEGMENT_RETRIEVAL_ERROR` (500)
- `RETRIEVAL_MERGE_ERROR` (500)
- `ROUTE_KEY_MISMATCH` (500)

---

## 7) 핸드오프

BE3로 전달:
- retrieval_trace 포함 `/search` 샘플
- segment 모드/단일 모드 비교 샘플

FE로 전달:
- applied_filters 표시용 키 사전

완료 체크:
- trace 필수 키 5종 항상 존재
- `/search`와 `/qa` route_key 일치율 100%

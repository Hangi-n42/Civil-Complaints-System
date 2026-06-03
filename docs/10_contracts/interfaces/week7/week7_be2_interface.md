# Week 7 BE2 인터페이스 문서

문서 버전: v1.0-week7-draft  
작성일: 2026-05-01  
책임: BE2  
협업: FE, BE1, BE3

---

## 1) 책임 범위

Week 7에서 BE2는 우측 AI 패널의 유사 민원 응답을 Workbench 표준 포맷으로 고정한다.

주요 작업:
1. 유사 민원 패널 응답 형식 고정
2. score 기반 정렬/중복 제거 규칙 적용
3. retrieval trace 최소 세트 유지

---

## 2) 입력 계약

### 2.1 Query Context
- `complaint_id`
- `query`
- `route_key`
- `strategy_id`
- `routing_trace`

### 2.2 Retrieval Policy
- `top_k`
- `snippet_max_chars`
- `chunk_policy`

---

## 3) 출력 계약

### 3.1 SimilarComplaintPanelItem

```json
{
  "doc_id": "DOC-001",
  "title": "유사 민원 처리 사례",
  "snippet": "관리비 이의제기 처리 절차...",
  "score": 0.89,
  "source": "civil_db",
  "metadata": {
    "strategy_id": "topic_welfare_high_v1",
    "topic_type": "welfare",
    "complexity_level": "high"
  }
}
```

필수 필드:
- `doc_id`
- `title`
- `snippet`
- `score`
- `source`
- `metadata.strategy_id`
- `metadata.topic_type`
- `metadata.complexity_level`

---

## 4) 패널 응답 계약

```json
{
  "items": [
    {
      "doc_id": "DOC-001",
      "title": "유사 민원 처리 사례",
      "snippet": "관리비 이의제기 처리 절차...",
      "score": 0.89,
      "source": "civil_db",
      "metadata": {
        "strategy_id": "topic_welfare_high_v1",
        "topic_type": "welfare",
        "complexity_level": "high"
      }
    }
  ],
  "result_count": 1,
  "retrieval_latency_ms": 132,
  "route_key": "welfare/high",
  "strategy_id": "topic_welfare_high_v1"
}
```

---

## 5) 정렬/중복 제거 규칙

- score 내림차순 정렬
- 동일 `doc_id` 중복 제거
- 결과가 `top_k`를 초과하지 않도록 절단
- 패널 결과와 search 결과 간 score 기준의 일관성 유지

---

## 6) 로그/에러 계약

필수 로그 키:
- `complaint_id`
- `route_key`
- `strategy_id`
- `retrieval_latency_ms`
- `result_count`

Week 7 BE2 에러 코드:
- `SIMILAR_PANEL_EMPTY`
- `RETRIEVAL_CONTEXT_INVALID`
- `ROUTE_KEY_MISMATCH`
- `PANEL_RESPONSE_MISMATCH`

---

## 7) 핸드오프

FE로 전달:
- 패널 카드 렌더용 필드 세트

BE1로 전달:
- 선택 민원 기준 panel query key

BE3로 전달:
- 답변 초안 생성에 사용할 유사 민원 top-k 샘플

완료 체크:
- 패널 응답이 FE 변환 없이 렌더된다
- duplicate doc가 노출되지 않는다

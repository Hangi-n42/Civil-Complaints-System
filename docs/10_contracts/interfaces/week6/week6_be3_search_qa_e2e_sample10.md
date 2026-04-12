# Week 6 BE3 Search-QA 연계 샘플 10건

문서 버전: v1.0-week6-sample10  
작성일: 2026-04-11  
기준 테스트: app/tests/integration/test_week6_search_to_qa_e2e_sample10.py

---

## 1) 구성 요약

- 단일 이슈(single): 4건
- 복합 이슈(multi): 4건
- 빈검색(empty): 2건

| No | complaint_id | 유형 | query 요약 | 기대 결과 |
|---|---|---|---|---|
| 1 | CMP-2026-1001 | single | 기초생활 수급 절차 | search 성공 + qa 성공 |
| 2 | CMP-2026-1002 | multi | 임대주택 보수 + 관리비 이의 | search 성공 + qa 성공 |
| 3 | CMP-2026-1003 | single | 도로 파손 긴급 보수 | search 성공 + qa 성공 |
| 4 | CMP-2026-1004 | multi | 신호 고장 + 불법주정차 | search 성공 + qa 성공 |
| 5 | CMP-2026-1005 | single | 생활 소음 기준 | search 성공 + qa 성공 |
| 6 | CMP-2026-1006 | multi | 악취 + 폐기물 적치 | search 성공 + qa 성공 |
| 7 | CMP-2026-1007 | single | 공사장 안전 펜스 | search 성공 + qa 성공 |
| 8 | CMP-2026-1008 | multi | 시설 보수 지연 + 안내 미흡 | search 성공 + qa 성공 |
| 9 | CMP-2026-1011 | empty | 의미 없는 질의(빈검색 유도) | search 0건 + qa 실패 |
| 10 | CMP-2026-1012 | empty | 노이즈 질의(빈검색 유도) | search 0건 + qa 실패 |

---

## 2) 공통 호출 순서

1. POST /api/v1/search
2. search.data.routing_hint, search.data.retrieved_docs를 사용해 POST /api/v1/qa

---

## 3) 샘플 payload

### Case 1 (single)

/search request
```json
{
  "complaint_id": "CMP-2026-1001",
  "query": "기초생활 수급 신청 절차를 안내해주세요",
  "top_k": 3
}
```

/search response 핵심
```json
{
  "success": true,
  "data": {
    "strategy_id": "topic_welfare_medium_v1",
    "route_key": "welfare/medium",
    "routing_hint": {
      "strategy_id": "topic_welfare_medium_v1",
      "route_key": "welfare/medium",
      "top_k": 3,
      "snippet_max_chars": 900,
      "chunk_policy": "balanced"
    },
    "retrieved_docs": [{"doc_id": "DOC-1201", "chunk_id": "CASE-1201__chunk-0", "case_id": "CASE-1201", "snippet": "..."}]
  }
}
```

/qa request
```json
{
  "complaint_id": "CMP-2026-1001",
  "query": "기초생활 수급 신청 절차를 안내해주세요",
  "routing_hint": {
    "strategy_id": "topic_welfare_medium_v1",
    "route_key": "welfare/medium",
    "top_k": 3,
    "snippet_max_chars": 900,
    "chunk_policy": "balanced"
  },
  "use_search_results": true,
  "search_results": [{"doc_id": "DOC-1201", "chunk_id": "CASE-1201__chunk-0", "case_id": "CASE-1201", "snippet": "...", "score": 0.9}]
}
```

/qa response 핵심
```json
{
  "success": true,
  "data": {
    "complaint_id": "CMP-2026-1001",
    "strategy_id": "topic_welfare_medium_v1",
    "route_key": "welfare/medium",
    "routing_trace": {"topic_type": "welfare", "complexity_level": "medium"},
    "structured_output": {"summary": "", "action_items": [], "request_segments": ["기초생활 수급 신청 절차를 안내해주세요"]},
    "answer": "...",
    "citations": [{"doc_id": "DOC-1201", "source": "retrieval", "quote": "..."}],
    "limitations": ["..."],
    "latency_ms": {"analyzer": 0, "router": 0, "retrieval": 0, "generation": 0},
    "quality_signals": {"citation_coverage": 1.0, "hallucination_flag": false, "segment_coverage": 1.0}
  }
}
```

### Case 2 (multi)

query: 임대주택 보수 지연 및 관리비 이의제기 관련 민원

핵심 기대:
```json
{
  "strategy_id": "topic_welfare_high_v1",
  "route_key": "welfare/high",
  "structured_output": {
    "request_segments": ["임대주택 보수 지연", "관리비 이의제기 관련 민원"]
  }
}
```

### Case 3 (single)

query: 도로 파손 구간 긴급 보수 요청

핵심 기대:
```json
{
  "strategy_id": "topic_traffic_medium_v1",
  "route_key": "traffic/medium",
  "routing_trace": {"topic_type": "traffic"}
}
```

### Case 4 (multi)

query: 교통 신호 고장, 불법주정차 단속 요청

핵심 기대:
```json
{
  "strategy_id": "topic_traffic_high_v1",
  "route_key": "traffic/high",
  "structured_output": {
    "request_segments": ["교통 신호 고장", "불법주정차 단속 요청"]
  }
}
```

### Case 5 (single)

query: 생활 소음 민원 처리 기준을 알려주세요

핵심 기대:
```json
{
  "strategy_id": "topic_environment_medium_v1",
  "route_key": "environment/medium"
}
```

### Case 6 (multi)

query: 악취 그리고 폐기물 적치 문제를 함께 신고합니다

핵심 기대:
```json
{
  "strategy_id": "topic_environment_high_v1",
  "route_key": "environment/high",
  "structured_output": {
    "request_segments": ["악취", "폐기물 적치 문제를 함께 신고합니다"]
  }
}
```

### Case 7 (single)

query: 공사장 안전 펜스 설치 요청

핵심 기대:
```json
{
  "strategy_id": "topic_construction_medium_v1",
  "route_key": "construction/medium"
}
```

### Case 8 (multi)

query: 시설 보수 지연; 현장 안내 미흡 개선 요청

핵심 기대:
```json
{
  "strategy_id": "topic_construction_high_v1",
  "route_key": "construction/high",
  "structured_output": {
    "request_segments": ["시설 보수 지연", "현장 안내 미흡 개선 요청"]
  }
}
```

### Case 9 (empty)

/search request
```json
{
  "complaint_id": "CMP-2026-1011",
  "query": "zxqv 991122 불명확 질의",
  "top_k": 3
}
```

/search response 핵심 (0건)
```json
{
  "success": true,
  "data": {
    "strategy_id": "topic_general_low_v1",
    "route_key": "general/low",
    "routing_hint": {"strategy_id": "topic_general_low_v1", "route_key": "general/low", "top_k": 3, "snippet_max_chars": 700, "chunk_policy": "compact"},
    "retrieved_docs": []
  }
}
```

/qa request
```json
{
  "complaint_id": "CMP-2026-1011",
  "query": "zxqv 991122 불명확 질의",
  "routing_hint": {"strategy_id": "topic_general_low_v1", "route_key": "general/low", "top_k": 3, "snippet_max_chars": 700, "chunk_policy": "compact"},
  "use_search_results": true,
  "search_results": []
}
```

/qa response 핵심 (실패)
```json
{
  "success": false,
  "error": {
    "code": "BAD_REQUEST",
    "message": "QA 컨텍스트를 구성할 수 없습니다. search_results 형식을 확인해주세요.",
    "retryable": false
  }
}
```

### Case 10 (empty)

query: @@@ ### ??? 무의미 입력

핵심 기대:
```json
{
  "search.data.retrieved_docs": [],
  "qa.success": false,
  "qa.error.code": "BAD_REQUEST"
}
```

---

## 4) 비고

- Case 1~8은 실제 자동화 테스트 케이스(샘플 fixture 10건 중 정상 검색 시나리오) 기준으로 검증 가능하다.
- Case 9~10은 FE 빈검색 대응 검증을 위한 운영 샘플이다.
- 계약상 FE가 필수로 참조해야 하는 키: strategy_id, route_key, routing_trace, structured_output, citations, limitations, latency_ms, quality_signals.

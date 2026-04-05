# Week 4 BE2 인터페이스 문서

문서 버전: v1.0-week4-draft  
작성일: 2026-04-05  
책임: BE2  
협업: BE1, BE3, FE

---

## 1) 책임 범위

Week 4에서 BE2는 검색 결과를 생성 입력으로 연결하는 **retrieval->QA 컨텍스트 계약**을 고정한다.

주요 작업:
1. SearchResult -> retrieval_context 매핑 규격 확정
2. 필터/Top-K 조합 성능 측정
3. 검색 기준선 리포트 배포

---

## 2) 입력 계약

### 2.1 SearchRequest (상속)
- 참조: `../week3/week3_common_interface.md#3) SearchRequest 계약`

### 2.2 품질 제약
- 필터 미지정: 정상 검색
- 필터 유효 + 매칭 없음: `200 + results=[]`
- 필터 오류: `400 FILTER_INVALID`

---

## 3) 출력 계약

### 3.1 SearchResult (상속)
- 참조: `../week3/week3_common_interface.md#4) SearchResult 계약`

### 3.2 retrieval_context 매핑 출력

```json
{
  "request_id": "SRCH-2026-000001",
  "retrieval_context": [
    {
      "chunk_id": "CHUNK-0001",
      "case_id": "CASE-2026-000101",
      "content": "야간 포트홀 민원이 증가...",
      "score": 0.87,
      "metadata": {
        "region": "서울시 강남구",
        "category": "도로안전",
        "created_at": "2026-03-05T10:15:00+09:00"
      }
    }
  ],
  "elapsed_ms": 342
}
```

필수 필드:
- `chunk_id`, `case_id`, `content`, `score`, `metadata`

---

## 4) 성능 기준선 계약

```json
{
  "retrieval_benchmark": {
    "scenario": "week4_baseline",
    "top_k_set": [3, 5, 10],
    "filters": ["none", "region", "category", "region+category"],
    "metrics": {
      "recall_at_5": 0.78,
      "latency_avg_ms": 420,
      "latency_p95_ms": 760
    }
  }
}
```

---

## 5) 핸드오프

BE3로 전달:
- retrieval_context 표준 샘플
- chunk_id/case_id trace 로그

FE로 전달:
- 검색 결과 카드 표시에 필요한 필드 고정 목록

BE1로 전달:
- 검색 기준선 측정값(Recall/Latency)

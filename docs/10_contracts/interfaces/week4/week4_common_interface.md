# Week 4 공통 인터페이스 규약

문서 버전: v1.0-week4-draft  
작성일: 2026-04-05  
적용 파트: FE, BE1, BE2, BE3  
상속: Week 3 공통 규약 (`../week3/week3_common_interface.md`)

---

## 1) Week 4 추가 규칙

### 1.1 단일 RAG baseline 공통 원칙
- `QARequest.request_id`는 `SearchResult.request_id`와 연결 가능해야 한다.
- `QAResponse.citations[]`의 `chunk_id`와 `case_id`는 검색 결과 trace와 일치해야 한다.
- 파싱 실패는 재시도 후에도 실패 시 표준 에러(`QA_PARSE_ERROR`)로 반환한다.
- `limitations`는 빈 문자열 허용 금지(근거 부족/범위 제한 문구 필수).

### 1.2 시각 고정
- `timestamp`, `created_at`는 ISO-8601 KST(+09:00) 형식 강제.

---

## 2) QARequest 계약

```json
{
  "request_id": "QA-2026-000001",
  "query": "최근 3개월 도로 안전 민원 핵심 요약",
  "top_k": 5,
  "retrieval_context": [
    {
      "chunk_id": "CHUNK-0001",
      "case_id": "CASE-2026-000101",
      "content": "야간 포트홀 민원이 증가...",
      "metadata": {
        "region": "서울시 강남구",
        "category": "도로안전",
        "created_at": "2026-03-05T10:15:00+09:00"
      }
    }
  ],
  "generation_config": {
    "temperature": 0.2,
    "max_tokens": 768,
    "model": "aihub_baseline"
  }
}
```

필수 필드:
- `request_id` (string)
- `query` (string)
- `top_k` (int, 1~20)
- `retrieval_context` (array)

선택 필드:
- `generation_config` (object)

---

## 3) QAResponse 계약

```json
{
  "success": true,
  "request_id": "QA-2026-000001",
  "timestamp": "2026-04-05T13:10:00+09:00",
  "data": {
    "answer": "최근 3개월 도로 안전 민원은 포트홀과 야간 조명 이슈가 집중되었습니다.",
    "citations": [
      {
        "chunk_id": "CHUNK-0001",
        "case_id": "CASE-2026-000101",
        "snippet": "야간 포트홀 민원이 증가",
        "confidence": 0.89
      }
    ],
    "confidence": "medium",
    "limitations": "최근 3개월 데이터 기준이며 장기 추세 해석에는 한계가 있습니다.",
    "latency_ms": 1850
  }
}
```

필수 필드:
- `success` (bool)
- `request_id` (string)
- `timestamp` (ISO-8601 KST)
- `data.answer` (string)
- `data.citations[]` (array)
- `data.confidence` (`low|medium|high`)
- `data.limitations` (string)
- `data.latency_ms` (int)

---

## 4) Citation 계약

```json
{
  "chunk_id": "CHUNK-0001",
  "case_id": "CASE-2026-000101",
  "snippet": "야간 포트홀 민원이 증가",
  "confidence": 0.89
}
```

필수 규칙:
- `chunk_id` unique
- `snippet` 최대 200자
- `confidence` 0~1

---

## 5) GateAReport 계약

```json
{
  "report_id": "GATEA-2026-W4-001",
  "generated_at": "2026-04-05T18:00:00+09:00",
  "metrics": {
    "recall_at_5": 0.78,
    "four_element_f1": 0.81,
    "citation_alignment": 0.84,
    "latency_avg_ms": 1920
  },
  "notes": "single RAG baseline 기준선 확정"
}
```

필수 필드:
- `metrics.recall_at_5`
- `metrics.four_element_f1`
- `metrics.citation_alignment`
- `metrics.latency_avg_ms`

---

## 6) 에러 응답 계약

```json
{
  "success": false,
  "request_id": "QA-2026-000001",
  "timestamp": "2026-04-05T13:10:00+09:00",
  "error": {
    "code": "QA_PARSE_ERROR",
    "message": "JSON 파싱 실패",
    "retryable": true
  }
}
```

Week 4 특화 에러 코드:
- `QA_PARSE_ERROR` (500, retryable=true)
- `CITATION_MISMATCH` (500, retryable=true)
- `INVALID_QA_REQUEST` (400, retryable=false)
- `GENERATION_TIMEOUT` (504, retryable=true)

# Week 4 BE3 인터페이스 문서

문서 버전: v1.0-week4-draft  
작성일: 2026-04-05  
책임: BE3  
협업: BE1, BE2, FE

---

## 1) 책임 범위

Week 4에서 BE3는 `/qa` 생성의 **파싱 안정화 + citation 정합성**을 고정한다.

주요 작업:
1. `POST /qa` 응답 계약 안정화
2. JSON 파싱 재시도 정책 고정
3. citation 정합성 검증 로직 운영

---

## 2) API 계약

### 2.1 POST /qa 요청

```json
{
  "request_id": "QA-2026-000001",
  "query": "최근 3개월 도로 안전 민원 요약",
  "top_k": 5,
  "retrieval_context": [...],
  "generation_config": {
    "model": "aihub_baseline",
    "temperature": 0.2,
    "max_tokens": 768
  }
}
```

### 2.2 POST /qa 성공 응답

```json
{
  "success": true,
  "request_id": "QA-2026-000001",
  "timestamp": "2026-04-05T13:10:00+09:00",
  "data": {
    "answer": "...",
    "citations": [
      {
        "chunk_id": "CHUNK-0001",
        "case_id": "CASE-2026-000101",
        "snippet": "...",
        "confidence": 0.89
      }
    ],
    "confidence": "medium",
    "limitations": "...",
    "latency_ms": 1850
  }
}
```

### 2.3 POST /qa 실패 응답

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

---

## 3) 파싱/재시도 정책

재시도 순서:
1. 동일 프롬프트 1회 재시도
2. compact prompt fallback
3. 실패 시 `QA_PARSE_ERROR` 반환

필수 기록:
- `request_id`
- `retry_count`
- `failure_reason`
- `model`

---

## 4) citation 정합성 규칙

- 모든 citation은 retrieval_context에서 생성되어야 함
- `chunk_id`/`case_id` 미일치 시 `CITATION_MISMATCH`
- snippet은 원문 200자 이하

검증 출력 예시:

```json
{
  "citation_validation": {
    "request_id": "QA-2026-000001",
    "is_valid": true,
    "mismatch_count": 0
  }
}
```

---

## 5) 로그 계약

로그 필드:
- `request_id`
- `elapsed_ms`
- `model`
- `retry_count`
- `error_code` (실패 시)

예시:

```text
2026-04-05T13:10:00+09:00 [QA-2026-000001] INFO qa.generate elapsed=1850 model=aihub_baseline retry=1
```

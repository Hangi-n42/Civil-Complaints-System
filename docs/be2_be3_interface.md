# BE2-BE3 인터페이스 계약 (Week 1)

문서 버전: v1.0  
작성일: 2026-03-17  
담당: BE2, BE3

## 1. 목적

QA 응답 파싱 안정성과 citation 정합성을 위해 `/qa` 응답 계약을 확정한다.

## 2. `/qa` 최소 응답 계약

```json
{
  "status": "ok",
  "request_id": "REQ-20260317-AB12CD34",
  "timestamp": "2026-03-17T18:30:00+09:00",
  "answer": "주요 이슈는 야간 조명 불량과 보행 위험입니다. [[CITE:1]]",
  "citations": [
    {
      "ref_id": 1,
      "doc_id": "DOC-25-088",
      "chunk_id": "CASE-2026-000123__chunk-0",
      "case_id": "CASE-2026-000123",
      "snippet": "...가로등이 깜빡거리고 일부 구간이 소등됩니다...",
      "relevance_score": 0.88,
      "source": "retrieval"
    }
  ],
  "confidence": "medium",
  "limitations": "검색 범위 내 데이터에 기반한 답변입니다.",
  "meta": {
    "processing_time": 2.5,
    "model": "qwen2.5:7b-instruct",
    "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다."
  },
  "qa_validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

## 3. 파싱 안정화 규칙

1. LLM 응답은 JSON 형식 강제 프롬프트 사용
2. 파싱 실패 시 최대 3회 재시도
3. 최종 실패 시 표준 에러 응답 반환

에러 예시:

```json
{
  "status": "error",
  "error_code": "JSON_PARSE_ERROR",
  "message": "모델 응답을 JSON으로 파싱하지 못했습니다.",
  "retryable": true,
  "request_id": "REQ-20260317-34EF56AA",
  "details": {
    "retry_count": 3
  }
}
```

## 4. citation 정합성 규칙

필수 필드:
- `ref_id`
- `doc_id`
- `chunk_id`
- `case_id`
- `snippet`

권장 필드:
- `relevance_score`
- `start`, `end`
- `source`

검증 포인트:
- `answer` 내 `[[CITE:n]]` 토큰과 `citations.ref_id`가 1:1 매핑
- `chunk_id`가 실제 검색 결과 목록에 존재해야 함
- `case_id`가 해당 `chunk_id`와 일치해야 함

## 5. 합의 체크포인트

- [ ] BE3가 위 JSON 계약으로 파서 구현 가능
- [ ] `confidence` 타입(`low`/`medium`/`high`) 합의
- [ ] `limitations` 항상 포함 합의
- [ ] 파싱 실패 에러코드(`JSON_PARSE_ERROR`) 합의
- [ ] `meta` 필수 3필드(processing_time/model/validation_warning) 합의

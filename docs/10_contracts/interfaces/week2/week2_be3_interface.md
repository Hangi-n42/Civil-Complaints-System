# Week 2 BE3 인터페이스 문서

문서 버전: v1.0-week2  
작성일: 2026-03-19  
책임: BE3  
협업: BE1, BE2, FE

## 1) 책임 범위

- `/ingest`, `/structure` 응답 포맷 고정
- 공통 에러 코드/검증 객체 일관성 유지
- JSON 파싱/검증 유틸 계약 통일

## 2) API 응답 래퍼 규약

성공:
```json
{
  "success": true,
  "request_id": "REQ-20260319-AB12CD34",
  "timestamp": "2026-03-19T10:00:00+09:00",
  "data": {}
}
```

실패:
```json
{
  "success": false,
  "request_id": "REQ-20260319-EF56GH78",
  "timestamp": "2026-03-19T10:00:01+09:00",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 본문 형식이 올바르지 않습니다.",
    "retryable": false,
    "details": {}
  }
}
```

## 3) `/ingest` 데이터 계약

`data` 객체 최소 필드:
- `ingested_count` (int)
- `skipped_count` (int)
- `records` (array)

`records[]` 최소 필드:
- `case_id`
- `status` (`accepted` | `skipped` | `rejected`)
- `normalized_text`

## 4) `/structure` 데이터 계약

`data` 객체 최소 필드:
- `structured_count` (int)
- `results` (`StructuredCivilCase[]`)

## 5) 변수명 충돌 방지 규칙

- 에러는 항상 `error.code`, `error.message`, `error.retryable` 3필드 유지
- 검증은 항상 `validation.is_valid` 구조 유지 (`is_valid`를 최상위로 올리지 않음)
- 처리시간 필드는 `processing_time`만 사용 (`latency_ms`, `elapsed` 혼용 금지)
- 응답 ID는 `request_id` 고정 (`trace_id` 혼용 금지)

## 6) BE3 완료 체크

- [ ] `/ingest`, `/structure` 모두 `success` 래퍼 일관성 확인
- [ ] 에러 코드 표준(`VALIDATION_ERROR`, `BAD_REQUEST`, `PROCESSING_ERROR`) 준수
- [ ] `request_id`, `timestamp` 누락률 0%

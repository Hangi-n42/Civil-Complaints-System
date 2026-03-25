# Week 2 BE3 인터페이스 문서

문서 버전: v1.3-week2-final  
작성일: 2026-03-19  
최신화: 2026-03-25 (422 VALIDATION_ERROR 래퍼 통일 반영)  
책임: BE3  
협업: BE1, BE2, FE

## 1) 책임 범위

- `/search`, `/qa` 응답 포맷 고정 (Week2 구현 완료)
- `/ingest`, `/structure` 응답 포맷 계약 정의 (Week 3 예정)
- 공통 에러 코드/검증 객체 일관성 유지
- JSON 파싱/검증 유틸 계약 통일

## 1.1) 현재 구현 상태 (Week 2)

**구현 완료:**
- ✅ `/api/v1/search` (POST): 검색 쿼리 기반 민원 검색
- ✅ `/api/v1/qa` (POST): 근거 기반 질의응답

**미구현 (Week 3 예정):**
- ❌ `/api/v1/ingest` (POST): 민원 데이터 수집/정제
- ❌ `/api/v1/structure` (POST): 민원 데이터 구조화

**BE3 역할 (구현된 엔드포인트 기준):**
- `/search`, `/qa` 응답 래퍼 계약 준수
- 공통 에러 처리 및 요청 추적

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

### 2.1) 검증 오류(HTTP 422) 래핑 규칙

- FastAPI/Pydantic 검증 실패(`RequestValidationError`)도 위 실패 래퍼 형식으로 반환한다.
- 오류 코드는 `VALIDATION_ERROR`로 통일한다.
- `error.details`에 최소 `path`, `errors`를 포함한다.

예시:
```json
{
  "success": false,
  "request_id": "REQ-20260325-AB12CD34",
  "timestamp": "2026-03-25T11:00:00+09:00",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 본문 형식이 올바르지 않습니다.",
    "retryable": false,
    "details": {
      "path": "/api/v1/search",
      "errors": []
    }
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

- [x] 구현된 `/search`, `/qa` 엔드포인트의 `success` 래퍼 일관성 확인
- [x] 구현된 `/search`, `/qa` 엔드포인트 에러 코드 표준 준수
- [x] 구현된 `/search`, `/qa` 엔드포인트 `request_id`, `timestamp` 누락률 0%
- [x] FastAPI 기본 422 검증 오류를 `VALIDATION_ERROR` 래퍼로 통일
- [ ] `/ingest`, `/structure` 구현 이후 동일 체크 재검증 예정

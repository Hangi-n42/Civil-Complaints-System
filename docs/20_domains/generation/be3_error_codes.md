# BE3 오류 코드 초안

문서 버전: v0.1  
작성일: 2026-03-13  
작성자: BE3 김현석  
기준 문서: [be3_validation_rules.md](be3_validation_rules.md), [schema_contract.md](../../10_contracts/schema/schema_contract.md), [api_spec.md](../../10_contracts/api/api_spec.md), [be3_manual.md](../../30_manuals/be3_manual.md)

## 1. 문서 목적

이 문서는 BE3가 사용할 validation/파싱/citation/성능/OOM 오류 코드를 고정하기 위한 초안이다.
목표는 다음과 같다.

- FE, BE1, BE2가 동일한 에러 의미로 소통할 수 있게 한다.
- API 응답과 로그에서 코드 기반으로 원인 추적이 가능하게 한다.
- JSON 파싱 실패 및 citation 정합성 실패를 분리해 대응 흐름을 명확히 한다.

## 2. 코드 설계 원칙

- 코드 형식: `도메인_세부원인` (영문 대문자 + `_`)
- 도메인 접두사:
  - `REQ` 요청 입력
  - `VAL` 스키마/검증
  - `PARSE` JSON 파싱
  - `CITE` citation
  - `MODEL` 모델/추론
  - `PERF` 성능
  - `OOM` 메모리
  - `SYS` 시스템
- 각 오류는 `severity`, `retryable`, `http_status`를 함께 가진다.
- 동일 오류라도 endpoint별 상세 message는 다를 수 있으나 `code`는 고정한다.

## 3. 공통 에러 응답 권장 포맷

```json
{
  "success": false,
  "error": {
    "code": "VAL_REQUIRED_FIELD_MISSING",
    "message": "필수 필드가 누락되었습니다.",
    "details": {
      "field": "request.text",
      "value": null,
      "expected": "non-empty string"
    },
    "severity": "error",
    "retryable": false
  }
}
```

## 4. 오류 코드 목록

### 4.1 Request/입력 (`REQ_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `REQ_BAD_REQUEST` | 요청 형식 오류 | 400 | false | JSON 바디 누락, 잘못된 형식 |
| `REQ_INVALID_TYPE` | 필드 타입 오류 | 422 | false | 기대 타입과 다른 값 |
| `REQ_REQUIRED_FIELD_MISSING` | 필수 요청 필드 누락 | 422 | false | case_id, text 등 필수 값 없음 |
| `REQ_INVALID_DATETIME` | datetime 형식 오류 | 422 | false | created_at 파싱 실패 |
| `REQ_EMPTY_TEXT` | 텍스트 비어 있음 | 422 | false | 공백 문자열 포함 |

### 4.2 Validation/스키마 (`VAL_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `VAL_REQUIRED_FIELD_MISSING` | 구조화 필수 필드 누락 | 422 | false | case_id, observation 등 |
| `VAL_INVALID_TYPE` | 필드 타입 위반 | 422 | false | object/array/string 타입 불일치 |
| `VAL_EMPTY_TEXT` | 추출 텍스트 비어 있음 | 422 | false | 4요소 text가 비어 있음 |
| `VAL_INVALID_CONFIDENCE_RANGE` | confidence 범위 위반 | 422 | false | 0~1 범위를 벗어남 |
| `VAL_INVALID_EVIDENCE_SPAN_FORMAT` | evidence_span 형식 오류 | 422 | false | 길이 2 배열 아님 |
| `VAL_INVALID_EVIDENCE_SPAN_ORDER` | evidence_span 순서 오류 | 422 | false | start > end |
| `VAL_INVALID_ENTITY_LABEL` | 허용되지 않은 엔티티 라벨 | 422 | false | LOCATION 등 허용 목록 위반 |
| `VAL_INVALID_VALIDATION_OBJECT` | validation 객체 자체 오류 | 422 | false | is_valid, errors 누락 |
| `VAL_WARNING_LOW_CONFIDENCE` | 신뢰도 낮음 경고 | 200 | false | 품질 경고, 처리 계속 |
| `VAL_WARNING_EMPTY_ENTITIES` | 엔티티 없음 경고 | 200 | false | 품질 경고, 처리 계속 |

### 4.3 JSON 파싱 (`PARSE_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `PARSE_JSON_DECODE_ERROR` | JSON 디코딩 실패 | 500 | true | 문법 오류, 괄호 불일치 |
| `PARSE_JSON_BLOCK_EXTRACTION_FAILED` | 코드블록 추출 실패 | 500 | true | ```json 블록 파싱 실패 |
| `PARSE_EMPTY_MODEL_RESPONSE` | 모델 응답 비어 있음 | 502 | true | 응답 공백/None |
| `PARSE_SCHEMA_MISMATCH` | JSON은 파싱되나 계약 불일치 | 500 | true | 필수 필드/타입 미충족 |
| `PARSE_RETRY_EXHAUSTED` | 재시도 한도 초과 | 500 | false | max retry 후 실패 |

호환성 규칙:

- `JSON_PARSE_ERROR`는 레거시 그룹 코드이며 신규 표준 코드로는 사용하지 않는다.
- 외부 연동이 `JSON_PARSE_ERROR`만 처리하는 경우, `PARSE_*` 코드를 `JSON_PARSE_ERROR` 그룹 라벨로 매핑해 표시할 수 있다.

### 4.4 Citation (`CITE_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `CITE_REQUIRED_FIELD_MISSING` | citation 필수 필드 누락 | 500 | true | chunk_id/case_id/snippet 누락 |
| `CITE_INVALID_TYPE` | citation 타입 오류 | 500 | true | citations가 배열이 아님 |
| `CITE_CASE_MISMATCH` | citation case_id 불일치 | 500 | true | 검색 컨텍스트와 case_id 다름 |
| `CITE_SNIPPET_NOT_FOUND` | snippet 근거 매칭 실패 | 500 | true | snippet이 원문에 없음 |
| `CITE_DUPLICATED_ENTRY` | citation 중복 경고 | 200 | false | 동일 근거 반복 |
| `CITE_EMPTY_WARNING` | citation 비어 있음 경고 | 200 | false | answer는 있으나 citations 없음 |

### 4.5 Model/추론 (`MODEL_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `MODEL_NOT_READY` | 모델 준비 안 됨 | 503 | true | Ollama/model 로드 실패 |
| `MODEL_CALL_FAILED` | 모델 호출 실패 | 502 | true | 네트워크/timeout 포함 |
| `MODEL_TIMEOUT` | 모델 응답 시간 초과 | 504 | true | 지정 timeout 초과 |
| `MODEL_RESPONSE_INVALID` | 모델 응답 형식 이상 | 502 | true | 예상 구조와 불일치 |

### 4.6 Performance (`PERF_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `PERF_LATENCY_THRESHOLD_EXCEEDED` | 지연 임계치 초과 | 200 | false | 경고성 이벤트 |
| `PERF_RETRIEVAL_SLOW` | 검색 구간 지연 | 200 | false | retrieval 병목 의심 |
| `PERF_PARSE_SLOW` | 파싱 구간 지연 | 200 | false | parse/retry 병목 의심 |

### 4.7 OOM/메모리 (`OOM_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `OOM_DETECTED` | OOM 감지 | 500 | true | CUDA/메모리 부족 |
| `OOM_CONTEXT_REDUCED` | 컨텍스트 축소 적용 | 200 | true | 폴백 1단계 적용 |
| `OOM_TOPK_REDUCED` | top_k 축소 적용 | 200 | true | 폴백 2단계 적용 |
| `OOM_MODEL_FALLBACK_APPLIED` | 경량 모델 폴백 적용 | 200 | true | 폴백 3단계 적용 |
| `OOM_FALLBACK_FAILED` | 폴백 실패 | 500 | false | 모든 폴백 실패 |

### 4.8 System/기타 (`SYS_*`)

| 코드 | 의미 | 기본 HTTP | retryable | 설명 |
| --- | --- | --- | --- | --- |
| `SYS_INTERNAL_ERROR` | 알 수 없는 내부 오류 | 500 | false | 예외 미분류 |
| `SYS_RESOURCE_NOT_FOUND` | 리소스 없음 | 404 | false | case/chunk 없음 |
| `SYS_INDEX_NOT_READY` | 인덱스 준비 안 됨 | 503 | true | 검색 전 인덱스 미생성 |

## 5. endpoint별 우선 사용 코드

### `/api/v1/structure`

- `REQ_*`
- `VAL_*`
- `MODEL_*` (LLM 구조화 호출 시)
- `SYS_INTERNAL_ERROR`

### `/api/v1/qa`

- `REQ_*`
- `MODEL_*`
- `PARSE_*`
- `CITE_*`
- `OOM_*`
- `PERF_*` (로그 이벤트)

### `/api/v1/search`

- `REQ_*`
- `SYS_INDEX_NOT_READY`
- `PERF_RETRIEVAL_SLOW`

## 6. severity 기준

| severity | 의미 | 처리 원칙 |
| --- | --- | --- |
| `error` | 계약 또는 기능 실패 | API 실패 응답, is_valid=false |
| `warning` | 품질 저하, 처리 계속 가능 | API 성공 + warnings 기록 |
| `info` | 운영 이벤트 | 성능/폴백 로깅 |

## 7. 로그 필드 권장 규격

오류/경고를 로그에 남길 때 아래를 포함한다.

- request_id
- endpoint
- code
- message
- severity
- retryable
- retry_count
- case_id (있을 때)
- chunk_id (있을 때)
- latency_ms
- memory_mb

## 8. 협업 전달 규칙

### FE 전달

- UI는 `code`와 `message`를 직접 표시 가능해야 한다.
- `warning`은 노란 상태 배너, `error`는 빨간 상태 배너로 구분한다.
- citation 관련 오류는 답변 본문과 분리해 표시한다.

### BE1 전달

- 구조화 실패 케이스는 `VAL_*` 코드 기준으로 집계한다.
- `VAL_WARNING_LOW_CONFIDENCE`, `VAL_WARNING_EMPTY_ENTITIES`는 품질 개선 리스트로 전달한다.

### BE2 전달

- QA 실패는 `PARSE_*`, `CITE_*` 중심으로 공유한다.
- 검색-응답 연결 문제는 `CITE_CASE_MISMATCH`, `CITE_SNIPPET_NOT_FOUND`로 추적한다.

## 9. 이번 주 적용 범위

이번 주는 아래까지를 완료 기준으로 둔다.

- 코드 목록 동결(v0.1)
- endpoint별 우선 코드 맵 고정
- FE/BE1/BE2 공유용 표준 에러 형식 고정

양자화(4-bit/8-bit) 실험 결과 연계 코드는 후순위로 미룬다.

## 10. 다음 작업 연결

다음 산출물은 아래 순서로 이어간다.

1. validation 결과 포맷 초안 (`docs/be3_validation_format.md`)
2. JSON 파싱 실패 유형 메모 (`docs/be3_json_parse_failures.md`)
3. JSON 재시도 전략 초안 (`docs/be3_json_retry_strategy.md`)
4. 성능/OOM 로깅 기준 (`docs/be3_perf_oom_baseline.md`)

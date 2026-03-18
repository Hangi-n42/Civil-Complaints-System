# BE3 Validation 결과 포맷 초안

문서 버전: v0.2  
작성일: 2026-03-18  
작성자: BE3 김현석  
기준 문서: [be2_be3_compromise_contract_week1.md](../../10_contracts/interfaces/be2_be3_compromise_contract_week1.md), [be3_validation_rules.md](be3_validation_rules.md), [be3_error_codes.md](be3_error_codes.md), [schema_contract.md](../../10_contracts/schema/schema_contract.md), [api_spec.md](../../10_contracts/api/api_spec.md)

## 1. 문서 목적

이 문서는 validation 결과를 API, FE, 로그에서 동일하게 다루기 위한 공통 포맷을 정의한다.
목표는 다음과 같다.

- 어떤 검증 실패가 있었는지 필드 단위로 추적 가능하게 한다.
- 에러와 경고를 분리해 처리 중단 여부를 명확히 한다.
- FE가 상태 배너와 상세 오류 목록을 일관되게 렌더링할 수 있게 한다.
- BE1/BE2가 품질 개선용 집계 데이터를 동일 기준으로 받을 수 있게 한다.

## 2. 설계 원칙

- validation 결과는 모든 구조화 결과에 포함한다.
- 에러가 없어도 errors는 빈 배열로 항상 포함한다.
- warnings도 가능하면 항상 포함한다.
- 각 항목은 최소 field, code, message를 가진다.
- 코드값은 [be3_error_codes.md](be3_error_codes.md)의 정의를 따른다.

## 3. ValidationResult 표준 구조

### 3.1 기본 스키마

```json
{
  "is_valid": true,
  "errors": [],
  "warnings": [],
  "summary": {
    "error_count": 0,
    "warning_count": 0,
    "checked_at": "2026-03-13T14:00:00+09:00",
    "validator_version": "be3-val-v0.1"
  }
}
```

### 3.2 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| is_valid | boolean | Y | 에러 기준 유효성 결과 |
| errors | array[ValidationIssue] | Y | 처리 중단 또는 실패로 보는 항목 |
| warnings | array[ValidationIssue] | N(권장 Y) | 품질 경고 항목 |
| summary | object | N(권장 Y) | 집계/추적 메타데이터 |

## 4. ValidationIssue 표준 구조

### 4.1 기본 스키마

```json
{
  "field": "request.confidence",
  "code": "VAL_INVALID_CONFIDENCE_RANGE",
  "message": "confidence는 0 이상 1 이하여야 합니다.",
  "severity": "error",
  "retryable": false,
  "value": 1.21,
  "expected": "0.0 <= value <= 1.0",
  "source": "validator",
  "hint": "모델 출력값을 clamp하거나 후처리 규칙을 적용하세요."
}
```

### 4.2 필드 정의

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| field | string | Y | 문제 발생 필드 경로 |
| code | string | Y | 표준 오류 코드 |
| message | string | Y | 사람이 읽는 설명 |
| severity | string | Y | error, warning |
| retryable | boolean | Y | 재시도 가치 여부 |
| value | any | N | 실제 관측 값 |
| expected | string | N | 기대 규칙 |
| source | string | N | validator, parser, citation_checker 등 |
| hint | string | N | 대응 가이드 |

## 5. summary 구조

```json
{
  "error_count": 1,
  "warning_count": 2,
  "checked_at": "2026-03-13T14:00:00+09:00",
  "validator_version": "be3-val-v0.1",
  "ruleset": "structured_civil_case",
  "case_id": "CASE-2026-000123"
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| error_count | integer | Y | errors 길이 |
| warning_count | integer | Y | warnings 길이 |
| checked_at | string(datetime) | Y | 검증 시각 |
| validator_version | string | Y | 검증기 버전 |
| ruleset | string | N | structured_civil_case, qa_response 등 |
| case_id | string | N | 해당 케이스 ID |

## 6. 구조화 결과용 validation 예시

### 6.1 통과 예시

```json
{
  "is_valid": true,
  "errors": [],
  "warnings": [
    {
      "field": "entities",
      "code": "VAL_WARNING_EMPTY_ENTITIES",
      "message": "추출된 엔티티가 없습니다.",
      "severity": "warning",
      "retryable": false,
      "source": "validator",
      "hint": "NER 프롬프트 또는 후처리 규칙을 점검하세요."
    }
  ],
  "summary": {
    "error_count": 0,
    "warning_count": 1,
    "checked_at": "2026-03-13T14:10:00+09:00",
    "validator_version": "be3-val-v0.1",
    "ruleset": "structured_civil_case",
    "case_id": "CASE-2026-000123"
  }
}
```

### 6.2 실패 예시

```json
{
  "is_valid": false,
  "errors": [
    {
      "field": "request.confidence",
      "code": "VAL_INVALID_CONFIDENCE_RANGE",
      "message": "confidence는 0 이상 1 이하여야 합니다.",
      "severity": "error",
      "retryable": false,
      "value": 1.21,
      "expected": "0.0 <= value <= 1.0",
      "source": "validator",
      "hint": "모델 출력값 보정 또는 룰 기반 후처리가 필요합니다."
    },
    {
      "field": "context.evidence_span",
      "code": "VAL_INVALID_EVIDENCE_SPAN_ORDER",
      "message": "evidence_span 시작 인덱스가 종료 인덱스보다 큽니다.",
      "severity": "error",
      "retryable": false,
      "value": [80, 20],
      "expected": "start <= end",
      "source": "validator"
    }
  ],
  "warnings": [],
  "summary": {
    "error_count": 2,
    "warning_count": 0,
    "checked_at": "2026-03-13T14:12:00+09:00",
    "validator_version": "be3-val-v0.1",
    "ruleset": "structured_civil_case",
    "case_id": "CASE-2026-000124"
  }
}
```

## 7. QA 응답용 validation 예시

```json
{
  "is_valid": false,
  "errors": [
    {
      "field": "citations[0].chunk_id",
      "code": "CITE_REQUIRED_FIELD_MISSING",
      "message": "citation 필수 필드 chunk_id가 누락되었습니다.",
      "severity": "error",
      "retryable": true,
      "source": "citation_checker",
      "hint": "LLM 출력 포맷에서 citations 스키마를 강제하세요."
    }
  ],
  "warnings": [
    {
      "field": "limitations",
      "code": "VAL_WARNING_LOW_CONFIDENCE",
      "message": "응답 신뢰도가 낮습니다.",
      "severity": "warning",
      "retryable": false,
      "source": "validator"
    }
  ],
  "summary": {
    "error_count": 1,
    "warning_count": 1,
    "checked_at": "2026-03-13T14:15:00+09:00",
    "validator_version": "be3-val-v0.1",
    "ruleset": "qa_response"
  }
}
```

## 8. API 응답 포함 방식

### 8.1 structure API

권장 방식:

- 각 result 객체에 validation 필드를 포함한다.
- 상위 응답에는 집계 메타를 함께 둔다.

```json
{
  "success": true,
  "structured_count": 2,
  "invalid_count": 1,
  "results": [
    {
      "case_id": "CASE-2026-000123",
      "observation": {"text": "...", "confidence": 0.91, "evidence_span": [0, 29]},
      "result": {"text": "...", "confidence": 0.87, "evidence_span": [30, 60]},
      "request": {"text": "...", "confidence": 0.93, "evidence_span": [61, 82]},
      "context": {"text": "...", "confidence": 0.84, "evidence_span": [83, 104]},
      "entities": [],
      "validation": {
        "is_valid": true,
        "errors": [],
        "warnings": []
      }
    }
  ]
}
```

### 8.2 qa API

권장 방식:

- 파싱 성공 시 qa_validation을 항상 포함해 citation 정합성을 표시한다.
- 파싱 실패 시 error 객체와 함께 마지막 validation 상태를 같이 보낸다.

```json
{
  "success": true,
  "request_id": "REQ-20260318-AB12CD34",
  "timestamp": "2026-03-18T18:30:00+09:00",
  "answer": "...",
  "citations": [
    {
      "ref_id": 1,
      "doc_id": "DOC-25-088",
      "chunk_id": "CHUNK-00044",
      "case_id": "CASE-2026-000123",
      "snippet": "..."
    }
  ],
  "confidence": "medium",
  "limitations": "...",
  "meta": {
    "processing_time": 3.87,
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

## 9. FE 표시 가이드

- is_valid=false 이면 상단 error 배너를 표시한다.
- errors 배열은 코드, 필드, 메시지 순서로 테이블 렌더링한다.
- warnings는 접기 가능한 섹션으로 표시한다.
- citations는 [[CITE:n]] 토큰의 n과 citations.ref_id를 기준으로 매핑한다.
- retryable=true 오류는 다시 시도 버튼과 연결 가능하게 노출한다.

## 10. 로그 저장 가이드

validation 결과를 로그로 저장할 때 아래 필드를 권장한다.

- request_id
- endpoint
- case_id
- validation.is_valid
- validation.summary.error_count
- validation.summary.warning_count
- first_error_code
- first_warning_code
- checked_at

## 11. 이번 주 완료 기준

- ValidationResult 기본 구조 동결
- ValidationIssue 필수 필드 동결
- structure/qa API 포함 방식 합의
- FE 렌더링 최소 규칙 합의

## 12. 다음 작업 연결

다음 문서는 아래 순서로 이어간다.

1. JSON 파싱 실패 유형 메모 ([docs/20_domains/generation/be3_json_parse_failures.md](be3_json_parse_failures.md))
2. JSON 재시도 전략 초안 ([docs/20_domains/generation/be3_json_retry_strategy.md](be3_json_retry_strategy.md))
3. 성능/OOM 기준 메모 ([docs/20_domains/generation/be3_perf_oom_baseline.md](be3_perf_oom_baseline.md))

## 13. FE/BE2 통합 스펙 링크

Citation, Error, Validation UI 연동용 단일 통합 스펙은 아래 문서를 기준으로 사용한다.

- [docs/10_contracts/interfaces/be3_fe_be2_unified_spec.md](../../10_contracts/interfaces/be3_fe_be2_unified_spec.md)

이 문서는 ValidationResult/ValidationIssue 기본 계약을 유지하고,
FE 렌더링 규칙과 BE2 응답 필드 매핑을 단일 포맷으로 통합한다.

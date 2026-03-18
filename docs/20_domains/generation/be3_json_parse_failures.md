# BE3 JSON 파싱 실패 유형 메모

문서 버전: v0.1  
작성일: 2026-03-13  
작성자: BE3 김현석  
기준 문서: [be3_error_codes.md](be3_error_codes.md), [be3_validation_format.md](be3_validation_format.md), [schema_contract.md](../../10_contracts/schema/schema_contract.md), [api_spec.md](../../10_contracts/api/api_spec.md)

## 1. 문서 목적

이 문서는 QA/구조화 단계에서 발생하는 JSON 파싱 실패를 유형별로 분류하고, 각 실패의 탐지 방식과 우선 대응 방향을 정의한다.
목표는 다음과 같다.

- 파싱 실패 원인을 빠르게 재현하고 분류한다.
- 재시도 전략에서 어떤 실패를 자동 복구할지 기준을 만든다.
- FE/BE2에 전달할 에러 코드와 메시지를 일관되게 유지한다.

## 2. 분류 원칙

- 1차 분류: 문법 실패(Syntax), 구조 실패(Structure), 계약 실패(Schema), 정합성 실패(Consistency)
- 2차 분류: 자동 복구 가능 여부
  - recoverable: 전처리 또는 재요청으로 복구 가능
  - non-recoverable: 재시도해도 의미 있는 복구 가능성이 낮음
- 오류 코드 체계는 [be3_error_codes.md](be3_error_codes.md)를 따른다.

## 3. 실패 유형 카탈로그

### 3.1 Syntax 실패

| ID | 유형 | 예시 | 탐지 신호 | 코드 | recoverable |
| --- | --- | --- | --- | --- | --- |
| S-01 | 닫히지 않은 중괄호/대괄호 | `{ "answer": "..."` | JSONDecodeError: EOF | `PARSE_JSON_DECODE_ERROR` | true |
| S-02 | trailing comma | `{ "a": 1, }` | JSONDecodeError near `, }` | `PARSE_JSON_DECODE_ERROR` | true |
| S-03 | 작은따옴표 사용 | `{ 'answer': '...' }` | JSONDecodeError: expecting `"` | `PARSE_JSON_DECODE_ERROR` | true |
| S-04 | 이스케이프 오류 | `"snippet": "a\b\c"` | invalid escape sequence | `PARSE_JSON_DECODE_ERROR` | true |
| S-05 | 코드블록 경계 손상 | ```json 시작만 있고 종료 없음 | 블록 추출 실패 | `PARSE_JSON_BLOCK_EXTRACTION_FAILED` | true |

### 3.2 Structure 실패

| ID | 유형 | 예시 | 탐지 신호 | 코드 | recoverable |
| --- | --- | --- | --- | --- | --- |
| T-01 | JSON 앞뒤 설명문 포함 | `답변입니다. { ... } 참고` | 객체 외 텍스트 존재 | `PARSE_JSON_BLOCK_EXTRACTION_FAILED` | true |
| T-02 | 최상위 타입 불일치 | `[ { ... } ]` 또는 `"..."` | dict 기대, list/string 수신 | `PARSE_SCHEMA_MISMATCH` | true |
| T-03 | 중첩 레벨 과다/붕괴 | citations가 객체로 옴 | 필드 타입 검사 실패 | `PARSE_SCHEMA_MISMATCH` | true |
| T-04 | 빈 응답 | `""` 또는 공백만 | length==0 | `PARSE_EMPTY_MODEL_RESPONSE` | true |

### 3.3 Schema 실패

| ID | 유형 | 예시 | 탐지 신호 | 코드 | recoverable |
| --- | --- | --- | --- | --- | --- |
| C-01 | 필수 필드 누락 | answer 없음 | required 필드 누락 | `PARSE_SCHEMA_MISMATCH` | true |
| C-02 | confidence enum 위반 | `"confidence": "highly"` | enum 검사 실패 | `PARSE_SCHEMA_MISMATCH` | true |
| C-03 | citations 타입 위반 | `"citations": "..."` | array 검사 실패 | `PARSE_SCHEMA_MISMATCH` | true |
| C-04 | citation 필수 필드 누락 | chunk_id 누락 | citation validator 실패 | `CITE_REQUIRED_FIELD_MISSING` | true |
| C-05 | evidence_span 포맷 오류 | `[10]`, `[30, 10]` | span 규칙 실패 | `VAL_INVALID_EVIDENCE_SPAN_FORMAT` 또는 `VAL_INVALID_EVIDENCE_SPAN_ORDER` | false |

### 3.4 Consistency 실패

| ID | 유형 | 예시 | 탐지 신호 | 코드 | recoverable |
| --- | --- | --- | --- | --- | --- |
| K-01 | citation case_id 불일치 | 검색 컨텍스트와 다른 case_id | context join 실패 | `CITE_CASE_MISMATCH` | true |
| K-02 | snippet 원문 불일치 | snippet이 검색 텍스트에 없음 | substring 매칭 실패 | `CITE_SNIPPET_NOT_FOUND` | true |
| K-03 | answer는 있으나 citations 전부 비어 있음 | citations=[] | 경고 기준 위반 | `CITE_EMPTY_WARNING` | false |
| K-04 | 동일 citation 반복 | 같은 chunk 3회 반복 | 중복 검사 | `CITE_DUPLICATED_ENTRY` | false |

## 4. 실패 우선순위

### P0 (즉시 차단)

- JSON 자체가 파싱되지 않는 경우
- 필수 필드(answer, confidence, limitations) 누락
- citations가 배열이 아니거나 필수 필드 누락

### P1 (자동 복구 후 재검증)

- 코드블록/앞뒤 설명문 제거로 복구 가능한 경우
- enum, 타입, 필드명 오타처럼 재요청으로 복구 가능한 경우
- citation 정합성 불일치

### P2 (경고 기록)

- citation 없음
- snippet 품질 저하
- 중복 citation

## 5. 탐지/기록 필드 표준

파싱 실패가 발생하면 아래를 로그에 남긴다.

- request_id
- endpoint
- model
- parse_stage
  - extract
  - decode
  - schema_validate
  - citation_validate
- error_code
- raw_response_length
- retry_count
- recoverable
- latency_ms

## 6. 파싱 단계별 실패 포인트

### 단계 1: JSON 후보 추출

실패 포인트:

- 코드블록 경계가 깨짐
- JSON 외 텍스트가 섞임

대표 코드:

- `PARSE_JSON_BLOCK_EXTRACTION_FAILED`

### 단계 2: JSON decode

실패 포인트:

- 문법 오류
- escape 오류
- 빈 문자열

대표 코드:

- `PARSE_JSON_DECODE_ERROR`
- `PARSE_EMPTY_MODEL_RESPONSE`

### 단계 3: 스키마 검증

실패 포인트:

- 필수 필드 누락
- 타입/enum 불일치

대표 코드:

- `PARSE_SCHEMA_MISMATCH`

### 단계 4: citation 정합성 검증

실패 포인트:

- chunk_id/case_id/snippet 누락
- 검색 컨텍스트와 불일치

대표 코드:

- `CITE_REQUIRED_FIELD_MISSING`
- `CITE_CASE_MISMATCH`
- `CITE_SNIPPET_NOT_FOUND`

## 7. 샘플 실패 케이스

### 케이스 A: 코드블록 밖 텍스트 혼합

입력 응답:

```text
다음은 결과입니다.
{
  "answer": "...",
  "citations": []
}
주의: 참고용입니다.
```

분류:

- T-01 (Structure)
- 코드: `PARSE_JSON_BLOCK_EXTRACTION_FAILED`
- 처리: 앞뒤 텍스트 제거 후 재시도

### 케이스 B: 필수 필드 누락

입력 응답:

```json
{
  "citations": [
    {
      "chunk_id": "CHUNK-0001",
      "case_id": "CASE-0001",
      "snippet": "..."
    }
  ],
  "confidence": "medium",
  "limitations": "..."
}
```

분류:

- C-01 (Schema)
- 코드: `PARSE_SCHEMA_MISMATCH`
- 처리: JSON-only 재요청

### 케이스 C: citation 정합성 실패

입력 응답:

```json
{
  "answer": "...",
  "citations": [
    {
      "chunk_id": "CHUNK-9999",
      "case_id": "CASE-8888",
      "snippet": "..."
    }
  ],
  "confidence": "high",
  "limitations": "..."
}
```

분류:

- K-01, K-02 (Consistency)
- 코드: `CITE_CASE_MISMATCH`, `CITE_SNIPPET_NOT_FOUND`
- 처리: citations 재생성 프롬프트로 재요청

## 8. 협업 전달 포인트

### FE

- 사용자 메시지는 `message` 중심으로 표시
- 디버그 모드에서만 `code`를 상세 표시
- retryable=true인 경우 재시도 버튼 활성화 가능

### BE2

- search->qa 연결 문제는 `CITE_*` 코드 중심으로 공유
- retrieval 품질 문제와 parse 문제를 코드로 분리 집계

### BE1

- 구조화 산출물의 span/confidence 오류는 `VAL_*` 코드 중심으로 전달

## 9. 이번 주 완료 기준

- 실패 유형 카탈로그(S/T/C/K) 확정
- 코드 매핑 확정
- 파싱 단계별 실패 지점 정의
- 샘플 실패 케이스 3종 정리

## 10. 다음 작업 연결

다음 문서는 JSON 재시도 전략 초안이다.

- 대상 파일: [docs/be3_json_retry_strategy.md](be3_json_retry_strategy.md)
- 핵심 내용: 단계별 재시도 정책, 프롬프트 보정, 중단 조건, 최종 에러 반환 규칙

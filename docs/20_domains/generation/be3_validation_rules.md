# BE3 Validation 규칙 메모

문서 버전: v0.2  
작성일: 2026-03-18  
작성자: BE3 김현석  
기준 문서: [be2_be3_compromise_contract_week1.md](../../10_contracts/interfaces/be2_be3_compromise_contract_week1.md), [schema_contract.md](../../10_contracts/schema/schema_contract.md), [api_spec.md](../../10_contracts/api/api_spec.md), [be3_manual.md](../../30_manuals/be3_manual.md), [prd.md](../../00_overview/prd.md)

## 1. 문서 목적

이 문서는 BE3 관점에서 구조화 결과와 QA 응답을 어떤 규칙으로 검증할지 정의한다.
목표는 다음과 같다.

- 어떤 경우를 validation error로 볼지 팀이 바로 이해할 수 있게 한다.
- FE가 표시할 validation/error 상태의 기준을 고정한다.
- BE1 구조화 출력과 BE2 QA 응답이 같은 데이터 계약을 따르도록 맞춘다.
- 2주차 이후 validator 구현 시 그대로 코드로 옮길 수 있는 기준을 만든다.

## 2. 적용 범위

이번 문서에서 우선 검증하는 대상은 아래 3종이다.

- StructuredCivilCase
- ValidationResult
- QAResponse

이번 주 범위에서 SearchResult 상세 검증은 후순위로 두되, citation 연결에 필요한 최소 필드는 함께 본다.

## 3. 검증 우선순위

### P0. 필수 에러로 즉시 처리할 항목

- 필수 필드 누락
- 필드 타입 불일치
- confidence 범위 위반
- evidence_span 형식 오류
- 허용되지 않은 entity label
- QA 성공 응답의 request_id, timestamp, answer, citations, confidence, limitations, meta, qa_validation 누락
- citation의 ref_id, chunk_id, case_id, snippet 누락

### P1. warning으로 기록하되 처리 계속 가능한 항목

- 엔티티 수가 지나치게 적음
- evidence_span이 원문 길이와 정확히 맞지 않음
- confidence가 임계치보다 지나치게 낮음
- citations가 비어 있음
- snippet 길이가 너무 짧아 근거 확인이 어려움

### P2. 후속 보정 또는 협의가 필요한 항목

- category, region 같은 선택 필드의 누락 처리 기준
- entity start/end를 MVP 필수로 볼지 여부
- search_trace, latency_ms 같은 API 부가 필드의 검증 수준

## 4. 검증 레벨 정의

### error

- 데이터 계약 위반이다.
- 저장, 후속 인덱싱, QA 연결 중 최소 한 단계 이상을 깨뜨릴 가능성이 높다.
- is_valid는 false가 된다.

### warning

- 데이터 계약은 통과하지만 품질이나 가시성이 떨어진다.
- 저장 및 후속 처리는 가능하다.
- is_valid는 true를 유지할 수 있다.

## 5. StructuredCivilCase 검증 규칙

### 5.1 루트 필드

필수 필드:

- case_id
- source
- created_at
- raw_text
- observation
- result
- request
- context
- entities
- validation

error 규칙:

- 필수 필드가 없으면 error
- case_id, source, raw_text가 빈 문자열이거나 공백만 있으면 error
- created_at이 YYYYMMDD, ISO 8601 처나 "unknown" 문자열이 아니면 error (BE1 입력 호환 위함)
- entities가 배열이 아니면 error
- validation이 객체가 아니면 error

warning 규칙:

- category 누락
- region 누락
- raw_text 길이가 지나치게 짧음

### 5.2 4요소 공통 규칙

대상 필드:

- observation
- result
- request
- context

각 필드는 아래 하위 구조를 만족해야 한다.

- text: string
- confidence: number
- evidence_span: [start, end]

error 규칙:

- text가 없거나 공백만 있으면 error
- confidence가 number가 아니면 error
- confidence가 0 미만 또는 1 초과면 error
- evidence_span이 길이 2 배열이 아니면 error
- evidence_span 원소가 integer가 아니면 error
- start가 end보다 크면 error
- start가 음수면 error

warning 규칙:

- evidence_span end가 raw_text 길이를 초과함
- evidence_span으로 추출한 substring이 text와 크게 불일치함
- confidence가 0.30 미만임
- text 길이가 지나치게 짧아 의미 단위로 보기 어려움

### 5.3 entities 규칙

허용 label:

- LOCATION
- TIME
- FACILITY
- HAZARD
- ADMIN_UNIT

error 규칙:

- 각 entity가 객체가 아니면 error
- label 또는 text 누락 시 error
- label이 허용 목록에 없으면 error
- text가 공백만 있으면 error
- start 또는 end가 있을 때 integer가 아니면 error
- start와 end가 함께 있을 때 start > end이면 error
- confidence가 있을 때 0~1 범위를 벗어나면 error

warning 규칙:

- entities가 빈 배열임
- 동일 label, 동일 text가 과도하게 중복됨
- start, end가 없어서 하이라이팅 정밀도가 떨어짐

### 5.4 validation 필드 규칙

error 규칙:

- is_valid 누락 또는 boolean 아님
- errors 누락 또는 배열 아님

warning 규칙:

- warnings 필드 누락

## 6. ValidationResult 검증 규칙

### 6.1 필수 구조

- is_valid: boolean
- errors: array
- warnings: array 권장

### 6.2 ValidationError 항목 규칙

권장 필드:

- field
- code
- message

후속 확장 필드:

- severity
- value
- expected
- retryable

error 규칙:

- errors 배열 원소가 객체가 아니면 error
- field, code, message 중 하나라도 없으면 error
- code가 사전 정의된 오류 코드 체계를 따르지 않으면 warning 후 추후 정리

## 7. QAResponse 검증 규칙

본 절의 QAResponse는 `success=true`인 QA API 응답 본문을 기준으로 한다.

### 7.1 루트 필드

필수 필드:

- success
- request_id
- timestamp
- answer
- citations
- confidence
- limitations
- meta
- qa_validation

선택 필드:

- search_trace

error 규칙:

- success가 true가 아니면 error
- request_id가 없거나 공백이면 error
- timestamp가 ISO 8601 형식이 아니면 error
- answer가 없거나 공백만 있으면 error
- citations가 배열이 아니면 error
- confidence가 low, medium, high 중 하나가 아니면 error
- limitations가 없거나 공백만 있으면 error
- meta가 객체가 아니면 error
- qa_validation이 객체가 아니면 error
- search_trace가 있을 때 객체가 아니면 error

warning 규칙:

- citations가 빈 배열임
- limitations가 지나치게 짧아 사용자 경고 역할을 못함

### 7.2 citations 규칙

필수 필드:

- ref_id
- chunk_id
- case_id
- snippet

조건부 필수 필드:

- doc_id (retrieval 결과에 존재하는 경우)

error 규칙:

- citation 원소가 객체가 아니면 error
- ref_id, chunk_id, case_id, snippet 중 하나라도 누락되면 error
- ref_id가 number가 아니면 error
- chunk_id, case_id, snippet가 공백 문자열이면 error
- answer의 [[CITE:n]] 토큰과 citations.ref_id가 1:1 매핑되지 않으면 error

warning 규칙:

- snippet 길이가 지나치게 짧음
- 동일 citation이 중복됨
- snippet이 실제 검색 컨텍스트와 정확히 연결되지 않음

### 7.3 search_trace 규칙

권장 필드:

- used_top_k
- retrieved_count

warning 규칙:

- used_top_k 또는 retrieved_count가 없으면 warning
- retrieved_count가 0인데 answer가 단정적으로 작성되면 warning

### 7.4 meta 규칙

필수 필드:

- processing_time
- model
- validation_warning

error 규칙:

- processing_time이 number가 아니면 error
- model이 없거나 공백이면 error
- validation_warning이 없거나 공백이면 error

### 7.5 qa_validation 규칙

필수 필드:

- is_valid
- errors
- warnings

error 규칙:

- is_valid가 boolean이 아니면 error
- errors가 배열이 아니면 error
- warnings가 배열이 아니면 error
- Week 1 기준으로 is_valid=false인데 answer를 함께 반환하면 error

## 8. API 응답에서 validation 처리 원칙

### structure 응답

- validation.is_valid는 항상 포함한다.
- errors는 빈 배열이어도 항상 포함한다.
- warnings는 가능하면 포함한다.
- validation error가 있어도 구조화 원문은 같이 반환해 FE와 BE1이 오류 사례를 분석할 수 있게 한다.

### qa 응답

- 파싱 성공 후 QAResponse 계약을 만족하지 못하면 PARSE_SCHEMA_MISMATCH 또는 VAL_* 계열로 처리한다.
- citations가 비어 있어도 answer 자체는 반환 가능하지만 warnings 또는 limitations에 반영한다.

## 9. 이번 주 구현 기준에서의 판단선

### 저장/후속 처리 중단이 필요한 경우

- StructuredCivilCase의 필수 필드 누락
- 4요소 하위 구조 파손
- confidence, evidence_span 형식 파손
- entity label 계약 위반
- QAResponse의 confidence 값 계약 위반
- citation 필수 필드 누락

### 저장은 가능하되 개선 대상으로 남길 경우

- category, region 누락
- entities 없음
- citation 개수 부족
- confidence 낮음
- evidence_span과 text 정합성 약함

## 10. 현재 확인된 문서/스키마 불일치

현재 [schemas/civil_case.schema.json](../schemas/civil_case.schema.json)은 README 및 계약 문서 기준 구조와 다르다.

현재 스키마 파일은 아래 특성을 가진다.

- id, requester, respondent, claim, reason 중심 구조
- confidence_score 단일 필드 사용
- entities가 persons, organizations, locations 객체 구조

반면 현재 프로젝트 기준 문서는 아래 구조를 요구한다.

- case_id, source, created_at, raw_text
- observation, result, request, context
- entities 배열
- validation 객체

따라서 이번 주 validator 초안과 이후 구현은 schema_contract 기준을 우선 적용하고, JSON 스키마 파일은 별도 정렬 작업이 필요하다.

## 11. 다음 문서 연결

이 문서 다음 작업은 아래 순서로 이어간다.

1. validation 오류 코드 초안 작성
2. validation 결과 포맷 초안 작성
3. JSON 파싱 실패 유형 메모 작성
4. 재시도 전략 초안 작성

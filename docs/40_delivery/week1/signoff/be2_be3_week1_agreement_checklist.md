# BE2-BE3 Week 1 합의 체크리스트 (1페이지)

문서 버전: v1.0  
작성일: 2026-03-18  
대상: BE2, BE3, FE
기준 문서: [be2_be3_compromise_contract_week1.md](../../../10_contracts/interfaces/be2_be3_compromise_contract_week1.md), [be3_fe_be2_unified_spec.md](../../../10_contracts/interfaces/be3_fe_be2_unified_spec.md), [api_spec.md](../../../10_contracts/api/api_spec.md), [be3_error_codes.md](../../../20_domains/generation/be3_error_codes.md)

## 1. 사용 규칙

- 이 문서는 Week 1 QA 인터페이스 합의 점검용이다.
- 각 항목은 반드시 필수(MUST) 또는 권장(SHOULD) 중 하나로 판정한다.
- 필수(MUST) 항목 미충족 시 합의 미완료로 본다.
- 권장(SHOULD) 항목 미충족 시 합의 완료는 가능하되 Week 2 개선 과제로 등록한다.

## 2. 필수(MUST) 체크리스트

### 2.1 응답 루트

- [ ] QA 성공 응답은 success=true를 사용한다.
- [ ] QA 실패 응답은 success=false를 사용한다.
- [ ] 성공/실패 모두 request_id를 포함한다.
- [ ] 성공/실패 모두 timestamp(ISO 8601)를 포함한다.

### 2.2 성공 응답 필수 필드

- [ ] answer를 포함한다.
- [ ] citations 배열을 포함한다.
- [ ] confidence를 포함하고 값은 low | medium | high 중 하나다.
- [ ] limitations를 포함하고 공백 문자열이 아니다.
- [ ] meta를 포함한다.
- [ ] qa_validation을 포함한다.

### 2.3 meta 필수 필드

- [ ] processing_time(number)을 포함한다.
- [ ] model(string)을 포함한다.
- [ ] validation_warning(string)을 포함한다.

### 2.4 qa_validation 필수 필드

- [ ] is_valid(boolean)을 포함한다.
- [ ] errors(array)를 포함한다.
- [ ] warnings(array)를 포함한다.

### 2.5 citation 필수 규칙

- [ ] 각 citation에 ref_id를 포함한다.
- [ ] 각 citation에 chunk_id를 포함한다.
- [ ] 각 citation에 case_id를 포함한다.
- [ ] 각 citation에 snippet을 포함하고 공백 문자열이 아니다.
- [ ] answer의 [[CITE:n]] 토큰과 citations.ref_id가 1:1로 매핑된다.

### 2.6 에러 응답 필수 규칙

- [ ] 실패 응답에서 error.code를 포함한다.
- [ ] 실패 응답에서 error.message를 포함한다.
- [ ] 실패 응답에서 error.retryable을 포함한다.
- [ ] JSON_PARSE_ERROR를 신규 표준 코드로 사용하지 않는다.
- [ ] 파싱 오류는 PARSE_* 세분화 코드를 사용한다.

### 2.7 재시도/정책 필수 규칙

- [ ] 파싱 재시도 최대 횟수는 3회다.
- [ ] 최종 파싱 실패 코드는 PARSE_RETRY_EXHAUSTED를 사용한다.
- [ ] Week 1에서는 qa_validation.is_valid=false와 answer 동시 반환을 허용하지 않는다.

## 3. 권장(SHOULD) 체크리스트

### 3.1 citation 확장

- [ ] doc_id를 포함한다 (retrieval 결과에 존재 시).
- [ ] relevance_score를 포함한다.
- [ ] source를 포함한다.
- [ ] start, end 오프셋을 포함한다.

### 3.2 응답 보강

- [ ] search_trace.used_top_k를 포함한다.
- [ ] search_trace.retrieved_count를 포함한다.

### 3.3 FE 렌더링

- [ ] success=false면 error.message를 상단 배너로 표시한다.
- [ ] [[CITE:n]]를 [출처 n] 배지로 렌더링한다.
- [ ] 배지 hover 시 citations.ref_id=n의 snippet을 표시한다.
- [ ] qa_validation.warnings를 접기 가능한 섹션으로 노출한다.

### 3.4 운영/호환

- [ ] 레거시 클라이언트는 필요 시 PARSE_*를 JSON_PARSE_ERROR 그룹으로만 매핑한다.
- [ ] 계약 버전 헤더 X-Contract-Version: qa-v1.1을 사용한다.

## 4. 판정 규칙

- 필수(MUST) 100% 충족 + 권장(SHOULD) 미충족 항목만 존재: Week 1 합의 완료
- 필수(MUST) 미충족 1개 이상: Week 1 합의 미완료

## 5. 서명

- BE2 확인: ____________________
- BE3 확인: ____________________
- FE 확인: ____________________
- 확인일: ____________________

# BE3 JSON 재시도 전략 초안

문서 버전: v0.2  
작성일: 2026-03-18  
작성자: BE3 김현석  
기준 문서: [be2_be3_compromise_contract_week1.md](../../10_contracts/interfaces/be2_be3_compromise_contract_week1.md), [be3_json_parse_failures.md](be3_json_parse_failures.md), [be3_error_codes.md](be3_error_codes.md), [be3_validation_format.md](be3_validation_format.md), [api_spec.md](../../10_contracts/api/api_spec.md)

## 1. 문서 목적

이 문서는 LLM 응답 JSON 파싱 실패 시 재시도 정책을 단계별로 정의한다.
목표는 다음과 같다.

- 파싱 실패를 자동 복구 가능한 경우와 즉시 실패 처리할 경우로 분리한다.
- 재시도 횟수, 프롬프트 보정 규칙, 중단 조건을 고정한다.
- 최종 실패 시 API/FE에 반환할 에러 형식을 일관되게 유지한다.

## 2. 기본 전략 요약

- 최대 재시도 횟수: 3회
- 재시도 방식: 단계형(전처리 복구 -> 포맷 강제 재요청 -> 축약 재요청)
- 실패 분기:
  - recoverable: 자동 재시도 수행
  - non-recoverable: 즉시 실패 반환
- 최종 실패 코드: `PARSE_RETRY_EXHAUSTED`
- 응답 래퍼: 성공/실패 모두 `success` 루트 필드 사용

## 3. 재시도 대상/비대상

### 3.1 재시도 대상 (recoverable)

- `PARSE_JSON_BLOCK_EXTRACTION_FAILED`
- `PARSE_JSON_DECODE_ERROR`
- `PARSE_EMPTY_MODEL_RESPONSE`
- `PARSE_SCHEMA_MISMATCH`
- `CITE_REQUIRED_FIELD_MISSING`
- `CITE_CASE_MISMATCH`
- `CITE_SNIPPET_NOT_FOUND`
- `MODEL_TIMEOUT`
- `MODEL_RESPONSE_INVALID`

### 3.2 재시도 비대상 (non-recoverable)

- `REQ_*` 계열 (요청 자체 오류)
- `VAL_INVALID_EVIDENCE_SPAN_ORDER` 등 입력 데이터 계약 자체 파손
- 보안/정책 위반 응답
- 동일 요청에서 반복적으로 동일 non-retryable 오류가 발생한 경우

## 4. 단계별 재시도 정책

## 4.1 Attempt 0 (초기 시도)

입력:

- 기본 RAG 프롬프트
- JSON 출력 강제 문구 포함

처리:

1. 코드블록 추출 시도
2. JSON decode
3. 스키마 검증
4. citation 정합성 검증

성공 조건:

- validation.is_valid=true
- error 없음

실패 시:

- recoverable이면 Attempt 1로 이동
- non-recoverable이면 즉시 실패

## 4.2 Attempt 1 (전처리 복구)

목적:

- 응답 문자열을 파괴적으로 바꾸지 않고 경미한 형식 오류를 복구

복구 규칙:

- 코드블록 밖 텍스트 제거
- 첫 번째 JSON 객체 범위만 추출
- 흔한 prefix/suffix 제거(예: "다음은 결과입니다")
- trailing comma 제거
- 줄바꿈/제어문자 정리

재검증:

- decode -> schema -> citation 순서 재검증

실패 시:

- `PARSE_JSON_DECODE_ERROR` 또는 `PARSE_SCHEMA_MISMATCH` 유지
- Attempt 2 이동

## 4.3 Attempt 2 (포맷 강제 재요청)

목적:

- 모델에 JSON만 반환하도록 재요청

재요청 프롬프트 가이드:

- 자연어 설명 금지
- 코드블록 금지
- 필수 필드 명시(request_id, timestamp, answer, citations, confidence, limitations, meta, qa_validation)
- enum 제한 명시(confidence: low|medium|high)
- citations 각 항목 필수 필드 명시(ref_id, chunk_id, case_id, snippet)

권장 재요청 템플릿:

```text
이전 응답은 JSON 계약을 만족하지 않았습니다.
아래 규칙을 정확히 지켜 JSON 객체 하나만 반환하세요.
1) 순수 JSON만 반환
2) 필수 필드: request_id, timestamp, answer, citations, confidence, limitations, meta, qa_validation
3) confidence는 low, medium, high 중 하나
4) citations는 배열이며, 각 원소는 ref_id, chunk_id, case_id, snippet 포함
5) meta는 processing_time, model, validation_warning 포함
6) qa_validation은 is_valid, errors, warnings 포함
```

실패 시:

- Attempt 3 이동

## 4.4 Attempt 3 (축약 재요청 + 폴백)

목적:

- 컨텍스트 과다/노이즈로 인한 실패 가능성을 줄임

조치:

- 컨텍스트 길이 축소
- top_k 축소
- 필요 시 limitations 중심의 보수적 답변 유도

실패 시:

- 최종 실패 처리
- 코드: `PARSE_RETRY_EXHAUSTED`

## 5. 중단 조건

아래 중 하나면 즉시 중단한다.

- 동일 오류 코드가 2회 연속 non-retryable로 발생
- 모델 호출 자체가 불가한 상태(`MODEL_NOT_READY`)
- OOM 발생 후 폴백까지 실패(`OOM_FALLBACK_FAILED`)
- 요청 타임아웃 상한 초과

## 6. 타임아웃/지연 상한

- 요청 전체 상한: 8초 목표, 12초 하드 상한
- Attempt별 권장 시간 예산:
  - Attempt 0: 4.5초
  - Attempt 1: 1.0초
  - Attempt 2: 4.0초
  - Attempt 3: 2.5초

상한 초과 시:

- `MODEL_TIMEOUT` 또는 `PERF_LATENCY_THRESHOLD_EXCEEDED` 기록
- 최종적으로 `PARSE_RETRY_EXHAUSTED` 또는 `MODEL_TIMEOUT` 반환

## 7. 반환 정책

### 7.1 최종 성공

- 정상 QAResponse 반환
- qa_validation 항상 포함
- meta(processing_time/model/validation_warning) 항상 포함
- warnings가 있으면 함께 반환

### 7.2 부분 성공

- Week 1에서는 `qa_validation.is_valid=false + answer 반환`을 허용하지 않는다.
- citations 품질 저하가 warning 수준이면 `qa_validation.is_valid=true`를 유지한 채 success=true 반환 가능하다.
- citation 정합성이 계약 위반(error 수준)이면 재시도 후 실패 응답으로 전환한다.

### 7.3 최종 실패

권장 응답:

```json
{
  "success": false,
  "request_id": "REQ-20260318-34EF56AA",
  "timestamp": "2026-03-18T18:30:01+09:00",
  "error": {
    "code": "PARSE_RETRY_EXHAUSTED",
    "message": "응답 JSON 파싱 재시도 한도를 초과했습니다.",
    "details": {
      "last_error_code": "PARSE_SCHEMA_MISMATCH",
      "retry_count": 3
    },
    "severity": "error",
    "retryable": false
  }
}
```

## 8. 로깅 규격

재시도 루프에서 attempt마다 아래 필드를 기록한다.

- request_id
- endpoint
- attempt
- stage(extract/decode/schema/citation)
- error_code
- recoverable
- prompt_mode(base/repair/strict/compact)
- context_size
- top_k
- latency_ms
- memory_mb

## 9. 구현 의사코드

```python
max_retry = 3
attempt = 0
last_error = None

while attempt <= max_retry:
    try:
        response_text = call_model(prompt_for(attempt))
        candidate = preprocess_if_needed(response_text, attempt)
        data = parse_json(candidate)
        validate_schema(data)
        validate_citations(data, context)
        return success(data)
    except KnownError as e:
        log_attempt(attempt, e)
        last_error = e
        if not is_retryable(e) or attempt == max_retry:
            break
        attempt += 1

return fail("PARSE_RETRY_EXHAUSTED", last_error)
```

## 10. 협업 전달 포인트

### FE

- retryable=true 오류는 사용자에게 "다시 시도" 액션 제공 가능
- 최종 실패는 원인 코드 + 사용자 친화 메시지 동시 노출
- 레거시 클라이언트는 필요 시 `PARSE_*`를 `JSON_PARSE_ERROR` 그룹으로 묶어 표시할 수 있다.

### BE2

- citation 정합성 실패는 retrieval 품질 이슈와 분리해 코드 기반 공유
- top_k 축소/컨텍스트 축소가 품질에 미치는 영향 로그 공유

### BE1

- 구조화 산출물 자체의 span/confidence 오류가 parse 실패로 전파되는 사례 공유

## 11. 이번 주 완료 기준

- 재시도 대상/비대상 코드 고정
- Attempt 0~3 정책 고정
- 중단 조건과 최종 실패 반환 형식 합의
- 로깅 필드 합의

## 12. 다음 작업 연결

다음 문서는 성능/OOM 기준 메모이다.

- 대상 파일: [docs/be3_perf_oom_baseline.md](be3_perf_oom_baseline.md)
- 핵심 내용: 측정 지표, 임계치, OOM 폴백 순서, 운영 체크리스트

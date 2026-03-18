# BE2-BE3 절충 인터페이스 계약 (Week 1)

문서 버전: v1.1-compromise  
작성일: 2026-03-18  
담당: BE2, BE3

## 1. 목적

이 문서는 BE3의 안정성 강점(에러 코드 세분화, 단계형 재시도, 기존 응답 호환)을 유지하면서,
BE2의 장점(ref_id 기반 citation 매핑, 메타 고정, FE 렌더링 단순화)을 흡수한 절충 계약이다.

핵심 목표:

- 파싱 실패 원인 분해 가능
- FE citation 배지 렌더링 단순화
- 기존 API 응답(success/error 래퍼)과의 호환 유지
- 구현 복잡도 급증 없이 Week 1 내 적용 가능

## 2. 최상위 응답 계약

최상위 응답은 기존 공통 포맷을 유지한다.

- 성공: success=true
- 실패: success=false

### 2.1 성공 응답 최소 계약

```json
{
  "success": true,
  "request_id": "REQ-20260318-AB12CD34",
  "timestamp": "2026-03-18T18:30:00+09:00",
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
  },
  "search_trace": {
    "used_top_k": 5,
    "retrieved_count": 5
  }
}
```

### 2.2 실패 응답 최소 계약

```json
{
  "success": false,
  "request_id": "REQ-20260318-34EF56AA",
  "timestamp": "2026-03-18T18:30:01+09:00",
  "error": {
    "code": "PARSE_JSON_DECODE_ERROR",
    "message": "모델 응답을 JSON으로 파싱하지 못했습니다.",
    "retryable": true,
    "details": {
      "retry_count": 3,
      "stage": "decode"
    }
  }
}
```

## 3. 에러 코드 절충 원칙

### 3.1 외부 계약 코드

외부 응답 error.code는 BE3의 세분화 코드를 사용한다.

- PARSE_JSON_DECODE_ERROR
- PARSE_JSON_BLOCK_EXTRACTION_FAILED
- PARSE_SCHEMA_MISMATCH
- PARSE_RETRY_EXHAUSTED

### 3.2 FE 표시 메시지

- 사용자 표시 문구는 message를 그대로 사용
- 필요 시 FE는 코드별 라벨(예: "JSON 파싱 오류")을 별도로 매핑

### 3.3 JSON_PARSE_ERROR 처리

- JSON_PARSE_ERROR는 더 이상 1차 표준 코드로 사용하지 않는다.
- 하위 호환이 필요하면 API Gateway 또는 FE 매핑에서
  PARSE_* -> JSON_PARSE_ERROR 그룹 라벨로만 묶어 표시한다.

## 4. 파싱 안정화 및 재시도

- 최대 재시도: 3회
- 재시도 단계:
  1) 전처리 복구(코드블록/앞뒤 텍스트 제거)
  2) JSON 형식 강제 재요청
  3) compact 포맷 재요청(불필요 설명 제거)
- 최종 실패 코드는 PARSE_RETRY_EXHAUSTED

## 5. citation 절충 규칙

### 5.1 필수 필드

- ref_id
- chunk_id
- case_id
- snippet

### 5.2 조건부 필수 필드

- doc_id: retrieval 결과에 존재하면 필수, 미보유 파이프라인에서는 생략 가능

### 5.3 권장 필드

- relevance_score
- start, end
- source

### 5.4 정합성 검증

- answer 내 [[CITE:n]] 토큰과 citations.ref_id는 1:1 매핑
- citations.ref_id는 응답 내 유일
- chunk_id는 검색 결과 목록에 존재
- case_id는 해당 chunk_id와 일치
- snippet은 공백 문자열 금지

## 6. confidence/limitations/meta 규칙

### 6.1 confidence

- QA confidence는 enum(string)으로 고정: low | medium | high
- 구조화(4요소) confidence(number 0~1)와 의미가 다름을 명시

### 6.2 limitations

- 항상 포함(필수)
- 빈 문자열 금지

### 6.3 meta

meta는 성공 응답에서 항상 포함한다. 필수 3필드:

- processing_time (number, second)
- model (string)
- validation_warning (string)

## 7. qa_validation 규칙

- 성공 응답에서 qa_validation은 항상 포함(권장이 아닌 필수)
- 최소 구조:

```json
{
  "is_valid": true,
  "errors": [],
  "warnings": []
}
```

- warnings만 있어도 success=true 가능
- is_valid=false인데 answer를 반환하는 경우는 Week 1에서는 금지하고 실패 응답으로 내린다.

## 8. 상태별 최소 필드 매트릭스

| 상태 | 필수 필드 |
| --- | --- |
| success=true | success, request_id, timestamp, answer, citations, confidence, limitations, meta, qa_validation |
| success=false | success, request_id, timestamp, error.code, error.message, error.retryable |

## 9. 버전/마이그레이션 정책

- 계약 버전 헤더: X-Contract-Version: qa-v1.1
- Week 1 동안은 하위 호환 모드 허용:
  - 구형 응답이 confidence number를 줄 경우, 서버 어댑터에서 enum으로 변환
  - 구형 citation이 ref_id가 없으면 서버에서 1..N 재부여
- Week 2 시작 시 하위 호환 모드 제거 여부 재합의

## 10. 구현 체크리스트

### BE2

- answer에 [[CITE:n]] 토큰 삽입
- citations에 ref_id/chunk_id/case_id/snippet 채움
- 가능하면 doc_id, relevance_score 포함
- confidence enum 준수

### BE3

- PARSE_* 코드 기반 파서/재시도 유지
- qa_validation 항상 생성
- chunk_id/case_id/snippet 정합성 검증
- 실패 시 success=false + error 객체 표준 반환

### FE

- answer에서 [[CITE:n]] 파싱해 [출처 n] 배지 렌더링
- 배지 hover 시 citations.ref_id == n의 snippet 표시
- success=false면 error.message 배너 표시
- meta 3필드 및 qa_validation.warnings 렌더링

## 11. Week 1 합의 포인트 (최종)

- 에러 래퍼는 success/error 구조 유지
- 파싱 오류 코드는 PARSE_* 세분화 코드 채택
- 재시도 3회 채택
- confidence enum(low/medium/high) 채택
- limitations 항상 포함
- meta 필수 3필드 채택
- qa_validation 성공 응답 필수 포함
- citation은 ref_id 기반 토큰 매핑 채택
- doc_id는 조건부 필수로 완화

## 12. 오픈 이슈 (Week 2)

- citation start/end 오프셋 강제 여부
- is_valid=false + answer 반환(부분 성공) 허용 여부
- PARSE_*와 MODEL_* 코드의 FE 단순화 매핑 표준화

## 13. 합의 체크리스트 링크

Week 1 합의 점검은 아래 체크리스트를 기준으로 진행한다.

- [docs/be2_be3_week1_agreement_checklist.md](be2_be3_week1_agreement_checklist.md)

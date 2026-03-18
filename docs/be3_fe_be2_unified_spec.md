# BE3-FE/BE2 단일 통합 응답 스펙 (Citation, Error, Validation)

문서 버전: v0.2  
작성일: 2026-03-18  
작성자: BE3 김현석  
기준 문서: [be2_be3_compromise_contract_week1.md](be2_be3_compromise_contract_week1.md), [be3_validation_format.md](be3_validation_format.md), [be3_error_codes.md](be3_error_codes.md), [be3_json_parse_failures.md](be3_json_parse_failures.md), [be3_json_retry_strategy.md](be3_json_retry_strategy.md), [api_spec.md](api_spec.md)

## 1. 문서 목적

이 문서는 FE/BE2가 동일한 데이터 형식으로 Citation, Error, Validation 정보를 처리하도록 하는 단일 통합 스펙이다.

핵심 목표:

- FE가 답변 본문 내 출처 배지를 안정적으로 렌더링한다.
- 치명 오류(OOM/타임아웃 등) 시 사용자 친화 한국어 메시지를 일관되게 표시한다.
- 답변 하단 메타 영역(처리시간, 모델, 검증 주의문구)을 고정 형식으로 제공한다.

## 2. 범위 및 전제

- 범위: `/api/v1/qa` 응답
- 포함: 성공/경고/실패 응답에서 Citation, Error, Validation 표시용 필드
- 제외: BE1 문서-스키마 불일치 정렬 작업(별도 협의 트랙)

## 3. 최상위 응답 구조

최상위는 기존 API와 호환되는 아래 2가지로 고정한다.

- 성공/부분성공: `success = true`
- 실패: `success = false`

공통 권장 필드:

- `request_id`: 추적용 ID
- `timestamp`: 응답 시각(ISO 8601)

## 4. Citation UI 스펙

### 4.1 설계 원칙

- FE가 본문 중간에 노란 배지 `[출처 N]`를 삽입할 수 있어야 한다.
- HTML 인라인 삽입을 강제하지 않는다.
- 본문은 토큰 방식으로 전달하고, 실제 배지 렌더링은 FE가 담당한다.

### 4.2 본문 토큰 규칙 (권장)

본문 필드 `answer` 안에서 citation 위치를 아래 토큰으로 표기한다.

- 토큰 형식: `[[CITE:ref_id]]`
- 예: `[[CITE:1]]`, `[[CITE:2]]`

FE 동작 규칙:

1. `answer` 문자열을 렌더링 전 파싱
2. `[[CITE:n]]`을 `[출처 n]` 배지 컴포넌트로 교체
3. 호버 시 `citations` 배열의 동일 `ref_id` 항목 `snippet`을 툴팁으로 표시

### 4.3 citations 배열 규칙

필수 필드:

- `ref_id`: number, 본문 토큰과 연결되는 키
- `chunk_id`: string, 검색 청크 식별자
- `case_id`: string, 케이스 식별자
- `snippet`: string, 툴팁에 표시할 근거 문장

조건부 필수 필드:

- `doc_id`: retrieval 결과에 존재하면 필수, 미보유 파이프라인에서는 생략 가능

권장 필드:

- `start`, `end`: number, 원문 내 오프셋(가능 시)
- `source`: string, 출처 타입(예: retrieval)

제약:

- `ref_id`는 응답 내 유일해야 한다.
- `answer` 내 등장한 모든 토큰은 `citations.ref_id`와 1:1 매칭되어야 한다.
- `snippet`은 공백 문자열이면 안 된다.

### 4.4 Citation 포함 성공 응답 예시

```json
{
  "success": true,
  "request_id": "REQ-20260316-0001",
  "timestamp": "2026-03-16T14:20:00+09:00",
  "answer": "이륜차 전도 위험이 매우 높으므로 최우선 처리 요망. [[CITE:1]] 해당 구간은 과거에도 우천 후 파손 이력이 있으므로 조기 보강이 필요합니다. [[CITE:2]]",
  "citations": [
    {
      "ref_id": 1,
      "doc_id": "DOC-25-088",
      "chunk_id": "CHUNK-00044",
      "case_id": "CASE-2026-000123",
      "snippet": "이륜차 전도사고 발생 이력 참조"
    },
    {
      "ref_id": 2,
      "doc_id": "DOC-24-913",
      "chunk_id": "CHUNK-00045",
      "case_id": "CASE-2026-000123",
      "snippet": "우천 직후 노면 파손 재발 사례 확인"
    }
  ],
  "confidence": "medium",
  "limitations": "현장 실측 자료가 부족해 추가 확인이 필요합니다.",
  "meta": {
    "processing_time": 6.2,
    "model": "Qwen2.5-7B",
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

## 5. Error UI 스펙

### 5.1 목적

치명 오류 발생 시 FE 상단 중앙 배너에서 즉시 표시 가능한 형식을 고정한다.

### 5.2 실패 응답 구조

필수 필드:

- `success`: false
- `error.code`: 표준 오류 코드
- `error.message`: 사용자 친화 한국어 메시지

권장 필드:

- `error.retryable`: 재시도 가능 여부
- `request_id`: 추적 ID
- `timestamp`: 응답 시각
- `details`: 디버깅용 부가 정보

### 5.3 에러 코드/메시지 규칙

- `error.code`는 [be3_error_codes.md](be3_error_codes.md) 표준 코드를 사용한다.
- `error.message`는 FE에 그대로 표시 가능한 한국어 문장으로 제공한다.
- 내부 예외 원문/스택트레이스는 `message`에 노출하지 않는다.
- `JSON_PARSE_ERROR`는 신규 표준 코드로 사용하지 않고 `PARSE_*` 코드를 사용한다.

### 5.4 실패 응답 예시 (OOM)

```json
{
  "success": false,
  "request_id": "REQ-20260316-0002",
  "timestamp": "2026-03-16T14:21:00+09:00",
  "error": {
    "code": "OOM_DETECTED",
    "message": "메모리 용량 초과로 답변 생성이 중단되었습니다. 검색할 문서를 줄여서 다시 시도해주세요.",
    "retryable": true,
    "details": {
      "fallback_stage": "context_reduced",
      "last_error_code": "OOM_TOPK_REDUCED"
    }
  }
}
```

### 5.5 실패 응답 예시 (타임아웃)

```json
{
  "success": false,
  "request_id": "REQ-20260316-0003",
  "timestamp": "2026-03-16T14:22:00+09:00",
  "error": {
    "code": "MODEL_TIMEOUT",
    "message": "응답 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
    "retryable": true
  }
}
```

## 6. Validation UI 스펙

### 6.1 메타 영역 구조

답변 하단 회색 안내 영역을 위해 `meta` 객체를 아래와 같이 고정한다.

필수 필드:

- `processing_time`: number, 초 단위
- `model`: string, 사용 모델명
- `validation_warning`: string, 사용자 안내 문구

권장 필드:

- `generated_at`: string(datetime)
- `validator_version`: string

### 6.2 meta 예시

```json
{
  "meta": {
    "processing_time": 6.2,
    "model": "Qwen2.5-7B",
    "validation_warning": "본 답변은 로컬 AI가 작성한 초안이므로 실제 공문 발송 전 반드시 담당자의 검토가 필요합니다.",
    "generated_at": "2026-03-16T14:20:00+09:00",
    "validator_version": "be3-val-v0.1"
  }
}
```

### 6.3 qa_validation 연계

`meta.validation_warning`은 사용자 안내용 단문이고,
상세 검증 내역은 `qa_validation`으로 분리한다.

- `qa_validation.is_valid`: bool
- `qa_validation.errors`: 배열
- `qa_validation.warnings`: 배열

## 7. 상태별 최소 응답 매트릭스

| 상태 | 필수 필드 |
| --- | --- |
| success=true | success, request_id, timestamp, answer, citations, confidence, limitations, meta, qa_validation |
| success=false | success, request_id, timestamp, error.code, error.message, error.retryable |

## 8. FE 렌더링 규칙 요약

1. `success == false`이면 상단 중앙 배너에 `error.message` 표시
2. `success == true`이면 `answer`의 `[[CITE:n]]` 토큰을 `[출처 n]` 배지로 치환
3. 배지 hover 시 `citations.ref_id == n`의 `snippet` 표시
4. 답변 하단에 `meta.processing_time`, `meta.model`, `meta.validation_warning` 표시
5. `qa_validation.warnings`가 있으면 하단 경고 섹션에 추가 렌더링

## 9. BE2 연동 체크리스트

- answer 생성 시 citation 토큰(`[[CITE:n]]`) 삽입
- citations 배열에 `ref_id/chunk_id/case_id/snippet` 채움
- retrieval에 doc_id가 있으면 함께 채움
- 에러 시 표준 `error.code` + 한국어 `error.message` 반환
- meta 필수 3필드(processing_time/model/validation_warning) 채움
- qa_validation은 성공 응답에도 항상 포함

## 10. 주간 적용 기준 (Week 1)

이번 주 완료 기준:

- 단일 통합 스펙 문서 배포
- FE 시안 기준 Citation/Error/Validation 렌더링 가능 여부 확인
- BE2와 토큰/배열 매핑 규칙 합의

다음 주 확장:

- citation `start/end` 오프셋 정밀 매핑 고도화
- 다중 문단/줄바꿈 환경에서 토큰 파서 안정화
- 에러 메시지 다국어 대응(필요 시)

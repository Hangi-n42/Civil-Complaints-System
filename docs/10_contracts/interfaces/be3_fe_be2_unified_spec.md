# BE3-FE/BE2 단일 통합 응답 스펙 (Week 1)

문서 버전: v1.1-compromise  
작성일: 2026-03-18  
작성자: BE3 김현석 (BE2-BE3 절충안 반영)

## 1. 목적

`/api/v1/qa` 응답을 FE/BE2/BE3에서 동일 형식으로 처리하도록 고정한다.

핵심:
- Citation 배지 렌더링 단순화
- Error 배너 렌더링 표준화
- Validation/Meta 표시 일원화

## 2. 최상위 구조

- 성공: `success = true`
- 실패: `success = false`

공통 필드:
- `request_id`
- `timestamp`

추가 헤더:
- `X-Contract-Version: qa-v1.1`

## 3. 성공 응답 최소 계약

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

## 4. 실패 응답 최소 계약

```json
{
	"success": false,
	"request_id": "REQ-20260318-34EF56AA",
	"timestamp": "2026-03-18T18:30:01+09:00",
	"error": {
		"code": "PARSE_RETRY_EXHAUSTED",
		"message": "모델 응답을 JSON으로 파싱하지 못했습니다.",
		"retryable": true,
		"details": {
			"retry_count": 3,
			"stage": "decode"
		}
	}
}
```

## 5. Citation 규칙

본문 토큰:
- 형식: `[[CITE:ref_id]]`
- 예: `[[CITE:1]]`

citations 필수 필드:
- `ref_id` (number)
- `chunk_id` (string)
- `case_id` (string)
- `snippet` (string)

조건부 필수:
- `doc_id` (retrieval 결과가 보유한 경우)

권장:
- `relevance_score`
- `start`, `end`
- `source`

제약:
- `ref_id`는 응답 내 유일
- `answer`의 `[[CITE:n]]`와 `citations.ref_id`는 1:1 매칭

## 6. Error 규칙

실패 응답 필수:
- `success=false`
- `error.code`
- `error.message`
- `error.retryable`

표준 파싱 코드:
- `PARSE_JSON_DECODE_ERROR`
- `PARSE_JSON_BLOCK_EXTRACTION_FAILED`
- `PARSE_SCHEMA_MISMATCH`
- `PARSE_RETRY_EXHAUSTED`

## 7. Validation/Meta 규칙

`meta` 필수 3필드:
- `processing_time` (number)
- `model` (string)
- `validation_warning` (string)

`qa_validation` 성공 응답 필수:
- `is_valid` (bool)
- `errors` (array)
- `warnings` (array)

제약:
- Week 1에서는 `is_valid=false`인 성공 응답은 금지

## 8. FE 렌더링 기준

- `answer`의 `[[CITE:n]]`를 `[출처 n]` 배지로 렌더링
- 배지 hover 시 `citations.ref_id == n`의 snippet 표시
- `success=false`면 `error.message` 배너 표시
- `meta` 3필드와 `qa_validation.warnings` 표시

## 9. Week 1 체크리스트

- [x] FE Citation/Error/Validation 렌더링 필드 정의
- [x] BE2 토큰(`[[CITE:n]]`) + citations/ref_id 매핑 합의
- [x] PARSE_* 세분화 코드 반영
- [x] success/error 래퍼 구조 동기화
- [ ] FE 화면에서 실제 배지 렌더링 확인
- [ ] BE3 파서와 실응답 샘플 매칭 확인

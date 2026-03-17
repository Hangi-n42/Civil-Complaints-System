# BE3-FE/BE2 단일 통합 응답 스펙 (Week 1)

문서 버전: v0.1  
작성일: 2026-03-17  
작성자: BE3 김현석 (공유본 기반 정리)

## 1. 목적

`/api/v1/qa` 응답을 FE/BE2에서 동일 형식으로 처리하도록 고정한다.

핵심:
- Citation 배지 렌더링
- Error 배너 렌더링
- Validation 메타 표시

## 2. 최상위 구조

- 성공/부분성공: `status = "ok"`
- 실패: `status = "error"`

권장 공통 필드:
- `request_id`
- `timestamp`

## 3. Citation 규칙

본문 토큰:
- 형식: `[[CITE:ref_id]]`
- 예: `[[CITE:1]]`

citations 필수 필드:
- `ref_id` (number)
- `doc_id` (string)
- `chunk_id` (string)
- `case_id` (string)
- `snippet` (string)

권장 필드:
- `start`, `end`
- `source`

제약:
- `ref_id`는 응답 내 유일
- `answer` 내 토큰과 `citations.ref_id` 1:1 매칭

## 4. Error 규칙

실패 응답 필수:
- `status = "error"`
- `error_code`
- `message`

권장:
- `retryable`
- `request_id`
- `details`

## 5. Validation/Meta 규칙

`meta` 필수:
- `processing_time` (number, 초)
- `model` (string)
- `validation_warning` (string)

`qa_validation` 권장:
- `is_valid` (bool)
- `errors` (array)
- `warnings` (array)

## 6. 상태별 최소 응답

| 상태 | 필수 필드 |
| --- | --- |
| ok | status, answer, citations, confidence, limitations, meta |
| ok(경고) | status, answer, citations, confidence, limitations, meta, qa_validation.warnings |
| error | status, error_code, message |

## 7. Week 1 적용 체크리스트

- [x] FE Citation/Error/Validation 렌더링 필드 정의
- [x] BE2 토큰(`[[CITE:n]]`) + citations/ref_id 매핑 합의
- [x] 표준 error_code/message 구조 합의
- [ ] FE 화면에서 실제 배지 렌더링 확인
- [ ] BE3 파서와 실응답 샘플 매칭 확인

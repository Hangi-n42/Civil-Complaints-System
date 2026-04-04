# Week 4 FE 인터페이스 문서

문서 버전: v1.0-week4-draft  
작성일: 2026-04-05  
책임: FE  
협업: BE2, BE3

---

## 1) 책임 범위

Week 4에서 FE는 QA 화면의 **결과 표시 일관성**과 **오류 상태 UX**를 고정한다.

주요 작업:
1. answer/citation/limitations 표시 규격 구현
2. loading/error/empty 상태 표준화
3. 업로드->검색->QA 데모 동선 고정

---

## 2) 입력 계약

### 2.1 SearchResult 입력 (BE2)
- `request_id`, `results[]`, `total_found`, `elapsed_ms`

### 2.2 QAResponse 입력 (BE3)
- `data.answer`
- `data.citations[]`
- `data.confidence`
- `data.limitations`
- `data.latency_ms`

---

## 3) 화면 표시 계약

### 3.1 QA 카드 표시 필드
- 답변 본문: `answer`
- 신뢰도 뱃지: `confidence`
- 한계 문구: `limitations`
- 응답 시간: `latency_ms`

### 3.2 citation 패널 표시 필드
- `chunk_id`
- `case_id`
- `snippet`
- `confidence`

### 3.3 상태 UX
- loading: 스피너 + "답변 생성 중"
- empty: "검색 결과가 없어 답변을 생성할 수 없습니다"
- error: `error.code`별 사용자 메시지 매핑

---

## 4) 에러 메시지 매핑

| error.code | 사용자 메시지 |
| --- | --- |
| `INVALID_QA_REQUEST` | 요청 형식이 올바르지 않습니다. 입력값을 확인해주세요. |
| `QA_PARSE_ERROR` | 답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요. |
| `CITATION_MISMATCH` | 근거 매핑 검증에 실패했습니다. 관리자에게 문의해주세요. |
| `GENERATION_TIMEOUT` | 응답 시간이 초과되었습니다. 질문을 조금 더 구체화해 주세요. |

---

## 5) 데모 동선 계약

1. 업로드/구조화 결과 확인
2. 검색 실행 + 필터 적용
3. QA 질의 실행
4. answer/citation/limitations 확인

완료 기준:
- 3개 시나리오(도로안전/소음/환경) 모두 동일 UX로 재현 가능

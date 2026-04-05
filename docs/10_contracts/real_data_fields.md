# 실데이터 필드 목록 (FE/BE 공유용)

작성일: 2026-04-06  
목적: 현재 Streamlit UI가 mock/하드코딩으로 채우는 값을, 실제 DB/BE 응답으로 대체하기 위해 **사이트에 들어가야 하는 데이터 필드**를 고정한다.

근거 소스:
- 구조화 원천 스키마: `schemas/civil_case.schema.json`
- 검색/인덱싱 API 스키마: `app/api/schemas/retrieval.py`
- QA API 스키마: `app/api/schemas/generation.py`
- 라우터 실제 응답 형태: `app/api/routers/retrieval.py`, `app/api/routers/generation.py`
- 공통 에러 응답: `app/api/error_utils.py`
- UI에서 참조하는 case/search/qa 필드: `app/ui/Home.py`, `app/ui/services/search_service.py`, `app/ui/components/search_ui.py`

---

## 0) 공통 규칙

- 시간 필드(`created_at`, `timestamp`, `structured_at` 등)는 ISO-8601을 권장하며, 가능하면 KST(+09:00)를 포함한다.
- 문자열은 비어있을 수 있으나, UX/계약상 의미가 있는 필드(`query`, `limitations`)는 빈 문자열을 피한다.

---

## 1) 민원(Case) 기본 레코드 (큐/선택 화면)

### 1.1 필수(권장 최소)

- `case_id`: string — 민원 고유 식별자
- `source`: string — 수집 출처/기관
- `created_at`: string — 민원 생성 시점
- `raw_text`: string — 민원 원문 텍스트
- `category`: string — 카테고리(검색 필터/제목 생성에 사용)
- `region`: string — 지역(검색 필터/표시에 사용)

### 1.2 UI 표시/업무 필드(선택이지만 있으면 좋음)

- `title`: string — 비어있으면 FE에서 `build_case_title()`로 생성
- `assignee`: string — 담당자
- `priority`: string — 우선순위(예: `매우급함|급함|보통`)
- `status`: string — 상태(예: `미처리|검토중|보류|처리완료`)
- 부서(택1): `admin_unit` 또는 `department` 또는 `dept`: string

---

## 2) 구조화 결과(4요소 + 엔티티 + 검증)

### 2.1 4요소 필드(필수)

- `observation`, `result`, `request`, `context`: 각각 아래 형태
  - `text`: string
  - `confidence`: number (0~1)
  - `evidence_span`: [start:int, end:int]  

### 2.2 엔티티(필수)

- `entities[]`: array
  - `label`: enum `LOCATION|TIME|FACILITY|HAZARD|ADMIN_UNIT`
  - `text`: string

### 2.3 검증/메타(선택)

- `structured_at`: string(date-time)
- `validation`: object
  - `is_valid`: bool
  - `errors[]`: string array

---

## 3) 검색 API (/api/v1/search)

### 3.1 요청(SearchRequest)

- `request_id`: string (선택)
- `query`: string (필수)
- `top_k`: int (기본 5)
- `filters`: object (선택)
  - `region`: string
  - `category`: string
  - `date_from`: string (ISO-8601)
  - `date_to`: string (ISO-8601)
  - `entity_labels[]`: string array (허용 라벨만)
- `collection_name`: string (기본 `civil_cases_v1`)

### 3.2 응답(SearchResponse)

- 공통: `success`, `request_id`, `timestamp`, `data`
- `data.results[]` 각 결과(표준 필드)
  - `rank`: int
  - `case_id`: string
  - `similarity_score`: float (0~1)
  - `content`: object
    - `observation`, `result`, `request`, `context`: string
  - `metadata`: object
    - `created_at`: string
    - `category`: string
    - `region`: string
    - `entity_labels[]`: string array

- 호환/표시 보강 필드(현재 UI가 방어적으로 지원)
  - `doc_id`: string?
  - `score`: float?
  - `chunk_id`: string?
  - `title`: string?
  - `snippet`: string?
  - `summary`: object? (`observation`, `request`)

---

## 4) QA API (/api/v1/qa)

### 4.1 요청(QARequest)

- `query`: string (필수)
- `top_k`: int
- `filters`: SearchFilters (선택)
- `use_search_results`: bool
- `search_results[]`: (선택) 검색 결과를 그대로 QA 입력으로 재사용할 때
  - `chunk_id`: string
  - `case_id`: string
  - `snippet`: string
  - `score`: float
  - `doc_id`: string? (선택)
- `context_window_policy`: object? (선택)

### 4.2 응답(QAResponse) (서버 구현 기준: 플랫)

- `success`: true
- `request_id`: string
- `timestamp`: string
- `answer`: string
- `citations[]`: array
  - `ref_id`: int
  - `chunk_id`: string
  - `case_id`: string
  - `snippet`: string
  - `relevance_score`: float?
  - `start`, `end`: int?
  - `source`: string? (기본 `retrieval`)
  - `doc_id`: string?
- `confidence`: `low|medium|high`
- `limitations`: string
- `meta`: object
  - `processing_time`: float
  - `model`: string
  - `validation_warning`: string
  - `generated_at`: string?
  - `validator_version`: string?
- `qa_validation`: object
  - `is_valid`: bool
  - `errors[]`: `{code, message}`
  - `warnings[]`: `{code, message}`
- `search_trace`: object
  - `used_top_k`: int
  - `retrieved_count`: int
  - `context_budget_chars`, `context_used_chars`: int?
  - `context_truncated_count`, `context_dropped_count`: int?

### 4.3 실패 응답(공통 에러)

- `success`: false
- `request_id`: string
- `timestamp`: string
- `error`: object
  - `code`: string
  - `message`: string
  - `retryable`: bool
  - `details`: object? (선택)

---

## 5) 저장/최신화 시 체크 포인트

- UI가 사용 중인 필드: `case_id`, `received_at/created_at`, `category`, `region`, `raw_text`, `structured.*`, `entities[]`, `search_results[]`, `citations[]`, `limitations`
- 계약 변경 시 우선 확인할 파일:
  - API 스키마: `app/api/schemas/retrieval.py`, `app/api/schemas/generation.py`
  - UI 정규화: `app/ui/services/search_service.py`
  - 상태/표시: `app/ui/components/search_ui.py`, `app/ui/Home.py`

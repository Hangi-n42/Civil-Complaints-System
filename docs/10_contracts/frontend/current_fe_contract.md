# 현재 FE-BE 계약

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `frontend/lib/api.ts`
  - `frontend/app/page.tsx`
  - `frontend/app/workbench/page.tsx`
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
- 관련 문서:
  - `docs/60_specs/ui_workbench_spec.md`
  - `docs/10_contracts/api/current_api_contract.md`

## 기본 API base

`frontend/lib/api.ts`는 `NEXT_PUBLIC_API_BASE_URL`을 우선 사용하고, 없으면 `http://127.0.0.1:8001`을 기본값으로 사용합니다.

확인 필요:

- 로컬 backend를 8000으로 실행하는 환경에서는 `.env.local` 또는 실행 설정으로 FE API base를 맞춰야 합니다.

## Workbench Search 흐름

FE 함수:

- `searchCasesApi`

Backend endpoint:

- `POST /api/v1/search`

FE 요청 필드:

- `complaintId`
- `query`
- `topK`
- `filters`
- `caseContext`

FE가 기대하는 응답:

- `query`
- `retrievedDocs`
- `results`
- `searchResults`
- `routingTrace`
- `routingHint`
- `strategyId`
- `routeKey`

Backend snake_case 응답은 `frontend/lib/api.ts`에서 camelCase 형태로 매핑됩니다.

## Workbench QA 흐름

FE 함수:

- `runQaApi`

Backend endpoint:

- `POST /api/v1/qa`

FE 요청 필드:

- `complaintId`
- `query`
- `routingHint`
- `routingTrace`
- `searchResults`

FE가 기대하는 응답:

- `answer`
- `citations`
- `limitations`
- `structuredOutput`
  - `summary`
  - `actionItems`
  - `requestSegments`
  - `segmentAnswers`

## Mock fallback

`frontend/lib/api.ts`는 일부 API 실패 시 빈 데이터 또는 mock 데이터를 반환합니다. 이 fallback은 화면 붕괴 방지용이며, 실제 BE 계약을 대체하지 않습니다.

## 문서화 원칙

- 현재 외부 계약은 `/api/v1/search`, `/api/v1/qa`, `/complaint-intelligence/...`를 기준으로 봅니다.
- 과거 `web/`, Streamlit, old `/search` 표현은 historical 자료에서만 사용합니다.

# 현재 API 계약

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `app/api/schemas/retrieval.py`
  - `app/api/schemas/generation.py`
- 관련 문서:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/10_contracts/data/current_data_contract.md`
  - `docs/10_contracts/frontend/intelligence_fe_contract.md`

## 공통 응답 envelope

대부분의 FastAPI 응답은 다음 형태를 사용합니다.

```json
{
  "success": true,
  "request_id": "...",
  "timestamp": "...",
  "data": {}
}
```

오류 응답은 endpoint별로 FastAPI validation error 또는 공통 error response를 사용할 수 있습니다. Duplicate Merge 상태 전이 충돌은 `409`와 함께 `DUPLICATE_GROUP_*` 계열 code를 반환합니다.

## Search/QA

### `POST /api/v1/search`

역할: 민원 query를 분석하고 adaptive retrieval 결과를 반환합니다.

요청 주요 필드:

- `request_id`: 선택
- `complaint_id`: 선택
- `query`: 필수 문자열
- `top_k`: 기본 5
- `filters`: 선택. region/category 등
- `query_signals`: 선택
- `collection_name`: 기본 `DEFAULT_CHROMA_COLLECTION`

응답 `data` 주요 필드:

- `complaint_id`
- `strategy_id`
- `route_key`
- `routing_hint`
- `routing_trace`
- `retrieved_docs`
- `results`, `items`: 후방 호환 목록
- `total_found`
- `result_count`
- `elapsed_ms`
- `retrieval_latency_ms`

### `POST /api/v1/qa`

역할: query와 검색 결과 또는 자체 검색을 바탕으로 답변 초안을 생성합니다.

요청 주요 필드:

- `request_id`: 선택
- `complaint_id`: 선택
- `query`: 필수
- `routing_hint`: 선택
- `routing_trace`: 선택
- `top_k`: 기본 5
- `filters`: 선택
- `query_signals`: 선택
- `use_search_results`: 기본 false
- `search_results`: `use_search_results=true`일 때 최소 1건 필요
- `context_window_policy`: 선택

응답 `data` 주요 필드:

- `complaint_id`
- `strategy_id`
- `route_key`
- `routing_trace`
- `structured_output`
- `answer`
- `citations`
- `legal_citations`
- `legal_citation_warnings`
- `limitations`
- `latency_ms`
- `quality_signals`
- `generation_metadata`

### `POST /api/v1/qa/stream`

역할: `/api/v1/qa`와 같은 요청을 받고 SSE로 stage/done event를 반환합니다.

대표 event:

- `stage`: retrieving, grounding, generating 등
- `done`: 최종 QAResponse envelope
- `error`: 실패 envelope

## Complaint Intelligence

Complaint Intelligence endpoint는 `/api/v1` prefix를 사용하지 않습니다.

### `POST /complaint-intelligence/run-analysis`

역할: 입력 민원 events를 분석해 IssueAlert와 PublicAgencyInsight를 저장하고 결과를 반환합니다.

요청:

- `request_id`: 선택
- `events`: `ComplaintIntelligenceEvent[]`
- `mode`: 선택. `realtime`, `replay`, `manual` 중 하나로 정규화
- `source_name`: 선택
- `as_of`: 선택

응답 `data`:

- `run_id`
- `mode`
- `source_name`
- `as_of`
- `latest_event_at`
- `event_count`
- `alert_count`
- `public_insight_count`
- `alerts`
- `public_insights`

### `POST /complaint-intelligence/public-insights/run-analysis`

역할: 현재 코드에서는 `run-analysis`와 같은 분석 실행 경로의 호환 endpoint입니다.

### `GET /complaint-intelligence/analysis-runs`

역할: 최근 분석 실행 이력을 조회합니다.

query:

- `limit`: 기본 20, 최대값은 코드에서 제한

응답 `data`:

- `count`
- `analysis_runs[]`: `run_id`, `mode`, `status`, `source_name`, `event_count`, `started_at`, `completed_at`, `as_of`, `metadata`

### Scheduler/Collector

- `GET /complaint-intelligence/scheduler/status`
- `POST /complaint-intelligence/scheduler/run-once`
- `GET /complaint-intelligence/collector/status`
- `POST /complaint-intelligence/collector/poll-once`

이 endpoint들은 운영/개발 확인용입니다. FE 기본 화면은 dashboard read-model을 조회합니다.

### `GET /complaint-intelligence/dashboard`

역할: FE Intelligence dashboard가 바로 표시할 수 있는 read-model을 반환합니다.

query:

- `status`: 선택
- `type`: 선택. PublicInsightType alias

응답 `data`:

- `summary`
- `tabs`
- `issue_alerts`
- `public_insights`
- `empty_state`

### `POST /complaint-intelligence/dashboard/run-analysis`

역할: 입력 events로 분석을 실행하고 응답은 `GET /dashboard`와 같은 형태로 반환합니다.

## IssueAlert/PublicAgencyInsight 조회

### `GET /complaint-intelligence/issue-alerts`

query:

- `status`: 선택

응답 `data`:

- `count`
- `alerts[]`

### `GET /complaint-intelligence/public-insights`

query:

- `status`: 선택
- `type`: 선택

응답 `data`:

- `count`
- `public_insights[]`

### `GET /complaint-intelligence/public-insights/llm-observability`

query:

- `limit`: 기본 100
- `provider`: 선택
- `model`: 선택

응답 `data`:

- `runs_analyzed`
- `report`

### `GET /complaint-intelligence/public-insights/{insight_id}`

응답은 `PublicAgencyInsight` 모델을 envelope 없이 직접 반환합니다.

### `GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack`

응답은 `PublicInsightEvidencePack` 모델을 envelope 없이 직접 반환합니다. EvidencePack은 관리자/검증용이며 raw PII를 포함하지 않아야 합니다.

## Duplicate Merge Recommendation

### `POST /complaint-intelligence/duplicate-groups/run-analysis`

역할: 입력 events에서 유사 민원 그룹 후보를 생성하고 저장합니다.

요청은 `RunAnalysisRequest`와 동일합니다.

응답 `data`:

- `event_count`
- `count`
- `duplicate_groups[]`

### `GET /complaint-intelligence/duplicate-groups`

query:

- `status`: `candidate`, `confirmed`, `split`, `rejected`
- `complaint_id`: 선택
- `issue_alert_id`: 선택
- `public_insight_id`: 선택

응답 `data`:

- `event_count`: run-analysis 응답에서만 주로 사용
- `count`
- `duplicate_groups[]`

### `GET /complaint-intelligence/duplicate-groups/{merge_id}`

응답 `data`:

- `duplicate_group`

### `POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm`

candidate 상태의 그룹을 confirmed로 전환합니다.

제약:

- status가 candidate가 아니면 409
- blocker risk가 있으면 409

### `POST /complaint-intelligence/duplicate-groups/{merge_id}/split`

candidate 또는 confirmed 그룹을 split으로 전환합니다.

### `POST /complaint-intelligence/duplicate-groups/{merge_id}/reject`

candidate 그룹을 rejected로 전환합니다.

### `POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply`

confirmed 그룹에서만 BE3 전달용 `DraftReplyPayload`를 생성합니다.

제약:

- confirmed가 아니면 409
- 필요한 member event가 없으면 409
- 이 endpoint는 실제 답변 초안이 아니라 payload 생성입니다.

### `POST /complaint-intelligence/duplicate-groups/{merge_id}/reply-draft`

confirmed 그룹에서만 실제 답변 초안을 생성합니다.

응답 `data`:

- `reply_draft`
  - `answer`
  - `citations`
  - `limitations`
  - `structured_output`
  - `generation_metadata`
  - `safety_warnings`
  - `draft_reply_payload`

확인 필요:

- 운영에서 `reply-draft`를 FE 기본 action으로 노출할지, 담당자 검증용 기능으로 제한할지는 제품 정책 확인이 필요합니다.

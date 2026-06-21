# Intelligence Dashboard FE 계약

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `frontend/app/intelligence/page.tsx`
  - `frontend/lib/api.ts`
  - `frontend/components/intelligence/`
  - `app/api/routers/complaint_intelligence.py`
- 관련 문서:
  - `docs/50_issues/complaint_intelligence_fe_handoff.md`
  - `docs/50_issues/duplicate_merge_recommendation_fe_handoff.md`
  - `docs/50_issues/duplicate_merge_reply_draft_fe_handoff.md`

## 기본 원칙

Intelligence 화면은 실시간 LLM 생성 대기 화면이 아니라, backend repository에 저장된 관제 read-model을 조회하는 화면입니다.

FE는 다음 두 축을 함께 표시합니다.

- 민원 핫스팟/이슈 자동감지: IssueAlert
- 행정 개선 인사이트: PublicAgencyInsight
- 중복 병합 추천: DuplicateMergeRecord

## Dashboard 조회

FE 함수:

- `fetchIntelDashboardApi`

Backend endpoint:

- `GET /complaint-intelligence/dashboard`

query:

- `status`
- `type`

응답 `data.summary` 주요 필드:

- `as_of`
- `latest_event_at`
- `event_count`
- `alert_count`
- `active_alert_count`
- `critical_alert_count`
- `public_insight_count`
- `high_priority_insight_count`
- `human_review_required_count`
- `linked_alert_count`

응답 `data.issue_alerts[]` 주요 필드:

- `id`
- `status`
- `severity`
- `severity_label`
- `color`
- `title`
- `summary`
- `topic`
- `region`
- `center`
- `radius`
- `recent_count`
- `baseline`
- `surge_ratio`
- `confidence`
- `keywords`
- `representative_complaint_ids`
- `linked_insight_ids`
- `map_focus`
- `first_seen`
- `last_seen`

응답 `data.public_insights[]` 주요 필드:

- `id`
- `type`
- `type_label`
- `status`
- `priority`
- `priority_label`
- `color`
- `title`
- `summary`
- `problem_diagnosis`
- `topic`
- `target_area`
- `affected_count`
- `affected_region`
- `related_department`
- `window_start`
- `window_end`
- `confidence`
- `grounding_score`
- `requires_human_review`
- `linked_alert_ids`
- `representative_evidence_ids`
- `top_aspects`
- `citizen_requests`
- `recommended_actions`
- `uncertainty`
- `metrics`

## Dashboard 분석 실행

FE 함수:

- `runIntelAnalysisApi`

Backend endpoint:

- `POST /complaint-intelligence/dashboard/run-analysis`

요청:

- `request_id`
- `events[]`
  - `id`
  - `received_at`
  - `body`
  - `region`
  - `final_department`
  - `status`
  - `structured_elements`

응답은 `GET /dashboard`와 같은 `IntelDashboardData` 형태입니다.

## EvidencePack 조회

FE 함수:

- `fetchEvidencePackApi`

Backend endpoint:

- `GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack`

주의:

- EvidencePack은 관리자/검증용입니다.
- `representative_complaints[*].masked_text` preview만 표시합니다.
- raw body나 상세 주소/전화번호는 노출하지 않습니다.

## Duplicate Groups 조회

FE 함수:

- `fetchDuplicateGroupsApi`

Backend endpoint:

- `GET /complaint-intelligence/duplicate-groups`

query:

- `status`
- `complaint_id`
- `issue_alert_id`
- `public_insight_id`

응답:

- `count`
- `duplicate_groups[]`

## Duplicate Group action

FE 함수:

- `transitionDuplicateGroupApi`

Backend endpoint:

- `POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/split`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/reject`

FE는 반드시 `allowed_actions`와 `blocked_actions`를 기준으로 버튼을 노출해야 합니다.

상태별 기본 계약:

- candidate: confirm/split/reject 가능. 단 blocker가 있으면 confirm 차단
- confirmed: split/draft_reply 가능
- split/rejected: action 없음

## Draft reply payload

FE 함수:

- `fetchDuplicateDraftReplyApi`

Backend endpoint:

- `POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply`

계약:

- confirmed 그룹에서만 허용
- payload 생성 endpoint이며 실제 답변 초안 endpoint와 구분합니다.
- candidate, split, rejected에서 호출하면 409가 올 수 있습니다.

## Reply draft

최신 backend에는 다음 endpoint가 있습니다.

- `POST /complaint-intelligence/duplicate-groups/{merge_id}/reply-draft`

역할:

- confirmed 그룹에서 실제 답변 초안을 생성합니다.
- `answer`, `citations`, `limitations`, `structured_output`, `generation_metadata`, `safety_warnings`를 포함합니다.

확인 필요:

- 현재 FE 기본 API helper는 `draft-reply` payload를 중심으로 사용합니다. `reply-draft`를 화면 action으로 노출할지는 제품/FE 정책 확인이 필요합니다.

## Empty/loading/error 상태

FE는 backend 실패 시 빈 dashboard나 빈 duplicate groups를 표시할 수 있습니다. 이 경우 사용자는 분석이 없는 상태와 API 실패 상태를 구분할 수 있어야 합니다.

권장 표시:

- loading: read-model 조회 중
- empty: 저장된 관제 결과 없음
- error: 일부 카드 조회 실패, 기존 관제 정보는 유지

## PII 표시 금지

- 민원 원문 raw body를 화면에 표시하지 않습니다.
- EvidencePack은 masked preview만 표시합니다.
- draft reply payload도 PII-safe summary 중심으로 표시합니다.

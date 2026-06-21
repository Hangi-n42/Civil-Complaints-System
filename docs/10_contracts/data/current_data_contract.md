# 현재 데이터 계약

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/schemas/retrieval.py`
  - `app/api/schemas/generation.py`
  - `app/complaint_intelligence/schemas.py`
  - `app/complaint_intelligence/public_insights/evidence_pack.py`
  - `app/complaint_intelligence/duplicate_merger/schemas.py`
- 관련 문서:
  - `docs/60_specs/data_schema_spec.md`
  - `docs/20_domains/complaint_intelligence/pii_safety_policy.md`

## Search/QA response wrapper

Search/QA API는 기본적으로 다음 envelope를 사용합니다.

- `success`
- `request_id`
- `timestamp`
- `data`
- 실패 시 `error`

`/api/v1/qa`는 추가로 `meta`, `qa_validation`, `search_trace`, `citation_validation`을 포함할 수 있습니다.

## SearchResultItem

검색 결과의 주요 필드:

- `rank`
- `case_id`
- `doc_id`
- `chunk_id`
- `snippet`
- `summary`
  - `observation`
  - `request`
- `content`
  - `observation`
  - `request`
  - `result`
  - `context`
- `metadata`
  - `created_at`
  - `category`
  - `region`
  - `entity_labels`
  - `entity_texts`
  - `legal_ref_names`
  - `legal_ref_ids`
  - `responsible_units`
  - `civil_category_primary`
  - `urgency_level`
  - `strategy_id`
  - `route_key`
  - `topic_type`
  - `complexity_level`
  - `retrieval_policy`
  - `matched_segments`
- `score`
- `similarity_score`
- `answers_by_admin_unit`
- `department_answers`

## ComplaintIntelligenceEvent

Complaint Intelligence 분석 입력 단위입니다.

주요 필드:

- `id`
- `received_at`
- `title`
- `body`
- `masked_text`
- `predicted_category`
- `final_category`
- `predicted_department`
- `final_department`
- `region`
- `latitude`
- `longitude`
- `status`
- `handling_time_minutes`
- `reopened`
- `escalated`
- `user_feedback_score`
- `reviewer_feedback`
- `structured_elements`
  - `observation`
  - `result`
  - `request`
  - `context`
- `request_segments`
- `responsible_unit`
- `civil_category`
- `entity_texts`
- `urgency`
- `risk_level`
- `pii_status`
- `pii_detected`
- `pii_labels`

PII 원칙:

- `body`, `masked_text`, `reviewer_feedback`, `structured_elements`, `request_segments`, `entity_texts`는 validator에서 마스킹됩니다.
- PublicAgencyInsight와 EvidencePack에는 masked text만 전달해야 합니다.

## IssueAlert

핫스팟/이슈 자동 감지 결과입니다.

주요 필드:

- `id`
- `status`: `ACTIVE`, `UPDATED`, `RESOLVED`
- `severity`: `WATCH`, `WARNING`, `CRITICAL`
- `trigger_type`: 선택. `SURGE_HOTSPOT`, `OPERATIONAL_BACKLOG`, `REOPEN_REPEAT`, `SERVICE_ACCESSIBILITY_PATTERN`, `SERVICE_UX_PATTERN`
- `title`
- `summary`
- `topic`
- `keywords`
- `region`
- `center`
- `radius`
- `recent_count`
- `baseline`
- `surge_ratio`
- `first_seen`
- `last_seen`
- `representative_complaints`
- `related_ids`
- `confidence`
- `explanation`
- `linked_insight_ids`

## PublicAgencyInsight

공공기관 담당자용 행정 조치 인사이트입니다.

주요 필드:

- `insight_id`
- `id`: 호환 필드
- `type`
- `status`: `open`, `acknowledged`, `resolved`, `dismissed`
- `priority`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `title`
- `summary`
- `problem_diagnosis`
- `topic`
- `target_area`
- `affected_region`
- `related_department`
- `affected_count`
- `window_start`
- `window_end`
- `metrics`
- `extracted_aspects`
- `citizen_requests`
- `root_cause_hypotheses`
- `evidence`
- `representative_complaint_ids`
- `linked_alert_ids`
- `recommended_actions`
- `recommended_action_texts`
- `expected_impact`
- `uncertainty`
- `requires_human_review`
- `confidence`
- `grounding_score`
- `created_at`
- `updated_at`
- `explanation`

중요 원칙:

- 인사이트는 AI/RAG/prompt 개선 제안이 아니라 공공기관 행정 조치 제안입니다.
- `recommended_actions[*].supporting_evidence_ids`는 EvidencePack의 evidence id와 연결되어야 합니다.
- 정책, 안전, 단속, 재민원, 병목 유형은 human review가 필요할 수 있습니다.

## EvidencePack

LLM에 전달되는 유일한 근거 입력입니다.

주요 필드:

- `candidate_id`
- `type_hint`
- `topic_label`
- `region_summary`
- `department_summary`
- `window_start`
- `window_end`
- `complaint_count`
- `baseline_count`
- `trend_metrics`
- `operational_metrics`
- `representative_complaints`
- `key_phrases`
- `extracted_aspects`
- `citizen_requests`
- `linked_alert_ids`
- `allowed_action_catalog`
- `valid_evidence_ids`
- `allowed_action_types`
- `preferred_action_types`

EvidencePack은 raw complaint body를 포함하면 안 됩니다.

## DuplicateMergeRecord

중복 병합 추천 read-model입니다.

주요 필드:

- `merge_id`
- `status`: `candidate`, `confirmed`, `split`, `rejected`
- `representative_complaint_id`
- `member_complaint_ids`
- `confidence`
- `recommendation_level`: `weak`, `review`, `strong`
- `recommended_decision`: 현재 `REVIEW_BEFORE_MERGE`
- `evidence`
- `risk_flags`
- `allowed_actions`
- `blocked_actions`
- `linked_issue_alert_ids`
- `linked_public_insight_ids`
- `representative`
- `score_breakdown`
- `location_state`
- `request_types`
- `created_at`
- `updated_at`

## DuplicateRiskFlag

담당자 검토가 필요한 위험 신호입니다.

주요 필드:

- `code`
- `severity`: `info`, `warning`, `blocker`
- `message`
- `affected_case_ids`
- `evidence`

대표 code:

- `LOCATION_MISMATCH`
- `LOCATION_AMBIGUOUS`
- `REQUEST_TYPE_MISMATCH`
- `DEPARTMENT_MISMATCH`
- `SAFETY_AND_INCONVENIENCE_MIXED`
- `LEGAL_RIGHTS_OR_DEADLINE_RISK`
- `PII_RISK`
- `MULTI_INTENT_SEGMENTS`
- `SEMANTIC_ONLY_MATCH`
- `LOW_EVIDENCE`
- `TIME_WINDOW_TOO_WIDE`

## DuplicateEvidence

병합 후보의 근거입니다.

- `type`
- `message`
- `affected_case_ids`
- `value`
- `details`

## allowed_actions / blocked_actions

상태별 FE action gate입니다.

- `candidate`
  - blocker 없음: `confirm`, `split`, `reject`
  - blocker 있음: `split`, `reject`
  - `draft_reply`는 차단
- `confirmed`
  - 허용: `split`, `draft_reply`
  - 차단: `confirm`, `reject`
- `split`, `rejected`
  - 모든 action 차단

## DraftReplyPayload

confirmed 그룹에서만 생성되는 BE3 전달용 payload입니다.

주요 필드:

- `merge_id`
- `representative_complaint_id`
- `member_complaint_ids`
- `representative`
- `members`
- `merge_evidence`
- `risk_flags`
- `system_instruction`
- `common_reply_constraints`
- `prohibited_content_rules`

`draft-reply`는 confirmed에서만 허용됩니다. candidate 상태에서 요청하면 409가 반환됩니다.

## DuplicateReplyDraft

confirmed 그룹에서 실제 답변 초안을 생성한 결과입니다.

주요 필드:

- `merge_id`
- `representative_complaint_id`
- `member_complaint_ids`
- `requires_human_review`
- `answer`
- `citations`
- `limitations`
- `structured_output`
- `generation_metadata`
- `safety_warnings`
- `query`
- `routing_hint`
- `routing_trace`
- `search_results`
- `draft_reply_payload`

## 상태 계약 요약

| 상태 | 의미 | 허용 action | 주의 |
| --- | --- | --- | --- |
| `candidate` | 병합 후보 | confirm/split/reject, 단 blocker 있으면 confirm 차단 | 실제 민원 상태 변경 아님 |
| `confirmed` | 담당자가 후보를 확인한 내부 상태 | split/draft_reply | 자동 발송 아님 |
| `split` | 병합하지 않기로 분리 | 없음 | read-model 상태 |
| `rejected` | 후보를 기각 | 없음 | read-model 상태 |

## PII-safe 원칙

- FE/API 문서에 raw body 표시를 권장하지 않습니다.
- EvidencePack과 draft reply payload는 PII-safe summary와 structured elements 중심으로 구성해야 합니다.
- raw response, prompt dump, checkpoint는 PR에 포함하지 않는 것이 원칙입니다.

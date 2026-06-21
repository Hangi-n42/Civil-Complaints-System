# Duplicate Merge Demo Flow

- 문서 상태: runbook
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `scripts/seed_duplicate_merge_demo.py`
  - `app/complaint_intelligence/duplicate_merger/`
  - `app/api/routers/complaint_intelligence.py`
  - `frontend/components/intelligence/DuplicateGroupTriage.tsx`
- 관련 문서:
  - `docs/20_domains/complaint_intelligence/duplicate_merge_policy.md`
  - `docs/10_contracts/frontend/intelligence_fe_contract.md`
  - `docs/50_issues/duplicate_merge_reply_draft_fe_handoff.md`

## 목적

중복 민원 후보를 생성하고 FE Intelligence dashboard에서 담당자가 확인할 수 있는 상태로 만듭니다.

## Seed

대표 seed:

- `data/complaint_intelligence/duplicate_merge_demo_events.json`

seed 실행:

```powershell
civil\Scripts\python.exe scripts\seed_duplicate_merge_demo.py
```

## API 흐름

1. 후보 생성

```http
POST /complaint-intelligence/duplicate-groups/run-analysis
```

2. 목록 조회

```http
GET /complaint-intelligence/duplicate-groups
GET /complaint-intelligence/duplicate-groups?status=candidate
```

3. 단건 조회

```http
GET /complaint-intelligence/duplicate-groups/{merge_id}
```

4. 담당자 action

```http
POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm
POST /complaint-intelligence/duplicate-groups/{merge_id}/split
POST /complaint-intelligence/duplicate-groups/{merge_id}/reject
```

5. confirmed 그룹의 답변 초안 payload

```http
POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply
```

6. confirmed 그룹의 실제 답변 초안

```http
POST /complaint-intelligence/duplicate-groups/{merge_id}/reply-draft
```

## 상태 전이

```text
candidate
  ├─ confirm -> confirmed
  ├─ split -> split
  └─ reject -> rejected

confirmed
  ├─ split -> split
  ├─ draft-reply 허용
  └─ reply-draft 허용
```

blocker risk가 있는 candidate는 confirm이 차단됩니다.

## FE 확인

`/intelligence` 화면의 “중복 병합” 탭에서 확인합니다.

FE는 다음 필드를 우선 사용합니다.

- `status`
- `confidence`
- `recommendation_level`
- `evidence`
- `risk_flags`
- `allowed_actions`
- `blocked_actions`
- `linked_issue_alert_ids`
- `linked_public_insight_ids`

## 주의사항

- candidate는 실제 병합이 아닙니다.
- confirmed도 자동 발송이 아닙니다.
- draft reply는 confirmed에서만 허용됩니다.
- blocker risk가 있으면 자동 병합을 허용하지 않습니다.
- raw body를 화면에 표시하지 않습니다.

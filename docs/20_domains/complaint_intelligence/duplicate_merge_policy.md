# Duplicate Merge Recommendation 정책

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/complaint_intelligence/duplicate_merger/candidate_generator.py`
  - `app/complaint_intelligence/duplicate_merger/scoring.py`
  - `app/complaint_intelligence/duplicate_merger/merge_verifier.py`
  - `app/complaint_intelligence/duplicate_merger/draft_payload.py`
  - `app/complaint_intelligence/duplicate_merger/reply_context.py`
  - `app/complaint_intelligence/duplicate_merger/reply_safety.py`
  - `app/complaint_intelligence/duplicate_merger/schemas.py`
- 관련 문서:
  - `docs/10_contracts/data/current_data_contract.md`
  - `docs/10_contracts/frontend/intelligence_fe_contract.md`

## 목적

Duplicate Merge Recommendation Layer는 의미와 위치가 유사한 민원을 담당자가 함께 검토할 수 있도록 후보 그룹으로 제안합니다.

중요:

- candidate는 실제 민원 병합이 아닙니다.
- confirmed도 자동 발송이나 외부 민원 상태 변경이 아닙니다.
- 담당자 검토와 action gate를 위한 read-model입니다.

## 생성 흐름

```text
ComplaintIntelligenceEvent[]
  -> pair scoring
  -> location state 검증
  -> request type 분류
  -> MergeVerifier risk flag
  -> representative 선택
  -> DuplicateMergeRecord(candidate)
```

## scoring과 hard gate

scoring은 유사도를 계산합니다.

- semantic similarity
- entity/location overlap
- request type
- time window
- structured elements

hard gate는 자동 병합을 막아야 하는 위험을 판단합니다.

- 위치 충돌
- 요청 유형 불일치
- 안전/긴급 위험
- 법적 권리/기한 위험
- PII 위험
- 근거 부족

위험하다고 항상 group 생성을 막는 것은 아닙니다. 같은 위치/시설/주제에서 안전 이슈와 절차 문의가 함께 들어오면 후보는 보여주되 blocker로 confirm/draft reply를 막는 방향이 우선입니다.

## risk_flags

`risk_flags`는 담당자가 병합 전 확인해야 하는 경고입니다.

- `info`: 참고
- `warning`: 주의
- `blocker`: 자동 confirm 또는 draft reply 차단

## allowed_actions / blocked_actions

FE는 버튼 노출을 status만으로 판단하지 말고 반드시 `allowed_actions`, `blocked_actions`를 사용해야 합니다.

- candidate + blocker 없음: confirm/split/reject
- candidate + blocker 있음: split/reject
- confirmed: split/draft_reply
- split/rejected: action 없음

## draft-reply와 reply-draft

- `draft-reply`: confirmed 그룹에서만 BE3 전달용 payload 생성
- `reply-draft`: confirmed 그룹에서만 실제 답변 초안 생성

두 endpoint 모두 candidate 상태에서 호출하면 안 됩니다.

## raw body 사용 금지

중복 병합 scoring과 draft payload는 PII-safe structured data와 masked text를 우선합니다. raw body를 scoring에 새로 추가하는 방식은 금지합니다.

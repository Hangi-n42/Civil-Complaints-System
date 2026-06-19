# Duplicate Merge Recommendation FE 핸드오프

기준일: 2026-06-19  
범위: 중복 민원 병합 추천 MVP API 연결 계약

## 1. 화면 목적

`Duplicate Merge Recommendation Layer`는 같은 사건으로 반복 접수된 민원을 담당자에게 추천 그룹으로 보여주는 sidecar 기능이다. MVP에서는 실제 민원 상태 변경, 자동 병합, 자동 일괄 발송을 하지 않는다.

FE는 `status`, `allowed_actions`, `blocked_actions`를 기준으로 버튼을 노출해야 한다.

## 2. 상태와 버튼 정책

| status | 의미 | 대표 답변 초안 |
| --- | --- | --- |
| `candidate` | 추천 후보, 담당자 검토 필요 | 비활성화 또는 숨김 |
| `confirmed` | 담당자가 병합 검토 단위로 확정 | 활성화 |
| `split` | 담당자가 분리 처리 | 비활성화 |
| `rejected` | 담당자가 추천을 기각 | 비활성화 |

`allowed_actions`에 없는 작업은 버튼을 숨기거나 disabled 처리한다. `blocked_actions`는 disabled 사유 표시용으로 사용할 수 있다.

## 3. API

### 3.1 분석 실행

```http
POST /complaint-intelligence/duplicate-groups/run-analysis
```

요청은 기존 Complaint Intelligence 이벤트 배열을 사용한다. duplicate layer는 원문보다 `structured_elements`, `request_segments`, `responsible_unit`, `civil_category`, `entity_texts`를 우선 사용한다.

### 3.2 목록 조회

```http
GET /complaint-intelligence/duplicate-groups?status=candidate
```

`status`는 선택값이며 `candidate`, `confirmed`, `split`, `rejected` 중 하나다.

### 3.3 단건 조회와 상태 전이

```http
GET  /complaint-intelligence/duplicate-groups/{merge_id}
POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm
POST /complaint-intelligence/duplicate-groups/{merge_id}/split
POST /complaint-intelligence/duplicate-groups/{merge_id}/reject
POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply
```

`draft-reply`는 `confirmed`에서만 성공한다. candidate, split, rejected에서 호출하면 409와 `DUPLICATE_GROUP_NOT_CONFIRMED`가 반환된다.

## 4. 핵심 응답 필드

```json
{
  "merge_id": "dup-...",
  "status": "candidate",
  "representative_complaint_id": "case-001",
  "member_complaint_ids": ["case-001", "case-002"],
  "confidence": 0.82,
  "recommendation_level": "review",
  "recommended_decision": "REVIEW_BEFORE_MERGE",
  "evidence": [],
  "risk_flags": [],
  "allowed_actions": ["confirm", "split", "reject"],
  "blocked_actions": ["draft_reply"],
  "representative": {
    "complaint_id": "case-001",
    "selection_reason": "4요소 구조화 정보가 풍부함",
    "quality_score": 0.78
  }
}
```

## 5. Risk Flag 표시

`risk_flags`는 병합 주의 사유다. `severity=blocker`는 confirm이 차단되는 위험이다.

필수 코드:

```text
LOCATION_MISMATCH
LOCATION_AMBIGUOUS
REQUEST_TYPE_MISMATCH
DEPARTMENT_MISMATCH
SAFETY_AND_INCONVENIENCE_MIXED
LEGAL_RIGHTS_OR_DEADLINE_RISK
PII_RISK
MULTI_INTENT_SEGMENTS
SEMANTIC_ONLY_MATCH
LOW_EVIDENCE
TIME_WINDOW_TOO_WIDE
```

권장 렌더링:

| severity | UI |
| --- | --- |
| `blocker` | 빨간 경고, confirm 버튼 숨김 또는 disabled |
| `warning` | 노란 경고, 담당자 검토 안내 |
| `info` | 회색 보조 설명 |

## 6. Draft Reply Payload

`POST /draft-reply` 성공 시 실제 답변 문장이 아니라 BE3에 넘길 PII-safe payload가 반환된다.

FE는 payload를 바로 시민에게 보여주지 말고, 후속 BE3 초안 생성 화면 또는 디버그 패널에서만 사용한다.

보장 사항:

- 대표 민원의 PII-safe 구조화 결과 포함
- 구성 민원의 PII-safe 요약 포함
- merge evidence와 risk_flags 포함
- 공통 적용 가능 문구 조건 포함
- 개인정보, 개별 보상, 권리관계 판단 금지 조건 포함
- 원문 전체 재노출 없음

## 7. 완료 기준

- candidate와 confirmed를 시각적으로 구분한다.
- candidate에서는 대표 답변 초안 생성 버튼이 보이지 않거나 비활성화된다.
- risk_flags와 evidence를 상세 패널에서 확인할 수 있다.
- confirm/split/reject 후 응답의 status와 allowed_actions로 화면을 갱신한다.
- `DUPLICATE_GROUP_NOT_CONFIRMED` 409 응답은 사용자 오류가 아니라 정상적인 상태 보호로 안내한다.

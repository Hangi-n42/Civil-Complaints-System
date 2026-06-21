# 도메인 설계 문서

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/retrieval/`
  - `app/generation/`
  - `app/structuring/`
  - `app/complaint_intelligence/`
- 관련 문서:
  - `docs/10_contracts/`
  - `docs/30_manuals/`
  - `docs/50_issues/`

## 디렉터리 역할

`docs/20_domains`는 기능별 정책, 설계 판단, 처리 경계를 설명합니다. API 필드의 정확한 계약은 `docs/10_contracts`를 기준으로 하고, 이 디렉터리는 “왜 그렇게 동작해야 하는가”와 “무엇을 하면 안 되는가”를 설명합니다.

## 권장 읽는 순서

1. `complaint_intelligence/README.md`
2. `complaint_intelligence/issue_detection_policy.md`
3. `complaint_intelligence/public_insight_policy.md`
4. `complaint_intelligence/duplicate_merge_policy.md`
5. `complaint_intelligence/pii_safety_policy.md`
6. 기존 retrieval/generation/structuring 도메인 문서

## canonical 문서

- `docs/20_domains/complaint_intelligence/README.md`
- `docs/20_domains/complaint_intelligence/issue_detection_policy.md`
- `docs/20_domains/complaint_intelligence/public_insight_policy.md`
- `docs/20_domains/complaint_intelligence/duplicate_merge_policy.md`
- `docs/20_domains/complaint_intelligence/pii_safety_policy.md`

## historical/source-spec 처리 기준

기존 retrieval/generation/structuring 문서는 실험과 설계 근거를 포함하므로 보존합니다. 단, endpoint나 응답 필드처럼 외부 계약에 해당하는 내용은 `docs/10_contracts`를 우선합니다.

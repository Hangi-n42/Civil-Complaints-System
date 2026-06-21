# Complaint Intelligence PII 보호 정책

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/complaint_intelligence/pii.py`
  - `app/complaint_intelligence/schemas.py`
  - `app/complaint_intelligence/public_insights/evidence_pack.py`
  - `app/complaint_intelligence/duplicate_merger/draft_payload.py`
- 관련 문서:
  - `docs/10_contracts/data/current_data_contract.md`

## 기본 원칙

Complaint Intelligence는 민원 데이터를 관제/인사이트 용도로 재가공하므로 PII 노출 위험이 큽니다. 따라서 raw body를 외부 계약이나 리포트에 노출하지 않고, PII-safe 구조화 결과와 masked text를 우선 사용합니다.

## 입력 단계

`ComplaintIntelligenceEvent`는 다음 필드를 validator에서 마스킹합니다.

- `title`
- `body`
- `masked_text`
- `answer`
- `feedback`
- `reviewer_feedback`
- `structured_elements`
- `request_segments`
- `responsible_unit`
- `entity_texts`
- `civil_category`
- `urgency`
- `risk_level`

PII가 감지되면 다음 필드를 갱신합니다.

- `pii_detected`
- `pii_labels`
- `pii_status`

## EvidencePack

EvidencePack은 LLM에 전달되는 유일한 근거 입력입니다.

금지:

- raw complaint body
- 전화번호
- 상세 주소
- 주민 식별 가능 정보
- prompt 전체 dump

허용:

- `masked_text`
- PII-safe `structured_elements`
- region/department/status 등 운영 메타데이터
- evidence id

## Duplicate Merge

중복 병합은 PII-safe summary와 structured elements를 사용합니다. confirmed 그룹의 draft payload도 raw body를 담지 않아야 합니다.

## FE 표시

FE는 다음을 표시하지 않습니다.

- raw body
- 상세 주소
- 전화번호
- 원본 prompt
- raw LLM response

Evidence는 masked preview만 표시합니다.

## reports/PR 산출물

PR에 포함하면 안 되는 산출물:

- raw LLM response
- prompt dump
- scenario별 checkpoint raw file
- PII 가능성이 있는 debug log

포함 가능한 산출물:

- 최종 summary report
- 사람이 읽는 markdown report
- PII 검사를 통과한 JSON report

## synthetic / real replay / evaluation 데이터

- synthetic: 실제 원문이 아닌 테스트 fixture. 사용 시 명시합니다.
- demo seed: FE demo를 위한 replay timeline 데이터.
- real replay: 실제 processed/raw 기반 데이터를 replay timeline으로 재배치한 데이터.
- evaluation: curated scenario 또는 holdout 평가 데이터.

모든 경우 PII-safe 검사를 전제로 합니다.

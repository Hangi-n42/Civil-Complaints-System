# Title
[Week 1][BE1][현기] 데이터 입력 규격·정제 규칙·구조화 평가 기준 초안 수립

# Suggested Labels
- backend
- be1
- week1
- data
- structuring

# Suggested Assignee
- 현기

# Summary
BE1의 1주차 핵심 목표는 이후 모든 파이프라인의 출발점이 되는 입력 데이터 기준과 구조화 평가 기준을 정리하는 것이다.  
즉, 어떤 데이터를 어떤 형식으로 받을지, 어떻게 정제할지, 구조화 품질을 무엇으로 측정할지를 고정해야 한다.

# Source Docs
- [docs/be1_manual.md](../../be1_manual.md)
- [docs/prd_draft.md](../../prd_draft.md)
- [docs/schema_contract.md](../../schema_contract.md)
- [docs/mvp_scope.md](../../mvp_scope.md)

# Tasks
- [x] 민원 원문 입력 포맷 정의 (`CSV/JSON/manual` 기준)
- [x] CSV 컬럼 규칙 초안 정리
- [x] JSON 입력 예시 1개 작성
- [x] 텍스트 정제 규칙 초안 작성
- [x] PII 마스킹 대상 패턴 초안 정의
- [x] 4요소 구조화 예시 20건 수작업 샘플 기준 수립
- [x] 구조화 품질 평가 기준 정리 (`Precision/Recall/F1` 계산 단위)
- [x] KPI 리포트 템플릿 초안 작성
- [x] BE2가 검색에 필요로 하는 메타데이터 후보 정리
- [x] BE3가 검증에 필요로 하는 필드 제약사항 정리

# Deliverables
- 입력 포맷 기준서
- CSV/JSON 샘플
- 정제 규칙 문서
- PII 마스킹 규칙 초안
- 구조화 예시 샘플셋 기준
- 구조화 평가 기준 문서
- KPI 리포트 템플릿 초안

## 산출물 경로
- `docs/week1/be1_input_format_spec.md`
- `docs/samples/week1_input_sample.csv`
- `docs/samples/week1_input_sample.json`
- `docs/week1/be1_cleaning_and_pii_rules.md`
- `docs/week1/be1_manual20_structuring_guideline.md`
- `docs/week1/be1_structuring_eval_criteria.md`
- `docs/week1/be1_kpi_report_template.md`
- `docs/week1/be1_handoff_be2_be3.md`

# Acceptance Criteria
- 팀이 같은 입력 포맷을 사용할 수 있다.
- 4요소 정의가 모호하지 않다.
- 구조화 품질을 어떻게 측정할지 팀이 이해한다.
- BE2/BE3가 후속 구현에 필요한 메타데이터와 필드 규칙을 받는다.

# Collaboration
- FE: 구조화 결과 화면에 어떤 필드가 보여야 하는지 확인 필요
- BE2: 검색용 메타데이터(`category`, `region`, `created_at`, 엔티티`) 요구사항 확인 필요
- BE3: validation에 필요한 필드 제약 및 에러 포맷 논의 필요

# Notes
이 이슈가 늦어지면 구조화 결과와 검색/검증 인터페이스가 동시에 흔들릴 수 있다.

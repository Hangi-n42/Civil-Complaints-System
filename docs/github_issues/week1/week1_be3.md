# Title
[Week 1][BE3][현석] 스키마 검증 규칙·JSON 파싱 실패 유형·성능/OOM 기준 초안 정리

# Suggested Labels
- backend
- be3
- week1
- validation
- performance

# Suggested Assignee
- 현석

# Summary
BE3의 1주차 핵심 목표는 프로젝트의 안정성과 정합성 기준을 미리 세우는 것이다.  
구조화 결과를 어떤 규칙으로 검증할지, JSON 파싱이 어디서 깨질 수 있는지, 로컬 환경 성능/메모리 문제를 어떻게 다룰지를 초반에 정리해야 한다.

# Source Docs
- [docs/be3_manual.md](../../be3_manual.md)
- [docs/schema_contract.md](../../schema_contract.md)
- [docs/api_spec.md](../../api_spec.md)
- [docs/prd_draft.md](../../prd_draft.md)

# Tasks
- [x] 구조화 결과 validation 항목 정의
  - 근거: docs/be3_validation_rules.md
- [x] validation 오류 코드 초안 작성
  - 근거: docs/be3_error_codes.md
- [x] validation 결과 포맷 초안 정리
  - 근거: docs/be3_validation_format.md
- [x] JSON 파싱 실패 유형 조사 및 분류
  - 근거: docs/be3_json_parse_failures.md
- [x] JSON 파싱 재시도 전략 초안 작성
  - 근거: docs/be3_json_retry_strategy.md
- [x] `confidence`, `evidence_span`, `citations` 등 핵심 필드 검증 규칙 정리
  - 근거: docs/be3_validation_rules.md, docs/be3_validation_format.md
- [x] 4-bit/8-bit 비교 시 측정할 항목 정의
  - 근거: docs/be3_perf_oom_baseline.md(항목/템플릿 정의만 했고 실험 실행은 아직 아님)
- [x] 응답 시간/메모리 로깅 기준 정의
  - 근거: docs/be3_perf_oom_baseline.md
- [x] OOM 발생 시 대응 흐름 초안 작성
  - 근거: docs/be3_perf_oom_baseline.md
- [x] FE/BE2에 전달할 error/citation/validation 표시용 데이터 형식 정리
  - 근거: docs/be3_validation_format.md, docs/be3_error_codes.md, docs/be3_json_parse_failures.md

# Deliverables
- validation 규칙 메모
- 오류 코드 초안
- validation 결과 포맷 초안
- JSON 파싱 실패 유형 메모
- 재시도 전략 초안
- 성능/양자화 측정 기준 메모
- OOM 대응 흐름도 초안

# Acceptance Criteria
- 어떤 경우를 validation error로 볼지 팀이 이해한다.
- 파싱 실패 시 어떤 방식으로 재시도할지 설명 가능하다.
- 2주차 이후 구현에 필요한 성능/메모리 측정 기준이 정해진다.

# Collaboration
- BE1: 구조화 필드 규칙과 실제 오류 케이스 협의 필요
- BE2: QA 응답 JSON 형식과 citation 필수 필드 협의 필요
- FE: validation/error/citation 정보를 어떤 UI로 보여줄지 협의 필요

# Notes
이 기준이 없으면 후반에 파싱 실패, citation 오류, OOM 대응이 한꺼번에 터질 가능성이 크다.

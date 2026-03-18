# Title
[Week 1][Common] MVP 기준선 정리 및 인터페이스 1차 동결

# Suggested Labels
- planning
- documentation
- week1
- common

# Suggested Assignees
- 현기
- 도훈
- 민건
- 현석

# Summary
1주차 목표는 프로젝트 전체의 기준선을 고정하는 것이다.  
이 이슈는 PRD, MVP, API, 스키마, 폴더 구조, 역할 문서를 팀 전체가 동일하게 이해하고 이후 병렬 개발이 가능하도록 만드는 공통 정렬 작업이다.

# Background
현재 다음 문서가 준비되어 있다.
- [docs/00_overview/prd.md](../../../00_overview/prd.md)
- [docs/00_overview/mvp_scope.md](../../../00_overview/mvp_scope.md)
- [docs/10_contracts/api/api_spec.md](../../../10_contracts/api/api_spec.md)
- [docs/10_contracts/schema/schema_contract.md](../../../10_contracts/schema/schema_contract.md)
- [docs/00_overview/folder_structure_draft.md](../../../00_overview/folder_structure_draft.md)
- [docs/30_manuals/be1_manual.md](../../../30_manuals/be1_manual.md)
- [docs/30_manuals/fe_manual.md](../../../30_manuals/fe_manual.md)
- [docs/30_manuals/be2_manual.md](../../../30_manuals/be2_manual.md)
- [docs/30_manuals/be3_manual.md](../../../30_manuals/be3_manual.md)

이 문서들을 기준으로 1주차 종료 시점까지 팀 전체가 같은 기준으로 움직여야 한다.

# Tasks
- [ ] PRD 기준 In Scope / Out of Scope 재확인
- [ ] MVP 필수 기능과 후순위 기능 팀 합의
- [ ] API 명세 초안 리뷰 및 피드백 반영 포인트 정리
- [ ] 스키마 계약 초안 리뷰 및 모호한 필드 정리
- [ ] 폴더 구조 초안 승인 여부 결정
- [ ] 역할별 매뉴얼 상호 검토
- [ ] 공통 용어 정의 확정 (`case_id`, `chunk_id`, `citation`, `validation`, `top_k` 등)
- [ ] 1주차 종료 회의에서 다음 주 PoC 기준선 확정

# Deliverables
- 인터페이스 동결 회의 메모
- 문서별 수정 필요 항목 목록
- 2주차 PoC 시작 기준선

# Acceptance Criteria
- 팀원 전원이 API, 스키마, 폴더 구조, 역할 분담을 같은 의미로 이해한다.
- 문서 간 충돌 항목이 식별되거나 해소된다.
- 2주차 PoC에 필요한 공통 기준이 정리된다.

# Dependencies
- 없음

# Notes
이 이슈는 구현보다 정렬이 목표다.  
1주차에 이 기준선을 놓치면 3~5주차 통합 비용이 크게 증가한다.

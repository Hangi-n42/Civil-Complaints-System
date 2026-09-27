# 문서 지도

- 문서 버전: v2.1
- 기준일: 2026-09-26

## 신규 제품: 회사 지식 워크벤치

아래 네 문서가 신규 개발의 주 기준입니다. 요구사항과 계획이며 구현 완료 보고가 아닙니다.

| 문서 | 역할 |
|---|---|
| [PRD](00_overview/company_knowledge_prd.md) | 문제·범위·요구사항·수용 기준 |
| [아키텍처·설계](05_plans/company_knowledge/architecture.md) | 기존 코드와 신규 모듈의 경계 |
| [구현 계획](05_plans/company_knowledge/implementation.md) | API·데이터·오픈소스 재사용·버전 조정 |
| [마일스톤](05_plans/company_knowledge/milestones.md) | K1 이후 구현 순서와 완료 조건 |

[파일럿 고정 기록](70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md)의 입력 준비는 완료됐지만 P0 제품 구현·효용 검증은 완료되지 않았습니다. 연구·선정 근거는 `70_research/company_knowledge/`에서 확인합니다.

## 현재 실행 가능한 민원 시스템

- [기능 PRD](00_overview/complaint_system_prd.md), [현재 아키텍처](00_overview/complaint_system_architecture.md), [기술 스택](00_overview/dev_stack.md)
- [계약 문서](10_contracts/README.md): 현재 API 계약과 과거 주차별 설계를 구분
- [민원 관제 도메인](20_domains/complaint_intelligence/README.md)
- [로컬 개발](30_manuals/local_dev_runbook.md), [평가 안내](30_manuals/evaluation_runbook.md)
- [폴더 구조](00_overview/folder_structure.md)

## 과거 기록과 문서 유지 원칙

[experiments](../experiments/README.md)는 모듈별 과거 실험 보고서입니다. 원작성일·수치·실험 조건은 보존하며 현재 성능 근거로 승격하지 않습니다. [reports](../reports/README.md)는 기존 스크립트의 산출물 경로를 유지합니다. `90_archive/`에는 이전 민원 MVP/WBS와 문서 감사표를 보관합니다.

신규 요구는 PRD, 구현 선택은 구현 계획, 코드 경계는 설계, 일정·완료 여부는 마일스톤에 한 번씩 기록합니다. 변경 시 해당 문서의 버전·기준일·상태를 함께 갱신합니다. 역사적 보고서 본문은 현재 구현에 맞춰 고쳐 쓰지 않습니다.

[문서 감사표](DOCS_AUDIT.md) · [이번 정리 검수 기록](documentation_reorganization_review_2026-09-26.md)

2026-09-26 후속 정리: 메인 PRD는 `00_overview/company_knowledge_prd.md`(v1.4), 상세 설계·구현·마일스톤은 `05_plans/company_knowledge/`에 둔다. [ADR](00_overview/adr_architecture_decision_record.md)은 Git·현재 코드에 맞춰 v3.0으로 갱신했다.

# 회사 지식 워크벤치

- 문서 버전: v2.0
- 기준일: 2026-09-26

회사 문서에서 근거가 있는 지식·온톨로지를 구축하고, 사람이 검토한 지식을 갱신하며 Local/Global 검색에 활용하는 제품을 개발합니다. 기존 민원 검색·답변·관제 시스템은 재사용 기반이자 향후 활용 예시입니다.

## 주 기준 문서

- [제품 요구사항(PRD)](docs/00_overview/company_knowledge_prd.md)
- [목표 아키텍처·설계](docs/05_plans/company_knowledge/architecture.md)
- [구현 계획·오픈소스 재사용](docs/05_plans/company_knowledge/implementation.md)
- [1~2일 단위 마일스톤](docs/05_plans/company_knowledge/milestones.md)

## 현재 상태

신규 제품은 P0 구현 전입니다. K1의 파일럿 자료와 12개 평가 과제는 고정했지만 비교 실행 절차와 최소 데이터/API 계약은 남아 있습니다. `app/knowledge`와 지식 전용 API·UI는 아직 없습니다. 파일럿 과제는 독립적인 사람의 맹검 평가 자료가 아니며 제품 효용을 입증한 결과도 아닙니다.

현재 실행할 수 있는 기능은 기존 민원 검색·답변 생성·평가·관제입니다. [기존 민원 기능 PRD](docs/00_overview/complaint_system_prd.md)와 [현재 구현 아키텍처](docs/00_overview/complaint_system_architecture.md)를 참고합니다.

## 개발 시작

[로컬 개발 안내](docs/30_manuals/local_dev_runbook.md)에 Python 3.11.9, Mac/Windows 환경, 로컬 `.env`, 데이터·Ollama·포트 설정을 정리했습니다. [프런트엔드 안내](frontend/README.md)도 함께 확인합니다. `npm run dev`의 사전 처리에는 replay DB 초기화가 포함되므로 실행 안내의 데이터 보존 경로를 먼저 확인합니다.

## 문서와 산출물

- [문서 전체 지도](docs/README.md): 요구사항·설계·현재 계약·운영 안내
- [파일럿 고정 기록](docs/70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md): 현재 준비 범위와 한계
- [모듈별 과거 실험](experiments/README.md): 과거 보고서 보관
- [실행 산출물](reports/README.md): 스크립트가 사용하는 JSON·캐시와 평가 절차
- [문서 정리 감사표](docs/DOCS_AUDIT.md): 이동 경로와 검토 범위

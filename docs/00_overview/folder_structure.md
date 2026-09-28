# 프로젝트 폴더 구조

> **2026-09-27 병합 상태 보충:** #498에서 `app/knowledge/`, `app/api/routers/knowledge.py`, `frontend/app/knowledge/`, `scripts/import_knowledge_pilot.py`가 추가됐다. 아래 목표 디렉터리 부재 설명은 #497 정리 당시 기준이다. `docs/05_plans/company_knowledge/contracts.md`, `evaluation_protocol.md`와 K2 실행 안내도 함께 유지한다.

- 문서 버전: v2.1
- 기준일: 2026-09-26

| 경로 | 역할·현재 상태 |
|---|---|
| `app/api/` | 기존 민원 API |
| `app/retrieval/`, `app/generation/`, `app/evaluation/` | 검색·답변 생성·평가 |
| `app/complaint_intelligence/` | 민원 관제·중복 판단 |
| `app/ui/` | 기존 Streamlit UI 코드 |
| `frontend/` | Next.js Workbench·Intelligence 화면 |
| `src/`, `scripts/` | 전처리·PII·적재·평가 등 기존 처리 |
| `configs/knowledge/pilot_v1/` | 신규 제품 파일럿 자료 목록·근거·12개 과제 |
| `data/` 및 설정된 Chroma 디렉터리 | 로컬 데이터·인덱스. 실제 경로는 설정과 실행 안내 확인 |
| `docs/00_overview/company_knowledge_prd.md` | 신규 제품의 메인 PRD v1.4 |
| `docs/00_overview/adr_architecture_decision_record.md` | 현재·대체·계획 아키텍처 결정 |
| `docs/05_plans/company_knowledge/` | 신규 제품 상세 설계·구현 계획·마일스톤 |
| `docs/00_overview/` | 신규 제품 PRD·ADR·기술 스택·기존 민원 구현 개요 |
| `docs/10_contracts/`, `docs/20_domains/` | 기존 민원 계약·도메인 |
| `docs/30_manuals/` | 실행·운영 안내 |
| `docs/70_research/company_knowledge/` | 신규 제품 조사·검수·파일럿 기록 |
| `docs/90_archive/` | 종료된 계획·이전 문서 감사 |
| `docs/90_archive/complaint_system/` | 과거 민원 ADR v2.2·UX 시나리오·검색 선정서·MVP/WBS |
| `experiments/<module>/` | 모듈별 과거 실험 보고서 |
| `reports/` | 기존 스크립트 산출물·평가 절차 |

`app/knowledge/`와 지식 전용 라우터·화면은 목표 설계이며 현재 존재하는 소스로 표시하지 않습니다. [문서 지도](../README.md)와 [실행 안내](../30_manuals/local_dev_runbook.md)를 참고합니다.

## 2026-09-28 불필요한 추적 파일 정리

루트 `schemas/`, `tests/fixtures/`, `.tmp_issue_bodies/`와 `logs/`에 남아 있던 과거 추적 파일을 삭제했다. 코드·테스트에서 해당 파일을 읽는 참조는 발견하지 못했다. `app/api/schemas/`, 각 모듈의 `schemas.py`, `app/tests/fixtures/`는 별개이며 유지한다. `logs/`는 실행 시 다시 만들어지는 로컬 출력 경로로 계속 사용하며 기존 Git 제외 규칙을 유지한다.

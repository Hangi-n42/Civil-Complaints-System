# 프로젝트 개요 문서

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/main.py`
  - `app/api/routers/`
  - `app/complaint_intelligence/`
  - `frontend/app/`
  - `frontend/components/intelligence/`
- 관련 문서:
  - `docs/10_contracts/README.md`
  - `docs/20_domains/README.md`
  - `docs/30_manuals/README.md`

## 디렉터리 역할

`docs/00_overview`는 처음 온 개발자가 프로젝트의 목표, 현재 구조, 주요 기능 경계, 실행 산출물의 위치를 이해하기 위한 진입점입니다.

이 디렉터리는 세부 API 계약이나 운영 명령을 모두 담지 않습니다. 상세 계약은 `docs/10_contracts`, 도메인 정책은 `docs/20_domains`, 실행 절차는 `docs/30_manuals`를 기준으로 봅니다.

## 권장 읽는 순서

1. `prd.md`: 현재 제품 목표와 기능 범위
2. `architecture.md`: 전체 시스템 경계와 주요 파이프라인
3. `folder_structure.md`: 코드/데이터/리포트/문서 위치
4. `dev_stack.md`: 기술 스택과 로컬 실행 전제

## canonical 문서

- `docs/00_overview/prd.md`
- `docs/00_overview/architecture.md`
- `docs/00_overview/folder_structure.md`
- `docs/00_overview/dev_stack.md`

## historical/source-spec 처리 기준

주차별 산출물, 실험 리포트, handoff 문서는 `docs/40_delivery`, `docs/50_issues`, `docs/60_specs`에 보존합니다. 이 문서들은 구현 맥락을 이해하는 근거 자료이지만, 현재 기준 계약은 아닙니다.

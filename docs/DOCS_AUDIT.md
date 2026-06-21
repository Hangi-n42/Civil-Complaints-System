# 문서 감사표

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `app/complaint_intelligence/service.py`
  - `app/complaint_intelligence/schemas.py`
  - `app/complaint_intelligence/duplicate_merger/schemas.py`
  - `frontend/app/intelligence/page.tsx`
  - `frontend/lib/api.ts`
- 관련 근거 문서:
  - `docs/40_delivery/`
  - `docs/50_issues/`
  - `docs/60_specs/`

## 감사 원칙

이 표는 현재 코드와 문서의 기준 위치를 맞추기 위한 작업 기록입니다. `00_overview`, `10_contracts`, `20_domains`, `30_manuals`를 현재 기준 문서 위치로 두고, `40_delivery`, `50_issues`, `60_specs`는 삭제하지 않고 근거, handoff, source-spec, historical 자료로 유지합니다.

처리 방침 값은 다음 의미입니다.

- `keep`: 현재 위치와 내용이 기준 역할에 부합합니다.
- `update`: 현재 위치에서 최신 코드 기준으로 갱신합니다.
- `merge`: 다른 기준 문서로 내용을 흡수합니다.
- `deprecate`: 현재 기준은 아니며 새 문서로 이동해야 합니다.
- `historical`: 과거 산출물 또는 주차별 기록입니다.
- `source-spec`: 기준 문서의 원천 근거로 보존합니다.

## 감사표

| 문서 경로 | 현재 역할 | 최신성 판단 | 목표 위치 | 처리 방침 | 기준 코드/근거 | 확인 필요 |
| --- | --- | --- | --- | --- | --- | --- |
| `docs/00_overview/README.md` | overview 진입점 | 신규 작성 | 유지 | keep | 전체 코드 구조 | 없음 |
| `docs/00_overview/folder_structure.md` | 폴더 구조 설명 | 기존 문서 일부 인코딩 깨짐, 최신 기능 부족 | 유지 | update | `app/`, `frontend/`, `scripts/`, `data/`, `reports/` | 없음 |
| `docs/00_overview/dev_stack.md` | 기술 스택 설명 | Adaptive RAG 중심, Intelligence 최신 기능 부족 | 유지 | update | `requirements.txt`, `frontend/package.json`, `app/core/config.py` | 일부 선택 의존성은 확인 필요 |
| `docs/00_overview/prd.md` | 제품/범위 설명 | Workbench 중심, 관제형 Intelligence 반영 부족 | 유지 | update | API 라우터, FE intelligence 화면 | 없음 |
| `docs/00_overview/architecture.md` | 아키텍처 개요 | 신규 작성 | 유지 | keep | `app/api/routers/*`, `app/complaint_intelligence/*` | 없음 |
| `docs/10_contracts/README.md` | 계약 문서 진입점 | 신규 작성 | 유지 | keep | API/스키마 코드 | 없음 |
| `docs/10_contracts/api/current_api_contract.md` | 현재 API 계약 | 신규 작성 | 유지 | keep | FastAPI 라우터 | 없음 |
| `docs/10_contracts/data/current_data_contract.md` | 현재 데이터 계약 | 신규 작성 | 유지 | keep | Pydantic schema | 없음 |
| `docs/10_contracts/frontend/current_fe_contract.md` | Workbench FE 계약 | 신규 작성 | 유지 | keep | `frontend/lib/api.ts` | 일부 UI 세부 상태는 확인 필요 |
| `docs/10_contracts/frontend/intelligence_fe_contract.md` | Intelligence FE 계약 | 신규 작성 | 유지 | keep | `frontend/app/intelligence/page.tsx`, `frontend/components/intelligence/*` | 없음 |
| `docs/10_contracts/api/old_api_spec.md` | 과거 API 계약 | 오래된 계약 | `10_contracts` 보존 | historical | 기존 문서 | 없음 |
| `docs/10_contracts/schema/old_schema_contract.md` | 과거 스키마 계약 | 오래된 계약 | `10_contracts` 보존 | historical | 기존 문서 | 없음 |
| `docs/10_contracts/interfaces/week*/` | 주차별 인터페이스 | 주차별 산출물 | `10_contracts` 보존 | historical | 기존 문서 | 없음 |
| `docs/20_domains/README.md` | 도메인 문서 진입점 | 신규 작성 | 유지 | keep | 도메인 모듈 | 없음 |
| `docs/20_domains/retrieval/*` | 검색 도메인 자료 | 대체로 근거 자료 | 유지 | keep | retrieval 코드/리포트 | 최신성은 문서별 재검토 필요 |
| `docs/20_domains/generation/*` | 생성 도메인 자료 | 대체로 근거 자료 | 유지 | keep | generation 코드/리포트 | 최신성은 문서별 재검토 필요 |
| `docs/20_domains/ingestion_structuring/*` | 구조화 도메인 자료 | 유효한 근거 자료 | 유지 | keep | structuring 코드 | 없음 |
| `docs/20_domains/complaint_intelligence/README.md` | Intelligence 도메인 진입점 | 신규 작성 | 유지 | keep | Complaint Intelligence 코드 | 없음 |
| `docs/20_domains/complaint_intelligence/issue_detection_policy.md` | IssueAlert 정책 | 신규 작성 | 유지 | keep | `issue_detection/engine.py` | 없음 |
| `docs/20_domains/complaint_intelligence/public_insight_policy.md` | PublicAgencyInsight 정책 | 신규 작성 | 유지 | keep | `public_insights/*` | 없음 |
| `docs/20_domains/complaint_intelligence/duplicate_merge_policy.md` | 중복 병합 정책 | 신규 작성 | 유지 | keep | `duplicate_merger/*` | 없음 |
| `docs/20_domains/complaint_intelligence/pii_safety_policy.md` | PII 보호 정책 | 신규 작성 | 유지 | keep | `pii.py`, schema validator | 없음 |
| `docs/30_manuals/README.md` | 매뉴얼 진입점 | 신규 작성 | 유지 | keep | 실행 스크립트 | 없음 |
| `docs/30_manuals/local_dev_runbook.md` | 로컬 실행 | 신규 작성 | 유지 | keep | `scripts/run_api.py`, frontend scripts | 포트는 환경별 확인 필요 |
| `docs/30_manuals/complaint_intelligence_demo_replay.md` | Intelligence seed/replay | 신규 작성 | 유지 | keep | seed/replay scripts | 없음 |
| `docs/30_manuals/duplicate_merge_demo_flow.md` | 중복 병합 demo | 신규 작성 | 유지 | keep | duplicate demo scripts/API | 없음 |
| `docs/30_manuals/evaluation_runbook.md` | 평가 절차 | 신규 작성 | 유지 | keep | evaluation scripts/reports | 없음 |
| `docs/60_specs/api_interface_spec.md` | 과거 API spec | 현재 계약과 중복 | `10_contracts/api/current_api_contract.md` | source-spec | FastAPI 라우터 | 없음 |
| `docs/60_specs/data_schema_spec.md` | 과거 데이터 spec | 현재 계약과 중복 | `10_contracts/data/current_data_contract.md` | source-spec | Pydantic schema | 없음 |
| `docs/60_specs/ui_workbench_spec.md` | 과거 UI spec | 현재 FE 계약과 중복 | `10_contracts/frontend/*` | source-spec | frontend 코드 | 없음 |
| `docs/40_delivery/` | 주차별/이슈별 delivery 산출물 | 근거 자료 | 보존 | historical | 리포트/인수인계 | 없음 |
| `docs/50_issues/` | 이슈별 설계/검증/handoff | 근거 자료 | 보존 | source-spec/handoff | 최신 handoff 문서 | 문서별 최신성 확인 필요 |

## 통합 결과

`docs/60_specs`의 현재 API, 데이터, UI 계약은 각각 다음 문서로 흡수했습니다.

- API: `docs/10_contracts/api/current_api_contract.md`
- 데이터: `docs/10_contracts/data/current_data_contract.md`
- FE/BE 계약: `docs/10_contracts/frontend/current_fe_contract.md`, `docs/10_contracts/frontend/intelligence_fe_contract.md`

원본 `60_specs` 문서는 삭제하지 않고 source-spec으로 남깁니다.

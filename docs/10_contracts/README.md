# 계약 문서

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `app/api/schemas/`
  - `app/complaint_intelligence/schemas.py`
  - `app/complaint_intelligence/duplicate_merger/schemas.py`
  - `frontend/lib/api.ts`
- 관련 문서:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`

## 디렉터리 역할

`docs/10_contracts`는 현재 살아있는 API, 데이터, FE-BE 계약의 기준 위치입니다. FE 담당자는 이 디렉터리를 먼저 보고 endpoint, 상태, 필드 계약을 확인합니다. BE 담당자는 Pydantic schema와 서비스 정책이 외부에 어떤 형태로 노출되는지 확인합니다.

## 권장 읽는 순서

1. `api/current_api_contract.md`
2. `data/current_data_contract.md`
3. `frontend/current_fe_contract.md`
4. `frontend/intelligence_fe_contract.md`

## canonical 문서

- `docs/10_contracts/api/current_api_contract.md`
- `docs/10_contracts/data/current_data_contract.md`
- `docs/10_contracts/frontend/current_fe_contract.md`
- `docs/10_contracts/frontend/intelligence_fe_contract.md`

## historical 문서 처리

`interfaces/week*`, `api/old_api_spec.md`, `schema/old_schema_contract.md`는 주차별 또는 과거 기준 계약입니다. 새 구현 판단의 기준으로 쓰지 말고, 변경 배경을 확인하는 historical 자료로 봅니다.

## `60_specs`와의 관계

`docs/60_specs`의 API, 데이터, UI 사양 중 현재 코드와 맞는 내용은 이 디렉터리로 흡수했습니다. `60_specs`는 source-spec으로 보존합니다.

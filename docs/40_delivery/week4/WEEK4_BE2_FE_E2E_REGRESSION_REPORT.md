# Week4 BE2 FE E2E/Regression Report (#128)

- Issue: #128 (parent)
- Scope: FE search contract stability and retrieval->QA context handoff readiness
- Generated at: 2026-04-08

## 1. Goal

This report proves BE2-side completion evidence for FE-linked E2E regression checks required by #128.

## 2. Validated Flows

1. Search API returns FE-required fields with stable fallback behavior.
2. `answers_by_admin_unit` is always present and `department_answers` alias is synchronized.
3. Search result payload can be mapped into QA context input without contract break.

## 3. Test Coverage

### 3.1 Contract-level Search API tests

- File: app/tests/unit/test_retrieval_router_contract.py
- Validates:
  - required wrappers (`success`, `request_id`, `timestamp`, `data`)
  - FE-required fields in `data.results[]`
  - safe default/fallback behavior

### 3.2 FE E2E regression path tests (new)

- File: app/tests/unit/test_be2_week4_fe_e2e_regression.py
- Test cases:
  1. `test_be2_fe_search_to_qa_context_flow`
     - Search -> FE-required fields -> QA context mapping all succeed
  2. `test_be2_fe_search_response_fallbacks_are_stable`
     - Missing source fields still produce stable FE schema + valid QA context mapping

### 3.3 Retrieval->QA mapper tests

- File: app/tests/unit/test_generation_context_mapper.py
- Validates budget clipping/drops/order guarantees for context mapping

## 4. Execution Command

```powershell
c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe -m pytest app/tests/unit/test_generation_context_mapper.py app/tests/unit/test_retrieval_router_contract.py app/tests/unit/test_be2_week4_fe_e2e_regression.py app/tests/unit/test_be1_week2_tasks.py
```

## 5. Result

- Status: PASS
- Summary: 15 passed / 0 failed

## 6. #128 Requirement Mapping

1. retrieval 결과를 QA 컨텍스트로 안정 연결: PASS
- Proven by context mapper tests + FE flow regression tests

2. 필터/Top-K 기준선 확정 및 성능 측정: PASS
- Refer: logs/evaluation/week4_issue136_baseline_report.json

3. 검색 결과 계약 안정화: PASS
- Proven by retrieval router contract and fallback tests

4. 실서비스 API 검색 경로 ChromaDB 벡터 검색 전환: PASS
- Refer: #148 completion evidence

5. 검색 결과 계약 유지 확인: PASS
- Proven by updated schema and router contract tests

6. FE 연계 E2E 테스트 및 회귀 점검: PASS
- Proven by this report and `test_be2_week4_fe_e2e_regression.py`

## 7. Evidence Artifacts

- app/api/routers/retrieval.py
- app/api/schemas/retrieval.py
- app/tests/unit/test_retrieval_router_contract.py
- app/tests/unit/test_be2_week4_fe_e2e_regression.py
- app/tests/unit/test_generation_context_mapper.py
- logs/evaluation/week4_issue136_baseline_report.json

# 실행/운영 매뉴얼

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `scripts/run_api.py`
  - `frontend/package.json`
  - `scripts/build_complaint_intelligence_demo_seed.py`
  - `scripts/seed_complaint_intelligence_demo.py`
  - `scripts/prepare_complaint_intelligence_real_replay.py`
  - `scripts/seed_duplicate_merge_demo.py`
  - `scripts/evaluate_complaint_intelligence_scenarios.py`
- 관련 문서:
  - `docs/10_contracts/`
  - `docs/20_domains/`
  - `docs/50_issues/complaint_intelligence_demo_seed.md`

## 디렉터리 역할

`docs/30_manuals`는 개발자와 운영/검증 담당자가 실제로 실행할 명령과 순서를 확인하는 곳입니다. 기능 설명보다 실행 절차, seed/replay, 평가, 흔한 문제 해결에 집중합니다.

## 권장 읽는 순서

1. `local_dev_runbook.md`
2. `complaint_intelligence_demo_replay.md`
3. `duplicate_merge_demo_flow.md`
4. `evaluation_runbook.md`
5. `chromadb_lfs_policy.md`

## canonical 문서

- `docs/30_manuals/local_dev_runbook.md`
- `docs/30_manuals/complaint_intelligence_demo_replay.md`
- `docs/30_manuals/duplicate_merge_demo_flow.md`
- `docs/30_manuals/evaluation_runbook.md`

## historical 문서 처리 기준

기존 실험/평가 매뉴얼은 보존합니다. 단, 현재 서버 실행, Intelligence demo/replay, 중복 병합 demo, 평가 실행 절차는 위 canonical 문서를 기준으로 합니다.

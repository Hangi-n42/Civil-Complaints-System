# Complaint Intelligence Demo/Replay Runbook

- 문서 상태: runbook
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `scripts/build_complaint_intelligence_demo_seed.py`
  - `scripts/seed_complaint_intelligence_demo.py`
  - `scripts/prepare_complaint_intelligence_real_replay.py`
  - `app/complaint_intelligence/service.py`
  - `app/api/routers/complaint_intelligence.py`
- 관련 문서:
  - `docs/50_issues/complaint_intelligence_demo_seed.md`
  - `docs/10_contracts/frontend/intelligence_fe_contract.md`

## 목적

FE Intelligence dashboard가 빈 화면으로 보이지 않도록, 실제 분석 파이프라인을 통과한 IssueAlert/PublicAgencyInsight/Duplicate Merge read-model을 준비합니다.

중요:

- mock 카드나 하드코딩 dashboard 응답을 만들지 않습니다.
- 실제 `ComplaintIntelligenceService.run_analysis(...)` 경로를 사용합니다.
- demo seed와 real replay seed를 구분합니다.

## Demo seed

입력/출력:

- seed: `data/demo/complaint_intelligence_demo_events.json`
- build report: `reports/complaint_intelligence_demo_seed_build_report.json`
- run report: `reports/complaint_intelligence_demo_seed_run_report.json`

생성:

```powershell
civil\Scripts\python.exe scripts\build_complaint_intelligence_demo_seed.py
```

적재/분석:

```powershell
civil\Scripts\python.exe scripts\seed_complaint_intelligence_demo.py
```

## Real replay seed

입력/출력:

- seed: `data/complaint_intelligence/complaint_intelligence_real_replay_events.json`
- build report: `reports/complaint_intelligence_real_replay_seed_build_report.json`
- run report: `reports/complaint_intelligence_real_replay_seed_run_report.json`

준비:

```powershell
civil\Scripts\python.exe scripts\prepare_complaint_intelligence_real_replay.py
```

실행 스크립트는 현재 repo의 실제 옵션을 확인한 뒤 사용합니다.

## Dashboard 확인

Backend 실행 후:

```http
GET /complaint-intelligence/dashboard
GET /complaint-intelligence/issue-alerts
GET /complaint-intelligence/public-insights
GET /complaint-intelligence/duplicate-groups
```

FE 확인:

```text
/intelligence
```

## DB 주의사항

demo/basic DB와 real replay DB를 섞지 마십시오.

- demo seed 검증: demo source_name과 demo DB path를 사용
- real replay 검증: real replay source_name과 별도 DB path 사용 권장

SQLite 파일은 로컬 산출물입니다. PR에 포함하기 전 PII와 용량 정책을 확인합니다.

## PII 확인

seed와 report에는 raw PII가 없어야 합니다. 최소한 전화번호, 상세 주소 패턴을 검색합니다.

```powershell
rg "010-|[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}" data reports
```

## 흔한 실패

- alert/insight가 0건: threshold, recent window, baseline 조건 확인
- dashboard가 비어 있음: seed script가 같은 DB path를 사용했는지 확인
- EvidencePack이 없음: PublicAgencyInsight 생성/저장 단계와 repository 상태 확인

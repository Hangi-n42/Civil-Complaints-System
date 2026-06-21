# Complaint Intelligence 데모 Seed 운영 메모

## 왜 대시보드가 비어 보일 수 있나

`GET /complaint-intelligence/dashboard`는 저장소의 최신 read-model을 읽습니다. 따라서 서버를 켠 직후 또는 분석을 한 번도 실행하지 않은 SQLite DB에서는 `ci_events`, `ci_issue_alerts`, `ci_public_insights`, `ci_evidence_packs`, `ci_analysis_runs`가 비어 있어 FE 탭도 비어 보입니다.

## 데모 seed 생성

실제 공개 민원 데이터를 우선 사용해 replay timeline seed를 생성합니다.

```powershell
civil\Scripts\python.exe scripts\build_complaint_intelligence_demo_seed.py --allow-synthetic-fill false
```

출력:

- `data/demo/complaint_intelligence_demo_events.json`
- `reports/complaint_intelligence_demo_seed_build_report.json`

기본값은 synthetic fill을 쓰지 않습니다. 실제 데이터가 부족해 `--allow-synthetic-fill true`를 쓴 경우에는 report의 `synthetic_event_count`를 시연/공유 문서에 반드시 명시해야 합니다.

## 분석 실행

생성된 seed를 실제 Complaint Intelligence 분석 파이프라인으로 실행해 SQLite read-model을 채웁니다.

```powershell
civil\Scripts\python.exe scripts\seed_complaint_intelligence_demo.py
```

출력:

- `reports/complaint_intelligence_demo_seed_run_report.json`
- 기본 SQLite DB: `data/complaint_intelligence/complaint_intelligence.db`

## FE 확인 endpoint

FE는 별도 mock 없이 다음 endpoint만 호출하면 됩니다.

```http
GET /complaint-intelligence/dashboard
GET /complaint-intelligence/issue-alerts
GET /complaint-intelligence/public-insights
```

## threshold 실패 시 확인할 항목

- `NO_ALERT_CREATED`: `CI_MIN_RECENT_COUNT`, `CI_MIN_SURGE_RATIO`, 최근 3시간 replay 배치 여부를 확인합니다.
- `NO_PUBLIC_INSIGHT_CREATED`: `PUBLIC_INSIGHT_MIN_CANDIDATE_COMPLAINT_COUNT`, QualityGate 실패 여부를 확인합니다.
- `NO_EVIDENCE_PACK`: PublicAgencyInsight 생성 후 evidence pack 저장 흐름을 확인합니다.
- `PII_IN_EVIDENCE_PACK`: seed 생성 전후 PII 마스킹과 repository 저장 마스킹을 확인합니다.

## 원칙

이 seed는 mock 카드가 아니라 실제 공개 데이터 후보를 실시간 관제 데모용 replay timeline으로 재배치한 입력입니다. dashboard 응답은 하드코딩하지 않고 실제 `ComplaintIntelligenceService.run_analysis(...)` 실행 결과로 채웁니다.

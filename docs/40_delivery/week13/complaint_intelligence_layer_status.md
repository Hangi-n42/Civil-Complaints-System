# Complaint Intelligence Layer 구현 현황 및 검증 결과

## 개요

Complaint Intelligence Layer는 민원 이벤트를 실시간 관제형 read-model로 저장하고, 의미적으로 유사한 민원 급증을 `IssueAlert`로 감지하며, EvidencePack 기반 `PublicAgencyInsight`를 생성합니다.

이번 구현은 mock dashboard 응답이 아니라 실제 분석 파이프라인을 통과한 결과를 SQLite repository에 저장하고 FE가 `GET /complaint-intelligence/dashboard`로 조회할 수 있게 만든 상태입니다.

## 전체 파이프라인

```text
ComplaintIntelligenceEvent
  -> PII 마스킹
  -> SQLite/InMemory repository 저장
  -> IssueDetectionEngine
  -> IssueAlert 저장
  -> PublicInsightCandidate 생성
  -> EvidencePack 구성
  -> Aspect/Request 집계
  -> Local/Fake LLM synthesis
  -> GroundingVerifier
  -> ActionRepair + ActionRubric
  -> InsightQualityGate
  -> PublicAgencyInsight 저장
  -> Dashboard read-model 조회
```

## 주요 구성 요소

| 영역 | 파일/모듈 | 역할 |
| --- | --- | --- |
| API | `app/api/routers/complaint_intelligence.py` | dashboard, run-analysis, issue-alerts, public-insights, scheduler, collector, duplicate endpoints |
| Orchestration | `app/complaint_intelligence/service.py` | 분석 실행, repository 저장, dashboard state 조회 |
| Repository | `app/complaint_intelligence/repository.py`, `sqlite_repository.py` | 분석 이력, 이벤트, alert, insight, evidence pack, duplicate group, checkpoint 영속화 |
| Scheduler | `app/complaint_intelligence/scheduler.py` | collector batch 수집 후 단일 프로세스 run-analysis 실행 |
| Collector | `app/complaint_intelligence/collector.py` | Noop/RepositoryReplay collector interface |
| Issue Detection | `app/complaint_intelligence/issue_detection/engine.py` | hotspot, surge, operational metadata 기반 IssueAlert 생성 |
| Public Insight | `app/complaint_intelligence/public_insights/` | candidate, evidence pack, LLM synthesis, verifier, quality gate, ranker, fallback |
| Duplicate Merge | `app/complaint_intelligence/duplicate_merger/` | 유사/중복 민원 병합 후보 관리 |

## PublicAgencyInsight 품질 안정화

### Evidence 기반 생성

- LLM은 raw 민원 원문이 아니라 `PublicInsightEvidencePack`만 봅니다.
- EvidencePack에는 `masked_text`, 구조화 4요소, 운영 메타데이터, 대표 evidence id, allowed action catalog가 포함됩니다.
- 모든 evidence text는 PII 마스킹된 값만 저장/전달합니다.

### Local LLM 안정화

Local LLM 모델은 `exaone3.5:7.8b`를 사용했습니다.

안정화 내용:

- compact EvidencePack serializer
- compact JSON-only prompt
- JSON parser/repair
- valid evidence id 제한
- action evidence repair
- action-level retry
- action_type rubric
- risk 기반 human_review 후처리
- QualityGate/actionability score

### Action Rubric

`action_type`을 LLM 자유 생성에 맡기지 않고 `type_hint/topic_label` 기반 후보로 제한합니다.

예시:

| 주제/유형 | 허용 action_type |
| --- | --- |
| 도로 침하/싱크홀 | `FIELD_INSPECTION`, `SAFETY_NOTICE`, `MAINTENANCE` |
| 불법주정차/단속 | `ENFORCEMENT`, `PUBLIC_GUIDANCE`, `FIELD_INSPECTION` |
| 대형폐기물 배출 안내 | `PUBLIC_GUIDANCE`, `CITIZEN_COMMUNICATION`, `SERVICE_DESIGN` |
| 공공자전거 UX | `SERVICE_DESIGN`, `PUBLIC_GUIDANCE`, `CITIZEN_COMMUNICATION` |
| 처리 지연/미처리 | `PROCESS_IMPROVEMENT`, `STAFFING_OR_WORKLOAD_REVIEW`, `CITIZEN_COMMUNICATION` |

## Demo/Evaluation 데이터

| 파일 | 역할 |
| --- | --- |
| `data/demo/complaint_intelligence_demo_events.json` | FE dashboard를 채우는 실제 데이터 기반 replay seed |
| `scripts/build_complaint_intelligence_demo_seed.py` | 실제 데이터 후보를 찾아 demo seed 생성 |
| `scripts/seed_complaint_intelligence_demo.py` | seed를 실제 분석 파이프라인에 투입하고 dashboard read-model 저장 |
| `data/evaluation/complaint_intelligence_eval_scenarios.json` | 13개 품질 평가 scenario |
| `scripts/evaluate_complaint_intelligence_scenarios.py` | IssueAlert/PublicAgencyInsight E2E 평가 |

## 평가 시나리오

총 13개 scenario를 사용했습니다.

1. 도로 침하/싱크홀 급증
2. 불법주정차 특정 시간대 반복
3. 대형폐기물 배출 방법 문의 반복
4. 복지 지원 기준/신청 절차 불편 반복
5. 악취/냄새/하수 민원 야간 집중
6. 공공자전거/앱 예약·대여 UX 불편
7. 부서 처리 지연/미처리 누적
8. 재민원/반복 민원 증가
9. 소음/공사 민원 특정 시간대 집중
10. 접근성/고령자·장애인 이용 어려움
11. 가로등/보안등 고장 반복
12. 낮은 건수 negative scenario
13. 지역/시간 분산 negative scenario

## 최신 평가 결과

### Fake provider

리포트: `reports/complaint_intelligence_eval_report_after_fake.json`

| 지표 | 값 |
| --- | ---: |
| overall_pass_rate | 1.0 |
| alert_recall | 1.0 |
| expected_topic_hit_rate | 1.0 |
| fallback_rate | 0.0 |
| pii_leak_rate | 0.0 |
| forbidden_ai_ops_term_rate | 0.0 |

### Local LLM: exaone3.5:7.8b

리포트: `reports/complaint_intelligence_eval_report_local_action_rubric.json`

| 지표 | 값 |
| --- | ---: |
| scenario_count | 13 |
| overall_pass_rate | 0.8462 |
| alert_recall | 1.0 |
| expected_topic_hit_rate | 1.0 |
| direct_llm_success_rate | 1.0 |
| fallback_rate | 0.0 |
| required_action_type_hit_rate | 0.9231 |
| human_review_requirement_pass_rate | 1.0 |
| pii_leak_rate | 0.0 |
| forbidden_ai_ops_term_rate | 0.0 |
| avg_llm_duration_ms | 133673.558 |
| p95_llm_duration_ms | 159262.161 |
| total_duration_seconds | 1470.627 |

이전 Local full 평가 대비:

| 지표 | 이전 | 현재 |
| --- | ---: | ---: |
| overall_pass_rate | 0.5385 | 0.8462 |
| fallback_rate | 0.0909 | 0.0 |
| direct_llm_success_rate | 0.9091 | 1.0 |
| required_action_type_hit_rate | 0.6154 | 0.9231 |
| human_review_requirement_pass_rate | 0.9231 | 1.0 |
| avg_llm_duration_ms | 148790.284 | 133673.558 |
| p95_llm_duration_ms | 197981.512 | 159262.161 |

## 남은 실패/한계

Local LLM 평가에서 13개 중 2개 scenario가 실패했습니다.

| scenario | 실패 사유 | 해석 |
| --- | --- | --- |
| 재민원/반복 민원 증가 | `REQUIRED_ASPECT_MISSING` | aspect extractor가 재접수/반복 민원 신호를 더 명시적으로 승격해야 함 |
| 소음/공사 민원 특정 시간대 집중 | `REQUIRED_ASPECT_MISSING`, `REQUIRED_ACTION_TYPE_MISSING` | 시간대/소음 aspect와 단속/프로세스 조치 분리가 더 필요함 |

이번 변경은 action_type/human_review 안정화에 초점을 맞췄고, 남은 문제는 aspect extractor와 scenario-specific topic/action 매핑을 추가 개선하는 영역입니다.

## 테스트 결과

실행 명령:

```powershell
civil\Scripts\python.exe -m compileall app\complaint_intelligence scripts\evaluate_complaint_intelligence_scenarios.py
civil\Scripts\python.exe -m pytest app\tests\unit -q
```

결과:

```text
663 passed, 3 warnings in 46.42s
```

경고는 sklearn pickle 버전 경고이며 이번 Complaint Intelligence 변경과 직접 관련 없습니다.

## FE 연결 준비 상태

FE는 다음 순서로 연결 가능합니다.

1. `GET /complaint-intelligence/dashboard`로 summary, issue_alerts, public_insights 조회
2. issue card에서 `linked_insight_ids`로 행정 인사이트 탭 필터링
3. insight card에서 `recommended_actions`, `top_aspects`, `citizen_requests`, `requires_human_review` 표시
4. 관리자/검증 화면에서 `GET /public-insights/{insight_id}/evidence-pack` 연결

## 운영 전 권장 후속 작업

1. 재민원/소음 시간대 aspect extractor 보강
2. Local LLM 비동기 job/queue 또는 scheduler 중심 운영 전환
3. 지도 좌표 정규화 및 지역 centroid 개선
4. LLM observability 리포트 장기 누적
5. 운영 데이터 기반 threshold 재조정

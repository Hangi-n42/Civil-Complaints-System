# Complaint Intelligence 평가 보고서

- Provider: `fake`
- Scenario count: `13`
- Overall pass rate: `0.538`

## 전체 지표

| 축 | 지표 | 값 |
| --- | --- | ---: |
| IssueAlert | alert_recall | 0.636 |
| IssueAlert | alert_precision_on_negative | 1.000 |
| IssueAlert | false_positive_count | 0 |
| IssueAlert | false_negative_count | 4 |
| PublicAgencyInsight | expected_type_hit_rate | 0.909 |
| PublicAgencyInsight | required_aspect_hit_rate | 1.000 |
| PublicAgencyInsight | required_action_type_hit_rate | 1.000 |
| PublicAgencyInsight | action_evidence_coverage_rate | 0.923 |
| PublicAgencyInsight | avg_grounding_score | 0.923 |
| PublicAgencyInsight | avg_confidence | 0.786 |
| PublicAgencyInsight | avg_actionability_score | 0.923 |
| PublicAgencyInsight | pii_leak_rate | 0.000 |
| PublicAgencyInsight | forbidden_ai_ops_term_rate | 0.000 |

## Scenario별 결과

| Scenario | Pass | Alert | Insight Type | 주요 실패 |
| --- | --- | ---: | --- | --- |
| 도로 침하/싱크홀 급증 | True | 1 | SAFETY_RISK_SIGNAL, SAFETY_RISK_SIGNAL, RECURRING_COMPLAINT_PATTERN | - |
| 불법주정차 특정 시간대 반복 | True | 1 | HOTSPOT_RESPONSE_REQUIRED, SAFETY_RISK_SIGNAL, RECURRING_COMPLAINT_PATTERN | - |
| 대형폐기물 배출 방법 문의 반복 | False | 1 | HOTSPOT_RESPONSE_REQUIRED, RECURRING_COMPLAINT_PATTERN, REGIONAL_SERVICE_GAP | ISSUE_TOPIC_MISMATCH |
| 복지 지원 기준/신청 절차 불편 반복 | True | 1 | RECURRING_COMPLAINT_PATTERN, REGIONAL_SERVICE_GAP, PUBLIC_GUIDANCE_NEEDED | - |
| 악취/냄새/하수 민원 야간 집중 | False | 1 | RECURRING_COMPLAINT_PATTERN, REGIONAL_SERVICE_GAP, PUBLIC_GUIDANCE_NEEDED | ISSUE_TOPIC_MISMATCH |
| 공공자전거/앱 예약·대여 UX 불편 | False | 0 | PUBLIC_GUIDANCE_NEEDED, POLICY_IMPROVEMENT_OPPORTUNITY, SERVICE_DESIGN_IMPROVEMENT | ISSUE_ALERT_MISSING |
| 부서 처리 지연/미처리 누적 | False | 0 | PUBLIC_GUIDANCE_NEEDED, POLICY_IMPROVEMENT_OPPORTUNITY, CITIZEN_COMMUNICATION_GAP | ISSUE_ALERT_MISSING |
| 재민원/반복 민원 증가 | False | 0 | PUBLIC_GUIDANCE_NEEDED, SERVICE_DESIGN_IMPROVEMENT, DEPARTMENT_WORKLOAD_BOTTLENECK | ISSUE_ALERT_MISSING, EXPECTED_INSIGHT_TYPE_MISSING |
| 소음/공사 민원 특정 시간대 집중 | True | 1 | HOTSPOT_RESPONSE_REQUIRED, RECURRING_COMPLAINT_PATTERN, REGIONAL_SERVICE_GAP | - |
| 접근성/고령자·장애인 이용 어려움 | False | 0 | PUBLIC_GUIDANCE_NEEDED, ACCESSIBILITY_OR_USABILITY_ISSUE, CITIZEN_COMMUNICATION_GAP | ISSUE_ALERT_MISSING |
| 가로등/보안등 고장 반복 | True | 1 | SAFETY_RISK_SIGNAL, RECURRING_COMPLAINT_PATTERN, REGIONAL_SERVICE_GAP | - |
| 낮은 건수라 alert가 뜨면 안 되는 상황 | True | 0 | - | - |
| 같은 키워드지만 지역·시간이 분산된 non-hotspot | True | 0 | PUBLIC_GUIDANCE_NEEDED, FACILITY_MAINTENANCE_PRIORITY, POLICY_IMPROVEMENT_OPPORTUNITY | - |

## 잘된 점
- 실제 run_analysis 경로에서 IssueAlert, PublicAgencyInsight, EvidencePack을 함께 평가했습니다.
- 추천 조치의 evidence id 연결, PII, 금지 AI 운영 용어를 scenario별로 검사했습니다.
- positive/negative scenario를 함께 두어 recall과 false positive 위험을 분리했습니다.

## 미흡한 점
- 기대된 hotspot scenario 일부에서 IssueAlert가 생성되지 않았습니다.

## 개선 제안
- IssueDetection의 의미 군집/지역·시간 기준을 scenario별로 재점검해야 합니다.

## Local LLM manual 평가

```powershell
civil\Scripts\python.exe scripts\evaluate_complaint_intelligence_scenarios.py --provider local --model exaone3.5:7.8b-instruct --base-url http://localhost:11434 --output reports\complaint_intelligence_eval_report_local.json
```

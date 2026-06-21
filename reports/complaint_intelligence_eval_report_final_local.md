# Complaint Intelligence 평가 보고서

- Provider: `local`
- Scenario requested/evaluated: `25` / `25`
- Scenario count: `25`
- Overall pass rate: `1.000`
- Limited reason: `-`
- Checkpoint resume: `True`
- Checkpoint dir: `reports\complaint_intelligence_eval_checkpoints`

## 전체 지표

| 축 | 지표 | 값 |
| --- | --- | ---: |
| IssueAlert | alert_recall | 1.000 |
| IssueAlert | alert_precision_on_negative | 1.000 |
| IssueAlert | false_positive_count | 0 |
| IssueAlert | false_negative_count | 0 |
| PublicAgencyInsight | expected_type_hit_rate | 1.000 |
| PublicAgencyInsight | required_aspect_hit_rate | 1.000 |
| PublicAgencyInsight | required_action_type_hit_rate | 1.000 |
| PublicAgencyInsight | allowed_action_type_hit_rate | 0.920 |
| PublicAgencyInsight | action_type_rubric_pass_rate | 1.000 |
| PublicAgencyInsight | action_evidence_coverage_rate | 0.920 |
| PublicAgencyInsight | avg_grounding_score | 0.920 |
| PublicAgencyInsight | avg_confidence | 0.778 |
| PublicAgencyInsight | avg_actionability_score | 0.920 |
| PublicAgencyInsight | pii_leak_rate | 0.000 |
| PublicAgencyInsight | forbidden_ai_ops_term_rate | 0.000 |
| PublicAgencyInsight | human_review_requirement_pass_rate | 1.000 |
| LLM | direct_llm_success_count | 23 |
| LLM | fallback_count | 0 |
| LLM | fallback_rate | 0.000 |
| LLM | direct_llm_success_rate | 1.000 |
| LLM | fallback_due_to_empty_actions_count | 0 |
| LLM | invalid_evidence_id_count | 0 |
| LLM | invalid_action_type_count | 1 |
| LLM | repaired_action_type_count | 3 |
| LLM | repaired_action_text_count | 10 |
| LLM | removed_action_due_to_action_type_count | 0 |
| LLM | action_repair_success_count | 0 |
| LLM | human_review_postprocess_count | 16 |
| LLM | action_retry_attempt_count | 0 |
| LLM | action_retry_success_count | 0 |
| LLM | json_parse_failure_count | 0 |
| LLM | schema_validation_failure_count | 0 |
| LLM | avg_llm_duration_ms | 146977.9 |
| LLM | avg_retry_duration_ms | 0.0 |
| LLM | p95_llm_duration_ms | 176541.9 |
| LLM | total_duration_seconds | 3381.0 |

## Local LLM 안정성 추적

- Slowest scenarios: `pet_waste_leash_complaints, smoking_enforcement_recurring, school_zone_commute_safety, construction_noise_time_pattern, illegal_dumping_recurring`
- Timeout scenarios: `-`
- Fallback scenarios: `-`

## 목표 기준

| 목표 | 기준 | 달성 |
| --- | --- | --- |
| fallback_rate | <=0.25 | True |
| direct_llm_success_rate | >=0.75 | True |
| json_parse_failure_count | 0 | True |
| schema_validation_failure_count | 0 | True |
| pii_leak_rate | 0 | True |
| forbidden_ai_ops_term_rate | 0 | True |

## Scenario별 결과

| Scenario | Pass | Alert | Insight Type | 주요 실패 |
| --- | --- | ---: | --- | --- |
| 도로 침하/싱크홀 급증 | True | 1 | SAFETY_RISK_SIGNAL | - |
| 불법주정차 특정 시간대 반복 | True | 4 | HOTSPOT_RESPONSE_REQUIRED | - |
| 대형폐기물 배출 방법 문의 반복 | True | 4 | PUBLIC_GUIDANCE_NEEDED | - |
| 복지 지원 기준/신청 절차 불편 반복 | True | 4 | PUBLIC_GUIDANCE_NEEDED | - |
| 악취/냄새/하수 민원 야간 집중 | True | 2 | HOTSPOT_RESPONSE_REQUIRED | - |
| 공공자전거/앱 예약·대여 UX 불편 | True | 3 | ACCESSIBILITY_OR_USABILITY_ISSUE | - |
| 부서 처리 지연/미처리 누적 | True | 2 | PROCESS_DELAY_RISK | - |
| 재민원/반복 민원 증가 | True | 1 | REOPEN_OR_REPEAT_RISK | - |
| 소음/공사 민원 특정 시간대 집중 | True | 3 | RECURRING_COMPLAINT_PATTERN | - |
| 접근성/고령자·장애인 이용 어려움 | True | 3 | SERVICE_DESIGN_IMPROVEMENT | - |
| 가로등/보안등 고장 반복 | True | 4 | RECURRING_COMPLAINT_PATTERN | - |
| 침수/배수 불량 위험 | True | 3 | SAFETY_RISK_SIGNAL | - |
| 무단투기/쓰레기 적치 반복 | True | 3 | PUBLIC_GUIDANCE_NEEDED | - |
| 공원/놀이터 시설 파손 및 이용 안전 | True | 2 | SAFETY_RISK_SIGNAL | - |
| 가로등/보안등 고장 반복 확장 | True | 4 | HOTSPOT_RESPONSE_REQUIRED | - |
| 버스 정류장/노선·배차 불편 | True | 2 | SERVICE_DESIGN_IMPROVEMENT | - |
| CCTV/방범 안전 설치 요청 | True | 4 | SAFETY_RISK_SIGNAL | - |
| 흡연/금연구역 단속 반복 | True | 3 | PUBLIC_GUIDANCE_NEEDED | - |
| 불법 광고물/현수막 정비 | True | 2 | FACILITY_MAINTENANCE_PRIORITY | - |
| 반려동물 배설물/목줄/유기동물 민원 | True | 4 | REGIONAL_SERVICE_GAP | - |
| 인허가/자격·서류 기준 안내 혼선 | True | 2 | PUBLIC_GUIDANCE_NEEDED | - |
| 장애인·고령자·외국인 접근성/이용 어려움 | True | 2 | PUBLIC_GUIDANCE_NEEDED | - |
| 어린이보호구역/통학 안전 | True | 2 | SAFETY_RISK_SIGNAL | - |
| 낮은 건수라 alert가 뜨면 안 되는 상황 | True | 0 | - | - |
| 같은 키워드지만 지역·시간이 분산된 non-hotspot | True | 0 | - | - |

## 잘된 점
- 실제 run_analysis 경로에서 IssueAlert, PublicAgencyInsight, EvidencePack을 함께 평가했습니다.
- 추천 조치의 evidence id 연결, PII, 금지 AI 운영 용어를 scenario별로 검사했습니다.
- positive/negative scenario를 함께 두어 recall과 false positive 위험을 분리했습니다.

## 미흡한 점
- 현재 평가 세트에서는 치명적 품질 실패가 두드러지지 않았습니다.

## 개선 제안
- 실제 운영 로그와 local LLM 결과를 누적해 scenario 난이도를 단계적으로 높이는 것이 좋습니다.

## Local LLM manual 평가

```powershell
civil\Scripts\python.exe scripts\evaluate_complaint_intelligence_scenarios.py --provider local --model exaone3.5:7.8b --base-url http://localhost:11434 --prompt-mode compact --output reports\complaint_intelligence_eval_report_local.json
```

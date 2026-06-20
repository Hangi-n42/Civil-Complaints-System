# Complaint Intelligence 평가 보고서

- Provider: `local`
- Scenario count: `3`
- Overall pass rate: `1.000`

## 전체 지표

| 축 | 지표 | 값 |
| --- | --- | ---: |
| IssueAlert | alert_recall | 1.000 |
| IssueAlert | alert_precision_on_negative | 0.000 |
| IssueAlert | false_positive_count | 0 |
| IssueAlert | false_negative_count | 0 |
| PublicAgencyInsight | expected_type_hit_rate | 1.000 |
| PublicAgencyInsight | required_aspect_hit_rate | 1.000 |
| PublicAgencyInsight | required_action_type_hit_rate | 1.000 |
| PublicAgencyInsight | action_evidence_coverage_rate | 1.000 |
| PublicAgencyInsight | avg_grounding_score | 1.000 |
| PublicAgencyInsight | avg_confidence | 0.846 |
| PublicAgencyInsight | avg_actionability_score | 1.000 |
| PublicAgencyInsight | pii_leak_rate | 0.000 |
| PublicAgencyInsight | forbidden_ai_ops_term_rate | 0.000 |
| LLM | direct_llm_success_count | 2 |
| LLM | fallback_count | 1 |
| LLM | fallback_rate | 0.333 |
| LLM | json_parse_failure_count | 0 |
| LLM | schema_validation_failure_count | 0 |
| LLM | avg_llm_duration_ms | 138408.2 |

## Scenario별 결과

| Scenario | Pass | Alert | Insight Type | 주요 실패 |
| --- | --- | ---: | --- | --- |
| 도로 침하/싱크홀 급증 | True | 1 | SAFETY_RISK_SIGNAL | - |
| 불법주정차 특정 시간대 반복 | True | 2 | HOTSPOT_RESPONSE_REQUIRED | - |
| 대형폐기물 배출 방법 문의 반복 | True | 2 | PUBLIC_GUIDANCE_NEEDED | - |

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

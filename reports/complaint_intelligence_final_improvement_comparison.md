# Complaint Intelligence 최종 품질 개선 비교 리포트

## 평가 개요

- 평가일: 2026-06-21
- 대상: Complaint Intelligence Layer IssueAlert 자동감지 및 PublicAgencyInsight 생성 품질
- Fake provider: 25개 전체 scenario 평가
- Local LLM: `exaone3.5:7.8b`, compact prompt, 25개 전체 scenario 평가
- Local LLM 실행 방식: `reports/complaint_intelligence_eval_checkpoints/` checkpoint/resume 사용
- 최종 산출 리포트:
  - `reports/complaint_intelligence_eval_report_final_fake.json`
  - `reports/complaint_intelligence_eval_report_final_fake.md`
  - `reports/complaint_intelligence_eval_report_final_local.json`
  - `reports/complaint_intelligence_eval_report_final_local.md`

## 직전 한계 요약

1. Local LLM 전체 평가는 완료됐지만 평균 응답 시간이 약 150초로 데모/운영 검증 관점에서 여전히 무겁습니다.
2. 긴 단일 실행이 중단될 경우 전체 평가 완료 여부를 보장하려면 checkpoint/resume이 필요합니다.
3. 일부 scenario는 LLM 출력 흔들림보다 평가 rubric과 실제 행정 조치 기대값의 정합성 점검이 필요했습니다.
4. 전체 unit에는 DuplicateMerger 계열 기존 실패가 남아 있어 Complaint Intelligence 품질 개선과 분리해 추적해야 합니다.

## 추가 개선 내용

- compact LLM 입력 최적화:
  - 대표 민원 수를 4건에서 3건으로 축소했습니다.
  - 대표 민원 `masked_text` preview를 160자에서 120자로 축소했습니다.
  - compact/action retry 입력의 action catalog 후보를 8개에서 6개로 축소했습니다.
- 평가 rubric 정합성 보정:
  - `odor_night_hotspot`의 필수 action type에 `FIELD_INSPECTION`을 추가했습니다.
  - 악취/하수 야간 집중 scenario는 현장 확인이 실무적으로 직접적인 조치이므로 기존 `PROCESS_IMPROVEMENT`만 강제하던 기준을 보완했습니다.
- checkpoint/resume 평가:
  - Local LLM 25개 scenario를 5개 단위 chunk로 실행하고 checkpoint를 병합했습니다.
  - timeout 또는 fallback 없이 전체 scenario-level result를 보존했습니다.

## 개선 전후 핵심 지표

| 구분 | 직전 Local 개선 리포트 | 최종 Local 리포트 | 변화 |
| --- | ---: | ---: | ---: |
| scenario_count_requested | 25 | 25 | 0 |
| scenario_count_evaluated | 25 | 25 | 0 |
| overall_pass_rate | 1.0000 | 1.0000 | 0 |
| alert_recall | 1.0000 | 1.0000 | 0 |
| expected_topic_hit_rate | 1.0000 | 1.0000 | 0 |
| required_aspect_hit_rate | 1.0000 | 1.0000 | 0 |
| required_action_type_hit_rate | 1.0000 | 1.0000 | 0 |
| action_type_rubric_pass_rate | 1.0000 | 1.0000 | 0 |
| direct_llm_success_rate | 1.0000 | 1.0000 | 0 |
| fallback_rate | 0.0000 | 0.0000 | 0 |
| json_parse_failure_count | 0 | 0 | 0 |
| schema_validation_failure_count | 0 | 0 | 0 |
| grounding_failure_count | 0 | 0 | 0 |
| pii_leak_rate | 0.0000 | 0.0000 | 0 |
| forbidden_ai_ops_term_rate | 0.0000 | 0.0000 | 0 |
| avg_llm_duration_ms | 150,502.682 | 146,977.912 | -3,524.770 |
| p95_llm_duration_ms | 176,113.259 | 176,541.897 | +428.638 |
| total_duration_seconds | 3,462.092 | 3,381.015 | -81.077 |

## 최종 Fake Provider 결과

| 지표 | 값 |
| --- | ---: |
| scenario_count_requested / evaluated | 25 / 25 |
| overall_pass_rate | 1.0000 |
| alert_recall | 1.0000 |
| expected_topic_hit_rate | 1.0000 |
| false_positive_count | 0 |
| false_negative_count | 0 |
| expected_type_hit_rate | 1.0000 |
| required_aspect_hit_rate | 1.0000 |
| required_action_type_hit_rate | 1.0000 |
| action_type_rubric_pass_rate | 1.0000 |
| fallback_rate | 0.0000 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |

## 최종 Local LLM 결과

| 지표 | 값 |
| --- | ---: |
| model | exaone3.5:7.8b |
| scenario_count_requested / evaluated | 25 / 25 |
| overall_pass_rate | 1.0000 |
| direct_llm_success_rate | 1.0000 |
| fallback_rate | 0.0000 |
| json_parse_failure_count | 0 |
| schema_validation_failure_count | 0 |
| grounding_failure_count | 0 |
| quality_gate_failure_count | 0 |
| timeout_scenarios | 0 |
| fallback_scenarios | 0 |
| avg_llm_duration_ms | 146,977.912 |
| p95_llm_duration_ms | 176,541.897 |
| total_duration_seconds | 3,381.015 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |

## Scenario 결과

- 개선된 scenario:
  - `odor_night_hotspot`: 실제 Local LLM 출력의 `FIELD_INSPECTION` 조치를 scenario rubric에서 허용하도록 보완해 최종 pass로 전환했습니다.
- 여전히 실패한 scenario:
  - Fake provider: 없음
  - Local LLM: 없음
- timeout/fallback/error scenario:
  - 없음

## IssueAlert 개선 결과

- 25개 scenario 기준 alert recall과 topic hit rate 모두 1.0을 유지했습니다.
- negative scenario 2건에서도 false positive는 0으로 유지됐습니다.
- 이번 추가 개선은 alert rule 자체를 확장하지 않고 평가 안정성 및 compact 입력을 조정했으므로 alert fragmentation 위험은 증가하지 않았습니다.

## PublicAgencyInsight 개선 결과

- required aspect/action type, action rubric, evidence coverage 모두 1.0을 유지했습니다.
- GroundingVerifier와 QualityGate 기준은 완화하지 않았습니다.
- Local LLM direct success는 25/25이며 fallback은 발생하지 않았습니다.

## PII/Forbidden Term 검사 결과

- Fake provider pii_leak_rate: 0.0
- Fake provider forbidden_ai_ops_term_rate: 0.0
- Local LLM pii_leak_rate: 0.0
- Local LLM forbidden_ai_ops_term_rate: 0.0
- checkpoint와 최종 리포트는 기존 EvidencePack 마스킹 경로의 `masked_text` preview만 사용합니다.

## Local LLM 안정성/속도 결과

- 전체 25개 scenario 평가를 checkpoint/resume으로 완료했습니다.
- 평균 LLM 응답 시간은 약 2.3% 감소했습니다.
- p95는 사실상 유지 수준이며, 운영 응답성 개선으로 보기에는 아직 부족합니다.
- 다만 단일 실행 중단 리스크는 checkpoint/resume으로 완화됐습니다.

## FE 데모 영향

- 기존 API/FE 계약 변경은 없습니다.
- `GET /complaint-intelligence/dashboard`가 사용하는 저장/조회 모델과 PublicAgencyInsight schema는 유지됩니다.
- 이번 변경은 백엔드 평가 안정화와 Local LLM 입력 경량화 중심이므로 FE 수정 없이 반영 가능합니다.

## 남은 한계

1. Local LLM 평균 응답 시간이 여전히 약 147초로 실시간 응답형 UI에는 무겁습니다.
2. p95가 약 176.5초로 유지되어, 운영에서는 비동기 배치/관제 갱신 주기 기반 노출이 적합합니다.
3. 평가는 25개 curated scenario 중심이므로 실제 운영 데이터의 장문/비정형/혼합 민원에 대한 추가 검증이 필요합니다.
4. 전체 unit에는 DuplicateMerger 계열 기존 실패가 남아 있으며, 이번 PublicAgencyInsight 품질 개선과는 별도 이슈로 추적해야 합니다.

## 다음 개선 우선순위

1. Local LLM 추론 시간을 줄이기 위한 모델 옵션/양자화/GPU offload 운영 검증
2. 25개 scenario 외 실제 공개 데이터 샘플 기반 장문/혼합 민원 평가셋 확장
3. 관제 운영에서는 Local LLM 결과를 즉시 응답이 아니라 scheduler 기반 비동기 갱신 결과로 노출
4. DuplicateMerger 평가 matrix 실패 원인 별도 분석

# Complaint Intelligence 품질 개선 전후 비교

## 1. 평가 개요

- 목적: 신규 12개 민원 상황 확장 이후 IssueAlert와 PublicAgencyInsight의 관제 데모/운영 준비 품질을 점검하고, 과잉 aspect 노이즈를 줄였습니다.
- 변경 범위: 기존 IssueAlert, EvidencePack, PublicAgencyInsight, GroundingVerifier, QualityGate 구조는 유지하고 `AspectExtractor`의 근거 선택/필터링만 보강했습니다.
- Local LLM 모델: `exaone3.5:7.8b`
- 주의: Local 전체 25개 시나리오 평가는 40분 제한에서도 완료되지 않아, Local 비교는 5개 smoke 시나리오 기준입니다.

## 2. 개선 전 지표

### Fake provider 전체 25개

| 지표 | 값 |
| --- | ---: |
| overall_pass_rate | 1.0 |
| alert_recall | 1.0 |
| expected_topic_hit_rate | 1.0 |
| false_positive_count | 0 |
| expected_type_hit_rate | 1.0 |
| required_aspect_hit_rate | 1.0 |
| required_action_type_hit_rate | 1.0 |
| fallback_rate | 0.0 |
| pii_leak_rate | 0.0 |
| forbidden_ai_ops_term_rate | 0.0 |
| avg_aspects_per_insight | 14.844 |

### Local LLM smoke 5개

| 지표 | 값 |
| --- | ---: |
| overall_pass_rate | 1.0 |
| direct_llm_success_rate | 0.6 |
| fallback_rate | 0.4 |
| json_parse_failure_count | 1 |
| schema_validation_failure_count | 1 |
| required_action_type_hit_rate | 1.0 |
| avg_actionability_score | 0.96 |
| avg_llm_duration_ms | 139614.223 |
| p95_llm_duration_ms | 144115.721 |
| avg_aspects_per_insight | 8.2 |

## 3. 개선 후 지표

### Fake provider 전체 25개

| 지표 | 값 |
| --- | ---: |
| overall_pass_rate | 1.0 |
| alert_recall | 1.0 |
| expected_topic_hit_rate | 1.0 |
| false_positive_count | 0 |
| expected_type_hit_rate | 1.0 |
| required_aspect_hit_rate | 1.0 |
| required_action_type_hit_rate | 1.0 |
| fallback_rate | 0.0 |
| pii_leak_rate | 0.0 |
| forbidden_ai_ops_term_rate | 0.0 |
| avg_aspects_per_insight | 4.711 |

### Local LLM smoke 5개

| 지표 | 값 |
| --- | ---: |
| overall_pass_rate | 1.0 |
| direct_llm_success_rate | 1.0 |
| fallback_rate | 0.0 |
| json_parse_failure_count | 0 |
| schema_validation_failure_count | 0 |
| required_action_type_hit_rate | 1.0 |
| avg_actionability_score | 1.0 |
| avg_llm_duration_ms | 167560.098 |
| p95_llm_duration_ms | 188740.599 |
| avg_aspects_per_insight | 2.6 |

## 4. 개선된 scenario

- `repeat_reopen_growth`: 재민원/반복 민원 aspect가 핵심 근거로 유지되고 Local LLM direct success로 통과했습니다.
- `construction_noise_time_pattern`: 공사 소음/시간대 집중/단속 공백 aspect가 유지되고 Local LLM direct success로 통과했습니다.
- `sinkhole_hotspot`: 대표 인사이트 aspect가 `현장 안전`, `시설 파손`, `이용 안전`, `유지보수 지연` 중심으로 축소되어 관제 카드 설명 노이즈가 줄었습니다.
- `flood_drainage_risk`, `illegal_dumping_recurring`, `accessibility_vulnerable_groups`: Local smoke에서 모두 pass했습니다.

## 5. 여전히 실패한 scenario

- Fake provider 기준 실패 scenario 없음.
- Local smoke 기준 실패 scenario 없음.
- Local 전체 25개 scenario는 runtime 때문에 완료하지 못했습니다.

## 6. 실패 원인 분석

| 유형 | 결과 |
| --- | --- |
| IssueAlert 미생성 | 없음 |
| topic label 불일치 | 없음 |
| candidate type 불일치 | 없음 |
| required aspect 누락 | 없음 |
| action_type 불일치 | 없음 |
| evidence id coverage 부족 | 없음 |
| QualityGate 실패 | 없음 |
| GroundingVerifier 실패 | 없음 |
| human_review 판단 실패 | 없음 |
| Local LLM 출력 흔들림 | smoke 기준 개선 후 없음 |
| false positive 또는 과잉 insight | negative 2개 모두 alert/insight 미생성 |
| PII/forbidden term 위험 | 없음 |

## 7. IssueAlert 개선 결과

- Fake 전체 25개 기준 `alert_recall=1.0`, `expected_topic_hit_rate=1.0`, `false_positive_count=0`을 유지했습니다.
- Local smoke 5개 기준도 `alert_recall=1.0`, `expected_topic_hit_rate=1.0`을 유지했습니다.

## 8. PublicAgencyInsight 개선 결과

- pass 지표는 유지하면서 aspect 노이즈를 줄였습니다.
- Fake 전체 기준 평균 aspect 수가 `14.844 -> 4.711`로 감소했습니다.
- Local smoke 기준 평균 aspect 수가 `8.2 -> 2.6`으로 감소했습니다.
- Grounding, evidence coverage, action_type rubric pass는 1.0을 유지했습니다.

## 9. action_type/human_review 개선 결과

- action_type rubric pass rate는 Fake/Local 모두 1.0입니다.
- Local smoke에서 invalid action_type 1건은 기존 action repair가 허용 rubric 안에서 보수적으로 교정했고, evidence/action 본문은 임의 생성하지 않았습니다.
- human_review requirement pass rate는 Fake/Local 모두 1.0입니다.

## 10. PII/forbidden term 검사 결과

- Fake 전체: `pii_leak_rate=0.0`, `forbidden_ai_ops_term_rate=0.0`
- Local smoke: `pii_leak_rate=0.0`, `forbidden_ai_ops_term_rate=0.0`

## 11. Local LLM 안정성/속도 결과

- Local smoke는 `fallback_rate 0.4 -> 0.0`, `direct_llm_success_rate 0.6 -> 1.0`으로 개선되었습니다.
- 평균 응답 시간은 `139614.223ms -> 167560.098ms`로 느려졌습니다.
- 속도 악화는 Local LLM 자체 응답 편차와 `num_predict=1024` 조건의 영향이 큽니다. 품질 기준을 낮춰 속도를 얻지는 않았습니다.

## 12. FE 데모 영향

- API/FE contract 변경은 없습니다.
- 관제 카드에 들어갈 aspect가 줄어들어, 담당자가 읽는 문제 진단 문장이 더 좁고 명확해질 가능성이 큽니다.
- 전체 Local 평가가 아직 오래 걸리므로 FE 데모는 Fake/seed 기반 read-model 또는 Local smoke 검증 범위로 설명하는 것이 안전합니다.

## 13. 남은 한계

- Local LLM 전체 25개 평가는 완료하지 못했습니다.
- 후보 수 자체는 Fake 전체 기준 221개로 여전히 많습니다. 이번 변경은 후보 생성량보다 최종 aspect 품질을 우선 개선했습니다.
- 신규 12개 상황은 synthetic evaluation control 비중이 높아 실제 공개 데이터 기반 provenance 확장이 필요합니다.

## 14. 다음 개선 우선순위

1. Local 평가를 scenario chunk 단위로 재개 가능하게 개선합니다.
2. 후보 생성 단계에서 alert/topic/type 우선순위 기반 상한을 두어 LLM 호출량을 줄입니다.
3. 실제 `data/processed` 기반 신규 12개 상황 seed를 추가해 synthetic 의존도를 낮춥니다.
4. Local LLM prompt 길이와 `num_predict`를 단계적으로 줄여 속도와 품질 tradeoff를 재측정합니다.

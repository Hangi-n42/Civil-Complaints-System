# Complaint Intelligence 운영 품질 최종 비교 리포트

## 평가 개요

- 평가일: 2026-06-21
- 범위: IssueAlert 감지 품질, PublicAgencyInsight 품질, Local LLM 운영 준비도, holdout robustness
- Local LLM 모델: `exaone3.5:7.8b`
- Curated 평가셋: 25개 scenario
- Holdout 평가셋: 실제 processed 데이터 기반 50건

## DuplicateMerger 실패 해결

전체 unit에서 남아 있던 `test_duplicate_merger_operational_scenario_matrix` 실패를 해결했습니다.

원인:

- `도로침하`, `도로파임`, `싱크홀` 같은 이슈 주제 엔티티가 세부 위치로 오인됐습니다.
- 그 결과 같은 `중앙로12길` 민원인데도 location conflict로 분류되어 candidate 생성 전에 탈락했습니다.
- 또한 정상 한국어 요청 유형 키워드가 깨진 문자열 목록에 의존해 safety/inquiry 분류가 불안정했습니다.

수정:

- 한국어 요청 유형 키워드를 `classify_request_type` 앞단에 추가했습니다.
- 위치 신호 추출에서 이슈 주제 엔티티를 제외했습니다.
- 위험 pair는 그룹 candidate로 만들되 `SAFETY_AND_INCONVENIENCE_MIXED` blocker로 자동 병합을 막는 기존 contract를 복구했습니다.

검증:

- `app/tests/unit/test_duplicate_merger_evaluation_matrix.py`: `2 passed, 1 xpassed`

## PR 산출물 정리

유지:

- 최종 fake/local JSON/Markdown report
- holdout build/eval report
- 최종 비교 리포트
- 운영 정책 문서
- FE handoff 문서

제외:

- scenario별 checkpoint 개별 JSON
- 중간 baseline/improved/smoke report
- raw LLM response 또는 prompt dump

## Compact LLM 품질 우선 재조정

직전 latency 최적화에서 줄였던 compact LLM 입력을 품질 우선으로 완화했습니다.

| 항목 | 직전 설정 | 최종 설정 |
| --- | ---: | ---: |
| representative_complaints | 3건 | 5건 |
| evidence preview | 120자 | 220자 |
| action retry representative_complaints | 3건 | 4건 |
| action retry preview | 120자 | 180자 |
| allowed_action_catalog | 6개 | 8개 |

QualityGate/GroundingVerifier 기준은 완화하지 않았습니다.

## Curated 25 - Fake Provider 결과

| 지표 | 값 |
| --- | ---: |
| scenario_count_requested/evaluated | 25 / 25 |
| overall_pass_rate | 1.0000 |
| alert_recall | 1.0000 |
| expected_topic_hit_rate | 1.0000 |
| false_positive_count | 0 |
| expected_type_hit_rate | 1.0000 |
| required_aspect_hit_rate | 1.0000 |
| required_action_type_hit_rate | 1.0000 |
| action_type_rubric_pass_rate | 1.0000 |
| fallback_rate | 0.0000 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |

## Curated 25 - Local LLM 결과

| 지표 | 값 |
| --- | ---: |
| scenario_count_requested/evaluated | 25 / 25 |
| overall_pass_rate | 1.0000 |
| direct_llm_success_rate | 1.0000 |
| fallback_rate | 0.0000 |
| json_parse_failure_count | 0 |
| schema_validation_failure_count | 0 |
| grounding_failure_count | 0 |
| timeout_scenarios | 0 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |
| avg_llm_duration_ms | 172,596.998 |
| p95_llm_duration_ms | 208,595.557 |
| total_duration_seconds | 3,970.780 |

## Latency 변화

| 구분 | 직전 최종 리포트 | 품질 우선 재조정 후 |
| --- | ---: | ---: |
| avg_llm_duration_ms | 146,977.912 | 172,596.998 |
| p95_llm_duration_ms | 176,541.897 | 208,595.557 |
| total_duration_seconds | 3,381.015 | 3,970.780 |

해석:

- 평균 latency는 약 25.6초 증가했습니다.
- p95는 약 32.1초 증가했습니다.
- 이번 작업은 latency보다 공공기관 담당자에게 보여줄 행정 인사이트 품질을 우선한 조정입니다.
- 운영 UX는 동기 생성 대기가 아니라 scheduler/read-model 조회 방식을 유지해야 합니다.

## Holdout 50 구성 방식

- 입력 파일: `data/processed/processed_consulting_data.json`
- 총 50건
- real_text_count: 50
- synthetic_count: 0
- PII 마스킹 적용: true
- 분포:
  - 안전/시설: 10
  - 단속/생활질서: 10
  - 안내/절차/서류: 10
  - 서비스/앱/접근성: 8
  - 처리 지연/재민원/소통: 7
  - 기타/혼합/negative: 5

## Holdout 50 - Fake Provider 평가 결과

Holdout은 정답 label 기반 성능 평가가 아니라 open-world robustness/qualitative readiness 점검입니다.

| 지표 | 값 |
| --- | ---: |
| input_event_count | 50 |
| generated_alert_count | 13 |
| generated_insight_count | 48 |
| candidate_count | 48 |
| high_priority_insight_count | 1 |
| direct_llm_success_rate | 1.0000 |
| fallback_rate | 0.0000 |
| grounding_pass_rate | 1.0000 |
| avg_grounding_score | 1.0000 |
| avg_confidence | 0.7896 |
| avg_actionability_score | 1.0000 |
| evidence_pack_presence_rate | 1.0000 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |

주의:

- 실제 processed 데이터에는 민원 본문과 답변 일부가 같이 포함된 사례가 있어, holdout 결과는 운영 성능 단정이 아니라 파이프라인 견고성 점검으로 해석해야 합니다.
- Local LLM holdout 전체는 후보 48개가 생성되어 동기 실행 비용이 매우 큽니다. 운영 정책상 candidate cap/scheduler 우선순위 기반 비동기 평가로 분리하는 것이 적절합니다.

## PII/Forbidden Term 검사

- Curated Fake: PII 0, forbidden AI ops term 0
- Curated Local: PII 0, forbidden AI ops term 0
- Holdout Fake: PII 0, forbidden AI ops term 0
- raw response와 prompt dump는 저장하지 않았습니다.

## FE 데모 영향

- FE/API breaking change는 없습니다.
- FE는 `GET /complaint-intelligence/dashboard` read-model을 조회하면 됩니다.
- EvidencePack은 관리자/검증 화면에서만 열고, 일반 카드에는 masked preview와 evidence count만 표시해야 합니다.

## 운영 정책 요약

- IssueAlert는 빠른 주기로 갱신합니다.
- PublicAgencyInsight는 우선순위 candidate 중심으로 비동기 생성합니다.
- 같은 topic/region/type은 TTL/dedupe window 안에서 재생성을 억제합니다.
- LLM 실패, QualityGate 실패, PII 복구 실패는 fallback/보류/discard 정책으로 처리합니다.

## 남은 한계

1. 품질 우선 입력 확대로 Local LLM latency가 다시 증가했습니다.
2. Holdout은 실제 텍스트 기반이지만 정답 label이 없어 precision/recall로 해석할 수 없습니다.
3. processed 데이터 특성상 민원 원문과 답변이 섞인 케이스가 있어 추후 민원 본문만 분리한 holdout이 필요합니다.
4. Local LLM holdout 전체는 candidate 48개 기준 장시간이 예상되어 이번 리포트에서는 Fake provider robustness 평가로 제한했습니다.

## 다음 개선 우선순위

1. holdout 원문에서 민원 본문과 답변 분리
2. Local LLM candidate cap과 scheduler 우선순위 실행 정책 구현
3. 실제 운영 로그 기반 holdout 확장
4. FE 관리자 화면에서 EvidencePack masked preview만 열람하도록 권한 분리

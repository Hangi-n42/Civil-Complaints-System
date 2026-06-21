# Complaint Intelligence Holdout 50 평가 리포트

## 평가 개요

- provider: `fake`
- model: `-`
- input_event_count: `50`
- generated_alert_count: `13`
- generated_insight_count: `48`
- candidate_count: `48`
- duration_seconds: `1.219`

## 품질 지표

| 지표 | 값 |
| --- | ---: |
| fallback_rate | 0.0000 |
| direct_llm_success_rate | 1.0000 |
| grounding_pass_rate | 1.0000 |
| avg_grounding_score | 1.0000 |
| avg_confidence | 0.7896 |
| avg_actionability_score | 1.0000 |
| evidence_pack_presence_rate | 1.0000 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |

## 주요 alert

- `대형폐기물 배출 안내` / `서구` / severity `CRITICAL` / related `10`
- `대형폐기물 배출 안내` / `중구` / severity `CRITICAL` / related `10`
- `공원 시설 파손` / `광역시` / severity `CRITICAL` / related `4`
- `복지 지원 신청/기준 안내` / `남구` / severity `CRITICAL` / related `8`
- `복지 지원 신청/기준 안내` / `동구` / severity `CRITICAL` / related `10`
- `복지 지원 신청/기준 안내` / `북구` / severity `CRITICAL` / related `7`
- `- 처리 지연/미처리 누적` / `북구` / severity `WARNING` / related `6`
- `재민원/반복 민원 증가` / `서구` / severity `WARNING` / related `23`
- `무단투기 반복` / `중구` / severity `WARNING` / related `6`
- `CCTV/방범 안전 요청` / `중구` / severity `WARNING` / related `3`

## 주요 insight

- `SAFETY_RISK_SIGNAL` / `무단투기 반복` / priority `MEDIUM` / actions `FIELD_INSPECTION`
- `HOTSPOT_RESPONSE_REQUIRED` / `버스 노선/배차 불편` / priority `MEDIUM` / actions `SERVICE_DESIGN`
- `HOTSPOT_RESPONSE_REQUIRED` / `무단투기 반복` / priority `MEDIUM` / actions `FIELD_INSPECTION`
- `HOTSPOT_RESPONSE_REQUIRED` / `금연구역 흡연 단속 필요` / priority `MEDIUM` / actions `ENFORCEMENT`
- `SAFETY_RISK_SIGNAL` / `CCTV/방범 안전 요청` / priority `HIGH` / actions `FIELD_INSPECTION`
- `HOTSPOT_RESPONSE_REQUIRED` / `복지 지원 신청/기준 안내` / priority `MEDIUM` / actions `PUBLIC_GUIDANCE`
- `HOTSPOT_RESPONSE_REQUIRED` / `복지 지원 신청/기준 안내` / priority `MEDIUM` / actions `PUBLIC_GUIDANCE`
- `PROCESS_DELAY_RISK` / `처리 지연` / priority `LOW` / actions `PROCESS_IMPROVEMENT`
- `PROCESS_DELAY_RISK` / `- 처리 지연/미처리 누적` / priority `MEDIUM` / actions `STAFFING_OR_WORKLOAD_REVIEW`
- `SAFETY_RISK_SIGNAL` / `불법주정차` / priority `MEDIUM` / actions `ENFORCEMENT`

## 실패/주의 항목

- 치명적 실패는 확인되지 않았습니다.

## 해석 주의

- holdout은 정답 label이 없는 open-world robustness 평가이므로 pass rate를 성능 주장으로 해석하지 않습니다.
- 생성된 insight는 EvidencePack, GroundingVerifier, QualityGate 경로를 통과한 최종 read-model 기준입니다.
- raw PII와 prompt 원문은 리포트에 저장하지 않았습니다.

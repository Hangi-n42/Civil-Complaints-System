# Duplicate Merge Labeled Evaluation Report

## Summary

- total_pairs: 100
- precision: 1.0
- recall: 1.0
- false_positive_rate: 0.0
- blocker_recall: 1.0
- risk_flag_hit_rate: 1.0
- pii_leak_rate: 0.0
- elapsed_ms: 205.77
- average_ms_per_pair: 2.0577
- problem_result_count: 0

## Category Counts

| category | count | tp | fp | tn | fn |
| --- | ---: | ---: | ---: | ---: | ---: |
| PII risk | 25 | 25 | 0 | 0 | 0 |
| same event different request | 25 | 25 | 0 | 0 | 0 |
| same keyword different event | 25 | 0 | 0 | 25 | 0 |
| true duplicate | 25 | 25 | 0 | 0 | 0 |

## Quality Gates

| gate | result |
| --- | ---: |
| true duplicate recall | 25/25 |
| same keyword different event false positives | 0 |
| same event different request risk flag hit rate | 1.0 |
| blocker recall | 1.0 |
| PII leak rate | 0.0 |

## Risk Flag Counts

| risk_flag | count |
| --- | ---: |
| LEGAL_RIGHTS_OR_DEADLINE_RISK | 15 |
| PII_RISK | 40 |
| REQUEST_TYPE_MISMATCH | 25 |
| SAFETY_AND_INCONVENIENCE_MIXED | 5 |

## Problem Examples

- 현재 100쌍 평가셋 기준 실패 pair, risk miss, PII leak은 없다.

## Notes

- true duplicate, same keyword different event, same event different request, PII risk를 각각 25쌍으로 구성했다.
- PII risk 사례는 합성 전화번호, 이메일, 상세주소만 사용했다.
- 후보 생성은 실제 민원 상태를 변경하지 않으며, draft payload는 confirmed 그룹에서만 평가했다.

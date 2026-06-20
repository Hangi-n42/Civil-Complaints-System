# Complaint Intelligence 개선 전후 비교

| 지표 | Delta |
| --- | ---: |
| alert_recall_delta | 0.3636 |
| topic_hit_rate_delta | 0.5455 |
| false_positive_delta | 0 |
| false_negative_delta | -4 |
| expected_type_hit_rate_delta | 0.0909 |
| avg_actionability_score_delta | -0.0769 |
| pii_leak_rate_delta | 0.0000 |
| forbidden_ai_ops_term_rate_delta | 0.0000 |

## 좋아진 점
- IssueAlert recall이 baseline보다 개선되었습니다.
- IssueAlert topic hit rate가 baseline보다 개선되었습니다.
- negative scenario의 false positive count를 유지했습니다.
- false negative count가 감소했습니다.

## 악화/주의
- 확인된 regression은 없습니다.

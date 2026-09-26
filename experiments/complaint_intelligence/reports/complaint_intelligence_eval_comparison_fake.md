> 과거 실험 기록 · 보관 문서 v1.0 · 정리일 2026-09-26
> 원래 경로: `reports/complaint_intelligence_eval_comparison_fake.md`. 원작성일·실험 조건·수치·결론은 당시 기록이며 현재 성능 확인 결과가 아니다.
> 관련 JSON 산출물: [기존 경로 유지](../../../reports/complaint_intelligence_eval_comparison_fake.json). 현재 파일이 이후 재생성될 수 있으므로 실행 시점/모델/데이터 일치를 확인한다.

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

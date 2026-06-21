# request_segments strict allow 후보 수집 리포트

## 요약

| 지표 | 값 |
| --- | ---: |
| pre-gate allow candidates | 1252 |
| LLM called | 929 |
| strict allow collected | 500 |
| strict allow / called | 53.8% |
| collection complete | True |
| hallucination suspected | 3 |

## latency

- avg: 14.74
- p50: 12.847
- p95: 26.874
- max: 40.665

## gate counts

```json
{
  "review_required": 343,
  "allow_assist": 500,
  "reject": 86
}
```

## reject/review reason

```json
{
  "llm_under_rule_segments": 193,
  "none": 500,
  "too_many_evidence_blocks": 90,
  "invalid_llm_segment_count": 30,
  "phone_dialogue_over_split": 13,
  "segment_too_long_for_assist": 15,
  "keep_rule": 14,
  "weak_request_signal:0": 14,
  "weak_request_signal:1": 5,
  "low_value_or_admin_segment:3": 1,
  "invalid_json": 3,
  "segment_too_short_for_action": 9,
  "segment_count_expanded_too_much": 14,
  "missing_text_or_evidence_ids:0": 5,
  "invalid_segment_count": 1,
  "weak_request_signal:3": 1,
  "multi_request_single_segment": 3,
  "weak_request_cue": 3,
  "weak_request_signal:2": 2,
  "long_legal_or_proposal_over_split": 12,
  "abstain": 1
}
```

## 주의

이 파일의 strict allow는 validator/gate 통과 후보이며 사람 검수 정답이 아니다.

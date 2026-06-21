# request_segments pre-gate shadow 평가

## 평가 설정

- mode: reuse
- seed: 20260620
- sample_size: 200
- model: exaone3.5:7.8b
- reuse_json: reports\request_segment_llm_pregate_shadow_eval.json

## 핵심 지표

| 지표 | 값 |
| --- | ---: |
| fallback candidates | 200 |
| pre_gate allow_call | 22 |
| pre_gate skipped | 178 |
| LLM called | 22 |
| LLM call rate | 11.0% |
| validation accepted | 19 |
| strict allow_assist | 12 |
| strict allow / total | 6.0% |
| hallucination suspected | 0 |

## latency

- avg: 12.902
- p50: 12.404
- p95: 19.064
- max: 20.241

## pre_gate 분포

```json
{
  "skip_shadow_only": 162,
  "allow_call": 22,
  "review_required": 16
}
```

## strict gate 분포

```json
{
  "not_evaluated": 178,
  "allow_assist": 12,
  "reject": 3,
  "review_required": 7
}
```

## reject/review reason

```json
{
  "not_list_trigger_candidate": 162,
  "none": 12,
  "keep_rule": 1,
  "too_many_evidence_blocks": 2,
  "excluded_fallback_reason:segment_too_long": 2,
  "llm_under_rule_segments": 4,
  "excluded_risk_tag:phone_dialogue": 13,
  "weak_request_signal:0": 2,
  "segment_too_long_for_assist": 1,
  "weak_source_block_request_cue": 1
}
```

## 해석

이 평가는 accepted/allow를 사람 검수 정답으로 간주하지 않는다. strict allow는 내부 실험 후보이며, BE3 action-item 확정값으로 바로 쓰면 안 된다.

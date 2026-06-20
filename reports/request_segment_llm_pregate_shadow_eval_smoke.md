# request_segments pre-gate shadow 평가

## 평가 설정

- mode: live
- seed: 20260620
- sample_size: 5
- model: exaone3.5:7.8b
- reuse_json: -

## 핵심 지표

| 지표 | 값 |
| --- | ---: |
| fallback candidates | 5 |
| pre_gate allow_call | 1 |
| pre_gate skipped | 4 |
| LLM called | 1 |
| LLM call rate | 20.0% |
| validation accepted | 1 |
| strict allow_assist | 1 |
| strict allow / total | 20.0% |
| hallucination suspected | 0 |

## latency

- avg: 23.377
- p50: 23.377
- p95: 23.377
- max: 23.377

## pre_gate 분포

```json
{
  "skip_shadow_only": 4,
  "allow_call": 1
}
```

## strict gate 분포

```json
{
  "not_evaluated": 4,
  "allow_assist": 1
}
```

## reject/review reason

```json
{
  "not_list_trigger_candidate": 4,
  "null": 1
}
```

## 해석

이 평가는 accepted/allow를 사람 검수 정답으로 간주하지 않는다. strict allow는 내부 실험 후보이며, BE3 action-item 확정값으로 바로 쓰면 안 된다.

> 과거 실험 기록 · 보관 문서 v1.0 · 정리일 2026-09-26
> 원래 경로: `reports/request_segment_llm_pregate_shadow_eval.md`. 원작성일·실험 조건·수치·결론은 당시 기록이며 현재 성능 확인 결과가 아니다.
> 관련 JSON 산출물: [기존 경로 유지](../../../reports/request_segment_llm_pregate_shadow_eval.json). 현재 파일이 이후 재생성될 수 있으므로 실행 시점/모델/데이터 일치를 확인한다.

# request_segments pre-gate shadow 평가

## 평가 설정

- mode: live
- seed: 20260620
- sample_size: 200
- model: exaone3.5:7.8b
- reuse_json: -

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

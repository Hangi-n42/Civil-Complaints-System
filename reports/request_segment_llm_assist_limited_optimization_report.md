# request_segments LLM assist 제한 최적화 보고서

## 1. 작업 배경

`request_segments`는 BE3 action-item과 FE 복합 민원 UI의 기준이 되므로, LLM 결과를 바로 신뢰값으로 쓰면 안 된다. 기존 구조는 규칙 기반 `complexity_analyzer.py`를 1차 판정기로 두고, 불확실한 케이스만 `request_segment_hybrid.py`에서 EXAONE 기반 shadow/assist 후보로 검증한다.

이전 검증에서 조건 B(source block + evidence_ids + `num_predict=256`)는 조건 A보다 안정적이었고, 사람 검수 100건 replay에서 `assist_limited_v2 strict`는 12건 allow 중 12건 pass였다. 다만 커버리지는 낮고 LLM latency가 높아, 이번 작업은 비용을 줄이는 pre-gate와 partial 원인 방어용 후처리를 추가하는 데 초점을 맞췄다.

## 2. Phase 1 - pre-gate 설계/구현

### 계획

- LLM 호출 전에 runtime에서 관측 가능한 cheap signal만으로 호출 필요성을 먼저 판단한다.
- `v2_strict` 정책에서만 pre-gate를 강하게 적용하고, `policy=none`은 기존 동작을 유지한다.
- allow 후보는 `numbered_under_split`, `heading_list_under_split`처럼 명확한 목록형 미분할 신호로 제한한다.
- 전화 대화체, 장문 법령/정책, segment limit, weak request signal 같은 위험군은 LLM 호출 전 `review_required` 또는 `skip_shadow_only`로 보낸다.

### 제3자 관점 평가

- 장점: strict gate에서 어차피 탈락할 위험군의 LLM 호출을 줄일 수 있다.
- 위험: allow 조건을 너무 좁히면 strict allow 후보까지 놓칠 수 있다.
- 판단: 이전 replay에서 strict allow가 목록형 trigger에 집중되어 있었으므로, `v2_strict`에 한해 목록형 중심 pre-gate를 두는 것은 안전성이 더 크다.

### 구현

- `app/retrieval/analyzers/request_segment_hybrid.py`
  - `LLMPreGateResult`, `assess_llm_pre_gate()` 추가
  - hybrid wrapper에 `llm_pre_gate`, `llm_pre_gate_reason`, `llm_pre_gate_rejected_reason`, `llm_pre_gate_risk_tags` trace 추가
  - pre-gate가 `allow_call`이 아니면 LLM을 호출하지 않고 규칙 기반 결과를 유지
- `app/tests/unit/test_request_segment_hybrid.py`
  - pre-gate allow/skip/review 케이스와 LLM 미호출 보장 테스트 추가

### 검증

- 단위 테스트: `35 passed`
- pre-gate는 기본 `off` 모드에는 영향을 주지 않고, `shadow/assist + v2_strict`에서만 호출 전 차단 역할을 한다.

## 3. Phase 2 - pre-gate 적용 후 EXAONE shadow 200건 평가

### 평가 설정

- 모델: `exaone3.5:7.8b`
- 방식: 조건 B(source block + evidence_ids + `num_predict=256`)
- seed: `20260620`
- 대상: 규칙 기반 fallback 후보 200건
- 산출물:
  - `reports/request_segment_llm_pregate_shadow_eval.json`
  - `reports/request_segment_llm_pregate_shadow_eval.md`

### 결과

| 지표 | 값 |
| --- | ---: |
| fallback candidates | 200 |
| pre_gate allow_call | 22 |
| pre_gate skipped/review | 178 |
| 실제 LLM 호출률 | 11.0% |
| validation accepted | 19/22 |
| accepted rate among called | 86.4% |
| strict allow_assist | 12 |
| strict allow / total | 6.0% |
| strict allow / called | 54.5% |
| hallucination suspected | 0 |
| latency avg / p50 / p95 / max | 12.902s / 12.404s / 19.064s / 20.241s |

### 해석

- pre-gate는 같은 fallback 후보군에서 LLM 호출을 22건으로 제한했다. 호출당 latency는 줄지 않지만, 불필요한 호출을 줄여 전체 비용/지연을 크게 낮춘다.
- strict allow는 12건으로, 커버리지는 여전히 낮다.
- allow는 사람 검수 정답이 아니라 validator/gate 통과 후보이므로 BE3 action-item 확정값으로 바로 쓰면 안 된다.

## 4. Phase 3 - partial 후처리 보강

### 문제 분석

사람 검수 100건에서 partial/fail 원인은 주로 다음이었다.

- 너무 추상적인 segment
- action-item으로 약한 표현
- 조건/수단/고려사항을 독립 요청처럼 분리
- rule 대비 LLM segment 수가 부적절하게 변함
- 전화 대화체/장문 문맥 혼동

### 계획

- LLM 재호출 없이 strict gate 주변에서만 보수적인 품질 게이트를 추가한다.
- runtime에서 관측 가능한 segment text만 사용한다.
- 사람 검수 필드(`human_judgment`, `human_note`)는 운영 조건에 사용하지 않는다.

### 제3자 관점 평가

- 장점: partial로 이어지기 쉬운 generic/actionability 약한 segment를 내부 실험 전에 review로 돌릴 수 있다.
- 위험: 과도한 reject는 좋은 목록형 pass 후보를 줄일 수 있다.
- 판단: 너무 일반적인 표현과 조건/고려사항 단독 표현만 차단하고, 명확한 요청/질의 표현은 그대로 통과시키는 방식이 안전하다.

### 구현

- `assess_segment_actionability()` 추가
  - `조치 요청`, `이용 방법 문의`, `안전 고려 요청`처럼 너무 일반적인 표현은 `generic_weak_actionability`
  - `... 고려사항`, `... 검토사항`처럼 독립 요청이 아닌 조건/수단 표현은 `method_or_condition_only_segment`
  - 너무 짧고 actionability가 약한 표현은 `segment_too_short_for_action`
- `evaluate_assist_limited_v2_strict_gate()`에서 validation 통과 후 최종 allow 전에 이 품질 게이트를 적용
- 테스트 추가:
  - generic segment reject
  - method/condition-only segment reject
  - actionable request 통과
  - 좋은 numbered list segment allow 유지

## 5. Phase 4 - 후처리 보강 후 동일 후보 재평가

### 평가 설정

- Phase 2와 동일한 200건 후보 사용
- 실제 LLM 재호출 없이 `reports/request_segment_llm_pregate_shadow_eval.json`의 raw response 재사용
- 산출물:
  - `reports/request_segment_llm_pregate_postprocess_shadow_eval.json`
  - `reports/request_segment_llm_pregate_postprocess_shadow_eval.md`

### 결과 비교

| 지표 | pre-gate 후 | 후처리 보강 후 |
| --- | ---: | ---: |
| fallback candidates | 200 | 200 |
| LLM called | 22 | 22 |
| LLM call rate | 11.0% | 11.0% |
| validation accepted | 19 | 19 |
| strict allow_assist | 12 | 12 |
| strict allow / total | 6.0% | 6.0% |
| review_required | 7 | 7 |
| reject | 3 | 3 |
| hallucination suspected | 0 | 0 |

### 해석

- 이번 200건 표본에서는 새 후처리 게이트가 기존 strict allow 12건을 줄이지 않았다.
- 이는 보강이 공격적으로 동작하지 않았다는 의미다.
- 다만 이번 표본에 generic/actionability 약한 allow 후보가 없었기 때문에, 실제 품질 개선 폭은 추가 사람 검수로만 확인할 수 있다.

## 6. 기존 결과와 종합 비교

| 기준 | 샘플 | LLM 호출률 | accepted | strict/assist allow | 사람 검수 해석 |
| --- | ---: | ---: | ---: | ---: | --- |
| 조건 B shadow 100 | 100 | 100.0% | 79 | assist_limited 후보 21 | 전체 pass 57%, pass+partial 78% |
| v2 strict replay | 100 | replay | - | 12 | 12/12 pass, internal experiment 가능 |
| pre-gate shadow 200 | 200 | 11.0% | 19/22 | 12 | 사람 검수 전 validator/gate 후보 |
| postprocess reuse 200 | 200 | 11.0% | 19/22 | 12 | 기존 allow 유지, 약한 segment 방어 추가 |

주의: 위 표의 100건과 200건은 서로 다른 표본이므로 직접적인 정확도 비교가 아니라 운영성 판단 참고 지표다.

## 7. 최종 정책 판단

- 기본 운영 모드: `off` 또는 `shadow` 유지
- 내부 제한 실험: `REQUEST_SEGMENT_LLM_MODE=assist` + `REQUEST_SEGMENT_LLM_ASSIST_POLICY=v2_strict`
- full mode: 비권장
- BE3 action-item 확정값으로 즉시 사용: 비권장
- 권장 gate 판단: `assist_limited_internal_experiment_ready`

pre-gate 덕분에 LLM 호출률은 낮아졌지만, allow 커버리지는 6% 수준으로 낮다. 따라서 실사용 기능으로 바로 확대하기보다, strict allow 후보만 내부 검수/실험 경로에서 쓰는 것이 적절하다.

## 8. BE3/FE/Multi-Agent Routing 전달사항

- 규칙 기반 analyzer는 계속 1차 판정기다.
- LLM hybrid는 불확실 케이스의 보조 후보이며, 기본값으로 사용자 응답이나 FE 복합 민원 모드에 직접 반영하지 않는다.
- `v2_strict` allow 후보는 번호/heading/list형 미분할 케이스에 한정된 내부 실험 후보로 볼 수 있다.
- 전화 대화체, 장문 법령/정책, 장문 제안서, weak request signal 단독 케이스는 계속 shadow/review 대상으로 남긴다.
- FE에는 기존 `request_segments`, `intent_count`, `is_multi` 계약 변화가 없다.

## 9. 남은 리스크

- allow 후보가 사람 검수 정답이라는 보장은 없다.
- 커버리지가 낮아 실제 사용자 체감 개선은 제한적일 수 있다.
- EXAONE 호출당 latency는 여전히 10초 이상으로 높다.
- 200건 postprocess 평가는 raw response 재사용 기반이므로, 프롬프트나 모델 상태 변화는 반영하지 않는다.
- partial 후처리의 실제 precision 개선은 별도 사람 검수로 확인해야 한다.

## 10. 다음 단계

1. `pre-gate + postprocess` 기준 strict allow 후보 50~100건을 별도 사람 검수한다.
2. allow precision이 90% 이상 유지되면 BE3 내부 관리자/검수 플로우에서 제한 실험한다.
3. latency 문제는 비동기 shadow 평가, 캐시, 관리자 후처리 플로우로 우회하는 것이 현실적이다.
4. 기본 assist/full 전환은 사람 검수 precision과 운영 latency가 모두 확인된 뒤 재논의한다.

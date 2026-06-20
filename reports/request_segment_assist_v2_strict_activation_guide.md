# request_segments assist + v2_strict 제한 가동 가이드

## 1. 배경

`request_segments` LLM hybrid fallback은 규칙 기반 `complexity_analyzer.py`를 1차 판정기로 유지하고, 불확실한 케이스에서만 별도 wrapper인 `request_segment_hybrid.py`가 EXAONE 후보를 검증한다. 이번 가이드는 전면 assist가 아니라 `assist + v2_strict` 제한 가동을 준비하기 위한 운영 설정과 확인 항목을 정리한다.

## 2. 품질 근거

- strict allow 수집: 500건
- pass: 466
- partial: 33
- fail: 1
- pass rate: 93.2%
- fail rate: 0.2%
- 100건 단위 pass rate: 92.5~93.2%
- strict allow 내부 evidence_id 오류: 없음
- 판단: `assist_limited_ready_for_controlled_rollout`

주의: strict allow도 사람 검수 전에는 정답이 아니라 교체 후보이다. 위 수치는 제한 rollout 가능성을 뒷받침하지만, full mode나 기본 assist 활성화를 의미하지 않는다.

## 3. 왜 full이 아니라 assist + v2_strict인가

조건 B(source block + evidence_ids + `num_predict=256`)와 v2_strict gate는 다음을 모두 통과한 경우에만 LLM segment 교체를 허용한다.

- pre-gate 통과
- EXAONE 조건 B 응답 생성
- evidence_ids validator 통과
- actionability 후처리 통과
- `v2_strict` runtime gate 통과
- 위험군 제외

반대로 `REQUEST_SEGMENT_LLM_MODE=assist`만 켜고 `REQUEST_SEGMENT_LLM_ASSIST_POLICY=none`인 상태는 위험하므로, 현재 runtime은 gate가 `allow_assist`가 아닌 경우 항상 규칙 기반 결과를 유지한다. 알 수 없는 policy 값도 `none`으로 정규화되어 교체되지 않는다.

## 4. 활성화 환경변수

제한 assist 가동 시 아래 값을 함께 설정한다.

```env
REQUEST_SEGMENT_LLM_MODE=assist
REQUEST_SEGMENT_LLM_ASSIST_POLICY=v2_strict
REQUEST_SEGMENT_LLM_PROVIDER=ollama
REQUEST_SEGMENT_LLM_MODEL=exaone3.5:7.8b
REQUEST_SEGMENT_LLM_PROMPT_STYLE=block
REQUEST_SEGMENT_LLM_BLOCK_NUM_PREDICT=256
REQUEST_SEGMENT_LLM_SOURCE_BLOCK_LIMIT=30
```

`REQUEST_SEGMENT_LLM_PROMPT_STYLE=block`은 필수다. 이 값이 빠지면 v2_strict gate가 `non_block_prompt_style`로 교체를 막는다.

## 5. 롤백 환경변수

문제가 생기면 즉시 shadow 또는 off로 되돌린다.

```env
REQUEST_SEGMENT_LLM_MODE=shadow
```

또는:

```env
REQUEST_SEGMENT_LLM_MODE=off
```

`shadow`는 LLM 후보 검증 trace만 남기고 실제 `request_segments`를 교체하지 않는다. `off`는 LLM 호출 자체를 하지 않는다.

## 6. 적용 범위

교체 가능 후보는 v2_strict gate가 허용한 케이스에 한정한다.

- 번호/heading/list형 미분할 신호
- source block evidence_id가 원문 block과 매칭되는 케이스
- actionability가 명확한 segment
- rule 대비 LLM segment 수가 과도하게 줄거나 늘지 않은 케이스

## 7. 제외 범위

다음 유형은 계속 rule 유지 또는 review/shadow 대상으로 둔다.

- phone dialogue
- long legal/policy
- long proposal
- weak request signal 단독
- segment_limit 위험군
- evidence_id 오류
- schema failure
- 너무 추상적인 segment
- 조건/수단/고려사항만 독립 요청처럼 분리된 segment

## 8. trace 확인 방법

운영 중 `complexity_trace`에서 최소 다음 필드를 확인한다.

| 필드 | 의미 |
| --- | --- |
| `request_segments_source` | `rule` 또는 `llm_fallback` |
| `llm_fallback_mode` | `off`, `shadow`, `assist` |
| `llm_assist_policy` | `none` 또는 `v2_strict` |
| `llm_pre_gate` | `allow_call`, `skip_shadow_only`, `review_required` |
| `llm_pre_gate_rejected_reason` | LLM 호출 전 차단 이유 |
| `llm_segments_accepted` | validator 통과 여부 |
| `llm_segments_rejected_reason` | validator reject 이유 |
| `llm_assist_gate` | `allow_assist`, `shadow_only`, `review_required`, `reject` |
| `llm_assist_gate_reason` | gate 판단 이유 |
| `llm_assist_gate_rejected_reason` | 실제 교체가 막힌 이유 |
| `llm_hallucination_suspected` | evidence/hallucination 의심 여부 |

실제 교체는 `request_segments_source=llm_fallback`이고 `llm_assist_policy=v2_strict`, `llm_assist_gate=allow_assist`인 경우에만 발생해야 한다.

## 9. 운영 후 최소 모니터링 지표

- LLM 호출 수
- fallback 후보 수
- pre-gate 통과 수
- pre-gate skip/review 수
- validation accepted 수
- strict allow 수
- 실제 assist 적용 수(`request_segments_source=llm_fallback`)
- fallback to rule 수
- 평균 latency / P95 latency
- schema failure 수
- evidence_id 오류 수
- hallucination suspected 수
- reject reason 분포
- partial/fail 의심 샘플 수동 검수 결과

## 10. 긴급 롤백 기준

다음 중 하나라도 관측되면 즉시 `shadow` 또는 `off`로 되돌린다.

- evidence_id 오류가 strict allow에 포함됨
- hallucination suspected가 교체 결과에 포함됨
- BE3 action-item 매핑에서 과분할/저분할 오류가 반복됨
- latency P95가 운영 SLA를 지속적으로 초과함
- FE 복합 민원 모드 오탐이 증가함
- `REQUEST_SEGMENT_LLM_MODE=assist`인데 policy가 `v2_strict`가 아닌 설정이 발견됨

## 11. BE3/FE 핸드오프

- 외부 DTO 변경 없음
- `request_segments`, `intent_count`, `is_multi` 계약 유지
- FE 변경 필요 없음
- BE3는 기존 `request_segments`를 그대로 사용하면 됨
- debug/metadata 용도로는 `complexity_trace.request_segments_source`, `llm_assist_policy`, `llm_assist_gate`를 참고할 수 있음
- `request_segments_source=llm_fallback`인 경우에도 v2_strict 제한 후보라는 뜻이지, 최종 정답 보장은 아님
- full mode는 사용하지 말 것

## 12. 남은 리스크

- strict allow 500건 검수 결과는 높게 나왔지만 실제 운영 트래픽 분포와 완전히 같지는 않다.
- partial 33건의 주요 원인은 저분할/과분할 가능성이므로 운영 중 샘플 검수가 계속 필요하다.
- EXAONE 호출 latency는 여전히 높아 동기 사용자 요청 경로에서는 부담이 될 수 있다.
- controlled rollout 중에도 기본값은 `off` 또는 `shadow`로 유지하고, 운영 환경변수로만 제한 활성화한다.

## 13. PR #441 리뷰 대응 보강 사항

Codex 리뷰에서 지적된 P2 이슈 4건을 반영했다.

- 운영 runtime 경로는 이제 `build_request_segment_analysis()` selector를 통해 진입한다.
  - `REQUEST_SEGMENT_LLM_MODE=off`이면 기존 `build_analyzer_output()` rule-only 결과를 반환한다.
  - `REQUEST_SEGMENT_LLM_MODE=shadow` 또는 `assist`이면 `request_segment_hybrid.py`의 `build_analyzer_output_hybrid()`를 호출한다.
  - 적용 호출부: retrieval routing payload, generation trace fallback, generation request segment fallback, prompt factory trace 보강 경로.
- 두 자리 번호 marker 회귀를 막기 위해 `10.`, `11.` 같은 orphan marker도 다음 문장과 병합하도록 보강했다.
- LLM replacement 응답은 `confidence`가 필수다.
  - `replace` 응답에서 confidence 누락은 `missing_confidence`로 reject한다.
  - 숫자가 아닌 confidence는 `invalid_confidence`로 reject한다.
  - `keep_rule`/`abstain`은 rule 유지 결정이므로 교체로 accepted되지 않는다.
- block/evidence_ids 응답은 evidence_id 존재 여부뿐 아니라 segment text가 cited evidence block에 의해 뒷받침되는지 확인한다.
  - 핵심 객체/숫자/행정 객체 토큰 overlap이 부족하면 `segment_not_supported_by_evidence:{index}`로 reject한다.
  - `요청`, `문의`, `가능`, `방법` 같은 일반어만 겹치는 경우는 support로 보지 않는다.

주의: `shadow`/`assist + v2_strict`를 활성화하면 API route의 현재 sync 흐름에서 EXAONE 호출 latency가 요청 지연으로 반영될 수 있다. 기본값은 계속 `off`이며, 운영 가동 시에는 P95 latency와 fallback-to-rule 비율을 반드시 같이 확인한다.

# request_segments assist_limited_v2 runtime 정책

## 작업 배경

조건 B(source block + `evidence_ids` + `num_predict=256`) 방식은 EXAONE shadow 평가와 100건 사람 검수에서 조건 A보다 안전한 근거 검증 특성을 보였다. 다만 전체 accepted 결과를 그대로 `request_segments`로 교체하기에는 precision이 부족했다.

사람 검수 100건과 replay 분석 결과, `assist_limited_v2 strict` 조건에서는 allow 12건이 모두 pass였고 fail은 0건이었다. 따라서 이 정책은 운영 기본값이 아니라 내부 제한 실험용 runtime 옵션으로만 둔다.

## 기본값

기본값은 기존 동작을 바꾸지 않는다.

```powershell
REQUEST_SEGMENT_LLM_MODE=off
REQUEST_SEGMENT_LLM_ASSIST_POLICY=none
```

- `off`: LLM 호출 없음
- `shadow`: LLM 호출/검증/trace만 수행, 결과 교체 없음
- `assist`: 검증 통과 시 결과 교체 가능
- `REQUEST_SEGMENT_LLM_ASSIST_POLICY=none`: 기존 assist 동작 유지
- `REQUEST_SEGMENT_LLM_ASSIST_POLICY=v2_strict`: 조건 B strict gate 통과 시에만 교체

## mode별 동작

| mode | assist policy | 동작 |
| --- | --- | --- |
| `off` | any | LLM 호출 없음. 규칙 기반 결과 유지 |
| `shadow` | `none` | LLM 후보 검증 및 trace 기록. 결과 교체 없음 |
| `shadow` | `v2_strict` | strict gate 판단까지 trace 기록. 결과 교체 없음 |
| `assist` | `none` | 기존 assist 동작 유지 |
| `assist` | `v2_strict` | 조건 B block validation과 strict gate를 모두 통과할 때만 LLM segment로 교체 |

## strict allow 조건

runtime에서는 사람 검수 필드(`human_judgment`, `human_note`)를 사용하지 않는다. 다음처럼 실행 시점에 관측 가능한 신호만 사용한다.

- 조건 B block prompt 결과여야 함
- LLM validation 통과
- `fallback_reasons`에 `numbered_under_split` 또는 `heading_list_under_split` 포함
- 제외 fallback reason 없음:
  - `weak_request_signal`
  - `possible_over_split`
  - `phone_dialogue_uncertain`
  - `segment_too_long`
- 제외 risk tag 없음:
  - `phone_dialogue`
  - `long_legal_or_policy`
  - `long_proposal`
  - `segment_limit_case`
  - `weak_request_signal`
- 전화 대화체 마커 없음
- LLM segment 수 1~3개
- rule segment 수가 4개 이하이면 LLM segment 수가 rule segment 수보다 작지 않음
- evidence reference 수가 LLM segment 수보다 많지 않음
- 각 segment 길이 70자 이하
- 각 segment가 요청/질의 cue를 포함
- 한 segment 안에 여러 요청 cue를 문장 결합 형태로 뭉개지 않음

## gate 결과

strict gate는 다음 중 하나를 남긴다.

- `allow_assist`: LLM 결과로 교체 가능
- `shadow_only`: 목록형 assist 후보가 아니므로 규칙 기반 결과 유지
- `review_required`: 위험 신호가 있어 규칙 기반 결과 유지
- `reject`: LLM validation 실패 등으로 규칙 기반 결과 유지

## trace 필드

외부 response schema는 바꾸지 않고 `complexity_trace` 내부에만 기록한다.

- `llm_assist_policy`: `none` 또는 `v2_strict`
- `llm_assist_gate`: `allow_assist`, `shadow_only`, `review_required`, `reject`, `not_evaluated`
- `llm_assist_gate_reason`: gate 판단 사유
- `llm_assist_gate_rejected_reason`: `allow_assist`가 아닐 때의 reject/review 사유
- `llm_assist_gate_risk_tags`: gate에서 감지한 위험 태그
- `llm_assist_gate_evidence_count`: LLM 응답의 evidence reference 수
- `llm_prompt_style`: `text` 또는 `block`
- `llm_source_block_count`: 조건 B block prompt에 전달된 source block 수

## BE3/FE/Multi-Agent Routing 영향

- BE3/FE 계약은 변경하지 않는다.
- `request_segments`, `intent_count`, `is_multi` 형식은 유지된다.
- `assist + v2_strict`는 내부 제한 실험용이다.
- FE 복합 민원 모드나 BE3 action-item 확정값으로 바로 쓰는 것은 권장하지 않는다.
- strict allow 후보는 내부 실험/검수 경로에서만 사용하고, 전화 대화체/장문 법령/약한 요청 신호는 계속 shadow/review로 둔다.

## 기존 100건 replay와 runtime gate 비교

구현 후 기존 100건 검수 결과에 runtime gate를 재적용했다. strict allow 건수와 품질 구성은 replay 결과와 동일하게 유지됐다.

- strict allow: 12건
- allow 중 pass: 12건
- allow 중 partial/fail/unsure: 0건
- fail rate: 0.0%

다만 allow 대상 source_id는 1건 swap이 있었다.

- replay strict에는 있었지만 runtime gate에서는 제외: `800815`
- runtime gate에서 새로 allow: `600282`

원인은 replay 보고서가 저장된 `risk_tags`를 사용한 반면, runtime gate는 실제 source text와 LLM raw response에서 위험 신호를 다시 계산하기 때문이다. `600282`는 저장된 risk tag에는 `phone_dialogue`가 있었지만 원문 자체는 전화 대화체가 아니어서 runtime에서는 allow됐다. 반대로 `800815`는 source text 기준으로는 안전하지만 runtime의 evidence/segment gate에서 제외됐다. 두 케이스 모두 사람 검수 기준 pass였으므로 strict gate의 pass/fail 구성은 유지된다.

## 운영 권장 모드

- 운영 기본: `off` 또는 `shadow`
- 내부 제한 실험: `REQUEST_SEGMENT_LLM_MODE=assist`, `REQUEST_SEGMENT_LLM_PROMPT_STYLE=block`, `REQUEST_SEGMENT_LLM_ASSIST_POLICY=v2_strict`
- 기본 assist 활성화: 비권장
- full mode: 비권장

## 남은 리스크

- 100건 사람 검수 replay 기준이므로 표본이 아직 작다.
- 전화 대화체 마커는 휴리스틱이라 일부 누락될 수 있다.
- 법령/조건 질의의 저분할은 gate만으로 완전히 해결되지 않는다.
- LLM latency 평균 12초대라 실시간 사용자 요청 경로에는 부담이 크다.

## 다음 단계

1. `v2_strict`를 shadow/내부 실험으로만 200~300건 추가 평가한다.
2. strict allow 후보를 사람이 재검수해 precision을 다시 산정한다.
3. partial 원인인 `under_split`, `dialogue_confusion`은 prompt/validator 보강 실험으로 분리한다.

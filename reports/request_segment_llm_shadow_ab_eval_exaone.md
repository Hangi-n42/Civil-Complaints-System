# request_segments EXAONE Shadow A/B 평가

## 작업 배경

기존 LLM hybrid fallback은 규칙 기반 analyzer를 1차 판정기로 유지하고, 불확실한 케이스에서만 EXAONE 후보를 shadow/assist로 검증하는 구조다. 이전 실제 EXAONE 30건 shadow 평가에서는 도움이 되는 사례가 있었지만 `evidence_not_in_source`, JSON schema 불일치, 높은 latency, 전화 대화체/장문 제안서 과분할 리스크가 확인됐다.

이번 작업은 조건 A/B를 같은 후보군에 대해 비교해, source block ID 기반 prompt가 실제로 더 안전한지 확인하는 것이다.

## 기존 EXAONE Shadow 30건 문제 요약

- evidence 불일치가 발생했다. EXAONE이 의미상 맞는 문장을 만들더라도 evidence를 원문과 다르게 재작성했다.
- 일부 응답은 `text`/`evidence` 구조를 지키지 못하거나 빈 segment 배열을 반환했다.
- 평균 latency가 약 17초대로 높았다.
- 전화 대화체에서는 4개 이상 segment로 과분할될 수 있었다.
- 장문 법령/제안서는 번호가 많아도 실제 독립 처리 요청인지 확정하기 어려웠다.

## 조건 A/B 차이

| 항목 | 조건 A | 조건 B |
| --- | --- | --- |
| Prompt 입력 | 원문 최대 3,500자 | source block 상위 30개 |
| Evidence 방식 | LLM이 evidence 자유문장 직접 작성 | LLM이 `evidence_ids`만 반환 |
| 출력 schema | `request_segments[].text/evidence/reason` | `decision`, `segments[].text/evidence_ids` |
| `num_predict` | 512 | 256 |
| 검증 방식 | evidence 문자열이 원문에 포함되는지 확인 | evidence ID가 실제 block인지 확인 후 block 복원 |
| 보수적 결정 | 없음 | `keep_rule`, `abstain` 허용 |

## Source Block Selector 설계

`build_source_blocks()`는 title/client_question 원문을 줄/문장 단위 block으로 나누고, 다음 신호를 기준으로 우선순위를 매긴다.

- 높은 우선순위: 번호/불릿, 요청/문의/가능/여부/확인/조치/개선/설치/보수/철거/단속/점검, 물음표, heading, 제목/본문 초반
- 낮은 우선순위: 인사말, 감사/마무리, 상담사 답변성 문장, 요청 신호 없는 긴 법령 인용, 반복 배경 설명
- 애매한 문장은 삭제하지 않고 낮은 점수로 둔다.
- 선택된 block은 원문 등장 순서로 재정렬하고 `S1`, `S2`처럼 안정적인 ID를 부여한다.

## JSON Schema 개선

조건 B의 출력은 아래 세 결정만 허용한다.

```json
{"decision":"keep_rule","segments":[],"confidence":0.0}
```

```json
{"decision":"replace","segments":[{"text":"도로 보수 일정을 알려주세요.","evidence_ids":["S3"]}],"confidence":0.82}
```

```json
{"decision":"abstain","segments":[],"confidence":0.0}
```

`replace`일 때만 segment를 요구한다. `keep_rule`/`abstain`이면 규칙 기반 결과를 유지한다.

## Parser/Validator 개선 내용

- fenced JSON 제거
- 첫 `{`부터 마지막 `}`까지 추출
- trailing comma 제거
- parse 실패 시 reject
- `decision` allowlist 검증
- `segments` 1~6개 검증
- 모든 `evidence_ids`가 실제 block ID인지 검증
- evidence block 또는 text에 요청/질의 신호가 있는지 검증
- 장문 segment reject
- 전화 대화체 4개 이상 segment reject
- 장문 법령/제안서 4개 이상 segment reject
- 기존 rule segment보다 과도하게 segment 수가 늘면 reject
- assist 적용은 `numbered_under_split`, `heading_list_under_split` allowlist trigger에서만 허용

## A/B 평가 조건

- Seed: `20260625`
- 모델: `exaone3.5:7.8b`
- Provider: Ollama
- Mode: shadow
- 후보: `data/raw_data/`에서 규칙 기반 analyzer 실행 후 `assess_fallback_need()`가 true인 동일 30건
- 스캔한 raw record: 81건
- 원자료: `reports/request_segment_llm_shadow_ab_eval_exaone.json`

## A/B 평가 결과

| 지표 | 조건 A | 조건 B |
| --- | ---: | ---: |
| 총 후보 | 30 | 30 |
| accepted | 21 | 23 |
| rejected | 9 | 7 |
| accepted rate | 70.00% | 76.67% |
| schema failure | 2 | 0 |
| evidence mismatch | 5 | 0 |
| hallucination suspected | 5 | 0 |
| oversplit suspected | 1 | 0 |
| accepted 평균 segment 수 | 1.476 | 1.130 |
| 평균 latency | 17.65초 | 12.28초 |
| P95 latency | 42.15초 | 29.09초 |
| max latency | 46.65초 | 34.73초 |
| 총 호출 시간 | 529.58초 | 368.46초 |

조건 B는 조건 A 대비 accepted가 2건 늘었고, evidence/schema/hallucination/과분할 의심은 모두 줄었다. latency도 평균 기준 약 30.4% 감소했다.

## Reject Reason 비교

### 조건 A

| 사유 | 건수 |
| --- | ---: |
| accepted | 21 |
| `evidence_not_in_source:0` | 3 |
| `invalid_segment_count` | 2 |
| `evidence_not_in_source:1` | 2 |
| `weak_request_signal:0` | 2 |

### 조건 B

| 사유 | 건수 |
| --- | ---: |
| accepted | 23 |
| `keep_rule` | 3 |
| `weak_request_signal:1` | 1 |
| `long_legal_or_proposal_over_split` | 1 |
| `phone_dialogue_over_split` | 1 |
| `weak_request_signal:0` | 1 |

조건 B는 evidence 불일치를 원천적으로 제거했다. 대신 위험한 전화 대화체/장문 제안서는 replace하지 않고 규칙 결과를 유지하도록 reject했다.

## 대표 개선 사례

| source_id | 조건 A | 조건 B |
| --- | --- | --- |
| `800193` 버스배차시간 | `evidence_not_in_source` reject | `버스 배차 간격 개선 요청` accepted |
| `800343` 도로 아스팔트 불량 | `evidence_not_in_source` reject | `아스팔트 보수 요청` accepted |
| `300558` 단위수량 측정 고시 질문 | `evidence_not_in_source` reject | 인정 절차 문의 accepted |
| `20036` 건축물분양 법률위반 | `evidence_not_in_source` reject | 조사/처분 요청 2개 accepted |

## 대표 위험/보수 처리 사례

| source_id | 처리 | 해석 |
| --- | --- | --- |
| `80131` 빙판길 제설 작업 요청 | `weak_request_signal` reject | 제설 요청은 유효하지만 일부 segment가 수단/배려 문구로 약해 보수 처리 |
| `001808` 전화 대화체 | `phone_dialogue_over_split` reject | 이용 방법/주차/현장 접수/예매로 나뉘지만 전화 흐름 과분할 위험 |
| `80092` 장문 도시계획 건의 | `long_legal_or_proposal_over_split` reject | 4개 제안으로 나뉘지만 장문 건의서는 사람 검수 전 replace 위험 |

## Assist 가능 여부 판단

조건 B는 조건 A보다 명확히 낫다.

- latency 감소
- schema failure 0건
- evidence mismatch 0건
- hallucination suspected 0건
- oversplit suspected 0건
- accepted rate 개선

하지만 바로 assist 기본 활성화는 아직 권장하지 않는다.

- 샘플이 30건으로 작다.
- accepted는 validator 통과이지 사람 검수 정답이 아니다.
- 일부 accepted segment는 요약형 text라 BE3 action-item에 적절한지 사람 검수가 필요하다.
- latency 12.28초도 운영 요청마다 동기 호출하기에는 여전히 크다.

## 운영 권장 모드

- 기본 운영: `shadow`
- 제한 실험: 조건 B 기반 `assist`를 관리자 검수/BE3 내부 실험에서만 허용
- `full`: 권장하지 않음

조건 B는 다음 단계로 갈 가치가 있다. 다만 다음 단계는 `shadow 100~200건 + 사람 검수`가 먼저다.

## BE3/FE/Multi-Agent Routing 관점 해석

- BE3는 조건 B의 `replace` 후보를 action-item 생성 후보로 볼 수 있지만, 현재는 shadow trace로 축적하는 것이 안전하다.
- FE는 기존 `is_multi == len(request_segments) >= 2` 계약을 그대로 유지하면 된다.
- LLM 결과를 사용자에게 확정 분해로 노출하지 말고, 내부 품질 검증 후 assist 적용 범위를 좁히는 것이 좋다.
- 전화 대화체/장문 제안서/장문 법령 질의는 계속 review 또는 keep_rule 대상으로 남기는 것이 안전하다.

## 남은 리스크

- EXAONE이 temp 0에서도 일부 응답 형식을 흔들 수 있다.
- source block selector가 상위 30개 밖의 중요한 근거를 누락할 수 있다.
- `text`가 원문 exact span이 아니라 요약형인 경우가 있어, BE3가 이를 action item으로 쓰기 전 검수 기준이 필요하다.
- 작은 샘플이라 도메인별 안정성은 아직 확정할 수 없다.

## 다음 단계

1. 조건 B로 shadow 100~200건을 추가 수집한다.
2. 사람이 accepted/rejected 대표 샘플을 검수한다.
3. 검수 결과로 assist allowlist trigger를 좁힌다.
4. latency가 부담되면 비동기 shadow 수집 또는 offline batch 평가로 분리한다.
5. BE3 action-item 품질과 FE 복합 모드 오탐률을 함께 본다.


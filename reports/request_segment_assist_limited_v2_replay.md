# request_segments assist_limited_v2 replay 분석

## 작업 배경

조건 B(source block + evidence_ids + num_predict=256) EXAONE shadow 100건에 대한 사람 검수 결과를 바탕으로 partial/fail/unsure 원인을 분석하고, 런타임 관측 가능 신호만으로 `assist_limited_v2` allow 정책을 replay 평가했다. LLM은 새로 호출하지 않았고, 코드 로직도 변경하지 않았다.

## 입력 검증

- 입력 JSONL: `reports\request_segment_llm_condition_b_shadow_100_human_reviewed.jsonl`
- 분석 대상: 100건
- 원본 JSON/JSONL은 수정하지 않음
- `human_judgment`는 replay 평가의 정답처럼 사용했지만, 이 검수 자체도 100건 표본에 대한 보수적 사람 판단이라는 한계가 있다.

## 기존 100건 human review 결과

| judgment | 건수 |
| --- | ---: |
| pass | 57 |
| partial | 21 |
| fail | 12 |
| unsure | 10 |

- 전체 pass rate: 57.0%
- 전체 pass + partial rate: 78.0%
- assist_limited 후보: 21건
- assist_limited pass rate: 61.9%

## partial/fail/unsure 원인 분석

| error_type | 건수 | 자동 gate 가능성 |
| --- | ---: | --- |
| none | 57 | 정상 |
| dialogue_confusion | 12 | 대화체 마커와 phone_dialogue gate로 차단 가능하나 누락 가능 |
| weak_actionability | 10 | weak_request_signal gate로 차단 가능 |
| over_split | 7 | possible_over_split, segment 길이, evidence 과다로 일부 차단 가능 |
| under_split | 7 | segment 수와 evidence 수 비교로 일부 차단 가능 |
| evidence_insufficient | 3 | evidence_count와 source block 품질 확인으로 일부 차단 가능 |
| legal_context_ambiguous | 2 | 법령/정책 장문 risk로 review 분리 필요 |
| too_abstract | 1 | segment 길이/추상 표현만으로는 한계, review 필요 |
| unsupported_segment | 1 | weak_request_signal과 evidence 검수로 차단 필요 |

## risk_tags별 분포

| risk tag | pass | partial | fail | unsure |
| --- | ---: | ---: | ---: | ---: |
| long_legal_or_policy | 0 | 0 | 1 | 0 |
| none | 43 | 9 | 2 | 9 |
| numbered_or_heading_list | 13 | 8 | 5 | 1 |
| phone_dialogue | 2 | 0 | 0 | 0 |
| segment_limit_case | 0 | 1 | 4 | 0 |
| weak_request_signal | 0 | 3 | 2 | 0 |

## fallback_reasons별 분포

| fallback reason | pass | partial | fail | unsure |
| --- | ---: | ---: | ---: | ---: |
| fallback_single_segment | 9 | 2 | 2 | 8 |
| heading_list_under_split | 1 | 0 | 0 | 0 |
| numbered_under_split | 12 | 8 | 5 | 1 |
| phone_dialogue_uncertain | 4 | 2 | 8 | 0 |
| possible_over_split | 0 | 1 | 1 | 0 |
| segment_too_long | 1 | 1 | 1 | 1 |
| strong_candidate_single_segment | 39 | 7 | 0 | 2 |
| weak_request_signal | 0 | 4 | 2 | 0 |

## assist_limited 후보 21건 분석

pass 13건은 대체로 번호/목록형 질의가 명확하고, LLM segment 수가 rule/evidence 수와 크게 어긋나지 않았다. partial 8건은 전화 대화체, 조건별 법령 질의 저분할, 책임/의무 질의의 추상화, 한 segment 안에 여러 질의를 묶는 패턴이 많았다.

특히 다음 신호는 v2 gate에 넣는 것이 안전하다.

- `phone_dialogue`, `segment_limit_case`, `weak_request_signal`, `long_legal_or_policy` risk는 allow에서 제외
- `weak_request_signal`, `possible_over_split`, `phone_dialogue_uncertain`, `segment_too_long` fallback reason은 allow에서 제외
- 제목/본문 초반에 `여보세요`, `아 네`, `네. 여보세요`, `아 그럼/아 홈페이지` 같은 전화 대화체 마커가 있으면 review
- LLM segment 수가 rule segment 수보다 줄면 review
- evidence block 수가 LLM segment 수보다 많으면 review
- LLM segment가 너무 길거나 한 segment 안에 여러 요청 cue를 합치면 review

## assist_limited_v2 정책 설계

운영 조건에는 `human_judgment`를 사용하지 않았다. replay 성능 산정에만 human review 결과를 사용했다.

### 공통 base 조건

- `accepted == true`
- `fallback_reasons`에 `numbered_under_split` 또는 `heading_list_under_split` 포함
- `llm_segments` 1개 이상
- 위험 risk/fallback reason 및 대화체 마커 제외

### strict

- `llm_segments <= 3`
- `rule_segments <= 4`이면 `llm_segments >= rule_segments`
- `restored_evidence_texts <= llm_segments`
- 최대 segment 길이 70자 이하
- 한 segment에 여러 요청 cue를 문장 결합 형태로 합치면 제외

### balanced

- strict와 유사하되 `rule_segments <= 3`, 최대 길이 75자로 완화

### recall

- 후보 수를 늘리기 위해 `llm_segments <= 4`, evidence 수 `llm_segments + 1`까지 허용

## replay 결과

| 정책 | allow_assist | pass | partial | fail | unsure | pass rate | fail rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strict | 12 | 12 | 0 | 0 | 0 | 100.0% | 0.0% |
| balanced | 13 | 12 | 1 | 0 | 0 | 92.3% | 0.0% |
| recall | 14 | 12 | 2 | 0 | 0 | 85.7% | 0.0% |

## strict/balanced/recall 비교

### strict

- allow_assist: 12건
- pass rate: 100.0%
- fail rate: 0.0%
- allow_assist source_id: 300138, 300309, 300912, 301057, 301301, 301527, 501472, 6899347, 6905873, 6907050, 701068, 800815
- 기존 human allow와 겹침: 12건
- 기존 human allow 중 누락: -
- v2 allow이나 기존 human allow가 아니었던 건: -

### balanced

- allow_assist: 13건
- pass rate: 92.3%
- fail rate: 0.0%
- allow_assist source_id: 300138, 300309, 300912, 301057, 301301, 301527, 501472, 6899347, 6905873, 6907050, 700210, 701068, 800815
- 기존 human allow와 겹침: 12건
- 기존 human allow 중 누락: -
- v2 allow이나 기존 human allow가 아니었던 건: 700210

### recall

- allow_assist: 14건
- pass rate: 85.7%
- fail rate: 0.0%
- allow_assist source_id: 300138, 300309, 300912, 301057, 301301, 301527, 501472, 6899347, 6905873, 6907050, 6907251, 700210, 701068, 800815
- 기존 human allow와 겹침: 12건
- 기존 human allow 중 누락: -
- v2 allow이나 기존 human allow가 아니었던 건: 6907251, 700210

## 최종 추천 정책

`strict`를 추천한다.

- allow_assist 12건
- pass 12건, partial 0건, fail 0건, unsure 0건
- 100건 replay에서는 allow_assist pass rate 100.0%, fail rate 0.0%
- 후보 수는 줄지만 자동 적용 전 gate로는 precision이 더 중요하다.

다만 이 결과는 100건 표본 replay 기준이므로 바로 운영 기본값을 바꿀 근거로 보기는 어렵다. 내부 제한 실험은 가능하지만 기본 assist/full 활성화는 여전히 권장하지 않는다.

## gate 판단

- 최종 판단: `assist_limited_v2_ready_for_internal_experiment`
- 내부 실험: strict 조건의 allow_assist에 한해 가능
- 운영 기본값 변경: 비권장
- 기본 모드: shadow 유지

## BE3/FE/Multi-Agent Routing 전달사항

- 조건 B + strict gate는 목록형 다중 질의 중 안전한 일부를 높은 precision으로 골라낼 수 있다.
- 그러나 전체 accepted 79건 중 자동 assist 가능한 건 극히 일부다.
- FE 복합 민원 모드나 BE3 action-item 자동 매핑에 바로 연결하지 말고, strict allow 후보만 내부 실험 플래그로 제한하는 것이 안전하다.
- 전화 대화체, 장문 법령/정책, 약한 요청 신호는 계속 shadow/review로 유지해야 한다.

## 남은 리스크

- 100건 표본 replay라 trigger별 confidence interval이 넓다.
- 대화체 마커는 휴리스틱이라 누락 가능성이 있다.
- 법령/조건 질의의 저분할은 segment 수/evidence 수만으로 완전히 잡기 어렵다.
- human review도 보수적 단일 검수 결과이므로 추가 이중 검수가 필요하다.

## 다음 단계

1. strict allow_assist 11건과 유사한 후보를 200~300건 shadow에서 추가 검수한다.
2. strict gate를 코드에 반영하기 전 feature flag로 shadow trace만 남기는 실험을 먼저 설계한다.
3. partial의 `under_split`, `dialogue_confusion`을 줄이는 LLM prompt/validator 보강은 별도 실험으로 분리한다.

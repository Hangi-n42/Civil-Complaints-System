# request_segments ?? B Shadow 100? ?? ?? ???

## ?? ??

?? B(source block + evidence_ids + `num_predict=256`)? 30? A/B ???? ?? A?? ?? ??? ????, ?? `exaone3.5:7.8b` shadow ??? 100??? ????. accepted? validator ?? ??? ? ?? ?? ??? ???, ?? assist ???? ?? ???.

## ?? ??

- ??: `exaone3.5:7.8b`
- Provider: Ollama
- Mode: shadow
- Prompt: ?? B source block + evidence_ids
- Source block limit: 30
- num_predict: 256
- Seed: `20260626`
- ??? raw record: 261
- fallback ??: 100
- ?? ??: `reports/request_segment_llm_condition_b_shadow_100_candidates.json`
- ???: `reports/request_segment_llm_condition_b_shadow_100.json`

## ?? ??

| ?? | ? |
| --- | ---: |
| total | 100 |
| accepted | 79 |
| rejected | 21 |
| accepted rate | 79.00% |
| schema failure | 3 |
| invalid evidence_id | 0 |
| hallucination suspected | 2 |
| oversplit suspected | 0 |
| assist_limited candidates | 21 |
| assist_limited safe candidates | 20 |
| review needed accepted | 59 |

## Latency ??

| ?? | ? |
| --- | ---: |
| avg | 12.65 |
| p50 | 9.72 |
| p95 | 27.81 |
| max | 39.26 |
| min | 6.09 |
| total | 1264.87 |

## Decision ??

| decision | ?? |
| --- | ---: |
| replace | 92 |
| keep_rule | 6 |
| parse_failed | 2 |

## Reject Reason ??

| reject_reason | ?? |
| --- | ---: |
| accepted | 79 |
| keep_rule | 6 |
| phone_dialogue_over_split | 5 |
| weak_request_signal:0 | 4 |
| invalid_json | 2 |
| segment_count_expanded_too_much | 1 |
| invalid_segment_count | 1 |
| weak_request_signal:1 | 1 |
| long_legal_or_proposal_over_split | 1 |

## Allowlist Trigger? ??

| fallback_reason | total | accepted | accepted_rate | assist_safe |
| --- | ---: | ---: | ---: | ---: |
| fallback_single_segment | 21 | 11 | 0.524 | 0 |
| heading_list_under_split | 1 | 1 | 1.0 | 1 |
| numbered_under_split | 26 | 20 | 0.769 | 19 |
| phone_dialogue_uncertain | 14 | 6 | 0.429 | 0 |
| possible_over_split | 2 | 1 | 0.5 | 1 |
| segment_too_long | 4 | 2 | 0.5 | 0 |
| strong_candidate_single_segment | 48 | 46 | 0.958 | 6 |
| weak_request_signal | 6 | 5 | 0.833 | 1 |

## ???? ??

| risk_tag | total | accepted | accepted_rate | assist_safe |
| --- | ---: | ---: | ---: | ---: |
| long_legal_or_policy | 1 | 0 | 0.0 | 0 |
| none | 63 | 52 | 0.825 | 0 |
| numbered_or_heading_list | 27 | 21 | 0.778 | 20 |
| phone_dialogue | 2 | 2 | 1.0 | 0 |
| segment_limit_case | 5 | 1 | 0.2 | 0 |
| weak_request_signal | 5 | 4 | 0.8 | 0 |

## ?? assist_limited ?? ??

- `501472` 4대보험 신고 관련 및 근로계약서 작성 관련: 4대보험 신고 여부 확인 (한 달 총 근로시간 64시간 기준) / 근로계약서 작성 시 근무일 범위 차이 확인
- `300927` 발코니 바닥 해체허가(신고) 관련 문의: 발코니 바닥 해체 허가(신고) 대상 여부 문의
- `001585` 4월 21일에 소풍을 가려하는데요.: 4월 21일 소풍 예약 방법 문의
- `700210` : 법 위반 책임이 누구에게 있는지 확인해 주세요. / 시설물 인수 시 법 기준 준수 의무 확인 필요성.
- `800815` 성남시내 주요 공원의 ▲▲▲ 조성관련 질의 및 건의 사항: 황톳길 조성 관련 사실 확인 요청 / 황톳길 황토 구성 성분 확인 요청 / 친환경 공법 개발 건의

## ?? review ?? ??

- `600282` 석면슬레이트 철거 및 처리 지원 사업에 대해 여쭙니다.: risk=['phone_dialogue', 'numbered_or_heading_list'], segments=석면슬레이트 철거 지원 범위 확인 / 과수원의 무허가 창고 철거 지원 여부 확인
- `6894187` 종량제 및 쓰레기 수거 차량의 최저 입찰가 관련: risk=['none'], segments=최저 낙찰가 외에 안전 및 위생 등 중요 요소를 고려한 계약 진행 요청
- `6893765` 불법 광고물 단속 요청합니다.: risk=['none'], segments=불법 광고물 단속 요청합니다. / 단속할 수 있는 근거 문의
- `6892861` 자동차세 연납승계제도 및 신규 취득 자동차 연납 신청 안내: risk=['none'], segments=자동차세 연납 후 변경이 있는 경우 연납 세금은 어떻게 되나요?
- `6895012` 청소년보호법 위반업소 신고 처리 경과 질의: risk=['none'], segments=청소년보호법 위반 업소의 포상금 및 처분결과 확인 요청

## ?? reject ??

- `6902956` 남구 구민안전보험 소개 및 보장내용, 청구방법: reject=keep_rule, risk=['none']
- `500659` 최저임금 및 월급계산: reject=weak_request_signal:0, risk=['none']
- `000676` 버스 정류장 정차: reject=keep_rule, risk=['none']
- `6891532` 치매안심센터 제공 서비스 현황: reject=keep_rule, risk=['none']
- `000247` 승강장 냉방기 관련: reject=keep_rule, risk=['none']

## assist_limited ?? ?? ??

?? B 100??? accepted? 79/100???, hallucination suspected? invalid evidence_id? 0????. ?? schema failure? 3? ???, accepted ? assist_limited safe? ? ? ?? ??? 20???. ??? ?? ?? ? ??? "??? ??"??. ?? assist ???? ?? ??, numbered/heading/list? allowlist??? ?? ?? ??? ???? ?? ????.

## ?? ?? ??

- ?? ??: `off` ?? `shadow`
- ?? ??: ?? B ?? shadow ?? ??
- ?? assist ??: `numbered_under_split`, `heading_list_under_split` ???? ??? ??? ?? ???
- ??: phone dialogue, long legal/policy, long proposal, weak_request_signal ??, segment_limit_case
- full mode: ???? ??

## BE3/FE/Multi-Agent Routing ????

BE3? ?? B? accepted ??? action-item ??? ??? ? ???, ?? ?? ?? ???? ?? ????? ?? ? ??. FE? ?? `is_multi == len(request_segments) >= 2` ??? ???? ??. Multi-Agent Routing??? assist_limited safe ??? ?? ????? ??, ???? shadow/review? ??? ??.

## ?? ???? ?? ??

- accepted? ?? ???? ?? ??? ????.
- 100???? invalid JSON/schema ??? ?? ???.
- latency ??? ?? ?? ???? ??? ????.
- ?? ??? review JSONL? ?? ?? ??? ???? pass/partial/fail precision? ???? ???.

# request_segments EXAONE Shadow 평가 결과

## 평가 개요

- 목적: 실제 `exaone3.5:7.8b`를 사용해 `request_segments` LLM hybrid fallback의 shadow 품질을 확인한다.
- 모델: `exaone3.5:7.8b`
- Provider: Ollama
- Mode: `shadow`
- Seed: `20260625`
- 대상: `data/raw_data/`에서 규칙 기반 analyzer 실행 후 `assess_fallback_need()`가 true인 30건
- 원자료: `reports/request_segment_llm_shadow_eval_exaone_20260625.json`

> 주의: 이 평가는 실제 EXAONE 응답을 사용했지만, 샘플 수가 30건으로 작다. 또한 `accepted`는 원문 evidence 검증을 통과했다는 뜻이지, 사람이 보기에 완전히 올바른 segment라는 뜻은 아니다.

## 요약 지표

| 항목 | 값 |
| --- | ---: |
| 스캔한 raw record 수 | 81 |
| fallback 후보 수 | 30 |
| LLM 검증 통과 | 18 |
| LLM 검증 실패 | 12 |
| hallucination 의심 | 6 |
| 평균 latency | 17.55초 |
| 최소 latency | 5.02초 |
| 최대 latency | 47.44초 |
| 총 호출 시간 | 526.52초 |

## Fallback Trigger 사유

| 사유 | 건수 |
| --- | ---: |
| `strong_candidate_single_segment` | 14 |
| `numbered_under_split` | 11 |
| `fallback_single_segment` | 8 |
| `weak_request_signal` | 2 |
| `segment_too_long` | 1 |

한 건에 여러 사유가 동시에 붙을 수 있다.

## Reject 사유

| 사유 | 건수 |
| --- | ---: |
| accepted | 18 |
| `evidence_not_in_source:0` | 3 |
| `weak_request_signal:0` | 3 |
| `invalid_segment_count` | 2 |
| `evidence_not_in_source:1` | 2 |
| `missing_text_or_evidence:0` | 1 |
| `evidence_not_in_source:2` | 1 |

`evidence_not_in_source`는 LLM이 원문 근거를 재작성하거나, 원문과 정확히 일치하지 않는 문장을 evidence로 낸 경우다. 이 방어가 없으면 hallucination 또는 근거 불일치 segment가 운영에 들어갈 수 있다.

## Accepted 대표 사례

| source_id | 제목 | 해석 |
| --- | --- | --- |
| `6907361` | 노원평생학습관 에버러닝 수강 신청 방법 | 단일 문의를 짧고 명확한 요청으로 정리 |
| `6899254` | 국방규격 표준서 부품번호 창생 문의 | 부품번호 생성/유지/행정절차를 3개 질의로 분리 |
| `6899262` | 국방규격화 진행 가능 여부 문의 | 규격화 가능 여부, 절차, 불가능 시 대안을 3개로 분리 |
| `000177` | 새일여성인턴제도 건 | 참여 가능 여부 재확인 요청으로 정리 |
| `301341` | 방화벽체 배관 관통 허가 대상 | 허가 대상 여부 질의로 정리 |

## Accepted 중 주의 사례

| source_id | 제목 | 주의점 |
| --- | --- | --- |
| `80131` | 빙판길 제설 작업 요청 | 제설 작업, 작은 제설 차량, 어르신 안전 고려로 분리했으나 독립 처리 요청인지 배경/수단인지 사람 검수가 필요 |
| `001808` | 전화 대화체 | 이용 방법, 주차 위치, 현장 접수, 현장 예매로 분리했지만 전화 흐름상 과분할 가능성이 있음 |

따라서 현재 `accepted=18`을 그대로 assist 적용 가능 건수로 해석하면 안 된다.

## Rejected 대표 사례

| source_id | Reject | 해석 |
| --- | --- | --- |
| `800193` | `evidence_not_in_source` | 버스 배차 문제를 잘 요약했지만 evidence를 원문과 다르게 재작성 |
| `800343` | `evidence_not_in_source` | 도로 아스팔트 보수/부실공사 확인을 생성했으나 evidence 정확 일치 실패 |
| `300697` | `missing_text_or_evidence` | JSON item 구조가 깨져 text/evidence가 분리되지 않음 |
| `6903274` | `weak_request_signal` | "NMN은 직구로 되나요"는 의미상 질의지만 현재 request cue 검증이 보수적으로 reject |
| `6901926` | `invalid_segment_count` | 빈 segment 배열 반환 |

## 품질 판단

실제 EXAONE은 복합 요청 분해에 도움이 되는 사례가 있었다. 특히 번호형 질의, 절차/가능 여부 질의, 긴 제목형 문의를 짧은 요청 단위로 정리하는 데 유효했다.

다만 현재 결과만으로 `assist`를 기본 활성화하기는 이르다.

- evidence 원문 불일치가 6/30건 발생했다.
- accepted 중에도 전화 대화체와 장문 제안에서는 과분할 가능성이 남았다.
- 평균 latency가 17.55초로 운영 요청마다 호출하기에는 크다.
- 일부 응답은 JSON schema를 완전히 지키지 못했다.

## 운영 권장

- 현재 권장 모드: `shadow`
- `assist`: BE3 내부 실험 또는 관리자 검수 플로우에서 제한적으로 사용
- `full`: 권장하지 않음

다음 단계는 shadow 모드로 100~200건을 추가 수집하고, 사람이 accepted 샘플을 검수해 `검증 통과`와 `실제 정답` 사이의 차이를 측정하는 것이다.

## BE3/FE 관점 해석

- BE3는 LLM fallback trace를 action-item 생성의 보조 신호로만 사용해야 한다.
- FE는 기존 `is_multi == len(request_segments) >= 2` 계약을 유지하면 된다.
- LLM fallback 결과는 당장 사용자에게 확정 분해로 노출하기보다, 내부 실험/검수 단계에서 shadow trace로 축적하는 것이 안전하다.


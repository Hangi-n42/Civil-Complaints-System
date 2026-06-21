# request_segments LLM Hybrid Fallback 5회 루프 보고서

## 1. 작업 배경

규칙 기반 `complexity_analyzer.py`는 1차 판정기로 유지하면서, 남은 `주의/실패` 케이스에만 LLM fallback을 붙일 수 있는 별도 계층을 설계했다. 목표는 Multi-Agent Routing에서 독립 요청 단위를 더 안정적으로 얻되, 원문에 없는 요청 생성과 과분할을 막는 것이다.

이번 작업은 외부 API/DTO/request/response 형식을 바꾸지 않았다. 추가 trace는 기존 `complexity_trace` 내부에만 들어간다.

## 2. 현재 규칙 기반 analyzer의 남은 한계

- 긴 법령 질의에서 번호가 법 조항 번호인지 요청 번호인지 애매하다.
- 제목과 본문이 같은 단일 질문이면 강한 복합 신호처럼 보일 수 있다.
- 전화 대화체는 실제 요청, 확인 질문, 상담 흐름이 섞여 과분할/미분할이 모두 발생한다.
- 장문 제안서는 여러 항목이 있어도 각 항목이 독립 처리 요청인지 배경 설명인지 자동 판정이 어렵다.
- `segment_limit_truncated`가 발생한 케이스는 규칙만으로 어떤 항목을 버릴지 판단하기 어렵다.

## 3. LLM hybrid 설계 원칙

- `complexity_analyzer.py`에는 LLM 호출 코드를 넣지 않고, `request_segment_hybrid.py` wrapper를 별도로 둔다.
- 운영 기본값은 `REQUEST_SEGMENT_LLM_MODE=off`다.
- 모드는 `off`, `shadow`, `assist`만 허용한다.
- LLM provider는 기본 `none`이며, 명시적으로 `REQUEST_SEGMENT_LLM_PROVIDER=ollama`일 때만 Ollama를 호출한다.
- LLM 출력은 JSON만 허용하고, `request_segments[].evidence`가 원문 부분 문자열이어야 한다.
- 검증 실패 시 항상 규칙 기반 결과를 유지한다.
- `full` 기본 적용은 하지 않는다.

## 4. Loop 1 결과

- Seed: `20260620`
- 샘플: raw_data 복합 후보 13,576건 중 500건
- 주요 주의/실패 유형: `fallback_single_segment`, `numbered_under_split`, `phone_dialogue_uncertain`, `segment_limit_truncated`
- 구현/수정: 별도 hybrid wrapper, `off/shadow/assist`, JSON 검증, evidence 원문 포함 검증, trace 기록

| 기준 | 정상 | 주의 | 실패 | 평균 segment |
| --- | ---: | ---: | ---: | ---: |
| 규칙 only | 180 | 68 | 252 | 1.794 |
| hybrid assist 검증 | 194 | 67 | 239 | 1.722 |

LLM fallback 후보 211건 중 69건 적용, 142건 reject, hallucination 의심 0건이었다. 실패가 13건 감소했고 정상은 14건 증가했다.

## 5. Loop 2 결과

- Seed: `20260621`
- 문제: 제목/본문 반복이 복합 후보로 과감지될 수 있음
- 보완: 강한 요청 후보 수 산정에서 근접 중복 문장을 병합

| 기준 | 정상 | 주의 | 실패 | 평균 segment |
| --- | ---: | ---: | ---: | ---: |
| 규칙 only | 190 | 54 | 256 | 1.800 |
| hybrid assist 검증 | 205 | 51 | 244 | 1.734 |

LLM fallback 후보 218건 중 61건 적용, 157건 reject, hallucination 의심 0건이었다. 실패가 12건 감소했고 정상은 15건 증가했다.

## 6. Loop 3 결과

- Seed: `20260622`
- 문제: LLM이 장문 문장을 그대로 반환하면 과분할보다 더 나쁜 장문 segment가 될 수 있음
- 보완: LLM 후보 segment 240자, evidence 320자 초과 시 reject

| 기준 | 정상 | 주의 | 실패 | 평균 segment |
| --- | ---: | ---: | ---: | ---: |
| 규칙 only | 180 | 62 | 258 | 1.842 |
| hybrid assist 검증 | 200 | 52 | 248 | 1.832 |

LLM fallback 후보 214건 중 82건 적용, 132건 reject, hallucination 의심 0건이었다. 실패가 10건 감소했고 정상은 20건 증가했다.

## 7. Loop 4 결과

- Seed: `20260623`
- 문제: 전화 대화체에서 확인 질문과 실제 처리 요청이 섞임
- 판단: 전화 대화체는 LLM이 도움될 수 있지만 과분할 위험도 높으므로 assist 기본 적용은 보류

| 기준 | 정상 | 주의 | 실패 | 평균 segment |
| --- | ---: | ---: | ---: | ---: |
| 규칙 only | 188 | 59 | 253 | 1.978 |
| hybrid assist 검증 | 206 | 55 | 239 | 1.892 |

LLM fallback 후보 203건 중 79건 적용, 124건 reject, hallucination 의심 0건이었다. 실패가 14건 감소했고 정상은 18건 증가했다.

## 8. Loop 5 결과

- Seed: `20260624`
- 문제: `numbered_under_split`은 줄지만 일부 법령/제안 장문은 여전히 자동 판정이 위험함
- 판단: content evidence 검증을 통과해도 독립 요청성은 별도 리스크로 남음

| 기준 | 정상 | 주의 | 실패 | 평균 segment |
| --- | ---: | ---: | ---: | ---: |
| 규칙 only | 199 | 60 | 241 | 1.814 |
| hybrid assist 검증 | 214 | 57 | 229 | 1.818 |

LLM fallback 후보 205건 중 69건 적용, 136건 reject, hallucination 의심 0건이었다. 실패가 12건 감소했고 정상은 15건 증가했다.

## 9. 전체 before/after 비교표

| Loop | Seed | 규칙 정상 | 규칙 주의 | 규칙 실패 | Hybrid 정상 | Hybrid 주의 | Hybrid 실패 | 실패 감소 | 호출 후보 | 적용 | Reject |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 20260620 | 180 | 68 | 252 | 194 | 67 | 239 | 13 | 211 | 69 | 142 |
| 2 | 20260621 | 190 | 54 | 256 | 205 | 51 | 244 | 12 | 218 | 61 | 157 |
| 3 | 20260622 | 180 | 62 | 258 | 200 | 52 | 248 | 10 | 214 | 82 | 132 |
| 4 | 20260623 | 188 | 59 | 253 | 206 | 55 | 239 | 14 | 203 | 79 | 124 |
| 5 | 20260624 | 199 | 60 | 241 | 214 | 57 | 229 | 12 | 205 | 69 | 136 |
| 평균 | - | 187.4 | 60.6 | 252.0 | 203.8 | 56.4 | 239.8 | 12.2 | 210.2 | 72.0 | 138.2 |

초기 넓은 trigger 설계에서는 loop별 호출 후보가 약 285~310건까지 늘었으나, 제목/본문 근접 중복 병합과 장문 reject를 추가한 최종안에서는 203~218건으로 줄었다.

## 10. LLM fallback 호출 조건 최종안

- 규칙 trace의 `fallback_segment_used=True`
- 강한 복합 후보 신호가 있는데 segment가 1개
- 번호/불릿 후보 수와 segment 수가 크게 어긋남
- heading 후보가 있는데 segment가 1개 이하
- segment가 5개 이상이고 약한 요청 신호가 섞임
- segment가 지나치게 김
- 약한 요청 신호 segment가 다수 포함됨
- 전화 대화체이며 segment가 1개 이하 또는 5개 이상

단, 제목/본문 반복처럼 근접 중복인 후보는 강한 복합 신호 카운트에서 병합한다.

## 11. LLM fallback reject 조건 최종안

- JSON 파싱 실패
- confidence가 `REQUEST_SEGMENT_LLM_MIN_CONFIDENCE` 미만
- segment 수가 1~6 범위를 벗어남
- 각 item이 dict가 아니거나 `text`/`evidence`가 없음
- `text` 240자 초과 또는 `evidence` 320자 초과
- evidence가 원문에 존재하지 않음
- 인사말, 상담사 답변, 행정기관 조치 예상 문구
- 요청 동사/질의 의도 신호가 없음
- 근접 중복 segment는 병합

## 12. 대표 개선 사례

| ID | 유형 | 해석 |
| --- | --- | --- |
| `000471` | 번호형 질의 | 불법주정차 단속 관련 3개 질의 중 누락된 자료 게시 문의를 복원할 수 있음 |
| `600378` | 제목+본문 질의 | 공항 복합환승센터 부지 결정 시점과 진행 방향 문의를 더 분명히 분리 |
| `6893453` | 법령 처분 질의 | 권리금 분쟁과 공인중개사법 처분 가능 여부 질의를 분리 가능 |
| `6904624` | 공개 여부 질의 | 사료 검정 결과 확인 가능 여부와 공개 여부를 분리 가능 |
| `6907293` | CCTV 확인 | 제목 질문과 본문 근거를 묶어 확인 요청을 보강 가능 |

## 13. 대표 실패/악화 사례

| ID | 유형 | 리스크 |
| --- | --- | --- |
| `001778` | 전화 대화체 | 문자 수신 확인, 대기자 상태, 수강 전환 여부가 섞여 LLM이 장문 덩어리로 묶을 수 있음 |
| `002134` | 전화 대화체 | 체험관/놀이터/주차 질문이 대화 흐름에 섞여 과분할 위험 |
| `002278` | 예약 전화 | 예약 변경 설명과 실제 요청이 섞여 일부 맥락 문장이 segment가 될 수 있음 |
| `300356` | 법령 인용 | 조항 번호와 실제 질의 번호를 혼동할 수 있음 |
| `301829` | 사업 입찰 장문 | 배경, 사유, 질의가 섞여 독립 요청 판정이 어려움 |

## 14. hallucination 방어 결과

검증용 추출 스텁은 evidence를 원문 부분 문자열로만 반환하므로 5회 루프에서 hallucination 의심은 0건이었다. 단, 실제 LLM 호출을 수행한 결과가 아니므로 운영 전에는 shadow 모드로 실제 모델 응답의 `evidence_not_in_source`, `low_value_or_admin_segment`, `segment_too_long` reject율을 별도로 측정해야 한다.

## 15. 비용/지연/운영 리스크

- 최종 trigger는 500건당 평균 210.2건으로, 전체 요청에 LLM을 호출하기에는 여전히 많다.
- 실제 운영에서는 raw 전체가 아니라 “복합 후보 + 불확실 trace”에만 적용해야 한다.
- Ollama 로컬 호출 기준이라도 장문 민원 1건당 prompt가 최대 3,500자까지 들어가므로 latency가 늘 수 있다.
- 전화 대화체는 hallucination보다 과분할 리스크가 더 크다.

## 16. BE3/FE/Multi-Agent Routing 관점의 해석

- BE3 action-item 매핑에는 `request_segments_source`가 `llm_fallback`인지 trace로 확인할 수 있어야 한다.
- FE 복합 민원 모드는 기존 `is_multi == len(request_segments) >= 2` 계약이 유지된다.
- Multi-Agent Routing에서는 assist 적용 결과라도 원문 evidence 기반 검증을 통과한 segment만 사용해야 한다.
- 전화 대화체와 장문 법령 질의는 자동 분해 결과를 UI에서 확정처럼 보여주기보다 “AI 제안”으로 다루는 것이 안전하다.

## 17. 운영 권장 모드

현재 권장 모드는 `shadow`다.

이유:
- wrapper와 검증 로직은 단위 테스트를 통과했고, 검증용 추출 스텁 기준으로 실패 감소가 확인됐다.
- 하지만 실제 LLM 응답 품질, latency, reject율은 아직 운영 데이터로 측정하지 않았다.
- `assist`는 BE3 내부 실험 또는 관리자 검수 플로우에서만 제한적으로 켜는 것이 적절하다.
- `full` 기본 활성화는 권장하지 않는다.

## 18. 남은 리스크

- 실제 LLM은 검증용 스텁보다 표현을 재작성할 가능성이 있어 evidence 검증 reject가 늘 수 있다.
- 법령 조항 번호가 많은 문서에서는 번호형 요청과 조항 번호 구분이 여전히 어렵다.
- 전화 대화체는 민원인 의도와 상담 흐름이 섞여 자동 분해 품질이 케이스별로 흔들린다.
- 현재 5회 평가는 자동 휴리스틱 판정 기반이며, 사람 검수 정답셋은 아니다.

## 19. 추후 권장 작업

- `REQUEST_SEGMENT_LLM_MODE=shadow`로 실제 LLM 응답 trace를 수집한다.
- 100~200건 정도의 사람 검수 segment 정답셋을 만든다.
- shadow trace에서 reject 사유별 비율을 측정한다.
- BE3 action-item 성공률과 FE 복합 모드 오탐률을 함께 비교한다.
- assist 전환은 사람 검수셋에서 과분할 악화가 없다는 근거가 생긴 뒤 결정한다.

## 테스트 결과

- `.\civil\Scripts\python.exe -m pytest app\tests\unit\test_request_segment_hybrid.py -q`
  - 8 passed
- `.\civil\Scripts\python.exe -m pytest app\tests\unit\test_complexity_analyzer.py app\tests\unit\test_preprocessing_adapter.py app\tests\unit\test_request_segment_hybrid.py -q`
  - 106 passed
- `.\civil\Scripts\python.exe -m pytest app\tests\unit\test_retrieval_router_contract.py app\tests\unit\test_generation_week5_contract.py app\tests\unit\test_generation_week6_prompt_normalize.py app\tests\unit\test_generation_common_utils.py app\tests\unit\test_generation_fallback_metadata.py -q`
  - 79 passed


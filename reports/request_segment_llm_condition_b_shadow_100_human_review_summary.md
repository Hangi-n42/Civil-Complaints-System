# request_segments LLM 조건 B 100건 사람 검수 요약

## 작업 배경

`request_segments` LLM hybrid fallback은 규칙 기반 analyzer를 1차 판정기로 유지하고, 불확실한 케이스에만 EXAONE `exaone3.5:7.8b`를 shadow 후보로 호출하는 구조다. 이번 검수는 조건 B 방식, 즉 source block + `evidence_ids` + `num_predict=256` 평가 결과 100건을 사람이 검수하듯 보수적으로 판단한 결과다.

검수 입력인 `reports/request_segment_llm_condition_b_shadow_100_review.jsonl`은 UTF-8 JSONL 기준 100줄 모두 정상 파싱됐다. 깨져 보이는 현상은 PowerShell 콘솔 출력 인코딩 문제로 판단했다. 원본 파일은 수정하지 않고 별도 검수 결과 파일을 생성했다.

## 검수 기준

- `pass`: LLM segment가 원문 evidence와 잘 맞고, 실제 독립 요청 단위로 BE3 action-item 후보에 써도 무리가 없는 경우
- `partial`: 큰 방향은 맞지만 과분할, 저분할, 추상화, evidence 부족, 대화체 혼선 등으로 자동 적용은 조심해야 하는 경우
- `fail`: 원문에 없는 요청 생성, 배경 설명 요청화, 상담 흐름 오해, 과도한 과분할/저분할 등으로 적용하면 위험한 경우
- `unsure`: 원문만으로 사람도 판단이 어렵거나, LLM replace 후보가 없어 개선 여부를 확정하기 어려운 경우

전화 대화체, 장문 법령/정책, 장문 제안서는 pass가 가능해 보여도 자동 assist 추천에서는 보수적으로 처리했다.

## 검수 범위

- 전체 검수: 100건
- assist_limited 후보 검수: 21건 전부
- 원본 accepted: validator 통과 결과일 뿐 정답으로 간주하지 않음
- 원본 JSON/JSONL/gold/코드 로직은 변경하지 않음

## 전체 집계

| judgment | 건수 | 비율 |
| --- | ---: | ---: |
| pass | 57 | 57.0% |
| partial | 21 | 21.0% |
| fail | 12 | 12.0% |
| unsure | 10 | 10.0% |

- pass rate: 57.0%
- pass + partial rate: 78.0%
- 적용 추천:
  - allow: 12
  - review_required: 23
  - shadow_only: 53
  - reject: 12

## assist_limited 후보 집계

| judgment | 건수 | 비율 |
| --- | ---: | ---: |
| pass | 13 | 61.9% |
| partial | 8 | 38.1% |
| fail | 0 | 0.0% |
| unsure | 0 | 0.0% |

- assist_limited reviewed: 21
- allow recommendation: 12
- review_required: 9
- fail은 없지만 pass rate가 90% 기준에 크게 못 미친다.
- 따라서 `assist_limited_ready`가 아니라 `assist_limited_shadow_more`로 판단한다.

## risk_tags별 결과

| risk tag | pass | partial | fail | unsure |
| --- | ---: | ---: | ---: | ---: |
| none | 43 | 9 | 2 | 9 |
| numbered_or_heading_list | 13 | 8 | 5 | 1 |
| phone_dialogue | 2 | 0 | 0 | 0 |
| weak_request_signal | 0 | 3 | 2 | 0 |
| segment_limit_case | 0 | 1 | 4 | 0 |
| long_legal_or_policy | 0 | 0 | 1 | 0 |

`phone_dialogue`는 표면상 pass 2건이 있었지만, 자동 적용 후보로 보지 않았다. 대화 흐름과 실제 요청의 경계가 쉽게 흔들리는 유형이라 사람 검수 또는 shadow 유지가 안전하다.

## error_type별 결과

| error type | 건수 |
| --- | ---: |
| none | 57 |
| dialogue_confusion | 12 |
| weak_actionability | 10 |
| under_split | 7 |
| over_split | 7 |
| evidence_insufficient | 3 |
| legal_context_ambiguous | 2 |
| too_abstract | 1 |
| unsupported_segment | 1 |

주요 리스크는 전화 대화체 혼선, 약한 요청 신호, 과분할/저분할이다. 조건 B의 `evidence_ids` 검증은 hallucination 방어에는 효과가 있었지만, “독립 요청 단위로 적절한가”까지 자동 보장하지는 못했다.

## 대표 pass 사례

### 501472 - 4대보험 신고 관련 및 근로계약서 작성 관련

- rule: 근로계약서 작성 방식 차이 중심으로 1개 segment
- LLM: 4대보험 신고 여부, 근로계약서 작성 시 근무일 범위 차이
- 판단: 원문 목록형 질의의 독립 요청을 잘 살렸다. assist_limited 제한 실험 후보로 허용 가능하다.

### 800815 - 성남시내 주요 공원의 조성관련 질의 및 건의 사항

- rule: 문의/건의 일부만 포착
- LLM: 황톳길 사실 확인, 황토 성분 확인, 친환경 공법 개발 건의
- 판단: 질의와 건의를 분리했고 evidence와도 잘 맞는다.

### 301301 - 방화구획 및 외벽 마감재 해체 관련 문의

- rule: 해체 허가 대상 여부 질의
- LLM: 방화구획 해체 허가 대상 여부 문의
- 판단: 원문 질의를 과장 없이 압축했다.

### 6894187 - 포스트 코로나 대응 지역문화 방향 정책토론회 자료 요청

- rule/LLM: 자료 요청
- 판단: 단일 요청을 안정적으로 유지했다.

### 6907050 - 문화유산 분석 연구사례 정보 요청

- rule/LLM: 연구사례 정보 요청
- 판단: 정보 요청 의도가 명확하며 BE3 action-item으로 자연스럽다.

## 대표 partial 사례

### 300927 - 발코니 바닥 해체허가 관련 문의

- rule: 덤웨이터 설치 목적 절단 여부와 구조상 중요하지 않은 부분 여부를 나누어 포착
- LLM: 발코니 바닥 해체 허가 대상 여부 1개로 압축
- 판단: 큰 방향은 맞지만 조건별 법령 질의가 하나로 묶였다. 자동 assist는 검수가 필요하다.

### 001585 - 4월 21일 소풍 예약 문의

- rule: 예약 방법, 홈페이지 예약, 인원 관련 대화 흐름
- LLM: 소풍 예약 방법 문의
- 판단: 핵심은 맞지만 전화 대화체의 세부 확인이 누락됐다.

### 20036 - 건축물분양에 관한 법률 위반 주장

- rule: 설계변경 절차와 행정처분 요청
- LLM: 법 위반 판단과 조사/처분 요청 2개
- 판단: 요청 방향은 맞지만 두 segment가 겹치고 법적 판단 표현이 강해졌다.

### 700301 - 산업안전보건 관련 질의

- rule: 여러 책임/점검/위반 여부 질의
- LLM: 일부 질의만 분리
- 판단: 다중 질의의 일부가 빠져 자동 assist는 위험하다.

### 6896513 - 출입국사실증명서 발급 방법

- rule/LLM: 발급 방법 문의
- 판단: title 기반으로는 맞지만 evidence가 충분하지 않아 검수 필요로 분류했다.

## 대표 fail 사례

### 80062 - 리모델링 부정투표 부당성

- rule: 감정적 호소와 질문형 문장 다수
- LLM: 리모델링 부당성 조사와 조치 요청
- 판단: 원문보다 넓은 행정 조치 요청을 생성했다. BE3 action-item으로 쓰기 위험하다.

### 001904 - 공연 예매 전화 대화

- rule: 긴 전화 예매 대화 전체
- LLM: 없음
- 판단: 대화체에서 자동 분할하면 좌석/결제/예매 흐름이 왜곡될 위험이 커 reject가 적절하다.

### 100057 - 버스 관련 장문 민원

- rule: 시간표, 기사 태도, 직원교육 등 다수
- LLM: 없음
- 판단: 장문 불만/질문이 뒤섞여 있어 자동 assist 적용이 위험하다.

### 001261 - 장문 제안/정책 민원

- rule: 다수 제안/요구
- LLM: 없음
- 판단: 장문 제안서는 과분할 위험이 높아 reject 유지가 안전하다.

### 6906011 - 복잡한 법령 질의

- rule: 여러 법령/절차 질의
- LLM: 없음
- 판단: 법령 맥락이 복잡하고 JSON 실패도 있어 shadow/reject 유지가 맞다.

## 대표 unsure 사례

### 6902956 - 구민안전보험 소개 및 보장내용, 청구방법

- LLM replace 후보 없음
- 판단: rule 결과를 유지하는 것은 가능하지만 LLM 개선 여부는 판단할 수 없어 shadow_only로 분류했다.

### 000676 - 버스 정류장 정차

- LLM replace 후보 없음
- 판단: 요청 신호가 약하고 서술형 민원이라 자동 assist로 볼 근거가 부족하다.

### 700139 - 법령/정책 질의

- LLM replace 후보 없음
- 판단: 법령 맥락은 사람 검수 없이 독립 요청 단위 확정이 어렵다.

## assist_limited gate 판단

결론: `assist_limited_shadow_more`

근거:

- assist_limited 후보 21건 중 fail은 0건이라 방향성은 긍정적이다.
- 그러나 pass가 13건, 61.9%에 그쳐 90% 기준을 만족하지 못한다.
- partial 8건은 대부분 저분할, 전화 대화체, 과분할/중복 문제라 BE3 action-item 자동 적용 전 검수가 필요하다.
- allow 추천은 12건뿐이며, phone dialogue pass 사례는 자동 allow에서 제외했다.

따라서 기본 assist 또는 full 활성화는 권장하지 않는다. 운영 기본은 `shadow` 또는 `off`로 두고, numbered/heading/list형 중 검수된 allow 패턴만 내부 제한 실험 대상으로 삼는 것이 적절하다.

## BE3/FE/Multi-Agent Routing 관점 해석

- 조건 B는 evidence mismatch를 줄이는 데 효과가 있다.
- 다만 validator 통과가 곧 “독립 요청 분해 정답”은 아니다.
- BE3 action-item 자동 생성에 바로 연결하면 partial 유형에서 action 누락 또는 중복이 생길 수 있다.
- FE 복합 민원 모드는 assist_limited allow 후보처럼 목록형 질의가 명확한 경우에만 제한적으로 실험하는 것이 안전하다.
- 전화 대화체, 장문 법령, 장문 제안서는 계속 shadow/review로 분리해야 한다.

## 운영 권장 모드

- 기본 운영: `shadow` 유지
- assist 기본 활성화: 비권장
- full mode: 비권장
- 제한 실험 후보: 사람이 검수한 `allow` 12건과 유사한 numbered/heading/list형 명확 질의
- 제외 유지: phone dialogue, long legal/policy, long proposal, weak_request_signal 단독

## 남은 리스크

- 100건 검수는 precision 산정의 시작점이지 최종 운영 품질 보장은 아니다.
- pass/partial 판단에는 행정 도메인 지식이 필요한 케이스가 있다.
- LLM이 evidence block 안에서 의미를 요약할 때 과분할/저분할을 만들 수 있다.
- accepted 79건 중에도 자동 적용 가능한 케이스는 훨씬 적다.

## 다음 단계

1. `allow` 12건과 유사한 trigger를 중심으로 작은 assist_limited 실험군을 만든다.
2. partial 21건을 오류 유형별로 다시 묶어 trigger/reject rule을 보강한다.
3. phone dialogue와 장문 법령/정책은 별도 evaluator 또는 사람 검수 큐로 분리한다.
4. 200건 이상으로 사람 검수 표본을 늘려 trigger별 precision을 산정한다.

## 산출물

- 검수 결과 JSONL: `reports/request_segment_llm_condition_b_shadow_100_human_reviewed.jsonl`
- 검수 집계 JSON: `reports/request_segment_llm_condition_b_shadow_100_human_review_counts.json`
- 검수 요약 보고서: `reports/request_segment_llm_condition_b_shadow_100_human_review_summary.md`

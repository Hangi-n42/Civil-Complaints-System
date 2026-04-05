# Week3 BE3 EXAONE Context A/B 비교 리포트

작성일: 2026-04-05  
대상: `candidate_exaone_3_5_7_8b` (`exaone3.5:7.8b-instruct`)  
케이스 수: 100  
비교 범위: Stage 1 / Stage 2

---

## 1. 비교 목적

Week3 BE3 기준에서 EXAONE 모델에 대해 `num_ctx` 변경(1024 -> 2048)이 JSON 파싱 안정성, 답변 생성률, citation 정합성, 응답 지연에 미치는 영향을 확인한다.

---

## 2. 실험 설정

| Stage | 설정 | 비고 |
|---|---|---|
| Stage 1 | `num_ctx=1024`, `num_predict=128` | 컨텍스트 기준선 |
| Stage 2 | `num_ctx=2048`, `num_predict=128` | 컨텍스트 확장 검증 |

공통 조건:
- `temperature=0.2`
- `timeout_sec=90`
- `repetitions_per_case=1`
- 입력: `logs/evaluation/week3/evaluation_set_100.json`
- 정책: citation-empty 강제 실패 미적용

---

## 3. 핵심 결과 비교

| Stage | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |
|---|---:|---:|---:|---:|---:|
| Stage 1 (`1024/128`) | 1.0 | 0.30 | 0.00 | 23.4292 | 32.1066 |
| Stage 2 (`2048/128`) | 0.98 | 0.28 | 0.00 | 32.1820 | 56.2073 |

---

## 4. 해석

### Stage 1 (`1024/128`)
- 파싱 안정성은 확보됐다(parse_success_rate = 1.0).
- 답변 생성률은 0.30으로, 응답이 비어있지 않은 케이스가 일부 있으나 여전히 낮다.
- citation 정합성은 0.0으로 근거 연결 품질이 확보되지 않았다.
- 평균 지연은 23.4292초이다.

### Stage 2 (`2048/128`)
- `num_ctx`를 2048로 확장했지만 파싱률은 0.98로 소폭 하락했다.
- 답변 생성률은 0.30 -> 0.28로 소폭 하락했다.
- citation 정합성은 여전히 0.0이다.
- 평균 지연은 **32.1820초로 약 8.75초 증가했다**, 약 37.4% 악화.
- p95 지연도 32.1066 -> 56.2073으로 크게 증가했다.

---

## 5. 권장안 판단

### 성능 관점
- **더 빠른 Stage**: Stage 1 (`1024/128`)
- **더 안정적인 Stage**: Stage 1 (`1024/128`)
- **파싱 안정성**: Stage 1이 우위다.

### 품질 관점
- Stage 1/2 모두 citation_match_rate가 0.0으로 근거 정합성 기준에 미달한다.
- Stage 2는 컨텍스트를 늘렸지만 답변 생성률과 파싱 안정성이 개선되지 않았다.

### 결론
- **이번 EXAONE A/B에서는 Stage 1(`1024/128`)이 더 낫다.**
- Stage 2(`2048/128`)는 지연이 늘고 파싱 안정성도 약화되어, 현재 조건에서는 추천되지 않는다.
- 다음 단계는 `num_ctx` 확장보다 citation 규칙 강화, 출력 제약 강화, 프롬프트 조정이 우선이다.

---

## 6. 운영 메모

- Stage 2 실행 중 case 77, 78에서 일시적인 에러가 관측됐지만 이후 정상 복구되었고, 전체 100개 케이스는 종료 코드 0으로 완료됐다.
- 따라서 최종 비교는 완료된 결과 파일을 기준으로 해석하는 것이 적절하다.

---

## 7. 다음 개선 포인트

1. citation 강제 규칙 강화
- citations 최소 1개 이상 필수화
- 근거가 없으면 제한 응답 또는 실패 처리

2. 출력 품질 조정
- 프롬프트를 더 짧고 강하게 고정
- JSON 스키마를 더 엄격하게 명시

3. 추가 A/B 제안
- `num_predict=128` 유지
- `num_ctx=1024` 유지 후 citation 필수화 전/후 비교
- context 확장보다 answer/citation 품질 개선 실험 우선

---

## 8. 관련 파일

- [Stage 1 결과](../../../logs/evaluation/week3/exaone_stage1_ctx1024/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [Stage 1 요약](../../../logs/evaluation/week3/exaone_stage1_ctx1024/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [Stage 2 결과](../../../logs/evaluation/week3/exaone_stage2_ctx2048/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [Stage 2 요약](../../../logs/evaluation/week3/exaone_stage2_ctx2048/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [Stage 1 raw responses](../../../logs/evaluation/week3/exaone_stage1_ctx1024/raw_responses.jsonl)
- [Stage 2 raw responses](../../../logs/evaluation/week3/exaone_stage2_ctx2048/raw_responses.jsonl)
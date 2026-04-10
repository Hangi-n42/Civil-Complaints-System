# Week5 BE3 4개 모델 sample50 비교 리포트

작성일: 2026-04-09  
대상: ax4-light-local:latest, exaone3.5:7.8b-instruct, gemma3:12b, gemma4:26b  
비교 범위: Week5 Stage 1 / num_ctx=1024 / sample50 동일 조건 비교  
비고: 4개 모델 모두 동일한 50개 케이스(`logs/evaluation/week3/evaluation_set_50.json`)와 동일 설정(`temp=0.2`, `num_predict=128`, `timeout_sec=90`)으로 측정했다.

---

## 1. 목적

이 문서는 Week5에서 진행한 4개 모델 sample50 벤치마크 결과를 하나의 흐름으로 정리한다.

핵심 질문은 다음과 같다.
- 동일 조건에서 4개 모델의 파싱/답변/citation/지연 성능은 어떻게 달랐는가
- strict / repaired 기준에서 어떤 차이가 남아 있는가
- 실제 운영 관점에서 어떤 모델이 가장 적합한가
- 데모 및 평가 대응을 위해 어떤 모델 조합이 현실적인가

---

## 2. 실험 조건

| 항목 | 공통 조건 |
|---|---|
| 모델 수 | 4개 |
| 케이스 수 | 50 |
| 입력 케이스 | `logs/evaluation/week3/evaluation_set_50.json` |
| num_ctx | 1024 |
| num_predict | 128 |
| temperature | 0.2 |
| timeout_sec | 90 |
| repetitions_per_case | 1 |
| 평가 기준 | strict + repaired |

---

## 3. 핵심 결과 비교

### 3.1 전체 지표

| 모델 | parse_success_rate | answer_non_empty_rate_strict | answer_non_empty_rate_repaired | citation_match_rate_strict | citation_match_rate_repaired | avg_latency_sec | p95_latency_sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| ax4-light-local:latest | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 13.2170 | 15.8466 |
| exaone3.5:7.8b-instruct | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 16.0846 | 16.7138 |
| gemma4:26b | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 18.3473 | 19.7273 |
| gemma3:12b | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 19.3726 | 20.1175 |

### 3.2 한 줄 요약
- **속도는 ax4-light-local:latest가 가장 빠르다.**
- **exaone3.5:7.8b-instruct는 ax4 다음으로 빠르며 지연 안정성도 좋다.**
- **gemma4:26b는 gemma3:12b보다 빠르지만, 둘 다 ax4/exaone 대비 느리다.**
- **이번 sample50에서는 4개 모델 모두 strict answer와 repaired answer/citation이 전부 1.0으로 수렴했다.**

---

## 4. 모델별 상세 해석

### 4.1 ax4-light-local:latest

- parse_success_rate: 1.0
- answer_non_empty_rate_strict: 1.0
- answer_non_empty_rate_repaired: 1.0
- citation_match_rate_strict: 0.0
- citation_match_rate_repaired: 1.0
- avg_latency_sec: 13.2170
- p95_latency_sec: 15.8466

해석:
- 4개 모델 중 가장 빠르다.
- strict와 repaired 모두 answer가 1.0으로 유지되어, sample50 기준으로는 답변 생성 안정성도 충분하다.
- citation은 strict에서 여전히 0.0이지만 repaired에서 1.0으로 회복된다.
- 이 조합은 데모에서 체감 속도 측면의 장점이 가장 크다.

### 4.2 exaone3.5:7.8b-instruct

- parse_success_rate: 1.0
- answer_non_empty_rate_strict: 1.0
- answer_non_empty_rate_repaired: 1.0
- citation_match_rate_strict: 0.0
- citation_match_rate_repaired: 1.0
- avg_latency_sec: 16.0846
- p95_latency_sec: 16.7138

해석:
- ax4보다 평균 2.9초 정도 느리지만, 여전히 16초대 초반으로 운영 가능한 범위다.
- p95가 16.7초로 좁게 유지되어 지연 분산이 크지 않다.
- sample50 기준으로는 answer/citation 품질이 ax4와 동일하게 수렴하여, 속도 차이가 주된 구분점이다.

### 4.3 gemma4:26b

- parse_success_rate: 1.0
- answer_non_empty_rate_strict: 1.0
- answer_non_empty_rate_repaired: 1.0
- citation_match_rate_strict: 0.0
- citation_match_rate_repaired: 1.0
- avg_latency_sec: 18.3473
- p95_latency_sec: 19.7273

해석:
- exaone보다 느리고, gemma3보다는 빠르다.
- 4개 모델 중 중간권이지만, sample50에서는 품질 차별점이 보이지 않아 속도에서 불리하다.
- 보정 경로 기준으로는 충분히 시연 가능하지만, 기본 후보로는 우선순위가 낮다.

### 4.4 gemma3:12b

- parse_success_rate: 1.0
- answer_non_empty_rate_strict: 1.0
- answer_non_empty_rate_repaired: 1.0
- citation_match_rate_strict: 0.0
- citation_match_rate_repaired: 1.0
- avg_latency_sec: 19.3726
- p95_latency_sec: 20.1175

해석:
- 4개 중 가장 느리다.
- 샘플50 기준으로는 품질이 다른 모델보다 떨어지지 않지만, 지연이 가장 길어 운영 관점에서 손해가 크다.
- 따라서 이번 비교에서는 균형형 장점이 드러나지 않았고, latency 기준으로는 가장 약하다.

---

## 5. 운영 관점 결론

| 항목 | 판단 |
|---|---|
| 파싱 안정성 | 4개 모두 동일 |
| answer 생성력 | 4개 모두 동일 |
| repaired citation | 4개 모두 동일 |
| 지연 성능 | ax4 > exaone > gemma4 > gemma3 |

결론:
- **이번 sample50 기준에서는 품질 지표가 모두 수렴했기 때문에, 사실상 지연 성능이 모델 선택을 좌우한다.**
- 이 조건에서는 **ax4-light-local:latest가 가장 유리**하고, **exaone3.5:7.8b-instruct가 바로 다음 후보**다.
- gemma4:26b와 gemma3:12b는 repaired 기준 데모는 가능하지만, 동일 품질이라면 더 느린 쪽을 선택할 이유가 약하다.

---

## 6. 해석 포인트

### 6.1 이번 sample50의 특징
- 4개 모델 모두 parse_success_rate가 1.0이다.
- 4개 모델 모두 strict answer_non_empty_rate가 1.0이다.
- 4개 모델 모두 repaired citation_match_rate가 1.0이다.
- 즉, 이번 실험에서는 **품질 격차보다 속도 격차가 더 크게 드러났다.**

### 6.2 기존 Week4 리포트와의 차이
- Week4 통합 리포트에서는 strict / repaired 분리 의미가 더 크게 나타났다.
- 이번 sample50에서는 네 모델 모두 strict와 repaired가 동일하게 잘 수렴해, 보정 효과보다는 모델별 지연 차이가 더 두드러진다.
- 따라서 이번 리포트는 **서비스 가용성 비교**보다는 **실행 효율 비교** 성격이 강하다.

---

## 7. 권장안

### 7.1 기본 운영 후보
1. **ax4-light-local:latest**
   - 가장 빠르다.
   - sample50 기준 품질 손실이 확인되지 않았다.

2. **exaone3.5:7.8b-instruct**
   - ax4 다음으로 빠르다.
   - 지연 분산이 작아 안정적인 대체 후보로 적합하다.

### 7.2 보조 후보
- **gemma4:26b**: 중간 속도 실험군
- **gemma3:12b**: 가장 느려 우선순위가 낮음

---

## 8. 최종 결론

1. sample50 기준 4개 모델은 모두 파싱과 답변 생성, repaired citation 정합성에서 동일한 수준까지 수렴했다.
2. 따라서 이번 비교에서는 모델 품질 차이보다 지연 성능 차이가 핵심이다.
3. 운영 기준으로는 **ax4-light-local:latest**가 가장 유리하고, **exaone3.5:7.8b-instruct**가 가장 현실적인 차선 후보다.
4. gemma4:26b와 gemma3:12b는 시연 가능성은 확보되지만, 동일 품질 기준이면 속도에서 불리하다.

---

## 9. 관련 파일

### sample50 결과 요약
- [ax4 요약](../../../logs/evaluation/week5/ax4_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_ax4_light.md)
- [exaone 요약](../../../logs/evaluation/week5/exaone_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [gemma3 요약](../../../logs/evaluation/week5/gemma3_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma3_12b.md)
- [gemma4:26b 요약](../../../logs/evaluation/week5/gemma4_26b_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma4_26b.md)

### Week4 기준 참고
- [Week4 통합 리포트](../week4/WEEK4_BE3_INTEGRATED_WEEK3_TO_WEEK4_MODEL_REPORT.md)

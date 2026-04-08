# Week4 BE3 GEMMA 3모델 비교 리포트

작성일: 2026-04-07  
대상: gemma3:12b, gemma4:26b, gemma4:e4b  
케이스 수: 100 (동일)  
비교 범위: Week4 Stage1 동조건 직접 비교

---

## 1. 비교 목적

Week4 동일 조건에서 GEMMA 계열 3개 모델의 품질/지연 트레이드오프를 확인한다.

비교 관점:
- 파싱 안정성
- answer 생성률(Strict/Repaired)
- citation 정합성(Strict/Repaired)
- 응답 지연(평균, p95)

---

## 2. 실험 설정

| 항목 | GEMMA3 | GEMMA4-26B | GEMMA4-E4B |
|---|---|---|---|
| 모델 | gemma3:12b | gemma4:26b | gemma4:e4b |
| 실행 ID | candidate_gemma3_12b | candidate_gemma4_26b | candidate_gemma4_e4b |
| 온도 | 0.2 | 0.2 | 0.2 |
| num_ctx | 1024 | 1024 | 1024 |
| num_predict | 128 | 128 | 128 |
| timeout_sec | 90 | 90 | 90 |
| repetitions_per_case | 1 | 1 | 1 |
| 입력 케이스 | logs/evaluation/week3/evaluation_set_100.json | 동일 | 동일 |
| 평가 방식 | strict + repaired | strict + repaired | strict + repaired |

---

## 3. 핵심 결과 비교

### 3.1 전체 지표 비교

| 지표 | GEMMA3 | GEMMA4-26B | GEMMA4-E4B | 우세 |
|---|---:|---:|---:|---|
| parse_success_rate | 1.0 | 1.0 | 1.0 | 동률 |
| answer_non_empty_rate_strict | 0.82 | 0.15 | 0.55 | GEMMA3 |
| answer_non_empty_rate_repaired | 1.0 | 1.0 | 1.0 | 동률 |
| citation_match_rate_strict | 0.0 | 0.0 | 0.0 | 동률 |
| citation_match_rate_repaired | 1.0 | 1.0 | 1.0 | 동률 |
| avg_latency_sec | 19.6311 | 18.9228 | 21.4271 | GEMMA4-26B |
| p95_latency_sec | 20.7955 | 20.3807 | 25.0768 | GEMMA4-26B |

### 3.2 순위 요약

- strict answer 생성률: GEMMA3(0.82) > GEMMA4-E4B(0.55) > GEMMA4-26B(0.15)
- 평균 지연: GEMMA4-26B(18.9228s) < GEMMA3(19.6311s) < GEMMA4-E4B(21.4271s)
- p95 지연: GEMMA4-26B(20.3807s) < GEMMA3(20.7955s) < GEMMA4-E4B(25.0768s)

### 3.3 모델 간 차이(핵심)

- GEMMA3 vs GEMMA4-26B
	- strict answer: +0.67p (0.82 - 0.15)
	- avg latency: +0.7083초 (GEMMA3가 느림)
- GEMMA3 vs GEMMA4-E4B
	- strict answer: +0.27p (0.82 - 0.55)
	- avg latency: +1.7960초 (GEMMA3가 빠름)
- GEMMA4-E4B vs GEMMA4-26B
	- strict answer: +0.40p (0.55 - 0.15)
	- avg latency: +2.5043초 (E4B가 느림)

---

## 4. 해석

### 4.1 안정성 관점
- 3개 모델 모두 parse_success_rate 1.0으로 파싱 안정성은 동일하다.
- repaired answer/citation도 모두 1.0이라 파이프라인 보정 이후 서비스 가용성은 동일하다.

### 4.2 모델 자체 출력 품질(strict) 관점
- GEMMA3가 strict answer 0.82로 가장 높다.
- GEMMA4-E4B는 0.55로 중간 수준이다.
- GEMMA4-26B는 0.15로 가장 낮아 strict 품질 의존 시 불리하다.

### 4.3 지연 관점
- 속도는 GEMMA4-26B가 평균/p95 모두 가장 빠르다.
- GEMMA3는 속도 2위지만 strict 품질 1위라 균형형 선택지다.
- GEMMA4-E4B는 strict 품질은 중간이지만 지연이 가장 느리다.

---

## 5. 운영 권장안

| 운영 우선순위 | 권장 모델 | 이유 |
|---|---|---|
| strict 품질 최우선 | gemma3:12b | strict answer 최고(0.82) |
| 지연 최우선 | gemma4:26b | avg/p95 최저 |
| 품질-지연 균형 | gemma3:12b | strict 우세 + 지연도 2위로 안정적 |
| 보정 파이프라인 기반 시연 | 3모델 모두 가능 | repaired 기준이 모두 1.0 |

---

## 6. 결론

- 모델 자체 품질(strict) 기준 최적: gemma3:12b
- 지연 기준 최적: gemma4:26b
- gemma4:e4b는 strict 품질이 26b보다 낫지만, 지연 비용이 커서 현재 조건에서는 우선순위가 낮다.

종합적으로, 현재 Week4 Stage1 조건에서는 기본 후보를 gemma3:12b로 두고, 지연 민감 시나리오에 한해 gemma4:26b를 대안으로 운용하는 구성이 가장 합리적이다.

---

## 7. 관련 파일

### GEMMA3 Week4
- [요약](../../../logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md)
- [결과 JSON](../../../logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.json)

### GEMMA4:26B Week4
- [요약](../../../logs/evaluation/week4/gemma4_ctx1024/model_benchmark_candidate_candidate_gemma4_26b.md)
- [결과 JSON](../../../logs/evaluation/week4/gemma4_ctx1024/model_benchmark_candidate_candidate_gemma4_26b.json)

### GEMMA4:E4B Week4
- [요약](../../../logs/evaluation/week4/gemma4_e4b_ctx1024/model_benchmark_candidate_candidate_gemma4_e4b.md)
- [결과 JSON](../../../logs/evaluation/week4/gemma4_e4b_ctx1024/model_benchmark_candidate_candidate_gemma4_e4b.json)

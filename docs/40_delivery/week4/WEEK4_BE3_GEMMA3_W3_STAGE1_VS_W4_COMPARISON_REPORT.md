# Week4 BE3 GEMMA3 Week3 Stage1 vs Week4 비교 리포트

작성일: 2026-04-07  
대상: gemma3:12b  
비교 범위: Week3 Stage1 (`num_ctx=1024`) vs Week4 Stage1 (`num_ctx=1024`)  
비고: Week3는 legacy `answer_non_empty_rate` 기준, Week4는 `strict/repaired` 분리 기준

---

## 1. 비교 목적

Week3 Stage1과 Week4 Stage1에서 동일 모델(gemma3:12b)의 결과가 어떻게 달라졌는지 확인한다.

특히 다음을 본다.
- 파싱 안정성
- 답변 생성률 변화
- citation 정합성 변화
- 응답 지연 변화
- strict/repaired 분리 도입 효과

---

## 2. 실험 조건

| 항목 | Week3 Stage1 | Week4 Stage1 |
|---|---|---|
| 모델 | gemma3:12b | gemma3:12b |
| num_ctx | 1024 | 1024 |
| num_predict | 128 | 128 |
| temperature | 0.2 | 0.2 |
| timeout_sec | 90 | 90 |
| repetitions_per_case | 1 | 1 |
| 입력 케이스 | logs/evaluation/week3/evaluation_set_100.json | 동일 |
| 평가 기준 | legacy answer/citation | strict + repaired |

---

## 3. 핵심 결과 비교

### 3.1 전체 지표

| 지표 | Week3 Stage1 | Week4 Stage1 | 변화 |
|---|---:|---:|---:|
| parse_success_rate | 1.0 | 1.0 | 동일 |
| answer_non_empty_rate | 0.31 | 0.82 (strict) / 1.0 (repaired) | 크게 개선 |
| citation_match_rate | 0.0 | 0.0 (strict) / 1.0 (repaired) | 보정 후 개선 |
| avg_latency_sec | 20.2235 | 19.6311 | -0.5924초 |
| p95_latency_sec | 24.4759 | 20.7955 | -3.6804초 |

### 3.2 해석 포인트

- Week4는 파싱 성공률이 동일하게 1.0이다.
- 답변 생성률은 legacy 기준 0.31에서 strict 기준 0.82로 크게 상승했다.
- repaired 기준으로는 answer/citation이 모두 1.0까지 회복된다.
- 지연도 평균과 p95 모두 개선되어, Week4가 Week3보다 더 안정적인 실행 분포를 보인다.

---

## 4. 상세 해석

### 4.1 파싱 안정성
- 두 시점 모두 parse_success_rate는 1.0이다.
- 즉, JSON 파싱 자체는 Week3부터 이미 안정적이었다.

### 4.2 답변 생성률
- Week3 Stage1은 legacy answer_non_empty_rate가 0.31로 낮았다.
- Week4 Stage1은 strict 기준 0.82, repaired 기준 1.0이다.
- 이는 모델 자체 출력 품질뿐 아니라, 파이프라인 보정과 후처리 효과가 함께 반영된 결과로 해석해야 한다.

### 4.3 citation 정합성
- Week3 Stage1은 citation_match_rate가 0.0이었다.
- Week4 Stage1은 strict 기준 0.0이지만 repaired 기준 1.0이다.
- 즉, 원본 모델 출력의 citation 품질은 여전히 낮지만, 보정 경로를 통해 서비스 결과는 회복된다.

### 4.4 지연 성능
- 평균 지연은 20.2235초 -> 19.6311초로 감소했다.
- p95 지연은 24.4759초 -> 20.7955초로 더 크게 감소했다.
- Week4는 상위 지연 구간이 더 안정화된 것으로 볼 수 있다.

---

## 5. 운영 관점 결론

| 항목 | 판단 |
|---|---|
| 파싱 안정성 | 동률 |
| 원본 답변 생성력 | Week4가 더 유리 |
| 보정 후 서비스 품질 | Week4가 더 유리 |
| 지연 성능 | Week4가 더 유리 |

결론:
- gemma3:12b는 Week4에서 Week3 대비 전반적으로 개선됐다.
- 특히 answer 생성률과 지연 분포가 함께 좋아져, 운영 기준 모델로 유지할 근거가 강화됐다.
- 다만 citation의 원본 strict 품질은 여전히 0.0이므로, 보정 파이프라인 의존은 계속 필요하다.

---

## 6. 참고 파일

### Week3 Stage1
- [요약](../../../logs/evaluation/week3/gemma_stage1_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md)

### Week4 Stage1
- [요약](../../../logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md)
- [결과 JSON](../../../logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.json)

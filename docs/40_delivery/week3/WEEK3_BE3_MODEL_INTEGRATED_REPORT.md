# Week3 BE3 모델 통합 비교 리포트 (EXAONE / PHI4 / GEMMA)

작성일: 2026-04-02  
대상: `candidate_exaone_3_5_7_8b`, `candidate_phi4_mini`, `candidate_gemma3_12b`  
케이스 수: 100  
비교 범위: 모델별 A/B 테스트 결과 통합 비교

---

## 1. 통합 목적

Week3 BE3 기준으로 EXAONE, PHI4, GEMMA의 A/B 테스트 결과를 한 곳에 모아,
- JSON 파싱 안정성
- 답변 생성률
- citation 정합성
- 응답 지연
관점에서 모델별 강점/약점을 비교하고, 다음 단계 우선순위를 정리한다.

---

## 2. 실험 조건 요약

공통 조건:
- `temperature=0.2`
- `timeout_sec=90`
- `repetitions_per_case=1`
- 입력: `logs/evaluation/week3/evaluation_set_100.json`
- 정책: citation-empty 강제 실패 미적용

모델별 비교 조건:
- EXAONE: `num_ctx` 2048/1024, `num_predict` 256/128 조합 3단계
- PHI4: `num_predict=128` 고정, `num_ctx` 1024 vs 2048
- GEMMA: `num_predict=128` 고정, `num_ctx` 1024 vs 2048

---

## 3. 모델별 Best Stage 비교

모델별 A/B 중 상대적으로 유리한 Stage를 대표값으로 비교:

| Model | 대표 Stage | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |
|---|---|---:|---:|---:|---:|---:|
| EXAONE | Stage 3 (`num_ctx=1024`, `num_predict=128`) | 1.0 | 0.33 | 0.00 | 15.7420 | 16.6224 |
| PHI4 | Stage 1 (`num_ctx=1024`, `num_predict=128`) | 1.0 | 0.03 | 0.00 | 22.8132 | 24.0367 |
| GEMMA | Stage 1 (`num_ctx=1024`, `num_predict=128`) | 1.0 | 0.31 | 0.00 | 20.2235 | 24.4759 |

참고:
- EXAONE Stage 1은 answer_non_empty_rate가 0.70으로 가장 높지만 avg_latency_sec가 25.4296으로 길어, 지연 관점에서 Stage 3를 대표값으로 선택했다.

---

## 4. 모델별 관찰 포인트

### EXAONE
- 파싱 안정성은 전 구간 1.0으로 안정적이다.
- `num_predict` 축소로 지연이 크게 개선됐다.
- citation 정합성은 Stage 1의 0.03 외에는 0.0으로 낮다.

### PHI4
- 파싱 안정성은 1.0으로 안정적이다.
- `num_ctx`를 2048로 늘려도 답변 생성률 개선이 없고 오히려 하락했다.
- 지연도 증가해 컨텍스트 확장 이득이 확인되지 않았다.

### GEMMA
- 파싱 안정성은 1.0으로 안정적이다.
- PHI4보다 answer_non_empty_rate가 높다(0.31 vs 0.03, 대표값 기준).
- `num_ctx` 2048 확장 시 품질 개선 없이 지연만 증가했다.

---

## 5. 통합 결론

1. 파싱 안정성 관점
- 세 모델 모두 parse_success_rate 1.0으로 안정적이다.

2. 품질 관점
- citation_match_rate가 전반적으로 0.0에 머물러, 근거 정합성은 아직 핵심 미해결 이슈다.
- answer_non_empty_rate는 EXAONE(Stage 1) > GEMMA(Stage 1) >> PHI4(Stage 1) 순으로 관측된다.

3. 지연 관점
- 대표값 기준 평균 지연은 EXAONE(Stage 3) < GEMMA(Stage 1) < PHI4(Stage 1) 순이다.

4. 현재 단계 권장
- 임시 운영 기준:
  - 지연 중심: EXAONE Stage 3
  - 답변 생성률 균형: GEMMA Stage 1
- 단, 어떤 모델도 citation 정합성 목표를 만족하지 못해 최종 baseline 확정은 보류가 타당하다.

---

## 6. 다음 액션 (우선순위)

1. citation 강제 규칙 실험 (최우선)
- citations 최소 1개 이상 필수화
- citation이 비면 제한 응답 강제 전환

2. 출력 품질 개선 실험
- 프롬프트에서 answer 필드 생성 규칙 강화
- 최소 답변 길이 가이드 도입

3. 비교 재측정
- 동일 조건에서 citation 강제 전/후를 모델별로 재측정
- 통합 리포트 지표를 동일 포맷으로 재업데이트

---

## 7. 상세 리포트 링크

- [EXAONE A/B 리포트](WEEK3_BE3_AB_COMPARISON_REPORT.md)
- [PHI4 A/B 리포트](WEEK3_BE3_PHI4_AB_COMPARISON_REPORT.md)
- [GEMMA A/B 리포트](WEEK3_BE3_GEMMA_AB_COMPARISON_REPORT.md)

세부 결과 파일:
- [EXAONE Stage 1 결과](../../../logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [EXAONE Stage 2 결과](../../../logs/evaluation/week3/ab_stage2/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [EXAONE Stage 3 결과](../../../logs/evaluation/week3/ab_stage3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [PHI4 Stage 1 결과](../../../logs/evaluation/week3/phi4_stage1/model_benchmark_candidate_candidate_phi4_mini.json)
- [PHI4 Stage 2 결과](../../../logs/evaluation/week3/phi4_stage2_ctx2048/model_benchmark_candidate_candidate_phi4_mini.json)
- [GEMMA Stage 1 결과](../../../logs/evaluation/week3/gemma_stage1_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.json)
- [GEMMA Stage 2 결과](../../../logs/evaluation/week3/gemma_stage2_ctx2048/model_benchmark_candidate_candidate_gemma3_12b.json)

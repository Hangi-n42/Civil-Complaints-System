# Week4 BE3 통합 벤치마크 및 모델 추천 리포트

작성일: 2026-04-08  
대상: exaone3.5:7.8b-instruct, ax4-light-local:latest, gemma3:12b, gemma4:26b, gemma4:e4b  
비교 범위: Week3 Stage 1 / Week4 Stage 1 / Week4 API 통합 후 성능 비교  

---

## 1. 목적

이 문서는 Week3에서 Week4로 넘어오면서 BE3 `/qa`와 벤치마크 경로에 어떤 작업이 들어갔고, 그 작업이 실제 수치에 어떤 변화를 만들었는지 하나의 흐름으로 정리한다.

핵심 질문은 다음과 같다.
- Week3 대비 Week4에서 무엇을 바꿨는가
- 어떤 작업이 어떤 지표를 개선했는가
- 현재 프로젝트에 가장 적합한 모델은 무엇인가
- 아직 남은 문제는 무엇이고, 다음 개선 방향은 무엇인가

---

## 2. Week3 -> Week4에서 실제로 한 작업

Week4에서는 단순히 모델만 다시 돌린 것이 아니라, 서비스 경로와 측정 경로를 맞추는 작업을 먼저 수행했다.

### 2.1 공통 파싱/검증 경로 통합
- 벤치마크와 API가 서로 다른 JSON 파싱/정규화/검증 규칙을 쓰지 않도록 정리했다.
- 공통 유틸을 재사용하도록 바꾸어, 벤치마크 수치가 실제 서비스 동작을 더 잘 반영하게 만들었다.

### 2.2 answer 최소 품질 가드 추가
- 빈 문자열이나 의미 없는 응답을 그대로 통과시키지 않도록 정규화와 최소 품질 가드를 넣었다.
- 이 작업이 repaired 기준 answer 회복의 핵심이었다.

### 2.3 citation 자동 교정과 재시도 정책 추가
- citation이 비거나 정합성이 맞지 않으면 compact fallback 또는 재생성 경로로 넘기도록 했다.
- 결과적으로 repaired 기준 citation_match_rate가 1.0까지 회복되었다.

### 2.4 strict / repaired 지표 분리
- strict: 모델 원본 출력 성능
- repaired: 파싱/정규화/교정 이후 서비스 성능
- 이 분리를 통해 “모델이 못한 것”과 “파이프라인이 보정한 것”을 구분해서 볼 수 있게 됐다.

### 2.5 벤치마크 경로 정렬
- API 기준과 같은 기준으로 결과를 측정하도록 스크립트를 정리했다.
- 그래서 Week4 수치는 단순 모델 점수라기보다 실제 서비스 가능성을 보여주는 값이 되었다.

---

## 3. 전체 요약

### 3.1 모델별 핵심 결과

| 모델 | Week3 Stage 1 | Week4 Strict | Week4 Repaired | 해석 |
|---|---:|---:|---:|---|
| exaone3.5:7.8b-instruct | answer=0.30, avg=23.4292, p95=32.1066 | answer=0.87, avg=17.1425, p95=18.8699 | answer=1.0, citation=1.0 | 품질과 지연이 모두 크게 개선 |
| ax4-light-local:latest | answer=0.0, avg=30.3459, p95=32.7393 | answer=0.0, avg=13.0711, p95=14.5985 | answer=1.0, citation=1.0 | 속도는 최고, 원본 답변은 여전히 취약 |
| gemma3:12b | answer=0.31, avg=20.2235, p95=24.4759 | answer=0.82, avg=19.6311, p95=20.7955 | answer=1.0, citation=1.0 | 가장 균형이 좋음 |
| gemma4:26b | Week3 비교 대상 없음 | answer=0.15, avg=18.9228, p95=20.3807 | answer=1.0, citation=1.0 | 지연은 좋지만 원본 품질이 낮음 |
| gemma4:e4b | Week3 비교 대상 없음 | answer=0.55, avg=21.4271, p95=25.0768 | answer=1.0, citation=1.0 | 26b보다 답변은 낫지만 지연이 큼 |

### 3.2 한 줄 결론
- **품질만 보면 exaone3.5:7.8b-instruct가 가장 우수하다.**
- **지연만 보면 ax4-light-local:latest가 가장 빠르다.**
- **균형과 운영 안정성까지 포함하면 gemma3:12b가 가장 무난한 기본 후보다.**

---

## 4. 모델별 변화 분석

### 4.1 exaone3.5:7.8b-instruct

Week3 Stage 1 대비 Week4에서 가장 눈에 띄는 변화가 있었다.

- answer_non_empty_rate: 0.30 -> 0.87
- avg_latency_sec: 23.4292 -> 17.1425
- p95_latency_sec: 32.1066 -> 18.8699

이 개선은 다음 작업의 효과로 해석할 수 있다.
- 공통 파싱/검증 유틸화
- 답변 최소 품질 가드
- citation 교정 경로
- strict/repaired 분리로 실제 개선이 더 잘 드러남

### 4.2 ax4-light-local:latest

Week3 Stage 1에서는 answer가 0.0이었지만, Week4에서는 repaired 기준으로 전부 복구되었다.

- answer_non_empty_rate_strict: 0.0 -> 0.0
- answer_non_empty_rate_repaired: 1.0
- avg_latency_sec: 30.3459 -> 13.0711
- p95_latency_sec: 32.7393 -> 14.5985

해석:
- 원본 모델 출력 자체는 여전히 비어 있는 경우가 많아 strict 기준으론 약하다.
- 하지만 서비스 보정 체계가 잘 작동해 repaired 기준에서는 충분히 시연 가능하다.
- 속도는 매우 뛰어나지만, 프로젝트 기본 모델로 쓰기엔 원본 품질이 부족하다.

### 4.3 gemma3:12b

Week3 Stage 1 대비 Week4에서 답변 생성률이 크게 좋아졌다.

- answer_non_empty_rate: 0.31 -> 0.82 (strict)
- repaired 기준 answer/citation: 1.0 / 1.0
- avg_latency_sec: 20.2235 -> 19.6311
- p95_latency_sec: 24.4759 -> 20.7955

해석:
- Week4에서 가장 안정적인 균형형 모델이다.
- 속도는 exaone보다 약간 느리지만, 여전히 충분히 운영 가능한 수준이다.
- 현재 BE3 맥락에서 가장 무난한 기본 후보 중 하나다.

### 4.4 gemma4:26b

Week4에서 새로 추가된 모델로, strict 품질은 낮고 속도는 좋은 편이다.

- answer_non_empty_rate_strict: 0.15
- repaired 기준 answer/citation: 1.0 / 1.0
- avg_latency_sec: 18.9228
- p95_latency_sec: 20.3807

해석:
- 지연은 좋지만 원본 답변 생성력이 너무 낮아 기본 후보로는 약하다.
- 보정 후에는 서비스 가능하나, 모델 자체 품질 설명이 필요한 평가에서는 불리하다.

### 4.5 gemma4:e4b

gemma4:26b보다 strict answer는 높지만, 지연이 더 크다.

- answer_non_empty_rate_strict: 0.55
- repaired 기준 answer/citation: 1.0 / 1.0
- avg_latency_sec: 21.4271
- p95_latency_sec: 25.0768

해석:
- gemma4 계열 중에서는 26b보다 품질이 낫다.
- 다만 속도가 느려서 운영 효율성은 떨어진다.
- 중간 성격의 실험군으로는 의미가 있지만, 기본 모델로는 우선순위가 낮다.

---

## 5. 프로젝트에 알맞은 모델

### 5.1 최종 추천
**기본 운영 모델은 exaone3.5:7.8b-instruct가 가장 적합하다.**

이유:
- strict answer_non_empty_rate가 0.87로 가장 높다.
- avg/p95 지연도 충분히 낮아 실제 운영에 무리가 없다.
- parse_success_rate와 repaired 지표도 모두 1.0이라 서비스 안정성이 확보된다.

### 5.2 보조 추천
- **지연 우선 경로**: ax4-light-local:latest
- **균형형 대안**: gemma3:12b
- **실험용 대안**: gemma4:e4b
- **비권장 기본 후보**: gemma4:26b

### 5.3 선택 기준 정리
| 기준 | 추천 모델 | 이유 |
|---|---|---|
| 원본 품질 우선 | exaone3.5:7.8b-instruct | strict answer 최고 |
| 지연 우선 | ax4-light-local:latest | 평균/p95 최저 |
| 균형형 운영 | gemma3:12b | 품질과 지연이 고르게 안정적 |
| 실험군 | gemma4:e4b | 중간 성격의 비교군 |
| 기본 제외 | gemma4:26b | strict 품질이 너무 낮음 |

---

## 6. 현재의 문제점

### 6.1 strict citation 품질이 아직 낮다
- 5모델 모두 strict citation_match_rate는 0.0이다.
- repaired 기준으로는 1.0까지 회복되지만, 원본 모델이 근거를 자발적으로 잘 붙이지는 못한다.

### 6.2 ax4는 속도는 좋지만 원본 answer가 비어 있다
- ax4는 strict answer_non_empty_rate가 0.0이다.
- 즉, 서비스 보정 없이는 모델 자체 품질만으로 쓰기 어렵다.

### 6.3 gemma4:26b는 지연 대비 원본 품질이 낮다
- 속도는 좋지만 strict answer가 0.15라서 실사용 기본 모델로는 약하다.

### 6.4 repaired 의존도가 높다
- 현재 서비스 가용성은 repaired 경로에서 완성된다.
- 데모와 운영은 가능하지만, 모델 본체 품질을 더 끌어올릴 여지는 남아 있다.

---

## 7. 앞으로의 개선 사항

### 7.1 답변 품질 강화
- answer 최소 길이 기준을 더 명확히 한다.
- 빈 응답을 더 강하게 제한하고, 의미 있는 제한 응답 템플릿을 고정한다.

### 7.2 citation 강화
- citation가 없으면 실패로 보는 정책을 더 엄격하게 적용한다.
- 필요한 경우 retrieval context와 강제 매핑 규칙을 더 세분화한다.

### 7.3 모델 라우팅
- 요청 유형별로 모델을 나눈다.
- 예: 일반 질의는 exaone, 초저지연은 ax4, 균형형은 gemma3.

### 7.4 회귀 테스트 강화
- strict / repaired 두 기준 모두를 회귀 테스트에 넣는다.
- 시나리오별로 answer와 citation을 동시에 검증한다.

### 7.5 추가 벤치마크
- prompt 강도별 비교
- citation 강제 정책 전/후 비교
- 장문/복합요청 중심 추가 샘플 벤치마크

---

## 8. 최종 결론

1. Week4로 오면서 가장 중요한 변화는 모델 교체가 아니라 **서비스 기준과 벤치마크 기준을 맞춘 것**이다.
2. 그 결과 strict/repaired를 분리해 보니, 원본 품질과 보정 효과를 구분해서 볼 수 있게 되었고, 실제 서비스 가용성은 크게 좋아졌다.
3. 프로젝트의 기본 모델은 **exaone3.5:7.8b-instruct**가 가장 적합하다.
4. 단, **gemma3:12b는 균형형 대안**, **ax4-light-local:latest는 속도 우선 경로**, **gemma4 계열은 실험군**으로 두는 구성이 현실적이다.
5. 앞으로의 핵심 과제는 strict citation 품질을 끌어올리고 repaired 의존도를 낮추는 것이다.

---

## 9. 관련 파일

### Week3 -> Week4 비교 리포트
- [EXAONE](WEEK4_BE3_EXAONE_W3_VS_W4_COMPARISON_REPORT.md)
- [AX4](WEEK4_BE3_AX4_W3_VS_W4_COMPARISON_REPORT.md)
- [GEMMA3 Week3 vs Week4](WEEK4_BE3_GEMMA3_W3_STAGE1_VS_W4_COMPARISON_REPORT.md)
- [GEMMA 3모델 비교](WEEK4_BE3_GEMMA3_VS_GEMMA4_COMPARISON_REPORT.md)

### 원본 결과
- [EXAONE Week4 요약](../../../logs/evaluation/week4/exaone_ctx1024/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [AX4 Week4 요약](../../../logs/evaluation/week4/ax4_ctx1024/model_benchmark_candidate_candidate_ax4_light.md)
- [GEMMA3 Week4 요약](../../../logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md)
- [GEMMA4:26B Week4 요약](../../../logs/evaluation/week4/gemma4_ctx1024/model_benchmark_candidate_candidate_gemma4_26b.md)
- [GEMMA4:E4B Week4 요약](../../../logs/evaluation/week4/gemma4_e4b_ctx1024/model_benchmark_candidate_candidate_gemma4_e4b.md)

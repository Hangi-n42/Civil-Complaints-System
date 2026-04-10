# Week4 vs Week5 BE3 모델 비교 분석 리포트

작성일: 2026-04-09  
비교 대상: [Week4 통합 벤치마크 및 모델 추천 리포트](../week4/WEEK4_BE3_INTEGRATED_WEEK3_TO_WEEK4_MODEL_REPORT.md), [Week5 sample50 4개 모델 비교 리포트](WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md)  
비교 범위: Week4 Stage 1 / Week5 Stage 1 sample50 / 동일 계열 모델 비교  

---

## 1. 목적

이 문서는 Week4 리포트와 Week5 리포트를 나란히 놓고, 같은 모델군이 어떤 방향으로 해석이 바뀌었는지 정리한다.

핵심 질문은 다음과 같다.
- Week4와 Week5는 같은 모델을 왜 다르게 읽어야 하는가
- 어떤 지표가 유지되었고, 어떤 지표가 달라졌는가
- 모델 추천의 우선순위가 실제로 바뀌었는가
- 데모와 운영 관점에서 어떤 해석을 우선해야 하는가

---

## 2. 두 리포트의 성격 차이

### 2.1 Week4 리포트의 성격

Week4 리포트는 Week3에서 Week4로 넘어오며 수행한 파싱/검증/보정 경로 통합의 결과를 설명한다.

이 리포트의 핵심은 다음이다.
- strict / repaired 기준 분리
- 서비스 경로와 벤치마크 경로 정렬
- 파이프라인 보정이 실제 결과를 어떻게 바꾸는지 설명
- 5개 모델을 한 번에 비교하며 최종 추천 모델을 정리

즉, Week4는 **전환 리포트**다.

### 2.2 Week5 리포트의 성격

Week5 sample50 리포트는 같은 조건에서 4개 모델을 다시 돌려, sample50 기준의 실행 효율을 비교한다.

이 리포트의 핵심은 다음이다.
- 동일 조건의 50개 샘플로 모델별 지연 차이 확인
- strict / repaired 수렴 여부 확인
- 품질 차이가 실제로 남아 있는지 검증
- 운영 관점에서 더 빠른 후보를 고르는 데 집중

즉, Week5는 **운영 비교 리포트**다.

---

## 3. 핵심 결과 비교

### 3.1 비교 축

| 항목 | Week4 리포트 | Week5 리포트 |
|---|---|---|
| 목적 | Week3 -> Week4 전환 효과 설명 | sample50 운영 효율 비교 |
| 모델 수 | 5개 | 4개 |
| 케이스 수 | 100 중심 | 50 |
| 평가 초점 | strict / repaired 차이 | 지연 성능 중심 |
| 추천 기준 | 서비스 안정성과 균형 | 속도와 실용성 |

### 3.2 전체 결론 비교

| 관점 | Week4 결론 | Week5 결론 |
|---|---|---|
| 최상위 모델 | exaone3.5:7.8b-instruct | ax4-light-local:latest |
| 균형형 모델 | gemma3:12b | exaone3.5:7.8b-instruct |
| 속도 우선 모델 | ax4-light-local:latest | ax4-light-local:latest |
| gemma4 계열 | e4b는 중간 후보, 26b는 약점 명확 | 26b만 남았고 품질 차별점은 약함 |

---

## 4. 지표 해석 차이

### 4.1 Week4에서 드러난 핵심

Week4에서는 모델 간 차이가 품질과 지연 모두에서 드러났다.

- exaone3.5:7.8b-instruct: 원본 품질과 지연이 함께 개선된 최상위 후보
- ax4-light-local:latest: 속도는 최고지만 원본 answer가 취약
- gemma3:12b: 균형형이지만 exaone보다 느림
- gemma4:26b: 지연은 괜찮지만 원본 품질이 낮음
- gemma4:e4b: 26b보다 낫지만 속도 비용이 더 큼

즉, Week4는 **품질과 보정 효과가 함께 중요했던 시점**이다.

### 4.2 Week5에서 드러난 핵심

Week5 sample50에서는 네 모델이 모두 strict answer, repaired answer, repaired citation에서 1.0으로 수렴했다.

이 때문에 차이는 사실상 지연으로 모였다.

- ax4-light-local:latest: 13.2170초
- exaone3.5:7.8b-instruct: 16.0846초
- gemma4:26b: 18.3473초
- gemma3:12b: 19.3726초

즉, Week5 sample50은 **서비스 가용성 비교보다 실행 효율 비교**에 가깝다.

---

## 5. 모델별 비교 분석

### 5.1 ax4-light-local:latest

Week4:
- 속도는 가장 빠르지만 strict answer가 0.0이었다.
- repaired 기준으로는 서비스 가능했지만, 원본 품질 한계가 분명했다.

Week5:
- sample50에서는 answer와 citation이 모두 1.0으로 수렴했다.
- 4개 모델 중 가장 빠르다.

해석:
- Week4에서는 보정 의존도가 큰 속도형 모델이었다.
- Week5에서는 그 보정 효과가 유지되면서 실행 효율이 가장 좋은 후보로 보인다.

### 5.2 exaone3.5:7.8b-instruct

Week4:
- 전체 품질과 지연의 균형이 가장 좋았다.
- 기본 운영 모델로 가장 강한 추천을 받았다.

Week5:
- answer와 citation은 완전히 수렴했고, 지연은 ax4 다음으로 빠르다.

해석:
- Week4의 "최상위 균형형"이라는 위치는 유지된다.
- 다만 Week5 sample50에서는 ax4가 품질 격차 없이 더 빠르게 나와, 운영 우선순위가 일부 재배치된다.

### 5.3 gemma3:12b

Week4:
- 균형형 후보로 의미가 있었고, exaone 다음으로 안정적인 선택지였다.

Week5:
- 품질은 충분하지만 속도는 4개 중 가장 느리다.

해석:
- Week4에서는 "안정적 균형형"의 의미가 있었지만,
- Week5 sample50에서는 그 균형이 속도 이점으로 연결되지 않아 우선순위가 내려간다.

### 5.4 gemma4:26b

Week4:
- 26b는 지연은 좋지만 원본 품질이 낮은 편이었다.

Week5:
- sample50에서 품질은 다른 모델과 동일하게 수렴했지만, 지연은 여전히 중간 이하이다.

해석:
- Week4의 평가에서는 원본 품질 한계가 눈에 띄었고,
- Week5에서는 그 차별점이 사라져, 굳이 선택할 이유가 더 약해졌다.

### 5.5 gemma4:e4b

Week4:
- 26b보다 원본 답변은 낫지만, 지연 비용이 더 큰 비교군이었다.

Week5:
- 이번 sample50 비교에는 포함되지 않았다.

해석:
- Week4에서는 "실험군"으로 의미가 있었지만,
- Week5 sample50에서는 비교 대상에서 빠지면서 실제 운영 우선순위 판단에는 직접 반영되지 않는다.

---

## 6. 추천 해석의 변화

### 6.1 Week4 추천

Week4 기준 추천은 다음 구조였다.
- 기본 운영 모델: exaone3.5:7.8b-instruct
- 속도 우선 경로: ax4-light-local:latest
- 균형형 대안: gemma3:12b
- 실험군: gemma4:e4b
- 비권장 기본 후보: gemma4:26b

이 추천은 모델 본체 품질과 보정 효과를 함께 고려한 결과였다.

### 6.2 Week5 추천

Week5 sample50 기준 추천은 다음 구조로 바뀐다.
- 기본 운영 후보: ax4-light-local:latest
- 차선 후보: exaone3.5:7.8b-instruct
- 보조 후보: gemma4:26b
- 후순위 후보: gemma3:12b

이 변화는 품질 차이가 사라진 sample50에서 속도 차이가 결정적이었기 때문이다.

### 6.3 추천 변화의 의미

- Week4는 "무엇이 가장 안정적으로 서비스되느냐"를 봤다.
- Week5는 "같은 품질이라면 무엇이 가장 빨리 서비스되느냐"를 봤다.

따라서 두 리포트는 서로 모순되지 않는다.
오히려 Week5가 Week4보다 더 좁은 실행 조건에서 추천을 미세 조정한 것으로 봐야 한다.

---

## 7. 왜 해석이 달라졌는가

### 7.1 평가 목적의 차이

Week4는 전환 구간이라 파이프라인 개선 효과를 설명해야 했다.
Week5는 이미 정렬된 조건에서 sample50의 실행 효율을 확인하는 단계였다.

### 7.2 대상 모델의 차이

Week4는 5개 모델을 포함했고 gemma4:e4b까지 보였다.
Week5는 4개 모델만 비교했다.

즉, Week5는 더 좁은 집합에서 더 실용적인 선택만 남긴 비교다.

### 7.3 샘플 특성의 차이

Week5 sample50에서는 strict/repaired가 모두 1.0으로 수렴했다.
이 경우 품질 지표가 모델 구분력을 거의 잃고, 지연 지표가 더 강한 선택 기준이 된다.

---

## 8. 운영 관점 결론

| 항목 | Week4 기준 | Week5 sample50 기준 |
|---|---|---|
| 기본 운영 우선순위 | exaone3.5:7.8b-instruct | ax4-light-local:latest |
| 차선 후보 | gemma3:12b | exaone3.5:7.8b-instruct |
| 실험군 | gemma4:e4b | gemma4:26b |
| 판단 기준 | 품질 + 보정 + 지연 | 지연 + 동일 품질 수렴 |

실무적으로는 다음처럼 정리할 수 있다.
- 데모/전환 기준으로는 Week4 결론이 더 보수적이고 안전하다.
- 동일 조건 sample50 효율 기준으로는 Week5 결론이 더 실용적이다.
- 최종 운영안은 "ax4를 기본 데모 경로로 쓰되, exaone을 안정형 백업으로 둔다"가 가장 현실적이다.

---

## 9. 최종 결론

1. Week4 리포트는 서비스 전환과 파이프라인 개선의 효과를 보여주는 보고서다.
2. Week5 sample50 리포트는 이미 정렬된 조건에서 속도 차이를 중심으로 운영 효율을 보는 보고서다.
3. Week4에서는 exaone3.5:7.8b-instruct가 가장 강한 기본 후보였고, Week5 sample50에서는 ax4-light-local:latest가 가장 빠른 운영 후보로 올라섰다.
4. 두 결론은 충돌하지 않는다. Week4는 넓은 전환 문맥, Week5는 좁은 sample50 운영 문맥을 반영하기 때문이다.
5. 따라서 현재 프로젝트는 **Week4 결론을 기본 안정성 기준으로 유지하고, Week5 sample50 결론을 속도 최적화 기준으로 보완**하는 방식이 가장 적합하다.

---

## 10. 관련 파일

### 비교 대상
- [Week4 통합 리포트](../week4/WEEK4_BE3_INTEGRATED_WEEK3_TO_WEEK4_MODEL_REPORT.md)
- [Week5 sample50 4개 모델 리포트](WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md)

### 참고 결과
- [ax4 요약](../../../logs/evaluation/week5/ax4_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_ax4_light.md)
- [exaone 요약](../../../logs/evaluation/week5/exaone_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [gemma3 요약](../../../logs/evaluation/week5/gemma3_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma3_12b.md)
- [gemma4:26b 요약](../../../logs/evaluation/week5/gemma4_26b_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma4_26b.md)
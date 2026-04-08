# Week4 BE3 발표용 1페이지 요약

작성일: 2026-04-08  
주제: Week3 -> Week4 벤치마크/서비스 개선 결과 요약

---

## 1. 한 줄 결론

Week4에서는 BE3 `/qa` 경로와 벤치마크 기준을 통합하면서, 모델 자체 품질과 서비스 가용성을 분리해서 볼 수 있게 되었고, 그 결과 exaone3.5:7.8b-instruct가 현재 프로젝트의 기본 운영 모델로 가장 적합하다는 결론에 도달했다.

---

## 2. Week3 -> Week4에서 한 핵심 작업

- 공통 JSON 파싱/검증 경로 통합
- answer 최소 품질 가드 추가
- citation 자동 교정 및 재시도 정책 도입
- strict / repaired 지표 분리
- 벤치마크와 API 해석 기준 정렬

이 작업들로 인해 단순 모델 점수가 아니라 실제 서비스 가능성을 반영하는 수치로 재측정할 수 있었다.

---

## 3. 핵심 수치 변화

| 모델 | Week3 Stage 1 | Week4 Strict | Week4 Repaired | 해석 |
|---|---:|---:|---:|---|
| exaone3.5:7.8b-instruct | answer 0.30, avg 23.43s, p95 32.11s | answer 0.87, avg 17.14s, p95 18.87s | answer 1.0, citation 1.0 | 가장 큰 개선, 품질과 속도 모두 우수 |
| ax4-light-local:latest | answer 0.0, avg 30.35s, p95 32.74s | answer 0.0, avg 13.07s, p95 14.60s | answer 1.0, citation 1.0 | 속도 최고, 원본 답변은 취약 |
| gemma3:12b | answer 0.31, avg 20.22s, p95 24.48s | answer 0.82, avg 19.63s, p95 20.80s | answer 1.0, citation 1.0 | 가장 안정적인 균형형 |
| gemma4:26b | 비교 대상 없음 | answer 0.15, avg 18.92s, p95 20.38s | answer 1.0, citation 1.0 | 빠르지만 원본 품질이 낮음 |
| gemma4:e4b | 비교 대상 없음 | answer 0.55, avg 21.43s, p95 25.08s | answer 1.0, citation 1.0 | 26b보다 낫지만 지연이 큼 |

---

## 4. 발표 포인트

### 무엇이 좋아졌나
- exaone는 answer 비율이 0.30에서 0.87로 크게 상승했고, 지연도 평균 23.43초에서 17.14초로 감소했다.
- gemma3는 Week4에서 균형형 모델로 안정화되었고, repaired 기준에서는 답변과 citation이 모두 1.0이다.
- ax4는 초저지연 경로로 유용하지만, strict 기준 answer가 0.0이라 원본 품질은 낮다.

### 왜 좋아졌나
- 서비스 경로와 벤치마크 경로를 공통 유틸로 맞췄다.
- 빈 answer를 그대로 허용하지 않고 최소 품질 가드를 넣었다.
- citation이 비거나 틀리면 자동 교정하도록 바꿨다.
- strict와 repaired를 분리해 개선 효과를 명확히 보이게 했다.

---

## 5. 프로젝트에 맞는 모델 추천

### 기본 운영 모델
- exaone3.5:7.8b-instruct
- 이유: strict answer가 가장 높고, 지연도 충분히 빠르며, repaired 기준도 안정적이다.

### 대안 모델
- 균형형: gemma3:12b
- 초저지연: ax4-light-local:latest
- 실험군: gemma4:e4b
- 비권장 기본 후보: gemma4:26b

---

## 6. 현재 문제점과 다음 과제

### 현재 문제점
- 5개 모델 모두 strict citation_match_rate는 0.0이다.
- ax4는 속도는 뛰어나지만 원본 answer가 비어 있는 경우가 많다.
- repaired 기준 의존도가 아직 높다.

### 다음 개선 과제
- citation 필수화 강화
- 빈 answer 제한 정책 고도화
- prompt 강도별 추가 실험
- 장문/복합요청 중심 회귀 테스트 강화
- repaired 의존도를 낮추는 모델 수준 개선

---

## 7. 최종 메시지

Week4의 핵심 성과는 단순한 벤치마크 점수 상승이 아니라, 실제 서비스 기준으로 모델을 다시 정의한 것이다. 현재 프로젝트에서는 exaone3.5:7.8b-instruct를 기본 운영 모델로 두고, gemma3:12b를 균형형 대안, ax4-light-local:latest를 초저지연 대안으로 운용하는 구성이 가장 현실적이다.

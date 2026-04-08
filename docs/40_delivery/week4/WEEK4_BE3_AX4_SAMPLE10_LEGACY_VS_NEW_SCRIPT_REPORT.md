# Week4 BE3 AX4 (10개 샘플) Legacy vs NewScript 비교 리포트

작성일: 2026-04-08  
대상 모델: ax4-light-local:latest  
입력: logs/evaluation/week3/evaluation_set_10.json (10 cases)  
비교 대상:
- Legacy: scripts/Be3_run_week3_model_benchmark.py
- NewScript: scripts/Be3_run_ax4_week4_medel_benchmark.py

---

## 1. 비교 목적

동일 10개 샘플에서 Legacy 스크립트와 AX4 전용 NewScript를 비교해, strict answer 복원 성능과 지연(latency) 변화를 재확인한다.

---

## 2. 핵심 결과 비교

| 지표 | Legacy | NewScript | 변화 |
|---|---:|---:|---|
| parse_success_rate | 1.0 | 1.0 | 동일 |
| answer_non_empty_rate_strict | 0.0 | 1.0 | +1.0p 개선 |
| answer_non_empty_rate_repaired | 1.0 | 1.0 | 동일 |
| citation_match_rate_strict | 0.0 | 0.0 | 동일 |
| citation_match_rate_repaired | 1.0 | 1.0 | 동일 |
| avg_latency_sec | 18.4196 | 14.7234 | -3.6962s 개선 |
| p95_latency_sec | 21.5146 | 16.0282 | -5.4864s 개선 |

해석 요약:
- NewScript는 strict 기준 answer 생성률을 0.0에서 1.0으로 개선했다.
- repaired 기준 가용성(1.0)과 citation 일치율(1.0)은 두 스크립트 모두 동일했다.
- 이번 10개 샘플에서는 NewScript가 평균/상위지연(p95) 모두 더 낮았다.

---

## 3. 결과 해석

이번 실행 기준으로는 NewScript가 다음 두 가지에서 우세하다.

1. strict answer 생성 안정성
- Legacy는 strict answer가 비어 있는 케이스가 존재했고, NewScript는 전 케이스에서 strict answer를 확보했다.

2. 응답 지연
- 평균 지연과 p95 지연 모두 NewScript가 더 낮아, 샘플 10건 범위에서 처리 효율도 개선됐다.

참고:
- `citation_match_rate_strict`는 두 스크립트 모두 0.0이므로, strict citation 품질은 별도 개선 과제로 유지된다.

---

## 4. 결론

- 현재 10개 샘플 재검증에서는 NewScript가 Legacy 대비 핵심 목표( strict answer non-empty )를 달성했다.
- 또한 latency까지 동반 개선되어, AX4 운영 후보로 NewScript를 우선 채택할 근거가 강화됐다.
- 다만 통계 안정성을 위해 100개 케이스 재측정으로 동일 경향 재확인을 권장한다.

---

## 5. 산출물 경로

### Legacy 실행 결과
- logs/evaluation/week4/ax4_ctx1024_LagacyScript_sample10/model_benchmark_candidate_candidate_ax4_light.md
- logs/evaluation/week4/ax4_ctx1024_LagacyScript_sample10/model_benchmark_candidate_candidate_ax4_light.json

### NewScript 실행 결과
- logs/evaluation/week4/ax4_ctx1024_TestScript_sample10/model_benchmark_candidate_candidate_ax4_light.md
- logs/evaluation/week4/ax4_ctx1024_TestScript_sample10/model_benchmark_candidate_candidate_ax4_light.json

### 스크립트
- scripts/Be3_run_week3_model_benchmark.py
- scripts/Be3_run_ax4_week4_medel_benchmark.py

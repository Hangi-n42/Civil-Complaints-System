# Week3 BE3 A.X-4.0-Light A/B 비교 리포트

작성일: 2026-04-03  
대상: `candidate_ax4_light` (`ax4-light-local:latest`)  
케이스 수: 100  
비교 범위: Stage 1 / Stage 2

---

## 1. 비교 목적

Week3 BE3 기준에서 A.X-4.0-Light 모델에 대해 `num_ctx` 변경(1024 -> 2048)이 JSON 파싱 안정성, 답변 생성률, citation 정합성, 응답 지연에 미치는 영향을 확인한다.

---

## 2. 실험 설정

| Stage | 설정 | 비고 |
|---|---|---|
| Stage 1 | `num_ctx=1024`, `num_predict=128` | 기본 컨텍스트 설정 |
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
| Stage 1 (`1024/128`) | 1.0 | 0.0 | 0.0 | 30.3459 | 32.7393 |
| Stage 2 (`2048/128`) | 1.0 | 0.0 | 0.0 | 25.4711 | 32.5377 |

---

## 4. 해석

### Stage 1 (`1024/128`)
- 파싱 안정성은 확보됐다(parse_success_rate = 1.0).
- 답변 생성률이 0.0으로, 평가 케이스 100건 모두에서 응답이 비어있다.
- citation 정합성은 0.0으로 근거 연결 품질이 확보되지 않았다.
- 평균 지연은 30.3459초이다.

### Stage 2 (`2048/128`)
- `num_ctx`를 2048로 확장했지만 파싱률은 동일(1.0)이다.
- 답변 생성률은 여전히 0.0이다(개선 미관측).
- citation 정합성은 여전히 0.0이다.
- 평균 지연은 **25.4711초로 약 4.88초 단축되었다**, 약 16.1% 개선.
- 상위 95 백분위(p95)는 거의 동일하다(32.7393 → 32.5377).

---

## 5. 권장안 판단

### 성능 관점
- **더 빠른 Stage**: Stage 2 (`2048/128`)
- **지연 단축 효과**: 약 16.1% 개선 (30.35초 → 25.47초)

### 품질 관점
- Stage 1/2 모두 answer_non_empty_rate가 0.0으로 기준 미달이다.
- Stage 1/2 모두 citation_match_rate가 0.0으로 근거 정합성이 확보되지 않았다.

### 결론
- **A.X-4.0-Light는 `num_ctx` 확장이 성능 이득을 가져왔다.**
- **현재 A.X-4.0-Light 기준 권장 설정은 Stage 2(`2048/128`)이다.**
- 다만 답변 생성 및 citation 정합성이 0.0으로 현저히 낮아, 추가 프롬프트/규칙 개선이 필수이다.

---

## 6. 모 타 모델과의 비교 맥락

| 모델 | 대표 Stage | parse_success_rate | answer_non_empty_rate | avg_latency_sec |
|---|---|---:|---:|---:|
| A.X-4.0-Light | Stage 2 (`2048/128`) | 1.0 | 0.0 | 25.4711 |
| EXAONE | Stage 3 (`1024/128`) | 1.0 | 0.33 | 15.7420 |
| GEMMA | Stage 1 (`1024/128`) | 1.0 | 0.31 | 20.2235 |
| PHI4 | Stage 1 (`1024/128`) | 1.0 | 0.03 | 22.8132 |

- A.X는 지연이 가장 길지만, `num_ctx` 확장 시 성능 개선 유일 사례다.
- 그러나 answer_non_empty_rate가 0.0으로 응답 품질은 현저히 낮다.

---

## 7. 다음 개선 포인트

1. 답변 생성 규칙 강화
- 프롬프트의 answer 필드 생성 강제화
- 토큰 최소 길이 또는 출력 보장 메커니즘 추가

2. citation 강제 규칙 실험
- citations 최소 1개 이상 필수화
- citation이 비면 제한 응답으로 강제 전환

3. A.X 특화 튜닝
- 장문 컨텍스트(2048+)에 최적화된 프롬프트 재설계
- 응답 양식/샘플 개선

---

## 8. 관련 파일

- [A.X Stage 1 결과](../../../logs/evaluation/week3/ax4_stage1_ctx1024/model_benchmark_candidate_candidate_ax4_light.json)
- [A.X Stage 1 요약](../../../logs/evaluation/week3/ax4_stage1_ctx1024/model_benchmark_candidate_candidate_ax4_light.md)
- [A.X Stage 2 결과](../../../logs/evaluation/week3/ax4_stage2_ctx2048/model_benchmark_candidate_candidate_ax4_light.json)
- [A.X Stage 2 요약](../../../logs/evaluation/week3/ax4_stage2_ctx2048/model_benchmark_candidate_candidate_ax4_light.md)
- [A.X Stage 1 raw responses](../../../logs/evaluation/week3/ax4_stage1_ctx1024/raw_responses.jsonl)
- [A.X Stage 2 raw responses](../../../logs/evaluation/week3/ax4_stage2_ctx2048/raw_responses.jsonl)

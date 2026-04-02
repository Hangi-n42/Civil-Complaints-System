# Week3 BE3 EXAONE A/B 비교 리포트

작성일: 2026-04-02  
대상: `candidate_exaone_3_5_7_8b`  
케이스 수: 100  
비교 범위: Stage 1 / Stage 2 / Stage 3

---

## 1. 비교 목적

Week3 BE3 기준 결과를 바탕으로 `num_predict`와 `num_ctx` 조정이 JSON 파싱 안정성, 답변 생성률, citation 정합성, 응답 지연에 미치는 영향을 확인한다.

---

## 2. 실험 설정

| Stage | 설정 | 비고 |
|---|---|---|
| Stage 1 | `num_ctx=2048`, `num_predict=256` | 기준선 |
| Stage 2 | `num_ctx=2048`, `num_predict=128` | 출력 길이 축소 |
| Stage 3 | `num_ctx=1024`, `num_predict=128` | 컨텍스트 + 출력 길이 축소 |

공통 조건:
- `temperature=0.2`
- `timeout_sec=90`
- `repetitions_per_case=1`
- 입력: `logs/evaluation/week3/evaluation_set_100.json`

---

## 3. 핵심 결과 비교

| Stage | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |
|---|---:|---:|---:|---:|---:|
| Stage 1 | 1.0 | 0.70 | 0.03 | 25.4296 | 29.6410 |
| Stage 2 | 1.0 | 0.28 | 0.00 | 16.2963 | 18.0696 |
| Stage 3 | 1.0 | 0.33 | 0.00 | 15.7420 | 16.6224 |

---

## 4. 해석

### Stage 1
- 파싱은 안정적이지만 답변 품질과 citation 정합성이 취약하다.
- 평균 지연이 25초대로 너무 길다.
- Week3 합격 기준에는 도달하지 못한다.

### Stage 2
- `num_predict` 축소로 지연은 확실히 줄었다.
- 그러나 답변 비어있음 비율이 크게 증가했다.
- citation 정합성은 0.0으로 떨어졌고, 근거 연결 품질은 개선되지 않았다.

### Stage 3
- `num_ctx`까지 줄이면서 지연은 Stage 2보다 조금 더 개선됐다.
- 답변 생성률은 Stage 2보다 약간 회복됐지만 여전히 낮다.
- citation 정합성은 계속 0.0이다.

---

## 5. 권장안 판단

### 성능 관점
- **가장 빠른 Stage**: Stage 3
- **가장 균형적인 Stage**: Stage 3
- **가장 안전한 파싱 기준**: Stage 1, Stage 2, Stage 3 모두 동일하게 1.0

### 품질 관점
- citation 정합성은 세 단계 모두 기준 미달이다.
- Stage 2/3는 지연을 줄였지만, 답변 생성률이 충분하지 않다.

### 결론
- **현재 단계에서는 Stage 3를 임시 추천안으로 둘 수는 있지만, 최종 baseline으로 확정하기는 어렵다.**
- 최종 baseline 후보로 쓰려면 citation 정합성과 answer_non_empty_rate를 별도로 끌어올리는 추가 조정이 필요하다.

---

## 6. 다음 개선 포인트

1. citation 강제 규칙 강화
- citations 최소 1개 이상 필수화
- 근거가 없으면 제한 응답 또는 실패 처리

2. 출력 품질 조정
- 프롬프트를 더 짧고 강하게 고정
- JSON 스키마를 더 엄격하게 명시

3. 추가 A/B 제안
- `num_predict=128` 유지
- `num_ctx=1024` 유지 또는 768 추가 실험
- citation 필수화 전/후 비교

---

## 7. 관련 파일

- [Stage 1 결과](../../../logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [Stage 1 요약](../../../logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md)
- [Stage 2 결과](../../../logs/evaluation/week3/ab_stage2/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [Stage 3 결과](../../../logs/evaluation/week3/ab_stage3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json)
- [튜닝 로그](WEEK3_BE3_TUNING_LOG.md)

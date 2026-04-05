# Week3 BE3 GEMMA A/B 비교 리포트

작성일: 2026-04-02  
대상: `candidate_gemma3_12b` (`gemma3:12b`)  
케이스 수: 100  
비교 범위: Stage 1 / Stage 2

---

## 1. 비교 목적

Week3 BE3 기준에서 GEMMA 모델에 대해 `num_ctx` 변경(1024 -> 2048)이 JSON 파싱 안정성, 답변 생성률, citation 정합성, 응답 지연에 미치는 영향을 확인한다.

---

## 2. 실험 설정

| Stage | 설정 | 비고 |
|---|---|---|
| Stage 1 | `num_ctx=1024`, `num_predict=128` | GEMMA 기준선 |
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
| Stage 1 (`1024/128`) | 1.0 | 0.31 | 0.00 | 20.2235 | 24.4759 |
| Stage 2 (`2048/128`) | 1.0 | 0.27 | 0.00 | 22.6454 | 27.1211 |

---

## 4. 해석

### Stage 1 (`1024/128`)
- 파싱 안정성은 확보됐다.
- 답변 생성률은 0.31로 GEMMA 기준으로는 상대적으로 양호하지만 목표치에는 부족하다.
- citation 정합성은 0.0으로 근거 연결 품질이 확보되지 않았다.

### Stage 2 (`2048/128`)
- `num_ctx`를 2048로 확장했지만 파싱률은 동일(1.0)이다.
- 답변 생성률은 0.31 -> 0.27로 소폭 하락했다.
- citation 정합성은 여전히 0.0이다.
- 지연은 평균/상위구간 모두 증가했다.

---

## 5. 권장안 판단

### 성능 관점
- **더 빠른 Stage**: Stage 1 (`1024/128`)
- **파싱 안정성**: Stage 1/2 모두 동일하게 1.0

### 품질 관점
- Stage 1/2 모두 citation_match_rate가 0.0으로 근거 정합성 기준에 미달한다.
- Stage 2는 품질 개선 없이 지연만 늘어나는 패턴이다.

### 결론
- **GEMMA에서는 `num_ctx`를 2048로 키워도 품질 이득이 없고, 지연만 증가했다.**
- **현재 GEMMA 기준 임시 베이스라인은 Stage 1(`1024/128`) 유지가 타당하다.**
- 다음 단계는 컨텍스트 확대보다 프롬프트/출력 제약/citation 강제 규칙 실험이 우선이다.

---

## 6. 다음 개선 포인트

1. citation 강제 규칙 실험
- citations 최소 1개 이상 필수화
- citation이 비면 제한 응답으로 강제 전환

2. 답변 품질 개선
- answer 필드 생성 규칙을 더 강하게 고정
- 질문 유형별 제한 응답 템플릿 정교화

3. 추가 A/B 제안
- `num_ctx=1024`, `num_predict=128` 고정
- prompt 강도(간결/강제형) 2안 비교
- citation 강제 전/후 비교

---

## 7. 관련 파일

- [Gemma Stage 1 결과](../../../logs/evaluation/week3/gemma_stage1_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.json)
- [Gemma Stage 1 요약](../../../logs/evaluation/week3/gemma_stage1_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md)
- [Gemma Stage 2 결과](../../../logs/evaluation/week3/gemma_stage2_ctx2048/model_benchmark_candidate_candidate_gemma3_12b.json)
- [Gemma Stage 2 요약](../../../logs/evaluation/week3/gemma_stage2_ctx2048/model_benchmark_candidate_candidate_gemma3_12b.md)
- [Gemma Stage 1 raw responses](../../../logs/evaluation/week3/gemma_stage1_ctx1024/raw_responses.jsonl)
- [Gemma Stage 2 raw responses](../../../logs/evaluation/week3/gemma_stage2_ctx2048/raw_responses.jsonl)

# Week3 BE3 설정/성능 튜닝 로그

문서 목적: EXAONE 벤치마크 결과를 기준으로 JSON 파싱 안정성, citation 정합성, 응답 지연을 개선하기 위한 A/B 테스트 기록을 남긴다.

## 1. 기준 결과

- 기준 모델: `candidate_exaone_3_5_7_8b`
- 기준 케이스 수: 100
- 기준 입력 파일: `logs/evaluation/week3/evaluation_set_100.json`
- 기준 벤치마크 결과:
  - `parse_success_rate`: 1.0
  - `answer_non_empty_rate`: 0.7
  - `citation_match_rate`: 0.03
  - `avg_latency_sec`: 25.4296
  - `p95_latency_sec`: 29.641

## 2. 현재 적용된 복구 로직

- 코드블록 제거 후 JSON 후보 추출
- 중괄호 범위 기반 JSON 본문 추출
- 스마트쿼트/후행 콤마 정리
- citations 타입 정규화(`str`/`dict`/`list` 대응)
- 1회 재시도 후 제한 응답 폴백
- 케이스 1건 처리마다 터미널 진행 로그 출력

## 3. A/B 테스트 계획

| 단계 | 목적 | num_ctx | num_predict | 기대 효과 |
|---|---|---:|---:|---|
| Stage 1 | 기준선 | 2048 | 256 | 현재 베이스라인 유지 |
| Stage 2 | 출력 길이 축소 | 2048 | 128 | 응답 길이/지연 감소 |
| Stage 3 | 컨텍스트 축소 | 1024 | 128 | 지연 및 메모리 부담 추가 감소 |

## 4. 실행 기록

| 단계 | 상태 | 결과 파일 | 메모 |
|---|---|---|---|
| Stage 1 | 완료 | `logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json` | 기존 기준 결과 확보 |
| Stage 2 | 완료 | `logs/evaluation/week3/ab_stage2/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json` | `num_predict=128` |
| Stage 3 | 완료 | `logs/evaluation/week3/ab_stage3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json` | `num_ctx=1024`, `num_predict=128` |

### Stage 2 측정 결과

- `parse_success_rate`: 1.0
- `answer_non_empty_rate`: 0.28
- `citation_match_rate`: 0.0
- `avg_latency_sec`: 16.2963
- `p95_latency_sec`: 18.0696

### Stage 2 해석

- Stage 1 대비 JSON 파싱 안정성은 유지됐지만, 답변 비어있음 비율이 크게 증가했다.
- 평균 지연은 25.4296초에서 16.2963초로 감소했지만, Week3 목표 12초에는 아직 못 미친다.
- citation 정합성은 여전히 0.0이라, 구조적 근거 연결 개선이 추가로 필요하다.

### Stage 3 측정 결과

- `parse_success_rate`: 1.0
- `answer_non_empty_rate`: 0.33
- `citation_match_rate`: 0.0
- `avg_latency_sec`: 15.742
- `p95_latency_sec`: 16.6224

### Stage 3 해석

- Stage 2 대비 `num_ctx` 축소로 지연은 소폭 개선됐지만, 여전히 목표 12초보다 느리다.
- 답변 비어있음 비율은 Stage 2(0.28)보다 약간 개선됐지만, 여전히 낮다.
- citation 정합성은 0.0으로 유지되어 근거 연결 개선 없이 baseline 후보로 쓰기 어렵다.

### A/B 결론

- `num_predict=128`은 `num_predict=256` 대비 평균 지연을 줄였다.
- `num_ctx=1024` 추가 축소는 지연을 조금 더 줄였지만, citation 정합성에는 효과가 없었다.
- 현재 병목은 파싱 안정성이 아니라 `answer_non_empty_rate`와 `citation_match_rate`이다.

## 5. 판정 기준

- `parse_success_rate >= 0.9`
- `citation_match_rate >= 0.8`
- `avg_latency_sec <= 12`
- `requires_multi_request=true` 슬라이스의 `answer_non_empty_rate >= 0.9`

## 6. 비고

- Stage 1은 이미 실행된 결과를 기준으로 기록한다.
- Stage 2/Stage 3 결과는 실행 후 본 문서에 갱신한다.

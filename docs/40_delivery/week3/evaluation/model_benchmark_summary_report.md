# [Week 3~4][BE1][Sub] 모델 비교 1차 리포트 (#100)

작성일: 2026-04-05  
상위 이슈: #91

## 1. 목적

후보 모델 성능을 동일 조건에서 비교하고, Week4 추가 검증 대상으로 최종 후보 2개를 선정한다.

## 2. 비교 대상 및 대표 Stage

- `candidate_exaone_3_5_7_8b`: Stage 3 (`num_ctx=1024`, `num_predict=128`)
- `candidate_gemma3_12b`: Stage 1 (`num_ctx=1024`, `num_predict=128`)
- `candidate_phi4_mini`: Stage 1 (`num_ctx=1024`, `num_predict=128`)
- `candidate_ax4_light`: Stage 2 (`num_ctx=2048`, `num_predict=128`)

## 3. 비교 결과 요약

| 모델 | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec |
| --- | ---: | ---: | ---: | ---: |
| EXAONE | 1.0 | 0.33 | 0.00 | 15.7420 |
| GEMMA | 1.0 | 0.31 | 0.00 | 20.2235 |
| PHI4 | 1.0 | 0.03 | 0.00 | 22.8132 |
| A.X-4.0-Light | 1.0 | 0.00 | 0.00 | 25.4711 |

## 4. 최종 후보 2개 선정

1. `candidate_exaone_3_5_7_8b`  
: 가장 낮은 지연과 상대적으로 높은 답변 생성률 균형이 우수함.

2. `candidate_gemma3_12b`  
: 파싱 안정성 유지, 답변 생성률이 두 번째로 높아 2차 검증 가치가 높음.

## 5. 해석 메모

- 본 1차 비교에서 `citation_match_rate`는 전 모델 0.0으로 동일해 변별력이 낮았다.
- 다음 테스트는 citation 강제 규칙/검증기 강화 후 재측정이 필요하다.

## 6. 근거 산출물

- 최종 비교 JSON: [docs/40_devlivery/evaluation/week3/model_benchmark_report_final.json](docs/40_devlivery/evaluation/week3/model_benchmark_report_final.json)
- 요약 보고서: [docs/40_devlivery/evaluation/week3/model_benchmark_summary_report.md](docs/40_devlivery/evaluation/week3/model_benchmark_summary_report.md)

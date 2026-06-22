# rand100 답변 점수 변화 보고서

## 1. 분석 기준

- 최신 벤치마크: `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv`
- 이전 비교 기준: `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619`
- 입력 데이터셋: `VS_지방행정기관/rand_test_100.json`
- 모델: `candidate_exaone_3_5_7_8b` / `exaone3.5:7.8b-instruct`
- 초기 답변 점수: `civil_llm_rubric_initial.score_summary.q0_final` 기준
- 루브릭 평가 후 답변 점수: 최종 채택 답변의 `civil_llm_rubric.score_summary.q0_final` 기준
- ARES 점수: 최종 채택 답변에 대한 integrated LLM judge 진단 점수입니다. ARES는 답변을 다시 생성하지 않고 근거/충실성/질의 대응성을 진단합니다.

주의: 이전 ARES는 `ares_lite_report_mapped.json`, 최신 ARES는 `ares_lite_report_integrated.json` 기준입니다. judge 구현과 매핑이 달라 ARES 수치는 방향성 참고용으로 해석해야 합니다.

## 2. 최신 벤치마크 점수 변화 요약

| 항목 | 값 |
| --- | ---: |
| 입력/평가 case 수 | 100 |
| benchmark ok / failed_fallback | 97 / 3 |
| Prometheus/루브릭 재생성 적용 | 47 |
| 초기 Q0 평균 | 4.74 |
| 루브릭 후 최종 Q0 평균 | 5.13 |
| 평균 Q0 변화량 | 0.38 |
| Q0 개선 / 악화 / 동일 | 39 / 0 / 61 |
| ARES integrated overall 평균 | 3.27 |
| ARES context / faithfulness / relevance 평균 | 2.59 / 2.98 / 4.32 |
| ARES risk high / medium / low | 98 / 2 / 0 |

## 3. 단계별 변화 해석

- 초기 Q0 평균은 **4.74점**, 루브릭 재생성/품질 게이트 후 최종 Q0 평균은 **5.13점**입니다. 평균 변화량은 **+0.38점**으로, 전체 평균 자체는 거의 유지됐습니다.
- case 단위로는 **39건 개선**, **0건 악화**, **61건 동일**입니다. 평균은 비슷하지만 개별 case에서는 재생성이 꽤 흔들립니다.
- 재생성 적용은 **47건**입니다. 이전 98건보다 크게 줄어, 최신 프롬프트/후처리에서는 1차 답변이 루브릭 게이트를 덜 자주 건드립니다.
- ARES integrated judge 기준으로는 faithfulness와 context relevance가 낮아, 답변 문체보다 검색 근거 직접성 및 근거-주장 연결이 핵심 병목으로 보입니다.

## 4. Q0 개선 상위 case

| case_id | 초기 Q0 | 최종 Q0 | ΔQ0 | 재생성 | ARES overall | faith | rel | risk |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 80470 | 3.50 | 6.64 | +3.14 | True | 3.00 | 3.00 | 4.00 | high |
| 80439 | 3.19 | 6.28 | +3.09 | True | 4.00 | 4.00 | 5.00 | high |
| 80412 | 4.00 | 6.66 | +2.66 | True | 5.00 | 5.00 | 6.00 | high |
| 80262 | 3.50 | 5.74 | +2.24 | True | 4.60 | 4.00 | 6.00 | high |
| 800845 | 3.05 | 4.81 | +1.76 | True | 2.30 | 2.00 | 3.00 | high |
| 80292 | 3.50 | 5.00 | +1.50 | True | 6.30 | 6.00 | 7.00 | medium |
| 80194 | 5.00 | 6.37 | +1.37 | True | 3.30 | 3.00 | 5.00 | high |
| 80150 | 3.90 | 5.25 | +1.35 | True | 3.00 | 3.00 | 4.00 | high |
| 80114 | 3.67 | 5.00 | +1.33 | True | 2.30 | 2.00 | 3.00 | high |
| 800833 | 4.41 | 5.63 | +1.22 | True | 3.00 | 3.00 | 4.00 | high |

## 5. Q0 악화 상위 case

| case_id | 초기 Q0 | 최종 Q0 | ΔQ0 | 재생성 | ARES overall | faith | rel | risk |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 80220 | 4.17 | 4.17 | +0.00 | False | 3.00 | 3.00 | 4.00 | high |
| 80331 | 5.29 | 5.29 | +0.00 | False | 3.00 | 3.00 | 4.00 | high |
| 80203 | 4.00 | 4.00 | +0.00 | False | 3.30 | 3.00 | 5.00 | high |
| 80401 | 5.69 | 5.69 | +0.00 | False | 2.90 | 2.00 | 4.00 | high |
| 800841 | 3.50 | 3.50 | +0.00 | False | 2.30 | 2.00 | 3.00 | high |
| 800851 | 5.00 | 5.00 | +0.00 | False | 2.30 | 2.00 | 3.00 | high |
| 80252 | 4.02 | 4.02 | +0.00 | False | 4.00 | 4.00 | 5.00 | high |
| 80138 | 4.95 | 4.95 | +0.00 | False | 3.70 | 4.00 | 5.00 | high |
| 80289 | 3.50 | 3.50 | +0.00 | False | 3.00 | 3.00 | 4.00 | high |
| 80319 | 5.31 | 5.31 | +0.00 | False | 4.00 | 4.00 | 5.00 | high |

## 6. ARES integrated 저점 case

| case_id | 초기 Q0 | 최종 Q0 | ΔQ0 | ARES overall | faith | rel | risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 800841 | 3.50 | 3.50 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80288 | 3.90 | 3.90 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80425 | 3.90 | 3.90 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80286 | 3.90 | 3.90 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 800830 | 3.93 | 3.93 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80358 | 3.97 | 3.97 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80202 | 4.28 | 4.28 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80208 | 4.33 | 4.33 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 80444 | 4.79 | 4.79 | +0.00 | 2.30 | 2.00 | 3.00 | high |
| 800845 | 3.05 | 4.81 | +1.76 | 2.30 | 2.00 | 3.00 | high |

## 7. 이전 벤치마크 대비 변화

| 항목 | 이전 | 최신 | 변화 |
| --- | ---: | ---: | ---: |
| ok / failed_fallback | 98 / 2 | 97 / 3 | 성공 1건 감소, fallback 1건 증가 |
| parse_success_rate | 0.68 | 0.33 | -0.35 |
| postprocess_success_rate | 0.98 | 0.97 | -0.01 |
| citation_match_rate | 1.0 | 0.9897 | -0.0103 |
| Civil Rubric Q0 avg | 5.1225 | 5.1268 | 0.0043 |
| Q0 < 6.0 | 81 | 75 | -6 |
| rubric revision applied | 98 | 47 | -51 |
| avg_latency_sec | 97.3529 | 114.2152 | 16.8623 |
| p95_latency_sec | 129.8022 | 154.2049 | 24.4027 |
| format: review phrase | 100 | 0 | -100 |
| format: 끝. | 100 | 0 | -100 |
| format: 감사합니다 종료 | 0 | 100 | 100 |
| ARES overall avg | 3.07 | 3.27 | 0.2 |
| ARES context avg | 3.16 | 2.59 | -0.57 |
| ARES faithfulness avg | 1.31 | 2.98 | 1.67 |
| ARES relevance avg | 5.3 | 4.32 | -0.98 |
| ARES unsupported_claims | 412 | 204 | -208 |
| ARES missing_segments | 41 | 270 | 229 |

## 8. 이전 대비 추가 해석

- **명확히 좋아진 부분**: 답변 포맷입니다. 이전에는 `검토 의견은 다음과 같습니다`와 `끝.`이 각각 100건 남았지만, 최신은 둘 다 0건입니다. 최신 100건은 모두 `감사합니다.`로 종료합니다.
- **근거/인용 계열도 개선**됐습니다. Civil LLM-Rubric 기준 Q3, Q4, Q5 평균이 모두 상승했고, Q3/Q4/Q5 low item도 줄었습니다.
- **재생성 의존도는 크게 줄었습니다.** 이전에는 98건이 재생성 적용됐지만 최신은 47건입니다. 이는 1차 생성 또는 후처리된 답변이 루브릭 게이트를 더 덜 건드린다는 뜻입니다.
- **전체 Q0 평균은 사실상 정체**입니다. Q0 평균은 5.1225에서 5.1268로 0.0043점만 올랐습니다. 즉 포맷과 citation support는 좋아졌지만, 최종 사용자 만족도 관점의 큰 품질 상승까지는 아직 이어지지 않았습니다.
- **스키마 안정성은 악화**됐습니다. raw parse success가 0.68에서 0.33으로 떨어졌습니다. 후처리로 0.97까지 복구되지만, 모델 원응답 단계의 JSON 준수는 다시 손봐야 합니다.
- **속도는 나빠졌습니다.** 평균 latency가 약 16.86초, p95가 약 24.40초 증가했습니다. 루브릭 재생성은 줄었는데도 느려졌으므로 검색/법령 grounding/LLM 호출 길이/후처리 경로를 따로 분해해야 합니다.
- **ARES는 해석 주의가 필요합니다.** 최신 ARES integrated judge는 faithfulness 개선과 unsupported claims 감소를 보여주지만, missing_segments를 훨씬 많이 잡습니다. 이전 ARES mapped와 완전히 같은 judge가 아니므로 절대 비교보다는 위험 신호의 방향성으로 보는 편이 안전합니다.

## 9. 결론

최신 벤치마크는 회신 형식, 종결 문구, citation support, unsupported claim 감소 측면에서 이전보다 좋아졌습니다. 반면 Q0 평균은 거의 그대로이고, raw JSON 스키마 안정성과 속도는 악화됐습니다. 다음 개선 우선순위는 `force_json`/스키마 지시 강화, 검색 근거 직접성 개선, ARES high-risk 기준 보정, latency 분해 측정입니다.

## 10. 관련 산출물

- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/civil_llm_rubric_scores.jsonl`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/ares_lite_report_integrated.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/rand100_shellfix_rubric_ares_analysis.md`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/answer_score_transition_report.md`

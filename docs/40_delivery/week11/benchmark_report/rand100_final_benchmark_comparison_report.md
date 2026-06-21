# Rand100 벤치마크 최종 비교 리포트

## 1. 비교 대상

이 문서는 Week11 rand100 direct 벤치마크 2회를 비교한 최종 요약 리포트이다.

| 구분 | 경로 | 특징 |
| --- | --- | --- |
| 1차 벤치마크 | `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619` | 새 Civil LLM-Rubric v2 적용, ARES mapped 평가 및 후속 분석 수행 |
| 2차 벤치마크 | `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv` | 회신 문구 수정 반영, `검토 의견은 다음과 같습니다`/`끝.` 제거, ARES integrated LLM judge 평가 수행 |

공통 조건:

- 입력 데이터셋: `VS_지방행정기관/rand_test_100.json`
- 실행 스크립트: `scripts/Be3_run_week6_model_benchmark.py`
- 설정 파일: `configs/week6_Be3_model_benchmark.yaml`
- 실행 모드: `direct`
- 모델: `candidate_exaone_3_5_7_8b` / `exaone3.5:7.8b-instruct`

주의:

- Civil LLM-Rubric 결과는 두 벤치마크 모두 같은 런타임 루브릭 산출물 기준으로 비교 가능하다.
- ARES는 1차가 `ares_lite_report_mapped.json`, 2차가 `ares_lite_report_integrated.json` 기준이다. judge 방식이 달라 절대 점수 비교보다 방향성 비교로 해석해야 한다.

## 2. 전체 지표 비교

| 지표 | 1차 | 2차 | 변화 | 해석 |
| --- | ---: | ---: | ---: | --- |
| 전체 case | 100 | 100 | 0 | 동일 |
| ok / failed_fallback | 98 / 2 | 97 / 3 | ok -1 | 2차에서 근거 0개 fallback이 1건 증가 |
| parse_success_rate | 0.68 | 0.33 | -0.35 | 2차 원응답 JSON/schema 안정성 악화 |
| postprocess_success_rate | 0.98 | 0.97 | -0.01 | 후처리 복구율은 거의 동일 |
| citation_match_rate | 1.0000 | 0.9897 | -0.0103 | 여전히 높지만 2차에서 소폭 하락 |
| Civil LLM-Rubric Q0 평균 | 5.1225 | 5.1268 | +0.0043 | 전체 만족도 평균은 사실상 정체 |
| Q0 < 6.0 | 81건 | 75건 | -6건 | 저점 답변은 일부 감소 |
| 루브릭 재생성 적용 | 98건 | 47건 | -51건 | 2차는 재생성 의존도가 크게 감소 |
| 평균 latency | 97.3529초 | 114.2152초 | +16.8623초 | 2차가 더 느림 |
| p95 latency | 129.8022초 | 154.2049초 | +24.4027초 | 꼬리 지연도 악화 |

## 3. 답변 형식 비교

| 항목 | 1차 | 2차 | 변화 |
| --- | ---: | ---: | ---: |
| `검토 의견은 다음과 같습니다` 포함 | 100건 | 0건 | -100건 |
| `끝.` 또는 `끝` 종결 | 100건 | 0건 | -100건 |
| `감사합니다.` 종료 | 0건 | 100건 | +100건 |
| empty answer | 0건 | 0건 | 동일 |
| 평균 답변 길이 | 674.6자 | 649.0자 | -25.6자 |

2차 벤치마크에서 회신 형식은 명확히 개선됐다. 사용자 요청대로 3문단의 고정 문구와 4문단의 `끝.` 종결이 제거되었고, 모든 답변이 `감사합니다.`로 마무리된다.

다만 평균 답변 길이가 다소 줄어들었으므로, 짧아진 문장이 실제 처리 방향을 충분히 담는지는 별도 수동 검토가 필요하다.

## 4. Civil LLM-Rubric 세부 비교

| Q | 1차 평균 0~10 | 2차 평균 0~10 | 변화 | 해석 |
| --- | ---: | ---: | ---: | --- |
| Q0 전체 회신 품질 | 5.2633 | 5.2588 | -0.0045 | 실질 정체 |
| Q1 자연스러움/공공문체 | 7.8006 | 7.7065 | -0.0941 | 고정 문구 제거 영향으로 소폭 하락 |
| Q2 근거 충분성 | 5.8222 | 5.7821 | -0.0401 | 거의 동일 |
| Q3 주장 인용 포함성 | 3.7143 | 4.1986 | +0.4843 | 개선 |
| Q4 인용 근거 정확성 | 2.4980 | 3.6662 | +1.1682 | 가장 크게 개선 |
| Q5 최적 근거 선택성 | 4.0780 | 4.5591 | +0.4811 | 개선 |
| Q6 중복/불필요 요소 없음 | 8.7596 | 8.6771 | -0.0825 | 소폭 하락 |
| Q7 간결성 | 7.4389 | 7.1575 | -0.2814 | 소폭 하락 |

핵심 변화:

- Q3, Q4, Q5가 모두 올랐다. 특히 Q4는 +1.1682점으로, citation과 답변 주장 연결 품질이 2차에서 가장 크게 좋아졌다.
- Q0 평균은 거의 변하지 않았다. 인용 품질 개선이 전체 만족도 상승으로 크게 이어지지는 않았다.
- Q1, Q6, Q7은 소폭 하락했다. 고정 문구 제거와 답변 구조 변화가 자연스러움/간결성 평가에 약간 영향을 준 것으로 보인다.

## 5. Low Item 변화

| low item | 1차 | 2차 | 변화 |
| --- | ---: | ---: | ---: |
| Q3 | 95건 | 85건 | -10건 |
| Q4 | 92건 | 74건 | -18건 |
| Q0 | 86건 | 80건 | -6건 |
| Q5 | 78건 | 62건 | -16건 |
| Q7 | 9건 | 15건 | +6건 |
| Q1 | 1건 | 3건 | +2건 |
| Q2 | 2건 | 3건 | +1건 |
| Q6 | 0건 | 1건 | +1건 |

2차에서는 인용 관련 low item이 확실히 줄었다. 반면 Q7 low item이 늘어, 일부 답변은 형식 수정 이후에도 간결성 또는 답변 효율성 측면에서 더 엄격하게 잡힌다.

## 6. 점수 변화 흐름

| 항목 | 1차 | 2차 |
| --- | ---: | ---: |
| 초기 Q0 평균 | 4.96 | 4.74 |
| 루브릭 후 최종 Q0 평균 | 5.12 | 5.13 |
| 평균 Q0 변화량 | +0.17 | +0.38 |
| Q0 개선 / 악화 / 동일 | 49 / 35 / 16 | 39 / 0 / 61 |
| 재생성 적용 | 98건 | 47건 |

2차는 초기 Q0가 더 낮게 시작했지만, 재생성/품질 게이트 후 최종 Q0는 1차와 거의 같은 수준까지 올라왔다. 특히 2차에서는 Q0가 악화된 case가 0건으로 집계된다.

다만 개선 case 수는 49건에서 39건으로 줄었다. 이는 2차에서 재생성 적용 자체가 47건으로 줄었기 때문이다. 즉 2차는 “많이 고쳐서 크게 올리는 방식”보다 “덜 고치고, 악화는 막는 방식”에 가깝다.

## 7. ARES 비교

| 지표 | 1차 ARES mapped | 2차 ARES integrated | 변화 |
| --- | ---: | ---: | ---: |
| overall 평균 | 3.07 | 3.27 | +0.20 |
| context relevance 평균 | 3.16 | 2.59 | -0.57 |
| answer faithfulness 평균 | 1.31 | 2.98 | +1.67 |
| answer relevance 평균 | 5.30 | 4.32 | -0.98 |
| risk high | 99건 | 98건 | -1건 |
| risk medium | 1건 | 2건 | +1건 |
| unsupported_claims | 412건 | 204건 | -208건 |
| missing_segments | 41건 | 270건 | +229건 |

해석:

- faithfulness와 unsupported claims는 2차에서 좋아졌다. 답변이 근거 없는 확정 표현을 덜 만들거나, ARES integrated judge가 그런 부분을 덜 많이 잡은 것으로 볼 수 있다.
- context relevance와 answer relevance는 2차에서 낮다. 이는 검색 근거가 현재 민원과 직접 대응하지 않거나, 통합 judge가 missing segment를 더 엄격하게 잡는 영향일 수 있다.
- ARES 방식이 1차와 2차에서 다르므로, ARES 수치는 “정확한 동일 조건 성능 비교”보다는 위험 신호로 봐야 한다.

## 8. 2차 벤치마크에서 좋아진 점

1. 회신 형식 안정화

`검토 의견은 다음과 같습니다`와 `끝.`이 완전히 제거됐다. 100건 모두 `감사합니다.`로 종료되어 사용자 요구 형식에 맞게 정리됐다.

2. citation 관련 품질 개선

Q3, Q4, Q5가 모두 상승했고, Q3/Q4/Q5 low item도 줄었다. 특히 Q4 개선 폭이 커서 답변 주장과 인용 근거의 연결이 이전보다 나아졌다.

3. 재생성 의존도 감소

루브릭 재생성 적용이 98건에서 47건으로 줄었다. 이는 1차 생성 또는 후처리 답변이 루브릭 게이트를 덜 자주 건드린다는 의미다.

4. Q0 저점 case 감소

Q0 < 6.0이 81건에서 75건으로 줄었다. 평균 Q0는 거의 그대로지만, 저점 분포는 약간 완화됐다.

5. unsupported claims 감소

ARES 기준 unsupported claims가 412건에서 204건으로 줄었다. judge 방식 차이를 감안하더라도 근거 없는 주장 위험은 완화된 방향으로 보인다.

## 9. 2차 벤치마크에서 나빠진 점

1. raw JSON/schema 안정성 악화

parse_success_rate가 0.68에서 0.33으로 크게 하락했다. 후처리로 대부분 복구되지만, 모델 원응답의 JSON 준수는 현재 중요한 취약점이다.

2. 실행 시간 증가

평균 latency가 약 16.86초, p95 latency가 약 24.40초 증가했다. 재생성 적용은 줄었는데도 느려졌으므로, 검색/법령 grounding/후처리/LLM 호출 길이 중 어느 단계에서 시간이 늘었는지 분해 측정이 필요하다.

3. ARES missing segment 증가

missing_segments가 41건에서 270건으로 증가했다. integrated judge가 더 엄격해진 영향일 수 있지만, 복합 민원 segment 대응이 여전히 약하다는 신호일 수도 있다.

4. 전체 Q0 평균 정체

Q0 평균은 5.1225에서 5.1268로 거의 변하지 않았다. 포맷과 citation 품질은 나아졌지만, 최종 사용자 만족도 수준의 큰 개선까지는 이어지지 않았다.

5. fallback 증가

failed_fallback이 2건에서 3건으로 늘었다. grounding filter 후 근거 0개가 되는 케이스를 별도 분석해야 한다.

## 10. 종합 판단

2차 벤치마크는 “회신 형식”과 “인용 근거 연결” 면에서 분명히 개선됐다. 사용자가 지적했던 `검토 의견은 다음과 같습니다`와 `끝.` 문제는 해결됐고, citation support 계열 점수도 상승했다.

그러나 전체 품질의 핵심 지표인 Q0 평균은 거의 그대로다. 즉 현재 개선은 “표면 형식과 인용 안정성”에는 효과가 있었지만, 답변의 실질적인 민원 대응력, 검색 근거 직접성, 복합 요청 반영률까지 크게 끌어올리지는 못했다.

따라서 다음 개선은 프롬프트 문구 조정보다 아래 항목에 집중하는 편이 좋다.

1. raw JSON/schema 안정성 회복
2. retrieval context와 현재 민원 간 직접성 개선
3. 복합 민원 segment별 답변 누락 방지
4. citation이 실제 주장과 맞는지 사후 검증 강화
5. latency 단계별 측정 및 병목 제거

## 11. 다음 개선 우선순위

| 우선순위 | 과제 | 이유 |
| --- | --- | --- |
| P0 | raw schema 안정성 회복 | parse_success_rate가 0.33까지 하락 |
| P0 | 근거 0개 fallback 3건 원인 분석 | 평가 가능한 답변 자체가 생성되지 않는 케이스 |
| P1 | 검색 근거 직접성 개선 | ARES context relevance가 2.59로 낮음 |
| P1 | 복합 민원 segment coverage 강화 | ARES missing_segments 급증 |
| P1 | citation verifier 강화 | Q4는 개선됐지만 여전히 3.6662로 낮음 |
| P2 | latency 분해 측정 | 평균/p95 모두 악화 |
| P2 | ARES integrated judge 캘리브레이션 | high risk가 98건으로 과민 가능성 |

## 12. 관련 산출물

1차 벤치마크:

- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/civil_llm_rubric_scores.jsonl`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/ares_lite_report_mapped.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/answer_score_transition_report.md`

2차 벤치마크:

- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/civil_llm_rubric_scores.jsonl`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/ares_lite_report_integrated.json`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/rand100_shellfix_rubric_ares_analysis.md`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_shellfix_20260621_venv/answer_score_transition_report.md`

# Issue #387 LLM-Rubric 완료 검토 보고서

## 1. 검토 범위

이 문서는 GitHub issue #387, `[BE3][Week11] LLM-Rubric 0~10 엄격화 및 생성 안전성·Grounding 평가 고도화`의 구현 완료 여부와 근거 산출물을 정리한다.

이번 이슈는 답변 생성 품질 자체를 모두 해결하는 작업이 아니라, 생성 답변을 더 엄격하고 재현 가능한 방식으로 평가하는 LLM-Rubric 프레임워크를 고도화하는 작업으로 본다. 따라서 아래 항목이 완료되면 #387의 평가 프레임워크 범위는 완료로 판단한다.

- Q0~Q8 평가 점수를 0.0~10.0 척도로 세분화했다.
- 기본 평가 범위를 `generated_body`로 설정하여, 고정 회신 문단인 1, 2, 4번 문단이 본문 품질 점수를 과대평가하지 않도록 했다.
- `data/processed/processed_consulting_data.json`의 `consultant_answer`를 모범 답안 기준선으로 사용했다.
- 케이스별로 reference alignment, strict/repaired citation 구분, semantic risk flag, reply shell 진단 정보를 기록한다.
- 최신 Week11 EXAONE rand50 safetyfix 산출물을 엄격화된 루브릭으로 평가했다.

루브릭은 생성 품질 실패를 숨기지 않는다. 빈 답변, 결론 반전, citation 부족, reference alignment 부족은 낮은 Q0 점수와 원인 플래그로 드러나며, 이러한 잔여 문제는 #393 같은 후속 생성·검색 품질 개선 이슈에서 처리한다.

## 2. 근거 산출물 경로

- 벤치마크 답변:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/parsed_answers.jsonl`
- 벤치마크 raw 응답:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/raw_responses.jsonl`
- 벤치마크 모델 리포트:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md`
- 루브릭 요약:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/llm_rubric_exaone_rand50_safetyfix_20260612_v1/rubric_summary.md`
- 루브릭 JSON 리포트:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/llm_rubric_exaone_rand50_safetyfix_20260612_v1/rubric_report.json`
- 케이스별 루브릭 점수:
  `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_safetyfix_20260612/llm_rubric_exaone_rand50_safetyfix_20260612_v1/rubric_scores.jsonl`
- 루브릭 구현 파일:
  `scripts/evaluate_llm_rubric_civil_replies.py`

## 3. 최신 평가 스냅샷

평가 대상은 다음과 같다.

- 모델: EXAONE
- 샘플: `rand_test_50`
- 평가 건수: 50건
- paired reference: 50건
- 평가 범위: `generated_body`
- 평가 방식: `llm_rubric_proxy_civil_replies_v3_generated_body`
- 점수 척도: 0.0~10.0

평균 점수는 다음과 같다.

| 문항 | 점수 / 10 |
| --- | ---: |
| Q0 | 5.66 |
| Q1 | 9.24 |
| Q2 | 7.482 |
| Q3 | 8.352 |
| Q4 | 6.72 |
| Q5 | 6.858 |
| Q6 | 9.57 |
| Q7 | 7.648 |
| Q8 | 6.016 |

Q0 분포는 다음과 같다.

| 구간 | 건수 |
| --- | ---: |
| 0.0~1.9 | 2 |
| 2.0~3.9 | 2 |
| 4.0~5.9 | 35 |
| 6.0~7.9 | 4 |
| 8.0~10.0 | 7 |

회신 형식 진단 결과는 다음과 같다.

| 진단 항목 | 값 |
| --- | ---: |
| 1~4번 문단 모두 존재 비율 | 0.96 |
| 종결문 1회 사용 비율 | 0.96 |

1~4번 문단 형식 실패 2건은 정상 답변의 형식 오류라기보다 empty answer 실패 케이스로 분류된다.

## 4. 저점 Q0 사례 분류

| row | case_id | Q0 | 원인 | 분류 |
| ---: | --- | ---: | --- | --- |
| 10 | 80286 | 0.0 | empty answer, no citations, zero reference alignment | retrieval/generation failure |
| 28 | 800808 | 3.5 | `disposition_reversal`, low reference alignment | semantic safety failure |
| 29 | 80189 | 0.0 | empty answer, no citations, zero reference alignment | retrieval/generation failure |
| 47 | 80245 | 3.5 | `disposition_reversal`, low reference alignment | semantic safety failure |

루브릭은 위 사례들이 높은 Q0 점수를 받지 않도록 정상적으로 제한한다.

- empty answer는 Q0 0.0으로 제한된다.
- 실제 처리 결론을 반대로 뒤집는 `disposition_reversal`은 Q0 3.5로 제한된다.
- citation 누락과 reference alignment 부족은 별도 이유로 기록된다.
- 고정 회신 형식 준수 여부는 별도 진단값으로 기록되며, generated body 품질 점수를 부풀리지 않는다.

## 5. 수용 기준 검토

| #387 수용 기준 | 상태 | 근거 |
| --- | --- | --- |
| Q0 0.0~3.9 사례를 분류하고 재현 가능하게 기록 | 완료 | 위 4개 저점 Q0 사례와 `rubric_scores.jsonl`의 cap reason으로 확인 |
| 1~4번 문단 및 단일 종결문 진단 제공 | 완료 | `reply_shell_diagnostics`에서 0.96 / 0.96 기록 |
| strict citation과 repaired citation 실패 구분 | 완료 | Q3/Q4 reason에서 strict/repaired citation 경로를 분리 기록 |
| Q4와 Q8을 주요 개선 대상으로 드러냄 | 완료 | 최신 요약에서 Q4=6.72, Q8=6.016으로 개선 필요 지표가 확인됨 |
| semantic safety cap을 적용하되 실패를 숨기지 않음 | 완료 | `disposition_reversal` 2건이 Q0=3.5로 제한됨 |
| Week11 산출물과 평가 산출물 기록 | 완료 | 2장 근거 산출물 경로에 기록 |

## 6. 잔여 후속 과제

다음 항목은 루브릭 프레임워크의 완료를 막는 요소가 아니라, 생성·검색 품질 개선을 위한 후속 과제다.

- case_id `80286`, `80189`의 empty answer를 줄이기 위해 retrieval fallback 또는 failure handling을 개선한다.
- case_id `800808`, `80245`의 `disposition_reversal`을 줄인다.
- Q4 개선을 위해 identity-only citation matching에서 snippet-supported citation evidence로 확장한다.
- Q8 개선을 위해 3번 생성 본문이 구체적인 제약, 담당 주체, 행정 판단 결론을 더 잘 보존하도록 한다.

## 7. 완료 판단

#387은 LLM-Rubric 평가 프레임워크 고도화 범위에서 완료로 판단한다. 평가기는 빈 답변, 결론 반전, citation 불일치, reference alignment 부족을 높은 점수로 통과시키지 않고, 케이스별 원인과 잔여 리스크를 산출물에 남긴다.

다만 생성 품질 자체의 잔여 문제는 별도 후속 이슈에서 추적한다. 특히 #393은 본 문서에서 식별된 저점 사례를 기반으로 Q0 0점 제거, `disposition_reversal` 감소, Q4/Q8 개선을 다룬 후속 작업이다.

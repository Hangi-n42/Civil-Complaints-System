# LLM-Rubric Strict Evaluation Summary

## 평가 조건

- method: `llm_rubric_proxy_civil_replies_v2_strict`
- 평가 건수: 50건
- 점수 범위: 0.0~10.0
- 모범 답안: `data/processed/processed_consulting_data.json`의 `consultant_answer` 9,130건
- 1:1 모범 답안 연결: 50/50건
- 평가 대상: `logs/evaluation/week11/be3_model_benchmark_exaone_rand50_direct_20260611/parsed_answers.jsonl`

## 평균 점수

| 항목 | 점수 / 10 |
| --- | ---: |
| Q0 종합 만족도 | 6.476 |
| Q1 회신 품질 | 8.890 |
| Q2 근거 충분성 | 8.000 |
| Q3 인용 포함 | 8.990 |
| Q4 인용 정확성 | 9.300 |
| Q5 최적 출처성 | 7.384 |
| Q6 중복 없음 | 7.490 |
| Q7 길이·밀도 | 8.644 |
| Q8 업무 완결성 | 7.172 |

## Q0 분포

| 점수 구간 | 건수 |
| --- | ---: |
| 0.0~1.9 | 0 |
| 2.0~3.9 | 0 |
| 4.0~5.9 | 31 |
| 6.0~7.9 | 3 |
| 8.0~10.0 | 16 |

이전 1~4점 평가와 달리, 일반적인 회신 형식만 맞춘 답변에는 높은 Q0를 부여하지 않는다. 낮은 모범 답안 정렬도, strict citation 부재, 템플릿 남용, 구조 문자열 및 디버그 정보 노출은 종합 점수 상한으로 반영한다.

## 상세 산출물

- `logs/evaluation/week11/llm_rubric_proxy_exaone_rand50_direct_20260611_v3_strict/rubric_scores.jsonl`
- `logs/evaluation/week11/llm_rubric_proxy_exaone_rand50_direct_20260611_v3_strict/rubric_report.json`
- `logs/evaluation/week11/llm_rubric_proxy_exaone_rand50_direct_20260611_v3_strict/rubric_summary.md`

평가 기준과 실행 방법은 `docs/30_manuals/llm_rubric_civil_reply_evaluation.md`를 따른다.

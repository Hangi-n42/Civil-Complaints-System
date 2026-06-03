# LLM-Rubric 기반 민원 회신 평가

## 목적

`parsed_answers.jsonl`에 저장된 생성 답변을 민원 회신 품질 관점에서 평가한다.

본 구현은 LLM-Rubric 논문의 핵심 아이디어인 다차원 루브릭 평가를 가져온다. 단, 논문처럼 사람 평가 데이터로 calibration network를 학습하지 않고, 현재 프로젝트에서 바로 실행 가능한 deterministic proxy 점수로 구현한다.

## 루브릭 매핑

| ID | 평가 항목 | 민원 회신 적용 |
| --- | --- | --- |
| Q0 | 종합 만족도 | 민원인이 회신을 읽고 전반적으로 만족할 가능성 |
| Q1 | 자연스러움/어조 | 공공기관 회신 문체, 번호 단락, 정중한 표현 |
| Q2 | 근거 충분성 | 검색 근거로 민원 해결 방향을 설명할 수 있는 정도 |
| Q3 | 인용 포함 | 주요 주장에 `[[출처 n]]` 토큰이 포함되는 정도 |
| Q4 | 인용 정확성 | citation match rate 기반 근거 매칭 정확도 |
| Q5 | 최적 출처성 | strict/repaired citation 지표 기반 유효 근거 우선 사용 |
| Q6 | 중복 없음 | 반복, 과잉 사양, 디버그 문자열 없음 |
| Q7 | 간결성 | 민원 회신으로 적절한 길이와 문장 수 |
| Q8 | 효율성 | 민원 요지, 검토 의견, 후속 문의 안내가 한 번에 정리되는 정도 |

## 실행 예시

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_llm_rubric_civil_replies.py `
  --answers logs\evaluation\week6\be3_model_benchmark_exaone_seongnam10_strict_citation_v9\parsed_answers.jsonl `
  --cases VS_지방행정기관\성남시_test_10.json `
  --output-dir logs\evaluation\week6\llm_rubric_proxy_exaone_seongnam10_v1
```

## 산출물

- `rubric_scores.jsonl`: 케이스별 Q0~Q8 점수와 사유
- `rubric_report.json`: 전체 평균, Q0 분포, 카테고리별 요약
- `rubric_summary.md`: 사람이 읽기 쉬운 요약표

## 해석 방법

- 점수 범위는 1~4이며 높을수록 좋다.
- Q0는 Q1~Q8의 가중 평균 기반 proxy 점수다.
- Q2~Q5는 citations 관련 지표를 강하게 반영한다.
- Q6~Q8은 FActScore류 사실성 지표가 놓치기 쉬운 반복, 장황함, 회신 흐름 문제를 잡기 위한 항목이다.

## 주의

- 이 스크립트는 논문의 학습형 calibration network를 구현하지 않는다.
- 사람 평가 데이터가 쌓이면 `rubric_scores.jsonl`을 feature로 사용해 Q0 calibration 모델을 별도로 학습할 수 있다.
- `parsed_answer_repaired`를 기본 평가 대상으로 사용한다. strict 원문만 평가하려면 `--answer-field parsed_answer_strict`를 지정한다.

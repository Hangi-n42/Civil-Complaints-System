# LLM-Rubric 기반 민원 회신 평가

## 목적

`parsed_answers.jsonl`의 생성 답변을 Q0~Q8 다차원 기준으로 평가한다. 점수 범위는 기존 1~4점에서 **0.0~10.0점**으로 세분화했으며, 단순 형식 준수만으로 고득점하지 않도록 실제 민원 회신을 기준으로 엄격하게 판정한다.

본 구현은 LLM-Rubric 논문의 평가 관점을 사용한 deterministic proxy다. 논문의 학습형 calibration network를 재현한 것은 아니며, 프로젝트 데이터에 맞춘 규칙 기반 진단 도구다.

## 모범 답안 기준

기본 모범 답안은 `data/processed/processed_consulting_data.json`의 비어 있지 않은 `consultant_answer`다.

- 전체 모범 답안의 길이, 문장 수, 문단 수, 회신 표현 분포를 계산해 Q1·Q7의 기준으로 사용한다.
- 생성 결과의 `case_id`와 모범 데이터의 `source_id`가 같으면 해당 `consultant_answer`를 1:1 참조 답안으로 사용한다.
- 1:1 참조가 있는 경우 핵심 내용 정렬도, 법령·부서·일정·수치와 같은 참조 앵커 포함 정도를 Q2·Q5·Q8에 반영한다.
- 실제 회신과 문구가 완전히 같아야 하는 것은 아니다. 다만 민원과 무관한 일반론만 생성하면 참조 정렬도가 낮아져 종합 점수 상한이 적용된다.

현재 데이터 프로파일 기준 비어 있지 않은 `consultant_answer`는 9,130건이다. 데이터 파일이 갱신되면 실행 시 분포를 다시 계산하므로 고정 숫자에 의존하지 않는다.

## 루브릭 매핑

| ID | 평가 항목 | 엄격 채점 기준 |
| --- | --- | --- |
| Q0 | 종합 만족도 | Q1~Q8 가중 평균에 치명적 품질 문제 상한을 적용 |
| Q1 | 회신 품질 | 공공기관 문체, 구조, 마무리, 템플릿·디버그 노출 여부 |
| Q2 | 근거 충분성 | strict citation, 구체 정보, 참조 답안 정렬도 |
| Q3 | 인용 포함 | 답변 본문 토큰이 아닌 구조화 `citations` 생성 수와 매칭률 |
| Q4 | 인용 정확성 | 모델 원출력 strict citation match rate를 우선 평가 |
| Q5 | 최적 출처성 | strict 근거 선택과 참조 답안 핵심·앵커 정렬 |
| Q6 | 중복 없음 | 반복, 일반 템플릿 남용, 구조 문자열, 디버그 정보 제거 |
| Q7 | 길이·밀도 | 전체 모범 답안 분포와 1:1 참조 답안 길이 대비 적절성 |
| Q8 | 업무 완결성 | 민원 요지, 검토 판단, 구체 조치·제약, 후속 안내 |

## 점수 해석

| 점수 | 해석 |
| ---: | --- |
| 0.0~1.9 | 실패 또는 평가 불가능에 가까움 |
| 2.0~3.9 | 주요 회신 요건이 다수 부족함 |
| 4.0~5.9 | 형식은 있으나 근거·구체성·정렬도가 부족함 |
| 6.0~7.9 | 실사용 가능한 수준이지만 개선 항목이 남음 |
| 8.0~10.0 | 모범 회신에 가까운 근거성·구체성·완결성을 갖춤 |

Q0는 가중 평균만 사용하지 않고 다음 상한을 적용한다.

- 답변 없음: 0점
- 검색 메타데이터 노출: 최대 3점
- JSON/list 등 구조 문자열 노출 또는 citation 없음: 최대 4점
- paired reference와 정렬이 전혀 없음: 최대 4.5점
- 법령 grounding 오류 또는 참조 정렬도가 매우 낮음: 최대 5점
- 일반 템플릿 남용: 최대 5.5점
- citations가 후처리로만 만들어지고 strict citation이 없음: 최대 6.5점

Q3~Q5에서도 후처리 결과만 좋은 경우를 모델 원출력과 동일하게 보지 않는다. strict citation이 없으면 Q3 최대 6점, Q4 최대 5점, Q5 최대 4점으로 제한한다.

## 실행 예시

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_llm_rubric_civil_replies.py `
  --answers logs\evaluation\week11\be3_model_benchmark_exaone_rand50_direct_20260611\parsed_answers.jsonl `
  --cases VS_지방행정기관\rand_test_50.json `
  --reference-data data\processed\processed_consulting_data.json `
  --output-dir logs\evaluation\week11\llm_rubric_proxy_exaone_rand50_direct_20260611_v2_strict
```

`--reference-data`를 생략하면 위 processed 파일을 기본값으로 사용한다. `parsed_answer_repaired`가 기본 평가 대상이며, 모델 원문만 평가하려면 `--answer-field parsed_answer_strict`를 지정한다.

## 산출물

- `rubric_scores.jsonl`: 케이스별 Q0~Q8 점수, 감점 사유, 참조 정렬도
- `rubric_report.json`: 0~10점 평균, Q0 구간 분포, 카테고리 요약, 모범 답안 프로파일
- `rubric_summary.md`: 실행 조건과 평균 점수를 정리한 Markdown 보고서

## 주의

- 이 점수는 사람 만족도를 학습한 calibration network의 예측값이 아니다.
- `consultant_answer`는 실제 회신 품질의 기준 표본이지만 모든 답변이 완벽하다고 가정하지 않는다.
- paired reference 정렬도는 복사 여부가 아니라 같은 민원에 필요한 구체 정보를 다루는지 확인하는 보조 지표다.
- 사람 평가 데이터가 축적되면 현재 Q1~Q8, 참조 정렬도, citation 지표를 feature로 사용해 별도 calibration 모델을 학습할 수 있다.

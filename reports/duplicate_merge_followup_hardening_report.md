# Duplicate Merge Quality Hardening Follow-up Report

## 1. 현재 결과 분석

직전 hardening 산출물의 100쌍 labeled evaluation은 후보/위험 지표가 모두 성공 기준을 만족했다.

| 지표 | 직전 보고서 | 후속 검증 |
| --- | ---: | ---: |
| total_pairs | 100 | 100 |
| precision | 1.0 | 1.0 |
| true duplicate recall | 1.0 | 1.0 |
| same keyword different event false positive rate | 0.0 | 0.0 |
| blocker recall | 1.0 | 1.0 |
| risk flag hit rate | 1.0 | 1.0 |
| PII leak rate | 0.0 | 0.0 |
| problem result count | 미기록 | 0 |
| elapsed_ms | 미기록 | 205.77 |
| average_ms_per_pair | 미기록 | 2.0577 |

현재 `reports/duplicate_merge_labeled_eval_report.json` 기준 실패 pair, risk miss, PII leak은 0건이다.

## 2. 발견한 미흡 사항

운영 로직의 새 실패는 발견되지 않았다. 다만 산출물과 테스트 관점에서 다음 두 가지가 미흡했다.

1. 평가 리포트의 진단 정보가 부족했다.
   - 기존 Markdown report는 precision/recall 등 summary만 제공했다.
   - 실행 시간, 평균 pair 처리 시간, problem examples, risk flag 분포가 없어 성능 병목이나 실패 원인 추적이 어려웠다.

2. PII email suffix 회귀가 aggregate 지표에만 묶여 있었다.
   - 1차 hardening 과정에서 `citizen001@example.com로` 같은 한국어 조사 결합 이메일이 payload에 남는 문제가 있었고, PII leak rate로는 잡혔다.
   - 하지만 직접 regression test가 없어 같은 문제가 재발했을 때 원인을 좁히기 어려웠다.

## 3. 개선 계획과 제3자 평가

계획은 운영 코드 추가 보수화가 아니라 평가/테스트 보강으로 제한했다.

- 평가 스크립트에 실행 시간, 평균 처리 시간, estimated score calls, problem result count, risk flag counts, problem examples를 추가한다.
- Markdown report에 quality gate와 problem examples 섹션을 추가한다.
- `test@example.com로`, `test@example.com으로` 형태가 draft payload에 raw email로 남지 않는 직접 regression test를 추가한다.

제3자 관점 검토:

- 현재 100쌍 지표는 이미 성공 기준을 만족하므로 threshold/location/request type을 더 조정하면 실제 true duplicate recall을 불필요하게 떨어뜨릴 위험이 있다.
- 이번 변경은 API contract, FE contract, draft payload schema를 바꾸지 않는다.
- raw body를 scoring에 추가하지 않고, DB migration도 없다.

## 4. 변경 내용

- `scripts/evaluate_duplicate_merge_labeled_pairs.py`
  - `elapsed_ms`, `average_ms_per_pair`, `estimated_score_calls`, `problem_result_count`, `risk_flag_counts`를 metrics에 추가했다.
  - 실패/불일치/PII leak 결과를 `diagnostics.problem_examples`에 수집하도록 했다.
  - Markdown report에 quality gates, risk flag counts, problem examples 섹션을 추가했다.

- `app/tests/unit/test_duplicate_merger_quality_hardening.py`
  - 한국어 조사가 붙은 이메일이 draft payload에서 `[REDACTED:EMAIL]`로 유지되는지 직접 검증했다.
  - 100쌍 평가 metrics에 `problem_result_count == 0`, `problem_examples == []`, 평균 처리 시간 필드가 포함되는지 확인했다.

- `reports/duplicate_merge_labeled_eval_report.json`
- `reports/duplicate_merge_labeled_eval_report.md`
  - 새 metrics와 diagnostics를 반영해 재생성했다.

## 5. 실패 pair 예시

현재 후속 평가 기준 실패 pair는 없다.

이전 hardening 루프에서 고위험으로 확인했던 유형은 다음과 같으며, 이번에 직접 회귀 테스트로 고정했다.

- PII risk 이메일 조사 케이스: `test@example.com로`, `test@example.com으로`
- 문제 성격: 기존 이메일 마스킹이 한국어 조사와 붙은 주소를 놓치면 draft payload PII leak으로 이어질 수 있음
- 현재 결과: raw email 미노출, `[REDACTED:EMAIL]` 유지

## 6. 남은 리스크

- 100쌍은 합성 라벨셋이므로 실제 운영 데이터의 precision/recall을 보장하지 않는다.
- 평가 스크립트의 `elapsed_ms`는 로컬 실행 환경에 따라 변동된다.
- `estimated_score_calls`는 평가 스크립트 기준 추정값이며, 실제 API batch의 pair 수 증가는 여전히 O(n^2) 경향을 가진다.
- PII로 세부 위치가 마스킹되는 경우 보수적으로 후보 제외될 수 있어 실제 데이터에서 recall 손실 여부를 별도 샘플로 확인해야 한다.

## 7. 검증

```text
python -m pytest app/tests/unit/test_duplicate_merger.py
결과: 글로벌 Python에서 yaml 의존성 누락으로 수집 실패

C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe -m pytest app/tests/unit/test_duplicate_merger.py app/tests/unit/test_duplicate_merger_quality_hardening.py
결과: 12 passed

C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe -m pytest app/tests/unit/test_duplicate_merger.py app/tests/unit/test_duplicate_merger_quality_hardening.py app/tests/unit/test_complaint_intelligence.py
결과: 33 passed

C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe scripts\evaluate_duplicate_merge_labeled_pairs.py --write-report
결과: precision=1.0, recall=1.0, false_positive_rate=0.0, blocker_recall=1.0, risk_flag_hit_rate=1.0, pii_leak_rate=0.0
```

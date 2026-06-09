# BE2 엉뚱한 근거 제거 완료 체크

- 생성 시각(UTC): `2026-06-09T08:14:39.541243+00:00`
- 전체 결과: **통과**
- 판정: **완료**

## 핵심 수치

| 항목 | 값 |
| --- | ---: |
| 원본 Hybrid rel0 비율 | 23.20% |
| 필터 후 rel0 비율 | 4.17% |
| rel0 상대 감소율 | 82.03% |
| 필터 후 유효 근거 비율(rel>=1) | 95.83% |
| rel0가 남은 쿼리 비율 | 14.00% |
| 필터 결과 0건 쿼리 비율 | 7.00% |
| 필터 결과 0건 쿼리 수 | 7 |
| 평균 근거 수 | 3.84 |
| 최종 E2E 샘플 수 | 10 |
| 최종 E2E grounding 오류 | 0 |
| 최종 E2E 빈 답변 | 0 |

## Gate

| Gate | 결과 | 값 | 기준 |
| --- | --- | ---: | --- |
| `filter_eval_query_count` | 통과 | 100 | >= 100 |
| `harmful_rate_topk` | 통과 | 0.0417 | <= 0.05 |
| `queries_with_harmful_topk` | 통과 | 0.14 | <= 0.15 |
| `useful_rate_topk` | 통과 | 0.9583 | >= 0.95 |
| `relative_harmful_reduction` | 통과 | 0.8203 | >= 0.8 |
| `empty_grounding_fallback_budget` | 통과 | 0.07 | <= 0.1 |
| `e2e_sample_count` | 통과 | 10 | >= 10 |
| `e2e_grounding_filter_enabled` | 통과 | True | True |
| `e2e_grounding_errors` | 통과 | 0 | 0 |
| `e2e_empty_answers` | 통과 | 0 | 0 |
| `e2e_search_path` | 통과 | 통과 | 통과 |
| `e2e_grounding_path` | 통과 | 통과 | 통과 |

## 판단

엉뚱한 근거 제거 기준은 통과했습니다. 법령 grounding fast_fallback은 BE3 생성 안정성 후속 리스크로 별도 관리합니다.

## 운영 해석

- 필터 결과 0건은 검색 실패가 아니라 안전 fallback 대상이다.
- `/qa`는 근거가 없을 때 `no_evidence_fallback`으로 가짜 근거 생성을 피해야 한다.
- 법령 grounding이 붙은 케이스의 `fast_fallback`은 BE2 검색 실패가 아니라 BE3 생성 안정성 지표로 분리한다.

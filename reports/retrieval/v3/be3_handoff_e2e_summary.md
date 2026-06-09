# BE3 handoff 기준 BE2 최종 QA E2E 검증 요약

작성일: 2026-06-09  
담당: BE2  
관련 이슈: #332

## 목적

BE3 handoff 문서 기준으로 `BE1 구조화 -> BE2 검색 -> grounding filter -> BE3 QA 생성` 흐름이 실제로 연결되는지 확인했다.

민원 원문, 답변 미리보기, 검색 snippet이 포함될 수 있는 raw 결과는 커밋하지 않고 `/tmp`에만 저장했다.

- `/tmp/be3_handoff_e2e_raw_10_with_legal.json`
- `/tmp/be3_handoff_e2e_raw_10_with_legal.md`

## 실행 조건

```bash
STRUCTURING_CONSTRAINED=true python scripts/e2e_be1_query_signals_search_qa.py \
  --structuring-mode actual \
  --grounding-filter \
  --run-generation \
  --limit 10 \
  --top-k 5 \
  --out-json /tmp/be3_handoff_e2e_raw_10_with_legal.json \
  --out-md /tmp/be3_handoff_e2e_raw_10_with_legal.md
```

## 핵심 결과

| 항목 | 결과 |
| --- | ---: |
| 샘플 수 | 10 |
| 정상 처리 | 10 |
| 실패 | 0 |
| baseline 빈 결과 | 0 |
| query_signals 적용 후 빈 결과 | 0 |
| grounding filter 실행 | 10 |
| grounding filter 오류 | 0 |
| 답변 생성 실행 | 10 |
| 답변 생성 오류 | 0 |
| 빈 답변 | 0 |
| fallback 사용 | 3 |
| 최대 JSON 파싱 재시도 | 3 |

## BE1 신호 커버리지

| 신호 | 값이 나온 샘플 수 |
| --- | ---: |
| `entity_texts` | 4 |
| `legal_ref_names` | 3 |
| `legal_ref_ids` | 3 |
| `issue_types` | 6 |
| `key_terms` | 6 |
| `responsible_units` | 0 |

`responsible_units`는 10건 모두 비어 있었다. 현재 BE1 책임부서 후보가 기본 비활성 또는 낮은 커버리지 상태일 가능성이 있어, 최종 운영 전 BE1/운영 데이터 기준으로 다시 확인해야 한다.

## 검색 및 rerank 관측

| 항목 | 결과 |
| --- | ---: |
| top1 변경 | 1 |
| 기존 top-k 안에서 위로 올라간 후보 | 4 |
| query_signals와 metadata overlap이 있는 후보가 top1인 건수 | 6 |

빈 검색 결과가 없었고, metadata soft rerank는 hard filter처럼 결과를 제거하지 않았다.

## 답변 생성 관측

| generation mode | 건수 |
| --- | ---: |
| `default` | 6 |
| `force_json` | 1 |
| `fast_fallback` | 3 |

| 법령 grounding 상태 | 건수 |
| --- | ---: |
| `no_candidates` | 7 |
| `grounded` | 3 |

BE3 PR #330 이후 빈 answer 방어는 통과했다. `fast_fallback`이 발생한 3건도 `answer_chars=462`로 비어 있지 않았다.

## 샘플별 요약

| case_id | 신호 수 | grounding 결과 수 | 생성 상태 | mode | 법령 상태 | fallback | retry | 답변 글자 수 | top1 변경 |
| --- | ---: | ---: | --- | --- | --- | --- | ---: | ---: | --- |
| 2000001 | 0 | 1 | ok | default | no_candidates | 아니오 | 0 | 296 | 아니오 |
| 2000010 | 0 | 1 | ok | default | no_candidates | 아니오 | 0 | 498 | 아니오 |
| 2000011 | 0 | 1 | ok | default | no_candidates | 아니오 | 0 | 532 | 아니오 |
| 2000002 | 4 | 1 | ok | default | no_candidates | 아니오 | 0 | 232 | 아니오 |
| 2000003 | 0 | 1 | ok | default | no_candidates | 아니오 | 0 | 328 | 아니오 |
| 2000004 | 2 | 1 | ok | default | no_candidates | 아니오 | 0 | 489 | 아니오 |
| 2000005 | 2 | 1 | ok | force_json | no_candidates | 아니오 | 1 | 554 | 아니오 |
| 2000006 | 11 | 3 | warning | fast_fallback | grounded | 예 | 3 | 462 | 아니오 |
| 2000007 | 18 | 1 | warning | fast_fallback | grounded | 예 | 3 | 462 | 예 |
| 2000008 | 9 | 2 | warning | fast_fallback | grounded | 예 | 3 | 462 | 아니오 |

## 결론

- BE2 검색 경로는 통과했다.
- metadata soft rerank는 결과를 비우지 않았다.
- grounding filter는 10건 모두 오류 없이 실행됐다.
- BE3 빈 answer 문제는 재현되지 않았다.
- 법령 grounding 상태는 `generation_metadata`로 관측 가능하다.

## 남은 리스크

법령 grounding이 적용된 3건은 모두 `fast_fallback`으로 생성됐다. 빈 답변은 아니지만, 법령 grounding이 붙은 질의에서 로컬 생성 모델이 JSON 계약을 안정적으로 맞추지 못하는 경향이 보인다. 이는 BE2 검색 문제가 아니라 BE3 생성 품질 후속 개선 후보로 기록한다.

또한 `responsible_units` 커버리지가 0건이라 담당부서 신호는 이번 sample 10에서는 검색/생성 신호로 검증되지 않았다.

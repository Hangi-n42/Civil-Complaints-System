# 메타데이터 soft rerank 평가 요약

- 평가셋: qrels_pooled_3judge, NO-self
- 후보 깊이: Hybrid RRF top-50, RRF k=60
- 평가 데이터에 PR #314 메타데이터가 없어 BE1 deterministic enrichment sidecar를 생성해 사용함

## 결론

- 일반 검색은 `nDCG@10` +0.0075, `R@10` +0.0021로 소폭 개선됐지만 `P@5`는 -0.0040 하락했다.
- 답변 초안 grounding에서는 metadata 단독 rel0 비율이 0.2320 -> 0.2360로 소폭 악화됐다.
- 따라서 grounding 기본값은 여전히 `Hybrid + LLM relevance filter`가 필요하다.
- `legal_ref_ids` coverage가 0이라 실제 PR #314 재인덱싱 후에는 법령 ID 효과를 다시 봐야 한다.

## 일반 검색

| 지표 | Hybrid | Hybrid+metadata | 변화 |
| --- | ---: | ---: | ---: |
| nDCG@5 | 0.7522 | 0.7552 | +0.0030 |
| nDCG@10 | 0.7375 | 0.7450 | +0.0075 |
| P@5 | 0.7660 | 0.7620 | -0.0040 |
| R@10 | 0.3134 | 0.3155 | +0.0021 |

## 답변 초안 grounding 관점(top-5)

| 방법 | rel0 비율 | rel0 포함 쿼리 비율 | 빈 결과 비율 | 평균 근거 수 |
| --- | ---: | ---: | ---: | ---: |
| Hybrid | 0.2320 | 0.4500 | 0.0000 | 5.00 |
| Hybrid+metadata | 0.2360 | 0.4500 | 0.0000 | 5.00 |
| Hybrid+metadata+LLM cache filter | 0.1108 | 0.3500 | 0.0000 | 4.24 |

## 해석

- metadata soft rerank는 hard filter가 아니므로 빈 결과를 만들지 않는다.
- LLM filter cache projection은 기존 LLM 채점 캐시를 재사용한 분석이며, cache coverage를 함께 확인해야 한다.
- LLM cache coverage: 0.8780 (878/1000)

## 기존 LLM filter 기준선

- 기존 `grounding_filter_effect.json`의 Hybrid+LLM-filter top-5: harmful_rate=0.0417, queries_empty_grounding=7, avg_filled_slots=3.84

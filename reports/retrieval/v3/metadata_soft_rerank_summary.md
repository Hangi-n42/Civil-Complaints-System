# 메타데이터 soft rerank 평가 요약

- 평가셋: qrels_pooled_3judge, NO-self
- 후보 깊이: Hybrid RRF top-50, RRF k=60
- 쿼리 신호: deterministic_sidecar (evaluation query files do not contain PR #314 metadata fields)
- 후보 문서 신호: chroma_metadata_with_sidecar_fallback (candidate case에 Chroma 검색 신호 metadata가 있으면 우선 사용하고, 누락 case만 deterministic sidecar로 보완)
- Chroma metadata 신호 사용 후보: 4356/4356건

## 결론

- 일반 검색은 `nDCG@10` +0.0054, `R@10` +0.0038로 소폭 개선됐고 `P@5`는 그대로였다.
- 답변 초안 grounding에서는 metadata 단독 rel0 비율이 0.2320 -> 0.2320로 같았다.
- 따라서 grounding 기본값은 여전히 `Hybrid + LLM relevance filter`가 필요하다.
- `legal_ref_ids` 후보 coverage: 1876건

## 평가 신뢰도 해석

- 현재 지표는 `data/evaluation/v3/qrels_pooled_3judge.tsv`의 100개 쿼리, 8057개 판정쌍을 기준으로 계산했다.
- relevance 분포: rel0=4965, rel1=2942, rel2=150.
- 3-채점관 median, no-self 제거, Dense/BM25 공정 풀링을 사용해 기존 평가보다 방법론은 개선됐다.
- 그래도 이 수치는 운영 품질의 최종 보증이 아니라, 검색 변경의 회귀 여부를 보는 방향성 지표로 해석해야 한다.
- 이유: 쿼리가 실제 신규 민원 held-out이 아니고, query_signals는 실제 BE1 출력이 아니라 deterministic sidecar이며, 정답표는 top-50 풀 기반이라 long-tail 불완전성이 남아 있다.

## 일반 검색

| 지표 | Hybrid | Hybrid+metadata | 변화 |
| --- | ---: | ---: | ---: |
| nDCG@5 | 0.7522 | 0.7542 | +0.0020 |
| nDCG@10 | 0.7375 | 0.7428 | +0.0054 |
| P@5 | 0.7660 | 0.7660 | +0.0000 |
| R@10 | 0.3134 | 0.3172 | +0.0038 |

## 답변 초안 grounding 관점(top-5)

| 방법 | rel0 비율 | rel0 포함 쿼리 비율 | 빈 결과 비율 | 평균 근거 수 |
| --- | ---: | ---: | ---: | ---: |
| Hybrid | 0.2320 | 0.4500 | 0.0000 | 5.00 |
| Hybrid+metadata | 0.2320 | 0.4500 | 0.0000 | 5.00 |
| Hybrid+metadata+LLM cache filter | 0.1108 | 0.3600 | 0.0000 | 4.24 |

## 해석

- metadata soft rerank는 hard filter가 아니므로 빈 결과를 만들지 않는다.
- LLM filter cache projection은 기존 LLM 채점 캐시를 재사용한 분석이며, cache coverage를 함께 확인해야 한다.
- LLM cache coverage: 0.8760 (876/1000)

## 기존 LLM filter 기준선

- 기존 `grounding_filter_effect.json`의 Hybrid+LLM-filter top-5: harmful_rate=0.0417, queries_empty_grounding=7, avg_filled_slots=3.84

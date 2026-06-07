# 검색 평가 지표 신뢰도 해석

## 결론

현재 v3 검색 평가는 이전보다 훨씬 나아졌지만, 운영 품질을 완전히 보증하는 최종 정답은 아니다.

따라서 `nDCG@10`, `P@5`, `R@10`, grounding rel0 비율은 다음처럼 해석한다.

- 검색 변경이 기존보다 나빠졌는지 보는 회귀 지표로는 유용하다.
- 검색 전략 사이의 상대 비교에는 어느 정도 신뢰할 수 있다.
- 실제 신규 민원에서 답변 초안이 항상 좋아진다는 최종 증거로 보기는 어렵다.

## 믿을 수 있는 부분

현재 평가셋은 기존 평가의 큰 결함을 보정했다.

- `qrels_pooled_3judge.tsv` 기준 100개 쿼리, 8,057개 판정쌍을 사용한다.
- relevance 분포는 rel0 4,965건, rel1 2,942건, rel2 150건이다.
- 각 쿼리는 최소 59개, 중앙값 82개, 최대 95개의 후보 문서가 판정되어 있다.
- 출처 문서를 정답으로 다시 찾는 자기참조를 제거한 `NO-self` 평가다.
- Dense top-50과 BM25 top-50을 합친 공정 풀을 사용해 풀링 편향을 줄였다.
- LLM 3개 채점관의 median으로 라벨을 정해 단일 모델 편향을 줄였다.

## 아직 조심해야 할 부분

현재 수치를 그대로 운영 품질로 받아들이기 어려운 이유도 있다.

- 쿼리가 실제 신규 운영 민원이 아니라 평가셋의 구조화 민원이다.
- 이번 metadata soft rerank 평가에서 query signal은 실제 BE1 출력이 아니라 deterministic sidecar다.
- Chroma 후보 문서 metadata는 백필 신호이므로, BE1 전체 파이프라인을 다시 통과한 산출물과 완전히 같다고 볼 수 없다.
- qrels는 top-50 풀 기반이라 long-tail 유사 문서가 모두 판정된 것은 아니다.
- spotcheck에서는 long-tail 불완전성이 남아 있음을 확인했다.
- LLM filter 평가는 일부 cache projection을 사용하므로, 운영 경로에서 live filter로 다시 확인해야 한다.
- 사람 라벨 골드시드와 통계적 유의성 검정은 아직 없다.

## 이번 PR의 수치 해석

`Hybrid + metadata soft rerank`는 일반 검색에서 기준선보다 소폭 좋아졌다.

- `nDCG@10`: +0.0054
- `R@10`: +0.0038
- `P@5`: 변화 없음

하지만 이 개선폭은 작다. 그래서 “검색기가 확실히 좋아졌다”보다는 “적어도 현재 평가셋에서는 하락하지 않고 약간의 개선 신호가 있다”로 해석하는 것이 안전하다.

답변 초안 grounding에서는 metadata rerank 단독으로 rel0 비율을 줄이지 못했다.

- Hybrid rel0 비율: 0.2320
- Hybrid + metadata rel0 비율: 0.2320

따라서 답변 초안 생성용 검색은 계속 `Hybrid + LLM relevance filter`를 기본값으로 둬야 한다.

## 다음 검증

평가 신뢰도를 더 높이려면 다음 작업이 필요하다.

1. 실제 신규 민원 또는 held-out 민원 50~100건으로 평가 query를 만든다.
2. BE1이 실제로 생성한 `query_signals`를 넣어 다시 평가한다.
3. BE1 재처리 산출물로 Chroma를 완전 재인덱싱한 뒤 백필 metadata 결과와 비교한다.
4. 사람 라벨 골드시드 50~100쌍을 만들어 LLM 라벨과 비교한다.
5. metric delta에 bootstrap confidence interval 또는 paired significance test를 붙인다.
6. 실패 사례를 rel0 원인별로 계속 분류한다.


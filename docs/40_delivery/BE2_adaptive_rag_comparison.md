# BE2 Adaptive RAG 비교 평가 정리

작성일: 2026-06-09
담당: BE2 검색
관련 이슈: #358

## 1. 목적

졸업작품 발표에서 Adaptive RAG를 검토했는지, 그리고 왜 최종 검색 전략을
Hybrid(BM25+Dense RRF)로 선택했는지 정량 근거로 설명하기 위해 기존 평가 산출물을
정리한다.

이 문서는 새로운 Adaptive RAG 튜닝이나 기능 구현을 추가하지 않는다. BE2 범위 안에서
이미 산출된 검색 평가, Adaptive 관련 실험, grounding filter 지표를 근거로 최종 판단을
정리한다.

## 2. 한 줄 결론

Adaptive RAG는 극한 튜닝 시 일부 지표 개선 가능성은 있으나, 현재 프로젝트 범위에서는
투자 대비 기대 이득이 작고 검증셋 과적합 위험이 있다. 따라서 BE2 최종 검색 전략은
정량적으로 안정적인 **Hybrid(BM25+Dense RRF)** 로 확정한다.

## 3. 비교 조건 주의

| 구분 | 평가 조건 | 판단 용도 |
| --- | --- | --- |
| 최종 BE2 검색 품질 | `qrels_pooled_3judge`, NO-self | 최종 전략 선택의 주 근거 |
| 기존 Adaptive 평가 | `qrels.tsv` 또는 초기 V3 라인 | Adaptive 미채택 판단의 참고 근거 |
| grounding filter | `qrels_pooled_3judge`, NO-self, top-k grounding | 최종 RAG 안정성 근거 |

현재 커밋된 Adaptive 평가는 최종 canonical NO-self 조건과 완전히 동일한 head-to-head는
아니다. 따라서 발표에서는 "Adaptive도 기존 실험에서 검토했으나, 최종 선택 근거는
canonical 평가에서 가장 안정적이었던 Hybrid"라고 표현하는 것이 안전하다.

## 4. 최종 검색 품질: Hybrid 선택 근거

최종 canonical 조건에서는 Hybrid가 BM25와 Dense보다 상위 검색 품질이 높다.

| 전략 | nDCG@5 | P@5 | RR@5 | R@10 | nDCG@10 | AP@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.6952 | 0.7140 | 0.8158 | 0.2885 | 0.6870 | 0.2324 |
| Dense | 0.7325 | 0.7540 | 0.8642 | 0.3132 | 0.7272 | 0.2563 |
| Hybrid(BM25+Dense RRF) | **0.7522** | **0.7660** | **0.8762** | **0.3134** | **0.7375** | **0.2604** |

Hybrid 개선폭:

| 비교 | nDCG@5 | P@5 | RR@5 | R@10 | nDCG@10 | AP@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hybrid - BM25 | +0.0570 | +0.0520 | +0.0603 | +0.0249 | +0.0505 | +0.0280 |
| Hybrid - Dense | +0.0197 | +0.0120 | +0.0120 | +0.0002 | +0.0103 | +0.0041 |

해석:

- BM25 대비로는 상위 검색 품질이 뚜렷하게 개선됐다.
- Dense 대비로는 개선폭이 작지만, 주요 상위권 지표에서 일관되게 앞선다.
- 따라서 BE2 최종 검색 전략으로는 복잡한 adaptive routing보다 Hybrid 고정 전략이 더
  설명 가능하고 안정적이다.

## 5. Adaptive RAG 기존 평가 결과

기존 `qrels.tsv` 기반 split 분석에서는 Adaptive가 Dense보다 낫다는 근거가 확인되지 않았다.

| 비교 | nDCG@5 | nDCG@10 | R@10 | AP@10 | P@5 | latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Adaptive - Dense | -0.0003 | -0.0185 | -0.0257 | -0.0210 | -0.0020 | +133.16s |

Risk 3C 경량 Adaptive 검증에서도 현재 Adaptive-Hybrid 계열은 pure Dense보다 높지 않았다.

| 비교 | nDCG@5 | nDCG@10 | R@10 | AP@10 | P@5 | latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current adaptive hybrid - pure dense | -0.0004 | -0.0195 | -0.0265 | -0.0219 | -0.0020 | +78.78s |

초기 49쿼리 라인에서는 Adaptive가 BM25보다 좋아졌지만, 사전에 둔 채택 기준은 통과하지
못했다.

| Gate | 기준 | 결과 |
| --- | --- | --- |
| nDCG@5 개선폭 | BM25 대비 +0.05 이상 | +0.0469, 실패 |
| Recall@10 guardrail | -0.02 이상 | +0.0751, 통과 |
| 전체 판정 | 모든 gate 통과 | 실패 |

해석:

- Adaptive는 BM25보다 나을 수는 있었지만, Dense/Hybrid 계열을 안정적으로 넘는 근거는
  부족했다.
- 검색 성능을 더 높이려면 단순 `top_k`, `snippet_max_chars` 조정이 아니라 쿼리 유형별로
  BM25/Dense/Hybrid 중 어떤 전략이 이기는지 학습하거나 규칙화해야 한다.
- 이 작업은 가능성은 있지만, 현재 BE2 최종 마감 기준에서는 투자 대비 효율이 낮다.

## 6. 최종 RAG 안정성: grounding filter 성과

최종 발표에서 가장 강하게 보여줄 수 있는 개선은 Hybrid 위에 grounding filter를 얹어
엉뚱한 근거를 줄인 부분이다.

| 전략 | 엉뚱한 근거 비율 | 유효 근거 비율 | rel0 포함 쿼리 | 빈 grounding |
| --- | ---: | ---: | ---: | ---: |
| Hybrid | 23.20% | 76.60% | 45.00% | 0건 |
| Hybrid+LLM-filter | **4.17%** | **95.83%** | **14.00%** | 7건 |

해석:

- 엉뚱한 근거 비율은 23.20%에서 4.17%로 감소했다.
- 상대 감소율은 약 82.03%다.
- 빈 grounding 7건은 검색 실패가 아니라 안전 fallback 대상이다.

## 7. 발표용 문장

검색 전략은 BM25, Dense, Adaptive, Hybrid를 비교했다. Adaptive RAG는 극한 튜닝 시 일부
개선 가능성은 있으나, 현재 평가에서는 Dense/Hybrid 대비 안정적인 이득이 확인되지 않았고
튜닝 대비 과적합 위험이 있었다. 따라서 최종 검색 전략은 Hybrid(BM25+Dense RRF)로
확정했다.

최종 Hybrid는 BM25 대비 nDCG@5를 +0.0570, Dense 대비 +0.0197 개선했다. 이후
grounding filter를 적용해 답변에 사용될 엉뚱한 근거 비율을 23.20%에서 4.17%로 낮췄다.

## 8. 후속으로 남길 수 있는 일

Adaptive RAG를 후속 연구로 확장하려면 먼저 oracle 분석이 필요하다.

1. 쿼리별로 BM25, Dense, Hybrid 중 어느 전략이 이겼는지 분류한다.
2. topic, complexity, query_signals별로 반복 패턴이 있는지 확인한다.
3. 패턴이 있을 때만 Adaptive Router의 숫자나 전략 선택 규칙을 튜닝한다.
4. 튜닝셋과 검증셋을 분리해 과적합 여부를 확인한다.

## 9. 근거 산출물

| 용도 | 파일 |
| --- | --- |
| 최종 canonical 검색 품질 | `reports/retrieval/v3/eval_hybrid_noself.json` |
| metadata soft rerank | `reports/retrieval/v3/metadata_soft_rerank_eval.json` |
| grounding filter | `reports/retrieval/v3/grounding_filter_effect.json` |
| Adaptive split 참고 | `reports/retrieval/v3/split_analysis_latest.json` |
| Risk 3C Adaptive 참고 | `reports/retrieval/v3/risk3c_lightweight_adaptive.json` |
| 초기 Adaptive gate 참고 | `reports/retrieval/v3/latest.json` |

# RAG Grounding 정확도 — 해로운 선례 제거 (2026-06)

> 검색(BE2) 결과를 **유사 민원 근거(grounding)로 답변 초안을 생성**하는 RAG 용도에서, 상위 K개에 섞이는 "해로운(rel0) 선례"를 측정하고 LLM 필터로 제거한 분석. (#299)

## 1. 동기 — 이 용도엔 recall이 아니라 top-K 정확도

용도: 처리 중인 민원과 **가장 유사한 과거 민원 몇 개(top-3~5)**를 근거로 답변 초안 생성.
→ 비슷한 민원을 *전부* 찾을 필요(recall) 없음. **상위 몇 개가 진짜 유사한가(precision)**가 전부.

특히 위험: rel0 문서(우리 기준 "주입 시 잘못된 안내/할루시네이션 유발")가 top-K에 끼면 → 답변이 엉뚱한 선례에 기반.
풀 불완전성 검증(`eval_overhaul_summary.md` §7)에서 retriever recall은 낮으나, 이 용도엔 무관함을 확인. 진짜 관리 대상은 **top-K 해로운 비율**.

## 2. Grounding 위험 측정 (현 상태)

canonical qrels(3채점관 median, no-self)로 BM25/Dense/Hybrid의 top-K를 분해. (`grounding_topk_breakdown.py`)

| 방법 (top-5) | 해로움(rel0) | 유효(rel≥1) | ≥1개 해로운 쿼리 |
|---|---|---|---|
| BM25 | 23.2% | 71.4% | 47% |
| Dense | 24.6% | 75.4% | 47% |
| **Hybrid** | 23.2% | 76.6% | **45%** |

- top-3: Hybrid 해로움 20.0%, ≥1 해로운 쿼리 35%.
- **프로덕션(Hybrid) top-5 기준, 질문의 45%에서 최소 1개의 해로운 선례가 근거에 포함** → 답변 오염 위험 정량화.

## 3. 리랭커 — 재정렬 vs 필터

LLM 리랭커(qwen2.5:14b, 관련성 루브릭으로 top-10 후보를 0/1/2 채점)를 두 방식으로 적용. (`grounding_filter_effect.py`)

| 변형 (top-5) | 해로움(rel0) | 유효(rel≥1) | ≥1 해로운 쿼리 | 평균 근거 수 | 근거 0개 쿼리 |
|---|---|---|---|---|---|
| Hybrid (원본) | 23.2% | 76.6% | 45% | 5.00 | 0 |
| Hybrid+LLM **재정렬** | 19.8% | 80.0% | 38% | 5.00 | 0 |
| **Hybrid+LLM 필터(0점 제거)** | **4.2%** | **95.8%** | **14%** | 3.84 | 7 |

- **재정렬만으론 미미**(-3.4pp) — 해로운 후보가 여전히 top-5 안에 잔류.
- **필터(0점 후보 제거)는 해로운 선례를 82% 제거**(23.2%→4.2%), 오염 쿼리 45%→14%.
- 잔여 4.2% = 단일 LLM(qwen)이 3채점관 median과 불일치하는 경우(판단 한계).
- (참고) `eval_llm_reranker_full.json`: 리랭커는 nDCG@10은 -0.012지만 P@5 0.766→0.800·RR@5 0.876→0.910. "리랭커가 해롭다"(`eval_overhaul_summary.md` §3.6)는 **@10 기준 결론**이며, **grounding(top-K) 용도엔 적용되지 않음**.

## 4. 왜 후보에 해로운 게 끼나 — 구조적 한계 + 2단계 설계

1단계 검색(BM25+Dense)은 전 코퍼스(9,132)를 빠르게 훑으려 **표면 유사도**(어휘·임베딩 의미)만 본다. 그러나 우리 관련성 기준은 **핵심 쟁점+법령+관할 일치**라는 깊은 판단 → 둘 사이 틈 때문에 "키워드는 같으나 쟁점이 다른 함정 민원"이 후보에 끼는 것은 **구조적으로 불가피**.

→ 이것이 retrieve-then-rerank **2단계 설계**의 근거. 깊은 판단을 전수에 못 돌리니, 1단계는 후보 모으기(recall), 2단계가 정밀 거르기(precision). 본 필터가 곧 2단계.

## 5. 권장

**RAG grounding 스택 = Hybrid + LLM 필터(0점 제거)**
- 해로운 선례 82% 제거 → 답변 품질 위험 대폭 감소.
- 근거 0개 쿼리(7%, LLM이 top-10 전부 0점) → **"유사 사례 없음" 폴백** (엉뚱한 근거보다 안전).
- 비용: 후보당 LLM 채점 → 쿼리당 ~2초 지연. 실시간 검색 아닌 답변 초안 용도엔 수용 가능.
- generator(BE3) 연계 사항이라 적용은 **핸드오프 필요**.

## 6. 프로덕션 통합 (#305)

필터는 두 곳에서 동일 코어(`app/retrieval/grounding_filter.py`)를 공유한다:
- **eval**: `LLMRelevanceFilterStage` + `hybrid_bm25_dense_rrf_llmfilter.yaml`
- **프로덕션**: `RetrievalService.search(query, top_k, grounding_filter=True)` — 답변 생성(be3)이 호출하는 실제 경로

**사용법 (be3)**
```python
results = await retrieval_service.search(query, top_k=5, grounding_filter=True)
# results == [] 이면 "유사 사례 없음" → grounding 없이 답변 정책 적용
```
또는 환경변수 `GROUNDING_FILTER_ENABLED=true`로 전역 활성화. 모델은 `GROUNDING_FILTER_MODEL`(미지정 시 `OLLAMA_MODEL`).

- 기본값 **OFF** → 켜기 전 검색 동작 불변.
- 켜지면 후보 `GROUNDING_FILTER_POOL`(10)개를 LLM 채점 → `rel0` 제거 → `top_k` 반환. 통과 0개면 빈 리스트(폴백 신호).
- LLM 장애 시 permissive(원본 유지) → 검색이 멈추지 않음.
- end-to-end 검증(#303): 실제 파이프라인에서 해로움 27.8%→0.9%. 단위·통합 테스트 포함.

## 7. 한계 · 향후

- 잔여 4% 추가 감소: 도메인 적응 임베딩(1단계 개선), 법령/관할 구조화 필드 1차 필터, 3채점관 필터(느림). 수확체감.
- 필터 임계값(0점만 제거 vs 1점 미만 제거)·K·폴백 정책은 generator 측 end-to-end 품질로 튜닝 필요.
- 멀티세그먼트 경로는 후보 풀이 작아 필터 효과 제한적(단일세그먼트 위주 적용).

## 7. 산출물

| 종류 | 경로 |
|---|---|
| 스크립트 | `scripts/grounding_topk_breakdown.py`, `scripts/grounding_filter_effect.py` |
| 리포트 | `reports/retrieval/v3/{grounding_topk_breakdown,grounding_filter_effect,eval_llm_reranker_full}.json` |
| LLM 점수 캐시 | `data/evaluation/v3/checkpoints/llm_rerank_full.json` |
| 공유 코어 · 스테이지 · 서비스 | `app/retrieval/grounding_filter.py`, `app/retrieval/pipeline/stages/llm_relevance_filter.py`, `RetrievalService.search(grounding_filter=...)` |
| 이슈 | #299, #301, #303, #305 |

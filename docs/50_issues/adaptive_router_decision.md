# Adaptive Router 가치 재평가 — 결정 보고서

**작성일**: 2026-05-28
**관련 이슈**: #159 (Week5 도입), #168 (Week6 trace), #234/P5 (topic 매핑 확장), #259 (Hybrid 통합)
**근거 데이터**: [reports/retrieval/v3/latest.json](../../reports/retrieval/v3/latest.json), [reports/retrieval/v3/split_analysis_latest.json](../../reports/retrieval/v3/split_analysis_latest.json)

---

## 1. 배경

[#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262) qrels 정정 후 V3 100쿼리 평가에서 Adaptive Router와 BGE-m3 Dense의 nDCG@5가 0.897로 사실상 동률. Latency는 Adaptive 162s vs Dense 29s로 5.6배 차이. "유지할 가치가 있는가" 결정 필요.

## 2. 측정 결과

### 2-1. 전체 100쿼리 ([latest.json](../../reports/retrieval/v3/latest.json), `qrels_final` 749쌍 기준)

| 지표 | BM25 | Dense | Adaptive | A − D |
|---|---|---|---|---|
| nDCG@5 | 0.397 | 0.483 | 0.444 | −0.039 |
| nDCG@10 | 0.435 | 0.567 | 0.494 | −0.073 |
| R@10 | 0.385 | 0.532 | 0.460 | −0.072 |
| MRR@10 | 0.402 | 0.447 | 0.423 | −0.024 |
| **Latency** | 9.18s | **18.62s** | 14.67s | — |

> 이 리포트는 qrels 49쿼리(`qrels_final.tsv`) 기준이므로 전체 100쿼리 결과와 다름. 아래 split_analysis_latest.json이 신뢰 가능한 100쿼리 결과.

### 2-2. 100쿼리 split 분석 ([split_analysis_latest.json](../../reports/retrieval/v3/split_analysis_latest.json), 2549쌍 기준)

| 영역 | 지표 | BM25 | Dense | Adaptive | A − D | 판정 |
|---|---|---|---|---|---|---|
| **all** | nDCG@5 | 0.839 | 0.897 | **0.897** | −0.0003 | ≈ tie |
| | nDCG@10 | 0.802 | **0.893** | 0.875 | −0.0185 | Dense win |
| | R@10 | 0.498 | **0.592** | 0.566 | −0.0257 | Dense win |
| **old(49)** | nDCG@5 | 0.868 | 0.925 | **0.935** | +0.0096 | Adaptive win |
| | nDCG@10 | 0.830 | **0.939** | 0.901 | −0.0382 | Dense win |
| | R@10 | 0.613 | **0.734** | 0.683 | −0.0516 | Dense win |
| **new(51)** | nDCG@5 | 0.811 | **0.870** | 0.860 | −0.0100 | Dense win |
| | nDCG@10 | 0.775 | 0.849 | 0.850 | +0.0005 | ≈ tie |
| | R@10 | 0.389 | 0.454 | 0.454 | −0.0007 | ≈ tie |

### 2-3. Latency

| 방법 | Latency (100쿼리 누적) |
|---|---|
| Dense | 29.03s |
| BM25 | 151.33s |
| **Adaptive** | **162.19s** (Dense의 **5.6배**) |
| Dense+Reranker | 211.60s |
| Hybrid+Reranker | 363.82s |

## 3. 진단

### 3-1. 성능
- **Primary 지표(nDCG@5)에서 동률**: A−D = −0.0003 (0.03% 차이). 통계적으로 무의미.
- **Secondary 지표는 일관되게 Dense 우세**: nDCG@10 -0.0185, R@10 -0.0257.
- **단 1개 slice(old·nDCG@5)에서만 Adaptive 우세**: +0.0096. 다른 5개 slice 비교에서 모두 동률 또는 Dense 우세.

### 3-2. Latency
- Adaptive 162s = Dense 29s + α(133s). α는 다음 요소:
  - `_normalize_request_segments()` 처리 (`\n` 감지 후 single-path 조기 반환, [#256](https://github.com/Hangi-n42/Civil-Complaints-System/pull/256))
  - `_apply_retrieval_policy()` policy boost 계산 ([service.py:475-516](../../app/retrieval/service.py))
  - `_hybrid_rrf()` BM25+Dense RRF 합산, top-k×3 풀링 ([service.py:564+](../../app/retrieval/service.py), [#259](https://github.com/Hangi-n42/Civil-Complaints-System/pull/259))
  - `topic_type` 매핑 + 메타데이터 부착
- 즉 Adaptive는 사실상 "Dense top-k×3 → 메타 가공 → Hybrid RRF" 파이프라인이며 그 추가 비용이 5.6배 latency로 환산.

### 3-3. Gate 판정 ([latest.json:gate](../../reports/retrieval/v3/latest.json))
49쿼리 기준 BM25 baseline 대비 Adaptive 채택 게이트:
- nDCG@5 개선 +0.0469 (요구 +0.05) → **FAIL** (0.0031 부족)
- Recall@10 개선 +0.0751 (요구 ≥ -0.02) → PASS
- **전체: FAIL**

## 4. 시나리오 비교

| 시나리오 | nDCG@5 | nDCG@10 | R@10 | Latency | 코드 복잡도 |
|---|---|---|---|---|---|
| **A. 현행 유지** | 0.897 | 0.875 | 0.566 | 162s | High (현행) |
| **B. Dense 단독** | 0.897 | 0.893 | 0.592 | **29s** | Low |
| C. Adaptive 경량화 (Hybrid·policy 제거, topic 메타만 유지) | 미측정 | 미측정 | 미측정 | 추정 ~50s | Mid |

## 5. 결정 (2026-05-28 갱신 — 시나리오 C 채택)

**채택: 시나리오 C (경량 Adaptive — Hybrid·policy 제거, topic 라우팅 유지)**

### 당초 시나리오 B(Dense 단독)에서 변경한 이유

Adaptive Router는 라우팅 공간이 Dense를 포함하므로 **이론상 잘 튜닝하면 Dense 이상**이어야 한다. 현재 Adaptive < Dense인 원인은 구조가 아니라 특정 컴포넌트(Hybrid RRF, policy boost)가 일관되지 않게 동작하기 때문:
- OLD(49)에서는 Hybrid가 nDCG@5 +0.0096 도움
- NEW(51)에서는 Hybrid가 −0.0100 방해
- → 평균 wash, nDCG@10·R@10에서는 순손해

즉 점수를 깎는 컴포넌트만 제거하면 nDCG 회복 + Latency 회복 + Adaptive 구조(미래 라우팅 capability) 보존이 동시에 가능. "완전 제거"는 미래 자산까지 버리는 과한 선택.

### 근거 (측정값)
1. **Hybrid가 Dense 단독보다 못함** — Risk 2: Dense nDCG@5 0.897 > BM25 0.836, Hybrid는 둘 사이로 끌어내려짐
2. **policy boost slice 비일관성** — OLD/NEW에서 반대 방향
3. **Latency 5.6배 페널티의 주범이 Hybrid BM25** — 제거 시 Dense 수준 회복 기대
4. **topic 라우팅은 보존 가치 있음** — 코퍼스 확대 시 재활용 가능한 확장점

## 6. 실행 계획 ([#263](https://github.com/Hangi-n42/Civil-Complaints-System/issues/263))

### 제거 ([service.py](../../app/retrieval/service.py))
- `_hybrid_rrf()` — BM25+Dense RRF 경로 ([#259](https://github.com/Hangi-n42/Civil-Complaints-System/pull/259) 도입분)
- `_apply_retrieval_policy()` policy boost(+0.04)
- `_bm25_top_k()` + `_bm25_cache` — Hybrid 제거 후 사용처 없으면 정리

### 유지
- `topic_type` 파라미터 + 메타데이터 (라우팅 capability)
- `_normalize_request_segments()` `\n` 구조화 쿼리 처리 ([#256](https://github.com/Hangi-n42/Civil-Complaints-System/pull/256))
- `search()` 시그니처 불변

### 검증 완료 (2026-05-28, 런타임 몽키패치 — 코드 변경 없음)

`_hybrid_rrf`만 비활성화하여 100쿼리 재측정 ([reports/retrieval/v3/risk3c_lightweight_adaptive.json](../../reports/retrieval/v3/risk3c_lightweight_adaptive.json)):

| 방법 | nDCG@5 | nDCG@10 | R@10 | Latency |
|---|---|---|---|---|
| 현행 Adaptive (Hybrid) | 0.8970 | 0.8736 | 0.5651 | 93.4s |
| **경량 Adaptive (no Hybrid)** | 0.8944 | **0.8929** | **0.5916** | **15.1s** |
| 순수 Dense (대조) | 0.8973 | 0.8932 | 0.5916 | 14.7s |

**가설 확인**:
- nDCG@10 회복 +0.0193, R@10 회복 +0.0265 → Dense와 동일
- Latency 6.2× 단축 (93.4s → 15.1s)
- **Hybrid RRF([#259](https://github.com/Hangi-n42/Civil-Complaints-System/pull/259))는 순수하게 해로웠음** — 어떤 지표에서도 이득 없이 nDCG/R만 깎고 latency 6배

**중요 단서**: 경량 Adaptive는 Dense를 **이기지 않고 동등**. scenario C의 실익은 무회귀 + latency 회복 + topic 라우팅 구조 보존(미래 자산)이며, Dense 초과 성능은 아님. 추가 튜닝(RRF k, weighted RRF)으로 Dense 초과를 노리려면 별도 sprint 필요하나, 현 코퍼스(9,132건)에서 BM25 신호가 Dense에 대부분 흡수되어 ROI는 낮을 것으로 예상.

## 7. 리스크 / 반대 의견

- **OLD 49쿼리에서는 Adaptive가 nDCG@5 +0.0096 우세** — 구형 평가셋에 한정된 advantage. 발표 자료에서 OLD만 보고하면 Adaptive가 더 좋아 보이지만, NEW 51쿼리에서는 -0.0100으로 상쇄됨. 즉 평가셋 구성에 의존적인 미세 차이.
- **Adaptive에 투자한 개발 시간 회수 손실** — Sunk cost로 간주. 평가 데이터가 명확히 가리키는 방향을 따르는 것이 옳음.
- **Topic-aware routing의 미래 가치** — 코퍼스 규모가 9,132건의 수십배로 늘어나면 다시 검토 가치 있음. 그때를 위해 `topic_analyzer.py`는 `app/retrieval/_archived/` 등으로 이동 보존 권장.

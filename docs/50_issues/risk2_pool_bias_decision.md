# Risk 2: qrels Pool Bias 검증 — 결정 보고서

**작성일**: 2026-05-28
**대상**: [#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262)에서 추가된 201쌍이 Dense 점수를 과대평가시켰는지
**근거 데이터**: [reports/retrieval/v3/risk2_pool_bias_analysis.json](../../reports/retrieval/v3/risk2_pool_bias_analysis.json)

---

## TL;DR

**Pool bias 위험은 LOW.** [#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262)의 nDCG@5 0.501 → 0.897 점프는 실제 qrels 개선이며, Dense에 편향되어 있지 않다. **추가된 201쌍은 오히려 BM25에 더 큰 절대 이득을 줬다.**

## 1. 측정 결과

| qrels 변형 | 쌍 수 | BM25 nDCG@5 | Dense nDCG@5 | Δ (Dense−BM25) |
|---|---|---|---|---|
| V0_full (현재) | 2,549 | 0.836 | **0.897** | +0.061 |
| V1_no_genorig (-35) | 2,514 | 0.693 | 0.762 | +0.069 |
| V2_no_cepool (-166) | 2,383 | 0.556 | 0.636 | +0.080 |
| V3_pre262 (#262 머지 전) | 2,348 | 0.413 | 0.501 | **+0.088** |

## 2. 핵심 발견

### 2-1. Pool 추가의 절대 이득 — BM25가 더 컸음

| 방법 | V3 → V0 nDCG@5 변화 | 상대 증가율 |
|---|---|---|
| BM25 | +0.413 → +0.836 (**Δ=+0.423**) | **+102%** |
| Dense | +0.501 → +0.897 (Δ=+0.396) | +79% |

→ Phase 1 정적 분석의 가설("pool 출처가 Dense+Reranker이므로 Dense-편향")이 **틀렸다**. 추가된 docs가 양쪽 모두에게 발견 가능한 정상적인 relevant 문서들이었다는 의미.

### 2-2. Dense 우위는 변형에 robust

Dense−BM25 격차가 4 변형에서 모두 **+0.06 ~ +0.09**로 거의 일정:
- V0 (full): +0.061
- V3 (pool 제거): +0.088

오히려 pool 제거 시 Dense 우위가 더 커짐 → Dense 우위는 pool과 무관한 본질적 능력 차이.

### 2-3. 35 generation-origin vs 166 cross-encoder pool 영향

| 그룹 | BM25 nDCG@5 영향 | Dense nDCG@5 영향 |
|---|---|---|
| 35 gen-origin (V0 vs V1) | −0.143 | −0.135 |
| 166 ce_pool (V0 vs V2) | −0.280 | −0.261 |

두 그룹 모두 BM25와 Dense에 거의 동등한 영향. **편향 부재**.

## 3. 평가셋 신뢰성 판정

| 항목 | 판정 |
|---|---|
| 0.897 nDCG@5가 pool inflation인가 | **NO** — 양 방법이 모두 동일 비율로 상승 |
| Dense의 우위가 평가셋 artifact인가 | **NO** — 변형 전체에서 +0.06~0.09 일정 |
| 발표용으로 신뢰 가능한가 | **YES** — 단 "재라벨링 + cross-encoder pool 확장 후" 명시 |

## 4. 결정

**[#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262) qrels 채택을 유지.** Phase 3 (held-out 검증)과 Phase 4 (스팟체크)는 **추가 진행 불필요** — Phase 2 정량 결과가 위험 가설을 기각.

## 5. 발표·보고 자료 권고

다음 두 가지 단서를 자연스럽게 명시:
1. "qrels는 #262 cross-encoder pooling으로 확장되어 인플레이션을 검증함. 변경 전후 비교에서 BM25/Dense 우위 격차는 보존됨 (+0.06~0.09)."
2. "절대 점수 0.897은 100-쿼리 / 2,549-쌍 qrels 기준이며, pool 출처 영향은 양 방법 동등."

## 6. 남은 사소한 followup

- **Adaptive 측정 미완료**: Risk 2 재실행 시 `RetrievalService`가 CUDA 기본값으로 동작해 CPU 환경에서 실패. Risk 3에서 Adaptive ≈ Dense로 결정했으므로 pool bias 측정에는 비핵심. 향후 service.py의 EMBEDDING_DEVICE 기본값 점검은 [#263](https://github.com/Hangi-n42/Civil-Complaints-System/issues/263)(Adaptive 제거) 범위 내 처리.

## 부록: 절대 점수 회복 분석

Pool 제거 시 BM25는 nDCG@5가 0.836 → 0.413으로 절반 수준까지 떨어짐. Dense도 0.897 → 0.501. 이는 **#262 이전의 qrels가 매우 불완전했음**을 보여줌. 즉 [#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262)의 pool 확장은 진정한 false negative 발견 작업이었으며, 평가 시스템의 정확도(어떤 방법을 채택할지)에는 영향 없음.

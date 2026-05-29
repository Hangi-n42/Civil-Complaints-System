# reranker가 Dense에 지는 원인 — 심화 진단

**작성일**: 2026-05-29
**관련**: [#202](https://github.com/Hangi-n42/Civil-Complaints-System/issues/202)(reranker 도입), [#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262)(cross-encoder 재평가)
**근거**: [reports/retrieval/v3/reranker_diagnosis.json](../../reports/retrieval/v3/reranker_diagnosis.json), [scripts/reranker_diagnosis.py](../../scripts/reranker_diagnosis.py)

---

## TL;DR

reranker가 Dense보다 낮은 점수(nDCG@5 0.824 vs 0.897)는 **두 원인의 복합**이며, "reranker가 나쁘다"는 단정은 틀렸다:

1. **(평가셋 한계) reranker top-5의 16%가 qrels 미판정** — 과거 판정 기록상 reranker가 발굴한 미판정 문서의 **83%가 실제 관련 문서**였음. 즉 reranker 실제 성능은 측정치보다 높다(unjudged penalty).
2. **(reranker 한계) Dense가 top-5에 둔 확인된 관련 문서의 35.6%를 reranker가 top-10 밖으로 강등** — 이건 평가셋 탓이 아닌 명백한 손해.

**순결론**: 이 도메인에서 **BGE-m3 Dense가 이미 천장에 근접**(top-5 unjudged 0.2%)하여 reranker가 끼어들 여지가 적고, 끼어들면 발굴 이득(<) 강등 손해(>)로 귀결. **현 코퍼스에서 비채택이 맞으나(#262 유효), reranker 무용론은 아님.**

## 측정 결과 (V3 100쿼리)

| 지표 | Dense | Reranker | Δ |
|---|---|---|---|
| nDCG@5 | 0.8973 | 0.8242 | −0.0732 |
| nDCG@10 | 0.8932 | 0.8008 | −0.0924 |
| R@10 | 0.5916 | 0.4947 | −0.0969 |

### 분석 1 — unjudged rate (qrels 편향)
| | Dense | Reranker | Δ |
|---|---|---|---|
| top-5 미판정 비율 | 0.2% | **16.0%** | +15.8%p |
| top-10 미판정 비율 | 0.1% | **24.1%** | +24.0%p |

Dense top은 거의 전부 qrels에 등재(=판정됨)된 반면, reranker는 top-5의 1/6, top-10의 1/4를 qrels 밖 문서로 채운다. 이 문서들은 자동으로 rel=0 처리되어 점수를 못 받는다.

**핵심 보강 증거**: [#262](https://github.com/Hangi-n42/Civil-Complaints-System/pull/262)에서 reranker가 발굴한 미판정 문서 199개를 LLM 판정한 결과 — **166개(83.4%)가 rel≥1, 59개(29.6%)가 rel=2**. 즉 reranker가 올리는 미판정 문서의 대다수가 실제로 관련 있다. → 측정된 0.824는 reranker를 **과소평가**한 값.

### 분석 2 — rank displacement (reranker 자체 한계)
Dense가 top-5에 둔 **확인된 positive(rel≥1) 405개**를 reranker가:
| 처리 | 개수 | 비율 |
|---|---|---|
| top-5 유지 | 207 | 51.1% |
| 6~10위로 강등 | 54 | 13.3% |
| **top-10 밖 탈락** | **144** | **35.6%** |

unjudged와 무관하게, **이미 관련으로 라벨된 문서**를 reranker가 35.6%나 밀어낸다. 예: Q-0001에서 dense#2(rel=1), dense#5(rel=1) 문서가 reranker에서 top-10 밖으로 탈락.

### 분석 3 — per-query 승패
| | 개수 |
|---|---|
| reranker 승 | 9 |
| reranker 패 | **53** |
| 무 | 38 |

reranker가 망친 쿼리들은 **Dense가 nDCG@5=1.0(완벽)으로 풀던 것**: Q-0060(1.0→0.51), Q-0012(1.0→0.61), Q-0019(1.0→0.63). dense가 완벽히 정렬한 상위권을 reranker가 흔들어 깨뜨린다.

## 해석

- **Dense(BGE-m3)가 이 도메인(한국어 행정 민원 + 4요소 구조화 쿼리)에 압도적으로 강하다.** top-5 unjudged 0.2%는 dense가 상위를 거의 전부 관련 문서로 채운다는 의미 — 개선 여지가 작은 "천장" 상태.
- **cross-encoder(bge-reranker-v2-m3)는 일반 도메인 학습**이라, dense가 이미 잘 정렬한 한국어 행정 민원 상위권을 재배치하면 confirmed positive를 흔드는 손해가 발굴 이득을 초과.
- reranker의 발굴 능력(83% 적중)은 진짜지만, **현 평가셋이 그걸 못 잡고 + dense 천장이 높아** 순효과가 마이너스.

## 권고

1. **현 코퍼스(9,132건)에서 cross-encoder reranker 비채택** — #262 결정 유효. 단 사유는 "reranker 열등"이 아니라 "dense 천장 + 평가셋 미판정".
2. **재고 조건**: 코퍼스가 수십 배로 커져 dense 단독 recall이 떨어지거나, dense가 약한 신규 도메인 유입 시 reranker 재평가 가치.
3. **평가셋 측면**: reranker top의 unjudged 16%를 추가 판정하면 reranker 실제 성능이 드러남. 단 이는 reranker 채택을 위한 것이며, dense 천장이 높은 현재로선 우선순위 낮음.
4. **하지 말 것**: "reranker가 nDCG 낮으니 무용"이라는 단순 결론. 측정의 unjudged penalty를 함께 보고해야 정확.

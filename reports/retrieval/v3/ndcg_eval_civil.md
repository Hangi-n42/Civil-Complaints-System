# 민원 검색 시스템 비교 — nDCG@10 (LLM-silver)

> 2026-06-21. 민원 코퍼스 9,132 / 쿼리 100(version-neutral) / pool top-50(dense·bm25·hybrid 합집합 8,732 pair).
> 채점: Codex(구독 모델, temperature 결정적) — 루브릭 v3.1(재사용 안전성, 3축+risk cap).
> **LLM-silver 기준. 절대 gold 아님 — variant 상대 비교·회귀 탐지용.**
>
> ⚠️ **중대 정정(2026-06-21): '어절 BM25' 기준 `dense>hybrid`는 BM25 한국어 토큰화 결함 아티팩트.** 형태소(kiwi)로 고치고 **확장 pool 재judge(미채점 0%)**까지 마친 결과 **형태소 hybrid 0.791 = dense 0.789 (동률 확정, Δ+0.0016 [−0.021,+0.024] 무의)**. 한국어 토큰화가 검색 1차 병목. 상세는 맨 아래 「형태소 토큰화 재평가」. (독립 AI 2차 검증 + 재judge 완료)

## 결과 (nDCG@10)

| 시스템 | linear(0,1,2) | exp(0,1,3) | hybrid 대비 Δ(linear) 95% CI |
|---|---|---|---|
| **dense** | **0.798** | **0.815** | — |
| hybrid | 0.754 | 0.771 | **−0.043** [−0.067, −0.019] · 유의 |
| bm25 | 0.556 | 0.581 | +0.199 [+0.162, +0.238] · 유의 |

- paired query-level block bootstrap(2,000 resample) 95% CI.
- dense vs hybrid: hybrid 우세 쿼리 41/100. hybrid vs bm25: 85/100.

## 결론
1. **dense > hybrid > bm25** — linear·exp gain 모두 동일 방향(robust), 세 쌍 모두 유의.
2. **dense 단독이 hybrid보다 유의하게 높음**(Δ −0.043). BM25(0.56)가 RRF에서 hybrid를 dense 아래로 끌어내림.
3. → **민원 도메인에선 BM25 결합(hybrid)의 기여가 음(−)** 일 수 있음. 운영 기본값(hybrid) 재검토 후보.

## 반드시 붙일 Caveat
- **LLM-silver**: Codex 단일 judge 채점, **사람 전문가 anchor 미실시**. 절대 점수 아닌 **상대 비교**로만 해석.
- **pool bias 가능**: pool이 세 시스템 합집합이라 dense 후보가 pool에 많아 dense에 유리한 측면 존재.
- **rel=2 희소**(83/8,732=0.95%): 직접답이 드물어 nDCG가 rel=1 중심. linear·exp 일치는 robust 신호이나, rel=2 판정 민감도는 사람 anchor로 검증 필요.
- 코퍼스 snapshot 고정(민원 9,132, 정책 Q&A 제외, sha256 fdda4ce9).

## 다음(권장)
- 사람 anchor 30~50쌍(층화: dense·hybrid 승패 갈리는 pair 우선)으로 Codex judge calibration(Spearman ρ, Cohen κ) → silver 신뢰도 보강.
- 신뢰되면 "dense 우세" 결론으로 운영 검색 전략 재검토.

## 독립 검증 — 실제 담당자 답변 교차검증
Codex silver를 **사람 신호로** 검증: 각 (쿼리,후보) pair에서 **쿼리 민원의 담당자 답변 ↔ 후보 사례의 담당자 답변** 유사도(bge-m3 cosine)를 Codex score와 비교. 담당자 답변 = `processed_consulting_data.json` 9,130건(consultant_answer 99.98% 채움, 실질정보 80%/정형응대 0%, 샘플 50). 교차검증 가능 8,730/8,732 pair(99%).

| Codex score | 담당자 답변유사도 평균 | n |
|---|---|---|
| 0 (무관) | 0.591 | 6,651 |
| 1 (부분) | 0.754 | 1,996 |
| 2 (직접답) | **0.977** | 83 |

- **단조 증가**(0.59 < 0.75 < 0.98): Codex가 높게 채점한 pair일수록 실제 담당자 답변이 유사 → silver가 사람 처리와 일관.
- Pearson 0.523 / Spearman 0.366(score 3등급 tied로 낮으나 추세 명확).
- **핵심**: 이 평가는 "LLM이 LLM을 채점"이 아니라 **실제 담당자 답변으로 교차검증된 silver**다.
- caveat: 답변유사도는 정형 응대 형식 때문에 rel0도 0.59 기반(절대 0 아님). rel=2는 n=83 소수.

## ⚠️ 형태소 토큰화 재평가 — 결론 정정 (가장 중요)
앞 결과의 BM25는 `InvertedBM25`(`hybrid.py`)의 토큰화 `_TOKEN=[A-Za-z0-9가-힣]+`를 쓰는데, 이는 **형태소 분석 없는 어절 분리**다. 조사가 붙어("도로법을" vs "도로법은") 한국어 BM25 매칭이 대량 실패. 토큰화만 **형태소(kiwi 내용어)**로 교체해 동일 조건 재평가(`scripts/eval_bm25_morph.py`):

| 시스템 | 어절(기존) | 형태소(kiwi) | Δ 95% CI |
|---|---|---|---|
| BM25 | 0.556 | **0.698** | +0.143 [+0.099, +0.190] · 유의 |
| hybrid | 0.754 | **0.798** | +0.043 [+0.022, +0.067] · 유의 |
| dense | 0.798 | — | (형태소 hybrid − dense) +0.0002 [−0.021, +0.023] · **무의=동률** |

- top-10 관련문서(rel≥1) 적중: 어절 BM25 3.83 → **형태소 5.09**(dense 6.24).
- **결론 정정**: "dense 우세 / BM25 손해"는 어절 BM25의 **토큰화 결함에 크게 의존**(robust 아님). 형태소로 고치면 동일 silver qrels에서 **hybrid의 열세가 사라짐**(Δ 무의). 단 'hybrid=dense 확정/hybrid 우세'는 재judge 전 **보류**.
- caveat(독립 AI 2차 검증 수용):
  - 형태소 top-10 pool 커버리지 80%(밖 20% 미채점=rel0). 이 미채점은 형태소에 **불리한 incomplete qrels**. 단 nDCG는 새 관련문서가 IDCG 분모도 바꿔 **단순 '하한'은 아님**(DCG·hit만 하한에 가까움) — '하한' 표현 철회.
  - 정식 비교 = 형태소 top-50을 pool에 추가해 **재judge**. 방향은 형태소 유리 가능성이 크나 보장 아님.
  - 토큰화 변경 시 k1/b/RRF/dense-BM25 weight **재튜닝** 대상. 복합명사 과분해('도로법'→'도로'+'법')는 법령·기관명 **정밀도 손실 위험**(원형+복합 둘 다 색인·도메인 사전·법령 phrase 보존이 대안).
- **함의**: 현재 evidence상 **가장 먼저 고칠 고ROI 항목은 BM25 한국어 토큰화**(BM25 전용으론 타당). 단 "전체 검색 개선 1순위=토큰화만"은 과함(dense도 한국어 영향). 운영 도입은 결정 사안 → Decision Brief + 사람 spot-check/A-B 후.

### ✅ 확장 pool 재judge 결과 — 최종 확정 (2026-06-21)
형태소 BM25/hybrid top-10 신규 후보 **198개(70쿼리)**를 동일 Codex 루브릭으로 재채점(rel 0=136/1=62/2=0; **신규의 31%가 관련** → 0점 처리가 형태소에 불리했음 확인). 기존 qrels와 병합, ideal=확장 pool, 형태소 top-10 채점 커버리지 **100%**:

| 시스템 | nDCG@10 |
|---|---|
| 형태소 hybrid | **0.791** |
| dense | 0.789 |
| 형태소 BM25 | 0.743 |
| 어절 hybrid | 0.746 |

- **형태소 hybrid − dense = +0.0016 [−0.021, +0.024] 무의 → 동률 확정**(42/100).
- 형태소 hybrid − 어절 hybrid = +0.045 [+0.024, +0.069] 유의(토큰화 개선 확정).
- 형태소 BM25 − dense = −0.046 [−0.080, −0.013] 유의(BM25 단독은 dense보다 약하나, hybrid 결합 시 동률 → **"BM25 결합 손해" 철회**).
- **최종 결론**: 초기 dense 우세는 토큰화 아티팩트, 형태소 적용 후 **hybrid=dense 확정**. 스크립트 `scripts/{build_morph_rejudge_input,eval_morph_final}.py`.
- 남는 한계: LLM-silver(사람 anchor 없음)·query 100 대표성·top-11~50 미채점(nDCG@10엔 미영향). **운영 전환은 사람 spot-check/A-B 후.**

## 지표 타당성 검토 (construct validity, 독립 AI 4차 검증 수용)
**질문: nDCG@10 / rel("재사용 안전")이 진짜 "답변 초안 생성 도움"을 재는가?**

BE3(답변 생성) 실제 사용(`app/generation/`): grounding **top-5**(프롬프트 2~3개), 사례의 **snippet(120~200자)만**, 역할은 "참고"(복사 금지).

**갭1 — top-k 정렬**(`scripts/eval_topk_validity.py`): 실제 범위(top-5/3)로 재계산:

| | nDCG@5 | nDCG@3 | Success@3 | MRR@5 |
|---|---|---|---|---|
| dense | 0.835 | 0.866 | 1.00 | 0.985 |
| 형태소 hybrid | 0.836 | 0.876 | 1.00 | 0.990 |

형태소 hybrid−dense Δ@5/@3 모두 무의(동률 유지). **Success@3=1.0·MRR≈0.99·hit@5≈3.6 = 천장 효과**(시스템 변별 거의 없음).

**천장 정체**(`scripts/diag_self_retrieval.py`): query↔top-1 유사도 평균 0.825(>0.95 **0%**, >0.90 **5%**), top-1 관련율 **97%**. → **near-dup/self-retrieval 아님**(평가가 복붙으로 부풀려진 게 아님). **검색이 실제로 잘 찾는 게 맞음.**

**갭2 — 평가 단위(미해결, 최대 validity gap)**: 평가 rel은 **문서 전체(2000자)** 기준인데 답변엔 **snippet(120~200자)만** 들어감. 문서가 rel2여도 snippet에 핵심 근거 없으면 BE3엔 무용 → 천장이 문서 기준의 관대함 탓일 수도.

**결론**:
- 검색 ranking은 천장(실제 실력) → **검색 nDCG를 더 올릴 여지 적음**. nDCG는 의사결정 지표에서 내려놓고 보조로.
- 진짜 개선 여지 = (a) **query 대표성**(운영 사용자 질문은 더 어려움; 현 query는 정제된 민원 원문) (b) **snippet utility** (c) **BE3 답변 생성**.
- 답변 도움 지표 권장: rel2@3, evidence sufficiency(top-5 snippet으로 근거 충분?), 법령/기관/숫자 일치, false-friend(비슷하나 결론 다른 위험).
- **최대 함정**: "검색 rel 포화 = RAG 품질 포화" 착각. BE3는 snippet이 좌우.

**다음(ROI)**: ① 사람 spot-check(50 query×top-5 snippet → 충분/부족/위험) ② snippet 기준 소규모 재평가 ③ near-dup 제거·운영형 query 추가 ④ 형태소 운영 튜닝 ⑤ end-to-end.

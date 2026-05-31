# BE2 검색 평가셋 정비 — 종합 보고 (2026-05)

> 검색(BE2) 평가셋의 **3대 방법론 결함**을 교정하고, 로컬 LLM 3-채점관으로 정답표를 재구축한 작업의 종합 기록. 논문 "평가 방법론" 절에 사용 가능.

## 1. 배경 — 왜 다시 봤나

기존 평가에서 **"reranker가 Dense에 진다"**는 결과가 나와, #263에서 reranker·Hybrid를 Adaptive Router에서 제거했다. 그러나 이 결론이 평가 자체의 artifact일 가능성이 제기되어 진단한 결과, 평가셋에 **3대 결함**을 확인했다.

| # | 결함 | 증상 |
|---|---|---|
| 1 | **풀링 편향** | qrels가 Dense/BM25 top-10 위주로 구축 → reranker가 끌어올린 문서의 24%가 미판정→오답(rel=0) 처리 |
| 2 | **자기참조** | 쿼리가 출처 문서에서 파생, 그 문서가 95% rel=2 → "쌍둥이 찾기"라 RR≈1.0 (현실과 괴리) |
| 3 | **채점 신뢰도** | 라벨 검증이 0~3 옛 척도·옛 50쿼리에만 수행, 신규 풀 미검증 |

## 2. 방법 — 3축 교정

**Pillar 1. 풀링 편향 제거 (공정 풀)**
각 쿼리에 대해 `Dense top-50 ∪ BM25 top-50` 합집합을 구성, 미판정 쌍 **5,508건**을 추가 판정. BM25가 **2,450건(44%)을 단독 발굴**(Dense가 top-50에서도 못 본 문서) → 다중 검색기 풀링의 효과 입증.
→ 산출: `qrels_pooled.tsv`

**Pillar 2. 자기참조 제거 (현실적 평가)**
각 쿼리의 출처 문서(CASE-source_id)가 코퍼스에 없는 것처럼 취급 — 검색 결과·qrels 양쪽에서 제외. "쌍둥이 찾기"가 아닌 "다른 유용한 사례 찾기"를 측정.
→ 산출: `eval_noself.py`

**Pillar 3. 채점 신뢰도 (3-채점관 median)**
LLM 채점관 3개의 **중앙값(median)**으로 라벨 결정. 약한 모델 ax4(24% 기권·87% 0점)를 폐기하고 RTX 4070(12GB)에 맞는 **Qwen2.5-14B**로 교체.

| 채점관 | 출신 | 비고 |
|---|---|---|
| EXAONE 3.5 7.8B | LG | 한국어 특화 |
| Gemma 3 12B | Google | 다국어 |
| Qwen2.5 14B | Alibaba | 지시준수·추론 강함 (ax4 대체) |

- 척도: 0~2 graded relevance (`docs/60_specs/retrieval_relevance_definition.md`)
- 집계: median(3), 동점 시 floor → exaone "거부권" 문제 해소
- 인프라: Tailscale로 Windows 데스크톱(RTX 4070) Ollama GPU에서 채점
→ 산출: `qrels_pooled_3judge.tsv` (canonical), `fair_pool_3judge_report.json`

## 3. 결과

### 3.1 풀링 편향 제거 효과 (그림 1)
미판정율과 Dense−Reranker 격차가 급감 → "reranker 열세"의 상당 부분이 artifact였음.

| | 풀링 전 | 풀링 후 |
|---|---|---|
| reranker top-10 미판정율 | 24.1% | **0.1%** |
| Dense−Reranker nDCG@10 격차 | +0.092 | **+0.041** |
| Dense−Reranker AP@10 격차 | +0.109 | **+0.038** |

→ 겉보기 격차의 **35~65%가 풀링 편향 artifact**.

### 3.2 자기참조 제거 효과 (그림 2)
쌍둥이 제거 시 모든 지표 급락 → 기존 점수가 자기참조로 과대평가됐음.

| 지표 | WITH-self | NO-self | 비고 |
|---|---|---|---|
| RR@5 (Dense) | 1.000 | **0.864** | "정답 1순위" 능력 |
| nDCG@10 (Dense) | 0.869 | **0.731** | ≈ −0.14 |

### 3.3 최종 시스템 비교 (그림 3, NO-self · 3채점관 median)

| 지표 | Dense | BM25 | Reranker |
|---|---|---|---|
| nDCG@10 | **0.727** | 0.687 | 0.680 |
| AP@10 | **0.256** | 0.232 | 0.223 |
| R@10 | **0.313** | 0.289 | 0.295 |
| RR@5 | **0.864** | 0.816 | 0.825 |

2-채점관↔3-채점관 결과는 **±0.01 이내·순위 동일** → 결론 견고.

### 3.4 채점관 패널 검증 (그림 4)

| 지표 | 3rd=ax4 | 3rd=Qwen2.5-14B |
|---|---|---|
| 기권율 | 24% | **0%** |
| Fleiss κ(패널) | 0.491 | **0.567** |
| Cohen κ gem–3rd | 0.371 | **0.484** |

(참고: 실제 라벨러 exaone–gemma κ = 0.666, 기존 검증값 0.715와 동급)

### 3.5 리랭커 입력 보강 (후속)
리랭커가 후보의 `observation+request`(4요소 중 2개)만 보고 있던 것을, Dense가 임베딩한 **전체 4요소 본문 + 소관 분야(category)·관할(region)**까지 보도록 보강(`_get_text`). BM25·Dense는 불변이라 효과가 리랭커에만 격리된다.

| 지표 (NO-self) | 구 입력 | 보강 입력 | 변화 |
|---|---|---|---|
| nDCG@10 | 0.680 | **0.712** | +0.032 |
| AP@10 | 0.223 | **0.254** | +0.031 |
| RR@5 | 0.825 | **0.849** | +0.024 |

→ 보강 후 **Reranker가 BM25를 추월(2위)하고 Dense와 거의 동률**(AP@10 격차 0.002). 리랭커의 열세는 "입력 빈약"이 원인이었음을 입증. 답변/법령 필드는 코퍼스에 없어 미사용(한계).

## 4. 결론

1. **Dense가 명확한 1위** — 공정·현실·3채점관 어느 조건에서도 전 지표 최고. Dense 채택은 정당.
2. **Reranker는 입력만 제대로 주면 Dense와 대등** — 기본 입력(2요소)에선 BM25와 비슷했으나, 전체 4요소+분야·관할로 보강하니 BM25를 추월하고 Dense에 거의 근접(§3.5). → **#263의 reranker/Hybrid 제거는 부풀려진 증거 + 빈약한 입력 기반이었음**.
3. **자기참조가 점수를 ~15pt 과대평가** (RR 1.0→0.86).

## 5. 한계 및 향후

- **쿼리가 여전히 출처 문서의 구조화 텍스트** — self-doc 제거는 표준적 교정이나, 이상형은 **진짜 held-out 민원**으로 쿼리 교체.
- **사람 검증 부재** — LLM-사람 일치도를 위해 **사람 골드시드 50~100쌍** 라벨 권장.
- **qrels 파일 다수 공존** — `qrels_pooled_3judge.tsv`를 canonical로 동결하고 나머지 아카이브 권장.

## 6. 산출물 · 재현

| 종류 | 경로 |
|---|---|
| Canonical 정답표 | `data/evaluation/v3/qrels_pooled_3judge.tsv` |
| 채점 체크포인트 | `data/evaluation/v3/checkpoints/fair_pool*.json` |
| 평가 리포트 | `reports/retrieval/v3/{reranker_condensed_eval,eval_noself}.json` |
| 그래프 | `reports/retrieval/v3/figures/fig{1..4}_*.png` |

**재현 순서**
```bash
# 1) 공정 풀 구성 (Dense∪BM25 top-50)
python scripts/build_fair_pool_qrels.py
# 2) 채점 (LLM은 Tailscale로 Windows GPU). 2채점관:
python scripts/judge_fair_pool.py --resume
#    3번째 채점관(Qwen) + median 집계:
python scripts/judge_pool_qwen.py --resume
# 3) 평가
QRELS_FILE=qrels_pooled_3judge.tsv python scripts/reranker_condensed_eval.py
QRELS_POOLED_FILE=qrels_pooled_3judge.tsv python scripts/eval_noself.py
# 4) 그래프
python scripts/plot_eval_overhaul.py
```

# RAG 검색 성능 평가 — 졸업작품 친화 lite 플랜

문서 버전: v3.0 (Lite)
이력: v1.0 (2026-05-05, 산업체 수준 초안) → v2.0 (2026-05-21, Two-tier 통합) → **v3.0 (2026-05-21, 졸업작품 친화로 단순화)**
담당: BE2 (검색 / Adaptive RAG 코어)
범위: 한정된 시간 내에 검색 변경의 효과를 "충분히 객관적으로" 비교할 수 있게 하는 최소 평가 체계

> **이 문서의 자세 차이.** v2.0은 산업체 운영 기준의 빡빡한 규약(Kappa, bootstrap CI, nightly CI, 4종 베이스라인 등)을 담았다. v3.0은 그 중 *발표·시연 가치와 직결되는 항목*만 남기고, 검증 비용이 큰 항목은 spot check 수준으로 낮춘다. 더 정밀한 운영이 필요해지면 v2.0의 절차로 언제든 승급할 수 있다.

---

## 0. 배경

사용자가 "답변 초안 생성" 버튼을 누르면 현재 민원과 유사한 과거 민원을 검색해 컨텍스트로 쓰고 답변 초안을 만든다. 검색 변경마다 "정말 좋아졌는지"를 *대략적으로라도* 비교할 수 있는 기준선이 필요하다. 본 문서는 **2주 안에 한 번 만들어 두면 그 뒤로 검색 PR마다 같은 잣대로 비교할 수 있는 최소 평가셋과 메트릭 운영안**을 정의한다.

---

## 1. 핵심 원칙 (Lite 버전)

1. **메트릭 2개만 본다.** Primary `nDCG@5`, Guardrail `Recall@10`. 그 외는 진단용.
2. **통계 검정은 안 한다.** 평균값 비교만 한다. 5%p 이상 차이는 "유의미"로 간주.
3. **라벨링은 작게 하되 깨끗이 한다.** 50 쿼리 × top-10 후보 = 500건만 사람이 본다.
4. **자동화는 수동 실행까지만.** CI는 욕심내지 않는다. 대신 *재현성*(시드, hash)은 챙긴다.
5. **발표에 쓰일 한 장의 표를 만든다.** Baseline 2종 + Ablation 3-mode의 비교표.

---

## 2. 현재 상태 (요약)

### 2.1 이미 있는 것

- `app/evaluation/metrics.py` (Recall, P, MRR, nDCG, AP)
- `app/evaluation/{datasets,slices,reporting}.py`
- [scripts/evaluate_retrieval.py](../../scripts/evaluate_retrieval.py), [scripts/build_aihub_retrieval_eval_set.py](../../scripts/build_aihub_retrieval_eval_set.py)
- `data/evaluation/`: 250 chunk pool, gold50, smoke10, manifest hash

### 2.2 꼭 고쳐야 할 3가지 (퀵윈)

| 항목 | 위치 | 조치 |
|---|---|---|
| Recall 분모 버그 | [run_issue_103.py:166](../../scripts/run_issue_103.py#L166) | 분모 `\|GT\|` → `min(\|GT\|, k)` |
| 시드 미고정 | [run_issue_103.py:140](../../scripts/run_issue_103.py#L140) | `--seed` 인자 추가 + `random.seed`/`numpy.seed` |
| Adaptive 우회 | [run_issue_103.py:266](../../scripts/run_issue_103.py#L266) | `top_k=10` 고정 대신 `RetrievalService.search()` 직접 호출 |

위 3개만 잡아도 평가 신뢰도가 즉시 올라간다.

### 2.3 현재 라벨의 약점 (꼭 해결)

- gold50은 `review_status: auto_candidate_pending_BE1_BE2_human_review`
- per query 정답 1개 (자기 source의 chunk) → **leak** 위험
- → §4에서 multi-positive + leak 방지로 v2 라벨셋 구축

---

## 3. Relevance 정의 (Lite)

### 3.1 3단계 graded relevance

| 등급 | 정의 | 판정 기준 |
|---|---|---|
| **2** | 답변에 그대로 인용 가능 | 같은 쟁점 + 같은 법령/제도 |
| **1** | 답변 일부 근거로 활용 | 같은 카테고리·주제, 쟁점 일부 일치 |
| **0** | 답변에 부적합 | 표면 키워드만 겹침 |

### 3.2 합의 절차 (Lite)

- Cohen's Kappa는 **계산하지 않는다**.
- 대신 BE1/BE2가 5건만 같이 라벨링하고 **모두 일치하면 OK**, 1건 이상 불일치하면 정의 한 줄 보강. (spot agreement)
- 정의서: `docs/60_specs/retrieval_relevance_definition.md` (예시 5건 포함)

---

## 4. Gold 평가셋 v2 구축 (Lite)
re
### 4.1 Pooling (축소판)

1. 평가 쿼리 **50건** (기존 gold50 재사용)
2. 후보 검색기 **2종** 실행: BM25 + BGE-m3
3. 각 쿼리당 **top-10**씩 → 합집합 = 한 쿼리당 약 15건 풀
4. 사람이 0/1/2 라벨링 (**총 ~750건**, 2인이면 1~2일)
5. TREC qrels 포맷(`qid 0 docid relevance`)으로 저장

### 4.2 자동 후보 보강 (사람 부담 절감)

- 같은 `source` + 같은 `consulting_category` → 1점 후보로 자동 추가
- 사람은 등급 매김만

### 4.3 Leak 방지 (필수)

- 쿼리 `source_id` == 후보 `source_id` → **정답에서 제외**
- "자기 자신"이 아닌 "다른 사례 중 유사한 것"만 정답

### 4.4 산출물

- `data/evaluation/v2/{corpus,queries}.jsonl`, `qrels.tsv`, `manifest.json`

> v2.0의 2,000건 라벨링 → v3.0의 ~750건으로 60% 절감.

---

## 5. 메트릭 (Lite)

### 5.1 2개만 본다

| 역할 | 메트릭 | 의도 |
|---|---|---|
| **Primary** | `nDCG@5` | 답변 컨텍스트(K=3~5)에 들어가는 상위 결과 품질 |
| **Guardrail** | `Recall@10` | 결정적 근거를 놓치지 않았는가 |

그 외(MRR@10, MAP@10, P@5, Hit Rate@K)는 `evaluate_retrieval.py`가 어차피 계산하므로 리포트에 같이 나오게만 두고, *의사결정엔 쓰지 않는다*.

### 5.2 채택 규칙 (Lite)

- Primary가 **+0.05 이상** 개선 + Guardrail이 **−0.02 이내** + Latency p95 **≤ 800ms**
- Bootstrap CI / paired bootstrap은 **하지 않는다**. 큰 차이만 본다.

### 5.3 재현성 (필수)

- `--seed` 인자, `random.seed`/`numpy.seed` 고정
- 리포트 메타데이터: `eval_set_hash`, 임베딩 모델 이름, git commit hash

---

## 6. Slice 평가 (Lite, 2축만)

평균만 보면 회귀를 놓친다. 다만 졸업작품 단계에서는 다축을 다 보지 않아도 된다. **2축만** 본다.

| 축 | 버킷 |
|---|---|
| **`route_key`** | `{topic_type}/{complexity_level}` (Adaptive Router 핵심 키 — 발표 효과↑) |
| **복잡도** | high / mid / low |

기관별·카테고리별 slice는 v2.0 산업체 운영 단계에서 추가.

---

## 7. Adaptive Router 평가 (필수 — 프로젝트의 차별점)

이 부분은 *졸업작품의 핵심 셀링 포인트*이므로 줄이지 않는다.

### 7.1 End-to-end 모드 측정

[app/retrieval/service.py](../../app/retrieval/service.py)의 `RetrievalService.search()`를 호출해 라우터가 정한 `top_k`/`retrieval_policy`가 반영된 결과로 메트릭 산출. `scripts/evaluate_retrieval.py`에 `--mode {raw,adaptive}` 인자 추가.

### 7.2 Ablation 3-mode (발표용 1회)

같은 쿼리셋으로 한 번만 측정해 발표 자료에 박는다.

| 모드 | 설명 |
|------|------|
| ① Fixed top_k=5 | 라우팅 비활성 |
| ② Adaptive | 복잡도 기반 top_k 동적 조정 |
| ③ Adaptive + segment merge | 복합 의도 분해 + 결과 병합 |

표 한 장에 nDCG@5 / Recall@10 / p95 latency를 모드별로 적는다.

---

## 8. Latency (Lite)

- **p95만 본다.** p50/p99는 같이 출력되지만 의사결정엔 안 씀.
- 게이트: p95 ≤ **800ms**
- 임베딩/Chroma 분리 측정은 v2.0 단계에서 추가.

---

## 9. 베이스라인 비교 (Lite, 2종만)

발표용 표 한 장에 들어갈 비교군.

| 베이스라인 | 비고 |
|---|---|
| BGE-m3 (현재 운영) | 단일 dense |
| BGE-m3 + BM25 hybrid (RRF) | 본 프로젝트 권장안 |

MiniLM, BM25 단독은 시간 남으면 추가.

---

## 10. End-to-end (답변 초안 품질, Lite)

자동화된 LLM-as-judge는 **하지 않는다**. 대신:

- 답변 **10건**을 BE1/BE2가 직접 눈으로 본다.
- 각 답변에 대해 단일 척도로 표시: **Yes / Partial / No** — "이 답변이 검색된 민원을 제대로 근거로 활용했는가?"
- 결과: Yes 비율을 baseline vs 변경 검색기에서 비교.

산출물: `reports/retrieval/answer_spot_check_{date}.md` (한 페이지)

> v2.0의 Faithfulness/Citation/Pairwise 자동화는 산업체 운영 단계로 미룬다.

---

## 11. 운영 규약 (Lite)

### 11.1 Run 식별자

`run_id = {pipeline_id}_{git_commit_short}_{eval_set_hash_short}`

### 11.2 비교 조건

두 run의 `eval_set_hash`가 다르면 비교 차단(스크립트 사전 검증).

### 11.3 실행

- **수동 실행**만. nightly CI 없음.
- 검색 변경 PR마다 BE2가 `scripts/evaluate_retrieval.py`를 직접 돌려 PR 본문에 결과 표 첨부.
- 발표 직전 1회 Ablation/Baseline 표 갱신.

---

## 12. 산출물 (Lite)

| 산출물 | 경로 | 비고 |
|--------|------|------|
| Relevance 정의서 | `docs/60_specs/retrieval_relevance_definition.md` | 5건 예시 |
| Gold v2 | `data/evaluation/v2/` | ~750건 라벨 |
| 평가 스크립트 보강 | `scripts/evaluate_retrieval.py` | `--mode`, `--seed`, `--baseline` |
| Adaptive Ablation 표 | `reports/retrieval/ablation_3mode.md` | 발표용 |
| Baseline 비교 표 | `reports/retrieval/baseline_2model.md` | 발표용 |
| 답변 spot check | `reports/retrieval/answer_spot_check_{date}.md` | 10건 직접 평가 |

---

## 13. 실행 로드맵 (2주)

| 주차 | 작업 | 산출물 |
|---|---|---|
| **W1** | (1) Recall 분모 보정 + 시드 고정 (퀵윈) ／ (2) Relevance 정의서 + 5건 spot agreement ／ (3) Pool 후보 추출 (BM25+BGE-m3 × top-10) ／ (4) 사람 라벨링 ~750건 | 정의서, `data/evaluation/v2/` |
| **W2** | (5) `--mode adaptive` 추가 ／ (6) Ablation 3-mode 측정 ／ (7) Baseline 2종 측정 ／ (8) 답변 10건 spot check ／ (9) 발표용 표 정리 | Ablation 표, Baseline 표, spot check 리포트 |

---

## 14. 함정 (Lite에서도 주의)

- **Leak 방지(§4.3)는 반드시 지킨다.** 자기 source를 정답으로 두면 메트릭이 거짓말한다.
- **시드 고정(§5.3) 없이는 비교가 의미 없다.** PR 비교의 전제 조건.
- **메트릭 절대값에 집착하지 말 것.** 같은 평가셋에서 변경 전후 추세만 본다.
- **답변 spot check를 빼먹지 말 것.** 검색 메트릭만 보면 답변 품질 회귀를 놓친다.

---

## 15. 산업체 운영 단계 승급 시 (v2.0으로 복귀할 항목)

졸업 후 또는 산업체 운영으로 넘어갈 때 다음을 v2.0 수준으로 복원한다.

- Cohen's Kappa 합의 절차 (현재 spot agreement만)
- Bootstrap CI / paired bootstrap (현재 평균 비교만)
- Pool 2,000건 라벨링 (현재 750건)
- End-to-end LLM-as-judge 자동화 (현재 수동 10건)
- 다축 slice (기관/카테고리 추가)
- 베이스라인 4종 (MiniLM, BM25 단독 추가)
- nightly CI + 다축 회귀 게이트

이때 본 문서의 §3.2, §4.1, §5.2, §6, §9, §10, §11.3을 v2.0 기준으로 되돌리면 된다.

---

## 16. 참고 문서 및 코드

- 기술 스택: [be2_retrieval_tech_stack.md](../00_overview/be2_retrieval_tech_stack.md)
- Week5-6 액션 플랜: [week5_6_adaptive_rag_core_action_plan.md](week5_6_adaptive_rag_core_action_plan.md)
- 평가 스크립트: [scripts/run_issue_103.py](../../scripts/run_issue_103.py), [scripts/evaluate_retrieval.py](../../scripts/evaluate_retrieval.py)
- 평가셋 빌더: [scripts/build_aihub_retrieval_eval_set.py](../../scripts/build_aihub_retrieval_eval_set.py)
- 검색 서비스: [app/retrieval/service.py](../../app/retrieval/service.py)
- 평가 모듈: `app/evaluation/{metrics,datasets,slices,reporting}.py`

---

## 변경 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v1.0 | 2026-05-05 | 최초 작성. Adaptive Router 검색기 단독 평가의 구체 액션 플랜 (6 phase) |
| v2.0 | 2026-05-21 | "답변 초안 생성" 메인 기능 관점의 Two-tier 평가 체계로 확장 (Component + End-to-end). 5주 로드맵. |
| **v3.0** | **2026-05-21** | **졸업작품 친화 lite 버전.** Kappa·bootstrap CI·nightly CI·4종 베이스라인·자동 judge 제거. Pool 2,000→750건, 5주→2주, slice 6축→2축으로 축소. 핵심(Adaptive Router 평가, leak 방지, 시드, Recall 분모 보정, Ablation 3-mode)은 그대로 유지. 산업체 운영 승급 시 v2.0 절차 §15에 명시. |

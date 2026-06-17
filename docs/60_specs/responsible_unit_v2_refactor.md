# responsible_unit v2 리팩토링 핸드오프

> 대상: 이 작업을 이어받는 다른 AI/엔지니어 (사전 맥락 없음 가정).
> 목표: 담당부서 후보(`responsible_unit`) 검색의 **점수 무력화 문제**를 Phase 0 → 1 → 2 순으로 해결.
> 작성 시점 브랜치: `feature/#346-responsible_units`.

---

## 0. 30초 요약

- `responsible_unit`(민원 → 담당부서 후보)은 bge-m3 임베딩 + ChromaDB로 부서 업무(task)를 검색해 부서 단위로 집계한다.
- **문제**: bge-m3 raw cosine 유사도가 **0.5~0.65 좁은 띠에 뭉쳐** 랭킹/신뢰도 신호로 쓸 수 없다. 실제로 **오답이 정답보다 높은 점수**가 나온다(아래 증거). 단일 신뢰도 하한(threshold)으로 정답/오답을 분리하는 것은 **수학적으로 불가능**함이 확인됐다.
- **해결 방향**(이 문서): Phase 0 평가셋 구축 → Phase 1 문서 확장 + 하이브리드(Dense+BM25+RRF) → Phase 2 상대적 신뢰도(마진/합의). Phase 3(크로스 인코더)는 평가 후 결정.
- **이미 한 것**: 보일러플레이트 필터의 도메인 오제거 수정(#346, 마스터 116→118부서/2,114업무), 신뢰도 하한 실험(실패 확인) 후 0.0으로 원복.
- **이번 추가**: Phase 0 평가셋 `data/departments/eval/responsible_unit_eval.jsonl` 100건을 구축하고 baseline을 산출했다. 이어서 Phase 1-A로 `DepartmentAssigner.build_index()`의 임베딩 문서를 확장했고, after 평가에서 Recall@3 0.5579→0.6947, MRR@3 0.4632→0.6000으로 개선됐다. Phase 1-B로 Dense+BM25+RRF 융합도 구현했지만, 평가지표가 하락해 기본값은 Phase 1-A dense로 유지한다. Phase 2에서는 랭킹 점수와 confidence를 분리해 Recall/MRR은 유지하면서 NONE abstention을 0.8000까지 올렸다. Phase 3 CrossEncoder 리랭커는 평가 후 운영에서 쓰지 않기로 결정했다. BE2 연동을 위해 `responsible_unit[].source`와 Chroma metadata `responsible_units_source` 출처 계약을 추가했다.

---

## 1. 시스템 맥락 (필요한 만큼만)

- 부산시 민원 RAG. BE1 구조화가 민원을 구조화하며 그중 하나가 `responsible_unit`(담당부서 후보 리스트).
- 구조화/담당부서 query prior 입력은 **민원인 원문(title + client_question)**만 사용한다. 검색 인덱싱 본문은 `search_text`를 통해 상담사 답변이 있으면 별도로 보강한다.
- `responsible_unit`은 BE2 검색의 **soft rerank 보조 신호**다. hard filter가 아니며, confidence가 높으면 강하게/낮으면 약하게 반영된다(BE2 측 설계). 즉 **정밀도는 BE2가 다신호로 보정**한다.

### 관련 파일 (현재 구현)
| 파일 | 역할 |
| --- | --- |
| `app/structuring/department_assigner.py` | **핵심**. `DepartmentAssigner`: bge-m3 임베딩 + Chroma(`busan_departments_v1`) 검색 → 부서 집계. 순수 함수 `aggregate_candidates`, `build_query_text`, `extract_key_terms`. |
| `scripts/build_department_master.py` | 마스터 빌더. 부서/업무 정제(블랙리스트 + 보일러플레이트 필터). `is_boilerplate`, `build_master`. |
| `data/departments/busan_departments_master.json` | 정제된 마스터(**118부서 / 2,114업무**). 인덱싱 대상. |
| `app/core/config.py` | 플래그: `ENABLE_RESPONSIBLE_UNIT`(기본 false), `RESPONSIBLE_UNIT_USE_LLM`(false), `RESPONSIBLE_UNIT_USE_HYBRID`(false), `RESPONSIBLE_UNIT_USE_RERANKER`(false), `RESPONSIBLE_UNIT_MIN_CONFIDENCE`(**0.0**, 하한 제거됨). |

### 재사용할 자산 (★ 중요 — 새로 만들지 말 것)
| 자산 | 위치 | 용도 |
| --- | --- | --- |
| **하이브리드 검색 레퍼런스** | `app/retrieval/law_article_store.py` | `tokenize`(단어+한글 char-bigram), `BM25Index`, `rrf_fuse`, `rank_articles`, `LawArticleStore.search`(Dense+BM25 RRF). **Phase 1에서 이 패턴을 부서 검색에 이식**. |
| **도메인 동의어 사전** | `app/structuring/enrichment.py` | `OBJECT_LEXICON`(객체 변이→표준), `LEGAL_REF_LEXICON`(법령 트리거어), `FACILITY_KEYWORDS`. **Phase 1 문서 확장의 동의어 출처**(임의 생성 금지). |

---

## 2. 문제: 증거와 근본 원인

### 2.1 재현 (로컬, `ENABLE_RESPONSIBLE_UNIT` 무관하게 직접 호출)
```python
from app.structuring.department_assigner import get_department_assigner as g
g().assign('3톤 미만 지게차 면허 적성검사 갱신 절차', top_n_units=5, min_confidence=0.0)
```
실제 출력(요약):
```
택시운수과    0.6289   evidence: 법인택시 면허 관리 / "면허"
도로계획과    0.5661   evidence: 황령3터널 관련 업무
트라이포트기획과 0.5372  evidence: 화물자동차운수사업 …
도시혁신균형실  0.5317   evidence: 남부 운전면허시험장 이전 …
미래혁신기획과  0.5317   evidence: 남부 운전면허시험장 이전 …
```
- 정답이어야 할 **건설행정과(건설기계 위임 사무 총괄)는 top-5에도 없음**.
- 지게차 = 건설기계관리법상 건설기계조종사면허인데, "면허/운수" 일반어 매칭이 더 높게 잡힘.

또 다른 질의 `'어린이 공원 안전 문제'`:
```
아동청소년과   0.6448
공원여가정책과  0.5705   ← 사실상 정답인데 낮음
…
```

### 2.2 핵심 모순
- 지게차의 **오답** 택시운수과 = **0.63**
- 공원의 **정답** 공원여가정책과 = **0.57**

→ **오답(0.63) > 정답(0.57)**. 어떤 단일 하한값도 한쪽을 망친다. 0.6으로 자르면 택시(오답) 통과·공원(정답) 폐기. **신뢰도 하한 전략(B)은 이 데이터에선 원천 불가** — 실험으로 확인 후 폐기(`RESPONSIBLE_UNIT_MIN_CONFIDENCE`를 0.0으로 원복).

### 2.3 근본 원인 (5)
1. **레지스터 불일치**: 질의=자연어 민원 문장, 문서=terse 행정 라벨 → bge-m3가 전부 "어중간히 유사"로 평가.
2. **Dense 단독**: 현재 부서 검색은 dense cosine만. (법령 store는 BM25 하이브리드+RRF를 쓰는데 부서엔 미적용.)
3. **일반어 분산**: "면허/안전/관리"가 다수 부서에 퍼져 신호 분산.
4. **신뢰도 = raw cosine**: confidence가 best 코사인값에 직결되어 좁은 띠를 그대로 물려받음.
5. **문서 측 신호 빈곤(키스톤)**: 정답 부서 task에 *지게차·조종사면허·적성검사* 어휘가 없음. → **어떤 랭킹 기법도 텍스트에 없는 신호는 못 만든다.** 문서 보강이 선행돼야 함.

---

## 3. 해결 계획: Phase 0 → 1 → 2

> 설계 원칙: ① 랭킹과 신뢰도를 **분리**한다(코사인 크기를 신뢰도로 쓰지 않는다). ② 문서·질의에 **신호를 주입**한다(기존 사전 재사용). ③ 점수를 **순위 기반**으로 만든다(RRF).

### Phase 0 — 평가셋 구축 (선행 필수)
**왜**: 지금은 정답셋이 없어 어떤 개선도 숫자로 측정 불가. 이게 없으면 Phase 1~2가 전부 추측이 된다.

**할 일**
1. 민원 30~50건을 샘플(가능하면 도메인 다양: 건설기계/건축/도로/공원/환경/복지/교통/위생 등 골고루).
   - 소스: `data/processed/processed_consulting_data.json`의 `title`+`client_question`(민원인 원문).
2. 각 민원에 **정답 부서 1~2개**를 사람이 라벨링. 정답은 반드시 `busan_departments_master.json`에 **실재하는 부서명**으로(없으면 `"NONE"`으로 표기 — 본청에 정답 부서가 없는 케이스를 분리 측정하기 위함. 예: 지게차 조종사면허).
3. 저장: `data/departments/eval/responsible_unit_eval.jsonl`
   ```jsonl
   {"query": "어린이 공원에 깨진 유리가 많아 위험합니다", "gold": ["공원여가정책과"]}
   {"query": "3톤 미만 지게차 면허 적성검사 갱신 절차", "gold": ["NONE"]}   // 본청에 정답 부서 부재
   ```
4. 평가 스크립트 `scripts/eval_responsible_unit.py`:
   - 입력: eval.jsonl. 각 query에 `assign(query, top_n_units=3, min_confidence=0.0)` 호출.
   - 지표: **Recall@3**(gold가 top-3에 있으면 hit), **MRR@3**, 그리고 `gold==["NONE"]` 케이스의 **무답률**(후보가 비거나 신뢰도 낮음 = 좋음).
   - 출력: 전체 지표 + 케이스별 표(현재값을 baseline으로 기록).

**현재 구현 상태**
- 평가 CLI 추가: `python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.seed.jsonl`
- 확정 평가셋 기본 경로: `data/departments/eval/responsible_unit_eval.jsonl`
- 확정 평가셋은 100건이다. 현재 baseline은 total=100, labeled=95, NONE=5, Recall@3=0.5579, MRR@3=0.4632, NONE abstention=0.0000(threshold=0.4)이다.
- Phase 1-A after 평가는 Recall@3=0.6947(+0.1368p), MRR@3=0.6000(+0.1368p), NONE abstention=0.0000(threshold=0.4)이다. 문서 확장은 랭킹을 개선했지만, 무답/신뢰도 분리는 아직 개선하지 못했다.
- Phase 2 after 평가는 Recall@3=0.6947(+0.1368p), MRR@3=0.6000(+0.1368p), NONE abstention=0.8000(threshold=0.4)이다. 랭킹 지표는 Phase 1-A와 동일하게 유지했고, 본청 마스터에 정답 부서가 없는 케이스 5건 중 4건을 낮은 confidence로 분리했다.
- seed 파일은 18건이며 각 row에 `note=seed_requires_human_review`를 남겼다. 이 파일은 smoke/baseline 리허설용이고, 확정 평가셋을 대체하지 않는다.
- 스크립트는 gold 부서명이 `busan_departments_master.json`에 있는지 검증하고, `NONE`은 단독 라벨로만 허용한다.

**완료 기준**: baseline 숫자 확보(현재 Recall@3, MRR, NONE-무답률). 이후 모든 변경은 이 숫자로 before/after 비교.

> ⚠️ Phase 0 없이 Phase 1로 가지 말 것. "좋아 보인다"는 측정이 아니다.

### Phase 1 — 문서 확장 + 하이브리드 검색 (최고 레버리지)
**1-A. 문서 확장 (정답을 "띄우는" 부분)**
- 인덱싱 시 각 task 문서를 `부서명 + task + 도메인 동의어`로 보강.
- 동의어는 **`enrichment.OBJECT_LEXICON` / `LEGAL_REF_LEXICON`** 에서 끌어온다(새 사전 만들지 말 것). 예:
  - task "건설기계 위임 사무 총괄"(건설행정과) → 인덱싱 문서: `"건설행정과 건설기계 위임 사무 총괄 건설기계관리법 지게차 굴착기 기중기 조종사면허 등록"`.
- 구현 위치: `scripts/build_department_master.py`에 확장 필드를 만들거나, `DepartmentAssigner.build_index`의 `docs` 생성부에서 동의어를 합쳐 임베딩. (메타데이터의 표시용 `task`는 원문 유지, 임베딩용 텍스트만 확장)
- **주의**: 확장은 *부서의 실제 도메인*에 한해서만. 모든 부서에 모든 동의어를 뿌리면 다시 노이즈가 된다. task에 트리거어(예: "건설기계")가 있을 때 해당 동의어군만 붙인다.
- **현재 구현 상태**: `app/structuring/department_assigner.py`의 `expand_department_task_text()`가 `OBJECT_LEXICON`, `LEGAL_REF_LEXICON`, `FACILITY_KEYWORDS`를 재사용해 트리거가 맞은 사전군만 붙인다. Chroma metadata의 `task`는 원문을 유지하고, `documents`에만 확장 텍스트를 넣는다.
- **평가 결과**: 재인덱싱 후 100건 평가에서 Recall@3 0.5579→0.6947, MRR@3 0.4632→0.6000으로 올랐다. 자원순환/공원/도로 계열은 크게 개선됐지만, NONE abstention은 0.0000으로 그대로라 Phase 2의 상대적 신뢰도 설계가 여전히 필요하다.

**1-B. Dense + BM25 + RRF (분리도를 올리는 부분)**
- `law_article_store.py`의 `tokenize` / `BM25Index` / `rrf_fuse`를 부서 task 코퍼스에 그대로 적용.
- `DepartmentAssigner.assign` 흐름을 변경:
  1. Dense top-K(예: 30) + BM25 top-K를 각각 구함(둘 다 확장된 문서 텍스트 대상).
  2. `rrf_fuse([dense_ranking, bm25_ranking])`로 task 순위 융합.
  3. 융합 순위를 `aggregate_candidates`에 넘겨 부서 집계.
- 코사인 → **RRF 점수**로 바뀌면 raw cosine의 좁은 띠 문제가 완화된다(순위 기반).
- **현재 구현 상태**: `DepartmentAssigner`가 마스터 JSON에서 `doc_id/department/task/text` 코퍼스를 지연 로딩하고, dense Chroma 결과와 BM25 결과를 `rrf_fuse`로 합친다. BM25는 Phase 1-A의 `expand_department_task_text()` 결과를 대상으로 하며, sparse-only hit도 마스터 metadata로 복원해 후보에 포함한다. `top_k_tasks` 기본값은 Phase 1-A와 같은 20을 유지한다.
- **설계 조정 및 채택 결정**: equal RRF 1차 실측은 Recall@3=0.6211, MRR@3=0.5491로 Phase 1-A보다 낮았다. dense 순위를 두 번 넣는 Dense:BM25=2:1 가중 RRF와 `extract_key_terms()` 기반 BM25 질의 제한도 Recall@3=0.6000, MRR@3=0.5123으로 더 낮았다. 따라서 하이브리드 코드는 `RESPONSIBLE_UNIT_USE_HYBRID=true` opt-in으로 보존하고, 운영 기본값은 검증된 Phase 1-A dense 검색으로 둔다.
- **주의**: RRF 점수는 `rrf_similarity()`로 0~1 범위에 맞춰 `aggregate_candidates()`에 전달하지만, 이는 아직 보정 확률이 아니다. NONE 무답 분리와 신뢰도 보정은 Phase 2에서 계속 다룬다.

**검증**: Phase 0 평가셋으로 Recall@3 / MRR before(현재) vs after. 건설행정과가 지게차 질의 top-3에 드는지 개별 확인.

### Phase 2 — 상대적 신뢰도 (0.63>0.57 역설 해결)
**왜**: 랭킹이 좋아져도 confidence를 raw 점수로 두면 질의 간 비교가 안 된다. 신뢰도를 *상대적*으로 재정의.

- `aggregate_candidates`의 confidence 산식 교체:
  - **마진**: top1과 top2의 격차를 반영. 무관 부서가 평평하게 깔리면(지게차) 마진 작음→낮은 신뢰. 정답군이 뭉치면(공원) 마진 큼→높은 신뢰.
  - **합의(multi-hit)**: 같은 부서가 여러 task로 히트하면 가산(현재 `_MULTIHIT_BONUS` 강화/재설계).
  - **(옵션) softmax 정규화**: top-K 점수에 temperature softmax → 0~1로 보정해 질의 간 비교 가능.
- 이렇게 하면 **신뢰도가 질의 간 비교 가능**해져, 그때 비로소 하한(`RESPONSIBLE_UNIT_MIN_CONFIDENCE`)이 의미를 가진다(Phase 2 이후 재도입 검토).
- **현재 구현 상태**: `aggregate_candidates()`가 부서별 내부 `_rank_score`(best similarity + multi-hit bonus)로 후보 순위를 먼저 정하고, 별도 `_relative_confidences()`에서 top1/top2 마진, multi-hit 합의, evidence term 수, rank/gap decay를 반영해 출력용 `confidence`를 계산한다. `DepartmentAssigner.assign()`은 `_rank_score`, `_hits`, `_evidence_terms`를 제거하고 기존 공개 스키마(`name`, `confidence`, `evidence`)만 반환한다.
- **평가 결과**: Phase 2 after 평가는 Recall@3=0.6947, MRR@3=0.6000으로 Phase 1-A 랭킹 지표를 유지했다. NONE abstention은 threshold=0.4 기준 0.0000→0.8000으로 개선됐다. 다만 eval-035는 top confidence가 0.4000 경계값에 걸려 false positive로 남아 있어, confidence는 여전히 보정 확률이 아니라 soft rerank 강도 신호로만 해석해야 한다.

**검증**: 평가셋에서 `gold==["NONE"]` 케이스의 신뢰도가 정답 존재 케이스보다 *낮게* 나오는지(분리되는지) 확인.

---

## 4. Phase 3 (보류, 평가 후 결정)
- top-K task를 **크로스 인코더 리랭커**(`bge-reranker-v2-m3`)로 재채점. logit은 bi-encoder 코사인보다 훨씬 잘 분리됨.
- ⚠️ **주의**: 이 저장소의 이전 검색평가에서 "리랭커는 오히려 해로움"(민원↔민원 검색) 결론이 있었음(커밋 히스토리 참조). 부서 검색은 다른 태스크라 **Phase 0 평가셋으로 반드시 재검증 후** 채택.
- bge-m3 sparse/ColBERT 멀티벡터는 FlagEmbedding 로딩 + 저장계층 교체가 필요해 후순위(Phase 1으로 대부분 해결 가능).
- **현재 구현 상태**: `DepartmentAssigner.assign(..., use_reranker=True)` 또는 `RESPONSIBLE_UNIT_USE_RERANKER=true`로 CrossEncoder task 리랭킹을 켤 수 있다. 리랭커 입력은 `[민원 질의, 부서명+업무+확장문서]` pair이며, `BAAI/bge-reranker-v2-m3` logit을 `sigmoid_similarity()`로 0~1에 맞춰 기존 `aggregate_candidates()`와 Phase 2 상대 confidence를 그대로 사용한다. 모델 로딩/예측 실패 시 Phase 2 task hit로 안전 폴백한다.
- **평가 결과와 채택 판단**: CPU 환경에서 top_k_tasks=20 전체 평가는 15분 제한을 초과해 완료하지 못했다. 대신 100건 평가셋에서 top_k_tasks=5 조건으로 같은 후보 풀을 비교했을 때, Phase 2 dense는 Recall@3=0.6211, MRR@3=0.5561, NONE abstention=0.8000이고, Phase 3 reranker는 Recall@3=0.6421, MRR@3=0.5737, NONE abstention=0.8000이었다. 리랭커는 같은 작은 후보 풀에서는 소폭 개선됐지만, 운영 기본 Phase 2 top_k_tasks=20 결과(Recall@3=0.6947, MRR@3=0.6000)를 넘지 못하고 CPU 비용도 커서 **기본 채택은 보류**한다.

---

## 5. 정직한 한계 (반드시 인지)
1. **데이터 갭은 랭킹으로 못 고친다**: 정답 부서가 **본청 마스터에 아예 없는** 민원(예: 지게차 조종사면허 = 구청/공단 소관)은 Phase 1~3로도 못 띄운다. 이건 **마스터 데이터 보강**(출처 기반, 임의 생성 금지) 별도 작업. Phase 0에서 이런 케이스를 `"NONE"`으로 분리 라벨해 두면, 시스템이 "무답"을 내는지로 평가할 수 있다.
2. **정답셋 없이는 무의미**: Phase 0를 건너뛰면 개선을 측정할 수 없다.
3. **confidence는 미보정**: 민원→부서 정답셋이 없어 보정 확률이 아니다. 절대 임계값을 신뢰하지 말고 상대 신호로 쓴다.

---

## 6. 운영/환경 메모
- **빌드는 로컬에서**: bge-m3(~2.3GB) + GPU 필요. 샌드박스/CI에선 인덱싱 불가. Chroma 경로 `data/chroma_db`(gitignore, LFS 아님 — 각 환경 1회 빌드).
- Phase 0 seed 리허설:
  ```bash
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.seed.jsonl
  ```
- Phase 0 확정 baseline:
  ```bash
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl --output-json reports/responsible_unit_baseline.json
  ```
- Phase 1-A after 평가:
  ```bash
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl --output-json reports/responsible_unit_phase1a.json
  ```
- Phase 1-B after 평가:
  ```bash
  $env:RESPONSIBLE_UNIT_USE_HYBRID="true"
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl --output-json reports/responsible_unit_phase1b.json
  ```
- Phase 2 after 평가:
  ```bash
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl --output-json reports/responsible_unit_phase2.json
  ```
- Phase 3 리랭커 평가:
  ```bash
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl --top-k-tasks 5 --use-reranker --output-json reports/responsible_unit_phase3_reranker_top5.json
  ```
- 인덱스 재빌드:
  ```bash
  python -c "from app.structuring.department_assigner import get_department_assigner as g; print(g().build_index(rebuild=True))"
  # 기대: {'departments': 118, 'tasks': 2114, 'skipped': 0}
  ```
- 컬렉션 확인: `python -c "import chromadb; print(chromadb.PersistentClient('data/chroma_db').get_collection('busan_departments_v1').count())"` → 2114.
- ⚠️ **마스터/문서 확장을 바꾸면 반드시 `build_index(rebuild=True)`로 재인덱싱**. (과거에 첫 빌드가 영속 안 돼 빈 결과가 나온 사례 있음 — 빌드 후 별도 프로세스에서 count로 영속 확인할 것.)
- 순수 함수(`aggregate_candidates` 등)는 모델 없이 단위 테스트 가능. 테스트: `app/tests/unit/test_department_assigner.py`, `test_department_master_filter.py`.

---

## 7. 작업 체크리스트 (이 순서대로)
- [x] **Phase 0**: `scripts/eval_responsible_unit.py` + `responsible_unit_eval.jsonl` 100건 사람 검수 라벨 + baseline 숫자 기록 완료.
- [x] **Phase 1-A**: 문서 확장(enrichment 사전 재사용, 트리거어 한정) → 재인덱싱 → after 평가 완료. Recall@3 +0.1368p, MRR@3 +0.1368p, NONE abstention 변화 없음.
- [x] **Phase 1-B**: Dense+BM25+RRF(law_article_store 패턴 이식) 구현 및 평가 완료. 지표 하락으로 기본 적용은 보류하고 `RESPONSIBLE_UNIT_USE_HYBRID=true` opt-in으로 남김.
- [x] **Phase 2**: 상대적 신뢰도(마진+합의) 구현 및 평가 완료. Recall/MRR은 Phase 1-A 유지, NONE abstention은 0.8000으로 개선.
- [x] (선택) **Phase 3**: CrossEncoder task 리랭커 opt-in 구현 및 100건 top_k_tasks=5 비교 평가 완료. 소폭 개선은 있으나 Phase 2 top_k_tasks=20 운영 기본보다 낮고 CPU 비용이 커 운영에서는 사용하지 않음.
- [x] 각 Phase 후 `BE2_structuring_handoff.md`의 responsible_unit 절 갱신.

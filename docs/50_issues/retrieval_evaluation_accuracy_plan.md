# RAG 검색 성능 평가 — 정확한 지표 산출 플랜

문서 버전: v1.0
작성 일시: 2026-05-05
범위: BE2 검색 / Adaptive RAG 코어의 검색 품질 측정 방법론

---

## 0. 배경

현재 [scripts/run_issue_103.py](../../scripts/run_issue_103.py)에 Recall@K / MRR@K / Precision@5 / latency 지표와 slice별 집계, gate 통과 기준이 구현돼 있다. 다만 **"정확한"** 지표 산출 관점에서 다음과 같은 구조적 한계가 있어, 이를 보완하는 단계별 플랜을 정리한다.

---

## 1. 현재 평가 파이프라인의 한계 진단

| 영역 | 현재 상태 | 한계 |
|------|----------|------|
| **정답(ground truth) 정의** | `evaluation_set.json`의 `context[].chunk_id` 단일 집합 (이진 관련성) | 부분 관련 사례, 여러 등급의 관련성을 표현 불가 → nDCG 계산 불가 |
| **메트릭 종류** | Recall@5/10, MRR@5/10, Precision@5, 평균 latency | nDCG@K, MAP, Hit Rate@K, p95/p99 latency 부재 |
| **재현성** | `random.sample`이 시드 미고정 ([run_issue_103.py:140](../../scripts/run_issue_103.py#L140)) | 샘플링 시 결과가 매번 다름 |
| **신뢰도** | 단일 평균값만 보고 | 신뢰구간(bootstrap CI) 없어 모델 비교 시 유의성 판단 불가 |
| **Adaptive Router 반영** | top_k=10 고정으로 검색 ([run_issue_103.py:266](../../scripts/run_issue_103.py#L266)) | 라우터가 결정한 `top_k`/`chunk_policy`를 거치지 않은 측정 → 실제 운영 성능과 괴리 |
| **베이스라인** | BGE-m3 단독 측정 | BM25 / 하이브리드 / 임베딩 모델 간 비교 가능한 공통 프레임 부재 |
| **Slice 분석** | scenario_type / risk_level / multi_request / time_sensitivity ([run_issue_103.py:185-198](../../scripts/run_issue_103.py#L185-L198)) | `topic_type` × `complexity_level` 조합(라우팅 키) 슬라이스 부재 |

---

## 2. 정답 데이터셋 품질 확보

`evaluation_set.json`이 결과의 정확도를 좌우하므로 가장 먼저 해결한다.

1. **Graded relevance 도입**
   - `context[].chunk_id` 외에 `relevance: 0|1|2|3` 필드 추가
   - 0 = 무관 / 1 = 약한 관련 / 2 = 관련 / 3 = 정답
2. **이중 라벨링**
   - 동일 쿼리를 2명이 라벨링 후 Cohen's κ ≥ 0.7 확보
   - 불일치는 합의(adjudication) 라벨링
3. **풀링(pooling) 전략**
   - BGE-m3 + BM25 + 다국어 SBERT의 top-20 합집합을 평가 후보로 사용
   - "정답인데 인덱스에 없음" 누락(missing relevant)을 줄임
4. **분포 검증**
   - `topic_type` × `complexity_level` 셀별 최소 30개 쿼리 확보 (slice 통계 신뢰도)
   - 셀별 분포 표를 리포트에 포함

---

## 3. 정확도 / 신뢰도가 보장되는 메트릭 산출

[scripts/run_issue_103.py](../../scripts/run_issue_103.py)를 기반으로 다음을 추가한다.

### 3.1 메트릭 확장

- **nDCG@5/10** — graded relevance를 활용한 순위 품질 지표
- **MAP@10** — 다중 정답 시 평균 정밀도
- **Hit Rate@K** — 최소 1개 정답 포함 여부 (binary)
- **Recall@K 보정** — 분모를 `min(|GT|, k)`로 변경
  - 현재 `_calculate_recall`은 `|GT|`로 나눠 GT가 k보다 크면 상한이 1 미만 → [run_issue_103.py:166](../../scripts/run_issue_103.py#L166) 수정 필요

### 3.2 Latency 분해

- 평균 외 **p50 / p95 / p99**
- **임베딩 시간**과 **Chroma query 시간** 분리 측정
- 콜드/워밍 상태 구분 (첫 N개 쿼리 제외)

### 3.3 부트스트랩 신뢰구간

- 쿼리 단위 결과 리스트를 1000회 resample → **95% CI** 산출
- 모델 A/B 비교 시 **paired bootstrap**으로 차이의 유의성 검정

### 3.4 재현성

- `--seed` 인자 추가, `random.seed` / `numpy.seed` 고정
- 리포트 메타데이터에 다음을 기록:
  - eval_set 파일 해시
  - 임베딩 모델 이름·버전
  - Chroma collection size, persist_dir
  - 실행 환경 (Python, OS, device)

---

## 4. Adaptive RAG 특화 평가

이 프로젝트의 핵심은 라우터이므로, "라우터 + 검색"을 묶어 평가해야 실제 성능이 측정된다.

### 4.1 End-to-end 모드

[app/retrieval/service.py](../../app/retrieval/service.py)의 `RetrievalService.search()`를 직접 호출해 라우터가 정한 `top_k`, `snippet_max_chars`, `retrieval_policy`가 반영된 결과로 메트릭 산출.

### 4.2 Route-key 슬라이스

`_aggregate_slice_metrics`에 다음 차원 추가:
- `route_key` (= `{topic_type}/{complexity_level}`)
- `strategy_id` (예: `topic_welfare_high_v1`)

### 4.3 라우팅 정확도

- 라벨러가 부여한 "기대 route_key"와 실제 라우팅 결과의 일치율
- **Top-1 라우팅 정확도** (별도 지표로 측정)

### 4.4 Ablation 비교

같은 쿼리셋으로 다음 3개 모드를 비교해 라우팅 기여도를 정량화:

| 모드 | 설명 |
|------|------|
| ① Fixed top_k=5 | 라우팅 비활성, 단일 segment |
| ② Adaptive | 복잡도 기반 top_k 동적 조정 |
| ③ Adaptive + segment merge | 복합 의도 분해 + 결과 병합 |

---

## 5. 베이스라인 비교 및 회귀 방지

### 5.1 베이스라인

다음 4종을 같은 evaluation_set으로 평가해 표 한 장에 정리:

- BM25 (`rank_bm25`)
- 다국어 MiniLM (`paraphrase-multilingual-MiniLM-L12-v2`)
- BGE-m3 (`BAAI/bge-m3`) — 현재 운영 모델
- BGE-m3 + BM25 하이브리드 (RRF, Reciprocal Rank Fusion)

### 5.2 회귀 게이트

현재 `Recall@5 ≥ 0.75` 단일 게이트를 다음으로 확장:

| 메트릭 | 임계값 | 현재 |
|--------|--------|------|
| `nDCG@10` | ≥ 0.70 | 미측정 |
| `MRR@10` | ≥ 0.65 | 미측정 |
| `p95 latency` | ≤ 800ms | 평균만 측정 |
| `route_key 정확도` | ≥ 0.85 | 미측정 |

### 5.3 CI 통합

- [scripts/evaluate_retrieval.py](../../scripts/evaluate_retrieval.py)를 nightly로 실행
- 결과를 `reports/retrieval/{date}/`에 시계열로 저장
- 이전 베이스라인 대비 회귀 시 알림

---

## 6. 산출물 (플랜 완료 시)

| 산출물 | 경로 | 설명 |
|--------|------|------|
| Graded eval set | `data/annotations/evaluation_set_v2.json` | 이중 라벨링 + relevance 등급 |
| 평가 공통 모듈 | `app/evaluation/metrics.py` | nDCG / MAP / Hit Rate / bootstrap CI |
| 평가 스크립트 리팩터 | `scripts/evaluate_retrieval.py` | `--mode {raw,adaptive}`, `--seed`, `--baseline` 인자 |
| 비교 리포트 | `reports/retrieval/{date}/{strategy}.json` | 시계열 회귀 추적 |
| 비교 리포트 생성기 | `scripts/generate_retrieval_comparison.py` | 모델/전략 간 표 자동 생성 |

---

## 7. 단계별 우선순위 및 일정 제안

| 단계 | 내용 | 예상 기간 | 우선순위 |
|------|------|-----------|----------|
| **Phase 1** | Recall@K 분모 보정 + 시드 고정 + p95/p99 latency 추가 | 0.5일 | 높음 (퀵윈) |
| **Phase 2** | Adaptive 모드 평가 추가 (`--mode adaptive`) | 1일 | 높음 (발표 효과) |
| **Phase 3** | nDCG / MAP / bootstrap CI 모듈화 | 2일 | 중간 |
| **Phase 4** | Graded relevance 라벨링 + 이중 라벨링 검수 | 5일 | 중간 (인력 필요) |
| **Phase 5** | BM25/하이브리드 베이스라인 비교 | 2일 | 중간 |
| **Phase 6** | 다축 회귀 게이트 + nightly CI | 1일 | 낮음 (장기 운영) |

---

## 8. 참고 문서

- 기술 스택: [be2_retrieval_tech_stack.md](../00_overview/be2_retrieval_tech_stack.md)
- Week5-6 액션 플랜: [week5_6_adaptive_rag_core_action_plan.md](week5_6_adaptive_rag_core_action_plan.md)
- 현재 평가 스크립트: [scripts/run_issue_103.py](../../scripts/run_issue_103.py), [scripts/evaluate_retrieval.py](../../scripts/evaluate_retrieval.py)
- 검색 서비스 구현: [app/retrieval/service.py](../../app/retrieval/service.py)

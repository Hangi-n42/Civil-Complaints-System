# Week 3 BE2 완료 리포트 (2026-03-31)

## 🎯 M2 (W3~W4) 완료 현황

### ✅ 완료 항목

#### Issue #101-2: 메타데이터 정규화
- **Status**: PASS
- **산출물**:
  - `configs/REGION_MAPPING.yaml`: 17개 광역시도, 50+ 별칭 정의
  - `configs/CATEGORY_ENUM.yaml`: 16개 민원 카테고리 + SLA 매핑
- **검증**: 500건 case_type → category 매핑 100% 커버리지

#### Issue #101-3: 임베딩 + 인덱싱 (500 Cases)
- **Status**: PASS
- **상세**:
  - Model: BAAI/bge-m3 (1024-dim, CPU-optimized)
  - Input: 500 evaluation_set cases
  - Output: 1000 chunks (500 cases × 2 chunks/case)
  - Embedding time: 4분 9초 (batch_size=64, CPU)
  - Index success rate: 100% (1000/1000)
  - Collection: `civil_cases_v1` (persistent ChromaDB)
- **참고 수치**: indexed_count=500

#### Issue #101-4/5: ChromaDB 컬렉션 + 보고서
- **Status**: PASS
- **컬렉션 정책**:
  - Collection name: `civil_cases_v1` (고정, 불변)
  - Metadata schema: case_id, chunk_id, source, created_at(Unix timestamp), category, region, benchmark_case_id, query, seed_score
  - created_at 형식: **Unix timestamp (정수)** - ChromaDB 범위 필터 호환성 확보
- **산출물**: `logs/evaluation/week3_indexing_report.json`
  ```json
  {
    "indexed_count": 500,
    "chunk_count": 1000,
    "success_rate": 1.0,
    "gate.passed": true
  }
  ```

#### Issue #102: 필터 검증 (5/5 시나리오)
- **Status**: PASS (모든 시나리오 통과)
- **수정 이력**:
  1. `created_at` ISO 문자열 → Unix 타임스탬프 변환 (Scenario D, E 실패 원인)
  2. Chroma $and 문법 수정: `{$gte, $lte}` → `$and: [{$gte}, {$lte}]`
- **검증 결과**:
  - Scenario A (region single): ✅ 1000/1000 matches
  - Scenario B (category single): ✅ 68/1000 matches
  - Scenario C (region+category AND): ✅ 68/1000 matches
  - Scenario D (date range): ✅ 1000/1000 matches (fixed)
  - Scenario E (complex multi-filter): ✅ 68/1000 matches (fixed)
- **산출물**: `logs/evaluation/week3_filter_validation.json` (status: success, all_passed: true)

#### Issue #103: 검색 성능 메트릭
- **Status**: PASS (초기값 산출 완료)
- **평가 대상**: 500개 쿼리 × evaluation_set
- **메트릭**:
  - Recall@5: **0.205** (20.5%)
  - Recall@10: **0.205**
  - MRR@5: **0.470** (first relevant 평균 순위 ≈ 2.1)
  - Precision@5: **0.094**
  - Avg Latency: **459.20ms** (target: ≤12000ms) ✅
  - Min/Max Latency: 315.42ms ~ 11466.74ms
- **산출물**: `logs/evaluation/week3_retrieval_metrics_full.json`
- **비교 요약**: recall_at_5는 상대적으로 낮고, latency는 상대적으로 우수함

---

## 🔍 Issue #103 Recall 저하 원인 분석

### 진단 결과

#### 1. 데이터 구조 검증 ✅
```
evaluation_set.json 구조:
├── case_id: BENCHX-0001
├── query: "현장 대응 관점에서 최근 3개월 야간 도로 조명 관련 민원..."
└── context: [
    { chunk_id: "CASE-2026-001__chunk-1", score: 0.94, ... },
    { chunk_id: "CASE-2026-019__chunk-2", score: 0.88, ... }
]

ChromaDB 저장 구조:
├── row_id: "BENCHX-0001::CASE-2026-001__chunk-1"
└── metadata:
    ├── chunk_id: "CASE-2026-001__chunk-1"
    ├── case_id: "CASE-2026-001"
    └── benchmark_case_id: "BENCHX-0001"
```
**결론**: chunk_id 일치 확인, 메타데이터 구조 정상 ✅

#### 2. 임베딩/색인 검증 ✅
- 1000개 청크 모두 정상 색인됨
- embedding dimension: 1024 (BAAI/bge-m3 표준)
- 검색 쿼리 embedding: 정상 수행
- Top-10 검색: 정상 반환

#### 3. Recall 저하의 가능한 원인

| 원인 | 검증 | 결론 |
|------|------|------|
| 청크 ID 매칭 실패 | evaluation_set과 ChromaDB의 chunk_id 형식 일치 | ✅ 제외 |
| 데이터 불일치 | 메타데이터 구조 및 값 확인 | ✅ 제외 |
| 임베딩 품질 | 1000개 청크 정상 임베딩, OOM 없음 | ✅ 제외 |
| 쿼리-문서 의미적 거리 | **evaluation_set이 synthetic/자동생성** | ⚠️ 의심 |
| 도메인 특화 부족 | BAAI/bge-m3은 일반 한국어, 민원 도메인 특화 없음 | ⚠️ 가능성 |
| 평가 기준 불일치 | evaluation_set의 context가 "관련성"을 정의하지 않을 가능성 | ⚠️ 조사 필요 |

#### 4. 샘플 쿼리 분석
```
Query: "현장 대응 관점에서 최근 3개월 야간 도로 조명 관련 민원 핵심 이슈를 요약해줘"
Ground truth (evaluation_set):
  - CASE-2026-001__chunk-1 (score: 0.94)
  - CASE-2026-019__chunk-2 (score: 0.88)

Top-5 semantic search 결과에 포함 여부: 23.5% (100개 샘플)
```
**해석**: BGE-m3의 semantic similarity로는 evaluation_set의 context를 충분히 찾기 어려움

---

## 📊 개선 계획 (M3/M4)

### 우선순위 1: 하이브리드 검색 도입 (M3 조건부)
```python
# 전략: BM25 + embedding 결합 → fusion ranking
# Recall@5 예상 개선: 0.205 → 0.50~0.65 (기타 도메인 사례 기준)

# 구현 방안:
# 1. BM25 index 추가 (sparse embedding)
# 2. Hybrid search: normalize(score_bm25) + α * normalize(score_embedding)
# 3. Re-rank fusion (RRF 또는 CombMNZ)
```

### 우선순위 2: 평가 메트릭istics/해석 재검토 (M2 종료 전)
- evaluation_set의 "context" 정의 재확인:
  - "관련성 높은 문서"인가?
  - "생성에 사용된 데이터"인가?
  - "synthetic 변형 문서"인가?
- Week3 평가 기준 재조정 필요 여부 검토

### 우선순위 3: 모델 후보 벤치마크 (M2 내 조건부)
- `candidate_ax4_light`: 후보 모델 테스트
- 다른 embedding 모델 비교 (인자: 차원수, 한국어 최적화도, 지연시간)

### 우선순위 4: 쿼리 재작성 / 프롬프트 최적화 (M3~M4)
- query 정규화 (길이, 도메인 특화 용어)
- prompt 기반 query expansion

---

## 📁 주간 산출물 체크리스트

### 코드/스크립트
- [x] `scripts/run_issue_101_3.py`: 임베딩 + 인덱싱 runner (341 lines)
- [x] `scripts/run_issue_102.py`: 필터 검증 runner (242 lines)
- [x] `scripts/run_issue_103.py`: 검색 성능 평가 runner (364 lines)
- [x] `scripts/build_index.py`: 통합 인덱싱 파이프라인 (subprocess 통합)

### 데이터/리포트
- [x] `logs/evaluation/week3_indexing_report.json` (Issue #101-5)
- [x] `logs/evaluation/week3_filter_validation.json` (Issue #102)
- [x] `logs/evaluation/week3_retrieval_metrics_full.json` (Issue #103)
- [x] `configs/REGION_MAPPING.yaml` (Issue #101-2)
- [x] `configs/CATEGORY_ENUM.yaml` (Issue #101-2)

### 문제 해결
- [x] #101-3 Duplicate ID 문제: row_id format 변경 (`{case_id}::{chunk_id}`)
- [x] #101-3 Invalid success_rate: indexed_count (cases) vs chunk_count 분리
- [x] #102 complex filter 실패: created_at Unix timestamp 변환 + $and 문법 수정
- [x] #103 recall 저하 원인: 분석 완료, 개선 계획 수립

---

## 🚀 다음 주 계획 (M2 종료)

### 즉시 실행 (화~목)
1. **평가 기준 재검토**: evaluation_set의 context 정의 확인
2. **후보 모델 벤치마크**: `candidate_ax4_light` 성능 평가
3. **통합 리포트**: 주간 완료 및 개선 계획 공유

### 조건부 실행 (목~금)
1. **하이브리드 검색 PoC**: BM25 + embedding 프로토타입
2. **쿼리-문서 일치도 분석**: 샘플 쿼리 손수 검토

### M2 완료 기준 재정의
| 항목 | 원래 기준 | 현재 상태 | 평가 |
|------|---------|---------|------|
| 500건 인덱싱 | ✅ 100% | ✅ 완료 | PASS |
| 필터 안정화 | ✅ 2종 | ✅ 5개 시나리오 | PASS |
| 검색 포맷 | Week3 계약 | ✅ 일치 | PASS |
| Recall@5 산출 | ✅ 초기값 | ✅ 0.205 | PASS* |
| 개선 계획 | 필수 | ✅ 정의 | PASS* |

*note: Recall 절대값은 낮지만, 평가 메트릭 재검토 후 베이스라인 재조정 가능

---

## 💡 기술 결론

### 현재 Weekly Baseline (확정)
```json
{
  "embedding_model": "BAAI/bge-m3",
  "vector_dim": 1024,
  "collection": "civil_cases_v1",
  "indexing_rate": "100%",
  "filters_passed": "5/5",
  "recall_at_5_initial": 0.205,
  "avg_latency_ms": 459.20,
  "metadata_schema_version": "week3",
  "created_at_format": "unix_timestamp"
}
```

### 다음 주 재검토 항목
1. evaluation_set 평가 정의 명확화
2. hybrid search 효과성 검증
3. Recall 목표치 현실화 또는 개선 경로 수립

---

**작성**: 2026-03-31 21:30 KST  
**담당**: BE2 (민건)  
**상태**: M2 진행중, Issue #102 완료, Issue #103 초기값 산출 완료

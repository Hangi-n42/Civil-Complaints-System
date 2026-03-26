# 검색 전략 문서

작성일: 2026-03-27  
목적: Week 3 검색 엔진 구현을 위한 전략 및 설계

---

## 1) 검색 전략 개요

### 1.1 목표
- 자연어 쿼리로 유사 민원 케이스 검색
- Top-K 검색으로 관련도 상위 5~20건 반환
- 메타데이터 필터(지역, 카테고리, 기간)로 검색 범위 제한
- 응답속도 500ms 이내

### 1.2 아키텍처
```
Query Input (자연어)
    ↓
Query Embedding (BGE-m3)
    ↓
Vector Similarity Search (ChromaDB)
    ↓
Metadata Filtering (region, category, date)
    ↓
Rank + Return Top-K
    ↓
SearchResult JSON
```

---

## 2) 검색 모드 2가지

### 2.1 Mode 1: 순수 시맨틱 검색 (기본)
- **쿼리**: "도로에 포트홀이 생겼어요"
- **처리**: 임베딩 → 벡터 유사도 검색
- **장점**: 키워드 없어도 의미 기반 검색
- **사용**: 첫 검색, 탐색적 쿼리

### 2.2 Mode 2: 필터링 결합 검색
- **쿼리**: "서울시 강남구 도로안전" + filters
- **처리**: 임베딩 → 필터 적용 → 벡터 검색
- **장점**: 범위 제한으로 정확도 향상
- **사용**: 재검색, 정확한 민원 찾기

---

## 3) 임베딩 모델 선택

### 3.1 선정 모델: BGE-m3

**이유:**
- 한국어 성능 우수 (mBERT 계열)
- 1024 차원으로 메모리 효율적
- Multi-lingual support (확장성)
- 검증된 민원 데이터 성능

**대안:**
- KoSimCSE: 한국어 특화, 768 차원

### 3.2 임베딩 설정

```yaml
# configs/week3_model_benchmark.yaml
retrieval:
  embedder:
    model: "BAAI/bge-m3"
    dimension: 1024
    pooling: "mean"
    normalize: true
```

---

## 4) 벡터DB 전략: ChromaDB

### 4.1 선정 이유
- 로컬 in-memory DB (인터넷 불필요)
- SQLite 기반 persistence
- 메타데이터 필터링 지원
- Python integration 간편

### 4.2 컬렉션 설계

```
Collection: civil_cases_v1
├── Document: 4요소 병합 텍스트
├── Embedding: 1024-dim vector
├── Metadata:
│   ├── case_id
│   ├── region
│   ├── category
│   ├── created_at
│   └── source
└── ID: case_id (unique)
```

### 4.3 저장소 경로
- 기본: `./data/vectorstore/chromadb/`
- 설정 가능: `configs/week3_model_benchmark.yaml`

---

## 5) 메타데이터 필터 전략

### 5.1 필터 종류

| 필터 | 타입 | 예시 | 검색 방식 |
|-----|------|------|---------|
| `region` | String | "서울시 강남구" | Exact match |
| `category` | String | "도로안전" | Exact match |
| `date_from` | ISO-8601 | "2026-01-01" | Range query |
| `date_to` | ISO-8601 | "2026-03-31" | Range query |

### 5.2 필터 결합 규칙

- **AND 결합**: 모든 필터 조건 만족해야 함
- **Optional**: 필터가 비어있으면 적용 안 함
- **실패 처리**: 필터 조건 만족하는 결과 0건이어도 에러 아님

### 5.3 ChromaDB 필터 구문

```python
# 지역 필터만
where = {"region": {"$eq": "서울시 강남구"}}

# 지역 + 기간
where = {
    "$and": [
        {"region": {"$eq": "서울시 강남구"}},
        {"created_at": {"$gte": "2026-01-01"}},
        {"created_at": {"$lte": "2026-03-31"}}
    ]
}
```

---

## 6) 청킹 전략

### 6.1 기본 청크 단위
- **방식**: 전체 케이스 = 1개 청크 (분할 없음)
- **이유**: 민원 텍스트 길이 평균 200~500자로 작음
- **장점**: 단순성, 빠른 검색

### 6.2 향후 고려 (적응형 청킹)
- Week 5-6: 길이 기반 청크 분할
  - Short (<300자): 전체 1청크
  - Medium (300~800자): 2~3청크로 분할
  - Long (>800자): 4청크 이상

---

## 7) 검색 성능 목표 및 측정

### 7.1 KPI

| 지표 | 목표 | 측정 방법 |
|-----|------|---------|
| Recall@5 | ≥ 75% | Top-5 결과 중 관련 민원 비율 |
| MRR@5 | ≥ 0.70 | Reciprocal rank 평균 |
| 응답시간 | ≤ 500ms | 벡터 검색 + 필터링 총 시간 |
| 처리량 | ≥ 100 QPS | 초당 질의 수 |

### 7.2 평가셋
- 총 500개 테스트 케이스
- 난이도: Easy(40%), Medium(40%), Hard(20%)
- 카테고리 균형: 도로/건설/상수도/가로등 균등 분배

### 7.3 평가 스크립트
```bash
python scripts/evaluate_retrieval.py \
  --queries docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --expected_results logs/evaluation/week3/ground_truth.json \
  --output logs/evaluation/week3/retrieval_metrics.json
```

---

## 8) 검색 쿼리 최적화

### 8.1 쿼리 전처리
- 특수문자 제거
- 공백 정규화
- 최대 길이 1000자 제한

### 8.2 재검색 전략
- 1차 검색 결과 0건 → 쿼리 축약 후 재검색
- 예: "포트홀로 인한 도로 훼손 신고 방법" → "도로 포트홀"

---

## 9) Week 3 검색 구현 체크리스트

- [ ] BGE-m3 모델 다운로드
- [ ] ChromaDB 500건 인덱싱 완료
- [ ] 지역/카테고리 검색 테스트
- [ ] 기간 필터 검색 테스트
- [ ] 응답시간 측정 (<500ms 목표)
- [ ] 평가셋 500건 준비 완료
- [ ] Recall@K 측정 완료
- [ ] 검색 성능 리포트 작성

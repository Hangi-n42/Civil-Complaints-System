# Week 3 BE2 인터페이스 문서

문서 버전: v1.0-week3-draft  
작성일: 2026-03-27  
책임: BE2  
협업: BE1, BE3, FE

---

## 1) 책임 범위

Week 3에서 BE2는 **인덱싱 엔진 구현** 및 **검색 엔진 안정화**를 담당한다.

### 1.1 주요 작업
1. `app/retrieval/service.py` 인덱싱/검색/필터 구현 고도화
2. ChromaDB 컬렉션 전략 고정 (컬렉션명, 메타데이터 스키마)
3. 메타데이터 필터 매핑 및 안정성 검증
4. 후보 1(`skt/A.X-4.0-Light`) 벤치마크 실행 및 결과 정리
5. 검색 성능 측정 (응답시간, 정확도)

---

## 2) 입력 계약

### 2.1 IndexRequest (FE/BE1 → BE2)

참고: `week3_common_interface.md#2) IndexRequest 계약`

```json
{
  "request_id": "IDX-2026-000001",
  "action": "bulk",
  "cases": [...],
  "collection_name": "civil_cases_v1"
}
```

### 2.2 SearchRequest (FE → BE2)

참고: `week3_common_interface.md#3) SearchRequest 계약`

```json
{
  "request_id": "SRCH-2026-000001",
  "query": "포트홀 안전",
  "top_k": 5,
  "filters": {
    "region": "서울시 강남구",
    "category": "도로안전"
  }
}
```

---

## 3) 출력 계약

### 3.1 SearchResult (BE2 → FE)

참고: `week3_common_interface.md#4) SearchResult 계약`

```json
{
  "request_id": "SRCH-2026-000001",
  "query": "포트홀 안전",
  "success": true,
  "results": [
    {
      "rank": 1,
      "case_id": "CASE-2026-000001",
      "similarity_score": 0.87,
      "content": {...},
      "metadata": {...}
    }
  ],
  "total_found": 125,
  "elapsed_ms": 342
}
```

---

## 4) ChromaDB 컬렉션 전략

### 4.1 컬렉션 설정

```yaml
# configs/week3_model_benchmark.yaml
retrieval:
  vectorstore:
    type: "chromadb"
    collection_name: "civil_cases_v1"
    embedding_model: "BAAI/bge-m3"
    similarity_metric: "cosine"
    distance_threshold: 0.3
```

### 4.2 컬렉션 메타스키마

각 document 저장 시 ChromaDB metadata 필드:

```json
{
  "case_id": "CASE-2026-000001",
  "source": "aihub_71852",
  "region": "서울시 강남구",
  "category": "도로안전",
  "created_at": "2026-03-05T10:15:00+09:00"
}
```

### 4.3 메타데이터 필터링 규칙
- `region`: exact matching 또는 prefix matching 지원
- `category`: exact matching
- `created_at`: range query (date_from ~ date_to)
- 필터 미지정: 제약 없음

---

## 5) 인덱싱 고도화

### 5.1 인덱싱 로직 (`app/retrieval/service.py`)

```python
def index_cases(index_request: IndexRequest) -> IndexResponse:
    """
    구조화된 케이스를 벡터DB에 저장.
    
    Args:
        index_request: IndexRequest 객체
        
    Returns:
        IndexResponse: 인덱싱 결과 및 통계
    """
    collection = self.get_or_create_collection(
        index_request.collection_name
    )
    
    indexed_count = 0
    failed_count = 0
    errors = []
    
    for case in index_request.cases:
        try:
            # 4요소 병합 텍스트 생성
            combined_text = self._merge_structured_text(case.structured)
            
            # 임베딩
            embedding = self.embedder.embed(combined_text)
            
            # 메타데이터 추출
            metadata = self._extract_metadata(case.metadata)
            
            # ChromaDB에 저장
            collection.add(
                ids=[case.case_id],
                embeddings=[embedding],
                documents=[combined_text],
                metadatas=[metadata]
            )
            indexed_count += 1
            
        except Exception as e:
            failed_count += 1
            errors.append({
                "case_id": case.case_id,
                "error": str(e)
            })
    
    return IndexResponse(
        request_id=index_request.request_id,
        indexed_count=indexed_count,
        failed_count=failed_count,
        errors=errors,
        collection_name=index_request.collection_name
    )
```

### 5.2 검색 로직 (`app/retrieval/service.py`)

```python
def search(search_request: SearchRequest) -> SearchResult:
    """
    자연어 쿼리로 유사 케이스 검색.
    
    Args:
        search_request: SearchRequest 객체
        
    Returns:
        SearchResult: 검색 결과
    """
    collection = self.get_collection(search_request.collection_name)
    
    # 쿼리 임베딩
    query_embedding = self.embedder.embed(search_request.query)
    
    # 필터 구성
    where_filter = self._build_where_filter(search_request.filters)
    
    # 검색 실행
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=search_request.top_k,
        where=where_filter
    )
    
    # 결과 포맷팅
    return SearchResult(
        request_id=search_request.request_id,
        results=self._format_results(results),
        total_found=len(results['ids'][0]) if results['ids'] else 0
    )
```

---

## 6) 메타필터 검증

### 6.1 필터 지원 종류

| 필터명 | 타입 | 예시 | 검증 규칙 |
|-------|------|------|---------|
| `region` | string | "서울시 강남구" | 미리 정의된 지역 목록 기준 |
| `category` | string | "도로안전" | 미리 정의된 카테고리 목록 기준 |
| `date_from` | ISO-8601 | "2026-01-01" | date_to보다 이전이어야 함 |
| `date_to` | ISO-8601 | "2026-03-31" | date_from보다 이후이어야 함 |

정책:
- 필터 미지정은 정상 검색(200) 처리
- 필터 값이 유효하나 매칭 없음은 `200 + results=[]` 처리
- 필터 형식/값 오류는 `400 FILTER_INVALID` 반환

### 6.2 필터 검증 함수

```python
def validate_filters(filters: dict) -> Tuple[bool, List[str]]:
    """필터 유효성 검증."""
    errors = []
    
    if "region" in filters:
        if filters["region"] not in VALID_REGIONS:
            errors.append(f"Invalid region: {filters['region']}")
    
    if "category" in filters:
        if filters["category"] not in VALID_CATEGORIES:
            errors.append(f"Invalid category: {filters['category']}")
    
    if "date_from" in filters and "date_to" in filters:
        if filters["date_from"] >= filters["date_to"]:
            errors.append("date_from must be before date_to")
    
    return len(errors) == 0, errors
```

---

## 7) 임베딩 모델

### 7.1 선택 사항
- **우선**: BGE-m3 (`BAAI/bge-m3`)
- **대안**: KoSimCSE (필요시)

### 7.2 임베딩 차원
- BGE-m3: 1024 차원

### 7.3 임베딩 실행

```python
class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = SentenceTransformer(model_name)
    
    def embed(self, text: str) -> List[float]:
        """텍스트를 임베딩 벡터로 변환."""
        embedding = self.model.encode(text)
        return embedding.tolist()
```

---

## 8) 검색 성능 측정

### 8.1 측정 지표

| 지표 | 단위 | 목표치 |
|-----|------|-------|
| Recall@5 | % | ≥ 75% |
| MRR@5 | - | ≥ 0.70 |
| 조회 응답시간 | ms | ≤ 500 |
| 인덱싱 처리량 | case/sec | ≥ 100 |

### 8.2 측정 스크립트

```bash
python scripts/evaluate_retrieval.py \
  --config configs/week3_model_benchmark.yaml \
  --test_queries docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --output logs/evaluation/week3/retrieval_metrics.json
```

---

## 9) 벤치마크: 후보 1 (`skt/A.X-4.0-Light`)

### 9.1 벤치마크 대상
- 모델명: `skt/A.X-4.0-Light`
- Hugging Face 경로: `skt/A.X-4.0-Light`
- 로컬 Ollama 태그: `ax4-light:latest` (설치 후)

### 9.2 실행 명령

```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_ax4_light
```

### 9.3 결과 수집
- 응답 시간
- JSON 파싱 성공률
- 샘플 출력값

---

## 10) Week 3 BE2 체크리스트

- [ ] 임베딩 모델 다운로드 및 테스트
- [ ] ChromaDB 500건 인덱싱 성공
- [ ] 메타필터 2종 이상 안정 동작
- [ ] 검색 기본 쿼리 테스트 완료
- [ ] 성능 측정 스크립트 완성
- [ ] 후보 1 벤치마크 완료
- [ ] 검색 성능 리포트 작성

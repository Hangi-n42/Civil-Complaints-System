# 인덱싱 계획 문서

작성일: 2026-03-27  
목적: Week 3 인덱싱 구현 상세 계획

---

## 1) 인덱싱 목표

- 500+ 개의 구조화된 민원 케이스를 벡터 임베딩으로 변환
- ChromaDB에 저장하여 빠른 시맨틱 검색 지원
- 메타데이터 기반 필터링 가능
- 인덱싱 처리 시간 최소화 (<5분/500건)

---

## 2) 인덱싱 파이프라인

### 2.1 End-to-End 흐름

```
StructuredCivilCase (BE1)
    ↓
[Step 1] 데이터 유효성 검증
    ↓
[Step 2] 텍스트 병합 (4요소 → 1개 텍스트)
    ↓
[Step 3] 임베딩 생성
    ↓
[Step 4] 메타데이터 추출
    ↓
[Step 5] ChromaDB 저장
    ↓
IndexResponse (성공/실패 통계)
```

### 2.2 각 Step 상세

#### Step 1: 유효성 검증
```python
def validate_case(case: StructuredCivilCase) -> Tuple[bool, List[str]]:
    errors = []
    
    if not case.case_id:
        errors.append("case_id is required")
    
    if not case.structured:
        errors.append("structured object is required")
    
    required_fields = ["observation", "result", "request", "context"]
    for field in required_fields:
        if not case.structured.get(field):
            errors.append(f"structured.{field} is required")
    
    return len(errors) == 0, errors
```

#### Step 2: 텍스트 병합
```python
def merge_structured_text(structured: dict) -> str:
    """4요소를 1개 문장으로 병합."""
    parts = [
        f"상황: {structured.get('observation', '')}",
        f"결과: {structured.get('result', '')}",
        f"요청: {structured.get('request', '')}",
        f"배경: {structured.get('context', '')}"
    ]
    return " ".join(p for p in parts if p)
```

#### Step 3: 임베딩
```python
def embed_text(text: str) -> List[float]:
    """BGE-m3로 임베딩."""
    embedder = SentenceTransformer("BAAI/bge-m3")
    embedding = embedder.encode(text)
    return embedding.tolist()  # 1024-dim vector
```

#### Step 4: 메타데이터 추출
```python
def extract_metadata(case: StructuredCivilCase) -> dict:
    """메타데이터 추출."""
    return {
        "case_id": case.case_id,
        "source": case.source,
        "region": case.metadata.get("region", "unknown"),
        "category": case.metadata.get("consulting_category", "기타"),
        "created_at": case.created_at
    }
```

#### Step 5: ChromaDB 저장
```python
def index_to_chromadb(collection, case_id, embedding, text, metadata):
    """ChromaDB에 저장."""
    collection.add(
        ids=[case_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )
```

---

## 3) 배치 인덱싱 전략

### 3.1 배치 크기 설정
- 기본: 50건/배치
- 메모리 부족 시: 25건으로 축소
- 처리 시간: ~100ms per batch (임베딩 포함)

### 3.2 병렬화 (선택사항)
- ThreadPoolExecutor 사용 (최대 4 threads)
- 임베딩과 저장 병렬화
- 주의: ChromaDB는 thread-safe이므로 직렬화 유지

### 3.3 진행상황 로깅
```python
def index_batch_with_logging(cases, batch_size=50):
    total = len(cases)
    
    for i in range(0, total, batch_size):
        batch = cases[i:i+batch_size]
        try:
            process_batch(batch)
            logger.info(f"Indexed {i+len(batch)}/{total} cases")
        except Exception as e:
            logger.error(f"Batch {i//batch_size} failed: {e}")
```

---

## 4) 컬렉션 초기화 및 관리

### 4.1 컬렉션 생성
```python
def get_or_create_collection(collection_name="civil_cases_v1"):
    """ChromaDB 컬렉션 생성 또는 기존 반환."""
    from chromadb import Client
    
    client = Client()
    
    try:
        collection = client.get_collection(collection_name)
        logger.info(f"Collection {collection_name} already exists. Using existing.")
    except:
        collection = client.create_collection(collection_name)
        logger.info(f"Collection {collection_name} created.")
    
    return collection
```

### 4.2 컬렉션 재설정
```python
def reset_collection(collection_name="civil_cases_v1"):
    """컬렉션 초기화 (재인덱싱용)."""
    client = Client()
    
    try:
        client.delete_collection(collection_name)
        logger.info(f"Collection {collection_name} deleted.")
    except:
        pass
    
    return get_or_create_collection(collection_name)
```

---

## 5) 에러 처리 및 재시도

### 5.1 재시도 전략
- 최대 3회 재시도
- 지수 백오프: 1초 → 2초 → 4초
- 실패 케이스 기록 및 로그

### 5.2 실패 케이스 처리
```python
failed_cases = []

for case in cases:
    retry_count = 0
    while retry_count < 3:
        try:
            index_case(case)
            break
        except Exception as e:
            retry_count += 1
            if retry_count == 3:
                failed_cases.append({
                    "case_id": case.case_id,
                    "error": str(e)
                })
            else:
                time.sleep(2 ** retry_count)

return {
    "indexed_count": len(cases) - len(failed_cases),
    "failed_count": len(failed_cases),
    "failed_cases": failed_cases
}
```

---

## 6) 메모리 및 성능 최적화

### 6.1 메모리 모니터링
```python
import psutil
import gc

def check_memory_usage():
    process = psutil.Process()
    memory_percent = process.memory_percent()
    
    if memory_percent > 80:
        logger.warning(f"High memory usage: {memory_percent}%")
        gc.collect()  # 가비지 컬렉션
```

### 6.2 OOM 대응
- 배치 크기 점진적 감소
- 불필요한 임베딩 캐시 정리
- 최악: 모델 양자화 (4-bit)

---

## 7) 인덱싱 성능 측정

### 7.1 메트릭
- 초당 처리 건수 (cases/sec)
- 임베딩 생성 시간 (ms/case)
- ChromaDB 저장 시간 (ms/case)
- 메모리 피크 (MB)

### 7.2 측정 스크립트
```bash
python scripts/benchmark_indexing.py \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --batch_size 50 \
  --output logs/evaluation/week3/indexing_benchmark.json
```

---

## 8) 증분 인덱싱 전략 (선택사항)

### 8.1 처음 인덱싱
```json
{
  "action": "bulk",
  "cases": [...500 cases...]
}
```

### 8.2 이후 추가 인덱싱
```json
{
  "action": "incremental",
  "cases": [...new cases...]
}
```

### 8.3 구현
```python
if action == "bulk":
    reset_collection()  # 기존 데이터 삭제
elif action == "incremental":
    # 기존 컬렉션 유지
    pass

for case in cases:
    index_case(case)
```

---

## 9) 검증 및 QA

### 9.1 인덱싱 후 검증
```python
def validate_indexed_data(collection, expected_count):
    """인덱싱된 데이터 검증."""
    actual_count = collection.count()
    
    if actual_count != expected_count:
        logger.error(f"Mismatch: expected {expected_count}, got {actual_count}")
        return False
    
    return True
```

### 9.2 샘플 검색 테스트
```python
def test_indexed_data(collection):
    """간단한 검색 테스트."""
    test_query = "포트홀"
    results = collection.query(query_texts=[test_query], n_results=5)
    
    if len(results['ids'][0]) > 0:
        logger.info("Search test passed")
        return True
    else:
        logger.error("Search test failed: no results")
        return False
```

---

## 10) Week 3 인덱싱 체크리스트

- [ ] BGE-m3 모델 다운로드 완료
- [ ] 데이터 유효성 검증 함수 구현
- [ ] 텍스트 병합 로직 검증
- [ ] 임베딩 생성 성능 측정
- [ ] ChromaDB 컬렉션 초기화 테스트
- [ ] 배치 인덱싱 50건 테스트
- [ ] 500건 인덱싱 완료
- [ ] 메모리 사용량 모니터링
- [ ] 검색 테스트 통과
- [ ] 인덱싱 리포트 생성

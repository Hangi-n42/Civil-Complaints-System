# BE2 Issue #92~#103 상세 명세서

**담당**: BE2(민건) - Retrieval 엔지니어  
**상위**: Issue #92 [Week 3][BE2][Main] 인덱싱/검색 안정화 및 retrieval 지표 확보  
**자식**: Issue #101, #102, #103  
**적용 범위**: K3 M2 (W3~W4, 현재 W3 진행중)

---

## 📋 이슈별 상세 액션 아이템

### Issue #101: BGE-m3 + ChromaDB 500건 인덱싱 안정화

**상위 목표**: 500건 케이스를 BGE-m3로 임베딩 후 ChromaDB에 저장, 성공률 >= 99% 달성

#### 작업 분해 (Task Breakdown)

| # | 타스크 | 담당 | 입력 | 출력 | 완료 기준 |
|---|--------|------|------|------|----------|
| 101-1 | 평가셋 500건 준비 및 검증 | BE1 협력 | initial_sample_20.json | evaluation_set.json | 500건 완성, 모든 필드 valid |
| 101-2 | 메타데이터 정규화 규칙 수립 | BE2 단독 | BE1 제시 region/category | REGION_MAPPING.yaml, CATEGORY_ENUM.yaml | 매핑표 100% 커버리지 |
| 101-3 | 임베딩 배치 파이프라인 구현 | BE2 단독 | evaluation_set.json | embeddings (500건) | batch_size 최적화, OOM 안전 |
| 101-4 | ChromaDB 컬렉션 설정 | BE2 단독 | - | civil_cases_v1 컬렉션 생성됨 | 컬렉션 메타스키마 확정 |
| 101-5 | 500건 인덱싱 실행 | BE2 단독 | embeddings + metadatas | ChromaDB 저장 완료 | indexed_count=500, failed=0 |
| 101-6 | 인덱싱 리포트 생성 | BE2 단독 | 실행 로그 | indexing_report.json | logs/evaluation/week3/ 위치 |

#### 101-1번 태스크: 평가셋 500건 준비 및 검증

**책임**: BE1(이택) 주도, BE2(민건) 검증 협력

**입력**: `data/samples/initial_sample_20.json` (초기 샘플 20건)

**실행 명령**:
```bash
python scripts/generate_week3_benchmark_cases_500.py \
  --input data/samples/initial_sample_20.json \
  --output docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --target 500 \
  --seed 42
```

**검증 체크리스트**:
```python
# 필수 필드 (case 별)
assert 'case_id' in case
assert 'source' in case
assert 'created_at' in case
assert 'structured' in case
assert 'observation' in case['structured']
assert 'result' in case['structured']
assert 'request' in case['structured']
assert 'context' in case['structured']

# 필수 메타필드
assert 'metadata' in case
assert 'region' in case['metadata']
assert 'category' in case['metadata']

# 형식 검증
assert isinstance(case['created_at'], str)
assert 'T' in case['created_at']  # ISO-8601
assert '+09:00' in case['created_at']  # KST

# 건수
assert len(evaluation_set) == 500
```

**산출물**: `docs/40_delivery/week3/model_test_assets/evaluation_set.json`

**완료 신호**:
- [ ] 파일 생성 완료
- [ ] 500건 모두 필수 필드 완성
- [ ] 시간대 분포 균등 확인 (시각 그래프 제시)
- [ ] 지역/카테고리 분포 확인 (coverage >= 70%)

---

#### 101-2번 태스크: 메타데이터 정규화 규칙 수립

**책임**: BE2(민건) 단독, BE1과 협의

**입력**: evaluation_set.json에서 추출한 region/category 값들

**산출물 1**: `scripts/normalization_rules.yaml`

```yaml
REGION_MAPPING:
  "강남": "서울시 강남구"
  "강남구": "서울시 강남구"
  "서울 강남구": "서울시 강남구"
  "서울시 강남구": "서울시 강남구"
  "서초": "서울시 서초구"
  # ... 모든 region 값
  
CATEGORY_ENUM:
  - "도로안전"
  - "환경오염"
  - "건축안전"
  - "기타"
  # ... 모든 category 값

DATE_FORMAT:
  input_patterns:
    - "YYYY-MM-DD"
    - "YYYY-MM-DDTHH:MM:SS"
    - "YYYY-MM-DDTHH:MM:SS+09:00"
  output: "ISO-8601 KST (+09:00)"
```

**산출물 2**: `app/retrieval/normalization.py`

```python
from enum import Enum
from typing import Dict

class RegionNormalization:
    MAPPING = {
        "강남": "서울시 강남구",
        # ...
    }
    
    @classmethod
    def normalize(cls, raw_region: str) -> str:
        return cls.MAPPING.get(raw_region.strip(), "Unknown")

class CategoryEnum(str, Enum):
    ROAD_SAFETY = "도로안전"
    ENVIRONMENT = "환경오염"
    BUILDING = "건축안전"
    OTHER = "기타"

def normalize_metadata(raw_metadata: Dict) -> Dict:
    normalized = {}
    normalized['region'] = RegionNormalization.normalize(
        raw_metadata.get('region', '')
    )
    normalized['category'] = CategoryEnum(
        raw_metadata.get('category', 'OTHER')
    ).value
    return normalized
```

**완료 신호**:
- [ ] REGION_MAPPING: 평가셋의 모든 region 값 매핑 (100% coverage)
- [ ] CATEGORY_ENUM: 평가셋의 모든 category 값 정의
- [ ] 정규화 함수: 테스트 케이스 10개 패스 (정규화 전후 비교)

---

#### 101-3번 태스크: 임베딩 배치 파이프라인 구현

**책임**: BE2(민건) 단독

**구현 위치**: `app/retrieval/service.py` 또는 `scripts/build_index.py`

**코드 예시**:

```python
from sentence_transformers import SentenceTransformer
import json
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

class EmbeddingPipeline:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = SentenceTransformer(model_name)
        self.batch_size = 64
        
    def _merge_structured_text(self, structured: Dict) -> str:
        """4요소를 단일 문자열로 병합"""
        parts = [
            structured.get('observation', ''),
            structured.get('result', ''),
            structured.get('request', ''),
            structured.get('context', '')
        ]
        return ' '.join([p for p in parts if p])
    
    def embed_batch(
        self, 
        cases: List[Dict],
        adjust_batch_size: bool = True
    ) -> Tuple[List[List[float]], List[Dict]]:
        """
        배치로 임베딩 생성
        
        Args:
            cases: 케이스 리스트 (각 250토큰 예상)
            adjust_batch_size: OOM 발생 시 배치 크기 자동 조정
            
        Returns:
            (embeddings, errors)
        """
        texts = [
            self._merge_structured_text(case['structured'])
            for case in cases
        ]
        
        embeddings = []
        errors = []
        current_batch_size = self.batch_size
        
        for i in range(0, len(texts), current_batch_size):
            batch_texts = texts[i:i+current_batch_size]
            try:
                batch_embeddings = self.model.encode(
                    batch_texts,
                    normalize_embeddings=True,
                    show_progress_bar=True
                )
                embeddings.extend(batch_embeddings)
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    # OOM 발생: 배치 크기 축소
                    logger.warning(f"OOM detected, reducing batch size: {current_batch_size} -> {current_batch_size//2}")
                    current_batch_size = max(current_batch_size // 2, 8)
                    # 재시도 (단순화, 실제는 recursive 또는 iterator 사용)
                else:
                    errors.append({
                        "batch_index": i // current_batch_size,
                        "error": str(e)
                    })
        
        return embeddings, errors
```

**테스트**:
```bash
python -c "
from app.retrieval.service import EmbeddingPipeline
import json

# 평가셋 로드
with open('docs/40_delivery/week3/model_test_assets/evaluation_set.json') as f:
    cases = json.load(f)

# 임베딩 생성
pipeline = EmbeddingPipeline()
embeddings, errors = pipeline.embed_batch(cases[:10])

print(f'Embedded {len(embeddings)} texts')
print(f'Embedding shape: {len(embeddings[0])}')
print(f'Errors: {len(errors)}')
"
```

**완료 신호**:
- [ ] 500건 임베딩 완료 (< 30분)
- [ ] OOM 안전장치 동작 확인
- [ ] 임베딩 차원: 1024 (BGE-m3 표준)
- [ ] 임베딩 normalize 확인 (L2-norm = 1.0)

---

#### 101-4번 태스크: ChromaDB 컬렉션 설정

**책임**: BE2(민건) 단독

**설정 파일**: `configs/week3_model_benchmark.yaml`

```yaml
retrieval:
  vectorstore:
    type: "chromadb"
    
  collection:
    name: "civil_cases_v1"
    embedding_model: "BAAI/bge-m3"
    embedding_dimension: 1024
    similarity_metric: "cosine"
    distance_threshold: 0.3  # 유사도 >= 0.3만 반환
    
  metadata_schema:
    case_id: "string"
    source: "string"
    region: "string"  # 필터용
    category: "string"  # 필터용
    created_at: "datetime"  # 시간 필터용
```

**초기화 코드**:

```python
import chromadb

client = chromadb.Client()
collection = client.get_or_create_collection(
    name="civil_cases_v1",
    metadata={"hnsw:space": "cosine"}
)

# 메타데이터 스키마 검증 (optional but recommended)
collection._client.reset()  # 기존 데이터 제거 (주의!)
print(f"Collection '{collection.name}' is ready.")
```

**완료 신호**:
- [ ] 컬렉션 생성 완료
- [ ] ChromaDB 클라이언트 정상 연결
- [ ] 메타스키마 문서화 완료

---

#### 101-5번 태스크: 500건 인덱싱 실행

**책임**: BE2(민건) 단독

**실행 흐름**:

```
1. 평가셋 로드 (evaluation_set.json)
2. 메타데이터 정규화 (normalization.py 사용)
3. 임베딩 생성 (EmbeddingPipeline)
4. ChromaDB 저장 (collection.add())
5. 실패 케이스 로깅
6. 재시도 로직 (3회)
7. indexing_report.json 생성
```

**구현 코드** (또는 스크립트):

```python
# scripts/build_index.py 또는 app/retrieval/service.py

def index_500_cases(
    eval_set_path: str,
    output_report_path: str
) -> Dict:
    """500건 인덱싱 및 리포트 생성"""
    
    # 1. 평가셋 로드
    with open(eval_set_path) as f:
        cases = json.load(f)
    
    logger.info(f"Loaded {len(cases)} cases")
    
    # 2-3. 임베딩 생성
    pipeline = EmbeddingPipeline()
    normalized_cases = [
        {**case, 'metadata': normalize_metadata(case.get('metadata', {}))}
        for case in cases
    ]
    embeddings, embed_errors = pipeline.embed_batch(normalized_cases)
    
    # 4. ChromaDB 저장
    client = chromadb.Client(
        path=settings.CHROMA_DB_PATH
    )
    collection = client.get_or_create_collection("civil_cases_v1")
    
    indexed_count = 0
    failed_count = 0
    errors = []
    
    for i, (case, embedding) in enumerate(zip(normalized_cases, embeddings)):
        if embedding is None:  # 임베딩 실패
            failed_count += 1
            errors.append({
                "case_id": case['case_id'],
                "reason": "embedding_failed"
            })
            continue
        
        try:
            # 5-6. 재시도 로직
            for attempt in range(3):
                try:
                    collection.add(
                        ids=[case['case_id']],
                        embeddings=[embedding],
                        documents=[pipeline._merge_structured_text(case['structured'])],
                        metadatas=[case['metadata']]
                    )
                    indexed_count += 1
                    break
                except Exception as e:
                    if attempt == 2:
                        failed_count += 1
                        errors.append({
                            "case_id": case['case_id'],
                            "reason": str(e)
                        })
                        logger.error(f"Failed to index {case['case_id']}: {e}")
                    else:
                        logger.warning(f"Retry {attempt+1} for {case['case_id']}")
                        time.sleep(0.5)
        
        except Exception as e:
            failed_count += 1
            errors.append({
                "case_id": case['case_id'],
                "reason": f"unexpected_error: {str(e)}"
            })
    
    # 7. 리포트 생성
    report = {
        "request_id": f"IDX-W3-{datetime.now().strftime('%Y-%m-%d')}",
        "indexed_count": indexed_count,
        "failed_count": failed_count,
        "total_count": len(cases),
        "success_rate": indexed_count / len(cases),
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    with open(output_report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Indexing complete: {indexed_count}/{len(cases)} success")
    return report
```

**실행 명령**:
```bash
python scripts/build_index.py \
  --eval_set docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --output logs/evaluation/week3/indexing_report.json
```

**완료 신호**:
- [ ] indexed_count >= 495 (99%+)
- [ ] failed_count <= 5
- [ ] 실행 시간 < 30분
- [ ] logs/evaluation/week3/indexing_report.json 생성

---

#### 101-6번 태스크: 인덱싱 리포트 생성

**책임**: 101-5번 태스크의 일부

**산출물 형식** (`logs/evaluation/week3/indexing_report.json`):

```json
{
  "report_id": "IDX-W3-2026-03-31",
  "timestamp": "2026-03-31T20:00:00+09:00",
  "indexing_config": {
    "collection_name": "civil_cases_v1",
    "embedding_model": "BAAI/bge-m3",
    "batch_size": 64,
    "total_cases": 500
  },
  "results": {
    "indexed_count": 500,
    "failed_count": 0,
    "success_rate": 1.0,
    "processing_time_sec": 180,
    "avg_time_per_case_ms": 360
  },
  "failures": [],
  "analysis": {
    "by_reason": {
      "embedding_error": 0,
      "chromadb_error": 0,
      "metadata_error": 0,
      "timeout": 0
    },
    "retry_success": 0,
    "notes": "모든 케이스 1회 시도로 성공"
  }
}
```

**완료 신호**:
- [ ] 리포트 파일 생성
- [ ] indexed_count = 500 (또는 >= 495)
- [ ] 모든 필드 완성

---

### Issue #102: 메타필터(region/category/date) 안정화

**상위 목표**: region, category, date_from/to 필터에 대해 단일/복합 필터 동작 검증 및 안정성 확보

#### 작업 분해

| # | 타스크 | 담당 | 완료 기준 |
|---|--------|------|----------|
| 102-1 | 필터 테스트 시나리오 5가지 정의 | BE2 단독 | 5개 시나리오 문서화 |
| 102-2 | 단일 필터 검증 (region, category, date) | BE2 단독 | Scenario B, C, E pass |
| 102-3 | 복합 필터 검증 (AND 조합) | BE2 단독 | Scenario D pass |
| 102-4 | 필터 오류 처리 검증 | BE2 단독 | 400 FILTER_INVALID |
| 102-5 | 필터 일관성 테스트 (3회 반복) | BE2 단독 | 100% 일관성 |
| 102-6 | 필터 검증 리포트 생성 | BE2 단독 | filter_validation.json |

#### 102-1번: 필터 테스트 시나리오 5가지 정의

**문서 위치**: `docs/40_delivery/week3/be2_filter_test_scenarios.md`

**Scenario A: No Filter (기준선)**
```json
Request: {
  "query": "포트홀",
  "top_k": 5
}

Expected:
  - success: true
  - total_found: 500 (또는 그 이상)
  - 모든 region/category 포함
```

**Scenario B: Single Filter - Region**
```json
Request: {
  "query": "포트홀",
  "filters": { "region": "서울시 강남구" }
}

Expected:
  - success: true
  - results[i].metadata.region == "서울시 강남구" (100%)
  - total_found <= Scenario A.total_found
```

**Scenario C: Single Filter - Category**
```json
Request: {
  "query": "포트홀",
  "filters": { "category": "도로안전" }
}

Expected:
  - success: true
  - results[i].metadata.category == "도로안전" (100%)
```

**Scenario D: Compound Filter - Region AND Category**
```json
Request: {
  "query": "포트홀",
  "filters": {
    "region": "서울시 강남구",
    "category": "도로안전"
  }
}

Expected:
  - success: true
  - results[i].metadata.region == "서울시 강남구" AND category == "도로안전" (100%)
  - total_found(D) <= min(total_found(B), total_found(C))
```

**Scenario E: Time Range Filter**
```json
Request: {
  "query": "포트홀",
  "filters": {
    "date_from": "2026-01-01T00:00:00+09:00",
    "date_to": "2026-03-31T23:59:59+09:00"
  }
}

Expected:
  - success: true
  - date_from <= results[i].metadata.created_at <= date_to (100%)
```

**완료 신호**:
- [ ] 5개 시나리오 모두 문서화
- [ ] 각 시나리오별 기대값 명시

---

#### 102-2번: 단일 필터 검증

**구현**: `scripts/check_chromadb_filters.py` 업데이트

```python
import requests
import json
from typing import Dict, List

class FilterTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def test_scenario_b_region_only(self) -> Dict:
        """Scenario B: region 필터만"""
        response = requests.post(
            f"{self.base_url}/api/v1/search",
            json={
                "query": "포트홀",
                "top_k": 5,
                "filters": {"region": "서울시 강남구"}
            }
        )
        
        data = response.json()
        passed = True
        errors = []
        
        for result in data.get('results', []):
            if result['metadata']['region'] != '서울시 강남구':
                passed = False
                errors.append(f"결과에 다른 region 포함: {result['metadata']['region']}")
        
        return {
            "scenario": "B",
            "passed": passed,
            "expected_count": "> 0",
            "actual_count": len(data.get('results', [])),
            "errors": errors
        }
    
    def test_scenario_c_category_only(self) -> Dict:
        """Scenario C: category 필터만"""
        response = requests.post(
            f"{self.base_url}/api/v1/search",
            json={
                "query": "포트홀",
                "top_k": 5,
                "filters": {"category": "도로안전"}
            }
        )
        
        data = response.json()
        passed = True
        errors = []
        
        for result in data.get('results', []):
            if result['metadata']['category'] != '도로안전':
                passed = False
                errors.append(f"결과에 다른 category 포함: {result['metadata']['category']}")
        
        return {
            "scenario": "C",
            "passed": passed,
            "expected_count": "> 0",
            "actual_count": len(data.get('results', [])),
            "errors": errors
        }
    
    def test_scenario_e_time_range(self) -> Dict:
        """Scenario E: 시간 범위 필터"""
        response = requests.post(
            f"{self.base_url}/api/v1/search",
            json={
                "query": "포트홀",
                "top_k": 5,
                "filters": {
                    "date_from": "2026-01-01T00:00:00+09:00",
                    "date_to": "2026-03-31T23:59:59+09:00"
                }
            }
        )
        
        data = response.json()
        passed = True
        errors = []
        
        date_from = "2026-01-01T00:00:00+09:00"
        date_to = "2026-03-31T23:59:59+09:00"
        
        for result in data.get('results', []):
            created_at = result['metadata']['created_at']
            if not (date_from <= created_at <= date_to):
                passed = False
                errors.append(f"범위 밖 created_at: {created_at}")
        
        return {
            "scenario": "E",
            "passed": passed,
            "expected_count": "> 0",
            "actual_count": len(data.get('results', [])),
            "errors": errors
        }
```

**실행 명령**:
```bash
python scripts/check_chromadb_filters.py \
  --scenarios B C E \
  --query "포트홀" \
  --output logs/evaluation/week3/filter_validation_single.json
```

**완료 신호**:
- [ ] Scenario B passed
- [ ] Scenario C passed
- [ ] Scenario E passed

---

#### 102-3번: 복합 필터 검증 (AND)

**구현**: `scripts/check_chromadb_filters.py`에 추가

```python
def test_scenario_d_compound_and(self) -> Dict:
    """Scenario D: region AND category"""
    # 먼저 각 필터 개별 결과 수집
    region_only = self._search({
        "query": "포트홀",
        "filters": {"region": "서울시 강남구"}
    })
    
    category_only = self._search({
        "query": "포트홀",
        "filters": {"category": "도로안전"}
    })
    
    both_filters = self._search({
        "query": "포트홀",
        "filters": {
            "region": "서울시 강남구",
            "category": "도로안전"
        }
    })
    
    # 논리 검증
    both_count = len(both_filters.get('results', []))
    region_count = len(region_only.get('results', []))
    category_count = len(category_only.get('results', []))
    
    passed = (
        both_count <= region_count and  # AND는 OR보다 작거나 같음
        both_count <= category_count and
        all(
            r['metadata']['region'] == '서울시 강남구' and
            r['metadata']['category'] == '도로안전'
            for r in both_filters['results']
        )
    )
    
    return {
        "scenario": "D",
        "passed": passed,
        "region_only_count": region_count,
        "category_only_count": category_count,
        "both_count": both_count,
        "logic_valid": both_count <= min(region_count, category_count),
        "accuracy": 1.0 if passed else 0.0
    }
```

**완료 신호**:
- [ ] Scenario D passed
- [ ] both_count <= min(region_count, category_count) 만족

---

#### 102-4번: 필터 오류 처리 검증

**테스트**:
```python
def test_invalid_region_filter(self):
    """Invalid region → 400 FILTER_INVALID"""
    response = requests.post(
        "http://localhost:8000/api/v1/search",
        json={
            "query": "포트홀",
            "filters": {"region": "INVALID_REGION_12345"}
        }
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data['error']['code'] == 'FILTER_INVALID'
    assert 'region' in data['error']['message'].lower()
```

**완료 신호**:
- [ ] Invalid region → 400 FILTER_INVALID
- [ ] Invalid category → 400 FILTER_INVALID
- [ ] Invalid date format → 400 FILTER_INVALID

---

#### 102-5번: 필터 일관성 테스트 (3회 반복)

**구현**:
```python
def test_filter_consistency():
    """동일 쿼리/필터 3회 실행 시 일관성 검증"""
    results_set = []
    
    for attempt in range(3):
        response = requests.post(
            "http://localhost:8000/api/v1/search",
            json={
                "query": "포트홀",
                "filters": {"region": "서울시 강남구"},
                "top_k": 5
            }
        )
        results_set.append([r['case_id'] for r in response.json()['results']])
    
    # 모든 결과가 동일한지 확인
    assert results_set[0] == results_set[1] == results_set[2], \
        f"결과 불일치: {results_set}"
    
    return {
        "consistency": 1.0,
        "attempt_1_count": len(results_set[0]),
        "attempt_2_count": len(results_set[1]),
        "attempt_3_count": len(results_set[2]),
        "all_equal": True
    }
```

**완료 신호**:
- [ ] 3회 실행 결과 완전 일치 (case_id 순서까지)

---

#### 102-6번: 필터 검증 리포트 생성

**산출물**: `logs/evaluation/week3/filter_validation.json`

```json
{
  "report_id": "FIL-W3-2026-03-31",
  "timestamp": "2026-03-31T21:00:00+09:00",
  "evaluation_config": {
    "query": "포트홀",
    "top_k": 5,
    "test_sample_size": 500
  },
  "scenarios": {
    "A_no_filter": {
      "passed": true,
      "total_found": 500,
      "errors": []
    },
    "B_region_only": {
      "passed": true,
      "total_found": 45,
      "filter_accuracy": 1.0,
      "errors": []
    },
    "C_category_only": {
      "passed": true,
      "total_found": 120,
      "filter_accuracy": 1.0,
      "errors": []
    },
    "D_region_and_category": {
      "passed": true,
      "total_found": 12,
      "filter_accuracy": 1.0,
      "logic_valid": true,
      "errors": []
    },
    "E_time_range": {
      "passed": true,
      "total_found": 432,
      "date_accuracy": 1.0,
      "errors": []
    }
  },
  "consistency_test": {
    "attempts": 3,
    "all_results_identical": true,
    "consistency_score": 1.0
  },
  "error_handling": {
    "invalid_region_4xx": true,
    "invalid_category_4xx": true,
    "invalid_date_4xx": true
  },
  "overall_passed": true
}
```

**완료 신호**:
- [ ] 7개 필터 관련 테스트 모두 passed=true
- [ ] overall_passed=true

---

### Issue #103: retrieval 지표 측정 및 candidate_ax4_light 테스트

**상위 목표**: 평가셋(500건)에 대해 Recall@5, latency를 측정하고 candidate_ax4_light 모델로 최종 벤치마크 실행

#### 작업 분해

| # | 타스크 | 담당 | 완료 기준 |
|---|--------|------|----------|
| 103-1 | Recall@K 측정 (평가셋 대한 검색 정확도) | BE2 단독 | recall_5 >= 0.75 |
| 103-2 | Latency 측정 (응답 시간 통계) | BE2 단독 | avg <= 12s |
| 103-3 | 필터별 성능 분석 | BE2 단독 | 필터 유무 성능 비교 |
| 103-4 | candidate_ax4_light 벤치마크 실행 | BE2 단독 | benchmark_*.json 생성 |
| 103-5 | 지표 분석 및 개선안 제시 | BE2 단독 | 리포트 작성 |

#### 103-1번: Recall@K 측정

**평가셋 구조** (BE1과 협력):

```json
{
  "evaluation_cases": [
    {
      "case_id": "EVAL-001",
      "query": "포트홀 보수 신청",
      "ground_truth": ["CASE-2026-000001", "CASE-2026-000003", "CASE-2026-000012"],
      "filters": { "region": "서울시" }
    },
    ...
  ]
}
```

**측정 프로세스**:

```python
def calculate_recall_at_k(
    ground_truth: List[str],
    retrieved: List[str],
    k: int = 5
) -> float:
    """
    Recall@K = |retrieved[:k] ∩ ground_truth| / |ground_truth|
    """
    if not ground_truth:
        return 1.0  # 관련 문서가 없으면 perfect score
    
    relevant_retrieved = len(set(retrieved[:k]) & set(ground_truth))
    return relevant_retrieved / len(ground_truth)

def evaluate_retrieval(eval_cases: List[Dict]) -> Dict:
    """전체 평가셋에 대해 Recall@K 측정"""
    recalls_5 = []
    recalls_10 = []
    latencies = []
    
    for case in eval_cases:
        # 검색 실행
        start = time.time()
        results = search(
            query=case['query'],
            filters=case.get('filters'),
            top_k=10
        )
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
        
        # Recall 계산
        retrieved_ids = [r['case_id'] for r in results]
        recall_5 = calculate_recall_at_k(case['ground_truth'], retrieved_ids, k=5)
        recall_10 = calculate_recall_at_k(case['ground_truth'], retrieved_ids, k=10)
        
        recalls_5.append(recall_5)
        recalls_10.append(recall_10)
    
    return {
        "recall_5": sum(recalls_5) / len(recalls_5),
        "recall_10": sum(recalls_10) / len(recalls_10),
        "avg_latency_ms": sum(latencies) / len(latencies),
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)]
    }
```

**완료 신호**:
- [ ] recall_5 >= 0.75
- [ ] recall_10 >= 0.85
- [ ] 측정 건수 = 500 (또는 evaluate_case의 수)

---

#### 103-2번: Latency 측정

**목표**: avg <= 12초, p95 <= 15초

**로깅**:
```python
def log_latency(query: str, filters: Optional[Dict], latency_ms: float):
    """latency 로깅 (나중에 분석용)"""
    logger.info(
        f"Search latency: {latency_ms:.0f}ms, "
        f"query={query}, "
        f"has_filter={filters is not None}"
    )
```

**분석**:
```python
def analyze_latency_by_filter(latencies: Dict[str, List[float]]) -> Dict:
    """필터 유무별 latency 분석"""
    return {
        "no_filter": {
            "avg": statistics.mean(latencies['no_filter']),
            "p95": sorted(latencies['no_filter'])[int(len(latencies['no_filter']) * 0.95)]
        },
        "with_filter": {
            "avg": statistics.mean(latencies['with_filter']),
            "p95": sorted(latencies['with_filter'])[int(len(latencies['with_filter']) * 0.95)]
        }
    }
```

**완료 신호**:
- [ ] avg_latency_ms <= 12000
- [ ] p95_latency_ms <= 15000
- [ ] 필터별 latency 차이 기록

---

#### 103-3번: 필터별 성능 분석

**비교 대상**:
- No filter vs Region only vs Region+Category
- 각 설정별 Recall@5, latency

**산출물**: retrieval_metrics.json의 `by_filter_config` 섹션

```json
{
  "by_filter_config": {
    "no_filter": {
      "recall_5": 0.78,
      "recall_10": 0.85,
      "avg_latency_ms": 280,
      "p95_latency_ms": 380,
      "count": 200
    },
    "region_only": {
      "recall_5": 0.76,
      "recall_10": 0.83,
      "avg_latency_ms": 320,
      "p95_latency_ms": 420,
      "count": 150
    },
    "region_category": {
      "recall_5": 0.74,
      "recall_10": 0.80,
      "avg_latency_ms": 380,
      "p95_latency_ms": 520,
      "count": 150
    }
  }
}
```

**완료 신호**:
- [ ] 3가지 필터 구성 모두 평가 완료
- [ ] 각각 50+ 샘플

---

#### 103-4번: candidate_ax4_light 벤치마크 실행

**모델 정보**:
- 이름: skt/A.X-4.0-Light
- 타입: 한국어 LLM (SKT)
- 용도: Week 3 후보 1번

**벤치마크 프로토콜**: `docs/40_delivery/week3/model_benchmark_protocol.md` 참고

**실행 명령**:
```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_ax4_light \
  --output logs/evaluation/week3/model_benchmark_candidate_ax4_light.json \
  --num_workers 1
```

**프로세스**:
1. 모델 로드 (Ollama)
2. 500건 가각에 대해 질답 생성
3. 응답 파싱 (JSON 검증)
4. 지표 산출 (성공률, latency, citation일치도)

**완료 신호**:
- [ ] 500건 모두 실행 완료
- [ ] json_parse_success_rate >= 0.9
- [ ] model_benchmark_candidate_ax4_light.json 생성

---

#### 103-5번: 지표 분석 및 개선안 제시

**산출물**: `docs/40_delivery/week3/be2_week3_analysis_report.md`

**내용**:
1. Recall@5/10 결과 해석
   - 목표 달성 여부 (>= 0.75)
   - 필터별 성능 차이
   - 낮은 성능 케이스 분석

2. Latency 결과 해석
   - 목표 달성 여부 (<= 12초)
   - 필터 추가 시 오버헤드
   - 병목 분석

3. candidate_ax4_light 평가
   - parse 안정성
   - citation 정확도
   - 다른 모델 대비 비교

4. 개선 액션 아이템
   - 우선순위 (높음/중간/낮음)
   - 예상 효과
   - 구현 난이도

**완료 신호**:
- [ ] 분석 리포트 작성 완료
- [ ] 개선 액션 3개 이상 제시

---

## 📊 최종 산출물 체크리스트

| 산출물 | 경로 | 담당 | 상태 |
|--------|------|------|------|
| indexing_report.json | `logs/evaluation/week3/indexing_report.json` | BE2 | ⏳ |
| filter_validation.json | `logs/evaluation/week3/filter_validation.json` | BE2 | ⏳ |
| retrieval_metrics.json | `logs/evaluation/week3/retrieval_metrics.json` | BE2 | ⏳ |
| model_benchmark_candidate_ax4_light.json | `logs/evaluation/week3/model_benchmark_candidate_ax4_light.json` | BE2 | ⏳ |
| be2_filter_test_scenarios.md | `docs/40_delivery/week3/be2_filter_test_scenarios.md` | BE2 | ⏳ |
| be2_week3_analysis_report.md | `docs/40_delivery/week3/be2_week3_analysis_report.md` | BE2 | ⏳ |

---

## 🎯 성공 기준 최종 확인

### Issue #101 (인덱싱)
- ✅ indexed_count >= 495
- ✅ failed_count <= 5
- ✅ logs/evaluation/week3/indexing_report.json 존재

### Issue #102 (필터)
- ✅ Scenario A~E 모두 passed=true
- ✅ consistency_test.all_results_identical=true
- ✅ error_handling 모두 정상

### Issue #103 (지표)
- ✅ recall_5 >= 0.75
- ✅ avg_latency_ms <= 12000
- ✅ candidate_ax4_light 벤치마크 완료
- ✅ 분석 리포트 작성

---

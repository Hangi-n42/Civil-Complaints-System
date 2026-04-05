# Week 3 BE3 인터페이스 문서

문서 버전: v1.0-week3-draft  
작성일: 2026-03-27  
책임: BE3  
협업: BE1, BE2, FE

---

## 1) 책임 범위

Week 3에서 BE3는 **API 안정화** 및 **LLM 벤치마크 3종 모델 테스트**를 담당한다.

### 1.1 주요 작업
1. `/index`, `/search` API 안정화
2. 응답 시간 로깅 및 에러 핸들링 정리
3. Ollama 기반 모델별 QA 생성 성능 측정
4. 후보 2/3/4(`exaone3.5:7.8b-instruct`, `gemma3:12b`, `phi4-mini:3.8b-instruct`) 벤치마크 실행
5. 통합 리포트 작성

---

## 2) API 입출력 계약

### 2.1 POST /index

**요청**:
```json
{
  "request_id": "IDX-2026-000001",
  "action": "bulk",
  "cases": [...],
  "collection_name": "civil_cases_v1"
}
```

**성공 응답** (202 Accepted):
```json
{
  "success": true,
  "request_id": "IDX-2026-000001",
  "timestamp": "2026-03-27T14:35:22+09:00",
  "data": {
    "indexed_count": 500,
    "failed_count": 0,
    "collection_name": "civil_cases_v1"
  }
}
```

**실패 응답** (400/500):
```json
{
  "success": false,
  "request_id": "IDX-2026-000001",
  "timestamp": "2026-03-27T14:35:22+09:00",
  "error": {
    "code": "INDEX_ERROR",
    "message": "인덱싱 중 오류 발생",
    "retryable": true
  }
}
```

---

### 2.2 POST /search

**요청**:
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

**성공 응답** (200 OK):
```json
{
  "success": true,
  "request_id": "SRCH-2026-000001",
  "timestamp": "2026-03-27T14:35:22+09:00",
  "data": {
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
}
```

정책 예외:
- 필터 미지정: 정상 검색(200)
- 필터 지정값이 유효하나 매칭 없음: `200 + data.results=[]`
- 필터 형식/값 오류: `400 FILTER_INVALID`

---

## 3) API 에러 처리 (Week 2 상속)

### 3.1 표준 에러 응답 구조

```json
{
  "success": false,
  "request_id": "...",
  "timestamp": "2026-03-27T14:35:22+09:00",
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 메시지",
    "retryable": true/false
  }
}
```

### 3.2 Week 3 특화 에러 코드

| 코드 | HTTP | 원인 | Retryable |
|-----|------|------|-----------|
| `INDEX_ERROR` | 500 | 인덱싱 실패 | true |
| `COLLECTION_NOT_FOUND` | 404 | 컬렉션 미존재 | false |
| `SEARCH_TIMEOUT` | 504 | 검색 타임아웃 | true |
| `INVALID_QUERY` | 400 | 쿼리 형식 오류 | false |
| `FILTER_INVALID` | 400 | 필터 형식 오류 | false |

---

## 4) 로깅 및 모니터링

### 4.1 요청/응답 로깅

```python
# app/api/main.py
import time
from app.core.logging import get_logger

logger = get_logger(__name__)

@app.post("/index")
def index_endpoint(request: IndexRequest):
    start_time = time.time()
    request_id = request.request_id
    logger.info(f"[{request_id}] Indexing request received: {len(request.cases)} cases")
    
    try:
        response = retrieval_service.index_cases(request)
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"[{request_id}] Indexing completed in {elapsed_ms:.0f}ms: {response.indexed_count} indexed, {response.failed_count} failed")
        return wrap_response(response)
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"[{request_id}] Indexing failed after {elapsed_ms:.0f}ms: {str(e)}")
        raise
```

### 4.2 성능 로그 포맷

```
[TIMESTAMP] [REQUEST_ID] [LOG_LEVEL] [SERVICE] message
2026-03-27T14:35:22+09:00 [SRCH-2026-000001] INFO retrieval.search Query processed in 342ms, ranked 5 results
```

---

## 5) 모델 벤치마크 (LLM QA 생성 성능)

### 5.1 벤치마크 대상 모델 (BE3 담당)

| # | 모델명 | Hugging Face | Ollama 태그 | 상태 |
|----|--------|--------------|-----------|------|
| 2 | EXAONE 3.5 | `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct` | `exaone3.5:7.8b-instruct` | ⏳ 테스트 예정 |
| 3 | Gemma 3 | `google/gemma-3-12b` | `gemma3:12b` | ⏳ 테스트 예정 |
| 4 | Phi 4 | `microsoft/phi-4-mini` | `phi4-mini:3.8b-instruct` | ⏳ 테스트 예정 |

### 5.2 벤치마크 실행 스크립트

```bash
# 개별 모델 테스트
python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_exaone_3_5_7_8b

python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_gemma3_12b

python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_phi4_mini
```

### 5.3 측정 지표

각 모델별로 다음 메트릭을 수집한다:

```json
{
  "model_name": "exaone3.5:7.8b-instruct",
  "metrics": {
    "avg_response_time_ms": 1200,
    "p95_response_time_ms": 1800,
    "json_parse_success_rate": 0.96,
    "total_tests": 500,
    "successful_tests": 480,
    "failed_tests": 20,
    "timeout_count": 5,
    "parsing_error_count": 15
  }
}
```

### 5.4 타임아웃 설정

- 모델별 최대 응답 시간: **3초** (3000ms)
- 초과 시: timeout 에러로 기록

---

## 6) LLM 모델 설치 확인

### 6.1 Ollama 설치 확인

```bash
# Ollama 모고 설치된 모델 목록 확인
ollama list

# 출력 예시
NAME                      	ID          	SIZE  	MODIFIED
aihub_baseline            	abc123      	7.9GB 	2026-03-20
exaone3.5:7.8b-instruct  	def456      	15GB  	2026-03-25
gemma3:12b                	ghi789      	25GB  	2026-03-25
phi4-mini:3.8b-instruct   	jkl012      	8GB   	2026-03-25
```

### 6.2 모델 미설치 시 자동 처리

```python
def get_installed_models():
    """Ollama에 설치된 모델 목록 반환."""
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True
    )
    return parse_ollama_list(result.stdout)

def check_model_available(model_name: str) -> bool:
    """모델 설치 여부 확인."""
    installed = get_installed_models()
    return model_name in installed

# 벤치마크 실행 중 미설치 모델 체크
if not check_model_available(model_name):
    logger.warning(f"Model {model_name} not installed. Skipping benchmark.")
    # 결과에 "not_installed" 표시
```

---

## 7) 성능 최적화 및 OOM 대응

### 7.1 메모리 사용 모니터링

```python
import psutil

def monitor_memory():
    """메모리 사용량 모니터링."""
    process = psutil.Process()
    mem_info = process.memory_info()
    logger.info(f"Memory usage: {mem_info.rss / 1024 / 1024:.0f}MB")
```

### 7.2 OOM 발생 시 대응

1. **1단계**: 컨텍스트 축소 (검색 결과 Top-K 감소)
2. **2단계**: 배치 크기 축소 (인덱싱 배치 50 → 25)
3. **3단계**: 모델 다운스케일 (양자화 적용)

---

## 8) 통합 벤치마크 리포트

### 8.1 리포트 생성 스크립트

```bash
python scripts/generate_week3_benchmark_report.py \
  --results logs/evaluation/week3/ \
  --output logs/evaluation/week3/model_benchmark_report_final.json
```

### 8.2 리포트 포함 사항

```json
{
  "report_id": "RPT-2026-WEEK3-001",
  "generated_at": "2026-03-31T18:00:00+09:00",
  "models": [
    {
      "model_name": "aihub_baseline",
      "metrics": {...}
    },
    {
      "model_name": "exaone3.5:7.8b-instruct",
      "metrics": {...}
    },
    {
      "model_name": "gemma3:12b",
      "metrics": {...}
    },
    {
      "model_name": "phi4-mini:3.8b-instruct",
      "metrics": {...}
    }
  ],
  "comparison": {
    "fastest_model": "...",
    "most_stable_model": "...",
    "recommendation": "..."
  }
}
```

---

## 9) Week 3 BE3 체크리스트

- [ ] Ollama 3개 모델 설치 완료
- [ ] 각 모델별 QA 생성 테스트
- [ ] 성능 측정 스크립트 완성
- [ ] 500건 평가셋 병렬 테스트 (각 20~30분)
- [ ] 메트릭 수집 및 정리
- [ ] 모델별 리포트 생성
- [ ] 최종 통합 리포트 작성


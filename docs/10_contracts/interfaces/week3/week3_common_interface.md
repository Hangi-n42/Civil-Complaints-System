# Week 3 공통 인터페이스 규약

문서 버전: v1.0-week3-draft  
작성일: 2026-03-27  
적용 파트: FE, BE1, BE2, BE3  
상속: Week 2 공통 규칙 (`10_contracts/interfaces/week2/week2_common_interface.md`)

---

## 1) Week 3 추가 규칙

### 1.1 인덱싱/검색 공통 원칙
- 모든 인덱싱/검색 요청은 `request_id`로 추적한다.
- 검색 결과의 `chunk_id`와 `case_id`는 벡터DB에 저장된 metadata와 일치해야 한다.
- 모든 필터는 **optional**이며, 필터 미지정 시 전체 인덱스 대상으로 검색한다.
- 필터 형식/값 오류(예: 잘못된 지역 코드)는 `400 FILTER_INVALID`로 처리한다.
- 필터 미지정은 정상 검색(200)으로 처리한다.
- 필터 값이 유효하지만 매칭 결과가 없으면 `200 + results=[]`로 처리한다.

### 1.2 시각 고정 (Week 2 상속)
- `created_at`, `structured_at`, `timestamp` 필드는 KST +09:00 포맷 강제

### 1.3 신규 객체명
- `IndexRequest` → 인덱싱 요청
- `SearchRequest` → 검색 요청
- `SearchResult` → 검색 결과
- `Citation` → 인용 근거(생성 단계에서 사용)
- `ModelEvaluationReport` → 모델 벤치마크 리포트

---

## 2) IndexRequest 계약 (BE2 입력)

### 2.1 기본 구조

```json
{
  "request_id": "IDX-2026-000001",
  "action": "bulk",
  "cases": [
    {
      "case_id": "CASE-2026-000001",
      "source": "aihub_71852",
      "created_at": "2026-03-05T10:15:00+09:00",
      "structured": {
        "observation": "민원 상황",
        "result": "처리 결과",
        "request": "요청사항",
        "context": "배경"
      },
      "metadata": {
        "category": "도로안전",
        "region": "서울시 강남구",
        "keywords": ["포트홀", "도로 훼손"]
      }
    }
  ],
  "collection_name": "civil_cases_v1"
}
```

### 2.2 필수 필드
- `request_id` (string)
- `action` (string: "bulk" | "incremental")
- `cases` (array)
- `collection_name` (string, 기본값: "civil_cases_v1")

### 2.3 케이스 객체 필수 필드
- `case_id`
- `source`
- `created_at`
- `structured` (4요소 문자열 포함)
- `metadata.category`, `metadata.region` (검색 필터용)

---

## 3) SearchRequest 계약 (FE/BE3 입력)

### 3.1 기본 구조

```json
{
  "request_id": "SRCH-2026-000001",
  "query": "포트홀 안전",
  "top_k": 5,
  "filters": {
    "region": "서울시 강남구",
    "category": "도로안전",
    "date_from": "2026-01-01",
    "date_to": "2026-03-31"
  },
  "collection_name": "civil_cases_v1"
}
```

### 3.2 필수 필드
- `request_id` (string)
- `query` (string, 최대 1000자)
- `top_k` (integer, 기본값: 5, 범위: 1~20)

### 3.3 선택 필드
- `filters` (object)
  - `region` (string, 선택): 지역 코드 또는 이름
  - `category` (string, 선택): 카테고리명
  - `date_from` (string, 선택): ISO-8601 형식
  - `date_to` (string, 선택): ISO-8601 형식

---

## 4) SearchResult 계약 (FE 출력)

### 4.1 기본 구조

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
      "content": {
        "observation": "도로에 포트홀 발견",
        "result": "즉시 수리 조치",
        "request": "안전 강화",
        "context": "도시 관리 사업"
      },
      "metadata": {
        "region": "서울시 강남구",
        "category": "도로안전",
        "created_at": "2026-03-05T10:15:00+09:00"
      }
    }
  ],
  "total_found": 125,
  "elapsed_ms": 342,
  "timestamp": "2026-03-27T14:35:22+09:00"
}
```

### 4.2 필수 필드
- `request_id`
- `query`
- `success` (boolean)
- `results` (array)
- `total_found` (integer)
- `elapsed_ms` (integer)
- `timestamp` (ISO-8601 KST)

### 4.3 결과 객체(results[]) 필드
- `rank` (integer, 1부터 시작)
- `case_id` (string)
- `similarity_score` (float, 0~1)
- `content` (4요소 객체)
- `metadata` (지역, 카테고리, 생성시각)

---

## 5) Citation 계약 (생성 단계, BE3 출력)

### 5.1 기본 구조

```json
{
  "chunk_id": "CHUNK-000001",
  "case_id": "CASE-2026-000001",
  "snippet": "도로에 포트홀이 급증함",
  "confidence": 0.92
}
```

### 5.2 필수 필드
- `chunk_id` (string, unique)
- `case_id` (string)
- `snippet` (string, 최대 200자)
- `confidence` (float, 0~1)

---

## 6) ModelEvaluationReport 계약 (BE1/BE2/BE3 출력)

### 6.1 기본 구조

```json
{
  "report_id": "RPT-2026-WEEK3-001",
  "generated_at": "2026-03-27T18:00:00+09:00",
  "benchmark_config": {
    "test_cases": 500,
    "models": ["aihub_baseline", "candidate_ax4_light", "candidate_exaone_3_5_7_8b", "candidate_gemma3_12b", "candidate_phi4_mini"]
  },
  "models": [
    {
      "model_name": "aihub_baseline",
      "model_type": "baseline",
      "metrics": {
        "avg_response_time_ms": 1250,
        "p95_response_time_ms": 1800,
        "json_parse_success_rate": 0.98,
        "total_tests": 500,
        "successful_tests": 490,
        "failed_tests": 10
      },
      "sample_outputs": [
        {
          "test_case_id": "TC-001",
          "input_query": "포트홀 신고",
          "output_snippet": "도로 보수 신청 절차는..."
        }
      ]
    }
  ],
  "comparison": {
    "fastest_model": "phi4-mini:3.8b-instruct",
    "most_stable_model": "aihub_baseline",
    "recommendation": "aihub_baseline for production, phi4-mini for speed"
  }
}
```

### 6.2 필수 필드
- `report_id` (string)
- `generated_at` (string, ISO-8601 KST)
- `benchmark_config` (object)
- `models` (array, 각 모델별 metrics)
- `comparison` (object, 비교 분석)

### 6.3 Model Metrics (models[].metrics)
- `avg_response_time_ms` (integer)
- `p95_response_time_ms` (integer)
- `json_parse_success_rate` (float, 0~1)
- `total_tests` (integer)
- `successful_tests` (integer)
- `failed_tests` (integer)

---

## 7) 에러 응답 (Week 2 상속)

```json
{
  "success": false,
  "request_id": "SRCH-2026-000001",
  "timestamp": "2026-03-27T14:35:22+09:00",
  "error": {
    "code": "SEARCH_ERROR",
    "message": "검색 엔진 오류 발생",
    "retryable": true
  }
}
```

---

## 8) Week 3 특화 에러 코드

| 코드 | 의미 | 대응 |
|-----|------|------|
| `INDEX_EMPTY` | 인덱싱할 케이스 없음 | 입력 데이터 확인 |
| `COLLECTION_NOT_FOUND` | 컬렉션 미존재 | 인덱싱 먼저 수행 |
| `SEARCH_NO_RESULTS` | 검색 결과 0건 | 쿼리/필터 수정 권장 |
| `FILTER_INVALID` | 잘못된 필터 형식 | 필터 포맷 확인 |
| `MODEL_NOT_AVAILABLE` | 모델 미설치 | Ollama 모델 설치 필요 |

---

## 9) Week 3 인터페이스 체크리스트

- [ ] IndexRequest 입출력 포맷 팀 리뷰 완료
- [ ] SearchRequest/SearchResult 정의 팀 리뷰 완료
- [ ] Citation 정의 BE3/FE 리뷰 완료
- [ ] ModelEvaluationReport 필드 BE1/BE2/BE3 협의 완료
- [ ] 에러 코드 매핑 팀 전체 동의

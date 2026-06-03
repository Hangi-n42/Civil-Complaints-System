# PromptFactory 평가 실행 가이드

## 목적

Generation 평가/벤치마크는 `PromptFactory`를 단일 진입점으로 사용한다. 프롬프트는 항상 검색 컨텍스트, JSON 스키마, citations 규칙, 모드별 지시문을 함께 포함해야 한다.

## 전제

- `CHROMA_DB_PATH`가 populated ChromaDB persist directory를 가리켜야 한다.
- 기본 컬렉션명은 `civil_cases_v1`이다.
- 로컬 생성 평가는 Ollama 서버와 대상 모델이 준비되어 있어야 한다.

## 원문 레코드 평가

`VS_지방행정기관/성남시_test_10.json`처럼 `query/context`가 없는 원문 레코드는 auto-retrieve 경로를 사용한다.
`logs/evaluation/week6/seongnam_test_10_cases.json`처럼 `query`에 민원 원문 전체가 들어 있고 `context`가 빈 배열인 경우도 원문 민원 데이터셋으로 취급한다. 이때 PromptFactory는 `제목/Q`에서 `derived_query`를 추출하고, 프롬프트에는 `민원 원문` 블록을 별도로 포함해 컨텍스트 요약이 아닌 사실적인 민원 회신을 작성하도록 지시한다.

```bash
python scripts/run_raw_dataset_qa.py \
  --input VS_지방행정기관/성남시_test_10.json \
  --output logs/evaluation/raw_dataset_qa_results.json \
  --limit 10 \
  --mode compact \
  --top-k 5 \
  --collection civil_cases_v1
```

## Week6 모델 벤치마크

Week6 BE3 모델 벤치마크는 `scripts/Be3_run_week6_model_benchmark.py`에서 `PromptFactory.build_from_dataset_record()`를 호출한다. 직접 프롬프트 문자열을 별도로 만들지 않는다.
벤치마크 케이스에 `context`가 비어 있으면 `PromptFactory.build_from_dataset_record_autoretrieve()`로 Chroma 근거를 검색한 뒤 direct 모델 호출을 수행한다.

```bash
python scripts/Be3_run_week6_model_benchmark.py \
  --benchmark-mode direct \
  --config configs/week6_Be3_model_benchmark.yaml \
  --cases ../40_delivery/week3/model_test_assets/evaluation_set.json \
  --output-dir logs/evaluation/week6/be3_model_benchmark
```

## 0건 근거 실패 점검

검색 컨텍스트가 0개면 `NoEvidenceError`로 즉시 실패한다. 에러 details에는 `derived_query`, `collection_name`, `top_k/effective_top_k`, `filters`, `threshold`, `topic_type`, `complexity_level`, `route_key`, `strategy_id`, `retrieval_policy`가 포함된다.

우선 아래 순서로 확인한다.

```bash
python scripts/inspect_chromadb.py list
python scripts/inspect_chromadb.py count --collection civil_cases_v1
python scripts/inspect_chromadb.py sample --collection civil_cases_v1 --limit 3
```

FastAPI 서버가 떠 있다면 read-only 디버그 엔드포인트도 사용할 수 있다.

```text
GET /api/v1/chroma/collections
GET /api/v1/chroma/collections/civil_cases_v1/count
GET /api/v1/chroma/collections/civil_cases_v1/sample?limit=3
```

원인 구분 기준:

- count가 0이면 DB 경로 또는 인덱싱 문제다.
- count는 있는데 0건이면 `filters`, `threshold`, `top_k`가 과도한지 확인한다.
- query가 이상하면 `derived_query`와 `search_query`를 원문 레코드와 비교한다.

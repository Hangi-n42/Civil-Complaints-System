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

이 fail-fast 규칙은 평가·벤치마크용 PromptFactory autoretrieve 경로에 적용된다.
사용자용 `/api/v1/qa`는 같은 상황에서 근거 없는 사실 단정을 하지 않는
`no_evidence_fallback` 응답을 반환하므로 두 경로를 구분해서 해석한다.

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

## 평가 누수 및 지표 해석

- 원문 데이터셋의 `case_id`, `complaint_id`, `source_id`가 있으면 해당 사례는
  autoretrieve 후보에서 제외된다. 같은 민원의 기존 답변을 다시 검색해 평가하는
  데이터 누수를 방지하기 위한 규칙이다.
- 인덱스는 민원 원문·구조화 필드만 근거로 만들어야 하며
  `consultant_answer` 포함 여부와 corpus build version을 실행 기록에 남긴다.
- `raw_schema_success_rate`는 모델 원출력이 PromptFactory JSON Schema를 그대로
  만족한 비율이다.
- `postprocess_success_rate`는 정규화·보정 뒤 QA validator를 통과한 비율이다.
- 기존 호환 필드 `parse_success_rate`는 이제 `raw_schema_success_rate`와 같은
  엄격 기준으로 집계한다.
- `citation_support_rate_strict`는 `chunk_id`, `case_id`, snippet 부분문자열이
  모두 검색 컨텍스트와 일치하는 원출력 citation 비율이다.
- `citations_strict`와 `citations_repaired`를 별도로 저장하므로 모델 성능과
  후처리 성능을 혼합해 해석하지 않는다.

direct 모드와 API 모드는 모두 grounding filter와 법령 검증을 사용한다. 다만 API
모드는 통합 응답 계약과 SSE를 거치므로, 모델 자체 비교에는 direct 결과의
`raw_schema_success_rate`를 우선 사용하고 제품 경로 검증에는 API 결과를 사용한다.

## 생성 속도와 회신 품질 점검

- Ollama 호출은 검색 컨텍스트에서 만든 동적 JSON Schema를 `format`으로 전달한다.
  citation의 `chunk_id/case_id/snippet`도 검색 근거 값으로 제한한다.
- strict 파싱 재시도는 `default -> compact` 두 단계만 사용한다. 정상 응답은 첫 호출에서
  종료하고, 두 단계가 모두 실패하면 fast fallback으로 전환한다.
- direct 벤치마크는 현재 후보 모델을 grounding filter에도 사용한다. 설정 모델명이
  실제 Ollama 모델명과 다르면 개별 판정 fallback으로 느려질 수 있으므로
  `OLLAMA_MODEL`과 `GROUNDING_FILTER_MODEL`을 확인한다.
- grounding 후보는 한 번의 배치 JSON 응답으로 채점하고, 배치 실패 시에만 기존
  후보별 병렬 판정으로 복귀한다.
- 회신 후처리는 3문단 안의 중복 `감사합니다. 끝.`, JSON 필드 잔여물,
  근거 없는 확약, 기관이 자신에게 `검토해 주시기 바랍니다`라고 지시하는 표현을 제거한다.
- 유사사례의 사실을 현재 민원의 확인 사실로 옮기지 않도록 `확인하였습니다`,
  `보고되었습니다` 단정은 현장 확인이 필요한 표현으로 낮춘다.

2026-06-12 Exaone 1건 smoke 기준:

| 항목 | 결과 |
| --- | ---: |
| 검색 + grounding | 54.053초 |
| 생성 | 33.377초 |
| 전체 | 87.432초 |
| 파싱 재시도 | 0회 |
| citation | 1개 |
| `감사합니다. 끝.` | 1회 |
| schema artifact | 없음 |

전체 50건 성능은 동일 입력으로 다시 실행한 뒤 `avg_latency_sec`, `p95_latency_sec`,
`raw_schema_success_rate`, Q0~Q8 및 semantic risk count를 이전 결과와 함께 비교한다.

추가로 다음 안전성 지표를 함께 확인한다.

- `qa_warning_codes`의 `ANSWER_REQUEST_MISMATCH`
- `PRECEDENT_FACT_LEAKAGE_RISK`
- `UNSUPPORTED_COMMITMENT_RISK`
- `UNVERIFIED_FACT_RISK`
- `CONTEXT_CONSTRAINT_CONFLICT`

잘린 JSON에서 `answer`를 복구하지 못한 경우 검색 snippet을 회신 본문으로
대체하지 않는다. 따라서 모델 형식 실패 건은 무관한 유사 사례 답변 대신
제한 응답 또는 실패 상태로 남아야 한다.

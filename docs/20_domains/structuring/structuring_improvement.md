# Structuring 구조 검증 및 개선 기록

작성일: 2026-06-10  
대상 브랜치: `improve/structuring-validation-loop`  
관점: BE1 구조화 파이프라인과 BE2, BE3, FE 계약 정합성

## 1. 검증 대상 파일/모듈

### BE1 structuring

- `app/structuring/service.py`
- `app/structuring/preprocessing.py`
- `app/structuring/enrichment.py`
- `app/structuring/department_assigner.py`
- `app/structuring/structured_extractor.py`
- `app/structuring/structured_merge.py`
- `app/structuring/merger.py`
- `app/structuring/llm_extractor.py`
- `app/structuring/verifier.py`
- `app/structuring/schemas.py`

### BE1 실행/적재 스크립트

- `scripts/build_index.py`
- `scripts/generate_week2_delivery_samples.py`
- `scripts/run_week2_be1_e2e.py`

### BE2 계약/저장 계층

- `app/api/schemas/retrieval.py`
- `app/api/routers/retrieval.py`
- `app/retrieval/service.py`
- `app/retrieval/vectorstores/chroma_store.py`
- `app/tests/unit/test_retrieval_search_signal_metadata.py`

### BE3/FE 계약 문서

- `app/api/schemas/generation.py`
- `app/generation/prompts/prompt_factory.py`
- `docs/10_contracts/interfaces/week6/week6_be3_interface.md`
- `docs/10_contracts/interfaces/week7/week7_fe_interface.md`

## 2. 현재 구조 요약

BE1 구조화 흐름은 원천 민원 입력을 `StructuringService.structure()`로 받아 다음 순서로 처리한다.

1. `preprocessing.py` 또는 `_normalize_required()`에서 원천 `consulting_content`를 민원인 원문 중심으로 정규화한다.
2. Rule NER로 `entities`를 추출한다.
3. 설정에 따라 constrained extractor 또는 기존 LLM extractor와 merger를 통해 `observation`, `result`, `request`, `context` 4요소를 생성한다.
4. BE2 검색 보조 신호인 `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `urgency`를 보강한다.
5. `validate_schema()`로 필수 구조와 entity label을 검증한다.
6. `scripts/build_index.py`가 BE1 구조화 결과를 BE2 `/api/v1/index` 입력 레코드로 변환해 전달한다.

## 3. BE1 관점의 판단

- BE1의 핵심 책임은 원천 민원에서 상담사 답변과 라벨링 데이터를 제외하고, 민원인 원문 기반 구조화 결과와 검색 보조 신호를 만드는 것이다.
- `StructuringService`는 orchestration 책임이 크지만 현재 외부 계약과 파이프라인 순서가 이 서비스에 모여 있으므로, 이번 작업에서는 큰 분해보다 계약 보존과 신호 전달 누락 해소에 집중한다.
- 구조화 결과에 생성되는 검색 보조 신호는 BE2 soft rerank에 필요한 정보이므로, BE1 내부 생성에서 끝나지 않고 인덱싱 레코드까지 일관되게 전달되어야 한다.

## 4. BE2, BE3, FE 정합성 검토 결과

### BE2

- `IndexRecord`는 `extra="allow"`를 사용하므로 기존 필드 외 선택 필드를 받을 수 있다.
- `RetrievalService._normalize_record()`는 `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `responsible_units_source`, `urgency`를 읽을 수 있다.
- `ChromaVectorStore._build_metadata()`는 정규화된 검색 신호를 Chroma metadata 문자열로 평탄화한다.
- 따라서 BE1 인덱싱 레코드에 위 필드를 추가 전달하는 것은 기존 API contract 변경이 아니라 누락된 optional signal 보존이다.

### BE3

- BE3 `/qa` 계약은 `routing_trace`, `structured_output`, `answer`, `citations`, `legal_citations`, `limitations`, `quality_signals`, `generation_metadata` 중심이다.
- BE3는 BE1 구조화 DTO를 직접 응답 DTO로 노출하지 않으므로 이번 변경에서 generation schema는 변경하지 않는다.
- `PromptFactory` 내부 raw 원문 추출 경로는 BE1 전처리와 일부 중복된다. 다만 generation 동작에 영향을 줄 수 있어 이번 작업에서는 승인 필요 항목으로만 남긴다.

### FE

- FE 계약은 workbench 상태, 유사 민원 패널, 답변 초안 편집 UI 중심이다.
- BE1 구조화 결과 필드 추가를 직접 의존하지 않는다.
- 이번 변경은 BE2 인덱싱 레코드의 optional signal 보존이므로 FE 응답 형식에 영향이 없다.

## 5. 발견한 문제 목록

### A. 승인 없이 반영 가능한 개선

1. BE1 구조화 결과의 검색 보조 신호가 `scripts/build_index.py` 변환 과정에서 BE2로 전달되지 않는 문제
   - 원인: `_build_api_case_record()`가 `entities`만 복사하고 `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `urgency`를 누락한다.
   - 영향: BE2 Chroma metadata에 soft rerank 신호가 빠질 수 있다.
   - 변경 방향: BE2가 이미 읽을 수 있는 optional top-level 필드로 그대로 보존한다.

2. Week2 샘플 생성 스크립트가 원천 `consulting_content` 정규화 결과보다 기존 `raw_text/text`를 먼저 사용할 수 있는 문제
   - 원인: `normalize_record()`의 raw text 우선순위가 `raw_text > text > structuring_record.text`이다.
   - 영향: 원천 상담 답변이 포함된 필드가 있으면 민원인 원문 원칙과 어긋날 수 있다.
   - 변경 방향: `consulting_content`가 있는 원천 데이터는 `to_structuring_record()` 결과를 우선 사용한다.

3. Week2 E2E fallback raw sample 수집이 과거 `case_id/text` 형식에 묶여 있는 문제
   - 원인: `_collect_raw_samples()`가 AI Hub 원천의 `source_id/consulting_content` 형식을 전처리 어댑터로 변환하지 않는다.
   - 영향: 기본 샘플 파일이 없을 때 원천 데이터 fallback 검증이 비어 버릴 수 있다.
   - 변경 방향: raw sample 수집 시 `to_structuring_record()`를 사용해 현재 전처리 경로와 맞춘다.

### B. 승인 필요한 개선

1. BE1 출력 DTO에 `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `urgency`를 공식 필수/권장 스키마로 승격
   - 사유: DTO/schema 문서와 소비자 계약을 변경한다.

2. BE3 `PromptFactory`의 raw 원문 추출 로직을 BE1 `preprocessing.py`로 통합
   - 사유: generation query 추출과 prompt 구성 결과가 달라질 수 있다.

3. `app.ingestion.service`가 `app.structuring.preprocessing`을 import하는 의존성 방향 정리
   - 사유: 모듈 경계 재설계이며 호출부 동시 수정이 필요할 수 있다.

4. `StructuringService` orchestration을 여러 하위 서비스로 분해
   - 사유: 내부 리팩터링이지만 파이프라인 실행 순서와 테스트 범위가 크게 바뀐다.

5. `validate_schema()` 필수 필드에 검색 보조 신호를 추가
   - 사유: 기존 구조화 호출 결과의 validation 판정이 바뀔 수 있다.

## 6. 검증 루프 로그

### Iteration 1 - 구조 및 계약 검증

- 검증 내용
  - BE1 구조화 모듈, BE2 인덱싱 schema, BE2 normalization/storage, BE3/FE 계약 문서를 확인했다.
- 판단
  - BE2는 검색 보조 신호를 받을 준비가 되어 있으나 BE1 적재 변환에서 일부 신호가 누락된다.
  - BE3/FE 응답 계약은 이번 개선 대상이 아니며, DTO 변경 없이 유지해야 한다.
- 승인 없이 진행할 작업
  - `scripts/build_index.py` optional search signal pass-through 보강
  - Week2 샘플/E2E 스크립트의 원천 전처리 경로 정합성 보강
- 승인 필요로 보류한 작업
  - DTO/schema 공식 변경
  - BE3 prompt raw 추출 경로 통합
  - 큰 서비스 분해
- 검증 방법 계획
  - 변환 함수 단위 테스트 추가
  - 기존 BE1 전처리/구조화 테스트 실행
  - BE2 search signal metadata 테스트 실행

### Iteration 2 - 승인 없이 가능한 개선 반영

- 변경 내용
  - `scripts/build_index.py`의 `_build_api_case_record()`가 BE1 구조화 결과의 `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `urgency`를 BE2 인덱싱 레코드 top-level optional field로 보존하도록 수정했다.
  - `scripts/generate_week2_delivery_samples.py`가 원천 `consulting_content`를 가진 레코드에서는 `to_structuring_record()` 결과를 우선해 `raw_text`를 구성하도록 수정했다.
  - `scripts/run_week2_be1_e2e.py`의 raw fallback 수집 경로가 AI Hub 원천 `source_id/consulting_content` 형식을 `to_structuring_record()`로 정규화하도록 수정했다.
- 변경 전
  - BE1이 생성한 검색 보조 신호가 BE2 인덱싱 요청에서 누락될 수 있었다.
  - 샘플/E2E 스크립트 일부가 현재 원천 전처리 원칙과 다르게 예전 `case_id/text` 중심 입력을 가정했다.
- 변경 후
  - BE2가 이미 지원하는 선택 metadata 신호가 인덱싱 레코드에 유지된다.
  - 당시 검증/샘플 경로는 민원인 원문만 사용하도록 정리했으나, 현재 검색 재색인 정책은 민원인 원문과 상담사 답변을 함께 사용하는 방향으로 변경됐다.
- 영향 범위
  - BE1 내부 실행 스크립트와 테스트에 한정된다.
  - BE2 `/api/v1/index`의 request schema는 `extra="allow"`이므로 기존 계약 변경이 없다.
  - BE3/FE request/response 형식에는 영향이 없다.
- 롤백 가능성
  - `scripts/build_index.py`의 `search_signals` pass-through와 두 스크립트의 전처리 우선순위 보정을 되돌리면 된다.

### Iteration 3 - 재검증 및 추가 분류

- 실행 테스트
  - `.\civil\Scripts\python.exe -m pytest app/tests/unit/test_build_index_contract.py app/tests/unit/test_week2_script_input_contract.py app/tests/unit/test_preprocessing_adapter.py app/tests/unit/test_be1_week2_tasks.py app/tests/unit/test_retrieval_search_signal_metadata.py -q`
  - 결과: `27 passed, 3 warnings`
  - warning: scikit-learn pickle 버전 차이 경고이며 이번 변경과 무관한 기존 urgency model 로딩 경고다.
  - `.\civil\Scripts\python.exe -m pytest app/tests/unit/test_structured_extractor.py app/tests/unit/test_structured_merge.py -q`
  - 결과: `9 passed`
- 재검증 결과
  - 기존 BE1 전처리/구조화 테스트가 통과했다.
  - 신규 변환 테스트가 BE1 검색 신호 pass-through를 확인했다.
  - BE2 search signal metadata 테스트가 통과해 Chroma metadata 저장 계약이 유지됨을 확인했다.
  - request/response 형식 변경은 없다.
  - 기존 파이프라인 순서 변경은 없다.
- 추가 발견
  - BE3 `PromptFactory`에도 raw 원문 추출 로직이 존재한다. BE1 전처리와 중복되지만 generation query와 prompt가 달라질 수 있으므로 승인 필요 항목으로 유지한다.
  - `StructuringService`는 책임이 큰 편이나 현재 파이프라인 중심축이므로, 승인 없는 큰 분해는 하지 않았다.

## 7. 승인 없이 반영한 개선사항

1. BE1 검색 보조 신호의 BE2 인덱싱 레코드 보존
   - 파일: `scripts/build_index.py`
   - 목적: `entity_texts`, `legal_refs`, `key_terms`, `responsible_unit`, `urgency`가 Chroma metadata로 이어질 수 있게 한다.
   - 계약 영향: 없음. BE2 `IndexRecord`는 extra field를 허용하고, `RetrievalService._normalize_record()`는 해당 필드를 이미 해석한다.

2. Week2 샘플 생성 입력 정합성 보정
   - 파일: `scripts/generate_week2_delivery_samples.py`
   - 목적: 당시 샘플 `raw_text` 정책을 고정하기 위한 항목이다. 현재 운영 구조화/검색 입력은 답변 포함 본문을 사용한다.
   - 계약 영향: 없음. 생성 샘플의 필드 이름과 구조는 유지된다.

3. Week2 E2E fallback 입력 정합성 보정
   - 파일: `scripts/run_week2_be1_e2e.py`
   - 목적: 샘플 파일이 없을 때도 실제 원천 `consulting_content` 형식을 처리한다.
   - 계약 영향: 없음. 내부 fallback 수집 경로만 보정한다.

4. 회귀 테스트 보강
   - 파일: `app/tests/unit/test_build_index_contract.py`
   - 파일: `app/tests/unit/test_week2_script_input_contract.py`
   - 목적: BE1 검색 신호 보존과 원천 상담 본문 전처리 우선순위를 고정한다.

## 8. 승인 필요한 개선사항

1. BE1 출력 schema 문서에 검색 보조 신호를 공식 필드로 승격
   - 기대 효과: BE1, BE2 사이 문서 계약이 실제 구현과 더 가까워진다.
   - 승인 필요 이유: DTO/schema 계약 문서 변경이다.

2. BE3 raw 원문 추출을 BE1 전처리 어댑터와 통합
   - 기대 효과: BE3 query/routing 원문 추출도 BE1 원천 데이터 원칙과 일치한다.
   - 승인 필요 이유: prompt 입력과 검색 query가 바뀔 수 있어 BE3 응답 품질에 영향을 줄 수 있다.

3. 전처리 공용 모듈 위치 재정리
   - 기대 효과: `ingestion -> structuring` 의존 방향을 더 명확히 할 수 있다.
   - 승인 필요 이유: import 경로와 호출부 동시 수정이 필요할 수 있다.

4. `StructuringService` orchestration 분해
   - 기대 효과: 입력 정규화, NER, 4요소 추출, enrichment, validation 책임을 더 명확히 나눌 수 있다.
   - 승인 필요 이유: 파이프라인 중심 서비스의 구조 변경이며 회귀 범위가 크다.

5. 검색 보조 신호 validation 강화
   - 기대 효과: 구조화 결과에 필요한 검색 신호 누락을 조기에 발견할 수 있다.
   - 승인 필요 이유: 기존 구조화 결과의 `validation.is_valid` 판정이 바뀔 수 있다.

## 9. 남은 리스크

- 이번 변경은 인덱싱 요청에 검색 보조 신호를 보존하는 것까지 검증했다. 실제 9,132건 재인덱싱 후 Chroma metadata 적재율은 BE2 인덱싱 실행 환경에서 재측정해야 한다.
- scikit-learn model pickle 버전 경고는 기존 urgency model 아티팩트와 실행 환경의 버전 차이에서 발생한다. 이번 변경의 직접 원인은 아니지만 운영 환경 고정이 필요하다.
- BE3 raw 추출 중복은 남아 있다. 다만 이번 작업에서 직접 수정하면 generation 결과가 달라질 수 있어 승인 필요 항목으로 남겼다.

## 10. 추후 권장 작업

1. BE2 인덱싱 실행 후 다음 명령으로 metadata coverage를 재측정한다.

```powershell
python scripts/check_chromadb_search_signal_coverage.py `
  --persist-dir data/chroma_db `
  --collection civil_cases_v1
```

2. BE1 출력 schema 문서에 검색 보조 신호의 optional contract를 명시할지 승인 후 결정한다.
3. BE3 `PromptFactory`의 raw 원문 추출을 BE1 전처리와 통합할지 별도 이슈로 검토한다.
4. `StructuringService` 분해는 테스트 보강과 함께 별도 리팩터링 브랜치에서 진행한다.

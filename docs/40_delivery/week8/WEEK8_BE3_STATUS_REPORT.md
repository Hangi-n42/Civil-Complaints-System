# WEEK8 BE3 현황 보고서 (객관/정확)

작성일: 2026-05-19  
작성: BE3  
기준 브랜치: `feature/#194-W7-Be3`  

참고 문서(프로젝트 기준선):
- `docs/00_overview/mvp_scope.md`
- `docs/00_overview/prd.md`
- `docs/00_overview/wbs_8weeks_v2_updated.md`
- `docs/30_manuals/manual.md`
- `docs/50_issues/week8/check.md` (2026-05-07, 일부 항목은 현재 브랜치에서 개선됨)
- `docs/10_contracts/interfaces/week6/week6_be3_interface.md`
- `docs/10_contracts/interfaces/week7/week7_be3_interface.md`

---

## 0. BE3 범위 재정의 (MVP 기준)

MVP(데모) 완료 정의의 핵심은 “민원 1건 선택 → Adaptive RAG 처리 → Workbench 우측 패널에서 답변 초안 + citation 확인/편집”이 **중단 없이 연속 동작**하는 것이다.

이 중 BE3 책임은 다음 3가지로 고정한다.
1) Generation 프롬프트 구성(`PromptFactory`)이 routing 정보(topic/complexity/segments)를 반영한다.
2) `/qa`의 **성공 응답**이 unified schema(answer/citations/limitations/structured_output/routing_trace/latency_ms/quality_signals)를 **항상 반환**하도록 보장한다(정규화 + 계약 검증).
3) FE가 편집 가능한 형태로 answer/structured_output/limitations을 제공하고, citation은 근거 하이라이팅 가능하도록 정합성을 유지한다.

---

## 1. 구현 현황 (2026-05-19 기준)

### 1.1 `/qa` unified schema 고정 (핵심 완료)
- 구현 위치: `app/api/routers/generation.py`
- 현 상태:
  - `/qa` 응답 생성 후 `normalize_response()`로 타입/기본값을 정규화
  - `validate_unified_contract()`로 필수 키 누락 시 500(`RESPONSE_SCHEMA_MISMATCH`)로 차단
  - 결과적으로 FE가 기대하는 “편집 가능한 answer/structured_output/limitations + read-only citations/routing_trace” 형태가 유지됨

### 1.2 PromptFactory (routing-aware + JSON 강제 모드 포함)
- 구현 위치: `app/generation/prompts/prompt_factory.py`
- 현 상태:
  - `TOPIC_GUIDANCE`(welfare/traffic/environment/construction/general) + `COMPLEXITY_GUIDANCE`(low/medium/high) 분기 반영
  - `request_segments` 존재 시 세그먼트별 답변/액션아이템 작성 지시 포함
  - prompt mode 지원:
    - `default`: 기본 JSON 규칙 + 품질 규칙
    - `force_json`: JSON Schema required 키 누락 방지에 집중
    - `compact`: 컨텍스트/출력 규칙을 더 강하게 압축(데모 끊김 방지 목적)
  - 공통 규칙으로 `[[출처 n]]` 토큰 포함을 지시(근거 하이라이팅 전제)

### 1.3 GenerationService (재시도 단계화 + fast fallback) — check.md 대비 개선
- 구현 위치: `app/generation/service.py`
- 현 상태:
  - 파싱/재시도 정책(단계 순서):
    - `default (temperature=0.2)` → `force_json (temperature=0.0)` → `compact (temperature=0.0)`
  - 각 단계에서 strict 파싱 실패 시 relaxed 파싱을 추가로 시도
  - 모든 파싱 시도 실패 시 `fast fallback`을 사용해 “파싱 실패로 인한 중단”을 피함(단, retrieval 컨텍스트가 존재하는 경우)

추가 관찰(동작 경계):
- `/qa`는 retrieval 컨텍스트를 구성할 수 없으면 성공 응답 대신 에러(`RESOURCE_NOT_FOUND` 또는 `BAD_REQUEST`)로 종료한다.

### 1.4 Citation 정합성/토큰 강제 (근거 하이라이팅 전제) — 핵심 완료
- 구현 위치:
  - `app/generation/validators/qa_response_validator.py`
  - `app/api/routers/generation.py`
  - `app/generation/citation/citation_mapper.py` (컨텍스트 대조)
- 현 상태:
  - citations 정규화(`normalize_citations`):
    - retrieval context의 `chunk_id/case_id`와 정합한 항목만 통과
    - 모델이 citations를 반환했지만 전부 무효화되는 경우 컨텍스트 기반 fallback으로 최소 1개 확보
  - answer 본문 `[[출처 n]]` 토큰 누락 시 자동 보완(`ensure_citation_tokens`)
  - `build_validation_result`에서 answer 토큰과 `citations.ref_id`의 1:1 일치 여부를 검증하고, 불일치 시 `/qa`는 에러로 차단
  - unified response의 `citations`는 FE 편의 형태(`doc_id/source/quote`)로 변환하여 제공

### 1.5 normalize_response / contract validation (스키마 경계 고정) — 완료
- 구현 위치: `app/generation/normalization/response_normalizer.py`
- 현 상태:
  - 필수 키 존재 여부 및 타입을 강제(부족하면 기본값 삽입)
  - citations 구조를 `doc_id/source/quote`로 정규화
  - limitations를 항상 `string[]`로 정규화
  - latency_ms, quality_signals는 타입을 강제(숫자/불리언 캐스팅)

### 1.6 벤치마크/로그 축적 (Week7)
- 현 상태(폴더 존재 확인): `logs/evaluation/week7/`
  - `ax4_direct_eval10_20260507_schemafmt/` 등 산출물 폴더 존재
  - direct 모드 평가 결과(md/json/jsonl) 누적 경로가 Week7 기준으로 고정됨

### 1.7 에러/헤더 계약(운영/디버깅 관점)
- 구현 위치: `app/api/routers/generation.py`, `app/api/error_utils.py`
- 현 상태:
  - 응답 헤더에 `X-Contract-Version`을 설정(현재 값: `qa-v1.1`)
  - 파싱 재시도 소진(`PARSE_RETRY_EXHAUSTED`)은 Week4 표준 에러 코드 `QA_PARSE_ERROR`로 변환해 반환
  - 성공/실패 로그 모두 request_id, latency_ms, retrieved_count 등을 포함하도록 로깅

### 1.8 검증 근거(테스트)
- 단위 테스트(파싱/정규화/토큰/검증):
  - `app/tests/unit/test_generation_common_utils.py`
- 단위 테스트(Week6 프롬프트/정규화 계약 고정):
  - `app/tests/unit/test_generation_week6_prompt_normalize.py`
- 단위 테스트(Week5 계약/경계 고정):
  - `app/tests/unit/test_generation_week5_contract.py`
- 통합 테스트(search→qa E2E 샘플 10건):
  - `app/tests/integration/test_week6_search_to_qa_e2e_sample10.py`

---

## 2. MVP 완료까지 “남은 일” (BE3 관점)

MVP 관점에서 BE3의 “필수 잔여”는 크지 않고, 주로 **데모 안정화/동결** 성격이다.

### 2.1 (필수) FE 연동 최종 점검용 체크리스트 고정
- FE가 실제로 사용하는 필드(특히 `data.answer`, `data.structured_output.*`, `data.citations[*].quote`, `data.limitations[]`)가 화면 렌더링/편집 흐름에서 깨지지 않는지 E2E 확인이 필요
- BE3 관점에서 필요한 것은 “스키마 변경 없이, 예외/폴백에서도 동일 구조 유지”를 최종 확인하는 것

### 2.2 (필수) Week8 동결 정책 반영
- Week8 운영 원칙상(매뉴얼/WBS): 스키마 변경 금지, 버그 픽스만 허용
- 따라서 BE3 남은 작업은 신규 기능이 아니라:
  - 데모 실패를 유발하는 파싱/검증/예외 케이스만 최소 수정
  - 실행/로그 경로를 문서화해 재현성을 유지

### 2.3 (선택, MVP 외) quality_signals의 “의미 있는 계산”
- 현 구현은 아래처럼 단순/하드코딩이 존재(현재 브랜치 기준):
  - `hallucination_flag = False` 고정
  - `citation_coverage`: citations 존재 여부 기반 이진값
  - `segment_coverage`: request_segments 존재 여부 기반 이진값
- 이는 API 계약을 깨지는 않지만, UI에서 지표를 신뢰하게 되면 오해를 유발할 수 있어 **표시/해석 시 주의**가 필요

---

## 3. 아쉬운 부분/리스크 (객관적 정리)

### 3.1 quality_signals 품질(정확도) 리스크
- `quality_signals`가 “계약 키는 충족하지만 값의 의미가 약함”
- 특히 `hallucination_flag`가 항상 False이면, 실제 위험 상황을 탐지하지 못하는 false negative가 구조적으로 발생

### 3.2 `/qa` 단계의 정책 전달 단절 가능성
- Week8 점검 문서 기준으로 `/qa`가 routing_trace의 `retrieval_policy`를 활용하지 않는 경로가 존재할 수 있음
- 현재는 기본적으로 `/qa`가 search 결과(context)를 받아 답변 생성하므로 즉시 문제가 표면화되지는 않지만,
  - “`/qa` 단독 호출 + 자체 retrieval 수행” 같은 경로가 늘어나면 정책 불일치 리스크가 커짐

### 3.3 통합 테스트/E2E 시나리오 수 부족
- 점검 문서 기준: E2E 통합 테스트가 1종(샘플 10건) 수준으로 제한적
- Week8의 “시나리오 3종 동결” 관점에서, 실패 재현/회귀 방지의 근거가 부족해질 수 있음

### 3.4 검색 결과 0건 케이스(데모 흐름 중단 가능)
- `/qa`는 retrieval 컨텍스트가 비어 있으면 `RESOURCE_NOT_FOUND`로 종료한다.
- 즉, “파싱 실패 대비 폴백”은 존재하지만 “검색 결과 없음”에 대한 성공 응답 폴백은 현재 경로상 제공되지 않는다.

---

## 4. 앞으로의 제안 (1~2개)

### 제안 1) Week8 데모 운영 관점의 “동결 체크리스트”를 BE3 기준으로 명문화
- 목적: 시연 당일 실패 원인을 코드가 아닌 운영(모델/캐시/로그/환경)에서 제거
- 예시 항목:
  - Ollama 모델 준비/워밍업(최초 응답 지연 제거)
  - `logs/api`, `logs/pipeline`, `logs/evaluation`에서 확인해야 할 최소 로그 경로 5개만 고정
  - `/qa` 폴백 발생 시 UI 메시지/제약 문구( limitations )가 데모에 적합한지 점검

### 제안 2) quality_signals는 “동결 이후(또는 최소 heuristic)”로 정리
- Week8은 기능 추가를 지양하므로, 지금은 지표 개선보다 “끊김 없는 데모”가 우선
- 다만 발표/평가에서 quality_signals를 언급해야 한다면:
  - (최소 heuristic) citation_coverage/segment_coverage를 비율 기반으로 계산
  - hallucination_flag는 “unknown 처리(예: False 고정 대신 heuristic 결과)” 또는 UI에서 숨김

---

## 5. 결론

- BE3 핵심 목표(프롬프트 라우팅 반영 + `/qa` unified schema 고정 + citation/토큰 정합성)는 현재 구현 기준으로 **대부분 충족**된 상태다.
- Week8에서 BE3의 잔여 작업은 신규 기능이 아니라 **통합 데모 안정화/동결 운영**에 가깝다.
- 기술적으로는 `quality_signals`의 의미(계산 로직)가 가장 큰 “아쉬운 부분”이며, 이는 MVP 완료 조건(데모 관통)과는 분리해 관리하는 것이 현실적이다.

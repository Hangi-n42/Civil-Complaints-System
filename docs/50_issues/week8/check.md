# 백엔드 구현 현황 점검 (Week 8 기준)

문서 버전: v1.0
작성일: 2026-05-07
기준 브랜치: feature/refactor-structured

---

## 1. 점검 요약

| 컴포넌트 | 구현 완성도 | 핵심 이슈 |
|---|---|---|
| TopicAnalyzer | 60% | 독립 클래스 없음, 인라인 키워드 함수로 대체 |
| ComplexityAnalyzer | 90% | 충분히 동작, MultiRequestDetector 내장 |
| MultiRequestDetector | 70% | 독립 모듈 없음, ComplexityAnalyzer에 병합 |
| AdaptiveRouter | 95% | 거의 완성, route_reason 문자열만 단순 고정 |
| RetrievalService | 90% | 멀티 세그먼트 검색 동작, retrieval_policy 분기 완성 |
| PromptFactory | 95% | topic/complexity 분기 완성, segment 지원 완성 |
| GenerationService | 85% | Ollama 통합, fallback 체계 완성. quality_signals 연산 미흡 |
| normalize_response | 90% | 스키마 정규화 완성, hallucination_flag 미계산 |
| /search API | 90% | routing_trace 포함 완성, TopicAnalyzer 분리 미적용 |
| /qa API | 85% | routing_hint 수신 및 전달 완성, segment_coverage 계산 단순 |
| Structuring | 85% | 4요소 추출 + NER 완성, supervision 연동 테스트 부재 |
| Ingestion | 95% | CSV/JSON 로드, PII 마스킹, 중복 제거 완성 |
| Tests (Unit) | 75% | 주요 계층 커버. E2E 통합 테스트 1종만 존재 |

---

## 2. 컴포넌트별 구현 현황 상세

### 2.1 Analyzer 계층

#### TopicAnalyzer
- **위치**: `app/api/routers/retrieval.py:122` (독립 클래스 없음)
- **현황**: `_detect_topic_type(query)` 인라인 함수로 구현. 키워드 딕셔너리 매핑으로 welfare / traffic / environment / construction / general 5종 분류.
- **한계**: MVP 명세의 `TopicAnalyzer` 클래스가 아닌 라우터 내부 private 함수. 테스트 대상에서 제외되어 있으며, 단독 호출 불가.
- **실제 분류 키워드**:
  - welfare: 복지, 급여, 기초생활, 수급, 임대주택
  - traffic: 도로, 교통, 신호, 불법주정차, 가로등
  - environment: 환경, 소음, 악취, 미세먼지, 폐기물
  - construction: 공사, 건축, 안전, 보수, 시설

#### ComplexityAnalyzer
- **위치**: `app/retrieval/analyzers/complexity_analyzer.py`
- **현황**: 완성. `build_analyzer_output(text, topic_type)` 공개 API로 topic_type 주입 → complexity 점수 계산 → request_segments 생성.
- **채점 가중치**: text_length(0.25), intent(0.20), constraint(0.20), entity(0.15), policy(0.20)
- **임계값**: low(<0.45), medium(0.45~0.75), high(≥0.75)
- **출력**: complexity_score, complexity_level, complexity_trace(세부 근거), request_segments, is_multi

#### MultiRequestDetector
- **위치**: `app/retrieval/analyzers/complexity_analyzer.py:146` (`_build_request_segments`)
- **현황**: ComplexityAnalyzer 내 `_build_request_segments()` private 함수로 구현. 구분자(및, 그리고, 콤마, 세미콜론)로 분리.
- **한계**: 독립 클래스/모듈 없음. MVP 명세의 `MultiRequestDetector` 독립 컴포넌트 아님.

---

### 2.2 Router 계층

#### AdaptiveRouter
- **위치**: `app/retrieval/router/adaptive_router.py`
- **현황**: 거의 완성.
  - `ROUTING_PARAMS_BY_COMPLEXITY`: low/medium/high 별 top_k, snippet_max_chars, chunk_policy 설정
  - `RETRIEVAL_POLICY_BY_TOPIC`: welfare→admin_policy, traffic/environment/construction→field_ops, general→general
  - `route()` → strategy_id, route_key, applied_params, route_reason, retrieval_policy 반환
- **출력 형식**:
  - strategy_id: `topic_{topic}_{level}_v1`
  - route_key: `{topic}/{complexity}`
- **미흡점**: route_reason이 고정 문자열("matched topic: X, complexity: Y") 수준. 분기 근거 설명이 단순함.

---

### 2.3 Retrieval 계층

#### RetrievalService
- **위치**: `app/retrieval/service.py`
- **현황**: 충분히 완성.
  - 멀티 세그먼트 쿼리 분리 + `dedupe_max_score` 병합 정책
  - `_apply_retrieval_policy()`: admin_policy(키워드 부스팅 강화), field_ops(직종/시설 키워드), general(기본)
  - `_normalize_record()`: case_id, entity_labels, chunk_text 정규화
  - 검색 결과에 strategy_id, route_key, topic_type, retrieval_policy, matched_segments 메타 포함
- **미흡점**:
  - entity_labels 파이프 구분 문자열로 ChromaDB에 저장 (파싱 시 분리 필요)
  - `_apply_retrieval_policy`에서 admin_policy/field_ops 키워드가 하드코딩

#### ChromaVectorStore
- **위치**: `app/retrieval/vectorstores/chroma_store.py`
- **현황**: SentenceTransformer 임베딩 + ChromaDB 연동 완성. where-clause 필터(category, region, created_at_ts, entity_labels) 지원.

---

### 2.4 Generation 계층

#### PromptFactory
- **위치**: `app/generation/prompts/prompt_factory.py`
- **현황**: 완성.
  - TOPIC_GUIDANCE: 5개 도메인별 지시문
  - COMPLEXITY_GUIDANCE: low(간결)/medium(구조화)/high(다단계)
  - request_segments 존재 시 섹션별 답변 지시 포함
  - 출력 스키마(answer, citations, limitations, structured_output) 프롬프트에 명시

#### GenerationService
- **위치**: `app/generation/service.py`
- **현황**: Ollama 통합 완성. 파싱 체계: strict → relaxed → fast_fallback 3단계.
- **미흡점**: retry는 단일 stage(default_only)만 구현. temperature=0.2 고정. Multi-turn이나 동적 retry 전략 없음.

#### normalize_response / validate_unified_contract
- **위치**: `app/generation/normalization/response_normalizer.py`
- **현황**: 완성. routing_trace 기본값 보완, structured_output(summary/action_items/request_segments) 강제화, latency_ms 객체 구성, quality_signals 구성.
- **미흡점**: `hallucination_flag`가 항상 `False` 하드코딩 (`app/api/routers/generation.py:511`). 실제 할루시네이션 검출 로직 없음.

#### CitationMapper / QAResponseValidator
- **위치**: `app/generation/citation/citation_mapper.py`, `app/generation/validators/qa_response_validator.py`
- **현황**: citation의 chunk_id/case_id 검증, ref_id 생성, [[출처 n]] 토큰 자동 삽입 완성.

---

### 2.5 Structuring 계층

#### StructuringService
- **위치**: `app/structuring/service.py`
- **현황**: 완성.
  - 4요소(observation/result/request/context) 추출 + 신뢰도 점수
  - NER(LOCATION/TIME/FACILITY/HAZARD/ADMIN_UNIT) 정규식 기반
  - `compute_confidence_score()`: 가중 평균 + entity 보너스
  - `validate_schema()`: 필수 필드, confidence 범위, evidence_span 검증
- **미흡점**: NER이 정규식 기반으로 어절 단위 오인식 가능. `supervision` 필드 연동 통합 테스트 없음.

---

### 2.6 API 계층

#### /api/v1/search
- **위치**: `app/api/routers/retrieval.py`
- **현황**: `_build_routing_payload()` → ComplexityAnalyzer + AdaptiveRouter 순차 호출. routing_hint + routing_trace SearchResponseData에 포함. 퍼포먼스 경고(2000ms) 로깅 포함.

#### /api/v1/qa
- **위치**: `app/api/routers/generation.py`
- **현황**: Week 6 계약 검증(`_validate_week6_qa_request`), routing_hint의 strategy_id / route_key 일관성 검사. `map_retrieval_to_qa_context()` 컨텍스트 버짓 적용. normalize_response 후 validate_unified_contract 호출.
- **미흡점**: `_derive_request_segments(query)` 가 search 단계와 별도로 QA에서 재계산 (routing_trace.request_segments 우선 사용하긴 하지만 fallback 경로에서 독립 재계산).

---

## 3. Analyzer → Router → Generation 데이터 유실 여부

### 3.1 전달 경로

```
[/search]
  _detect_topic_type(query)
    → topic_type: str

  build_analyzer_output(query, topic_type)
    → complexity_score, complexity_level, complexity_trace
    → request_segments, is_multi

  route_adaptive(topic_type, complexity_level, complexity_score)
    → strategy_id, route_key, retrieval_policy
    → applied_params(top_k, snippet_max_chars, chunk_policy)
    → route_reason

  SearchResponseData
    → routing_hint: {strategy_id, route_key, top_k, snippet_max_chars, chunk_policy}
    → routing_trace: {topic_type, complexity_level, complexity_score, request_segments,
                      complexity_trace, route_reason, applied_filters, retrieval_policy}

[/qa 수신]
  QARequest.routing_hint (strategy_id, route_key 검증)
  QARequest.routing_trace (topic_type, complexity_level, request_segments)

  PromptFactory.build(routing_trace)
    → topic_type → TOPIC_GUIDANCE 분기
    → complexity_level → COMPLEXITY_GUIDANCE 분기
    → request_segments → 섹션별 답변 지시

  normalize_response(routing_trace=routing_trace, ...)
    → 최종 QAResponse.routing_trace 포함
```

### 3.2 유실 여부 판정

| 필드 | /search 생성 | /qa 수신 | PromptFactory 사용 | normalize_response 보존 | 판정 |
|---|---|---|---|---|---|
| topic_type | ✅ | ✅ | ✅ | ✅ | 정상 |
| complexity_level | ✅ | ✅ | ✅ | ✅ | 정상 |
| complexity_score | ✅ | ✅ | — | ✅ | 정상 |
| complexity_trace | ✅ | ✅ | — | ✅ | 정상 (프롬프트 미사용은 의도적) |
| request_segments | ✅ | ✅ | ✅ | ✅ | 정상 |
| strategy_id | ✅ | ✅ (검증) | — | ✅ | 정상 |
| route_key | ✅ | ✅ (검증) | — | ✅ | 정상 |
| retrieval_policy | ✅ | — | — | △ | **주의**: /qa 라우터가 retrieval_policy를 routing_trace에서 참조하지 않음 |
| applied_filters | ✅ | ✅ | — | ✅ | 정상 |
| hallucination_flag | — | — | — | 항상 False | **결함**: 실제 계산 없이 하드코딩 |
| segment_coverage | — | — | — | 단순 이진값 | **결함**: request_segments 존재 여부만 판단 |
| citation_coverage | — | — | — | 이진값(1.0/0.0) | **미흡**: citation 개수 기반 비율 미계산 |

### 3.3 구조적 주의점

- `/qa`에서 `search_results`가 사전 제공되지 않으면 RetrievalService를 직접 호출하는데, 이 경우 routing_trace의 retrieval_policy가 검색에 반영되지 않을 수 있음 (routing_hint만 전달)
- `_derive_request_segments(query)`가 `/qa` 라우터 내에도 존재 (`:40`) → search에서 받은 request_segments와 QA 자체 계산 결과가 충돌 가능. 현재는 routing_trace 우선이지만 fallback 분기 존재.

---

## 4. MVP 대비 각 모듈별 미흡 사항

### 4.1 MVP 명세 vs 실제 구현 대응표

| MVP 명세 항목 | 실제 구현 상태 | 갭 |
|---|---|---|
| TopicAnalyzer 독립 모듈 | 라우터 내 `_detect_topic_type()` 함수 | 클래스화·테스트 미적용 |
| ComplexityAnalyzer 독립 모듈 | `ComplexityAnalyzer` 클래스 완성 | 완성 |
| MultiRequestDetector(보조) | `_build_request_segments()` 내장 | 독립 클래스 미분리, 단독 테스트 없음 |
| AdaptiveRouter topic+complexity | `AdaptiveRouter.route()` 완성 | 완성 |
| Topic/Complexity 분기 검색 | `_apply_retrieval_policy()` 완성 | 완성 |
| strategy별 결과 반환 + metadata | SearchResultItem에 포함 | 완성 |
| Topic-aware PromptFactory | TOPIC_GUIDANCE + COMPLEXITY_GUIDANCE | 완성 |
| normalize_response | `response_normalizer.py` 완성 | hallucination_flag 미계산 |
| `/search` routing_trace/hint 전달 | 완성 | 완성 |
| `/qa` routing_hint 수신 및 적용 | 완성 | segment_coverage 단순화 |
| 통합 데모 E2E 흐름 | `test_week6_search_to_qa_e2e_sample10.py` | 샘플 10건 고정. 시나리오 3종 미정 |
| Workbench API 계약 고정 | unified schema 완성 | 완성 |

### 4.2 모듈별 미흡 요약

**Analyzer 계층**
- `TopicAnalyzer`가 독립 클래스/파일 없이 라우터에 묻혀 있어, 단독 테스트·교체·고도화 불가
- 키워드 매핑이 각 도메인당 5개 수준으로 좁음 (복지 키워드에 "노인", "장애" 등 미포함)
- `MultiRequestDetector`가 별도 파일 없음 → 유지보수 분리 불가

**Router 계층**
- `route_reason` 설명이 단순 문자열 포맷 ("matched topic: X, complexity: Y"). UI에 표시될 경우 정보량 부족.
- `applied_filters`가 항상 빈 리스트(`[]`) → 실제 필터 조건이 routing_trace에 기록되지 않음

**Retrieval 계층**
- `_apply_retrieval_policy()` 키워드 목록이 소스코드에 하드코딩. 도메인 확장 시 코드 수정 필요.
- entity_labels ChromaDB 저장 시 "|" 구분 문자열 직렬화 → 필터 쿼리의 부분 매칭이 불안정

**Generation 계층**
- `hallucination_flag`가 항상 `False` (계산 로직 없음)
- `citation_coverage`가 이진값(citation 존재 시 1.0, 없으면 0.0). 실제 문서 커버리지 비율 미계산.
- `segment_coverage`가 request_segments 존재 여부만 체크 (1.0 or 0.0). 각 세그먼트가 실제로 답변에 반영되었는지 미검증.
- Ollama retry가 단일 온도(0.2) 고정. 파싱 실패 시 온도 조정이나 프롬프트 변경 없이 fallback.

**Structuring 계층**
- NER이 정규식 기반이라 어절 경계에서 오인식 발생 가능
- `supervision` 필드가 생성되나 downstream 파이프라인(retrieval 인덱싱)과의 연동 테스트 없음

**테스트**
- TopicAnalyzer 전용 단위 테스트 없음
- MultiRequestDetector 전용 단위 테스트 없음
- `hallucination_flag` 계산 단위 테스트 없음
- E2E 통합 테스트가 `test_week6_search_to_qa_e2e_sample10.py` 1종뿐
- MVP 정의의 "데모 시나리오 3종" 미구성

---

## 5. 앞으로 해야 할 구현 (컴포넌트별)

### 5.1 Analyzer 계층 (BE1 우선)

#### 우선순위 HIGH

**[A-1] TopicAnalyzer 클래스 독립 모듈화**
- 신규 파일: `app/retrieval/analyzers/topic_analyzer.py`
- 현재 `_detect_topic_type()` 로직을 `TopicAnalyzer` 클래스로 이전
- `analyze(text: str) -> dict` 인터페이스 정의 (topic_type, topic_confidence, matched_keywords)
- `app/retrieval/analyzers/__init__.py`에 export 추가
- `app/api/routers/retrieval.py`의 인라인 함수를 클래스 호출로 교체
- 단위 테스트 `app/tests/unit/test_topic_analyzer.py` 신규 작성

**[A-2] 도메인별 키워드 확장**
- welfare: "노인", "장애", "보육", "아동", "기초연금" 추가
- traffic: "주차", "과속", "횡단보도", "버스노선" 추가
- environment: "수질", "토양", "쓰레기", "재활용" 추가
- construction: "균열", "누수", "도로파손", "보도블록" 추가

#### 우선순위 MEDIUM

**[A-3] MultiRequestDetector 독립 파일 분리**
- 신규 파일: `app/retrieval/analyzers/multi_request_detector.py`
- `_build_request_segments()` 로직 이전 + `MultiRequestDetector` 클래스 래핑
- 구분자 목록 외부 설정 가능하도록 개방
- 단위 테스트 작성

---

### 5.2 Router 계층 (BE2)

#### 우선순위 MEDIUM

**[R-1] applied_filters 실제 기록**
- `_build_routing_payload()`에서 적용된 날짜/카테고리/지역 필터가 있을 경우 `applied_filters`에 기록
- 현재 항상 `[]` → 필터 전달 시 dict 리스트로 채울 것

**[R-2] route_reason 설명 강화**
- 단순 문자열("matched topic: X") 대신 구조화된 dict 또는 rich string 반환
- 예: `"welfare/high 경로 선택: 복지 키워드(수급) 감지, complexity_score=0.72, top_k=7"`
- UI 패널에서 라우팅 근거를 사용자에게 설명 가능한 수준으로 개선

---

### 5.3 Retrieval 계층 (BE2)

#### 우선순위 MEDIUM

**[Ret-1] retrieval_policy 키워드 외부화**
- admin_policy / field_ops 도메인 키워드를 `config.py` 또는 별도 `retrieval_policy_config.py`로 분리
- 하드코딩 제거 → 도메인 추가 시 코드 수정 불필요

**[Ret-2] entity_labels 저장 방식 개선**
- 현재 `"|".join(labels)` 직렬화 → ChromaDB where-clause 부분 매칭 불안정
- `$contains` 필터 활용하거나, 레이블당 별도 boolean 메타 필드로 분리 검토
- `chroma_validation.py` 필터 테스트 추가

#### 우선순위 LOW

**[Ret-3] 검색 결과 score 정규화**
- 현재 raw cosine similarity 반환. 0~1 범위 정규화 후 confidence 표시 권장.

---

### 5.4 Generation 계층 (BE3)

#### 우선순위 HIGH

**[G-1] hallucination_flag 실제 계산 구현**
- 위치: `app/api/routers/generation.py:511` (현재 `False` 하드코딩)
- 구현 방안:
  - 답변 문자열 내 citation 토큰(`[[출처 n]]`) 수 vs. 핵심 주장 문장 수 비율 계산
  - context에 없는 내용이 answer에 등장하는지 키워드 커버리지 체크 (간단한 heuristic)
  - `True` 조건: citation 없이 단언적 문장 3개 이상, 또는 context 키워드 커버리지 < 0.3
- 단위 테스트 작성

**[G-2] citation_coverage 비율 계산**
- 위치: `app/api/routers/generation.py:510` (현재 이진값)
- `len(response_citations) / max(len(search_results), 1)` 비율로 교체
- 0.0~1.0 실수 반환

**[G-3] segment_coverage 세그먼트별 검증**
- 위치: `app/api/routers/generation.py:512`
- 현재: `1.0 if routing_trace.get("request_segments") else 0.0`
- 개선: request_segments 각 항목이 answer 또는 structured_output.request_segments에 반영되었는지 키워드 매칭으로 체크
- `matched_count / total_segment_count` 비율 반환

#### 우선순위 MEDIUM

**[G-4] Ollama retry 전략 강화**
- 현재 temperature=0.2 고정 단일 시도
- 파싱 실패 시 temperature를 0.1로 낮추거나 프롬프트에 "반드시 JSON만 출력" 강조 추가
- `app/generation/service.py`의 `generate_qa()` retry 루프 수정

**[G-5] context_mapper 토큰 예산 동적 조정**
- 현재 2048 고정 (`app/generation/context_mapper.py`)
- `settings.py`에서 읽어오도록 연결 (현재 config에 model_ctx_tokens 없음)
- Ollama 모델별 컨텍스트 길이 설정 가능하도록 개방

---

### 5.5 Structuring 계층 (BE1)

#### 우선순위 MEDIUM

**[S-1] supervision 연동 통합 테스트**
- `extract_supervision()` 결과가 Retrieval 인덱싱 시 올바르게 저장되는지 검증
- `app/tests/integration/` 에 structuring → indexing 흐름 통합 테스트 추가

**[S-2] NER 커버리지 확인**
- 현재 정규식 패턴 어절 경계 오인식 사례 수집
- 필요 시 형태소 기반 후처리 추가 또는 패턴 보완

---

### 5.6 API / E2E (공통)

#### 우선순위 HIGH

**[E-1] 데모 시나리오 3종 고정**
- MVP DoD 항목 5 요건: "E2E 시나리오 3종 고정 및 동결"
- 시나리오 구성 예시:
  - 시나리오 1: 복지/단순 (welfare/low) — 수급 자격 문의
  - 시나리오 2: 건설/복합 (construction/high) — 균열 보수 + 관리비 이의제기 복합 민원
  - 시나리오 3: 환경/중간 (environment/medium) — 소음 민원
- `app/tests/integration/test_demo_scenarios.py` 작성
- 각 시나리오별로 `/search` → `/qa` 완주 + routing_trace 필드 검증 포함

**[E-2] /qa 내 request_segments 이중 계산 제거**
- `app/api/routers/generation.py:40` `_derive_request_segments()` 함수 제거 또는 routing_trace 우선 사용 명확화
- search 단계 routing_trace.request_segments를 항상 우선 사용하도록 코드 정리

#### 우선순위 MEDIUM

**[E-3] TopicAnalyzer 단위 테스트 작성**
- [A-1] 완료 후 `app/tests/unit/test_topic_analyzer.py` 작성
- 각 도메인 키워드별 정분류 + "일반" fallback 케이스 포함

**[E-4] applied_filters 필드 채우기 (SearchFilters 연동)**
- SearchRequest의 filters 필드가 실제 검색에 적용될 경우, routing_trace.applied_filters에 기록
- 현재 항상 빈 리스트

---

## 6. MVP DoD 체크리스트 (현재 상태)

| DoD 항목 | 상태 | 비고 |
|---|---|---|
| 1. 민원 선택 시 analyzer 결과(topic/complexity/segment) 생성 | ✅ 완성 | TopicAnalyzer가 인라인 함수이나 기능 동작 |
| 2. 검색에서 adaptive 전략 선택 + routing_trace 응답 포함 | ✅ 완성 | |
| 3. QA에서 routing_hint 수신 → 답변/citation 생성 | ✅ 완성 | |
| 4. Workbench 우측 패널 답변/citation 표시 | ⬜ FE 미확인 | 백엔드 API 준비 완료, FE 연동 확인 필요 |
| 5. 답변 초안 검토/수정 가능 | ⬜ FE 미확인 | |
| 6. 1-5 동일 데모 흐름 중단 없이 연속 동작 | ⚠️ 부분 완성 | E2E 통합 테스트 1종, 시나리오 3종 미정 |

---

## 7. 결론 및 권장 작업 순서

1. **[A-1] TopicAnalyzer 클래스 분리** — 독립 모듈 없이 테스트 불가. 1~2시간 작업.
2. **[G-1] hallucination_flag 계산** — 항상 False는 quality_signals 신뢰도 파괴.
3. **[E-1] 데모 시나리오 3종 고정** — MVP DoD 직결. E2E 테스트 없으면 데모 중 실패 위험.
4. **[E-2] request_segments 이중 계산 제거** — 잠재적 불일치 원인 제거.
5. **[G-2], [G-3] coverage 지표 실제 계산** — quality_signals 의미 있는 값으로 채우기.
6. **[A-2] 도메인 키워드 확장** — 분류 정확도 향상.
7. **[R-1], [R-2] Router applied_filters / route_reason 강화** — UI 가시화 품질 향상.
8. **[Ret-1] retrieval_policy 키워드 외부화** — 유지보수성 개선.

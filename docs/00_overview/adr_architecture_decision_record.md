# ARD (Architecture Decision Record)

문서 버전: v2.2  
작성일: 2026-03-26  
최신화: 2026-05-07 (하이브리드 구조화 아키텍처 반영, TopicAnalyzer 독립 클래스화 결정 추가)

## 1. 문서 목적

본 문서는 프로젝트의 핵심 아키텍처 결정을 기록하고, 변경 시 근거와 트레이드오프를 추적하기 위한 기준 문서다. 이전 변경 기록은 90_archive/week4_overview/ 에 유지하고 있다.

## 2. 현재 유효 결정 요약

- On-device 우선 처리
- Adaptive RAG 단계 적용
- 계약 기반 API 통합
- Week5-8은 코어 구현 + 데모 동결 중심 운영
- 라우팅 기준은 topic + complexity 중심으로 운영

## 3. 결정 기록

## 3. 결정 기록

## ARD-001: On-Device 우선 아키텍처 채택

- 상태: 승인(Active)
- 맥락:
  - 민원 데이터는 개인정보 포함 가능성이 높고 외부 API 사용 제약이 큼
  - 데모와 운영 모두에서 네트워크 의존을 낮춰야 함
- 결정:
  - LLM 추론과 검색을 로컬 환경 중심으로 설계
  - Ollama 기반 로컬 모델 실행을 표준 경로로 채택
- 대안:
  - 클라우드 LLM API 중심 구조
  - 하이브리드(클라우드+로컬) 구조
- 결과:
  - 장점: 보안/프라이버시, 오프라인 시연 안정성 향상
  - 단점: 하드웨어 자원 제약(OOM/지연) 대응 필요
  - 후속: OOM 폴백, 양자화(4-bit/8-bit) 실험을 품질 과제로 유지

## ARD-002: 도메인 분리형 모듈 아키텍처 채택

- 상태: 승인(Active)
- 맥락:
  - 팀 병렬 개발과 유지보수성을 위해 모듈 경계가 필요
- 결정:
  - `app/` 하위에 `ingestion`, `structuring`, `retrieval`, `generation`, `ui`, `api`, `core`를 분리
  - API/서비스/UI를 결합하지 않고 서비스 계층을 공유
- 대안:
  - 단일 서비스 파일 중심 모놀리식 구조
  - 기능별 분리 없는 라우터 중심 구조
- 결과:
  - 장점: 책임 분리, 테스트 범위 명확화, 병렬 작업 용이
  - 단점: 초기 인터페이스 계약 관리 비용 증가
  - 후속: 계약 문서 우선(Week2 인터페이스)으로 충돌 완화

## ARD-003: FastAPI + Streamlit 이원화

- 상태: 승인(Active)
- 맥락:
  - API 계약 안정성과 데모 제작 속도를 동시에 확보해야 함
- 결정:
  - 백엔드 API는 FastAPI, 데모 UI는 Streamlit으로 분리
  - UI는 API 계약을 통해서만 백엔드와 통신
- 대안:
  - 단일 웹 프레임워크(예: React+별도 API)로 통합
  - UI 없이 API-only 데모
- 결과:
  - 장점: 구현 속도와 계약 안정성 균형
  - 단점: FE/BE 간 계약 불일치 가능성 존재
  - 후속: 공통 응답 래퍼와 request_id 기반 추적 규칙 고정

## ARD-004: Schema-First + Validation-First 데이터 계약

- 상태: 승인(Active)
- 맥락:
  - 구조화 결과가 검색/QA 품질의 기반이며, 필드 불일치 시 전체 파이프라인이 흔들림
- 결정:
  - 핵심 객체(`StructuredCivilCase`, `SearchChunk`, `SearchResult`, `QAResponse`)를 계약 중심으로 고정
  - 입력 단계는 일부 유연 허용, 저장/출력 단계는 엄격 강제
  - 엔티티 라벨 정규화 규칙(`TYPE -> HAZARD` 등) 서버 강제
- 대안:
  - 모듈별 자유 포맷 사용 후 후처리 변환
  - 검증 최소화(런타임 실패 시 대응)
- 결과:
  - 장점: 파이프라인 안정성, 디버깅 용이성 향상
  - 단점: 초기 스키마 합의 비용 증가
  - 후속: 스키마 변경은 문서/코드 동시 수정 원칙 유지

## ARD-005: Week2 공통 API 래퍼 표준화

- 상태: 승인(Active)
- 맥락:
  - FE/BE 간 에러 처리 형태가 다르면 예외 흐름이 복잡해짐
- 결정:
  - 성공: `success`, `request_id`, `timestamp`, `data`
  - 실패: `success`, `request_id`, `timestamp`, `error(code,message,retryable,details)`
  - FastAPI 기본 422도 `VALIDATION_ERROR` 래퍼로 통일
- 대안:
  - 엔드포인트별 개별 응답 형식
  - FastAPI 기본 422 포맷 그대로 사용
- 결과:
  - 장점: 클라이언트 처리 단순화, 운영 로그 일관화
  - 단점: 프레임워크 기본 응답과 괴리로 추가 핸들러 유지 필요
  - 후속: 신규 라우터 추가 시 공통 래퍼 준수 검증 필수

## ARD-006: KST(+09:00) 시각 정책 단일화

- 상태: 승인(Active)
- 맥락:
  - naive datetime, `Z`, `+09:00` 혼용 시 필터/비교 오류 가능
- 결정:
  - 출력 시각 필드(`created_at`, `structured_at`, `timestamp`, `generated_at`)는 ISO-8601 `+09:00`로 통일
  - 타임존 없는 입력은 내부 정규화에서 KST 부여
- 대안:
  - UTC(`Z`) 단일화
  - 입력 포맷 그대로 보존
- 결과:
  - 장점: 검색 필터 및 정렬 일관성 향상
  - 단점: 외부 UTC 연동 시 변환 로직 필요
  - 후속: 모든 신규 datetime 필드는 동일 정책 적용

## ARD-007: Retrieval 스택 고정 (BGE-m3 + ChromaDB)

- 상태: 승인(Active)
- 맥락:
  - MVP 일정상 빠른 로컬 구축과 재현 가능한 실험 환경이 필요
- 결정:
  - 임베딩: `BAAI/bge-m3`
  - 벡터 저장소: `ChromaDB`
  - 초기 검색은 Top-K 시맨틱 검색 + 메타데이터 필터 중심
- 대안:
  - FAISS 우선
  - 하이브리드 검색(BM25+dense)을 초기부터 기본 적용
- 결과:
  - 장점: 로컬 개발 생산성, 빠른 PoC
  - 단점: 대규모 트래픽/복합 쿼리 최적화 여지
  - 후속: 성능 병목 시 하이브리드/리랭킹은 단계적 도입

## ARD-008: RAG 전략 단계 적용 (단일 -> Adaptive)

- 상태: 승인(Active)
- 맥락:
  - 민원 길이/주제/복합도 편차가 커 adaptive 필요성이 있으나, 초기 안정화가 선행되어야 함
- 결정:
  - 1단계: 단일 RAG baseline 확정
  - 2단계: 길이/주제/단일-복합 분기 adaptive RAG 도입
  - 전환은 E2E 안정화 게이트 충족 후 진행
- 대안:
  - 초기부터 full adaptive 적용
  - adaptive 미적용 고정 전략 유지
- 결과:
  - 장점: 일정 리스크 제어 + 실험 비교 가능성 확보
  - 단점: 중간 단계에서 기능 중복 관리 필요
  - 후속: baseline 대비 개선치(Recall@5, F1, citation 정합성, latency) 정량 비교

## ARD-009: 관측성/평가 내장 아키텍처

- 상태: 승인(Active)
- 맥락:
  - 품질 개선 여부를 감으로 판단하면 후반 통합 리스크 증가
- 결정:
  - 로그를 `api`, `pipeline`, `evaluation`로 분리 저장
  - 파싱 실패/검증 오류를 코드화해 운영 데이터로 축적
- 대안:
  - 최소 로그만 유지
  - 수동 측정 중심 운영
- 결과:
  - 장점: 병목 추적과 품질 회귀 탐지 용이
  - 단점: 초기 계측 코드/로그 관리 비용 증가
  - 후속: 지표 리포트 자동화 수준 점진 강화

## ARD-010: 역할 오너십 기반 아키텍처 거버넌스

- 상태: 승인(Active)
- 맥락:
  - 4인 병렬 개발에서 기능 책임이 겹치면 결정 지연과 계약 충돌이 증가
- 결정:
  - FE: 사용자 흐름, 상태 UI(success/loading/error/empty), 데모 시나리오 책임
  - BE1: 데이터 정제/PII/구조화 품질 및 평가 기준 책임
  - BE2: 인덱싱/검색/RAG API 연결과 검색 품질 책임
  - BE3: 파싱 안정성/검증/근거 정합성/성능 폴백 책임
  - 모듈 경계 침범 대신 계약 문서로 상호 연동한다.
- 대안:
  - 기능별 공동 소유(공동 수정 중심)
  - UI/BE 경계 없는 빠른 임시 통합
- 결과:
  - 장점: 책임 소재와 의사결정 채널 명확화
  - 단점: 오너 병목 발생 가능
  - 후속: 오너 부재 시 대체 승인 경로를 주간 점검에서 지정

## ARD-011: 데모 우선 UX 안정성 규약

- 상태: 승인(Active)
- 맥락:
  - 졸업작품 특성상 기능 완성뿐 아니라 시연 중단 없는 UX가 핵심
- 결정:
  - FE는 핵심 화면(업로드/검색/QA)에서 상태 4종(success/loading/error/empty)을 필수 처리
  - 백엔드 오류는 코드/사용자 메시지를 분리해 전달
  - citation, validation, limitation을 UI에서 가시화 가능한 데이터로 표준 노출
- 대안:
  - 정상 응답 중심 UX만 우선 구현
  - 장애 시 raw error 노출
- 결과:
  - 장점: 데모 신뢰성, 장애 상황 복구력 향상
  - 단점: 초기 UI 구현 복잡도 상승
  - 후속: 데모 시나리오 3종 기준으로 UX 회귀 점검

## ARD-012: Week2 계약 우선순위와 동결(freeze) 운영

- 상태: 승인(Active)
- 맥락:
  - Week2에 계약 문서가 다수 존재하여 우선순위 부재 시 동일 필드 충돌 발생
- 결정:
  - 충돌 시 우선순위: Week2 인터페이스 문서 > schema_contract > api_spec > Week1 문서
  - 금지 별칭(`id`, `submitted_at`, `src` 등) 사용 금지
  - datetime 표기는 `+09:00` 형식 고정
- 대안:
  - 문서별 독립 운영 후 구현체에서 흡수
  - 코드 우선, 문서 사후 반영
- 결과:
  - 장점: FE/BE 계약 불일치 조기 차단
  - 단점: 문서 동기화 비용 증가
  - 후속: 계약 변경은 단일 PR로 동시 반영 원칙 유지


## ARD-013: FE 아키텍처 전환 및 3단 Workbench UX 채택

- 상태: 승인(Active)
- 날짜: 2026-04-09

### 1) Context (도입 배경)

- 기존 Streamlit 기반 UI는 빠른 프로토타이핑에는 유리했지만, 실무자 중심의 복합 워크플로우(실시간 목록 + 상세 검토 + 초안 편집)를 안정적으로 표현하기에 한계가 있었다.
- Week5-8의 핵심 목표가 Adaptive RAG 코어 구현 결과를 명확히 보여주는 데모 완성으로 이동하면서, 화면 구조와 상태 관리의 확장성이 필요해졌다.
- 특히 민원 담당자 동선 기준으로 "민원 선택 -> 진행 상태 확인 -> 근거 기반 답변 검토/편집"을 한 화면에서 처리할 수 있는 구조가 요구되었다.

### 2) Decision (결정 사항)

- FE 스택을 Streamlit에서 React/Next.js로 전환한다.
- BE는 FastAPI를 유지하고, FE는 FastAPI API 계약을 소비하는 분리형 구조로 고정한다.
- UX는 3단 분할 통합 Workbench를 채택한다.
  - 좌측: 네비게이션(민원 선택, 워크벤치, 관리자 대시보드)
  - 중앙: 실시간 민원 목록 및 상태 관리
  - 우측: AI 어시스턴트 패널(요약, 유사 민원 검색, 답변 초안 검토/편집)

### 3) Consequences (기대 효과 및 한계)

- 기대 효과
  - Adaptive RAG 처리 결과를 역할 동선에 맞게 명확히 시각화할 수 있다.
  - 데모 완성도와 설득력이 높아진다.
  - 이후 기능 확장(권한, 워크플로우 상태, 편집 이력)에 유리하다.
- 한계/트레이드오프
  - FE 개발 복잡도와 초기 구현 비용이 증가한다.
  - API 계약 동기화 부담이 증가한다.
  - 팀 내 FE/BE 통합 테스트 루틴을 더 엄격히 운영해야 한다.

## ARD-014: Adaptive Router 복잡도 기반 전환 (length/is_multi 중심 분기 대체)

- 상태: 승인(Active)
- 날짜: 2026-04-10

### 1) Context (도입 배경)

- 기존 length_bucket/is_multi 중심 분기는 구현 단순성은 높지만, 실제 민원 난이도와 검색 난도를 충분히 설명하지 못하는 한계가 있었다.
- 특히 같은 길이여도 요청 의도 수, 제약 조건 수, 정책 참조 밀도에 따라 retrieval/generation 복잡도가 크게 달라졌다.
- Week5-8 목표가 데모 관통 안정성과 설명 가능성인 만큼, 라우팅 근거가 사용자에게 더 납득 가능해야 했다.

### 2) Decision (결정 사항)

- `topic_type`은 유지하고, 라우팅 핵심 축을 `complexity_level`로 전환한다.
- 신규 분석 모듈 `ComplexityAnalyzer`를 도입해 아래 지표를 기반으로 `complexity_score`, `complexity_level`을 산출한다.
  - `intent_count`
  - `constraint_count`
  - `entity_diversity`
  - `policy_reference_count`
  - `cross_sentence_dependency`
- `route_key`는 `{topic_type}/{complexity_level}` 포맷으로 고정한다.
- `length_bucket`, `is_multi`는 보조 분석/표시 용도로만 유지하고 라우팅 핵심 기준으로는 사용하지 않는다.

### 3) Consequences (기대 효과 및 한계)

- 기대 효과
  - 라우팅 근거의 설명 가능성이 향상된다.
  - retrieval 파라미터를 실제 난이도에 더 밀접하게 조정할 수 있다.
  - FE에서 `complexity_trace`를 통해 전략 선택 이유를 사용자에게 직관적으로 제시할 수 있다.
- 한계/트레이드오프
  - 초기 복잡도 규칙 설계 비용이 증가한다.
  - Analyzer/Router/API/UI 문서 동시 변경이 필요해 동기화 부담이 커진다.
- 후속
  - PRD/WBS/MVP/specs/issues/manual을 동일 기준으로 동기화한다.
  - `/search`, `/qa` 계약에서 `routing_trace` 내 complexity 필드를 필수화한다.

## ARD-015: 구조화 서비스 하이브리드 아키텍처 전환 (Rule NER + LLM 4요소 추출)

- 상태: 승인(Active)
- 날짜: 2026-05-07

### 1) Context (도입 배경)

- 기존 4요소(observation/result/request/context) 추출은 단어 점수 기반 휴리스틱(`_score_candidate`, `_pick_best`, `_split_segments` 등)으로 구현되어 있었다.
- 민원 표현의 다양성을 수용하지 못하고, 키워드 룰이 비대해지면서 유지보수 비용이 높아졌다.
- LOCATION NER이 하드코딩된 6개 지명(`서울`, `경기`, `안양` 등)에만 의존하여 커버리지가 낮았다.
- Rule-based 4요소 추출과 Rule-based NER이 동일 클래스에 혼재해 역할 경계가 불분명했다.
- Week8 기준 Ollama 인프라가 안정화되어 로컬 경량 LLM을 구조화에 활용할 여건이 마련되었다.

### 2) Decision (결정 사항)

- 구조화 파이프라인을 3단계 하이브리드 구조로 전환한다.
  - **Stage 1 — Rule-based Entity Extractor**: 정규식·키워드로 확실하게 추출 가능한 객관적 명사(ADMIN_UNIT/TIME/FACILITY/HAZARD/LOCATION)만 담당. LOCATION은 기존 하드코딩 목록을 `동·읍·면·리·로·길` 패턴 기반으로 교체.
  - **Stage 2 — LLM Semantic Extractor**: Ollama EXAONE 3.0 (7.8B-Instruct)로 4요소를 JSON 추출. `format="json"` + `FourElementsLLMOutput.model_validate()` 조합으로 Instructor 없이 출력 규격 강제. 파싱 실패 시 temperature 0.1→0.0 재시도 1회 후 빈 Fallback 반환.
  - **Stage 3 — ResultMerger**: Stage 1/2 결과를 병합. LLM 텍스트를 원문에서 exact→partial→inferred 순서로 탐색해 evidence_span 결정. non-null 필드 비율(4/3/2/1/0)로 confidence(0.90/0.82/0.75/0.70/0.0) 산정.
- `validate_schema()`에 `extraction_method` 파라미터를 추가한다. `"hybrid"`/`"llm"`/`"fallback"` 모드에서 span 범위 오류 및 텍스트 불일치를 error에서 warning으로 완화한다. `"rule"` 모드는 기존과 동일하게 엄격 검증을 유지한다.
- 구조화 전용 Ollama 모델(`STRUCTURING_MODEL`, 기본값 `exaone3:7.8b-instruct`)을 QA 생성 모델(`OLLAMA_MODEL`)과 분리한다. `STRUCTURING_TIMEOUT`, `STRUCTURING_MAX_TEXT_LEN`도 독립 환경 변수로 제어한다.
- 신규 파일: `app/structuring/schemas.py`, `app/structuring/llm_extractor.py`, `app/structuring/merger.py`.
- `service.py`에서 4요소 추출 관련 메서드(`extract_four_elements`, `_split_segments`, `_sentence_candidates`, `_score_candidate`, `_pick_best`, `_score_to_confidence` 등) 전량 제거. 880줄 → 310줄.

### 3) Consequences (기대 효과 및 한계)

- 기대 효과
  - 민원 표현 다양성 대응: LLM이 문맥을 이해해 휴리스틱으로 잡기 어려운 4요소를 추출한다.
  - 유지보수성 향상: 키워드 룰 비대 문제 해소. 도메인 확장 시 프롬프트 수정만으로 대응 가능.
  - 역할 분리 명확화: NER(Rule)과 의미 추출(LLM)의 경계가 파일 수준으로 분리된다.
  - Ollama 미기동·타임아웃 시 빈 4요소 Fallback으로 파이프라인이 중단되지 않는다.
  - `structured_by`/`extraction_meta` 필드로 추출 경로와 LLM 지연·span 품질을 추적 가능.
- 한계/트레이드오프
  - Ollama EXAONE 모델 추가 로딩으로 구조화 지연이 증가한다(~1~3초).
  - LLM이 원문과 다른 텍스트를 반환할 경우 evidence_span이 `inferred`가 되어 span 정확도가 낮아진다.
  - Fallback 시 4요소가 모두 비어 있어 retrieval 인덱스의 chunk_text 품질이 저하될 수 있다.
- 후속
  - `span_source="inferred"` 비율을 운영 지표로 수집해 프롬프트 개선 여부를 판단한다.
  - Fallback 발생률이 높을 경우 ConnectError에도 재시도 또는 대기 로직 도입을 검토한다.
  - `result.status="insufficient"` 처리 통합 테스트를 추가한다.

## ARD-016: TopicAnalyzer 독립 클래스화 및 점수 기반 분류 전환

- 상태: 승인(Active)
- 날짜: 2026-05-07

### 1) Context (도입 배경)

- 기존 `_detect_topic_type(query)` 함수는 `app/api/routers/retrieval.py:122`에 private 함수로 매몰되어 있어 단독 테스트·교체·고도화가 불가능했다.
- 키워드 딕셔너리 순서(삽입 순서) 의존의 first-match 방식으로 인해 복합 맥락 쿼리에서 오분류가 발생했다.
  - 예: "복지시설 건축 허가" → welfare 반환 (실제 의도: construction)
- 카테고리당 키워드가 5개(총 25개)에 불과해 한국어 행정 민원 도메인 어휘를 극히 일부만 커버했다.
- `ComplexityAnalyzer`와 달리 독립 클래스/파일이 없어 역할 경계가 불일치했다.
- `topic_type`은 `retrieval_policy(admin_policy/field_ops/general)` 결정의 1차 입력이므로 오분류 시 검색 전략 전체가 틀어지는 고위험 컴포넌트였다.

### 2) Decision (결정 사항)

- `app/retrieval/analyzers/topic_analyzer.py`를 신규 파일로 생성하고 `TopicAnalyzer` 클래스를 독립 구현한다.
- `_detect_topic_type` 함수를 `retrieval.py`에서 제거하고, `detect as detect_topic` import로 교체한다.
- **점수 기반 집계**: first-match 대신 키워드별 가중치 합산 후 최고 점수 카테고리를 선택한다.
- **키워드 대폭 확장**: 카테고리당 50개(총 200개+) 키워드로 확장. 고유성이 높은 키워드(예: `포트홀`, `터파기`, `긴급복지`)는 가중치 1.5, 공통 키워드(예: `도로`, `교통`)는 가중치 0.8~0.9.
- **기관명 필터**: `환경부`, `교통공단`, `안전교육` 등 false-positive 유발 패턴을 분류 전 제거한다.
- **신뢰도(confidence)**: 전체 점수 합 대비 top-1 점수 비율로 0~1 정규화. 0.40 미만 시 "general"로 강등.
- **모호성(is_ambiguous)**: top-1과 top-2 점수 차이가 top-1의 15% 이하이면 `is_ambiguous=True`, `secondary_topic` 반환.
- **띄어쓰기 정규화**: 키워드와 쿼리 모두 공백 제거 후 비교해 "기초 생활" / "기초생활" 동일 처리.
- 모듈 레벨 `analyze(text)`, `detect(text)` 편의 함수를 제공해 `ComplexityAnalyzer`와 API 패턴을 통일한다.

### 3) Consequences (기대 효과 및 한계)

- 기대 효과
  - `TopicAnalyzer`를 독립 단위 테스트로 검증 가능해진다.
  - 키워드 확장·가중치 조정을 라우터 코드 변경 없이 수행할 수 있다.
  - first-match 편향 제거로 복합 맥락 쿼리 분류 정확도 향상.
  - 기관명 등 false-positive 오분류 차단.
  - `confidence`, `is_ambiguous`를 라우터가 활용해 routing 파라미터를 보수적으로 조정할 수 있는 기반 마련.
- 한계/트레이드오프
  - 점수 기반 집계라도 키워드 기반의 본질적 한계(미등록 어휘, 신조어, 문맥 미감지)는 잔존한다.
  - 가중치 초기값이 경험적으로 설정되어 있어 실제 민원 데이터로 검증·조정이 필요하다.
- 후속
  - confidence < 0.40 비율을 운영 지표로 수집해 임베딩 기반 fallback(방향 B) 도입 여부를 판단한다.
  - `is_ambiguous` 케이스를 라우터에서 `top_k` 보수적 증가로 연동한다 (week8 P1).
  - 부산시 행정 기관명 목록 기반으로 `_NEGATIVE_PATTERNS` 확장 (하드코딩 또는 크롤링, 추후 결정).
  - 임베딩 토픽 센트로이드 fallback(`EmbeddingTopicClassifier`) 구현: week8 P2/P3 (WBS 방향 B 참조).

## 4. 후속 액션

- PRD/WBS/MVP/dev_stack/folder_structure/FE manual을 본 결정과 정렬한다.
- Week5-6에 API 필드(`routing_trace`, `routing_hint`, `structured_output`)를 동결한다.
- Week7부터 UI 기능 추가보다 통합 안정화에 집중한다.

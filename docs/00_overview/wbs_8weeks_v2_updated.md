# 8주 WBS 문서 (Adaptive RAG Demo Focus)

문서 버전: v4.1  
작성일: 2026-03-11  
최신화: 2026-04-10 (복잡도 기반 라우팅 기준 반영)

## 1. 문서 목적

본 문서는 8주 프로젝트의 남은 기간(Week5-8) 동안 팀이 Adaptive RAG 코어 로직 구현과 데모 UI 완성에만 집중하도록 실행 계획을 고정한다.

## 2. 운영 원칙

- Week1-4 세부 태스크는 완료 사인오프로 묶고 재논의하지 않는다.
- Week5-8은 코어 모듈 개발과 E2E 데모 흐름 관통 구현만 수행한다.
- 지표 확장, 추가 벤치마크, 리팩토링 중심 태스크는 배치하지 않는다.
- 모든 주차 완료 기준은 기능 동작 검증(입력 -> UI 출력)으로 판단한다.

## 3. 역할 정의

| 역할 | 담당자 | 핵심 책임 |
| --- | --- | --- |
| FE | 도훈 | Next.js Workbench UI, 상태/동선, BE 결과 가시화 |
| BE1 | 현기 | Length/Topic/Multi Analyzer 메타데이터 생성 |
| BE2 | 민건 | Adaptive Router(주제+복잡도), Retrieval 전략 분기, retrieval trace |
| BE3 | 현석 | Topic-aware Prompt, normalize_response, /qa 통합 |

## 4. 주차별 요약

| 주차 | 상태 | 목표 | 핵심 산출물 |
| --- | --- | --- | --- |
| Week1-4 | 완료 | 단일 RAG + Baseline + M2 사인오프 완료 | 완료 보고 및 운영 기록 |
| Week5 | 진행 | Complexity 기반 Adaptive 분기 + 검색/생성 전달 | ComplexityAnalyzer, AdaptiveRouter(1차), routing_trace |
| Week6 | 계획 | Topic/Multi 분기 + Prompt/Schema 통합 | TopicAnalyzer, PromptFactory, normalize_response |
| Week7 | 계획 | BE->FE 데모 관통 통합 및 Workbench UX 고정 | 3단 Workbench E2E 시연 경로 |
| Week8 | 계획 | 데모 동결, 리허설, 발표 산출물 마감 | 최종 데모 빌드/시나리오/문서 동결 |

## 5. 완료 사인오프 (Week1-4)

- Week1-4는 기획/단일 RAG/Baseline 관련 세부 작업을 완료한 것으로 사인오프한다.

## 6. 상세 WBS (Week5-8)

## Week5: Complexity Adaptive Core 구현

### 목표
- 복잡도 기반 분기(low/medium/high)를 실제 검색/생성 체인에 연결한다.

### FE
- 검색 결과 카드에 `routing_trace.complexity_level`, `routing_trace.complexity_score`, `strategy_id` 표시.
- 검색 -> QA 전환 시 `routing_hint` 전달 상태를 UI에서 유지.

### BE1
- `LengthAnalyzer.analyze(text)` 구현.
- `MultiRequestDetector.detect(text)` 1차 룰 구현(요청문 분리 포함).

### BE2
- `AdaptiveRouter.route(topic_type, complexity_level, complexity_score)` 1차 구현(복잡도 우선).
- 복잡도 레벨별 `top_k`, `snippet_max_chars`, `chunk_policy` 적용.

### BE3
- `/search` 응답에 `routing_trace` 포함.
- `/qa` 요청 `routing_hint` 수신/전달 경로 연결.

### 완료 기준
- 입력 질의가 complexity level로 분기되고, 동일 `strategy_id`가 검색 응답과 QA 응답에 모두 노출된다.

## Week6: Topic/Multi + Unified Output 구현

### 목표
- 주제/복합 분기를 반영한 generation 통합과 응답 정규화를 완료한다.

### FE
- 단일/복합 요청 UI 렌더링 분기(`request` list 대응).
- topic badge 및 strategy badge 표시 고정.

### BE1
- `TopicAnalyzer.classify(text, category, entity_labels)` 구현.
- `ComplexityAnalyzer.analyze(text, topic_type)` 구현.
- analyzer 출력을 `{topic_type, complexity_level, complexity_score, complexity_trace, request_segments}`로 통일.

### BE2
- topic_type별 retrieval 분기(field_ops/admin_policy) 적용.
- retrieval trace에 `route_key`, `applied_filters` 포함.

### BE3
- `PromptFactory.build(query, context, routing_trace)` 구현.
- `normalize_response(payload)`로 unified schema 확정.

### 완료 기준
- topic/multi 분기 입력에 대해 `/qa`가 `structured_output` + `routing_trace`를 일관 반환한다.

## Week7: 3단 Workbench E2E 통합

### 목표
- FastAPI + Next.js 기반 통합 워크벤치 데모 흐름을 고정한다.

### FE
- 3단 분할 Workbench 구현:
  - 좌측: 민원 선택/워크벤치/관리자 대시보드 네비게이션
  - 중앙: 실시간 민원 목록/상태 관리
  - 우측: AI 패널(요약/유사민원/답변초안 검토/편집)
- 상태 UX(success/loading/error/empty) 통일.

### BE1
- Workbench 중앙 목록에 필요한 구조화/분류 요약 필드 제공.

### BE2
- 우측 AI 패널용 유사 민원 목록 API 응답을 Workbench 형식으로 고정.

### BE3
- 답변 초안/근거/제약사항 응답 스키마를 편집 가능한 형태로 고정.

### 완료 기준
- 단일 민원 선택 후 우측 패널에서 답변과 citation이 생성/표시되고, 수정 가능한 초안 영역이 동작한다.

## Week8: 데모 동결 및 발표 준비

### 목표
- 기능 변경을 중지하고 데모 시나리오와 문서를 동결한다.

### FE
- 시연 동선 3종을 클릭 순서 문서와 일치하도록 고정.

### BE1/BE2/BE3
- E2E 시연 중 필요한 로그/추적 정보 최소 세트 유지.
- 스키마 변경 금지, 버그 픽스만 허용.

### 완료 기준
- 데모 시나리오 3종이 동일 워크벤치 UX에서 연속 실행된다.

## 7. 주차 게이트 (기능 중심)

- Gate W5: 복잡도 분기 라우팅 trace가 검색/생성/화면에서 확인 가능.
- Gate W6: topic/multi 분기 후 unified schema가 UI에서 그대로 렌더 가능.
- Gate W7: 3단 Workbench에서 실시간 목록/AI 패널 연동 완료.
- Gate W8: 기능 동결 상태로 리허설 시나리오 연속 성공.

## 8. 금지 항목 (Week5-8)

- 추가 지표 측정/리포트 확장 태스크
- 모델 벤치마크 확장 태스크
- 리팩토링 중심 태스크
- 예외 처리 고도화만을 목표로 한 태스크

# Week5-6 Adaptive RAG E2E Core Action Plan

## 원칙 고정
- 범위: Adaptive RAG 코어 로직 구현 + Streamlit 데모 관통 연결
- 제외: 지표 측정/리포트, 모델 벤치마크, 리팩토링, 예외 처리 고도화
- 목표: 입력 질의가 analyzer -> router -> retrieval -> generation -> UI까지 전략 정보를 유지하며 출력되도록 구현

## Core Module Deep-dive Task 5

### 1) Input Analyzer 모듈 구현 (LengthAnalyzer + TopicAnalyzer + MultiRequestDetector)
- 핵심 클래스
  - `LengthAnalyzer.analyze(text) -> {word_count, length_bucket}`
  - `TopicAnalyzer.classify(text, category, entity_labels) -> topic_type`
  - `MultiRequestDetector.detect(text) -> {is_multi, request_segments}`
- 구현 포인트
  - 검색/QA 시작 시 1회 분석 후 `analysis_meta`로 고정
  - `length_bucket`: short/medium/long
  - `topic_type`: field_ops/admin_policy
  - `is_multi`: bool, `request_segments`: list[str]
- 기대 결과
  - 이후 모든 체인에서 동일 메타데이터를 재사용 가능

### 2) AdaptiveRouter + Strategy Registry 구현
- 핵심 클래스
  - `AdaptiveRouter.route(length_bucket, topic_type, is_multi)`
  - `LengthStrategyProfile` / `TopicStrategyProfile`
- 구현 포인트
  - route key: `(length_bucket, topic_type, is_multi)`
  - 반환: `strategy_id`, `profile`, `routing_trace`
  - retrieval/qa 응답에 `routing_trace`를 항상 포함
- 기대 결과
  - 검색 단계에서 선택된 전략이 생성/화면까지 유지됨

### 3) Length/Topic Adaptive Retrieval 구현
- 핵심 함수
  - `RetrievalService.search(..., routing_hint=None)`
  - `build_snippet_by_strategy(result, profile)`
- 구현 포인트
  - short/medium/long별 `top_k`, `chunk_policy`, `snippet_max_chars` 분기
  - field_ops/admin_policy별 필터 우선순위와 snippet 추출 기준 분리
  - 결과 metadata에 `topic_type`, `strategy_id`, `route_key` 주입
- 기대 결과
  - 같은 질의라도 분기 상태에 맞는 결과 구성 가능

### 4) Topic-aware PromptFactory + normalize_response 구현
- 핵심 클래스/함수
  - `PromptFactory.build(query, context, routing_trace)`
  - `normalize_response(payload) -> unified schema`
- 구현 포인트
  - topic별 프롬프트 문맥 분기(field_ops vs admin_policy)
  - long 버킷일 때 "핵심 이슈 우선 추출" 지시 자동 삽입
  - `structured_output.request`를 항상 list로 통일
- 기대 결과
  - FE가 단일/복합 응답을 같은 렌더링 경로로 처리 가능

### 5) API-UI E2E 관통 연결
- 핵심 연결 지점
  - `/search` 응답: `routing_trace`
  - `/qa` 요청/응답: `routing_hint`/`routing_trace` + `structured_output`
  - Streamlit: adaptive 배지 + multi-request 패널
- 구현 포인트
  - 검색에서 받은 trace를 QA 요청 payload로 그대로 전달
  - 화면에 length/topic/multi/strategy_id를 노출
  - 결과 카드/답변 패널/citations 순서를 고정
- 기대 결과
  - 데모 중 전략 선택 근거가 화면에서 즉시 확인 가능

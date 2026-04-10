# [PRD] 민원 담당자를 위한 Adaptive RAG Workbench 시스템

문서 버전: v2.1  
작성일: 2026-03-17  
최신화: 2026-04-10 (복잡도 기반 라우팅 기준 반영)

## 1. 문서 목적

본 문서는 Week5-8 개발 범위를 Adaptive RAG 코어 로직 구현 및 데모 UI 완성에 집중하도록 고정한다.

## 2. 프로젝트 개요

- 목표: 민원 데이터를 Adaptive RAG로 처리하고, 담당자 워크벤치에서 근거 기반 답변 초안을 제공한다.
- 환경: 로컬/온디바이스 우선.
- 집중 범위: Analyzer -> Router -> Retrieval -> Generation -> Workbench E2E.

## 3. 성공 조건 (데모 중심)

- 민원 선택 후 adaptive 처리 결과가 UI에서 확인된다.
- 유사 민원 근거와 답변 초안이 같은 화면 흐름에서 출력된다.
- 단일/복합 요청 케이스 모두 워크벤치에서 처리된다.

## 4. 사용자

### 4.1 민원 담당 공무원
- 빠른 요약 확인
- 유사 사례 참고
- 답변 초안 검토/편집

### 4.2 관리자
- 처리 상태 확인
- 시연용 운영 흐름 점검

## 5. 범위 정의

### 5.1 In Scope

- TopicAnalyzer, ComplexityAnalyzer (복잡도 지표 기반)
- AdaptiveRouter(route key: topic/complexity)
- Topic/Complexity adaptive retrieval
- Topic-aware PromptFactory
- normalize_response 기반 unified output
- FastAPI + React/Next.js 3단 Workbench UI

### 5.2 Out of Scope

- 추가적인 지표 벤치마크 작업
- 지표 산출 리포트 확장 작업
- 리팩토링 중심 작업
- 실제 행정시스템 실연동
- 모바일 네이티브 앱

## 6. 핵심 유스케이스

### UC-01: Adaptive 검색/생성
- 입력: 민원 텍스트 또는 선택된 민원
- 처리: analyzer -> router -> retrieval -> generation
- 출력: 답변 초안 + citation + routing_trace

### UC-02: Workbench 검토
- 입력: UC-01 결과
- 처리: 우측 AI 패널 표시 + 초안 편집
- 출력: 검토 가능한 답변 초안

## 7. 기능 요구사항

### FR-1 Analyzer
- 주제(`topic_type`)와 복잡도(`complexity_level`, `complexity_score`)를 metadata로 반환한다.
- 복잡도 산출 근거(`complexity_trace`)를 함께 반환한다.

### FR-2 Router
- `(topic_type, complexity_level)` 기반 전략을 선택한다.

### FR-3 Retrieval
- 전략별 파라미터를 적용해 검색 결과와 trace를 반환한다.

### FR-4 Generation
- topic-aware prompt를 사용해 답변을 생성한다.
- normalize_response로 unified schema를 반환한다.

### FR-5 API 계약
- `/search`는 `routing_trace`를 반환한다.
- `/qa`는 `routing_hint`를 수신하고 `routing_trace`를 반환한다.

### FR-6 UI/UX
- 3단 분할 Workbench를 제공한다.
  - 좌측: 네비게이션
  - 중앙: 민원 목록/상태
  - 우측: AI 패널(요약, 유사 민원, 답변 초안, citation, 편집)

## 8. 비기능 요구사항

- 보안: 로컬 처리 원칙 유지
- 안정성: 데모 시나리오 연속 동작 보장
- 유지보수성: 모듈 경계와 API 계약 고정

## 9. 시스템 아키텍처

1. Ingestion/Structuring
2. Adaptive Analyzer
3. Adaptive Router
4. Retrieval
5. Generation
6. FastAPI API Layer
7. Next.js Workbench Layer

## 9.1 데이터 기반 Adaptive RAG 설계 (실행 기준)

### 9.1.1 Input Analyzer
- `TopicAnalyzer`
- `ComplexityAnalyzer`
- (보조) `MultiRequestDetector`
- 출력: `{topic_type, complexity_level, complexity_score, complexity_trace, request_segments}`

### 9.1.2 Router
- `AdaptiveRouter`
- route key: `(topic_type, complexity_level)`
- 출력: `{strategy_id, route_key, routing_trace}`

### 9.1.3 Retrieval
- `TopicAdaptiveRetriever`
- `ComplexityAdaptiveRetriever`
- 결과 metadata에 `strategy_id`, `topic_type`, `complexity_level` 포함

### 9.1.4 Generation
- `PromptFactory`
- `normalize_response()`
- unified output: `answer`, `citations`, `limitations`, `structured_output`, `routing_trace`

## 10. 주차 전략 (현재 시점)

- Week1-4: 완료 사인오프
- Week5-6: Adaptive 코어 모듈 구현
- Week7-8: Workbench 통합 및 데모 동결

## 11. 역할 분담

- FE: Next.js Workbench UX
- BE1: Analyzer
- BE2: Router/Retrieval
- BE3: Generation/API 통합

## 12. 완료 판정

- 특정 민원 선택 -> adaptive 처리 -> 답변 초안 + citation UI 출력이 연속 동작하면 완료로 판단한다.

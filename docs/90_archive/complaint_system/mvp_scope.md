# MVP 범위 문서 (Adaptive RAG Demo Focus)

문서 버전: v2.1  
작성일: 2026-03-11  
최신화: 2026-04-10 (복잡도 기반 라우팅 기준 반영)

## 1. 문서 목적

본 문서는 남은 기간에서 반드시 완성해야 할 MVP를 "동작하는 데모" 기준으로 재정의한다. 핵심은 특정 민원 입력 시 Workbench에서 답변과 citation이 출력되는 E2E 흐름이다.

## 2. MVP 정의 원칙

- 구현 우선순위는 코어 모듈 동작과 UI 연동 순서로 정한다.
- 측정 지표 개선보다 사용자가 확인 가능한 결과 출력을 우선한다.
- 백엔드 분기 정보가 화면에서 설명 가능하게 노출되어야 한다.
- 기능 추가보다 데모 시나리오 완주율을 우선한다.

## 3. MVP 한 줄 정의

"민원 1건을 선택해 Adaptive RAG로 처리하고, Workbench 우측 패널에 답변 초안과 citation을 즉시 확인/검토할 수 있는 통합 데모 시스템"

## 4. 포함 범위

### 4.1 필수 기능

| 구분 | 필수 항목 | 완료 관점 |
| --- | --- | --- |
| Analyzer | TopicAnalyzer, ComplexityAnalyzer, MultiRequestDetector(보조) | 입력 민원별 routing metadata 생성 |
| Router | AdaptiveRouter | topic/complexity route key 기준 전략 선택/trace 생성 |
| Retrieval | Topic/Complexity 분기 검색 | strategy별 결과 반환 및 metadata 포함 |
| Generation | Topic-aware PromptFactory, normalize_response | unified schema 반환 |
| API | `/search`, `/qa` adaptive 필드 전달 | routing_trace/routing_hint 일관 전달 |
| FE | Next.js 3단 Workbench | 좌-중-우 구조에서 결과 가시화 |
| UX | 답변/근거/제약/편집 동선 | 담당자 검토 흐름 완주 |

### 4.2 제외/후순위

- 추가 지표 산출 자동화
- 추가 벤치마크 캠페인
- 리팩토링 전용 작업
- 대시보드 고급 통계 시각화

## 5. 화면 기준 MVP

## 5.1 좌측 네비게이션
- 민원 선택
- 워크벤치 진입
- 관리자 대시보드 진입

## 5.2 중앙 민원 리스트
- 실시간 민원 목록
- 처리 상태(대기/진행/검토완료)
- 선택 민원 상세 진입

## 5.3 우측 AI 패널
- 요약
- 유사 민원 검색 결과
- 답변 초안
- citation
- 답변 초안 편집

## 6. 기술 스택(최종)

| 영역 | 선택 |
| --- | --- |
| API | FastAPI |
| FE | React/Next.js |
| Retrieval | ChromaDB + adaptive retrieval strategy |
| Generation | Ollama + PromptFactory |

## 7. 팀별 MVP 책임

### FE
- Next.js 3단 Workbench 구현
- routing trace/응답 결과 시각화
- 답변 초안 검토/편집 UI

### BE1
- Analyzer 모듈 구현 및 metadata 제공

### BE2
- AdaptiveRouter(topic+complexity) + retrieval 분기 구현

### BE3
- PromptFactory + normalize_response + `/qa` 통합

## 8. MVP 완료 정의 (Definition of Done)

아래 조건을 모두 만족하면 MVP 완료로 간주한다.

1. 사용자가 민원 1건을 선택하면 analyzer 결과(topic/complexity/segment)가 생성된다.
2. 검색 단계에서 adaptive 전략이 선택되고 `routing_trace`가 응답에 포함된다.
3. QA 단계에서 `routing_hint`를 받아 답변과 citation을 생성한다.
4. Workbench 우측 패널에서 답변 초안과 citation이 표시된다.
5. 사용자가 답변 초안을 검토/수정할 수 있다.
6. 위 1-5가 동일 데모 흐름에서 중단 없이 연속 동작한다.

## 9. 실행 우선순위

1. Analyzer/Router 구현
2. Retrieval/Generation adaptive 연결
3. API 계약 필드 고정
4. Next.js Workbench 3단 레이아웃 구현
5. E2E 시나리오 3종 고정 및 동결

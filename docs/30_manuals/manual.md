# Week5-8 실행 매뉴얼 (파트별 역할/산출물 가이드)

문서 버전: v1.1  
작성일: 2026-04-10  
기준 문서:
- 이전: `previous_prd.md`, `previous_wbs_8weeks_v2_updated.md`
- 현재: `docs/00_overview/prd.md`, `docs/00_overview/wbs_8weeks_v2_updated.md`

---

## 1) 이 매뉴얼의 목적

이 문서는 팀원/비팀원 누구나 현재 프로젝트 진행 상태를 이해하고,  
**각 파트(FE/BE1/BE2/BE3)가 지금까지 무엇을 했는지 / 앞으로 무엇을 해야 하는지 / 주차별로 무엇을 산출해야 하는지**를 한 번에 확인하도록 만든 실행 가이드다.

---

## 2) 이전 계획 → 현재 계획 변화 요약 (핵심)

## 2.1 방향 전환 요약

- 이전(Week1~4 중심):  
  - Streamlit 기반 빠른 PoC/벤치마크/지표 중심 운영 비중이 컸음
  - 단일 RAG baseline 확정까지 포함
- 현재(Week5~8 중심):  
  - **FastAPI + Next.js 3단 Workbench + Adaptive RAG E2E 데모 완주**가 최우선
  - 지표 확장/리팩토링 중심 작업은 범위 밖(지양)

## 2.2 반드시 고정할 계약

- `/search` 응답: `routing_trace`, `routing_hint`, `strategy_id`, `route_key`
- `/qa` 요청: `routing_hint`
- `/qa` 응답: `routing_trace`, `structured_output`, `answer`, `citations`, `limitations`

---

## 3) 현재까지 완료된 것 (공통 인식)

- Week1~4 완료 사인오프
- 단일 RAG + baseline 구간 종료
- Week5 실행 문서(규칙/스펙/이슈) 생성 완료
  - `.clinerules`
  - `docs/specs/*` (api/data/ui)
  - `issues/week5/*` (FE/BE1/BE2/BE3 작업지시)

즉, 현재는 “기획/탐색 단계”가 아니라 **Week5~8 구현/통합/동결 단계**다.

---

## 4) 파트별 기능 정의 (비전공자도 이해 가능한 형태)

## 4.1 FE (도훈) — “보여주고 조작하는 화면 책임”

### 지금까지
- Workbench 3단 구조 요구사항 확정
- `/search` → `/qa` 흐름에서 라우팅 정보 표시 요구사항 정리

### 앞으로 해야 할 일
- 좌측 네비, 중앙 민원목록, 우측 AI패널 고정 구현
- 검색 결과에서 `complexity_level`, `complexity_score`, `strategy_id` 노출
- QA 생성 시 `routing_hint` 유지 전달
- 답변 초안 편집/검토완료 UX 완성

### 주차 산출물
- W5: 길이 라우팅 표시 UI + 3단 레이아웃 스캐폴딩
- W6: topic/multi 뱃지 + 복합요청 렌더 분기
- W7: 상태 UX 4종(success/loading/error/empty) 통일 + E2E 화면 고정
- W8: 시연 클릭 동선 3종 고정(문서와 동일)

---

## 4.2 BE1 (현기) — “입력 민원을 기계가 이해할 수 있게 분석”

### 지금까지
- 구조화/검증 기반 정제 흐름 완료(Week1~4 범위)

### 앞으로 해야 할 일
- TopicAnalyzer, ComplexityAnalyzer, MultiRequestDetector(보조) 고정
- 출력 키 통일:
- `topic_type`
- `complexity_level`
- `complexity_score`
- `complexity_trace`
- `request_segments`

### 주차 산출물
- W5: `LengthAnalyzer.analyze`, `MultiRequestDetector.detect` 1차 구현
- W6: `TopicAnalyzer.classify` 구현 + Analyzer 통합 출력 확정
- W7: 중앙 리스트용 요약 필드 공급
- W8: 로그/추적 최소 세트 유지, 스키마 변경 금지

---

## 4.3 BE2 (민건) — “어떤 검색 전략을 쓸지 결정하고 검색 실행”

### 지금까지
- 검색/인덱싱 기반 확보(Week1~4 범위)

### 앞으로 해야 할 일
- `AdaptiveRouter`로 `topic_type + complexity_level` 기반 전략 선택
- 복잡도 레벨(low/medium/high)에 따라 retrieval 파라미터 분기
- retrieval trace를 FE가 해석 가능하게 제공(`complexity_trace` 포함)

### 주차 산출물
- W5: `AdaptiveRouter.route(topic_type, complexity_level, complexity_score)` 1차
- W6: topic_type별 retrieval 분기 + `applied_filters` trace
- W7: 우측 패널용 유사 민원 API 응답 형식 고정
- W8: 시연 안정화 로그 유지, 버그 픽스만 허용

---

## 4.4 BE3 (현석) — “답변 생성과 API 최종 통합 책임”

### 지금까지
- `/qa` 파싱 안정화 및 baseline 생성 흐름 경험 확보(Week1~4 범위)

### 앞으로 해야 할 일
- `/search`에 `routing_trace` 통합
- `/qa`가 `routing_hint`를 받아 동일 전략으로 생성
- `PromptFactory` + `normalize_response`로 unified output 고정

### 주차 산출물
- W5: `/search` trace 통합, `/qa` hint 수신 경로 연결
- W6: `PromptFactory.build`, `normalize_response` 확정
- W7: 편집 가능한 응답 스키마(답변/근거/제약) 고정
- W8: 최종 스키마 동결 + 데모 안정화

---

## 5) 주차별 공통 산출물 정의 (Week5~8)

## Week5 (Complexity Adaptive Core)
- 공통 목표: 복잡도 기반 전략 분기가 실제 검색/생성/화면에 반영
- 공통 산출물:
- Analyzer 복잡도 분류
  - Router 1차 전략 결정
  - `/search`/`/qa` 간 `strategy_id` 일치
  - 화면에서 `routing_trace` 확인 가능

## Week6 (Topic/Multi + Unified Output)
- 공통 목표: 주제/복합 분기 + 생성 응답 정규화
- 공통 산출물:
  - topic/multi 분석 결과 반영
  - retrieval 분기 trace 강화
  - `/qa` 응답에 `structured_output` 일관 제공

## Week7 (3단 Workbench E2E 고정)
- 공통 목표: FastAPI ↔ Next.js 완전 관통
- 공통 산출물:
  - 단일 민원 선택 후 우측 패널에 답변+citation 생성
  - 답변 편집 가능
  - 상태 UX 4종 통일

## Week8 (동결/리허설/발표 준비)
- 공통 목표: 기능 추가 중단, 데모 성공률 극대화
- 공통 산출물:
  - 시나리오 3종 연속 실행
  - 코드/문서/시연 동선 동결
  - 버그 픽스 외 변경 금지

---

## 6) 파트 간 인터페이스 체크리스트 (매주 공통)

- [ ] `/search` 응답에 `routing_trace`가 있는가
- [ ] `/qa` 요청에 `routing_hint`를 반드시 넣는가
- [ ] `/qa` 응답에 `structured_output`이 있는가
- [ ] FE 카드/패널이 `strategy_id`, `complexity_level`, `complexity_score`를 렌더하는가
- [ ] 단일/복합 입력 모두 동일 흐름으로 동작하는가

---

## 7) 8주 종료 시 최종 산출물 (필수)

## 7.1 기능 산출물
1. FastAPI + Next.js 3단 Workbench 통합 데모
2. Analyzer→Router→Retrieval→Generation E2E 파이프라인
3. `/search`, `/qa` 계약 필드 고정 구현 (`routing_trace`, `routing_hint`, `structured_output`)

## 7.2 문서 산출물
1. 최신 PRD/WBS/폴더구조/스펙 문서 정합본
2. 파트별 이슈 수행 결과 정리본
3. 시연 시나리오/운영 체크리스트

## 7.3 시연 산출물
1. 단일/복합/예외 시나리오 3종 실행 스크립트
2. 발표용 화면 동선 문서(클릭 순서 고정)
3. 리허설 기록(실패 원인/수정 내역 포함)

---

## 8) 완료 판정 기준 (최종)

아래를 모두 만족하면 Week8 종료/프로젝트 완료로 본다.

1. 민원 선택 → adaptive 처리 → 답변 초안 + citation 표시가 중단 없이 동작
2. 검색/생성 단계에서 동일 `strategy_id` 추적 가능
3. `/qa` 응답에서 `routing_trace`, `structured_output` 일관 제공
4. 답변 초안 편집 및 검토완료 처리 가능
5. 시나리오 3종 연속 실행 성공(동결 버전 기준)

---

## 9) 운영 원칙 재확인 (중요)

- Week5-8은 **데모 완주율**이 최우선
- 지표 확장, 추가 벤치마크, 리팩토링 중심 작업은 수행하지 않음
- 계약 필드 누락은 기능 완료로 인정하지 않음